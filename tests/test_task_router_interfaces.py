"""
Tests for task router interface definitions and protocols.

These tests define the expected contracts for:
- ProviderAwareStrategy explicit interface
- Tool and ToolRegistry protocols
- ClassificationStrategy reasoning customization
- MetricsLike protocol

Following TDD: Tests written first to specify expected behavior.
"""

import pytest
from typing import Dict, List, Optional, Any, runtime_checkable
from unittest.mock import Mock, MagicMock
from abc import ABC

from src.task_router.strategies.base import (
    ExecutionStrategy,
    ProviderAwareStrategy,
    ExecutionResult,
    OrchestratorLike,
    ContextLike,
    ProviderRegistryLike,
    ToolLike,
    ToolRegistryLike,
)
from src.task_router.classification_strategy import (
    ClassificationStrategy,
    TaskType,
    StrategyResult,
    PatternBasedStrategy,
)
from src.task_router.classifier import ClassifiedTask
from src.task_router.metrics_collector import MetricsCollector, RouterMetrics, MetricsLike


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
# ProviderAwareStrategy Interface Tests
# =============================================================================

class TestProviderAwareStrategyInterface:
    """Tests for ProviderAwareStrategy explicit interface."""

    def test_provider_aware_strategy_is_abstract_base(self):
        """ProviderAwareStrategy should be an abstract base class."""
        # It inherits from ExecutionStrategy which is ABC
        assert issubclass(ProviderAwareStrategy, ExecutionStrategy)

    def test_provider_aware_strategy_requires_orchestrator(self, mock_orchestrator):
        """ProviderAwareStrategy must be initialized with orchestrator."""
        # Create a concrete implementation for testing
        class ConcreteStrategy(ProviderAwareStrategy):
            @property
            def name(self):
                return "test"

            def can_handle(self, task):
                return True

            def execute(self, task):
                return ExecutionResult(success=True, output="done")

        strategy = ConcreteStrategy(mock_orchestrator)
        assert strategy.orchestrator is mock_orchestrator

    def test_set_provider_method_exists(self, mock_orchestrator):
        """ProviderAwareStrategy must have set_provider method."""
        class ConcreteStrategy(ProviderAwareStrategy):
            @property
            def name(self):
                return "test"

            def can_handle(self, task):
                return True

            def execute(self, task):
                return ExecutionResult(success=True, output="done")

        strategy = ConcreteStrategy(mock_orchestrator)
        assert hasattr(strategy, 'set_provider')
        assert callable(strategy.set_provider)

    def test_set_provider_stores_values(self, mock_orchestrator):
        """set_provider should store provider and model names."""
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

        assert strategy._resolved_provider == "cerebras"
        assert strategy._resolved_model == "llama-3.3-70b"

    def test_resolve_and_validate_provider_priority(self, mock_orchestrator):
        """_resolve_and_validate_provider should follow priority order."""
        class ConcreteStrategy(ProviderAwareStrategy):
            @property
            def name(self):
                return "test"

            def can_handle(self, task):
                return True

            def execute(self, task):
                return ExecutionResult(success=True, output="done")

        strategy = ConcreteStrategy(mock_orchestrator)

        # Test priority: resolved > preferred > brain

        # No resolved, no preferred -> uses brain
        provider = strategy._resolve_and_validate_provider()
        assert provider == "test_provider"

        # With preferred -> uses preferred
        provider = strategy._resolve_and_validate_provider("groq")
        assert provider == "groq"

        # With resolved (highest priority)
        strategy.set_provider("cerebras")
        provider = strategy._resolve_and_validate_provider("groq")
        assert provider == "cerebras"

    def test_resolve_clears_after_use(self, mock_orchestrator):
        """_resolve_and_validate_provider should clear resolved values after use."""
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
        strategy._resolve_and_validate_provider()

        # Second call should fallback to brain since cleared
        provider = strategy._resolve_and_validate_provider()
        assert provider == "test_provider"
        assert strategy._resolved_provider is None
        assert strategy._resolved_model is None

    def test_invalid_provider_falls_back_to_brain(self, mock_orchestrator):
        """Invalid provider should fallback to brain."""
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


# =============================================================================
# Tool and ToolRegistry Protocol Tests
# =============================================================================

