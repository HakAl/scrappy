# Existing Integration Status

src/context/protocols.py, line 406
```python

# --- Semantic Search Data Classes ---


@dataclass
class CodeChunk:
    """Represents a chunk of code with line range."""
    start_line: int
    end_line: int
    file_path: Optional[str] = None


@dataclass
class SearchResult:
    """Result from semantic search."""
    chunks: List[Dict[str, Any]]  # [{path, lines: (start, end), content, score}]
    tokens_used: int
    limit_hit: Optional[str] = None  # 'token_limit' | None


# --- Semantic Search Protocols ---


@runtime_checkable
class CodeChunkerProtocol(Protocol):
    """
    Protocol for code chunking strategies.

    Abstracts code chunking to enable different strategies
    (semantic, line-based, AST-based) without changing consumers.

    Implementations:
    - SemanticCodeChunker: Semantic chunking with overlap
    - LineBasedChunker: Simple line-count chunking (future)
    - TestChunker: Fixed chunks for testing

    Example:
        def chunk_file(chunker: CodeChunkerProtocol, content: str) -> List[CodeChunk]:
            return chunker.chunk("example.py", content)
    """

    def chunk(self, file_path: str, content: str) -> List[CodeChunk]:
        """
        Chunk code content into retrievable segments.

        Args:
            file_path: Path to the file being chunked
            content: File content to chunk

        Returns:
            List of CodeChunk objects with line ranges
        """
        ...


@runtime_checkable
class SemanticSearchProtocol(Protocol):
    """
    Protocol for semantic code search.

    Abstracts semantic search implementation to enable:
    - Swapping search backends (LanceDB, Pinecone, Chroma)
    - Testing with mock search results
    - Graceful degradation when not available

    Implementations:
    - LanceDBSearchProvider: Vector + FTS hybrid search
    - MockSearchProvider: Preset results for testing
    - NullSearchProvider: No-op for when dependencies unavailable

    Example:
        def search_code(search: SemanticSearchProtocol, query: str) -> SearchResult:
            if search.is_indexed():
                return search.search(query)
            return SearchResult(chunks=[], tokens_used=0)
    """

    def index_files(self, files: Dict[str, str]) -> None:
        """
        Index files for semantic search.

        Args:
            files: Dict mapping file paths to content

        Raises:
            IndexingError: If indexing fails
        """
        ...

    def search(
        self,
        query: str,
        max_results: int = 25,
        max_tokens: int = 4000
    ) -> SearchResult:
        """
        Search indexed files semantically.

        Args:
            query: Search query
            max_results: Maximum results to return
            max_tokens: Token budget for results

        Returns:
            SearchResult with chunks and metadata
        """
        ...

    def is_indexed(self) -> bool:
        """
        Check if files have been indexed.

        Returns:
            True if index exists and is usable, False otherwise
        """
        ...

    def clear_index(self) -> None:
        """Clear the search index."""
        ...
```
src/context/code_chunker.py
```python
"""
Code chunking for semantic search.

Implements CodeChunkerProtocol with semantic overlap strategy.
"""

from typing import List
from .protocols import CodeChunk, CodeChunkerProtocol


class SemanticCodeChunker:
    """
    Chunks code with overlapping lines for better context.

    Implements CodeChunkerProtocol.

    Design decisions:
    - Overlap prevents context loss at chunk boundaries
    - Line-based chunking (not token-based) for simplicity
    - Configurable chunk size for different use cases
    """

    def __init__(
        self,
        chunk_size: int = 100,
        overlap: int = 3
    ):
        """
        Initialize chunker (NO I/O, just configuration).

        Args:
            chunk_size: Lines per chunk
            overlap: Overlapping lines between chunks

        Raises:
            ValueError: If overlap >= chunk_size
        """
        if overlap >= chunk_size:
            raise ValueError(f"Overlap ({overlap}) must be less than chunk_size ({chunk_size})")

        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk(self, file_path: str, content: str) -> List[CodeChunk]:
        """
        Chunk content with overlap.

        Example with chunk_size=10, overlap=3:
        - Chunk 1: lines 1-10
        - Chunk 2: lines 8-17 (3 line overlap)
        - Chunk 3: lines 15-24 (3 line overlap)

        Args:
            file_path: Path to file (for reference, not used)
            content: File content to chunk

        Returns:
            List of CodeChunk objects with line ranges
        """
        if not content.strip():
            return []

        lines = content.splitlines()
        chunks: List[CodeChunk] = []

        i = 0
        while i < len(lines):
            chunk_start = i + 1  # 1-indexed for human readability
            chunk_end = min(i + self._chunk_size, len(lines))

            chunks.append(CodeChunk(
                start_line=chunk_start,
                end_line=chunk_end,
                file_path=file_path
            ))

            # Move forward by (chunk_size - overlap)
            step = self._chunk_size - self._overlap
            i += step

        return chunks
```

