"""
Tests for task router interface definitions and protocols.

Verifies that protocol implementations actually WORK correctly,
not just that they implement required methods.

Following Phase 5 principles:
- Test behavior, not structure
- Prove features work
- Cover edge cases
- Minimal mocking (only external dependencies)
"""

import pytest
from typing import Dict, List, Optional, Any
from unittest.mock import Mock

from src.task_router.strategies.base import (
    ExecutionStrategy,
    ProviderAwareStrategy,
    ExecutionResult,
)
from src.task_router.classification_strategy import (
    TaskType,
    PatternBasedStrategy,
)
from src.task_router.classifier import ClassifiedTask
from src.task_router.metrics_collector import MetricsCollector, RouterMetrics, 


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_orchestrator():
    """Create a mock orchestrator for testing."""
    orch = Mock()
    orch.brain = "test_provider"

    # Provider registry
    providers = Mock()
    providers.list_available.return_value = ["test_provider", "cerebras", "groq"]
    orch.providers = providers

    # Context
    context = Mock()
    context.is_explored.return_value = False
    context.get_summary.return_value = ""
    context.file_index = {}
    orch.context = context

    # Delegate method
    response = Mock()
    response.content = "test response"
    response.tokens_used = 100
    orch.delegate.return_value = response

    return orch


@pytest.fixture
def sample_task():
    """Create a sample classified task."""
    return ClassifiedTask(
        original_input="test task",
        task_type=TaskType.RESEARCH,
        confidence=0.8,
        reasoning="test reasoning"
    )


# =============================================================================
# ProviderAwareStrategy Behavior Tests
# =============================================================================

class TestProviderResolutionBehavior:
    """Tests that provider resolution actually works correctly."""

    def test_resolves_provider_with_correct_priority_order(self, mock_orchestrator):
        """Provider resolution follows priority: resolved > preferred > brain."""
        class ConcreteStrategy(ProviderAwareStrategy):
            @property
            def name(self):
                return "test"

            def can_handle(self, task):
                return True

            def execute(self, task):
                return ExecutionResult(success=True, output="done")

        strategy = ConcreteStrategy(mock_orchestrator)

        # No resolved, no preferred -> uses brain
        provider = strategy._resolve_and_validate_provider()
        assert provider == "test_provider"

        # With preferred -> uses preferred
        provider = strategy._resolve_and_validate_provider("groq")
        assert provider == "groq"

        # With resolved (highest priority) -> overrides preferred
        strategy.set_provider("cerebras")
        provider = strategy._resolve_and_validate_provider("groq")
        assert provider == "cerebras"

    def test_stores_and_uses_provider_from_set_provider(self, mock_orchestrator):
        """set_provider stores values that are used in resolution."""
        class ConcreteStrategy(ProviderAwareStrategy):
            @property
            def name(self):
                return "test"

            def can_handle(self, task):
                return True

            def execute(self, task):
                return ExecutionResult(success=True, output="done")

        strategy = ConcreteStrategy(mock_orchestrator)
        strategy.set_provider("cerebras", "llama-3.3-70b")

        # Verify provider is used
        provider = strategy._resolve_and_validate_provider()
        assert provider == "cerebras"

    def test_clears_resolved_provider_after_first_use(self, mock_orchestrator):
        """Resolved provider is cleared after use to prevent reuse."""
        class ConcreteStrategy(ProviderAwareStrategy):
            @property
            def name(self):
                return "test"

            def can_handle(self, task):
                return True

            def execute(self, task):
                return ExecutionResult(success=True, output="done")

        strategy = ConcreteStrategy(mock_orchestrator)
        strategy.set_provider("cerebras", "model")

        # First call uses and clears
        first_call = strategy._resolve_and_validate_provider()
        assert first_call == "cerebras"

        # Second call should fallback to brain since cleared
        second_call = strategy._resolve_and_validate_provider()
        assert second_call == "test_provider"

    def test_fallback_to_brain_when_provider_invalid(self, mock_orchestrator):
        """Invalid provider falls back to brain provider."""
        class ConcreteStrategy(ProviderAwareStrategy):
            @property
            def name(self):
                return "test"

            def can_handle(self, task):
                return True

            def execute(self, task):
                return ExecutionResult(success=True, output="done")

        strategy = ConcreteStrategy(mock_orchestrator)
        strategy.set_provider("invalid_provider")

        provider = strategy._resolve_and_validate_provider()
        assert provider == "test_provider"  # Falls back to brain

    def test_handles_provider_validation_exception(self, mock_orchestrator):
        """Provider resolution handles exceptions gracefully during validation."""
        # Make list_available raise exception
        mock_orchestrator.providers.list_available.side_effect = Exception("Network error")

        class TestStrategy(ProviderAwareStrategy):
            @property
            def name(self):
                return "test"

            def can_handle(self, task):
                return True

            def execute(self, task):
                return ExecutionResult(success=True, output="done")

        strategy = TestStrategy(mock_orchestrator)
        strategy.set_provider("cerebras")

        # Should fallback to brain on exception
        provider = strategy._resolve_and_validate_provider()
        assert provider == "test_provider"

    def test_handles_none_provider_gracefully(self, mock_orchestrator):
        """set_provider with None falls back to brain."""
        class TestStrategy(ProviderAwareStrategy):
            @property
            def name(self):
                return "test"

            def can_handle(self, task):
                return True

            def execute(self, task):
                return ExecutionResult(success=True, output="done")

        strategy = TestStrategy(mock_orchestrator)
        strategy.set_provider(None, None)

        # Should fallback to brain
        provider = strategy._resolve_and_validate_provider()
        assert provider == "test_provider"


