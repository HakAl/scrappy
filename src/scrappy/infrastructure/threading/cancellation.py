"""
Cancellation token for cooperative cancellation of long-running operations.

Provides thread-safe cancellation signaling with support for both
graceful cancellation and force cancellation (after multiple requests).
"""

import threading
from typing import Optional


class CancellationToken:
    """
    Thread-safe cancellation token with force-cancel support.

    Tracks the number of cancel requests to distinguish between:
    - First cancel: Graceful cancellation (stop at next checkpoint)
    - Second+ cancel: Force cancellation (stop immediately)

    Example:
        token = CancellationToken()

        # Worker checks for cancellation
        for item in items:
            if token.is_cancelled:
                if token.is_force_cancelled:
                    # User pressed escape twice - stop NOW
                    break
                # Graceful cancel - finish current item then stop
                cleanup()
                break
            process(item)

        # UI thread requests cancellation
        token.cancel()  # First press
        token.cancel()  # Second press - triggers force cancel
    """

    # Number of cancel calls before force cancellation is triggered
    FORCE_CANCEL_THRESHOLD = 2

    def __init__(self) -> None:
        """Initialize the cancellation token in uncancelled state."""
        self._cancelled = threading.Event()
        self._force_cancelled = threading.Event()
        self._cancel_count = 0
        self._lock = threading.Lock()

    @property
    def is_cancelled(self) -> bool:
        """
        Check if cancellation has been requested.

        Returns:
            True if cancel() has been called at least once
        """
        return self._cancelled.is_set()

    @property
    def is_force_cancelled(self) -> bool:
        """
        Check if force cancellation has been requested.

        Force cancellation is triggered after FORCE_CANCEL_THRESHOLD
        calls to cancel(), indicating the user wants immediate termination.

        Returns:
            True if cancel() has been called multiple times
        """
        return self._force_cancelled.is_set()

    @property
    def cancel_count(self) -> int:
        """
        Get the number of times cancel() has been called.

        Returns:
            Number of cancel requests received
        """
        with self._lock:
            return self._cancel_count

    def cancel(self) -> None:
        """
        Request cancellation.

        First call sets is_cancelled to True.
        Second+ call sets is_force_cancelled to True.
        """
        with self._lock:
            self._cancel_count += 1
            self._cancelled.set()
            if self._cancel_count >= self.FORCE_CANCEL_THRESHOLD:
                self._force_cancelled.set()

    def reset(self) -> None:
        """
        Reset the token to uncancelled state.

        Use this to reuse the token for a new operation.
        """
        with self._lock:
            self._cancelled.clear()
            self._force_cancelled.clear()
            self._cancel_count = 0

    def wait(self, timeout: Optional[float] = None) -> bool:
        """
        Block until cancelled or timeout.

        Args:
            timeout: Maximum seconds to wait (None = wait forever)

        Returns:
            True if cancelled, False if timeout reached
        """
        return self._cancelled.wait(timeout=timeout)
