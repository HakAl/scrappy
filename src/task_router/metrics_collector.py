"""
Metrics collection and tracking for task routing.

Provides RouterMetrics dataclass and MetricsCollector for tracking
task execution statistics including success rates, execution times, and token usage.
"""

from dataclasses import dataclass, field
from typing import Dict, Protocol, runtime_checkable

from .classifier import ClassifiedTask
from .strategies import ExecutionResult


@runtime_checkable
class MetricsLike(Protocol):
    """Protocol for metrics tracking data.

    Defines the required fields for any metrics implementation.
    Allows custom metrics classes to be used interchangeably.
    """

    total_tasks: int
    """Total number of tasks executed."""

    success_rate: float
    """Ratio of successful tasks (0.0 to 1.0)."""

    avg_execution_time: float
    """Average execution time in seconds."""

    tasks_by_type: Dict[str, int]
    """Count of tasks by task type."""

    total_tokens_used: int
    """Total tokens consumed across all tasks."""


@dataclass
class RouterMetrics:
    """Metrics tracking for task routing."""
    total_tasks: int = 0
    tasks_by_type: Dict[str, int] = field(default_factory=dict)
    avg_execution_time: float = 0.0
    total_tokens_used: int = 0
    success_rate: float = 1.0


class MetricsCollector:
    """
    Collects and tracks metrics for task routing operations.

    Tracks:
    - Total tasks executed
    - Tasks categorized by type
    - Average execution time (running average)
    - Total tokens used
    - Success rate (ratio of successful to total tasks)
    """

    def __init__(self):
        """Initialize metrics collector with default metrics."""
        self._metrics = RouterMetrics()

    def update(self, task: ClassifiedTask, result: ExecutionResult) -> None:
        """
        Update metrics after task execution.

        Args:
            task: The classified task that was executed
            result: The execution result containing success status, timing, and token info
        """
        self._metrics.total_tasks += 1

        # Track by type
        type_key = task.task_type.value
        if type_key not in self._metrics.tasks_by_type:
            self._metrics.tasks_by_type[type_key] = 0
        self._metrics.tasks_by_type[type_key] += 1

        # Update average execution time (running average formula)
        n = self._metrics.total_tasks
        old_avg = self._metrics.avg_execution_time
        self._metrics.avg_execution_time = old_avg + (result.execution_time - old_avg) / n

        # Track tokens
        self._metrics.total_tokens_used += result.tokens_used

        # Update success rate
        if not result.success:
            success_count = self._metrics.success_rate * (n - 1)
            self._metrics.success_rate = success_count / n

    def get_metrics(self) -> RouterMetrics:
        """
        Get current routing metrics.

        Returns:
            RouterMetrics instance with current statistics
        """
        return self._metrics
