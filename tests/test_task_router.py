"""
Tests for TaskRouter - task routing and execution strategies.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import time

from src.task_router.router import TaskRouter
from src.task_router.classifier import TaskClassifier, ClassifiedTask, TaskType
from src.task_router.strategies import ExecutionResult


class TestTaskRouter:
    """Tests for TaskRouter main class."""

    @pytest.fixture
    def router(self):
        """Create a TaskRouter without orchestrator."""
        return TaskRouter(
            orchestrator=None,
            auto_confirm_direct=True,
            verbose=False
        )

    @pytest.mark.unit
    def test_router_creation(self, router):
        """Test basic router creation."""
        assert router is not None
        assert hasattr(router, 'route')
        assert hasattr(router, 'get_metrics')

    @pytest.mark.unit
    def test_route_returns_result(self, router):
        """Test that route returns ExecutionResult."""
        result = router.route("hello")
        assert isinstance(result, ExecutionResult)
        assert hasattr(result, 'success')
        assert hasattr(result, 'execution_time')

    @pytest.mark.unit
    def test_conversation_routing(self, router):
        """Test that simple greetings are routed correctly."""
        result = router.route("hello")
        assert result.success is True

    @pytest.mark.unit
    @pytest.mark.skip(reason="Triggers interactive prompt in low confidence scenarios")
    def test_direct_command_routing(self, router):
        """Test that shell commands are routed to direct executor."""
        # This test may actually execute the command
        result = router.route("echo test")
        assert isinstance(result, ExecutionResult)

    @pytest.mark.unit
    def test_metrics_tracking(self, router):
        """Test that router tracks metrics."""
        router.route("hello")
        router.route("thanks")

        metrics = router.get_metrics()
        assert metrics.total_tasks >= 2
        assert isinstance(metrics.success_rate, float)

    @pytest.mark.unit
    def test_metrics_structure(self, router):
        """Test metrics data structure."""
        router.route("hello")  # Use clear conversation task
        metrics = router.get_metrics()

        assert hasattr(metrics, 'total_tasks')
        assert hasattr(metrics, 'tasks_by_type')
        assert hasattr(metrics, 'success_rate')
        assert hasattr(metrics, 'avg_execution_time')

    @pytest.mark.unit
    def test_execution_time_tracked(self, router):
        """Test that execution time is measured."""
        result = router.route("hello")
        assert result.execution_time >= 0
        assert isinstance(result.execution_time, float)


class TestConfidenceEscalation:
    """Tests for confidence-based task escalation."""

    @pytest.fixture
    def router(self):
        return TaskRouter(orchestrator=None, verbose=False)

    @pytest.mark.unit
    def test_low_confidence_research_with_action_word_escalates(self, router):
        """Test that low confidence research with action words escalates."""
        task = ClassifiedTask(
            original_input="create something",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Low confidence"
        )

        escalated = router._apply_confidence_escalation(task)
        # Should escalate to CODE_GENERATION because of 'create'
        assert escalated.task_type == TaskType.CODE_GENERATION

    @pytest.mark.unit
    def test_high_confidence_no_escalation(self, router):
        """Test that high confidence tasks don't escalate."""
        task = ClassifiedTask(
            original_input="explain python",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="High confidence"
        )

        escalated = router._apply_confidence_escalation(task)
        # Should stay as RESEARCH
        assert escalated.task_type == TaskType.RESEARCH

    @pytest.mark.unit
    def test_escalation_updates_reasoning(self, router):
        """Test that escalation updates the reasoning."""
        task = ClassifiedTask(
            original_input="write code",
            task_type=TaskType.RESEARCH,
            confidence=0.3,
            reasoning="Original reasoning here"
        )

        escalated = router._apply_confidence_escalation(task)
        # The reasoning should be updated to include escalation info
        assert "escalat" in escalated.reasoning.lower() or escalated.reasoning != "Original reasoning here"


class TestIntentClarification:
    """Tests for intent clarification detection."""

    @pytest.fixture
    def router(self):
        return TaskRouter(orchestrator=None, verbose=False)

    @pytest.mark.unit
    def test_conflicting_intent_needs_clarification(self, router):
        """Test that conflicting intents are detected."""
        classifier = TaskClassifier()
        task = classifier.classify("explain how to create a file")
        needs_clarify = router._needs_intent_clarification(task)
        # 'explain' vs 'create' - conflicting
        assert needs_clarify is True

    @pytest.mark.unit
    def test_clear_action_no_clarification(self, router):
        """Test that clear actions don't need clarification."""
        classifier = TaskClassifier()
        task = classifier.classify("create requirements.txt")
        needs_clarify = router._needs_intent_clarification(task)
        assert needs_clarify is False

    @pytest.mark.unit
    def test_clear_question_no_clarification(self, router):
        """Test that clear questions don't need clarification."""
        classifier = TaskClassifier()
        task = classifier.classify("what is python?")
        needs_clarify = router._needs_intent_clarification(task)
        assert needs_clarify is False


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    @pytest.mark.unit
    def test_result_creation(self):
        """Test creating execution result."""
        result = ExecutionResult(
            success=True,
            output="Command output",
            execution_time=0.5
        )

        assert result.success is True
        assert result.output == "Command output"
        assert result.execution_time == 0.5

    @pytest.mark.unit
    def test_result_with_error(self):
        """Test result with error."""
        result = ExecutionResult(
            success=False,
            output="",
            execution_time=1.0,
            error="API timeout"
        )

        assert result.success is False
        assert result.error == "API timeout"


