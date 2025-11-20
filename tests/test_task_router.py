"""
Tests for TaskRouter - task routing and execution strategies.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import time

from src.task_router.router import TaskRouter
from src.task_router.classifier import TaskClassifier, ClassifiedTask, TaskType
from src.task_router.strategies import ExecutionResult
from src.task_router.intent_clarifier import NullClarifier


class TestTaskRouter:
    """Tests for TaskRouter main class."""

    @pytest.fixture
    def router(self):
        """Create a TaskRouter without orchestrator."""
        return TaskRouter(
            orchestrator=None,
            auto_confirm_direct=True,
            verbose=False,
            intent_clarifier=NullClarifier()
        )

    @pytest.mark.unit
    def test_conversation_routing(self, router):
        """Test that simple greetings are routed correctly."""
        result = router.route("hello")
        assert result.success is True

    @pytest.mark.unit
    def test_direct_command_routing(self, router):
        """Test that shell commands are routed to direct executor."""
        # With NullClarifier injected, this won't trigger interactive prompts
        result = router.route("echo test")
        assert isinstance(result, ExecutionResult)
        # Echo should succeed with auto_confirm_direct=True
        assert result.success is True

    @pytest.mark.unit
    def test_metrics_tracking(self, router):
        """Test that router tracks metrics."""
        router.route("hello")
        router.route("thanks")

        metrics = router.get_metrics()
        assert metrics.total_tasks >= 2
        assert isinstance(metrics.success_rate, float)

    @pytest.mark.unit

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


class TestRouterWithMockOrchestrator:
    """Tests for router with mock orchestrator."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create a mock orchestrator with complete interface."""
        orch = Mock()
        orch.delegate.return_value = Mock(
            content="Mock response about machine learning",
            tokens_used=100
        )
        # Need providers attribute for LLM classification
        orch.providers = Mock()
        orch.providers.list_available.return_value = ['groq']
        return orch

        # The result should be a fallback since orchestrator isn't fully wired
        # but the point is it doesn't error out or trigger prompts


class TestTaskTypeRouting:
    """Tests for routing different task types."""

    @pytest.fixture
    def router(self):
        return TaskRouter(
            orchestrator=None,
            auto_confirm_direct=True,
            verbose=False,
            intent_clarifier=NullClarifier()
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
    def test_empty_input_handled(self, router):
        """Test that empty input is handled gracefully."""
        # With NullClarifier injected, this won't trigger interactive prompts
        result = router.route("")
        assert isinstance(result, ExecutionResult)
        # Empty input should fail validation
        assert result.success is False


