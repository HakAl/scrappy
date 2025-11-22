"""
LanceDB-based semantic search provider.

Implements SemanticSearchProtocol using LanceDB for vector storage
and hybrid search (vector + full-text).
"""

import hashlib
import logging
from pathlib import Path
from typing import Dict, Optional
from contextlib import contextmanager

# Use simple imports to avoid circular dependency messes
try:
    import lancedb
    import fasteners
    from lancedb.pydantic import LanceModel, Vector
    from lancedb.embeddings import get_registry
except ImportError:
    lancedb = None

from ..protocols import CodeChunkerProtocol, SearchResult
from ...infrastructure.protocols import ProgressReporterProtocol

logger = logging.getLogger(__name__)

# --- Configuration Constants ---
DB_DIR_NAME = ".lancedb"
LOCK_FILE_NAME = "update.lock"
TABLE_NAME = "code_chunks"
TOKEN_ESTIMATION_CHAR_RATIO = 3.0
BATCH_SIZE = 64  # Larger batches for efficiency (now thread-safe)
MIN_CHUNK_SIZE = 20  # Skip very small chunks


class IndexingError(Exception):
    """Custom exception for user-facing indexing failures."""
    pass


# --- Lazy Embedding Function Setup ---
# NOTE: JinaEmbedFunction is registered at module import (fast, metadata only)
# The actual TextEmbedding model is created when .create() is called (lazy)


def _create_embedding_func():
    """
    Create embedding function (called lazily on first use).

    Uses the custom fastembed-jina embedding function registered in embeddings.py.
    This provides Jina AI's code-optimized embeddings via FastEmbed.

    Returns:
        Initialized embedding function instance

    Raises:
        Exception: If fastembed-jina is not available or initialization fails
    """
    # Import here to ensure JinaEmbedFunction is registered
    from .embeddings import JinaEmbedFunction  # noqa: F401
    return get_registry().get("fastembed-jina").create()