---

src/context/semantic/embeddings.py
```python
"""
Custom FastEmbed embedding function for LanceDB.

Provides Jina AI embeddings optimized for code understanding.
Uses FastEmbed for fast, local embedding generation.
"""

import logging
from typing import List
import numpy as np

from lancedb.embeddings import register, TextEmbeddingFunction
from fastembed import TextEmbedding

logger = logging.getLogger(__name__)


@register("fastembed-jina")
class JinaEmbedFunction(TextEmbeddingFunction):
    """
    Custom embedding function using Jina AI's code-optimized model via FastEmbed.

    Model: jinaai/jina-embeddings-v2-base-code
    - Optimized for code understanding and semantic search
    - 768 dimensions
    - 8K context window
    - Runs locally (no API calls)

    Usage:
        from lancedb.embeddings import get_registry

        registry = get_registry()
        embed_func = registry.get("fastembed-jina").create()

    Architecture Notes:
        - Registration (@register) happens at module import (fast, metadata only)
        - TextEmbedding model is created in __init__ (lazy, called by .create())
        - Follows SOLID: Single responsibility, dependency inversion ready
    """

    name: str = "jinaai/jina-embeddings-v2-base-code"

    def __init__(self, **kwargs):
        """
        Initialize the embedding function.

        This is called lazily when registry.get("fastembed-jina").create() is invoked.
        The TextEmbedding model is loaded here (10-30s on first use for model download).

        Args:
            **kwargs: Additional arguments passed to parent TextEmbeddingFunction
        """
        super().__init__(**kwargs)
        logger.debug(f"Initializing FastEmbed with model: {self.name}")
        self._model = TextEmbedding(model_name=self.name)
        logger.debug("FastEmbed model initialized")

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each vector is a list of floats)

        Note:
            FastEmbed returns a generator of numpy.ndarray objects.
            We must convert each array to a Python list to satisfy LanceDB/Pydantic validation.
            Without this conversion, ONNX Runtime may miscalculate buffer sizes.
        """
        # FastEmbed returns Iterable[np.ndarray]
        embeddings_generator = self._model.embed(texts)

        # Convert numpy arrays to python lists to satisfy LanceDB/Pydantic validation
        return [embedding.tolist() for embedding in embeddings_generator]

    def ndims(self) -> int:
        """
        Return the dimensionality of the embeddings.

        Returns:
            768 (dimensions of Jina v2 base code model)

        Note:
            Hardcoded since we control the model choice. More efficient than
            running a dummy embedding to detect dimensions.
        """
        return 768

```

