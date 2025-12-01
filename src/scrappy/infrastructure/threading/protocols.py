"""
Threading protocols for background task management.

Defines abstract interfaces for thread-safe event handling and
background-to-main-thread communication.
"""

from typing import Protocol, Callable, Any, Optional
from enum import Enum
from dataclasses import dataclass


class EventType(Enum):
    """Types of background events."""

    INIT_COMPLETE = "init_complete"
    INIT_FAILED = "init_failed"
    PROGRESS = "progress"


@dataclass
class BackgroundEvent:
    """
    Event from background thread.

    Represents a notification from a background thread that should be
    processed on the main thread.

    Attributes:
        event_type: Type of event (complete, failed, progress)
        source: Identifier for the source of the event (e.g., "semantic_search")
        data: Optional data payload (e.g., initialized object)
        error: Optional exception if event represents a failure
    """

    event_type: EventType
    source: str
    data: Any = None
    error: Optional[Exception] = None


class EventQueueProtocol(Protocol):
    """
    Protocol for thread-safe event queue.

    Enables background threads to submit events that are processed
    on the main thread, ensuring callbacks run in the correct context.

    Implementations:
    - ThreadSafeEventQueue: Production implementation using queue.Queue
    - TestEventQueue: Testing implementation with synchronous processing

    Example:
        queue = ThreadSafeEventQueue()

        # Background thread submits event
        queue.put(BackgroundEvent(
            event_type=EventType.INIT_COMPLETE,
            source="semantic_search",
            data=search_provider
        ))

        # Main thread processes events
        queue.register_handler("semantic_search", handle_semantic_event)
        queue.process_pending()
    """

    def put(self, event: BackgroundEvent) -> None:
        """
        Submit event to queue (thread-safe).

        Can be called from any thread. Events are queued for processing
        on the main thread.

        Args:
            event: Event to submit
        """
        ...

    def get(self, timeout: Optional[float] = None) -> Optional[BackgroundEvent]:
        """
        Get next event (blocks if empty until timeout).

        Args:
            timeout: Maximum seconds to wait (None = wait forever)

        Returns:
            Next event or None if timeout reached
        """
        ...

    def get_nowait(self) -> Optional[BackgroundEvent]:
        """
        Get next event without blocking.

        Returns:
            Next event or None if queue is empty
        """
        ...

    def register_handler(
        self, source: str, handler: Callable[[BackgroundEvent], None]
    ) -> None:
        """
        Register handler for events from a specific source.

        Args:
            source: Event source identifier to handle
            handler: Function to call when event from source is processed
        """
        ...

    def process_pending(self) -> int:
        """
        Process all pending events on current thread.

        Calls registered handlers for each event. Should be called
        from the main thread in an event loop.

        Returns:
            Number of events processed
        """
        ...


class MainThreadCallbackProtocol(Protocol):
    """
    Protocol for scheduling callbacks on main thread.

    Alternative to EventQueueProtocol for simple callback scheduling
    without event typing.

    Implementations:
    - MainThreadCallbackScheduler: Production implementation
    - TestCallbackScheduler: Testing implementation

    Example:
        scheduler = MainThreadCallbackScheduler()

        # Background thread schedules callback
        scheduler.schedule(lambda: ui.update("Ready"))

        # Main thread processes callbacks
        scheduler.process_callbacks()
    """

    def schedule(self, callback: Callable[[], None]) -> None:
        """
        Schedule callback to run on main thread.

        Args:
            callback: Function to call on main thread
        """
        ...

    def process_callbacks(self) -> int:
        """
        Process pending callbacks on current thread.

        Returns:
            Number of callbacks processed
        """
        ...


class ManagedThreadProtocol(Protocol):
    """
    Protocol for threads with proper lifecycle management.

    Unlike daemon threads which are killed abruptly on process exit,
    managed threads support graceful shutdown with configurable timeouts.

    Implementations:
    - ManagedThread: Production implementation with shutdown signaling

    Example:
        def worker(thread: ManagedThreadProtocol) -> None:
            while not thread.shutdown_requested:
                # Do work
                pass

        managed = ManagedThread(target=worker, name="Worker")
        managed.start()

        # Later, request graceful shutdown
        if managed.stop(timeout=5.0):
            print("Thread stopped cleanly")
        else:
            print("Thread did not stop within timeout")
    """

    @property
    def shutdown_requested(self) -> bool:
        """
        Check if shutdown has been requested.

        Worker functions should poll this property periodically
        and exit cleanly when it returns True.

        Returns:
            True if shutdown was requested via stop()
        """
        ...

    def start(self) -> None:
        """
        Start the thread.

        Does nothing if thread is already started.
        """
        ...

    def stop(self, timeout: float = 5.0) -> bool:
        """
        Request thread stop and wait for completion.

        Sets the shutdown flag and waits for the thread to exit.

        Args:
            timeout: Maximum seconds to wait for thread to stop

        Returns:
            True if thread stopped within timeout, False otherwise
        """
        ...

    def is_running(self) -> bool:
        """
        Check if thread is currently running.

        Returns:
            True if thread is alive and running
        """
        ...

    def join(self, timeout: Optional[float] = None) -> None:
        """
        Wait for thread to complete.

        Args:
            timeout: Maximum seconds to wait (None = wait forever)
        """
        ...
