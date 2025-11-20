"""
Tests for BackgroundTaskManager.

Tests the async background task management functionality extracted from core.py.
"""

import pytest
import asyncio
from datetime import datetime


class TestBackgroundTaskManagerProtocolCompliance:
    """Test that BackgroundTaskManager implements BackgroundTaskManagerProtocol."""


    def test_has_all_protocol_methods(self):
        """BackgroundTaskManager has all methods defined in protocol."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        # Verify all protocol methods exist
        assert hasattr(manager, 'submit_background_task')
        assert callable(manager.submit_background_task)

        assert hasattr(manager, 'get_task_status')
        assert callable(manager.get_task_status)

        assert hasattr(manager, 'wait_for_background_tasks')
        assert callable(manager.wait_for_background_tasks)

        assert hasattr(manager, 'cancel_task')
        assert callable(manager.cancel_task)

        assert hasattr(manager, 'clear_background_errors')
        assert callable(manager.clear_background_errors)


class TestBackgroundTaskManagerInit:
    """Test BackgroundTaskManager initialization."""

    def test_initializes_with_empty_state(self):
        """Manager starts with no pending tasks or errors."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        status = manager.get_task_status()
        assert status['pending_tasks'] == 0
        assert status['recent_errors'] == []
        assert status['total_errors'] == 0

    def test_initializes_multiple_instances_independently(self):
        """Multiple managers maintain separate state."""
        from src.orchestrator.background import BackgroundTaskManager

        manager1 = BackgroundTaskManager()
        manager2 = BackgroundTaskManager()

        # They should be independent
        assert manager1.get_task_status()['pending_tasks'] == 0
        assert manager2.get_task_status()['pending_tasks'] == 0


class TestSubmitBackgroundTask:
    """Test submitting background tasks."""

    async def test_submit_task_tracks_pending(self):
        """Submitted task appears in pending count."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        # Create a task that won't complete immediately
        event = asyncio.Event()

        async def wait_for_signal():
            await event.wait()

        manager.submit_background_task(wait_for_signal())

        # Task should be pending
        status = manager.get_task_status()
        assert status['pending_tasks'] == 1

        # Signal completion
        event.set()
        await asyncio.sleep(0.01)  # Let task complete

        # Task should be gone
        status = manager.get_task_status()
        assert status['pending_tasks'] == 0

    async def test_submit_multiple_tasks(self):
        """Can submit and track multiple concurrent tasks."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        event = asyncio.Event()

        async def wait_for_signal():
            await event.wait()

        # Submit multiple tasks
        manager.submit_background_task(wait_for_signal())
        manager.submit_background_task(wait_for_signal())
        manager.submit_background_task(wait_for_signal())

        status = manager.get_task_status()
        assert status['pending_tasks'] == 3

        # Complete all
        event.set()
        await asyncio.sleep(0.01)

        status = manager.get_task_status()
        assert status['pending_tasks'] == 0

    async def test_completed_task_removed_from_tracking(self):
        """Tasks are automatically removed when they complete."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        async def quick_task():
            return "done"

        manager.submit_background_task(quick_task())

        # Give it time to complete
        await asyncio.sleep(0.01)

        status = manager.get_task_status()
        assert status['pending_tasks'] == 0

    async def test_task_error_captured(self):
        """Errors in tasks are captured without crashing."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        async def failing_task():
            raise ValueError("Test error")

        manager.submit_background_task(failing_task())

        # Give it time to fail
        await asyncio.sleep(0.01)

        status = manager.get_task_status()
        assert status['pending_tasks'] == 0
        assert status['total_errors'] == 1
        assert len(status['recent_errors']) == 1

        error = status['recent_errors'][0]
        assert "Test error" in error['error']
        assert error['type'] == "ValueError"
        assert 'timestamp' in error

    async def test_multiple_errors_captured(self):
        """Multiple task errors are all captured."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        async def failing_task(msg):
            raise RuntimeError(msg)

        manager.submit_background_task(failing_task("error1"))
        manager.submit_background_task(failing_task("error2"))
        manager.submit_background_task(failing_task("error3"))

        await asyncio.sleep(0.01)

        status = manager.get_task_status()
        assert status['total_errors'] == 3

    async def test_error_log_limited_to_50(self):
        """Error log is capped at 50 entries."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        async def failing_task(i):
            raise ValueError(f"error {i}")

        # Submit 60 failing tasks
        for i in range(60):
            manager.submit_background_task(failing_task(i))

        await asyncio.sleep(0.1)  # Wait for all to complete

        status = manager.get_task_status()
        assert status['total_errors'] == 50  # Capped at 50