class TestProviderAwareStrategyIntegration:
    """Integration tests for provider-aware strategies."""

    def test_strategy_uses_orchestrator_for_execution(self, mock_orchestrator):
        """Strategy uses orchestrator to delegate work to provider."""
        class TestStrategy(ProviderAwareStrategy):
            @property
            def name(self):
                return "test"

            def can_handle(self, task):
                return task.task_type == TaskType.RESEARCH

            def execute(self, task):
                provider = self._resolve_and_validate_provider()
                response = self.orchestrator.delegate(
                    provider,
                    task.original_input,
                    max_tokens=1000
                )
                return ExecutionResult(
                    success=True,
                    output=response.content,
                    tokens_used=response.tokens_used,
                    provider_used=provider
                )

        strategy = TestStrategy(mock_orchestrator)
        task = ClassifiedTask(
            original_input="explain code",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="research task"
        )

        result = strategy.execute(task)

        # Verify execution worked
        assert result.success
        assert result.output == "test response"
        assert result.tokens_used == 100
        assert result.provider_used == "test_provider"
        assert mock_orchestrator.delegate.called


# =============================================================================
# ClassificationStrategy Behavior Tests
# =============================================================================

class TestClassificationReasoningBehavior:
    """Tests that classification reasoning generation works correctly."""

    def test_generates_custom_reasoning_when_overridden(self):
        """Subclasses can override reasoning generation for custom formats."""
        class CustomReasoningStrategy(PatternBasedStrategy):
            def task_type(self):
                return TaskType.RESEARCH

        strategy = CustomReasoningStrategy()
        result = strategy.evaluate("test input")

        assert "CUSTOM:" in result.reasoning
        assert "test_pattern" in result.reasoning

    def test_uses_default_reasoning_format(self):
        """Default reasoning format includes task_type and patterns."""
        class DefaultReasoningStrategy(PatternBasedStrategy):
            def task_type(self):
                return TaskType.CONVERSATION

        strategy = DefaultReasoningStrategy()
        result = strategy.evaluate("hello world")

        assert "conversation:" in result.reasoning
        assert "greeting" in result.reasoning

    def test_returns_empty_reasoning_when_no_patterns_match(self):
        """When no patterns match, reasoning is empty."""
        class NoMatchStrategy(PatternBasedStrategy):
            def task_type(self):
                return TaskType.RESEARCH

        strategy = NoMatchStrategy()
        result = strategy.evaluate("common input")

        assert result.reasoning == ""
        assert result.matched_patterns == []

    def test_handles_many_matched_patterns(self):
        """Reasoning handles many matched patterns gracefully."""
        class ManyPatternsStrategy(PatternBasedStrategy):
            def task_type(self):
                return TaskType.RESEARCH

        strategy = ManyPatternsStrategy()
        result = strategy.evaluate("test input")

        # Default implementation shows first 3 patterns
        assert result.reasoning.count("pattern_") == 3

    def test_includes_extracted_command_in_result(self):
        """StrategyResult includes extracted_command for direct commands."""
        class CommandStrategy(PatternBasedStrategy):
            def task_type(self):
                return TaskType.DIRECT_COMMAND

        strategy = CommandStrategy()
        result = strategy.evaluate("run tests")

        assert result.extracted_command == "run tests"

    def test_empty_strategy_returns_zero_confidence(self):
        """Strategy with no patterns returns zero confidence."""
        class EmptyStrategy(PatternBasedStrategy):
  # No patterns
            def task_type(self):
                return TaskType.CONVERSATION

        strategy = EmptyStrategy()
        result = strategy.evaluate("any input")

        assert result.score == 0.0
        assert result.confidence == 0.0
        assert result.matched_patterns == []