def _create_code_schema():
    """
    Create schema for code chunks with embeddings.

    Returns:
        CodeSchema class for LanceDB table
    """
    class CodeSchema(LanceModel):
        """Schema for storing code chunks with vector embeddings."""
        id: str                 # Composite: "path:start_line"
        file_path: str          # Normalized POSIX path
        start_line: int
        end_line: int
        content_hash: str       # MD5 hash for change detection
        content: str            # Chunk text
        vector: Vector(384)     # Manually computed embeddings (384-dim for BGE-small)

    return CodeSchema


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
    - Custom FastEmbed + Jina embeddings for code understanding

    Architecture:
    - Follows SOLID principles (dependency injection, single responsibility)
    - Lazy initialization (no I/O in constructor)
    - Protocol-based design (easy to test and swap implementations)
    """

    def __init__(
        self,
        project_path: Path,
        chunker: CodeChunkerProtocol,
        db_dir_name: str = DB_DIR_NAME,
        lock_timeout: int = 300,  # 5 minutes (large repos need time)
        progress_reporter: Optional[ProgressReporterProtocol] = None,
    ):
        """
        Initialize search provider (NO I/O in constructor).

        Args:
            project_path: Project root path
            chunker: Code chunking strategy (INJECTED)
            db_dir_name: Database directory name
            lock_timeout: Lock acquisition timeout in seconds
            progress_reporter: Progress reporter for indexing operations (INJECTED)
        """
        self._project_path = project_path.resolve()
        self._chunker = chunker  # Injected dependency
        self._db_path = self._project_path / db_dir_name
        self._lock_path = self._db_path / LOCK_FILE_NAME
        self._lock_timeout = lock_timeout

        # Lazy initialization
        self._db = None
        self._embedding_func = None
        self._code_schema = None

        # Progress reporter (defaults to NullProgressReporter if not provided)
        if progress_reporter is None:
            from ...infrastructure.progress import NullProgressReporter
            progress_reporter = NullProgressReporter()
        self._progress = progress_reporter

    def set_progress_reporter(self, progress_reporter: ProgressReporterProtocol) -> None:
        """
        Set or update the progress reporter.

        Args:
            progress_reporter: Progress reporter to use for indexing operations
        """
        self._progress = progress_reporter

    def _ensure_db(self):
        """Lazy DB initialization (creates directory and connects)."""
        if self._db is None:
            self._db_path.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(self._db_path)

    def _ensure_schema(self):
        """
        Lazy schema initialization (creates embedding func and schema).

        Raises:
            IndexingError: If fastembed is not available or initialization fails
        """
        if self._code_schema is None:
            try:
                logger.debug("Initializing embedding function (may take 10-30s on first use)...")
                self._embedding_func = _create_embedding_func()

                # Ensure the model is fully loaded by generating a test embedding
                # This ensures the heavy model loading happens here, not later
                try:
                    _ = self._embedding_func.generate_embeddings(["test"])
                    logger.debug("Embedding model is fully loaded")
                except Exception as e:
                    logger.warning(f"Error during test embedding generation: {e}")

                self._code_schema = _create_code_schema()
                logger.debug("Embedding function initialized")
            except Exception as e:
                raise IndexingError(
                    f"Failed to initialize embedding function. "
                    f"Make sure semantic search dependencies are installed: "
                    f"pip install fastembed lancedb. "
                    f"Error: {e}"
                ) from e

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
        except Exception as e:
            # Handle internal LanceDB errors (catch-all since LanceDB doesn't have specific exception types)
            if "lance" in str(type(e)).lower() or "table" in str(e).lower():
                raise IndexingError(f"Search engine error: {e}")
            raise  # Re-raise if not a LanceDB error
        finally:
            try:
                lock.release()
            except Exception:
                pass  # Best effort

    # --- Core: Indexing ---

    def index_files(self, files: Dict[str, str], is_batch: bool = False) -> None:
        """
        Index files for semantic search (incremental updates).

        Implements SemanticSearchProtocol.

        Strategy:
        1. Snapshot current DB state (path -> hash)
        2. Diff against filesystem state
        3. Remove stale entries (deleted/modified files) - SKIPPED if is_batch=True
        4. Add new entries (new/modified files)
        5. Update FTS index

        Args:
            files: Dict mapping file paths to content
            is_batch: If True, skip deletion detection (for batched indexing)

        Raises:
            IndexingError: If indexing fails
        """
        # Early logging to see if we're even called
        logger.info(f"index_files called with {len(files)} files")

        if not files:
            logger.warning("No files provided for indexing")
            return

        self._ensure_db()
        self._ensure_schema()  # Lazy-initialize embedding function and schema

        with self._safe_db_context():
            table_exists = TABLE_NAME in self._db.table_names()
            logger.debug(f"Table exists: {table_exists}")

            if not table_exists:
                logger.info("Creating new index table")
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
            except Exception as e:
                # Schema mismatch or corruption - rebuild
                logger.warning(f"Could not read existing index ({type(e).__name__}: {e}). Rebuilding...")
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
            # SKIP during batched indexing to avoid deleting files from previous batches
            if not is_batch:
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
                # Build SQL with quoted strings for safety
                paths_sql = ", ".join(f"'{path}'" for path in paths_to_remove)
                table.delete(f"file_path IN ({paths_sql})")

            # Add new entries
            if files_to_add:
                self._add_files_in_batches(table, files_to_add)

                # Update FTS index (only if table has rows)
                try:
                    if table.count_rows() > 0:
                        logger.debug("Creating FTS index")
                        table.create_fts_index("content", replace=True)
                    else:
                        logger.warning("Table is empty, skipping FTS index creation")
                except Exception as e:
                    logger.warning(f"FTS indexing failed (search will still work via vector): {e}")

            table.cleanup_old_versions()

    def _create_and_populate(self, files: Dict[str, str]):
        """Create table from scratch."""
        logger.info(f"Creating new index from {len(files)} files")

        # Drop if exists
        if TABLE_NAME in self._db.table_names():
            logger.debug("Dropping existing table")
            self._db.drop_table(TABLE_NAME)

        # Don't create table if no valid files
        if not files:
            logger.warning("No files to index, skipping table creation")
            return

        # Normalize and validate paths BEFORE creating table
        valid_files = {}
        skipped = 0
        for k, v in files.items():
            try:
                norm_path = self._normalize_path(k)
                valid_files[norm_path] = v
            except ValueError as e:
                logger.warning(f"Path normalization failed for {k}: {e}")
                skipped += 1
            except Exception as e:
                logger.error(f"Unexpected error normalizing {k}: {e}")
                skipped += 1

        if skipped > 0:
            logger.warning(f"Skipped {skipped}/{len(files)} files with invalid paths")

        if not valid_files:
            logger.error(f"No valid files after normalization. Project path: {self._project_path}")
            return

        # Only create table if we have valid files to index
        logger.info(f"Creating table and indexing {len(valid_files)} valid files")
        table = self._db.create_table(TABLE_NAME, schema=self._code_schema)

        self._add_files_in_batches(table, valid_files)

        # Only create FTS if rows exist
        try:
            if table.count_rows() > 0:
                logger.debug("Creating FTS index on new table")
                table.create_fts_index("content", replace=True)
            else:
                logger.warning("No rows added to table")
        except Exception as e:
            logger.warning(f"Initial FTS creation failed: {e}")

    def _add_files_in_batches(self, table, files: Dict[str, str]):
        """Chunk content and add to DB in batches (memory efficient)."""
        batch = []
        total_chunks = 0
        skipped_small = 0
        files_processed = 0
        total_files = len(files)

        logger.debug(f"Processing {total_files} files for chunking")

        for norm_path, content in files.items():
            try:
                chunks = self._chunker.chunk(norm_path, content)
                lines = content.splitlines()
                file_hash = self._compute_hash(content)

                file_chunk_count = 0
                for chunk in chunks:
                    # Safety check for line ranges
                    start = max(0, chunk.start_line - 1)
                    end = min(len(lines), chunk.end_line)
                    chunk_text = '\n'.join(lines[start:end])

                    # Skip very small chunks (noise)
                    if len(chunk_text) < MIN_CHUNK_SIZE:
                        skipped_small += 1
                        continue

                    batch.append({
                        "id": f"{norm_path}:{chunk.start_line}",
                        "file_path": norm_path,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "content_hash": file_hash,
                        "content": chunk_text,
                    })
                    file_chunk_count += 1
                    total_chunks += 1

                    if len(batch) >= BATCH_SIZE:
                        logger.debug(f"Adding batch of {len(batch)} chunks to table")
                        try:
                            import time
                            # Generate embeddings for the batch (truncate to 2000 chars for speed)
                            texts = [item["content"][:2000] for item in batch]
                            logger.debug(f"Generating embeddings for {len(texts)} chunks")
                            t0 = time.time()
                            embeddings = self._embedding_func.generate_embeddings(texts)
                            t1 = time.time()
                            logger.debug(f"Embedding generation took {t1-t0:.2f}s")

                            # Add vectors to batch
                            for item, embedding in zip(batch, embeddings):
                                item["vector"] = embedding
                            t2 = time.time()
                            logger.debug(f"Adding vectors to dicts took {t2-t1:.2f}s")

                            table.add(batch)
                            t3 = time.time()
                            logger.debug(f"table.add() took {t3-t2:.2f}s")
                            logger.debug(f"Successfully added batch of {len(batch)} chunks (total: {t3-t0:.2f}s)")
                        except Exception as e:
                            logger.error(f"Failed to add batch to table: {e}")
                            import traceback
                            logger.debug(traceback.format_exc())
                            raise
                        batch = []

                logger.debug(f"Indexed {norm_path}: {file_chunk_count} chunks")
                files_processed += 1

            except Exception as e:
                logger.error(f"Failed to chunk/index file {norm_path}: {e}")
                import traceback
                logger.debug(traceback.format_exc())

        if batch:
            logger.debug(f"Adding final batch of {len(batch)} chunks to table")
            try:
                import time
                # Generate embeddings for final batch
                texts = [item["content"] for item in batch]
                logger.debug(f"Generating embeddings for {len(texts)} chunks")
                t0 = time.time()
                embeddings = self._embedding_func.generate_embeddings(texts)
                t1 = time.time()
                logger.debug(f"Embedding generation took {t1-t0:.2f}s")

                # Add vectors to batch
                for item, embedding in zip(batch, embeddings):
                    item["vector"] = embedding
                t2 = time.time()

                table.add(batch)
                t3 = time.time()
                logger.debug(f"table.add() took {t3-t2:.2f}s")
                logger.debug(f"Successfully added final batch of {len(batch)} chunks (total: {t3-t0:.2f}s)")
            except Exception as e:
                logger.error(f"Failed to add final batch to table: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                raise

        logger.info(f"Added {total_chunks} chunks total (skipped {skipped_small} small chunks)")

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