class TestWaitForBackgroundTasks:
    """Test waiting for background tasks to complete."""

    async def test_wait_with_no_tasks(self):
        """Waiting with no tasks returns immediately."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        result = await manager.wait_for_background_tasks()

        assert result['status'] == 'no_pending'
        assert result['completed'] == 0
        assert result['errors'] == 0

    async def test_wait_completes_all_tasks(self):
        """Wait returns when all tasks complete."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        results = []

        async def task(value):
            await asyncio.sleep(0.01)
            results.append(value)

        manager.submit_background_task(task(1))
        manager.submit_background_task(task(2))
        manager.submit_background_task(task(3))

        result = await manager.wait_for_background_tasks(timeout=1.0)

        assert result['status'] == 'completed'
        assert result['completed'] == 3
        assert len(results) == 3

    async def test_wait_timeout(self):
        """Wait times out if tasks take too long."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        async def slow_task():
            await asyncio.sleep(10)  # Very slow

        manager.submit_background_task(slow_task())

        result = await manager.wait_for_background_tasks(timeout=0.05)

        assert result['status'] == 'timeout'
        assert result['pending'] == 1
        assert result['completed'] == 0

    async def test_wait_with_mixed_success_and_failure(self):
        """Wait handles mix of successful and failed tasks."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        async def success_task():
            return "ok"

        async def failing_task():
            raise ValueError("fail")

        manager.submit_background_task(success_task())
        manager.submit_background_task(failing_task())
        manager.submit_background_task(success_task())

        result = await manager.wait_for_background_tasks(timeout=1.0)

        assert result['status'] == 'completed'
        assert result['completed'] == 3
        assert result['errors'] == 1