# =============================================================================
# MetricsCollector Behavior Tests
# =============================================================================

class TestMetricsCollectionBehavior:
    """Tests that metrics collection tracks data correctly."""

    def test_tracks_total_task_count(self, sample_task):
        """Collector increments total tasks on each update."""
        collector = MetricsCollector()
        result = ExecutionResult(success=True, output="done", tokens_used=50)

        # Initially zero
        assert collector.get_metrics().total_tasks == 0

        # After first update
        collector.update(sample_task, result)
        assert collector.get_metrics().total_tasks == 1

        # After second update
        collector.update(sample_task, result)
        assert collector.get_metrics().total_tasks == 2

    def test_tracks_tasks_by_type(self, sample_task):
        """Collector tracks task counts by task type."""
        collector = MetricsCollector()
        result = ExecutionResult(success=True, output="done")

        # Add research task
        collector.update(sample_task, result)

        # Add conversation task
        conv_task = ClassifiedTask(
            original_input="hello",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="greeting"
        )
        collector.update(conv_task, result)

        metrics = collector.get_metrics()
        assert metrics.tasks_by_type["research"] == 1
        assert metrics.tasks_by_type["conversation"] == 1

    def test_calculates_running_average_execution_time(self, sample_task):
        """Collector calculates running average of execution times."""
        collector = MetricsCollector()

        # First task: 1.0 seconds
        result1 = ExecutionResult(success=True, output="done", execution_time=1.0)
        collector.update(sample_task, result1)
        assert collector.get_metrics().avg_execution_time == 1.0

        # Second task: 3.0 seconds -> avg = 2.0
        result2 = ExecutionResult(success=True, output="done", execution_time=3.0)
        collector.update(sample_task, result2)
        assert collector.get_metrics().avg_execution_time == 2.0

    def test_accumulates_total_tokens(self, sample_task):
        """Collector accumulates token usage across tasks."""
        collector = MetricsCollector()

        result1 = ExecutionResult(success=True, output="done", tokens_used=100)
        collector.update(sample_task, result1)

        result2 = ExecutionResult(success=True, output="done", tokens_used=150)
        collector.update(sample_task, result2)

        assert collector.get_metrics().total_tokens_used == 250

    def test_calculates_success_rate_correctly(self, sample_task):
        """Collector calculates correct success rate from successes and failures."""
        collector = MetricsCollector()

        # Two successes
        success = ExecutionResult(success=True, output="done")
        collector.update(sample_task, success)
        collector.update(sample_task, success)
        assert collector.get_metrics().success_rate == 1.0

        # One failure -> 2/3 success rate
        failure = ExecutionResult(success=False, output="", error="failed")
        collector.update(sample_task, failure)
        assert abs(collector.get_metrics().success_rate - 0.6667) < 0.001

    def test_success_rate_starts_at_one_with_no_tasks(self):
        """Success rate is 1.0 when no tasks have been executed."""
        collector = MetricsCollector()
        assert collector.get_metrics().success_rate == 1.0
        assert collector.get_metrics().total_tasks == 0


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestMetricsEdgeCases:
    """Edge case tests for metrics collection."""

    def test_handles_zero_execution_time(self, sample_task):
        """Metrics handles zero execution time without error."""
        collector = MetricsCollector()
        result = ExecutionResult(success=True, output="done", execution_time=0.0)

        collector.update(sample_task, result)
        assert collector.get_metrics().avg_execution_time == 0.0

    def test_handles_missing_token_count(self, sample_task):
        """Metrics handles tasks with no token count."""
        collector = MetricsCollector()
        result = ExecutionResult(success=True, output="done", tokens_used=0)

        collector.update(sample_task, result)
        assert collector.get_metrics().total_tokens_used == 0

    def test_handles_all_failures(self, sample_task):
        """Success rate is 0.0 when all tasks fail."""
        collector = MetricsCollector()
        failure = ExecutionResult(success=False, output="", error="failed")

        collector.update(sample_task, failure)
        collector.update(sample_task, failure)

        assert collector.get_metrics().success_rate == 0.0
        assert collector.get_metrics().total_tasks == 2


