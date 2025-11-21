"""
LanceDB-based semantic search provider.

Implements SemanticSearchProtocol using LanceDB for vector storage
and hybrid search (vector + full-text).
"""

import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional
from contextlib import contextmanager

import lancedb
import fasteners
from lancedb.pydantic import LanceModel, Vector
from lancedb.embeddings import get_registry

from .protocols import (
    CodeChunk,
    CodeChunkerProtocol,
    SemanticSearchProtocol,
    SearchResult
)

logger = logging.getLogger(__name__)

# --- Configuration Constants ---
DB_DIR_NAME = ".lancedb"
LOCK_FILE_NAME = "update.lock"
TABLE_NAME = "code_chunks"
EMBEDDING_MODEL = "jinaai/jina-embeddings-v2-base-code"
TOKEN_ESTIMATION_CHAR_RATIO = 3.0
BATCH_SIZE = 1000
MIN_CHUNK_SIZE = 20  # Skip very small chunks


class IndexingError(Exception):
    """Custom exception for user-facing indexing failures."""
    pass


# --- Setup Embedding Function ---
embedding_func = get_registry().get("fastembed").create(name=EMBEDDING_MODEL)


class CodeSchema(LanceModel):
    """Schema for storing code chunks with vector embeddings."""
    id: str                 # Composite: "path:start_line"
    file_path: str          # Normalized POSIX path
    start_line: int
    end_line: int
    content_hash: str       # MD5 hash for change detection
    content: str = embedding_func.SourceField()
    vector: Vector(embedding_func.ndims()) = embedding_func.VectorField()