class TestCancelTask:
    """Test cancelling background tasks."""

    async def test_cancel_pending_task(self):
        """Can cancel a pending task."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        event = asyncio.Event()

        async def wait_forever():
            await event.wait()

        task_id = manager.submit_background_task(wait_forever())

        assert manager.get_task_status()['pending_tasks'] == 1

        # Cancel it
        cancelled = manager.cancel_task(task_id)
        assert cancelled is True

        await asyncio.sleep(0.01)
        assert manager.get_task_status()['pending_tasks'] == 0

    async def test_cancel_nonexistent_task(self):
        """Cancelling nonexistent task returns False."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        cancelled = manager.cancel_task("nonexistent-id")
        assert cancelled is False

    async def test_cancel_already_completed_task(self):
        """Cancelling completed task returns False."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        async def quick_task():
            return "done"

        task_id = manager.submit_background_task(quick_task())

        await asyncio.sleep(0.01)  # Let it complete

        cancelled = manager.cancel_task(task_id)
        assert cancelled is False


class TestGetTaskStatus:
    """Test getting task status."""

    async def test_status_shows_pending_count(self):
        """Status accurately reflects pending task count."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()
        event = asyncio.Event()

        async def wait_task():
            await event.wait()

        assert manager.get_task_status()['pending_tasks'] == 0

        manager.submit_background_task(wait_task())
        assert manager.get_task_status()['pending_tasks'] == 1

        manager.submit_background_task(wait_task())
        assert manager.get_task_status()['pending_tasks'] == 2

        event.set()
        await asyncio.sleep(0.01)
        assert manager.get_task_status()['pending_tasks'] == 0

    async def test_status_shows_recent_errors_limited(self):
        """Status shows only last 10 errors in recent_errors."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        async def failing_task(i):
            raise ValueError(f"error {i}")

        # Submit 15 failing tasks
        for i in range(15):
            manager.submit_background_task(failing_task(i))

        await asyncio.sleep(0.1)

        status = manager.get_task_status()
        assert len(status['recent_errors']) == 10  # Only last 10
        assert status['total_errors'] == 15  # But total is 15


class TestClearBackgroundErrors:
    """Test clearing background errors."""

    async def test_clear_removes_all_errors(self):
        """Clear removes all captured errors."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        async def failing_task():
            raise ValueError("fail")

        manager.submit_background_task(failing_task())
        manager.submit_background_task(failing_task())

        await asyncio.sleep(0.01)

        assert manager.get_task_status()['total_errors'] == 2

        manager.clear_background_errors()

        status = manager.get_task_status()
        assert status['total_errors'] == 0
        assert status['recent_errors'] == []

    def test_clear_on_empty_succeeds(self):
        """Clear works even with no errors."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        # Should not raise
        manager.clear_background_errors()

        assert manager.get_task_status()['total_errors'] == 0


class TestTaskIdTracking:
    """Test task ID generation and tracking."""

    async def test_submit_returns_task_id(self):
        """Submit returns a task ID."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        async def task():
            return "done"

        task_id = manager.submit_background_task(task())

        assert task_id is not None
        assert isinstance(task_id, str)
        assert len(task_id) > 0

    async def test_task_ids_are_unique(self):
        """Each submitted task gets a unique ID."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()
        event = asyncio.Event()

        async def wait_task():
            await event.wait()

        ids = set()
        for _ in range(10):
            task_id = manager.submit_background_task(wait_task())
            ids.add(task_id)

        assert len(ids) == 10  # All unique

        event.set()
        await asyncio.sleep(0.01)


class TestIntegrationScenarios:
    """Integration tests for realistic usage scenarios."""

    async def test_fire_and_forget_logging(self):
        """Can use for fire-and-forget operations like logging."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()
        logged = []

        async def log_event(event):
            await asyncio.sleep(0.001)  # Simulate async I/O
            logged.append(event)

        # Fire-and-forget logging
        manager.submit_background_task(log_event("user_action"))
        manager.submit_background_task(log_event("api_call"))
        manager.submit_background_task(log_event("response"))

        # Main code continues immediately
        assert manager.get_task_status()['pending_tasks'] <= 3

        # Wait for completion
        await manager.wait_for_background_tasks()

        assert len(logged) == 3
        assert set(logged) == {"user_action", "api_call", "response"}

    async def test_graceful_shutdown(self):
        """Can gracefully shutdown with pending tasks."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()

        async def cleanup_task():
            await asyncio.sleep(0.01)
            return "cleaned"

        manager.submit_background_task(cleanup_task())
        manager.submit_background_task(cleanup_task())

        # Graceful shutdown
        result = await manager.wait_for_background_tasks(timeout=1.0)

        assert result['status'] == 'completed'
        assert manager.get_task_status()['pending_tasks'] == 0

    async def test_error_resilience(self):
        """Manager remains functional after task errors."""
        from src.orchestrator.background import BackgroundTaskManager

        manager = BackgroundTaskManager()
        results = []

        async def good_task():
            results.append("good")

        async def bad_task():
            raise ValueError("bad")

        # Mix of good and bad
        manager.submit_background_task(good_task())
        manager.submit_background_task(bad_task())
        manager.submit_background_task(good_task())
        manager.submit_background_task(bad_task())
        manager.submit_background_task(good_task())

        await manager.wait_for_background_tasks()

        # Good tasks completed
        assert len(results) == 3

        # Errors captured
        assert manager.get_task_status()['total_errors'] == 2

        # Manager still functional
        manager.submit_background_task(good_task())
        await manager.wait_for_background_tasks()
        assert len(results) == 4
