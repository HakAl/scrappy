"""
LanceDB-based semantic search provider.

Implements SemanticSearchProtocol using LanceDB for vector storage
and hybrid search (vector + full-text).
"""

import hashlib
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from contextlib import contextmanager

# Use simple imports to avoid circular dependency messes
try:
    import lancedb
    import fasteners
    from lancedb.pydantic import LanceModel, Vector
except ImportError:
    lancedb = None

from ..protocols import (
    CodeChunkerProtocol,
    EmbeddingFunctionProtocol,
    RankingConfig,
    ResultRankerProtocol,
    ScoredChunk,
    SearchResult,
)
from ...infrastructure.protocols import ProgressReporterProtocol
from .config import SemanticIndexConfig

logger = logging.getLogger(__name__)

# --- Configuration Constants ---
LOCK_FILE_NAME = "update.lock"
TABLE_NAME = "code_chunks"
TOKEN_ESTIMATION_CHAR_RATIO = 3.0


@dataclass
class IndexingMetrics:
    """Metrics from an indexing operation."""
    files_processed: int = 0
    chunks_added: int = 0
    chunks_skipped: int = 0
    embedding_time_seconds: float = 0.0
    db_write_time_seconds: float = 0.0
    total_time_seconds: float = 0.0

    @property
    def chunks_per_second(self) -> float:
        """Calculate throughput."""
        if self.embedding_time_seconds > 0:
            return self.chunks_added / self.embedding_time_seconds
        return 0.0


class IndexingError(Exception):
    """Custom exception for user-facing indexing failures."""
    pass


# --- Lazy Embedding Function Setup ---
# NOTE: EmbedFunction is registered at module import (fast, metadata only)
# The actual TextEmbedding model is created when .create() is called (lazy)


def _create_embedding_func(model_id: Optional[str] = None):
    """
    Create embedding function using the registry.

    Uses the embedding registry to select and instantiate the embedding backend.
    If model_id is specified, uses that model. Otherwise auto-detects the best
    available model based on priority (Nomic > Jina > BGE-small).

    Args:
        model_id: Optional model identifier (bge-small, nomic, jina). If None,
                  auto-detects the best available model.

    Returns:
        Initialized embedding function instance

    Raises:
        ValueError: If specified model is not available
        RuntimeError: If no embedding backends are available
    """
    from .registry import get_embedding_registry, EmbeddingModelId

    registry = get_embedding_registry()

    if model_id:
        # Explicit model requested - validate and create
        try:
            model_enum = EmbeddingModelId(model_id)
        except ValueError:
            valid = [m.value for m in EmbeddingModelId]
            raise ValueError(
                f"Unknown embedding model '{model_id}'. Valid options: {valid}"
            )
        return registry.create(model_enum)
    else:
        # Auto-detect best available
        return registry.create_best_available()