class TestToolProtocol:
    """Tests for Tool protocol definition."""

    def test_tool_protocol_exists(self):
        """Tool protocol should be importable from base or tools module."""
        # ToolLike is imported at module level, this verifies it exists
        assert ToolLike is not None

    def test_tool_protocol_is_runtime_checkable(self):
        """Tool protocol should be runtime checkable."""
        from typing import Protocol

        # Check it's a Protocol (runtime_checkable protocols have this)
        assert hasattr(ToolLike, '_is_runtime_protocol') or issubclass(ToolLike, Protocol)

    def test_tool_must_be_callable(self):
        """Tool must implement __call__(context, **kwargs) -> str."""
        class ValidTool:
            @property
            def name(self) -> str:
                return "valid_tool"

            def __call__(self, context: Any, **kwargs) -> str:
                return "result"

            def get_full_description(self) -> str:
                return "description"

        tool = ValidTool()
        assert isinstance(tool, ToolLike)

    def test_tool_must_have_get_full_description(self):
        """Tool must implement get_full_description() -> str."""
        # Missing get_full_description should not satisfy protocol
        class InvalidTool:
            @property
            def name(self) -> str:
                return "invalid"

            def __call__(self, context: Any, **kwargs) -> str:
                return "result"

        tool = InvalidTool()
        # This should NOT be a valid ToolLike
        assert not isinstance(tool, ToolLike)

    def test_tool_must_have_name_property(self):
        """Tool should have a name property."""
        class ToolWithName:
            @property
            def name(self) -> str:
                return "test_tool"

            def __call__(self, context: Any, **kwargs) -> str:
                return "result"

            def get_full_description(self) -> str:
                return "description"

        tool = ToolWithName()
        assert tool.name == "test_tool"
        assert isinstance(tool, ToolLike)


class TestToolRegistryProtocol:
    """Tests for ToolRegistry protocol definition."""

    def test_tool_registry_protocol_exists(self):
        """ToolRegistryLike protocol should be importable."""
        # ToolRegistryLike is imported at module level
        assert ToolRegistryLike is not None

    def test_tool_registry_must_have_get_method(self):
        """ToolRegistry must implement get(tool_name) -> Optional[Tool]."""
        class ValidRegistry:
            def get(self, tool_name: str) -> Optional[Any]:
                return None

            def register(self, tool: Any) -> None:
                pass

            def list_tools(self) -> List[str]:
                return []

        registry = ValidRegistry()
        assert isinstance(registry, ToolRegistryLike)

    def test_tool_registry_must_have_register_method(self):
        """ToolRegistry must implement register(tool) -> None."""
        class RegistryWithoutRegister:
            def get(self, tool_name: str) -> Optional[Any]:
                return None

            def list_tools(self) -> List[str]:
                return []

        registry = RegistryWithoutRegister()
        # Should NOT be a valid ToolRegistryLike
        assert not isinstance(registry, ToolRegistryLike)

    def test_tool_registry_must_have_list_tools_method(self):
        """ToolRegistry must implement list_tools() -> List[str]."""
        class ValidRegistry:
            def get(self, tool_name: str) -> Optional[Any]:
                return None

            def register(self, tool: Any) -> None:
                pass

            def list_tools(self) -> List[str]:
                return ["tool1", "tool2"]

        registry = ValidRegistry()
        assert isinstance(registry, ToolRegistryLike)
        assert registry.list_tools() == ["tool1", "tool2"]


# =============================================================================
# ClassificationStrategy Reasoning Tests
# =============================================================================

