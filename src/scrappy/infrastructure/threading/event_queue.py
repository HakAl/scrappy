"""
Thread-safe event queue for background-to-main communication.

Provides a queue-based mechanism for background threads to submit events
that are processed on the main thread.
"""

import logging
import queue
from typing import Optional, Callable, Dict

from .protocols import BackgroundEvent

logger = logging.getLogger(__name__)


class ThreadSafeEventQueue:
    """
    Thread-safe event queue for background-to-main communication.

    Events can be submitted from any thread via put(), and are processed
    on the calling thread via process_pending(). This ensures callbacks
    always execute on the main thread when process_pending() is called there.

    Thread Safety:
    - put(): Thread-safe, can be called from any thread
    - get(): Thread-safe, blocks until event available or timeout
    - get_nowait(): Thread-safe, returns immediately
    - register_handler(): Should be called from main thread during setup
    - process_pending(): Should be called from main thread in event loop

    Example:
        queue = ThreadSafeEventQueue()

        # Setup (main thread)
        queue.register_handler("semantic_search", handle_semantic_event)

        # Background thread
        queue.put(BackgroundEvent(
            event_type=EventType.INIT_COMPLETE,
            source="semantic_search",
            data=result
        ))

        # Main thread event loop
        while running:
            queue.process_pending()
            # ... other work ...
    """

    def __init__(self) -> None:
        """Initialize the event queue."""
        self._queue: queue.Queue[BackgroundEvent] = queue.Queue()
        self._handlers: Dict[str, Callable[[BackgroundEvent], None]] = {}

    def put(self, event: BackgroundEvent) -> None:
        """
        Submit event to queue (thread-safe, can be called from any thread).

        Args:
            event: Event to submit
        """
        logger.debug(f"Event submitted: {event.event_type.value} from {event.source}")
        self._queue.put(event)

    def get(self, timeout: Optional[float] = None) -> Optional[BackgroundEvent]:
        """
        Get next event (blocks if empty until timeout).

        Args:
            timeout: Maximum seconds to wait (None = wait forever)

        Returns:
            Next event or None if timeout reached
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_nowait(self) -> Optional[BackgroundEvent]:
        """
        Get next event without blocking.

        Returns:
            Next event or None if queue is empty
        """
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def register_handler(
        self, source: str, handler: Callable[[BackgroundEvent], None]
    ) -> None:
        """
        Register handler for events from a specific source.

        Args:
            source: Event source identifier to handle
            handler: Function to call when event from source is processed
        """
        logger.debug(f"Registered handler for source: {source}")
        self._handlers[source] = handler

    def unregister_handler(self, source: str) -> None:
        """
        Unregister handler for events from a specific source.

        Args:
            source: Event source identifier to unregister
        """
        if source in self._handlers:
            del self._handlers[source]
            logger.debug(f"Unregistered handler for source: {source}")

    def process_pending(self) -> int:
        """
        Process all pending events on current thread.

        Calls registered handlers for each event. Should be called
        from the main thread in an event loop.

        Returns:
            Number of events processed
        """
        count = 0
        while True:
            event = self.get_nowait()
            if event is None:
                break

            handler = self._handlers.get(event.source)
            if handler:
                try:
                    logger.debug(
                        f"Processing event: {event.event_type.value} "
                        f"from {event.source}"
                    )
                    handler(event)
                except Exception as e:
                    logger.error(
                        f"Error processing event from {event.source}: {e}",
                        exc_info=True,
                    )
            else:
                logger.warning(f"No handler registered for source: {event.source}")

            count += 1

        return count

    def pending_count(self) -> int:
        """
        Get approximate number of pending events.

        Note: This is approximate due to race conditions. Use only for
        monitoring/debugging, not for control flow.

        Returns:
            Approximate number of pending events
        """
        return self._queue.qsize()

    def clear(self) -> int:
        """
        Clear all pending events without processing.

        Returns:
            Number of events cleared
        """
        count = 0
        while True:
            try:
                self._queue.get_nowait()
                count += 1
            except queue.Empty:
                break
        return count
