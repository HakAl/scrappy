"""
Background task management for fire-and-forget async operations.

Extracted from core.py to improve modularity.
"""

import asyncio
import uuid
from datetime import datetime


class BackgroundTaskManager:
    """
    Manages async background tasks (fire-and-forget operations).

    Provides task tracking, error capture, and graceful shutdown support.

    Usage:
        manager = BackgroundTaskManager()

        # Submit fire-and-forget task
        task_id = manager.submit_background_task(some_async_operation())

        # Check status
        status = manager.get_task_status()

        # Wait for all to complete (e.g., during shutdown)
        await manager.wait_for_background_tasks(timeout=5.0)

        # Cancel specific task
        manager.cancel_task(task_id)
    """

    def __init__(self):
        """Initialize with empty task tracking."""
        self._tasks: dict[str, asyncio.Task] = {}
        self._errors: list[dict] = []

    def submit_background_task(self, coro) -> str:
        """
        Schedule a coroutine as a background task (fire-and-forget).

        The task runs without blocking the caller. Errors are captured
        but don't affect the main flow.

        Args:
            coro: Coroutine to execute in background

        Returns:
            str: Unique task ID for tracking/cancellation
        """
        task_id = str(uuid.uuid4())
        task = asyncio.create_task(coro)

        # Track by ID
        self._tasks[task_id] = task

        # Set up cleanup callback
        def on_done(t):
            # Remove from tracking
            self._tasks.pop(task_id, None)

            # Capture any errors
            try:
                exc = t.exception()
                if exc:
                    self._errors.append({
                        'timestamp': datetime.now().isoformat(),
                        'error': str(exc),
                        'type': type(exc).__name__
                    })
                    # Keep only last 50 errors
                    if len(self._errors) > 50:
                        self._errors = self._errors[-50:]
            except asyncio.CancelledError:
                pass  # Task was cancelled, not an error

        task.add_done_callback(on_done)

        return task_id

    def get_task_status(self) -> dict:
        """
        Get status of background task processing.

        Returns:
            Dict with pending task count and recent errors
        """
        return {
            'pending_tasks': len(self._tasks),
            'recent_errors': self._errors[-10:],
            'total_errors': len(self._errors)
        }

    async def wait_for_background_tasks(self, timeout: float = 5.0) -> dict:
        """
        Wait for all pending background tasks to complete.

        Useful for testing or graceful shutdown.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            Dict with completion status
        """
        if not self._tasks:
            return {
                'status': 'no_pending',
                'completed': 0,
                'errors': len(self._errors)
            }

        pending_count = len(self._tasks)
        tasks = list(self._tasks.values())

        try:
            # Wait for all tasks with timeout
            done, pending = await asyncio.wait(
                tasks,
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED
            )

            return {
                'status': 'completed' if not pending else 'timeout',
                'completed': len(done),
                'pending': len(pending),
                'errors': len(self._errors)
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'pending': pending_count
            }

    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending background task.

        Args:
            task_id: ID returned from submit_background_task

        Returns:
            True if task was found and cancelled, False otherwise
        """
        task = self._tasks.get(task_id)
        if task is None:
            return False

        if task.done():
            return False

        task.cancel()
        return True

    def clear_background_errors(self):
        """Clear the background error log."""
        self._errors.clear()
