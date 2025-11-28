"""
Tests for ManagedThread.

Tests lifecycle management, graceful shutdown, and thread safety.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import pytest

from src.infrastructure.threading import ManagedThread


class TestManagedThread:
    """Tests for ManagedThread basic functionality."""

    def test_start_and_join(self):
        """Thread can be started and joined."""
        result = []

        def worker(thread: ManagedThread) -> None:
            result.append("executed")

        managed = ManagedThread(target=worker, name="TestWorker")
        managed.start()
        managed.join(timeout=2.0)

        assert result == ["executed"]
        assert not managed.is_running()

    def test_is_running_before_and_after(self):
        """is_running reflects thread state correctly."""
        event = threading.Event()

        def worker(thread: ManagedThread) -> None:
            event.wait(timeout=5.0)

        managed = ManagedThread(target=worker, name="TestWorker")

        # Before start
        assert not managed.is_running()

        managed.start()
        time.sleep(0.05)  # Give thread time to start

        # While running
        assert managed.is_running()

        event.set()
        managed.join(timeout=2.0)

        # After completion
        assert not managed.is_running()

    def test_daemon_thread_safety_net(self):
        """ManagedThread creates daemon threads as safety net for process exit."""
        event = threading.Event()

        def worker(thread: ManagedThread) -> None:
            event.wait(timeout=5.0)

        managed = ManagedThread(target=worker, name="TestWorker")
        managed.start()

        # Access the internal thread to check daemon status
        # daemon=True ensures process can exit even if thread stuck in blocking I/O
        assert managed._thread is not None
        assert managed._thread.daemon is True

        event.set()
        managed.join(timeout=2.0)

    def test_start_idempotent(self):
        """Calling start multiple times only starts thread once."""
        call_count = []

        def worker(thread: ManagedThread) -> None:
            call_count.append(1)

        managed = ManagedThread(target=worker, name="TestWorker")
        managed.start()
        managed.start()  # Second call should be no-op
        managed.start()  # Third call should be no-op

        managed.join(timeout=2.0)

        assert len(call_count) == 1

    def test_worker_receives_thread_instance(self):
        """Worker function receives ManagedThread instance."""
        received_thread = []

        def worker(thread: ManagedThread) -> None:
            received_thread.append(thread)

        managed = ManagedThread(target=worker, name="TestWorker")
        managed.start()
        managed.join(timeout=2.0)

        assert len(received_thread) == 1
        assert received_thread[0] is managed

    def test_thread_name_set(self):
        """Thread is created with specified name."""

        def worker(thread: ManagedThread) -> None:
            pass

        managed = ManagedThread(target=worker, name="CustomName")
        managed.start()

        assert managed._thread is not None
        assert managed._thread.name == "CustomName"

        managed.join(timeout=2.0)


class TestManagedThreadShutdown:
    """Tests for ManagedThread graceful shutdown."""

    def test_graceful_shutdown(self):
        """Thread responds to shutdown request."""
        iterations = []

        def worker(thread: ManagedThread) -> None:
            while not thread.shutdown_requested:
                iterations.append(1)
                time.sleep(0.01)

        managed = ManagedThread(target=worker, name="TestWorker")
        managed.start()

        # Let it run for a bit
        time.sleep(0.05)

        # Request shutdown
        stopped = managed.stop(timeout=2.0)

        assert stopped is True
        assert not managed.is_running()
        assert len(iterations) > 0  # Did some work before stopping

    def test_stop_returns_true_if_not_started(self):
        """stop() returns True if thread was never started."""

        def worker(thread: ManagedThread) -> None:
            pass

        managed = ManagedThread(target=worker, name="TestWorker")

        # Never started
        result = managed.stop(timeout=1.0)

        assert result is True

    def test_stop_returns_false_on_timeout(self):
        """stop() returns False if thread doesn't stop within timeout."""
        # Worker that ignores shutdown request
        def worker(thread: ManagedThread) -> None:
            time.sleep(10.0)  # Long sleep, ignores shutdown

        managed = ManagedThread(target=worker, name="TestWorker")
        managed.start()

        # Very short timeout
        stopped = managed.stop(timeout=0.1)

        assert stopped is False
        assert managed.is_running()

        # Clean up: the thread is still running but will eventually finish
        # In real code, you might want to handle this more gracefully

    def test_shutdown_requested_initially_false(self):
        """shutdown_requested is False before stop() is called."""

        def worker(thread: ManagedThread) -> None:
            assert not thread.shutdown_requested
            thread.wait_for_shutdown(timeout=1.0)

        managed = ManagedThread(target=worker, name="TestWorker")
        managed.start()

        # Give worker time to check initial state
        time.sleep(0.05)

        managed.stop(timeout=2.0)

    def test_wait_for_shutdown_blocks_until_requested(self):
        """wait_for_shutdown blocks until shutdown is requested."""
        wait_result = []

        def worker(thread: ManagedThread) -> None:
            result = thread.wait_for_shutdown(timeout=5.0)
            wait_result.append(result)

        managed = ManagedThread(target=worker, name="TestWorker")
        managed.start()

        # Worker should be blocked
        time.sleep(0.05)
        assert managed.is_running()

        # Request shutdown
        managed.stop(timeout=2.0)

        assert wait_result == [True]

    def test_wait_for_shutdown_returns_false_on_timeout(self):
        """wait_for_shutdown returns False on timeout."""
        wait_result = []

        def worker(thread: ManagedThread) -> None:
            result = thread.wait_for_shutdown(timeout=0.1)
            wait_result.append(result)

        managed = ManagedThread(target=worker, name="TestWorker")
        managed.start()
        managed.join(timeout=2.0)

        assert wait_result == [False]