src/context/semantic/initializer.py
```python
"""
Background initializer for semantic search with FastEmbed and LanceDB.

Loads heavy dependencies (FastEmbed models, LanceDB) in a background thread
to prevent UI freezing during startup.
"""

import logging
import threading
from pathlib import Path
from typing import Optional

from ...infrastructure.protocols import BackgroundInitializerProtocol
from ..protocols import SemanticSearchProtocol

logger = logging.getLogger(__name__)


class SemanticSearchInitializer:
    """
    Background initializer for semantic search.

    Loads FastEmbed and LanceDB in a background thread to prevent
    blocking the UI during startup.

    Usage:
        initializer = SemanticSearchInitializer(project_path)
        initializer.start()  # Non-blocking

        # Later when needed
        if initializer.wait_for_completion(timeout=30.0):
            search = initializer.get_result()
            if search:
                search.index_files(files)
    """

    def __init__(self, project_path: Path):
        """
        Initialize semantic search loader.

        Args:
            project_path: Path to project root for semantic search
        """
        self._project_path = project_path
        self._thread: Optional[threading.Thread] = None
        self._complete = False
        self._result: Optional[SemanticSearchProtocol] = None
        self._error: Optional[Exception] = None
        self._lock = threading.Lock()
        self._status = "Not started"

    def start(self) -> None:
        """
        Start background initialization.

        This is non-blocking and returns immediately.
        """
        with self._lock:
            if self._thread is not None:
                logger.debug("Initialization already started")
                return

            self._status = "Initializing semantic search..."
            self._thread = threading.Thread(
                target=self._initialize_semantic_search,
                daemon=True,
                name="SemanticSearchInit"
            )
            self._thread.start()
            logger.debug("Started background semantic search initialization")

    def is_complete(self) -> bool:
        """Check if initialization is complete."""
        with self._lock:
            return self._complete

    def is_running(self) -> bool:
        """Check if initialization is currently running."""
        with self._lock:
            return self._thread is not None and not self._complete

    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for initialization to complete.

        Args:
            timeout: Maximum seconds to wait (None = wait forever)

        Returns:
            True if completed successfully, False if timed out or failed
        """
        if self._thread is None:
            logger.debug("No initialization started, nothing to wait for")
            return False

        self._thread.join(timeout=timeout)

        with self._lock:
            if not self._complete:
                logger.warning("Initialization did not complete within timeout")
                return False

            if self._error:
                logger.debug(f"Initialization failed: {self._error}")
                return False

            return True

    def get_result(self) -> Optional[SemanticSearchProtocol]:
        """
        Get the initialized semantic search object.

        Returns:
            Initialized semantic search or None if failed/not complete
        """
        with self._lock:
            return self._result

    def get_error(self) -> Optional[Exception]:
        """
        Get initialization error if any.

        Returns:
            Exception if initialization failed, None otherwise
        """
        with self._lock:
            return self._error

    def get_status(self) -> str:
        """
        Get human-readable status message.

        Returns:
            Status message
        """
        with self._lock:
            return self._status

    def _initialize_semantic_search(self) -> None:
        """
        Internal method to initialize semantic search in background thread.

        This is the actual heavy lifting that happens in the background.
        """
        try:
            logger.debug("Starting semantic search initialization in background")

            # Import heavy dependencies here (in background thread)
            from ..code_chunker import SemanticCodeChunker
            from .provider import LanceDBSearchProvider

            with self._lock:
                self._status = "Loading embedding model..."

            # Create chunker (lightweight)
            chunker = SemanticCodeChunker(chunk_size=100, overlap=3)

            # Create LanceDB provider (triggers FastEmbed model download if needed)
            # Store database in .scrappy/lancedb/ instead of .lancedb/ at project root
            with self._lock:
                self._status = "Initializing vector database..."

            search_provider = LanceDBSearchProvider(
                self._project_path,
                chunker,
                db_dir_name=".scrappy/lancedb"
            )

            # Trigger model loading in background by ensuring schema is ready
            # This downloads/loads the FastEmbed model NOW (in background)
            # instead of blocking later during index_files()
            with self._lock:
                self._status = "Loading embedding model (this may take 10-30s)..."

            search_provider._ensure_db()
            search_provider._ensure_schema()  # Loads FastEmbed model here

            with self._lock:
                self._result = search_provider
                self._status = "Complete"
                self._complete = True

            logger.debug("Semantic search initialized successfully in background")

        except ImportError as e:
            with self._lock:
                self._error = e
                self._status = f"Failed: Missing dependencies ({e})"
                self._complete = True
            logger.debug(f"Semantic search not available: {e}")

        except Exception as e:
            with self._lock:
                self._error = e
                self._status = f"Failed: {e}"
                self._complete = True
            logger.warning(f"Failed to initialize semantic search: {e}")


class NullInitializer:
    """
    No-op initializer for when background initialization is not needed.

    Always returns None and completes immediately.
    """

    def start(self) -> None:
        """No-op start."""
        pass

    def is_complete(self) -> bool:
        """Always complete."""
        return True

    def is_running(self) -> bool:
        """Never running."""
        return False

    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """Always returns False (no result)."""
        return False

    def get_result(self) -> None:
        """Always returns None."""
        return None

    def get_error(self) -> None:
        """No error."""
        return None

    def get_status(self) -> str:
        """Returns not available status."""
        return "Not available"

```