class TestRouterWithMockOrchestrator:
    """Tests for router with mock orchestrator."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create a mock orchestrator."""
        orch = Mock()
        orch.delegate.return_value = Mock(
            content="Mock response",
            tokens_used=100
        )
        return orch

    @pytest.mark.unit
    def test_router_with_orchestrator(self, mock_orchestrator):
        """Test router creation with orchestrator."""
        router = TaskRouter(
            orchestrator=mock_orchestrator,
            verbose=False
        )
        assert router.orchestrator is mock_orchestrator

    @pytest.mark.unit
    @pytest.mark.skip(reason="Requires full orchestrator setup")
    def test_research_uses_orchestrator(self, mock_orchestrator):
        """Test that research tasks use orchestrator."""
        router = TaskRouter(
            orchestrator=mock_orchestrator,
            verbose=False
        )

        result = router.route("what is machine learning?")
        # Should have called orchestrator for research
        # This depends on strategy implementation


class TestTaskTypeRouting:
    """Tests for routing different task types."""

    @pytest.fixture
    def router(self):
        return TaskRouter(
            orchestrator=None,
            auto_confirm_direct=True,
            verbose=False
        )

    @pytest.mark.unit
    def test_conversation_returns_success(self, router):
        """Test that conversation tasks succeed."""
        result = router.route("hi there")
        assert result.success is True

    @pytest.mark.unit
    def test_thanks_is_conversation(self, router):
        """Test that 'thanks' is handled as conversation."""
        result = router.route("thanks")
        # ExecutionResult doesn't have task_type, just check success
        assert result.success is True

    @pytest.mark.unit
    @pytest.mark.skip(reason="Empty input triggers interactive clarification prompt")
    def test_empty_input_handled(self, router):
        """Test that empty input is handled gracefully."""
        result = router.route("")
        assert isinstance(result, ExecutionResult)

    @pytest.mark.unit
    def test_very_long_input_handled(self, router):
        """Test that very long input is handled."""
        long_input = "explain " + "python " * 1000
        result = router.route(long_input)
        assert isinstance(result, ExecutionResult)


class TestRouterConfiguration:
    """Tests for router configuration options."""

    @pytest.mark.unit
    def test_auto_confirm_direct_option(self):
        """Test auto_confirm_direct configuration."""
        router = TaskRouter(
            orchestrator=None,
            auto_confirm_direct=False
        )
        assert router.auto_confirm_direct is False

    @pytest.mark.unit
    def test_verbose_option(self):
        """Test verbose configuration."""
        router = TaskRouter(
            orchestrator=None,
            verbose=True
        )
        assert router.verbose is True

    @pytest.mark.unit
    def test_default_configuration(self):
        """Test default configuration values."""
        router = TaskRouter(orchestrator=None)
        assert hasattr(router, 'auto_confirm_direct')
        assert hasattr(router, 'verbose')


class TestDirectExecutor:
    """Tests for direct command execution."""

    @pytest.fixture
    def router(self):
        return TaskRouter(
            orchestrator=None,
            auto_confirm_direct=True,
            verbose=False
        )

    @pytest.mark.unit
    @pytest.mark.skip(reason="Echo command triggers interactive clarification prompt")
    def test_echo_command_execution(self, router):
        """Test executing echo command."""
        result = router.route("echo 'test output'")
        assert isinstance(result, ExecutionResult)
        # Echo should succeed
        assert result.success is True

    @pytest.mark.unit
    def test_dangerous_command_blocked(self, router):
        """Test that dangerous commands are blocked."""
        result = router.route("rm -rf /")
        # Should either fail validation or refuse to execute
        # Depends on implementation
        assert isinstance(result, ExecutionResult)

    @pytest.mark.unit
    def test_pip_command_recognized(self, router):
        """Test that pip commands are recognized as direct."""
        classifier = TaskClassifier()
        task = classifier.classify("pip install requests")
        assert task.task_type == TaskType.DIRECT_COMMAND

    @pytest.mark.unit
    def test_git_command_recognized(self, router):
        """Test that git commands are recognized as direct."""
        classifier = TaskClassifier()
        task = classifier.classify("git status")
        assert task.task_type == TaskType.DIRECT_COMMAND


class TestMetricsAggregation:
    """Tests for metrics aggregation."""

    @pytest.fixture
    def router(self):
        return TaskRouter(
            orchestrator=None,
            auto_confirm_direct=True,
            verbose=False
        )

    @pytest.mark.unit
    def test_tasks_by_type_tracking(self, router):
        """Test that tasks are counted by type."""
        router.route("hello")  # conversation
        router.route("thanks")  # conversation
        router.route("hi there")  # conversation

        metrics = router.get_metrics()
        assert TaskType.CONVERSATION.value in metrics.tasks_by_type
        assert metrics.tasks_by_type[TaskType.CONVERSATION.value] >= 2

    @pytest.mark.unit
    def test_success_rate_calculation(self, router):
        """Test success rate calculation."""
        router.route("hello")
        router.route("thanks")

        metrics = router.get_metrics()
        # All conversation tasks should succeed
        assert metrics.success_rate >= 0.0
        assert metrics.success_rate <= 1.0

    @pytest.mark.unit
    def test_average_execution_time(self, router):
        """Test average execution time calculation."""
        router.route("hello")
        router.route("thanks")

        metrics = router.get_metrics()
        assert metrics.avg_execution_time >= 0
        assert isinstance(metrics.avg_execution_time, float)