# =============================================================================
# Integration Tests
# =============================================================================

class TestClassificationToMetricsFlow:
    """Integration tests for complete classification -> execution -> metrics flow."""

    def test_complete_flow_from_classification_to_metrics(self):
        """Test complete flow: classify -> execute -> track metrics."""
        # 1. Classify
        class TestClassifier(PatternBasedStrategy):
            def task_type(self):
                return TaskType.RESEARCH

        classifier = TestClassifier()
        classification_result = classifier.evaluate("run test")

        # 2. Create task from classification
        task = ClassifiedTask(
            original_input="run test",
            task_type=classifier.task_type(),
            confidence=classification_result.confidence,
            reasoning=classification_result.reasoning
        )

        # 3. Execute and track
        exec_result = ExecutionResult(
            success=True,
            output="tests passed",
            execution_time=0.5,
            tokens_used=50
        )

        # 4. Collect metrics
        collector = MetricsCollector()
        collector.update(task, exec_result)

        # Verify complete flow worked
        metrics = collector.get_metrics()
        assert metrics.total_tasks == 1
        assert metrics.tasks_by_type["research"] == 1
        assert metrics.total_tokens_used == 50
        assert metrics.avg_execution_time == 0.5
        assert metrics.success_rate == 1.0

    def test_handles_multiple_task_types_in_flow(self):
        """Integration test with multiple different task types."""
        collector = MetricsCollector()

        # Research task
        research_task = ClassifiedTask(
            original_input="explain code",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="research"
        )
        collector.update(
            research_task,
            ExecutionResult(success=True, output="explanation", tokens_used=100)
        )

        # Conversation task
        conv_task = ClassifiedTask(
            original_input="hello",
            task_type=TaskType.CONVERSATION,
            confidence=0.95,
            reasoning="greeting"
        )
        collector.update(
            conv_task,
            ExecutionResult(success=True, output="Hi!", tokens_used=20)
        )

        # Code generation task
        code_task = ClassifiedTask(
            original_input="write function",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.85,
            reasoning="code_gen"
        )
        collector.update(
            code_task,
            ExecutionResult(success=True, output="def foo(): pass", tokens_used=150)
        )

        metrics = collector.get_metrics()
        assert metrics.total_tasks == 3
        assert metrics.tasks_by_type["research"] == 1
        assert metrics.tasks_by_type["conversation"] == 1
        assert metrics.tasks_by_type["code_generation"] == 1
        assert metrics.total_tokens_used == 270
        assert metrics.success_rate == 1.0