src/context/semantic/provider.py
```python
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

logger = logging.getLogger(__name__)

# --- Configuration Constants ---
DB_DIR_NAME = ".lancedb"
LOCK_FILE_NAME = "update.lock"
TABLE_NAME = "code_chunks"
TOKEN_ESTIMATION_CHAR_RATIO = 3.0
BATCH_SIZE = 1000
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


def _create_code_schema(embedding_func):
    """
    Create schema dynamically with embedding function.

    Args:
        embedding_func: Initialized embedding function

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
        content: str = embedding_func.SourceField()
        vector: Vector(embedding_func.ndims()) = embedding_func.VectorField()

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
        self._embedding_func = None
        self._code_schema = None

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
                self._code_schema = _create_code_schema(self._embedding_func)
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

        table = self._db.create_table(TABLE_NAME, schema=self._code_schema)

        # Normalize keys
        valid_files = {}
        skipped = 0
        for k, v in files.items():
            try:
                valid_files[self._normalize_path(k)] = v
            except ValueError as e:
                logger.debug(f"Skipping invalid path {k}: {e}")
                skipped += 1

        if skipped > 0:
            logger.info(f"Skipped {skipped} files with invalid paths")

        if not valid_files:
            logger.warning("No valid files after normalization")
            return

        logger.info(f"Indexing {len(valid_files)} valid files")
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

        logger.debug(f"Processing {len(files)} files for chunking")

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
                        table.add(batch)
                        batch = []

                logger.debug(f"Indexed {norm_path}: {file_chunk_count} chunks")

            except Exception as e:
                logger.error(f"Failed to chunk/index file {norm_path}: {e}")
                import traceback
                logger.debug(traceback.format_exc())

        if batch:
            logger.debug(f"Adding final batch of {len(batch)} chunks to table")
            table.add(batch)

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
```

