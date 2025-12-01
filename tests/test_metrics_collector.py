"""
Tests for MetricsCollector - metrics tracking and calculation.

Following TDD: These tests define expected behavior BEFORE implementation.
"""
import pytest
from scrappy.task_router.classifier import ClassifiedTask, TaskType
from scrappy.task_router.strategies import ExecutionResult


class TestMetricsCollectorInitialization:
    """Test MetricsCollector initialization and default state."""

    @pytest.mark.unit
    def test_collector_initializes_with_zero_tasks(self):
        """Test that new collector starts with zero tasks."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        metrics = collector.get_metrics()

        assert metrics.total_tasks == 0

    @pytest.mark.unit
    def test_collector_initializes_with_empty_type_tracking(self):
        """Test that new collector has empty task type dictionary."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        metrics = collector.get_metrics()

        assert metrics.tasks_by_type == {}

    @pytest.mark.unit
    def test_collector_initializes_with_zero_avg_time(self):
        """Test that average execution time starts at zero."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        metrics = collector.get_metrics()

        assert metrics.avg_execution_time == 0.0

    @pytest.mark.unit
    def test_collector_initializes_with_zero_tokens(self):
        """Test that total tokens starts at zero."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        metrics = collector.get_metrics()

        assert metrics.total_tokens_used == 0

    @pytest.mark.unit
    def test_collector_initializes_with_perfect_success_rate(self):
        """Test that success rate starts at 100% (1.0)."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        metrics = collector.get_metrics()

        assert metrics.success_rate == 1.0


class TestMetricsCollectorSingleTask:
    """Test MetricsCollector with single task updates."""

    @pytest.mark.unit
    def test_update_increments_total_tasks(self):
        """Test that updating metrics increments total task count."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        task = ClassifiedTask(
            original_input="test task",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="test classification"
        )
        result = ExecutionResult(
            success=True,
            output="done",
            execution_time=0.5
        )

        collector.update(task, result)
        metrics = collector.get_metrics()

        assert metrics.total_tasks == 1

    @pytest.mark.unit
    def test_update_tracks_task_by_type(self):
        """Test that tasks are tracked by their type."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        task = ClassifiedTask(
            original_input="test task",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="test classification"
        )
        result = ExecutionResult(
            success=True,
            output="done",
            execution_time=0.5
        )

        collector.update(task, result)
        metrics = collector.get_metrics()

        assert "research" in metrics.tasks_by_type
        assert metrics.tasks_by_type["research"] == 1

    @pytest.mark.unit
    def test_update_sets_avg_execution_time_for_first_task(self):
        """Test that first task sets the average execution time."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        task = ClassifiedTask(
            original_input="test task",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="test classification"
        )
        result = ExecutionResult(
            success=True,
            output="done",
            execution_time=1.5
        )

        collector.update(task, result)
        metrics = collector.get_metrics()

        assert metrics.avg_execution_time == 1.5

    @pytest.mark.unit
    def test_update_tracks_tokens_used(self):
        """Test that tokens are accumulated correctly."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        task = ClassifiedTask(
            original_input="test task",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="test classification"
        )
        result = ExecutionResult(
            success=True,
            output="done",
            execution_time=0.5,
            tokens_used=100
        )

        collector.update(task, result)
        metrics = collector.get_metrics()

        assert metrics.total_tokens_used == 100

    @pytest.mark.unit
    def test_successful_task_maintains_perfect_success_rate(self):
        """Test that single successful task keeps 100% success rate."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        task = ClassifiedTask(
            original_input="test task",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="test classification"
        )
        result = ExecutionResult(
            success=True,
            output="done",
            execution_time=0.5
        )

        collector.update(task, result)
        metrics = collector.get_metrics()

        assert metrics.success_rate == 1.0

    @pytest.mark.unit
    def test_failed_task_reduces_success_rate_to_zero(self):
        """Test that single failed task results in 0% success rate."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        task = ClassifiedTask(
            original_input="test task",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="test classification"
        )
        result = ExecutionResult(
            success=False,
            output="",
            error="failed",
            execution_time=0.5
        )

        collector.update(task, result)
        metrics = collector.get_metrics()

        assert metrics.success_rate == 0.0


class TestMetricsCollectorMultipleTasks:
    """Test MetricsCollector with multiple task updates."""

    @pytest.mark.unit
    def test_multiple_updates_increment_total_tasks(self):
        """Test that multiple updates correctly increment total count."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        for i in range(5):
            task = ClassifiedTask(
                original_input=f"task {i}",
                task_type=TaskType.CONVERSATION,
                confidence=0.9,
                reasoning="test classification"
            )
            result = ExecutionResult(
                success=True,
                output="done",
                execution_time=0.5
            )
            collector.update(task, result)

        metrics = collector.get_metrics()
        assert metrics.total_tasks == 5

    @pytest.mark.unit
    def test_tracks_multiple_task_types(self):
        """Test that different task types are tracked separately."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        # Add 2 conversation tasks
        for i in range(2):
            task = ClassifiedTask(
                original_input="hello",
                task_type=TaskType.CONVERSATION,
                confidence=0.9,
                reasoning="test classification"
            )
            result = ExecutionResult(success=True, output="hi", execution_time=0.1)
            collector.update(task, result)

        # Add 3 research tasks
        for i in range(3):
            task = ClassifiedTask(
                original_input="explain X",
                task_type=TaskType.RESEARCH,
                confidence=0.9,
                reasoning="test classification"
            )
            result = ExecutionResult(success=True, output="info", execution_time=0.2)
            collector.update(task, result)

        metrics = collector.get_metrics()
        assert metrics.tasks_by_type["conversation"] == 2
        assert metrics.tasks_by_type["research"] == 3

    @pytest.mark.unit
    def test_calculates_average_execution_time_correctly(self):
        """Test that average execution time is calculated correctly over multiple tasks."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        times = [1.0, 2.0, 3.0]
        for exec_time in times:
            task = ClassifiedTask(
                original_input="task",
                task_type=TaskType.CONVERSATION,
                confidence=0.9,
                reasoning="test classification"
            )
            result = ExecutionResult(
                success=True,
                output="done",
                execution_time=exec_time
            )
            collector.update(task, result)

        metrics = collector.get_metrics()
        expected_avg = sum(times) / len(times)
        assert abs(metrics.avg_execution_time - expected_avg) < 0.01

    @pytest.mark.unit
    def test_accumulates_tokens_across_tasks(self):
        """Test that tokens are accumulated across multiple tasks."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        token_counts = [100, 200, 150]
        for tokens in token_counts:
            task = ClassifiedTask(
                original_input="task",
                task_type=TaskType.CONVERSATION,
                confidence=0.9,
                reasoning="test classification"
            )
            result = ExecutionResult(
                success=True,
                output="done",
                execution_time=0.5,
                tokens_used=tokens
            )
            collector.update(task, result)

        metrics = collector.get_metrics()
        assert metrics.total_tokens_used == sum(token_counts)

    @pytest.mark.unit
    def test_calculates_success_rate_with_mixed_results(self):
        """Test success rate calculation with mix of successful and failed tasks."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        # 3 successful tasks
        for i in range(3):
            task = ClassifiedTask(
                original_input="task",
                task_type=TaskType.CONVERSATION,
                confidence=0.9,
                reasoning="test classification"
            )
            result = ExecutionResult(success=True, output="done", execution_time=0.5)
            collector.update(task, result)

        # 1 failed task
        task = ClassifiedTask(
            original_input="task",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="test classification"
        )
        result = ExecutionResult(success=False, output="", error="failed", execution_time=0.5)
        collector.update(task, result)

        metrics = collector.get_metrics()
        assert metrics.success_rate == 0.75  # 3 out of 4 succeeded

    @pytest.mark.unit
    def test_success_rate_with_all_failures(self):
        """Test success rate calculation when all tasks fail."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        for i in range(5):
            task = ClassifiedTask(
                original_input="task",
                task_type=TaskType.CONVERSATION,
                confidence=0.9,
                reasoning="test classification"
            )
            result = ExecutionResult(success=False, output="", error="failed", execution_time=0.5)
            collector.update(task, result)

        metrics = collector.get_metrics()
        assert metrics.success_rate == 0.0


class TestMetricsCollectorEdgeCases:
    """Test MetricsCollector edge cases and boundary conditions."""

    @pytest.mark.unit
    def test_handles_zero_execution_time(self):
        """Test that collector handles zero execution time gracefully."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        task = ClassifiedTask(
            original_input="instant task",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="test classification"
        )
        result = ExecutionResult(
            success=True,
            output="done",
            execution_time=0.0
        )

        collector.update(task, result)
        metrics = collector.get_metrics()

        assert metrics.avg_execution_time == 0.0

    @pytest.mark.unit
    def test_handles_zero_tokens(self):
        """Test that collector handles zero tokens gracefully."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        task = ClassifiedTask(
            original_input="task",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="test classification"
        )
        result = ExecutionResult(
            success=True,
            output="done",
            execution_time=0.5,
            tokens_used=0
        )

        collector.update(task, result)
        metrics = collector.get_metrics()

        assert metrics.total_tokens_used == 0

    @pytest.mark.unit
    def test_increments_existing_task_type_count(self):
        """Test that updating same task type increments existing count."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        # First conversation task
        task = ClassifiedTask(
            original_input="hello",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="test classification"
        )
        result = ExecutionResult(success=True, output="hi", execution_time=0.1)
        collector.update(task, result)

        # Second conversation task
        task = ClassifiedTask(
            original_input="thanks",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="test classification"
        )
        result = ExecutionResult(success=True, output="welcome", execution_time=0.1)
        collector.update(task, result)

        metrics = collector.get_metrics()
        assert metrics.tasks_by_type["conversation"] == 2

    @pytest.mark.unit
    def test_running_average_updates_correctly(self):
        """Test that running average calculation is numerically stable."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        # First task: avg should be 1.0
        task = ClassifiedTask(
            original_input="task",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="test classification"
        )
        result = ExecutionResult(success=True, output="done", execution_time=1.0)
        collector.update(task, result)

        metrics = collector.get_metrics()
        assert metrics.avg_execution_time == 1.0

        # Second task: avg should be (1.0 + 2.0) / 2 = 1.5
        result = ExecutionResult(success=True, output="done", execution_time=2.0)
        collector.update(task, result)

        metrics = collector.get_metrics()
        assert abs(metrics.avg_execution_time - 1.5) < 0.01

        # Third task: avg should be (1.0 + 2.0 + 3.0) / 3 = 2.0
        result = ExecutionResult(success=True, output="done", execution_time=3.0)
        collector.update(task, result)

        metrics = collector.get_metrics()
        assert abs(metrics.avg_execution_time - 2.0) < 0.01


class TestMetricsCollectorReturnedData:
    """Test that MetricsCollector returns correct data structure."""

    @pytest.mark.unit

    @pytest.mark.unit

    @pytest.mark.unit
    def test_metrics_reflects_current_state(self):
        """Test that get_metrics returns current state, not a snapshot."""
        from scrappy.task_router.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        # Get metrics before any tasks
        metrics1 = collector.get_metrics()
        assert metrics1.total_tasks == 0

        # Add a task
        task = ClassifiedTask(
            original_input="task",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="test classification"
        )
        result = ExecutionResult(success=True, output="done", execution_time=0.5)
        collector.update(task, result)

        # Get metrics again
        metrics2 = collector.get_metrics()
        assert metrics2.total_tasks == 1