class TestManagedThreadResults:
    """Tests for ManagedThread result and error handling."""

    def test_get_result_returns_worker_return_value(self):
        """get_result returns value returned by worker."""

        def worker(thread: ManagedThread) -> str:
            return "success_result"

        managed = ManagedThread(target=worker, name="TestWorker")
        managed.start()
        managed.join(timeout=2.0)

        assert managed.get_result() == "success_result"
        assert managed.get_error() is None

    def test_get_result_returns_none_before_completion(self):
        """get_result returns None before thread completes."""
        event = threading.Event()

        def worker(thread: ManagedThread) -> str:
            event.wait(timeout=5.0)
            return "result"

        managed = ManagedThread(target=worker, name="TestWorker")
        managed.start()

        # Before completion
        assert managed.get_result() is None

        event.set()
        managed.join(timeout=2.0)

        # After completion
        assert managed.get_result() == "result"

    def test_get_error_captures_exception(self):
        """get_error returns exception raised by worker."""

        def worker(thread: ManagedThread) -> None:
            raise ValueError("test error")

        managed = ManagedThread(target=worker, name="TestWorker")
        managed.start()
        managed.join(timeout=2.0)

        error = managed.get_error()
        assert error is not None
        assert isinstance(error, ValueError)
        assert str(error) == "test error"

    def test_get_error_returns_none_on_success(self):
        """get_error returns None when worker succeeds."""

        def worker(thread: ManagedThread) -> str:
            return "success"

        managed = ManagedThread(target=worker, name="TestWorker")
        managed.start()
        managed.join(timeout=2.0)

        assert managed.get_error() is None


class TestManagedThreadConcurrency:
    """Stress tests for ManagedThread thread safety."""

    def test_multiple_threads_can_run_concurrently(self):
        """Multiple ManagedThreads can run at the same time."""
        results = []
        lock = threading.Lock()

        def worker(thread: ManagedThread, worker_id: int) -> None:
            time.sleep(0.01)
            with lock:
                results.append(worker_id)

        threads = []
        for i in range(10):
            # Use a closure to capture worker_id
            def make_worker(wid):
                return lambda t: worker(t, wid)

            managed = ManagedThread(target=make_worker(i), name=f"Worker{i}")
            threads.append(managed)
            managed.start()

        for t in threads:
            t.join(timeout=5.0)

        assert len(results) == 10
        assert set(results) == set(range(10))

    def test_concurrent_stop_calls(self):
        """Multiple concurrent stop() calls are safe."""
        stop_results = []

        def worker(thread: ManagedThread) -> None:
            thread.wait_for_shutdown(timeout=10.0)

        managed = ManagedThread(target=worker, name="TestWorker")
        managed.start()

        # Call stop from multiple threads concurrently
        def call_stop():
            result = managed.stop(timeout=5.0)
            stop_results.append(result)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(call_stop) for _ in range(5)]
            for f in futures:
                f.result()

        # At least one should succeed (all should, actually)
        assert any(stop_results)
        assert not managed.is_running()