class TestClassificationStrategyReasoning:
    """Tests for ClassificationStrategy reasoning customization."""

    def test_generate_reasoning_is_overridable(self):
        """_generate_reasoning should be overridable by subclasses."""
        class CustomReasoningStrategy(PatternBasedStrategy):
            def _init_patterns(self):
                self.add_pattern(r"test", 1.0, "test_pattern")

            def task_type(self):
                return TaskType.RESEARCH

            def _generate_reasoning(self, patterns: List[str]) -> str:
                # Custom reasoning format
                if not patterns:
                    return "No patterns matched"
                return f"CUSTOM: Matched {len(patterns)} patterns: {', '.join(patterns)}"

        strategy = CustomReasoningStrategy()
        result = strategy.evaluate("test input")

        assert "CUSTOM:" in result.reasoning
        assert "test_pattern" in result.reasoning

    def test_default_reasoning_format(self):
        """Default _generate_reasoning provides task_type: patterns format."""
        class DefaultReasoningStrategy(PatternBasedStrategy):
            def _init_patterns(self):
                self.add_pattern(r"hello", 1.0, "greeting")

            def task_type(self):
                return TaskType.CONVERSATION

        strategy = DefaultReasoningStrategy()
        result = strategy.evaluate("hello world")

        assert "conversation:" in result.reasoning
        assert "greeting" in result.reasoning

    def test_empty_patterns_returns_empty_reasoning(self):
        """_generate_reasoning with no patterns returns empty string."""
        class NoMatchStrategy(PatternBasedStrategy):
            def _init_patterns(self):
                self.add_pattern(r"xyz123", 1.0, "rare_pattern")

            def task_type(self):
                return TaskType.RESEARCH

        strategy = NoMatchStrategy()
        result = strategy.evaluate("common input")

        assert result.reasoning == ""
        assert result.matched_patterns == []

    def test_reasoning_truncates_many_patterns(self):
        """Reasoning should handle many matched patterns gracefully."""
        class ManyPatternsStrategy(PatternBasedStrategy):
            def _init_patterns(self):
                for i in range(10):
                    self.add_pattern(r"test", 0.1, f"pattern_{i}")

            def task_type(self):
                return TaskType.RESEARCH

        strategy = ManyPatternsStrategy()
        result = strategy.evaluate("test input")

        # Default implementation shows first 3 patterns
        assert result.reasoning.count("pattern_") == 3

    def test_strategy_result_includes_extracted_command(self):
        """StrategyResult should include extracted_command when applicable."""
        class CommandStrategy(PatternBasedStrategy):
            def _init_patterns(self):
                self.add_pattern(r"^run ", 1.0, "run_command")

            def task_type(self):
                return TaskType.DIRECT_COMMAND

        strategy = CommandStrategy()
        result = strategy.evaluate("run tests")

        assert result.extracted_command == "run tests"


# =============================================================================
# MetricsLike Protocol Tests
# =============================================================================

class TestMetricsLikeProtocol:
    """Tests for MetricsLike protocol definition."""

    def test_metrics_like_protocol_exists(self):
        """MetricsLike protocol should be importable."""
        # MetricsLike is imported at module level
        assert MetricsLike is not None

    def test_metrics_must_have_required_fields(self):
        """MetricsLike must have total_tasks, success_rate, avg_execution_time."""
        class ValidMetrics:
            def __init__(self):
                self.total_tasks: int = 0
                self.success_rate: float = 1.0
                self.avg_execution_time: float = 0.0
                self.tasks_by_type: Dict[str, int] = {}
                self.total_tokens_used: int = 0

        metrics = ValidMetrics()
        assert isinstance(metrics, MetricsLike)

    def test_router_metrics_satisfies_protocol(self):
        """RouterMetrics dataclass should satisfy MetricsLike protocol."""
        metrics = RouterMetrics()
        assert isinstance(metrics, MetricsLike)

    def test_custom_metrics_implementation(self):
        """Custom metrics implementations should work with MetricsLike."""
        class CustomMetrics:
            def __init__(self):
                self.total_tasks = 0
                self.success_rate = 1.0
                self.avg_execution_time = 0.0
                self.tasks_by_type = {}
                self.total_tokens_used = 0
                # Additional custom fields
                self.custom_field = "custom"

        metrics = CustomMetrics()
        assert isinstance(metrics, MetricsLike)
        assert metrics.custom_field == "custom"


# =============================================================================
# MetricsCollector Behavior Tests
# =============================================================================

