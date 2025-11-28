"""
Semantic search lifecycle management.

Coordinates semantic search initialization, indexing, and search operations.
Extracts the semantic search complexity from CodebaseContext for better
testability and single responsibility.
"""

import logging
from pathlib import Path
from typing import Optional, Callable, TYPE_CHECKING

from ..infrastructure.protocols import (
    BackgroundInitializerProtocol,
    ProgressReporterProtocol,
)
from ..infrastructure.threading import (
    EventQueueProtocol,
    ThreadSafeEventQueue,
    BackgroundEvent,
    EventType,
)

if TYPE_CHECKING:
    from .protocols import (
        SemanticSearchProtocol,
        FileCollectorProtocol,
        SearchResult,
    )

logger = logging.getLogger(__name__)


class SemanticSearchManager:
    """
    Manages semantic search lifecycle.

    Coordinates semantic search initialization, indexing, and search operations.
    Separates the complexity of background initialization, event handling,
    and progress reporting from CodebaseContext.

    Single Responsibility: Coordinate semantic search lifecycle.

    Usage:
        manager = SemanticSearchManager(project_path)
        manager.start_background_init()

        # Later, in event loop
        manager.process_events()

        # When ready
        if manager.is_ready():
            result = manager.search("error handling")
    """

    def __init__(
        self,
        project_path: Path,
        initializer: Optional[BackgroundInitializerProtocol] = None,
        event_queue: Optional[EventQueueProtocol] = None,
        io: Optional['CLIIOProtocol'] = None,
    ):
        """
        Initialize semantic search manager.

        Args:
            project_path: Path to project root
            initializer: Background initializer for semantic search (auto-created if None)
            event_queue: Event queue for background notifications (auto-created if None)
            io: IO interface for progress reporting (optional)
        """
        self._project_path = project_path
        self._event_queue = event_queue or ThreadSafeEventQueue()
        self._io = io

        # Semantic search state
        self._semantic_search: Optional['SemanticSearchProtocol'] = None
        self._initializer = initializer
        self._progress_callback: Optional[Callable[[str], None]] = None
        self._is_indexed = False
        self._file_collector_callback: Optional[Callable[[], Optional['FileCollectorProtocol']]] = None
        self._cancellation_check: Optional[Callable[[], bool]] = None

    @property
    def event_queue(self) -> EventQueueProtocol:
        """Get the event queue for external processing."""
        return self._event_queue

    def set_initializer(self, initializer: BackgroundInitializerProtocol) -> None:
        """
        Set the background initializer.

        Args:
            initializer: Background initializer to use
        """
        self._initializer = initializer

    def set_file_collector_callback(
        self,
        callback: Optional[Callable[[], Optional['FileCollectorProtocol']]]
    ) -> None:
        """
        Set callback to get file collector for auto-indexing.

        When INIT_COMPLETE event is received, this callback will be invoked
        to get a file collector. If the collector is available, auto-indexing
        will be triggered.

        Args:
            callback: Function returning FileCollectorProtocol or None
        """
        self._file_collector_callback = callback

    def start_background_init(self) -> None:
        """
        Start background initialization of semantic search.

        Non-blocking - returns immediately. Use is_ready() or
        process_events() to check completion status.
        """
        if not self._initializer:
            self._initializer = self._create_default_initializer()

        if self._initializer:
            logger.debug("Starting background semantic search initialization")

            # Set callback for when model is ready (called from background thread)
            if hasattr(self._initializer, 'set_on_ready_callback'):
                self._initializer.set_on_ready_callback(self._on_model_ready)

            # Keep event handler registration for backward compatibility
            self._event_queue.register_handler(
                "semantic_search",
                self._handle_event,
            )

            self._initializer.start()
        else:
            logger.debug("No semantic initializer available")

    def _create_default_initializer(self) -> Optional[BackgroundInitializerProtocol]:
        """Create default semantic search initializer."""
        try:
            from .semantic.initializer import SemanticSearchInitializer
            logger.debug("Creating SemanticSearchInitializer with event queue")
            return SemanticSearchInitializer(
                self._project_path,
                event_queue=self._event_queue,
            )
        except ImportError as e:
            logger.debug(f"Semantic search dependencies not available: {e}")
            from .semantic.initializer import NullInitializer
            return NullInitializer()

    def _handle_event(self, event: BackgroundEvent) -> None:
        """
        Handle semantic search events (runs on main thread via event queue).

        Args:
            event: Background event from semantic search initialization
        """
        if event.event_type == EventType.INIT_COMPLETE:
            logger.info("Semantic search model ready (via event)")
            self._notify_progress("Semantic search ready")

            # Cache the result
            self._semantic_search = event.data

            # Trigger auto-indexing if file collector callback is set
            if self._file_collector_callback:
                logger.info("Triggering auto-indexing...")
                self._notify_progress("Starting file indexing...")
                try:
                    file_collector = self._file_collector_callback()
                    if file_collector:
                        self.index_files(file_collector)
                    else:
                        logger.debug("File collector callback returned None, skipping auto-indexing")
                except Exception as e:
                    logger.warning(f"Auto-indexing failed: {e}")
                    self._notify_progress(f"Auto-indexing failed: {e}")

        elif event.event_type == EventType.INIT_FAILED:
            logger.warning(f"Semantic search initialization failed: {event.error}")
            self._notify_progress(f"Semantic search initialization failed: {event.error}")

    def _on_model_ready(self, search_provider) -> None:
        """Called from background thread when model finishes loading.

        Args:
            search_provider: The initialized SemanticSearchProtocol instance
        """
        logger.info("Semantic search model ready (via callback)")
        self._semantic_search = search_provider
        self._notify_progress("Semantic search ready")

        # Wire up cancellation before indexing
        self._set_cancellation_from_initializer()

        # Trigger indexing (runs on background thread)
        if self._file_collector_callback:
            self._notify_progress("Starting file indexing...")
            try:
                file_collector = self._file_collector_callback()
                if file_collector:
                    self.index_files(file_collector)
                else:
                    logger.debug("File collector callback returned None")
            except Exception as e:
                logger.warning(f"Auto-indexing failed: {e}")
                self._notify_progress(f"Indexing failed: {e}")

    def _set_cancellation_from_initializer(self) -> None:
        """Wire up cancellation check to initializer's shutdown state."""
        if self._initializer and hasattr(self._initializer, 'is_shutdown_requested'):
            self.set_cancellation_check(self._initializer.is_shutdown_requested)

    def is_ready(self) -> bool:
        """
        Check if semantic search is ready to use.

        Returns:
            True if initialized and ready for search, False otherwise
        """
        if self._semantic_search:
            return True
        if self._initializer:
            return (
                self._initializer.is_complete()
                and self._initializer.get_error() is None
            )
        return False

    def get_status(self) -> Optional[str]:
        """
        Get human-readable initialization status.

        Returns:
            Status string, None if no initializer configured
        """
        if self._initializer:
            return self._initializer.get_status()
        return None

    def get_search_provider(self) -> Optional['SemanticSearchProtocol']:
        """
        Get the semantic search provider if available.

        Returns:
            SemanticSearchProtocol instance or None if not available
        """
        if self._semantic_search:
            return self._semantic_search

        # Check if background initializer has completed
        if self._initializer and self._initializer.is_complete():
            result = self._initializer.get_result()
            if result:
                self._semantic_search = result
                return result
            else:
                error = self._initializer.get_error()
                logger.debug(f"Semantic search initialization failed: {error}")
                return None

        return None

    def search(self, query: str, max_tokens: int = 4000) -> Optional['SearchResult']:
        """
        Search indexed codebase semantically.

        Args:
            query: Search query
            max_tokens: Maximum tokens in results

        Returns:
            SearchResult if available, None if not ready
        """
        provider = self.get_search_provider()
        if not provider or not provider.is_indexed():
            return None

        try:
            return provider.search(query, max_tokens=max_tokens)
        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")
            return None

    def index_files(self, file_collector: 'FileCollectorProtocol') -> None:
        """
        Index files for semantic search.

        Uses batched file collection to prevent memory spikes.

        Args:
            file_collector: Collector providing files to index
        """
        provider = self.get_search_provider()
        if not provider:
            logger.warning("Cannot index - semantic search not available")
            return

        # Create progress reporter
        from ..infrastructure.progress import UnifiedIOProgressReporter, NullProgressReporter
        progress = UnifiedIOProgressReporter(self._io) if self._io else NullProgressReporter()
        progress_started = False

        try:
            logger.info("Starting semantic search indexing (batched)...")
            self._notify_progress("Preparing file collector...")

            if file_collector is None:
                logger.warning("No file collector available - skipping indexing")
                self._notify_progress("No file collector available")
                return

            # Set progress reporter on the provider
            provider.set_progress_reporter(progress)

            self._notify_progress("Collecting and indexing files in batches...")

            total_indexed = 0
            batch_count = 0

            progress.start("Indexing files for semantic search")
            progress_started = True

            logger.info("Starting batch collection...")
            for batch in file_collector.collect_files_batched(batch_size=20):
                # Check for cancellation between batches
                if self._is_cancelled():
                    logger.info("Indexing cancelled by user")
                    self._notify_progress("Indexing cancelled")
                    return

                batch_count += 1
                batch_size = len(batch)
                total_indexed += batch_size
                logger.info(f"Received batch {batch_count} with {batch_size} files")

                progress_msg = f"Indexing files: batch {batch_count} ({total_indexed} files total)"
                progress.update(description=progress_msg)

                self._notify_progress(
                    f"Indexing batch {batch_count} ({batch_size} files, "
                    f"{total_indexed} total)..."
                )

                logger.debug(f"Indexing batch {batch_count} with {batch_size} files")
                provider.index_files(batch, is_batch=True)

            if total_indexed == 0:
                logger.warning("No files collected for semantic search indexing")
                self._notify_progress("No files to index")
                return

            self._is_indexed = True
            logger.info(f"Semantic search indexing complete ({total_indexed} files)")
            self._notify_progress(f"Indexing complete ({total_indexed} files)")

        except Exception as e:
            logger.error(f"Semantic indexing failed: {e}")
            import traceback
            logger.debug(traceback.format_exc())

            self._notify_progress(f"Indexing failed: {e}")
            if progress_started:
                progress.error(str(e))

            # Gracefully degrade - disable semantic search
            self._semantic_search = None

        finally:
            if progress_started:
                progress.complete("Indexing complete")

            # Reset progress reporter
            if provider:
                provider.set_progress_reporter(NullProgressReporter())

    def process_events(self) -> int:
        """
        Process pending background events.

        Should be called periodically from main thread.

        Returns:
            Number of events processed
        """
        return self._event_queue.process_pending()

    def set_progress_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        """
        Set callback for progress updates.

        Args:
            callback: Function taking a string message (or None to clear)
        """
        self._progress_callback = callback

    def set_cancellation_check(self, check: Optional[Callable[[], bool]]) -> None:
        """
        Set callback to check if indexing should be cancelled.

        The callback should return True if indexing should stop.
        Called between batch operations for cooperative cancellation.

        Args:
            check: Function returning True if cancelled (or None to clear)
        """
        self._cancellation_check = check

    def _is_cancelled(self) -> bool:
        """Check if indexing has been cancelled."""
        if self._cancellation_check:
            try:
                return self._cancellation_check()
            except Exception:
                return False
        return False

    def _notify_progress(self, message: str) -> None:
        """Notify registered callback of progress."""
        if self._progress_callback:
            try:
                self._progress_callback(message)
            except Exception as e:
                logger.debug(f"Error in progress callback: {e}")

    def shutdown(self) -> None:
        """Signal background tasks to stop and clean up resources."""
        # Break reference cycle to allow GC
        self._progress_callback = None
        self._file_collector_callback = None

        if self._initializer is not None:
            stopped = self._initializer.shutdown()
            if not stopped:
                logger.info("Indexing interrupted - will resume on next launch")


class NullSemanticSearchManager:
    """
    No-op semantic search manager.

    Used when semantic search is not available or for testing.
    """

    @property
    def event_queue(self) -> EventQueueProtocol:
        """Get a null event queue."""
        return ThreadSafeEventQueue()

    def set_file_collector_callback(
        self,
        callback: Optional[Callable[[], Optional['FileCollectorProtocol']]]
    ) -> None:
        """No-op."""
        pass

    def start_background_init(self) -> None:
        """No-op."""
        pass

    def is_ready(self) -> bool:
        """Always returns False."""
        return False

    def get_status(self) -> Optional[str]:
        """Returns None."""
        return None

    def get_search_provider(self) -> None:
        """Returns None."""
        return None

    def search(self, query: str, max_tokens: int = 4000) -> None:
        """Returns None."""
        return None

    def index_files(self, file_collector: 'FileCollectorProtocol') -> None:
        """No-op."""
        pass

    def process_events(self) -> int:
        """Returns 0."""
        return 0

    def set_progress_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        """No-op."""
        pass

    def set_cancellation_check(self, check: Optional[Callable[[], bool]]) -> None:
        """No-op."""
        pass

    def shutdown(self) -> None:
        """No-op shutdown."""
        pass