class LanceDBSearchProvider:
    """
    LanceDB-based semantic search provider.

    Implements SemanticSearchProtocol using LanceDB for vector storage,
    hybrid search (vector + FTS), and incremental updates.

    Key features:
    - Incremental indexing (only updates changed files)
    - File locking (prevents race conditions)
    - Graceful error handling
    - Windows path normalization
    - Security (path traversal prevention)
    """

    def __init__(
        self,
        project_path: Path,
        chunker: CodeChunkerProtocol,
        db_dir_name: str = DB_DIR_NAME,
        lock_timeout: int = 300,  # 5 minutes (large repos need time)
    ):
        """
        Initialize search provider (NO I/O in constructor).

        Args:
            project_path: Project root path
            chunker: Code chunking strategy (INJECTED)
            db_dir_name: Database directory name
            lock_timeout: Lock acquisition timeout in seconds
        """
        self._project_path = project_path.resolve()
        self._chunker = chunker  # Injected dependency
        self._db_path = self._project_path / db_dir_name
        self._lock_path = self._db_path / LOCK_FILE_NAME
        self._lock_timeout = lock_timeout

        # Lazy initialization
        self._db = None

    def _ensure_db(self):
        """Lazy DB initialization (creates directory and connects)."""
        if self._db is None:
            self._db_path.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(self._db_path)

    # --- Helper: Path Normalization & Security ---

    def _normalize_path(self, raw_path: str) -> str:
        """
        Normalize paths to POSIX style and ensure within project root.

        Prevents path traversal attacks (e.g., "../../../etc/passwd").

        Args:
            raw_path: Raw path from user/filesystem

        Returns:
            Normalized POSIX path relative to project root

        Raises:
            ValueError: If path is outside project root
            IndexingError: If path is malformed
        """
        try:
            # Resolve handles symlinks and absolute paths
            full_path = (self._project_path / raw_path).resolve()
        except OSError as e:
            logger.error(f"Invalid path structure: {raw_path}")
            raise IndexingError(f"Path invalid: {raw_path}") from e

        # Security Check: Ensure file is actually inside the project
        if not full_path.is_relative_to(self._project_path):
            logger.warning(f"Security: Attempted access outside root: {raw_path}")
            raise ValueError(f"Security: File outside project root: {raw_path}")

        # Return POSIX path relative to root (e.g., "src/main.py")
        return full_path.relative_to(self._project_path).as_posix()

    def _compute_hash(self, text: str) -> str:
        """Fast hash for content change detection."""
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    # --- Helper: Safe Context Manager ---

    @contextmanager
    def _safe_db_context(self, timeout: Optional[int] = None):
        """
        Acquire file lock to prevent race conditions.

        Multiple CLI instances can't update index simultaneously.

        Args:
            timeout: Lock timeout in seconds (None = use default)

        Raises:
            IndexingError: If lock cannot be acquired
        """
        timeout = timeout or self._lock_timeout
        lock = fasteners.InterProcessLock(self._lock_path)
        got_lock = lock.acquire(blocking=True, timeout=timeout)

        if not got_lock:
            raise IndexingError(
                "Database locked by another process. "
                "Please wait or check for stuck processes."
            )

        try:
            yield
        except lancedb.db.LanceError as e:
            # Handle internal LanceDB corruption or errors
            raise IndexingError(f"Search engine error: {e}")
        finally:
            try:
                lock.release()
            except Exception:
                pass  # Best effort

    # --- Core: Indexing ---

    def index_files(self, files: Dict[str, str]) -> None:
        """
        Index files for semantic search (incremental updates).

        Implements SemanticSearchProtocol.

        Strategy:
        1. Snapshot current DB state (path -> hash)
        2. Diff against filesystem state
        3. Remove stale entries (deleted/modified files)
        4. Add new entries (new/modified files)
        5. Update FTS index

        Args:
            files: Dict mapping file paths to content

        Raises:
            IndexingError: If indexing fails
        """
        self._ensure_db()

        with self._safe_db_context():
            table_exists = TABLE_NAME in self._db.table_names()

            if not table_exists:
                self._create_and_populate(files)
                return

            table = self._db.open_table(TABLE_NAME)

            # 1. Snapshot current DB state (Path -> Hash)
            db_state = {}
            try:
                for batch in table.search().select(["file_path", "content_hash"]).to_batches():
                    df = batch.to_pandas()
                    for _, row in df.iterrows():
                        db_state[row["file_path"]] = row["content_hash"]
            except Exception:
                # Schema mismatch or corruption - rebuild
                logger.warning("Could not read existing index. Rebuilding...")
                self._create_and_populate(files)
                return

            # 2. Calculate Diff
            files_to_add = {}     # {path: content}
            paths_to_remove = []  # [path]

            # Check filesystem against DB
            for raw_path, content in files.items():
                try:
                    norm_path = self._normalize_path(raw_path)
                except ValueError:
                    continue  # Skip unsafe paths

                current_hash = self._compute_hash(content)

                # If new or modified
                if norm_path not in db_state or db_state[norm_path] != current_hash:
                    files_to_add[norm_path] = content
                    if norm_path in db_state:
                        paths_to_remove.append(norm_path)

            # Check DB against filesystem (detect deletions)
            fs_paths_set = set()
            for p in files:
                try:
                    fs_paths_set.add(self._normalize_path(p))
                except ValueError:
                    pass

            for db_path in db_state:
                if db_path not in fs_paths_set:
                    paths_to_remove.append(db_path)

            # 3. Apply Updates
            if not files_to_add and not paths_to_remove:
                logger.debug("Index is up to date")
                return

            logger.info(
                f"Updating index: +{len(files_to_add)} modified, "
                f"-{len(paths_to_remove)} deleted"
            )

            # Remove stale entries
            if paths_to_remove:
                table.delete("file_path IN (@paths)", {"paths": paths_to_remove})

            # Add new entries
            if files_to_add:
                self._add_files_in_batches(table, files_to_add)

                # Update FTS index
                # replace=True is expensive but ensures consistency
                table.create_fts_index("content", replace=True)

            table.cleanup_old_versions()

    def _create_and_populate(self, files: Dict[str, str]):
        """Create table from scratch."""
        # Drop if exists
        if TABLE_NAME in self._db.table_names():
            self._db.drop_table(TABLE_NAME)

        table = self._db.create_table(TABLE_NAME, schema=CodeSchema)

        # Normalize keys
        valid_files = {}
        for k, v in files.items():
            try:
                valid_files[self._normalize_path(k)] = v
            except ValueError:
                pass

        self._add_files_in_batches(table, valid_files)
        table.create_fts_index("content", replace=True)

    def _add_files_in_batches(self, table, files: Dict[str, str]):
        """Chunk content and add to DB in batches (memory efficient)."""
        batch = []

        for norm_path, content in files.items():
            try:
                chunks = self._chunker.chunk(norm_path, content)
                lines = content.splitlines()
                file_hash = self._compute_hash(content)

                for chunk in chunks:
                    chunk_text = '\n'.join(lines[chunk.start_line - 1:chunk.end_line])

                    # Skip very small chunks (noise)
                    if len(chunk_text) < MIN_CHUNK_SIZE:
                        continue

                    batch.append({
                        "id": f"{norm_path}:{chunk.start_line}",
                        "file_path": norm_path,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "content_hash": file_hash,
                        "content": chunk_text,
                    })

                    if len(batch) >= BATCH_SIZE:
                        table.add(batch)
                        batch = []

            except Exception as e:
                logger.error(f"Failed to chunk/index file {norm_path}: {e}")

        if batch:
            table.add(batch)

    # --- Core: Retrieval ---

    def search(
        self,
        query: str,
        max_results: int = 25,
        max_tokens: int = 4000
    ) -> SearchResult:
        """
        Search indexed files semantically.

        Implements SemanticSearchProtocol.

        Uses hybrid search: vector similarity + full-text search.
        Falls back to vector-only if FTS fails.

        Args:
            query: Search query
            max_results: Maximum results to return
            max_tokens: Token budget for results

        Returns:
            SearchResult with chunks and metadata
        """
        if not self.is_indexed():
            return SearchResult(chunks=[], tokens_used=0, limit_hit=None)

        table = self._db.open_table(TABLE_NAME)

        # Hybrid Search: Vector (semantic) + FTS (keyword)
        try:
            results = (
                table.search(query, query_type="hybrid")
                .limit(max_results)
                .to_list()
            )
        except Exception as e:
            # Fallback if FTS index broken or missing
            logger.warning(f"Hybrid search failed ({e}), falling back to vector search")
            results = table.search(query, query_type="vector").limit(max_results).to_list()

        final_chunks = []
        used_tokens = 0
        limit_hit = None

        # Deduplication: (file_path, start_line)
        seen_chunks = set()

        for row in results:
            chunk_id = (row['file_path'], row['start_line'])
            if chunk_id in seen_chunks:
                continue

            content = row['content']
            # Rough token estimation
            cost = int(len(content) / TOKEN_ESTIMATION_CHAR_RATIO)

            if used_tokens + cost > max_tokens:
                limit_hit = 'token_limit'
                break

            final_chunks.append({
                'path': row['file_path'],
                'lines': (row['start_line'], row['end_line']),
                'content': content,
                'score': row.get('_score', 0.0)
            })
            used_tokens += cost
            seen_chunks.add(chunk_id)

        return SearchResult(
            chunks=final_chunks,
            tokens_used=used_tokens,
            limit_hit=limit_hit
        )

    def is_indexed(self) -> bool:
        """
        Check if files have been indexed.

        Implements SemanticSearchProtocol.

        Returns:
            True if index exists and is usable
        """
        try:
            self._ensure_db()
            return TABLE_NAME in self._db.table_names()
        except Exception:
            return False

    def clear_index(self) -> None:
        """
        Clear the search index.

        Implements SemanticSearchProtocol.
        """
        self._ensure_db()
        with self._safe_db_context():
            if TABLE_NAME in self._db.table_names():
                self._db.drop_table(TABLE_NAME)