class TestMetricsCollectorBehavior:
    """Tests for MetricsCollector behavior with protocols."""

    def test_metrics_collector_initializes_with_defaults(self):
        """MetricsCollector should initialize with default metrics."""
        collector = MetricsCollector()
        metrics = collector.get_metrics()

        assert metrics.total_tasks == 0
        assert metrics.success_rate == 1.0
        assert metrics.avg_execution_time == 0.0
        assert metrics.total_tokens_used == 0
        assert metrics.tasks_by_type == {}

    def test_update_increments_total_tasks(self, sample_task):
        """update() should increment total_tasks."""
        collector = MetricsCollector()
        result = ExecutionResult(success=True, output="done", tokens_used=50)

        collector.update(sample_task, result)
        assert collector.get_metrics().total_tasks == 1

        collector.update(sample_task, result)
        assert collector.get_metrics().total_tasks == 2

    def test_update_tracks_by_task_type(self, sample_task):
        """update() should track tasks by type."""
        collector = MetricsCollector()
        result = ExecutionResult(success=True, output="done")

        # Research task
        collector.update(sample_task, result)

        # Conversation task
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

    def test_update_calculates_running_average_time(self, sample_task):
        """update() should calculate running average execution time."""
        collector = MetricsCollector()

        # First task: 1.0 seconds
        result1 = ExecutionResult(success=True, output="done", execution_time=1.0)
        collector.update(sample_task, result1)
        assert collector.get_metrics().avg_execution_time == 1.0

        # Second task: 3.0 seconds -> avg = 2.0
        result2 = ExecutionResult(success=True, output="done", execution_time=3.0)
        collector.update(sample_task, result2)
        assert collector.get_metrics().avg_execution_time == 2.0

    def test_update_accumulates_tokens(self, sample_task):
        """update() should accumulate total tokens used."""
        collector = MetricsCollector()

        result1 = ExecutionResult(success=True, output="done", tokens_used=100)
        collector.update(sample_task, result1)

        result2 = ExecutionResult(success=True, output="done", tokens_used=150)
        collector.update(sample_task, result2)

        assert collector.get_metrics().total_tokens_used == 250

    def test_update_calculates_success_rate(self, sample_task):
        """update() should calculate correct success rate."""
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

    def test_success_rate_starts_at_one(self, sample_task):
        """Success rate should start at 1.0 with no tasks."""
        collector = MetricsCollector()
        assert collector.get_metrics().success_rate == 1.0


# =============================================================================
# Integration Tests for Interface Contracts
# =============================================================================

class TestInterfaceIntegration:
    """Integration tests verifying interface contracts work together."""

    def test_strategy_with_real_orchestrator_interface(self, mock_orchestrator):
        """Strategies should work with any OrchestratorLike implementation."""
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
        assert result.success
        assert result.provider_used == "test_provider"
        assert mock_orchestrator.delegate.called

    def test_classification_to_metrics_flow(self):
        """Test complete flow from classification to metrics."""
        # Classify
        class TestClassifier(PatternBasedStrategy):
            def _init_patterns(self):
                self.add_pattern(r"test", 1.0, "test_pattern")

            def task_type(self):
                return TaskType.RESEARCH

        classifier = TestClassifier()
        result = classifier.evaluate("run test")

        # Create task from classification result
        task = ClassifiedTask(
            original_input="run test",
            task_type=classifier.task_type(),
            confidence=result.confidence,
            reasoning=result.reasoning
        )

        # Execute and track
        exec_result = ExecutionResult(
            success=True,
            output="tests passed",
            execution_time=0.5,
            tokens_used=50
        )

        collector = MetricsCollector()
        collector.update(task, exec_result)

        metrics = collector.get_metrics()
        assert metrics.total_tasks == 1
        assert metrics.tasks_by_type["research"] == 1
        assert metrics.total_tokens_used == 50


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestInterfaceEdgeCases:
    """Edge case tests for interface implementations."""

    def test_provider_resolution_with_exception(self, mock_orchestrator):
        """Provider resolution should handle exceptions gracefully."""
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

    def test_empty_strategy_evaluation(self):
        """Strategy with no patterns should return zero confidence."""
        class EmptyStrategy(PatternBasedStrategy):
            def _init_patterns(self):
                pass  # No patterns

            def task_type(self):
                return TaskType.CONVERSATION

        strategy = EmptyStrategy()
        result = strategy.evaluate("any input")

        assert result.score == 0.0
        assert result.confidence == 0.0
        assert result.matched_patterns == []

    def test_metrics_with_zero_execution_time(self, sample_task):
        """Metrics should handle zero execution time."""
        collector = MetricsCollector()
        result = ExecutionResult(success=True, output="done", execution_time=0.0)

        collector.update(sample_task, result)
        assert collector.get_metrics().avg_execution_time == 0.0

    def test_none_provider_handling(self, mock_orchestrator):
        """set_provider with None should be handled correctly."""
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
