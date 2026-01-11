"""Tests for CancellationToken."""

import threading
import time

from scrappy.infrastructure.threading import CancellationToken


class TestCancellationToken:
    """Tests for CancellationToken behavior."""

    def test_initial_state_not_cancelled(self) -> None:
        """Token starts in uncancelled state."""
        token = CancellationToken()
        assert not token.is_cancelled
        assert not token.is_force_cancelled
        assert token.cancel_count == 0

    def test_single_cancel_sets_cancelled(self) -> None:
        """Single cancel() sets is_cancelled but not is_force_cancelled."""
        token = CancellationToken()
        token.cancel()
        assert token.is_cancelled
        assert not token.is_force_cancelled
        assert token.cancel_count == 1

    def test_double_cancel_sets_force_cancelled(self) -> None:
        """Second cancel() sets is_force_cancelled."""
        token = CancellationToken()
        token.cancel()
        token.cancel()
        assert token.is_cancelled
        assert token.is_force_cancelled
        assert token.cancel_count == 2

    def test_multiple_cancels_increment_count(self) -> None:
        """Cancel count increments with each call."""
        token = CancellationToken()
        for i in range(5):
            token.cancel()
            assert token.cancel_count == i + 1
        assert token.is_force_cancelled

    def test_reset_clears_all_state(self) -> None:
        """Reset clears cancelled state and count."""
        token = CancellationToken()
        token.cancel()
        token.cancel()
        assert token.is_force_cancelled

        token.reset()
        assert not token.is_cancelled
        assert not token.is_force_cancelled
        assert token.cancel_count == 0

    def test_wait_returns_immediately_when_cancelled(self) -> None:
        """Wait returns True immediately if already cancelled."""
        token = CancellationToken()
        token.cancel()
        result = token.wait(timeout=0.1)
        assert result is True

    def test_wait_blocks_until_cancelled(self) -> None:
        """Wait blocks until cancel() is called from another thread."""
        token = CancellationToken()

        def canceller() -> None:
            time.sleep(0.05)
            token.cancel()

        thread = threading.Thread(target=canceller)
        start = time.time()
        thread.start()

        result = token.wait(timeout=1.0)
        elapsed = time.time() - start

        thread.join()
        assert result is True
        assert 0.04 < elapsed < 0.5  # Should wake up after ~50ms

    def test_wait_returns_false_on_timeout(self) -> None:
        """Wait returns False if timeout expires without cancel."""
        token = CancellationToken()
        start = time.time()
        result = token.wait(timeout=0.05)
        elapsed = time.time() - start

        assert result is False
        assert elapsed >= 0.05
        assert not token.is_cancelled

    def test_thread_safety(self) -> None:
        """Multiple threads can safely cancel concurrently."""
        token = CancellationToken()
        num_threads = 10

        def cancel_thread() -> None:
            token.cancel()

        threads = [threading.Thread(target=cancel_thread) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert token.is_cancelled
        assert token.is_force_cancelled
        assert token.cancel_count == num_threads
