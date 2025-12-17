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
    """

    def __init__(self):
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        """Signal cancellation."""
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        """Check if cancelled."""
        return self._cancelled.is_set()

    def reset(self) -> None:
        """Reset for reuse."""
        self._cancelled.clear()