[//]: # (TODO)

# P0
finish semantic search integration -- whe have partial implementation outlined above
    - loads in background on app start with rich progress
    - progress displayed clearly to user
    - progress display goes away shortly after complete

 - add logs or a way to interact. where's the db?
 - indexing htmlcov, temp, cache, everything



--------------------------------------------------------
1.  Token estimator still drifts on minified / Unicode files
--------------------------------------------------------
`len(content)/3` is fine for normal source, but collapses on:
- minified JS (1 char ≈ 1 token)  
- files with emoji or CJK comments (1 glyph ≈ 2–3 tokens).

Cheap improvement: keep a running **tiktoken** counter once you are within 20 % of the budget:

```python
import tiktoken
enc = tiktoken.get_encoding("cl100k_base")
...
if used_tokens + cost > max_tokens * 0.8:          # 80 % trigger
    cost = len(enc.encode(content))
    if used_tokens + cost > max_tokens:
        ...
```

You only pay for the exact count on the last few chunks.

--------------------------------------------------------
2.  Hash collision safety
--------------------------------------------------------
MD5 is fine for change detection, but if you ever expose `content_hash` to the user (e.g. for de-duplication UI) move to Blake3 or SHA-256 to avoid “but MD5 is broken” conversations.  One-line change, zero perf hit for code-base sizes.

--------------------------------------------------------
3.  FTS “replace=True” blocks readers
--------------------------------------------------------
Re-building the FTS index locks the table for ~100–400 ms per 10 k rows.  
LanceDB ≥ 0.6 lets you build incrementally:

```python
table.create_fts_index("content", replace=False)
```

Do it once after the **first** batch and never again; deletes are automatically handled.  Readers stay lock-free.


--------------------------------------------------------
5.  Optional: HNSW instead of IVF-PQ for < 1 M rows
--------------------------------------------------------
IVF-PQ is fastest for > 1 M vectors, but for the usual 50 k–200 k code-chunk data set HNSW gives *lower* latency and better recall.  One-liner:

```python
table.create_index(
    index_type="HNSW",
    metric="cosine",
    m=32,
    ef_construction=150,
    replace=True
)
```

===

The logic of **"Trust Git first, fall back to regex, check for binary last"** is the correct hierarchy for a developer tool.

### 1. The "Substring Match" Bug (Critical)
Your current regexes are too loose.
```python
r"build", r"dist", r"target"
```
**The problem:** These are searching purely for substrings.
*   `r"build"` will skip `src/builders.py`.
*   `r"dist"` will skip `src/distributed_systems.py`.
*   `r"target"` will skip `src/utils/retargeting.ts`.

**The Fix:**
You need to match these either as **directories** or **exact filenames**, not arbitrary substrings. The cleanest way in your `_should_skip` helper is to check path *parts*, or use stricter regex boundaries.

**Revised Regex Strategy:**
Update the regexes to match path separators or boundaries.
```python
# Match "dist" only if it appears as a complete folder name or file name
r"(^|/)dist(/|$)", r"(^|/)build(/|$)", r"(^|/)node_modules(/|$)"
```
*Or, clearer but slightly more Python code:* leave regexes for extensions (`\.pyc$`) and use a set for directory names.

### 2. The "Fall-back" Security Risk
```python
candidates = self._list_files_git() or self._list_files_plain()
```
If `git ls-files` fails (e.g., a corrupt git index, or git isn't installed), you silently fall back to `_list_files_plain`.
**The Risk:** If a user has a `secret.key` file that is ignored via `.gitignore`, and the git command fails, your tool falls back to the regex list. Since `secret.key` isn't in your hardcoded regex list, **it gets indexed**.

**The Fix:**
Only fall back if `path` is **not** a git repository. If it *is* a git repo but the command fails, you should probably warn/abort rather than ignoring the `.gitignore`.

```python
def _crawl_filesystem(self) -> dict[str, str]:
    is_git = (self._project_path / ".git").exists()
    candidates = set()
    
    if self.filter_config.respect_gitignore and is_git:
        candidates = self._list_files_git()
        # If git repo exists but returns empty/fails, DO NOT fall back 
        # unless you really trust your regex list to catch secrets.
        if not candidates: 
             # logic to decide if we fall back or warn
             pass 
    else:
        candidates = self._list_files_plain()
    
    # ... rest of function
```

### 3. The "Memory Bomb" (Large Files)
You are doing `path.read_text()`. If the repo contains a 2GB `server.log` or a minified JS bundle that isn't in `.gitignore`, your process will crash or hang.

**The Fix:**
Add a simple size check before reading.

```python
MAX_FILE_SIZE = 1024 * 1024 * 5  # 5MB limit

# ... inside the loop
stat = path.stat()
if stat.st_size > MAX_FILE_SIZE:
    logger.debug(f"Skipping large file: {rel} ({stat.st_size} bytes)")
    continue
```

---

### Polished Code (Incorporating Fixes)

Here is the refined version of your strategy. It fixes the regex boundaries and adds the size limit.

```python
from dataclasses import dataclass, field
import re
import subprocess
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

@dataclass
class IndexFilterConfig:
    # Mixed strategy: 
    # 1. Exact directory/file matches (safer than regex for names like "build")
    # 2. Regex for extensions/patterns
    
    ignore_names: set[str] = field(default_factory=lambda: {
        "__pycache__", "node_modules", ".git", ".svn", ".hg", 
        ".idea", ".vscode", ".DS_Store", "Thumbs.db",
        "dist", "build", "target", "venv", ".venv", ".env"
    })
    
    ignore_extensions: list[str] = field(default_factory=lambda: (
        r"\.py[cod]$", r"\.so$", r"\.dylib$", r"\.dll$", r"\.exe$", 
        r"\.bin$", r"\.jpe?g$", r"\.png$", r"\.gif$", r"\.svg$", r"\.ico$",
        r"\.lock$", r"package-lock\.json$", r"yarn\.lock$", 
    ))

    respect_gitignore: bool = True
    include_untracked: bool = False
    max_file_size_bytes: int = 5 * 1024 * 1024  # 5MB

    def __post_init__(self):
        self._compiled_ext = [re.compile(p, re.I) for p in self.ignore_extensions]

    def should_skip(self, path: Path, root: Path) -> bool:
        """
        Checks if path should be skipped based on static rules.
        path: absolute path
        root: project root
        """
        rel = path.relative_to(root)
        
        # 1. Check path parts against denied directory/file names
        # This prevents "dist" matching "distributed_systems.py"
        if any(part in self.ignore_names for part in rel.parts):
            return True
            
        # 2. Check regex extensions on the filename
        filename = path.name
        if any(r.search(filename) for r in self._compiled_ext):
            return True
            
        return False

class FileEnumerator:
    def __init__(self, project_path: Path, config: IndexFilterConfig):
        self.root = project_path
        self.cfg = config

    def _list_files_git(self) -> set[Path]:
        try:
            # -z is crucial for filenames with spaces/newlines
            cmd = ["git", "ls-files", "-z", "--cached"]
            if self.cfg.include_untracked:
                cmd.append("--others")
                cmd.append("--exclude-standard") # Important: Respect .gitignore for untracked files
                
            out = subprocess.check_output(cmd, cwd=self.root, stderr=subprocess.DEVNULL)
            
            # Decode and build paths
            paths = set()
            for p in out.split(b'\0'):
                if not p: continue
                try:
                    # Git returns bytes relative to root
                    fpath = self.root / p.decode('utf-8')
                    if fpath.is_file(): # Handle edge cases where file was deleted but listed
                        paths.add(fpath)
                except UnicodeDecodeError:
                    continue
            return paths
        except (subprocess.CalledProcessError, FileNotFoundError):
            return set()

    def _list_files_plain(self) -> set[Path]:
        keep = set()
        for p in self.root.rglob("*"):
            if p.is_file() and not self.cfg.should_skip(p, self.root):
                keep.add(p)
        return keep

    def crawl(self) -> dict[str, str]:
        is_git_repo = (self.root / ".git").exists()
        candidates = set()

        # Strategy: If it looks like git, try git. 
        # If git fails/returns empty in a git repo, do NOT fall back (security).
        # Only use plain walker if not a git repo or configured to ignore git.
        if self.cfg.respect_gitignore and is_git_repo:
            candidates = self._list_files_git()
            # If git command worked but returned nothing, candidates is empty. 
            # If git command failed, it returned empty.
            # Edge case: A new git repo with no commits/staged files will be empty.
        else:
            candidates = self._list_files_plain()

        results = {}
        for path in candidates:
            rel_str = path.relative_to(self.root).as_posix()
            
            # Even if git returned it, apply static filter for binary extensions/locks
            # (Git tracks package-lock.json, but you might not want to embed it)
            if self.cfg.should_skip(path, self.root):
                continue
                
            try:
                # Check size
                if path.stat().st_size > self.cfg.max_file_size_bytes:
                    logger.debug(f"Skipping large file {rel_str}")
                    continue
                
                # Check content
                results[rel_str] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Binary file that slipped past extension checks
                continue
            except Exception as e:
                logger.warning(f"Could not read {rel_str}: {e}")

        return results
```

### Summary of Changes
1.  **Fix Regex Matches:** Split checks into `parts` check (exact directory names) vs `regex` (extensions).
2.  **`--exclude-standard`**: Added to the untracked git command so untracked-but-ignored files don't show up.
3.  **Safety:** `read_text` is wrapped in a size check.
4.  **Output handling:** Switched `git` output handling to bytes (`b'\0'`) + decode to be safer with weird filenames on different OS environments.