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
