"""
Output adapter for bridging OutputSink protocol to thread-safe queue.

This adapter allows non-Textual code to post output to the TUI
via a thread-safe queue that the main Textual event loop consumes.
"""

from typing import Any, Dict, Optional, TYPE_CHECKING
import threading
import uuid
from queue import Queue, Empty

if TYPE_CHECKING:
    from ..protocols import ActivityState


class TextualOutputAdapter:
    """Adapter that bridges OutputSink protocol to thread-safe queue."""

    # Sentinel value for shutdown - wakes blocked consumer immediately
    SHUTDOWN_SENTINEL = ('_shutdown', None)

    def __init__(self) -> None:
        self._queue: Queue[tuple[str, Any]] = Queue()
        self._flush_events: Dict[str, threading.Event] = {}
        self._flush_lock = threading.Lock()
        self._shutdown_requested = False

    def post_output(self, content: str) -> None:
        self._queue.put(('output', content))

    def post_renderable(self, obj: Any) -> None:
        self._queue.put(('renderable', obj))

    def post_tasks_updated(self, tasks: list) -> None:
        """Post task list update to UI.

        Args:
            tasks: List of Task objects to display.
        """
        self._queue.put(('tasks', tasks))

    def post_activity(
        self,
        state: "ActivityState",
        message: str = "",
        elapsed_ms: int = 0,
    ) -> None:
        """Post activity state change to UI.

        Thread-safe method to update the activity indicator from worker threads.

        Args:
            state: Current activity state (IDLE, THINKING, TOOL_EXECUTION, etc.)
            message: Optional descriptive message
            elapsed_ms: Elapsed time in milliseconds
        """
        self._queue.put(('activity', (state, message, elapsed_ms)))

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait for all pending output to be processed.

        Posts a flush sentinel and waits for consumer to acknowledge it.
        Returns True if flushed successfully, False on timeout.
        """
        flush_id = str(uuid.uuid4())
        event = threading.Event()

        with self._flush_lock:
            self._flush_events[flush_id] = event

        self._queue.put(('flush', flush_id))

        success = event.wait(timeout=timeout)

        with self._flush_lock:
            self._flush_events.pop(flush_id, None)

        return success

    def acknowledge_flush(self, flush_id: str) -> None:
        """Called by consumer when flush sentinel is processed."""
        with self._flush_lock:
            event = self._flush_events.get(flush_id)
            if event:
                event.set()

    def request_shutdown(self) -> None:
        """Signal the consumer to exit immediately.

        Puts a sentinel on the queue to wake blocked get_message() calls.
        Should be called before Textual's exit() to ensure the consumer
        worker exits promptly.
        """
        self._shutdown_requested = True
        # Put sentinel to wake any blocked consumer
        self._queue.put(self.SHUTDOWN_SENTINEL)

    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_requested

    def get_message(self, block: bool = True, timeout: Optional[float] = None) -> Optional[tuple[str, Any]]:
        try:
            msg = self._queue.get(block=block, timeout=timeout)
            # Check for shutdown sentinel
            if msg == self.SHUTDOWN_SENTINEL:
                return None
            return msg
        except Empty:
            return None
