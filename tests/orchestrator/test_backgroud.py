import pytest
import asyncio
from scrappy.orchestrator.background import BackgroundTaskManager


@pytest.fixture
def manager():
    """Fixture to provide a fresh manager for each test."""
    return BackgroundTaskManager()


@pytest.mark.asyncio
class TestBackgroundTaskManager:

    async def test_submit_and_complete_success(self, manager):
        """Should submit a task and track it until completion."""

        # Define a simple task
        async def simple_task():
            await asyncio.sleep(0.01)
            return "done"

        # Submit
        task_id = manager.submit_background_task(simple_task())

        # Verify immediate state
        status_immediate = manager.get_task_status()
        assert status_immediate['pending_tasks'] == 1
        assert task_id is not None

        # Wait for completion
        result = await manager.wait_for_background_tasks(timeout=1.0)

        # Verify completion state
        assert result['status'] == 'completed'
        assert result['completed'] == 1
        assert manager.get_task_status()['pending_tasks'] == 0
        assert manager.get_task_status()['total_errors'] == 0

    async def test_captures_exceptions(self, manager):
        """Should catch exceptions in background tasks without crashing."""

        async def failing_task():
            await asyncio.sleep(0.01)
            raise ValueError("Intentional Failure")

        manager.submit_background_task(failing_task())

        # Wait for task to finish (and fail)
        await manager.wait_for_background_tasks()

        # Verify error logging
        status = manager.get_task_status()
        assert status['total_errors'] == 1

        error_entry = status['recent_errors'][0]
        assert error_entry['type'] == 'ValueError'
        assert "Intentional Failure" in error_entry['error']
        assert 'timestamp' in error_entry

    async def test_wait_timeout_behavior(self, manager):
        """Should report timeout if tasks take too long."""

        async def slow_task():
            await asyncio.sleep(0.5)

        manager.submit_background_task(slow_task())

        # Wait with a very short timeout
        result = await manager.wait_for_background_tasks(timeout=0.05)

        assert result['status'] == 'timeout'
        assert result['pending'] == 1

        # Allow the task to actually finish to prevent "Task was destroyed" warnings
        await asyncio.sleep(0.5)

    async def test_cancel_task(self, manager):
        """Should cancel specific task and NOT log it as an error."""

        async def forever_task():
            await asyncio.sleep(10)

        task_id = manager.submit_background_task(forever_task())

        # Verify it's running
        assert manager.get_task_status()['pending_tasks'] == 1

        # Cancel
        success = manager.cancel_task(task_id)
        assert success is True

        # Allow the callback to process the cancellation
        await asyncio.sleep(0.01)

        # Verify removed from pending
        assert manager.get_task_status()['pending_tasks'] == 0

        # Crucial: CancelledError should NOT be logged in _errors
        assert manager.get_task_status()['total_errors'] == 0

    async def test_cancel_nonexistent_or_done_task(self, manager):
        """Should handle invalid cancellation requests gracefully."""
        # 1. Cancel random ID
        assert manager.cancel_task("fake-id") is False

        # 2. Cancel already completed task
        async def quick_task(): pass

        task_id = manager.submit_background_task(quick_task())
        await manager.wait_for_background_tasks()

        assert manager.cancel_task(task_id) is False

    async def test_error_log_rotation(self, manager):
        """Should keep only the last 50 errors."""

        async def fail():
            raise Exception("boom")

        # Submit 60 failing tasks
        # We don't await them one by one; we fire them all then wait once
        for _ in range(60):
            manager.submit_background_task(fail())

        await manager.wait_for_background_tasks()

        status = manager.get_task_status()
        assert status['pending_tasks'] == 0
        # Should be capped at 50
        assert status['total_errors'] == 50
        assert len(manager._errors) == 50

    async def test_clear_errors(self, manager):
        """Should clear error history."""

        async def fail(): raise Exception("x")

        manager.submit_background_task(fail())
        await manager.wait_for_background_tasks()

        assert len(manager._errors) == 1
        manager.clear_background_errors()
        assert len(manager._errors) == 0

    async def test_wait_on_empty_manager(self, manager):
        """Should return immediately if no tasks pending."""
        result = await manager.wait_for_background_tasks()
        assert result['status'] == 'no_pending'

    async def test_multiple_concurrent_tasks(self, manager):
        """Should handle multiple mix of success and failure tasks."""

        async def success(idx):
            await asyncio.sleep(0.01)
            return idx

        async def fail(idx):
            await asyncio.sleep(0.01)
            raise ValueError(f"fail {idx}")

        # 5 success, 5 fail
        for i in range(5):
            manager.submit_background_task(success(i))
            manager.submit_background_task(fail(i))

        assert manager.get_task_status()['pending_tasks'] == 10

        await manager.wait_for_background_tasks()

        status = manager.get_task_status()
        assert status['pending_tasks'] == 0
        assert status['total_errors'] == 5