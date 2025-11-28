"""
Background initializer for semantic search with FastEmbed and LanceDB.

Loads heavy dependencies (FastEmbed models, LanceDB) in a background thread
to prevent UI freezing during startup.
"""

import logging
import threading
import warnings
from pathlib import Path
from typing import Optional, Any, TYPE_CHECKING

from ..protocols import SemanticSearchProtocol
from ...infrastructure.protocols import BackgroundInitializerProtocol
from ...infrastructure.threading.managed_thread import ManagedThread
from .config import SemanticIndexConfig

if TYPE_CHECKING:
    from ...infrastructure.threading.protocols import EventQueueProtocol

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

    def __init__(
        self,
        project_path: Path,
        event_queue: Optional["EventQueueProtocol"] = None,
    ):
        """
        Initialize semantic search loader.

        Args:
            project_path: Path to project root for semantic search
            event_queue: Optional event queue for main-thread-safe notifications.
                        When provided, completion/failure events are submitted
                        to the queue instead of using callback threads.
        """
        self._project_path = project_path
        self._event_queue = event_queue
        self._managed_thread: Optional[ManagedThread] = None
        self._complete = False
        self._result: Optional[SemanticSearchProtocol] = None
        self._error: Optional[Exception] = None
        self._lock = threading.Lock()
        self._status = "Not started"
        self._on_ready_callback = None

    def set_on_ready_callback(self, callback) -> None:
        """Set callback to invoke when model is ready.

        Args:
            callback: Function taking the search_provider as argument
        """
        self._on_ready_callback = callback

    def start(self) -> None:
        """
        Start background initialization.

        This is non-blocking and returns immediately.
        Uses ManagedThread for proper lifecycle management instead of daemon threads.
        """
        with self._lock:
            if self._managed_thread is not None:
                logger.debug("Initialization already started")
                return

            self._status = "Initializing semantic search..."
            self._managed_thread = ManagedThread(
                target=self._initialize_worker,
                name="SemanticSearchInit"
            )
            self._managed_thread.start()
            logger.debug("Started background semantic search initialization")

    def is_complete(self) -> bool:
        """Check if initialization is complete."""
        with self._lock:
            return self._complete

    def is_running(self) -> bool:
        """Check if initialization is currently running."""
        with self._lock:
            return self._managed_thread is not None and not self._complete

    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for initialization to complete.

        Args:
            timeout: Maximum seconds to wait (None = wait forever)

        Returns:
            True if completed successfully, False if timed out or failed
        """
        if self._managed_thread is None:
            logger.debug("No initialization started, nothing to wait for")
            return False

        self._managed_thread.join(timeout=timeout)

        with self._lock:
            if not self._complete:
                logger.warning("Initialization did not complete within timeout")
                return False

            if self._error:
                logger.debug(f"Initialization failed: {self._error}")
                return False

            return True

    def wait_with_callback(self, callback, timeout: Optional[float] = None) -> None:
        """
        DEPRECATED: Wait for initialization to complete and call a callback when done.

        This method spawns a thread that runs the callback, which may cause issues
        if the callback contains code that must run on the main thread (e.g., signal
        registration, UI updates).

        Use event_queue pattern instead:
            initializer = SemanticSearchInitializer(path, event_queue=queue)
            queue.register_handler("semantic_search", handler)
            initializer.start()
            # Later in main loop: queue.process_pending()

        Args:
            callback: Function to call when initialization is complete
            timeout: Maximum seconds to wait (None = wait forever)
        """
        warnings.warn(
            "wait_with_callback is deprecated. Use event_queue pattern instead. "
            "Pass event_queue to constructor and call process_pending() on main thread.",
            DeprecationWarning,
            stacklevel=2,
        )

        def wait_thread():
            completed = self.wait_for_completion(timeout=timeout)
            callback(completed, self.get_result(), self.get_error())

        thread = threading.Thread(target=wait_thread)
        thread.daemon = True
        thread.start()

    def get_result(self) -> Optional[Any]:
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

    def shutdown(self, timeout: float = 5.0) -> bool:
        """
        Gracefully shutdown background initialization.

        Requests the background thread to stop and waits for it to finish.
        If initialization is in progress, it will be interrupted at the
        next shutdown check point.

        Args:
            timeout: Maximum seconds to wait for thread to stop

        Returns:
            True if thread stopped within timeout, False if still running
        """
        if self._managed_thread is None:
            return True

        logger.debug(f"Requesting shutdown of semantic search initializer")
        stopped = self._managed_thread.stop(timeout)

        if stopped:
            logger.debug("Semantic search initializer shutdown complete")
        else:
            logger.debug(
                f"Semantic search initializer did not stop within {timeout}s"
            )

        return stopped

    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested.

        Returns:
            True if shutdown was requested, False otherwise
        """
        if self._managed_thread:
            return self._managed_thread.shutdown_requested
        return False

    def _initialize_worker(self, thread: ManagedThread) -> None:
        """
        Worker function for ManagedThread to initialize semantic search.

        Checks for shutdown requests at key points to allow graceful termination.

        Args:
            thread: The ManagedThread instance, used to check shutdown_requested
        """
        try:
            logger.debug("Starting semantic search initialization in background")

            # Check for shutdown before heavy imports
            if thread.shutdown_requested:
                logger.debug("Shutdown requested before initialization started")
                return

            # Import heavy dependencies here (in background thread)
            from .chunkers import CompositeCodeChunker
            from .provider import LanceDBSearchProvider

            with self._lock:
                self._status = "Loading embedding model..."

            # Check for shutdown after imports
            if thread.shutdown_requested:
                logger.debug("Shutdown requested after imports")
                return

            # Create chunker (AST-aware for Python, fallback for other languages)
            chunker = CompositeCodeChunker(
                fallback_chunk_size=60,
                fallback_overlap=15,
            )

            # Create LanceDB provider (triggers FastEmbed model download if needed)
            # Store database in .scrappy/lancedb/ instead of .lancedb/ at project root
            with self._lock:
                self._status = "Initializing vector database..."

            # Check for shutdown before database initialization
            if thread.shutdown_requested:
                logger.debug("Shutdown requested before database init")
                return

            config = SemanticIndexConfig(db_dir_name=".scrappy/lancedb")
            search_provider = LanceDBSearchProvider(
                self._project_path,
                chunker,
                config=config,
            )

            # Trigger model loading in background by ensuring schema is ready
            # This downloads/loads the FastEmbed model NOW (in background)
            # instead of blocking later during index_files()
            with self._lock:
                self._status = "Loading embedding model (this may take 10-30s)..."

            # Check for shutdown before expensive model loading
            if thread.shutdown_requested:
                logger.debug("Shutdown requested before model loading")
                return

            search_provider._ensure_db()

            # Check for shutdown between DB and schema setup
            if thread.shutdown_requested:
                logger.debug("Shutdown requested after DB setup")
                return

            # Now load the embedding model by accessing the embedding function
            # This is the critical step that loads the heavy model in the background
            search_provider._ensure_schema()  # This will call _create_embedding_func()

            # Check for shutdown before test embedding
            if thread.shutdown_requested:
                logger.debug("Shutdown requested after schema setup")
                return

            # Additional step to ensure the model is fully loaded
            # Generate a dummy embedding to trigger model initialization if needed
            try:
                if search_provider._embedding_func:
                    # This will trigger the actual model loading if not already done
                    _ = search_provider._embedding_func.generate_embeddings(["test"])
                    logger.debug("Embedding model is fully loaded")
            except Exception as e:
                logger.warning(f"Error during test embedding generation: {e}")

            # Final shutdown check before marking complete
            if thread.shutdown_requested:
                logger.debug("Shutdown requested before completion")
                return

            with self._lock:
                self._result = search_provider
                self._status = "Complete"
                self._complete = True

            logger.debug("Semantic search initialized successfully in background")

            # Notify via event queue if configured (main-thread-safe)
            self._emit_completion_event(search_provider)

            # Call on_ready_callback (runs on background thread)
            if self._on_ready_callback:
                try:
                    self._on_ready_callback(search_provider)
                except Exception as e:
                    logger.warning(f"Error in on_ready_callback: {e}")

        except ImportError as e:
            with self._lock:
                self._error = e
                self._status = f"Failed: Missing dependencies ({e})"
                self._complete = True
            logger.debug(f"Semantic search not available: {e}")
            self._emit_failure_event(e)

        except Exception as e:
            with self._lock:
                self._error = e
                self._status = f"Failed: {e}"
                self._complete = True
            logger.warning(f"Failed to initialize semantic search: {e}")
            self._emit_failure_event(e)

    def _emit_completion_event(self, result: Any) -> None:
        """
        Emit initialization complete event via event queue.

        Args:
            result: The initialized semantic search provider
        """
        if self._event_queue:
            from ...infrastructure.threading.protocols import BackgroundEvent, EventType

            self._event_queue.put(
                BackgroundEvent(
                    event_type=EventType.INIT_COMPLETE,
                    source="semantic_search",
                    data=result,
                )
            )
            logger.debug("Emitted INIT_COMPLETE event to queue")

    def _emit_failure_event(self, error: Exception) -> None:
        """
        Emit initialization failed event via event queue.

        Args:
            error: The exception that caused the failure
        """
        if self._event_queue:
            from ...infrastructure.threading.protocols import BackgroundEvent, EventType

            self._event_queue.put(
                BackgroundEvent(
                    event_type=EventType.INIT_FAILED,
                    source="semantic_search",
                    error=error,
                )
            )
            logger.debug("Emitted INIT_FAILED event to queue")


class NullInitializer:
    """
    No-op initializer for when background initialization is not needed.

    Always returns None and completes immediately.
    Implements BackgroundInitializerProtocol.
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

    def shutdown(self, timeout: float = 5.0) -> bool:
        """No-op shutdown, always returns True (success)."""
        return True

    def is_shutdown_requested(self) -> bool:
        """Always returns False - null initializer is never shutting down."""
        return False

    def set_on_ready_callback(self, callback) -> None:
        """No-op - null initializer never becomes ready."""
        pass