def _create_code_schema(ndims: int = 384):
    """
    Create schema for code chunks with embeddings.

    Args:
        ndims: Embedding dimensions (depends on model: BGE-small=384, Nomic/Jina=768)

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
        vector: Vector(ndims)   # Embeddings (384 for BGE-small, 768 for Nomic/Jina)

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
    - Custom FastEmbed + embeddings

    Architecture:
    - Follows SOLID principles (dependency injection, single responsibility)
    - Lazy initialization (no I/O in constructor)
    - Protocol-based design (easy to test and swap implementations)
    """

    def __init__(
        self,
        project_path: Path,
        chunker: CodeChunkerProtocol,
        config: Optional[SemanticIndexConfig] = None,
        embedding_func: Optional[EmbeddingFunctionProtocol] = None,
        progress_reporter: Optional[ProgressReporterProtocol] = None,
        ranker: Optional[ResultRankerProtocol] = None,
    ):
        """
        Initialize search provider (NO I/O in constructor).

        Args:
            project_path: Project root path
            chunker: Code chunking strategy (INJECTED)
            config: Index configuration (INJECTED, defaults provided)
            embedding_func: Embedding function (INJECTED, lazy-loaded if None)
            progress_reporter: Progress reporter for indexing operations (INJECTED)
            ranker: Result ranker for re-ranking search results (INJECTED, optional)
        """
        self._project_path = project_path.resolve()
        self._chunker = chunker  # Injected dependency
        self._config = config or SemanticIndexConfig()
        self._lock_timeout = self._config.lock_timeout

        # Model ID and info are resolved lazily when embedding function is created
        self._model_id: Optional[str] = None
        self._model_info = None  # EmbeddingModelInfo with indexing profile

        # DB path is determined lazily based on model selection
        # (each model gets its own subdirectory to avoid dimension conflicts)
        self._db_path: Optional[Path] = None
        self._lock_path: Optional[Path] = None

        # Lazy initialization (embedding_func can be injected for testing)
        self._db = None
        self._embedding_func = embedding_func  # None means lazy-load default
        self._code_schema = None
        self._is_writing = False  # Write protection flag for graceful shutdown
        self._chunks_since_fts_rebuild = 0  # Track cumulative chunks for FTS threshold

        # Progress reporter (defaults to NullProgressReporter if not provided)
        if progress_reporter is None:
            from ...infrastructure.progress import NullProgressReporter
            progress_reporter = NullProgressReporter()
        self._progress = progress_reporter

        # Result ranker (optional - if None, results use raw scores from LanceDB)
        self._ranker = ranker

    def set_progress_reporter(self, progress_reporter: ProgressReporterProtocol) -> None:
        """
        Set or update the progress reporter.

        Args:
            progress_reporter: Progress reporter to use for indexing operations
        """
        self._progress = progress_reporter

    def _resolve_model_and_paths(self) -> None:
        """
        Resolve embedding model and set up paths based on selection.

        Called lazily on first use. Sets _model_id, _model_info, _db_path, _lock_path.
        """
        if self._model_id is not None:
            return  # Already resolved

        from .registry import get_embedding_registry, EmbeddingModelId
        registry = get_embedding_registry()

        # Get configured model (may be None for auto-detect)
        configured_model = self._config.get_embedding_model()

        if configured_model:
            self._model_id = configured_model
            logger.info(f"Using configured embedding model: {self._model_id}")
            # Try to get model info for configured model
            try:
                model_enum = EmbeddingModelId(configured_model)
                self._model_info = registry.get_info(model_enum)
            except ValueError:
                self._model_info = None
        else:
            # Auto-detect: get best available model
            best = registry.get_best_available()
            if best:
                self._model_id = best.id.value
                self._model_info = best
                logger.info(f"Auto-detected embedding model: {self._model_id}")
            else:
                # Fallback (should not happen in practice)
                self._model_id = "bge-small"
                self._model_info = registry.get_info(EmbeddingModelId.BGE_SMALL)
                logger.warning("No embedding models available, defaulting to bge-small")

        # Set per-model database path
        db_dir = self._config.get_db_dir_for_model(self._model_id)
        self._db_path = self._project_path / db_dir
        self._lock_path = self._db_path / LOCK_FILE_NAME

        logger.debug(f"Index path for model {self._model_id}: {self._db_path}")

    def _ensure_db(self):
        """Lazy DB initialization (creates directory and connects)."""
        if self._db is None:
            self._resolve_model_and_paths()
            self._db_path.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(self._db_path)

    def _ensure_schema(self):
        """
        Lazy schema initialization (creates embedding func and schema).

        If embedding_func was injected via constructor, uses that.
        Otherwise lazy-loads using the registry based on config.

        Raises:
            IndexingError: If embedding backend is not available or initialization fails
        """
        if self._code_schema is None:
            try:
                # Ensure model and paths are resolved
                self._resolve_model_and_paths()

                # Only create embedding func if not already injected
                if self._embedding_func is None:
                    logger.debug(f"Initializing embedding function for model {self._model_id}...")
                    self._embedding_func = _create_embedding_func(self._model_id)

                    # Ensure the model is fully loaded by generating a test embedding
                    # This ensures the heavy model loading happens here, not later
                    try:
                        _ = self._embedding_func.generate_embeddings(["test"])
                        logger.debug("Embedding model is fully loaded")
                    except Exception as e:
                        logger.warning(f"Error during test embedding generation: {e}")
                else:
                    logger.debug("Using injected embedding function")

                # Create schema with correct dimensions for the model
                ndims = self._embedding_func.ndims()
                self._code_schema = _create_code_schema(ndims)
                logger.debug(f"Schema created with {ndims} dimensions")
            except ValueError as e:
                # Model not available error from registry
                raise IndexingError(str(e)) from e
            except Exception as e:
                raise IndexingError(
                    f"Failed to initialize embedding function. "
                    f"Make sure semantic search dependencies are installed: "
                    f"pip install fastembed lancedb. "
                    f"Error: {e}"
                ) from e

    def _check_table_dimensions(self, table) -> bool:
        """
        Check if existing table's vector dimensions match expected dimensions.

        This detects when a user switches embedding models (e.g., from BGE-small
        to Nomic) and the existing index has incompatible dimensions.

        Args:
            table: LanceDB table to check

        Returns:
            True if dimensions match (or can't be determined), False if mismatch
        """
        expected_dims = self._embedding_func.ndims()

        try:
            # Get the schema from the table
            schema = table.schema
            # Find the vector field
            for field in schema:
                if field.name == "vector":
                    # LanceDB stores vectors as FixedSizeList
                    # The list_size is the dimension
                    if hasattr(field.type, "list_size"):
                        actual_dims = field.type.list_size
                        if actual_dims != expected_dims:
                            logger.warning(
                                f"Index dimension mismatch: table has {actual_dims} dims, "
                                f"but model expects {expected_dims} dims. Will rebuild index."
                            )
                            return False
                        logger.debug(f"Index dimensions match: {actual_dims}")
                        return True
            # Couldn't find vector field - assume OK (will fail later if not)
            logger.debug("Could not find vector field in schema, assuming OK")
            return True
        except Exception as e:
            # Can't read schema - assume OK (will fail later if corrupt)
            logger.debug(f"Could not check table dimensions: {e}")
            return True

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

        # Validate paths BEFORE acquiring lock or initializing DB
        # This avoids unnecessary work when all files have invalid paths
        valid_files = {}
        for raw_path, content in files.items():
            try:
                norm_path = self._normalize_path(raw_path)
                valid_files[norm_path] = content
            except (ValueError, IndexingError):
                logger.debug(f"Skipping invalid path: {raw_path}")
                continue

        if not valid_files:
            logger.warning("No valid files after path validation")
            return

        self._ensure_db()
        self._ensure_schema()  # Lazy-initialize embedding function and schema

        with self._safe_db_context():
            table_exists = TABLE_NAME in self._db.table_names()
            logger.debug(f"Table exists: {table_exists}")

            if not table_exists:
                logger.info("Creating new index table")
                self._create_and_populate(valid_files)
                return

            table = self._db.open_table(TABLE_NAME)

            # Check for dimension mismatch (e.g., user switched embedding models)
            if not self._check_table_dimensions(table):
                logger.info("Dimension mismatch detected, rebuilding index from scratch")
                self._create_and_populate(valid_files)
                return

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
                self._create_and_populate(valid_files)
                return

            # 2. Calculate Diff (using pre-validated paths)
            files_to_add = {}     # {path: content}
            paths_to_remove = []  # [path]

            # Check filesystem against DB (paths already normalized)
            for norm_path, content in valid_files.items():
                current_hash = self._compute_hash(content)

                # If new or modified
                if norm_path not in db_state or db_state[norm_path] != current_hash:
                    files_to_add[norm_path] = content
                    if norm_path in db_state:
                        paths_to_remove.append(norm_path)

            # Check DB against filesystem (detect deletions)
            # SKIP during batched indexing to avoid deleting files from previous batches
            if not is_batch:
                fs_paths_set = set(valid_files.keys())

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
                metrics = self._add_files_in_batches(table, files_to_add)

                # Conditionally rebuild FTS index
                self._maybe_rebuild_fts(table, metrics.chunks_added)

            table.cleanup_old_versions()

    def _create_and_populate(self, valid_files: Dict[str, str]):
        """
        Create table from scratch with pre-validated files.

        Args:
            valid_files: Dict mapping normalized paths to content (already validated)
        """
        logger.info(f"Creating new index from {len(valid_files)} files")

        # Drop if exists
        if TABLE_NAME in self._db.table_names():
            logger.debug("Dropping existing table")
            self._db.drop_table(TABLE_NAME)

        # Don't create table if no files
        if not valid_files:
            logger.warning("No files to index, skipping table creation")
            return

        # Create table and index files (paths already validated by caller)
        logger.info(f"Creating table and indexing {len(valid_files)} files")
        table = self._db.create_table(TABLE_NAME, schema=self._code_schema)

        metrics = self._add_files_in_batches(table, valid_files)

        # Always create FTS on new table (no threshold check for initial creation)
        self._maybe_rebuild_fts(table, metrics.chunks_added, force=True)

    def _add_files_in_batches(self, table, files: Dict[str, str]) -> IndexingMetrics:
        """
        Chunk content and add to DB with super-batch processing.

        Uses super-batch pattern for memory safety:
        1. Collect chunks up to super_batch_size
        2. Embed and write to DB
        3. Clear memory and repeat

        Args:
            table: LanceDB table to add to
            files: Dict mapping file paths to content

        Returns:
            IndexingMetrics with timing and counts
        """
        metrics = IndexingMetrics()
        start_time = time.time()
        config = self._config

        # Use model-specific profile if available, otherwise fall back to config
        if self._model_info:
            batch_size = self._model_info.batch_size
            super_batch_size = self._model_info.super_batch_size
            max_text_length = self._model_info.max_text_length
        else:
            batch_size = config.batch_size
            super_batch_size = config.super_batch_size
            max_text_length = config.max_text_length

        all_chunks: List[Dict] = []
        total_files = len(files)

        logger.debug(f"Processing {total_files} files (batch={batch_size}, "
                     f"super_batch={super_batch_size}, max_text={max_text_length})")

        for norm_path, content in files.items():
            try:
                chunks = self._chunker.chunk(norm_path, content)
                lines = content.splitlines()
                file_hash = self._compute_hash(content)

                for chunk in chunks:
                    # Safety check for line ranges
                    start = max(0, chunk.start_line - 1)
                    end = min(len(lines), chunk.end_line)
                    chunk_text = '\n'.join(lines[start:end])

                    # Skip very small chunks (noise)
                    if len(chunk_text) < config.min_chunk_size:
                        metrics.chunks_skipped += 1
                        continue

                    all_chunks.append({
                        "id": f"{norm_path}:{chunk.start_line}",
                        "file_path": norm_path,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "content_hash": file_hash,
                        "content": chunk_text[:max_text_length],
                    })

                    # Memory safety: flush when super-batch is full
                    if len(all_chunks) >= super_batch_size:
                        batch_metrics = self._process_super_batch(table, all_chunks)
                        metrics.chunks_added += batch_metrics["added"]
                        metrics.embedding_time_seconds += batch_metrics["embed_time"]
                        metrics.db_write_time_seconds += batch_metrics["db_time"]
                        all_chunks = []

                metrics.files_processed += 1

                # Report progress (protocol uses 'description', not 'message')
                self._progress.update(
                    current=metrics.files_processed,
                    description=f"Indexing {norm_path} ({metrics.files_processed}/{total_files})"
                )

            except Exception as e:
                logger.error(f"Failed to chunk/index file {norm_path}: {e}")
                import traceback
                logger.debug(traceback.format_exc())

        # Final flush
        if all_chunks:
            batch_metrics = self._process_super_batch(table, all_chunks)
            metrics.chunks_added += batch_metrics["added"]
            metrics.embedding_time_seconds += batch_metrics["embed_time"]
            metrics.db_write_time_seconds += batch_metrics["db_time"]

        metrics.total_time_seconds = time.time() - start_time

        logger.info(
            f"Added {metrics.chunks_added} chunks in {metrics.total_time_seconds:.1f}s "
            f"(skipped {metrics.chunks_skipped}, {metrics.chunks_per_second:.0f} chunks/s)"
        )

        return metrics

    def _process_super_batch(self, table, chunks: List[Dict]) -> Dict:
        """
        Process a super-batch: embed and insert to DB.

        Args:
            table: LanceDB table
            chunks: List of chunk dicts (without vectors)

        Returns:
            Dict with 'added', 'embed_time', 'db_time'
        """
        result = {"added": 0, "embed_time": 0.0, "db_time": 0.0}

        if not chunks:
            return result

        logger.debug(f"Processing super-batch of {len(chunks)} chunks")

        # Generate embeddings for all chunks in batch_size batches
        texts = [c["content"] for c in chunks]

        t0 = time.time()
        embeddings = list(self._embedding_func.generate_embeddings(texts))
        t1 = time.time()
        result["embed_time"] = t1 - t0

        # Attach vectors to chunks
        for chunk, embedding in zip(chunks, embeddings):
            chunk["vector"] = embedding

        # Insert in DB-optimal batches (LanceDB handles larger batches well)
        # CRITICAL SECTION - protect against mid-write termination
        DB_BATCH_SIZE = 1000
        t2 = time.time()
        for i in range(0, len(chunks), DB_BATCH_SIZE):
            batch = chunks[i:i + DB_BATCH_SIZE]
            try:
                self._is_writing = True
                try:
                    table.add(batch)
                finally:
                    self._is_writing = False
                result["added"] += len(batch)
            except Exception as e:
                logger.error(f"Failed to add batch to table: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                raise
        t3 = time.time()
        result["db_time"] = t3 - t2

        logger.debug(
            f"Super-batch complete: {result['added']} chunks, "
            f"embed={result['embed_time']:.2f}s, db={result['db_time']:.2f}s"
        )

        return result

    def _maybe_rebuild_fts(self, table, chunks_added: int, force: bool = False) -> None:
        """
        Conditionally update FTS index based on cumulative chunks added.

        Uses incremental FTS indexing (replace=False) when possible to avoid
        locking readers. Falls back to full rebuild on initial creation or
        when incremental update fails.

        FTS rebuilding is O(N) where N is total rows. For small updates,
        this overhead isn't worth it. Only rebuild when significant
        data has been added cumulatively since last rebuild.

        Args:
            table: LanceDB table
            chunks_added: Number of chunks added in this operation
            force: If True, skip threshold check (for initial creation)
        """
        threshold = self._config.fts_rebuild_threshold

        # Track cumulative chunks since last FTS rebuild
        self._chunks_since_fts_rebuild += chunks_added

        if not force and self._chunks_since_fts_rebuild < threshold:
            logger.debug(
                f"Skipping FTS rebuild ({self._chunks_since_fts_rebuild} cumulative chunks < {threshold} threshold)"
            )
            return

        try:
            row_count = table.count_rows()
            if row_count > 0:
                # Try incremental update first (replace=False)
                # This is faster and doesn't lock readers
                try:
                    logger.debug(f"Updating FTS index incrementally ({row_count} rows)")
                    table.create_fts_index("content", replace=False)
                    # Reset counter after successful FTS rebuild
                    self._chunks_since_fts_rebuild = 0
                except Exception as e:
                    # Index may already exist or incremental not supported
                    # Fall back to full rebuild
                    error_msg = str(e).lower()
                    if "already exists" in error_msg or "exist" in error_msg:
                        # Index exists and is up to date - this is expected
                        logger.debug("FTS index already exists, skipping update")
                        # Reset counter - index is current
                        self._chunks_since_fts_rebuild = 0
                    else:
                        # Other error - try full rebuild
                        logger.debug(f"Incremental FTS update failed ({e}), trying full rebuild")
                        table.create_fts_index("content", replace=True)
                        # Reset counter after successful FTS rebuild
                        self._chunks_since_fts_rebuild = 0
            else:
                logger.warning("Table is empty, skipping FTS index creation")
        except Exception as e:
            logger.warning(f"FTS indexing failed (search will still work via vector): {e}")
            # Don't reset counter on failure - try again next time

    # --- Core: Retrieval ---

    def search(
        self,
        query: str,
        max_results: int = 25,
        max_tokens: int = 4000,
        ranking_config: Optional[RankingConfig] = None,
    ) -> SearchResult:
        """
        Search indexed files semantically.

        Implements SemanticSearchProtocol.

        Uses hybrid search: vector similarity + full-text search.
        Falls back to vector-only if FTS fails.

        If a ranker was provided at construction time, results are re-ranked
        using the specified ranking configuration.

        Args:
            query: Search query
            max_results: Maximum results to return
            max_tokens: Token budget for results
            ranking_config: Optional ranking configuration for result re-ranking

        Returns:
            SearchResult with chunks and metadata
        """
        if not self.is_indexed():
            return SearchResult(chunks=[], tokens_used=0, limit_hit=None)

        self._ensure_schema()  # Ensure model is loaded

        table = self._db.open_table(TABLE_NAME)
        # 1. Embed the query manually
        # Note: embed_query returns a generator, use list() + next() or standard methods
        query_vector = self._embedding_func.generate_embeddings([query])[0]

        # Hybrid Search: Vector (semantic) + FTS (keyword)
        try:
            # LanceDB requires explicit .vector() and .text() for hybrid search
            # Cannot pass vector to search() AND call .text() - must use both explicitly
            results = (
                table.search(query_type="hybrid")
                .vector(query_vector)
                .text(query)
                .limit(max_results)
                .to_list()
            )
        except (KeyboardInterrupt, SystemExit, MemoryError):
            # Don't catch fatal errors - let them propagate
            raise
        except Exception as e:
            # Fallback if FTS index broken or missing (e.g., index not created, corrupted)
            logger.warning(f"Hybrid search failed ({e}), falling back to vector search")
            results = table.search(query_vector, query_type="vector").limit(max_results).to_list()

        # If ranker is available, convert to ScoredChunk and re-rank
        if self._ranker is not None:
            scored_chunks = self._convert_to_scored_chunks(results)
            ranked_chunks = self._ranker.rank(query, scored_chunks, ranking_config)
            return self._build_result_from_ranked(ranked_chunks, max_tokens)

        # Otherwise use original behavior (no re-ranking)
        return self._build_result_from_raw(results, max_tokens)

    def _convert_to_scored_chunks(self, results: List[Dict]) -> List[ScoredChunk]:
        """
        Convert raw LanceDB results to ScoredChunk objects.

        Args:
            results: Raw results from LanceDB search

        Returns:
            List of ScoredChunk objects with scores extracted
        """
        scored_chunks = []
        seen_chunks = set()

        for row in results:
            chunk_id = (row['file_path'], row['start_line'])
            if chunk_id in seen_chunks:
                continue
            seen_chunks.add(chunk_id)

            # LanceDB hybrid search provides _score (combined) and _distance (vector)
            # _distance is L2 distance, lower is better; convert to similarity
            raw_distance = row.get('_distance', 0.0)
            # Convert L2 distance to similarity score (0-1, higher is better)
            # Using simple exponential decay: similarity = exp(-distance)
            vector_score = math.exp(-raw_distance) if raw_distance >= 0 else 0.0

            # _score from hybrid search (FTS contribution)
            fts_score = row.get('_score', 0.0)

            scored_chunks.append(ScoredChunk(
                file_path=row['file_path'],
                start_line=row['start_line'],
                end_line=row['end_line'],
                content=row['content'],
                vector_score=vector_score,
                fts_score=fts_score,
                final_score=0.0,  # Will be set by ranker
            ))

        return scored_chunks

    def _build_result_from_ranked(
        self,
        ranked_chunks: List[ScoredChunk],
        max_tokens: int,
    ) -> SearchResult:
        """
        Build SearchResult from ranked ScoredChunk list.

        Args:
            ranked_chunks: Chunks sorted by final_score (highest first)
            max_tokens: Token budget for results

        Returns:
            SearchResult with chunks and metadata
        """
        final_chunks = []
        used_tokens = 0
        limit_hit = None

        for chunk in ranked_chunks:
            cost = int(len(chunk.content) / TOKEN_ESTIMATION_CHAR_RATIO)

            if used_tokens + cost > max_tokens:
                limit_hit = 'token_limit'
                break

            final_chunks.append({
                'path': chunk.file_path,
                'lines': (chunk.start_line, chunk.end_line),
                'content': chunk.content,
                'score': chunk.final_score,
            })
            used_tokens += cost

        return SearchResult(
            chunks=final_chunks,
            tokens_used=used_tokens,
            limit_hit=limit_hit,
        )

    def _build_result_from_raw(
        self,
        results: List[Dict],
        max_tokens: int,
    ) -> SearchResult:
        """
        Build SearchResult from raw LanceDB results (no re-ranking).

        Args:
            results: Raw results from LanceDB search
            max_tokens: Token budget for results

        Returns:
            SearchResult with chunks and metadata
        """
        final_chunks = []
        used_tokens = 0
        limit_hit = None
        seen_chunks = set()

        for row in results:
            chunk_id = (row['file_path'], row['start_line'])
            if chunk_id in seen_chunks:
                continue

            content = row['content']
            cost = int(len(content) / TOKEN_ESTIMATION_CHAR_RATIO)

            if used_tokens + cost > max_tokens:
                limit_hit = 'token_limit'
                break

            final_chunks.append({
                'path': row['file_path'],
                'lines': (row['start_line'], row['end_line']),
                'content': content,
                'score': row.get('_score', 0.0),
            })
            used_tokens += cost
            seen_chunks.add(chunk_id)

        return SearchResult(
            chunks=final_chunks,
            tokens_used=used_tokens,
            limit_hit=limit_hit,
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

    def cleanup_deleted_files(self, current_files: set) -> int:
        """
        Remove stale entries for deleted files.

        Implements SemanticSearchProtocol.

        Should be called AFTER batched indexing completes with the full
        set of currently-existing file paths. This ensures that files
        deleted from the filesystem are also removed from the index.

        Args:
            current_files: Set of normalized POSIX paths that currently exist

        Returns:
            Number of entries removed
        """
        if not self.is_indexed():
            return 0

        self._ensure_db()

        with self._safe_db_context():
            table = self._db.open_table(TABLE_NAME)

            # Get all indexed file paths (unique)
            indexed_paths = set()
            try:
                for batch in table.search().select(["file_path"]).to_batches():
                    df = batch.to_pandas()
                    indexed_paths.update(df["file_path"].tolist())
            except Exception as e:
                logger.warning(f"Could not read indexed paths: {e}")
                return 0

            # Find stale paths (in DB but not in current files)
            stale_paths = indexed_paths - current_files

            if not stale_paths:
                logger.debug("No stale entries to clean up")
                return 0

            logger.info(f"Removing {len(stale_paths)} stale file entries from index")

            # Delete in batches to avoid huge SQL statements
            BATCH_SIZE = 100
            removed = 0
            stale_list = list(stale_paths)

            for i in range(0, len(stale_list), BATCH_SIZE):
                batch = stale_list[i:i + BATCH_SIZE]
                # Escape single quotes in paths for SQL safety
                paths_sql = ", ".join(f"'{p.replace(chr(39), chr(39)+chr(39))}'" for p in batch)
                try:
                    table.delete(f"file_path IN ({paths_sql})")
                    removed += len(batch)
                except Exception as e:
                    logger.warning(f"Failed to delete batch of stale entries: {e}")

            # Clean up old versions after deletion
            try:
                table.cleanup_old_versions()
            except Exception as e:
                logger.debug(f"Cleanup old versions failed: {e}")

            logger.info(f"Cleaned up {removed} stale file entries")
            return removed

    def remove_files(self, files: set) -> int:
        """
        Remove specific files from the index.

        Implements SemanticSearchProtocol.

        More efficient than cleanup_deleted_files when you already know
        which files were deleted (e.g., from staleness detection).

        Args:
            files: Set of file paths to remove from index

        Returns:
            Number of entries removed
        """
        if not files:
            return 0

        if not self.is_indexed():
            return 0

        self._ensure_db()

        with self._safe_db_context():
            table = self._db.open_table(TABLE_NAME)

            # Delete in batches to avoid huge SQL statements
            BATCH_SIZE = 100
            removed = 0
            files_list = list(files)

            for i in range(0, len(files_list), BATCH_SIZE):
                batch = files_list[i:i + BATCH_SIZE]
                # Escape single quotes in paths for SQL safety
                paths_sql = ", ".join(f"'{p.replace(chr(39), chr(39)+chr(39))}'" for p in batch)
                try:
                    table.delete(f"file_path IN ({paths_sql})")
                    removed += len(batch)
                except Exception as e:
                    logger.warning(f"Failed to delete batch of file entries: {e}")

            # Clean up old versions after deletion
            try:
                table.cleanup_old_versions()
            except Exception as e:
                logger.debug(f"Cleanup old versions failed: {e}")

            if removed > 0:
                logger.info(f"Removed {removed} deleted file entries from index")

            return removed

    def save_index_state(self, state_manager) -> None:
        """
        Save current index state after successful indexing.

        Args:
            state_manager: IndexStateProtocol implementation for persisting state
        """
        from datetime import datetime
        from ..protocols import IndexState

        if not self.is_indexed():
            logger.warning("Cannot save state: index does not exist")
            return

        try:
            total_chunks, total_files = self.get_current_stats()

            # Build file_hashes from current index
            file_hashes = {}
            self._ensure_db()
            table = self._db.open_table(TABLE_NAME)

            try:
                for batch in table.search().select(["file_path", "content_hash"]).to_batches():
                    df = batch.to_pandas()
                    for _, row in df.iterrows():
                        # Store the latest hash for each file
                        file_hashes[row["file_path"]] = row["content_hash"]
            except Exception as e:
                logger.warning(f"Could not read file hashes from index: {e}")

            state = IndexState(
                last_indexed=datetime.now(),
                total_chunks=total_chunks,
                total_files=total_files,
                index_version="1.0",
                file_hashes=file_hashes,
            )

            state_manager.save(state)
            logger.debug(f"Saved index state: {total_chunks} chunks, {total_files} files")

        except Exception as e:
            logger.warning(f"Failed to save index state: {e}")

    def get_current_stats(self) -> tuple:
        """
        Return (total_chunks, total_files) from current index.

        Returns:
            Tuple of (total_chunks, total_files)
        """
        if not self.is_indexed():
            return (0, 0)

        try:
            self._ensure_db()
            table = self._db.open_table(TABLE_NAME)

            # Count total chunks
            total_chunks = table.count_rows()

            # Count unique files
            unique_files = set()
            try:
                for batch in table.search().select(["file_path"]).to_batches():
                    df = batch.to_pandas()
                    unique_files.update(df["file_path"].tolist())
            except Exception as e:
                logger.warning(f"Could not read file paths: {e}")

            total_files = len(unique_files)

            return (total_chunks, total_files)

        except Exception as e:
            logger.warning(f"Failed to get index stats: {e}")
            return (0, 0)
