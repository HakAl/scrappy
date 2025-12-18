"""
Cancellation token for agent operations.

Provides thread-safe cancellation signaling for cross-thread agent control.
"""

import threading
from typing import Protocol


class CancellationTokenProtocol(Protocol):
    """Protocol for cancellation tokens."""

    def cancel(self) -> None:
        """Signal cancellation."""
        ...

    def is_cancelled(self) -> bool:
        """Check if cancelled."""
        ...

    def reset(self) -> None:
        """Reset for reuse."""
        ...


class CancellationToken:
    """Thread-safe cancellation signal for agent operations.

    Used to signal cancellation from UI thread to worker thread running agent.
    The agent checks this token between iterations and gracefully stops.

    Supports force cancel: after multiple cancel requests, is_force_cancelled()
    returns True to indicate immediate termination is requested.
    """

    def __init__(self):
        self._cancelled = threading.Event()
        self._force_cancelled = threading.Event()
        self._cancel_count = 0
        self._lock = threading.Lock()

    def cancel(self) -> None:
        """Signal cancellation. Multiple calls trigger force cancel."""
        with self._lock:
            self._cancel_count += 1
            self._cancelled.set()
            if self._cancel_count >= 2:
                self._force_cancelled.set()

    def is_cancelled(self) -> bool:
        """Check if cancelled (graceful)."""
        return self._cancelled.is_set()

    def is_force_cancelled(self) -> bool:
        """Check if force cancel was requested (immediate termination)."""
        return self._force_cancelled.is_set()

    def reset(self) -> None:
        """Reset for reuse."""
        with self._lock:
            self._cancelled.clear()
            self._force_cancelled.clear()
            self._cancel_count = 0
