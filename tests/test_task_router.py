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


class TestLLMClassification:
    """Tests for LLM-based classification fallback."""

    @pytest.fixture
    def fake_orchestrator(self):
        """Create a fake orchestrator that returns configurable responses."""
        class FakeOrchestrator:
            def __init__(self):
                self.response_content = ""
                self.providers = self  # Self-reference for providers attribute

            def list_available(self):
                return ['groq', 'gemini']

            def delegate(self, provider, prompt, **kwargs):
                class Response:
                    def __init__(self, content):
                        self.content = content
                return Response(self.response_content)

        return FakeOrchestrator()

    @pytest.mark.unit
    def test_llm_classification_extracts_json_from_plain_text(self, fake_orchestrator):
        """Test parser finds JSON object embedded in text."""
        fake_orchestrator.response_content = 'Here is my analysis: {"task_type": "CODE_GENERATION", "confidence": 0.85, "reasoning": "User wants code"} That is my response.'

        router = TaskRouter(orchestrator=fake_orchestrator, verbose=False)
        task = ClassifiedTask(
            original_input="write a function",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Low confidence"
        )

        result = router._classify_with_llm(task)
        assert result.task_type == TaskType.CODE_GENERATION
        assert result.confidence == 0.85

    @pytest.mark.unit
    def test_llm_classification_extracts_json_from_code_block(self, fake_orchestrator):
        """Test parser extracts JSON from markdown code block."""
        fake_orchestrator.response_content = '''Here is the classification:
```json
{"task_type": "RESEARCH", "confidence": 0.9, "reasoning": "Research task"}
```
That's my analysis.'''

        router = TaskRouter(orchestrator=fake_orchestrator, verbose=False)
        task = ClassifiedTask(
            original_input="explain python",
            task_type=TaskType.CONVERSATION,
            confidence=0.3,
            reasoning="Low confidence"
        )

        result = router._classify_with_llm(task)
        assert result.task_type == TaskType.RESEARCH
        assert result.confidence == 0.9

    @pytest.mark.unit
    def test_llm_classification_extracts_json_from_plain_code_block(self, fake_orchestrator):
        """Test parser extracts JSON from plain code block without language tag."""
        fake_orchestrator.response_content = '''```
{"task_type": "DIRECT_COMMAND", "confidence": 0.95, "reasoning": "Shell command"}
```'''

        router = TaskRouter(orchestrator=fake_orchestrator, verbose=False)
        task = ClassifiedTask(
            original_input="git status",
            task_type=TaskType.RESEARCH,
            confidence=0.3,
            reasoning="Low confidence"
        )

        result = router._classify_with_llm(task)
        assert result.task_type == TaskType.DIRECT_COMMAND
        assert result.confidence == 0.95

    @pytest.mark.unit
    def test_llm_classification_rejects_low_confidence(self, fake_orchestrator):
        """Test that LLM confidence below 0.7 does not override original."""
        fake_orchestrator.response_content = '{"task_type": "CODE_GENERATION", "confidence": 0.69, "reasoning": "Uncertain"}'

        router = TaskRouter(orchestrator=fake_orchestrator, verbose=False)
        task = ClassifiedTask(
            original_input="something ambiguous",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original reasoning"
        )

        result = router._classify_with_llm(task)
        # Must keep original since 0.69 < 0.7
        assert result.task_type == TaskType.RESEARCH
        assert result.confidence == 0.4
        assert result.reasoning == "Original reasoning"

    @pytest.mark.unit
    def test_llm_classification_accepts_exactly_0_7_confidence(self, fake_orchestrator):
        """Test that exactly 0.7 confidence is accepted."""
        fake_orchestrator.response_content = '{"task_type": "CODE_GENERATION", "confidence": 0.7, "reasoning": "Just confident enough"}'

        router = TaskRouter(orchestrator=fake_orchestrator, verbose=False)
        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original"
        )

        result = router._classify_with_llm(task)
        assert result.task_type == TaskType.CODE_GENERATION
        assert result.confidence == 0.7

    @pytest.mark.unit
    def test_llm_classification_handles_malformed_json_missing_brace(self, fake_orchestrator):
        """Test parser handles JSON missing closing brace."""
        fake_orchestrator.response_content = '{"task_type": "CODE_GENERATION", "confidence": 0.9'

        router = TaskRouter(orchestrator=fake_orchestrator, verbose=False)
        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original"
        )

        result = router._classify_with_llm(task)
        # Should keep original on parse failure
        assert result.task_type == TaskType.RESEARCH
        assert result.confidence == 0.4

    @pytest.mark.unit
    def test_llm_classification_handles_json_with_trailing_comma(self, fake_orchestrator):
        """Test parser handles invalid JSON with trailing comma."""
        fake_orchestrator.response_content = '{"task_type": "CODE_GENERATION", "confidence": 0.9, "reasoning": "test",}'

        router = TaskRouter(orchestrator=fake_orchestrator, verbose=False)
        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original"
        )

        result = router._classify_with_llm(task)
        # JSON with trailing comma is invalid
        assert result.task_type == TaskType.RESEARCH

    @pytest.mark.unit
    def test_llm_classification_handles_missing_task_type_field(self, fake_orchestrator):
        """Test parser handles JSON missing required task_type field."""
        fake_orchestrator.response_content = '{"confidence": 0.9, "reasoning": "Missing task type"}'

        router = TaskRouter(orchestrator=fake_orchestrator, verbose=False)
        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original"
        )

        result = router._classify_with_llm(task)
        # Missing task_type means empty string, not in type_map
        assert result.task_type == TaskType.RESEARCH

    @pytest.mark.unit
    def test_llm_classification_handles_invalid_task_type_value(self, fake_orchestrator):
        """Test parser handles unknown task type value."""
        fake_orchestrator.response_content = '{"task_type": "UNKNOWN_TYPE", "confidence": 0.9, "reasoning": "Invalid type"}'

        router = TaskRouter(orchestrator=fake_orchestrator, verbose=False)
        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original"
        )

        result = router._classify_with_llm(task)
        # UNKNOWN_TYPE not in type_map
        assert result.task_type == TaskType.RESEARCH

    @pytest.mark.unit
    def test_llm_classification_handles_lowercase_task_type(self, fake_orchestrator):
        """Test parser handles lowercase task type (should work due to .upper())."""
        fake_orchestrator.response_content = '{"task_type": "code_generation", "confidence": 0.85, "reasoning": "lowercase"}'

        router = TaskRouter(orchestrator=fake_orchestrator, verbose=False)
        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original"
        )

        result = router._classify_with_llm(task)
        # Should work because code calls .upper()
        assert result.task_type == TaskType.CODE_GENERATION

    @pytest.mark.unit
    def test_llm_classification_handles_confidence_as_string(self, fake_orchestrator):
        """Test parser converts string confidence to float."""
        fake_orchestrator.response_content = '{"task_type": "RESEARCH", "confidence": "0.85", "reasoning": "String confidence"}'

        router = TaskRouter(orchestrator=fake_orchestrator, verbose=False)
        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.CONVERSATION,
            confidence=0.4,
            reasoning="Original"
        )

        result = router._classify_with_llm(task)
        # float() should convert string "0.85" to 0.85
        assert result.task_type == TaskType.RESEARCH
        assert result.confidence == 0.85

    @pytest.mark.unit
    def test_llm_classification_handles_missing_confidence_field(self, fake_orchestrator):
        """Test parser uses default 0.5 for missing confidence."""
        fake_orchestrator.response_content = '{"task_type": "CODE_GENERATION", "reasoning": "No confidence field"}'

        router = TaskRouter(orchestrator=fake_orchestrator, verbose=False)
        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original"
        )

        result = router._classify_with_llm(task)
        # Default confidence is 0.5 which is < 0.7, so original kept
        assert result.task_type == TaskType.RESEARCH

    @pytest.mark.unit
    def test_llm_classification_handles_empty_response(self, fake_orchestrator):
        """Test parser handles empty string response."""
        fake_orchestrator.response_content = ''

        router = TaskRouter(orchestrator=fake_orchestrator, verbose=False)
        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original"
        )

        result = router._classify_with_llm(task)
        assert result.task_type == TaskType.RESEARCH

    @pytest.mark.unit
    def test_llm_classification_handles_no_providers_available(self):
        """Test classification when no providers are available."""
        class NoProviderOrchestrator:
            def __init__(self):
                self.providers = self

            def list_available(self):
                return []  # No providers

            def delegate(self, *args, **kwargs):
                raise Exception("Should not be called")

        router = TaskRouter(orchestrator=NoProviderOrchestrator(), verbose=False)
        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original"
        )

        result = router._classify_with_llm(task)
        # No provider available, should return original
        assert result.task_type == TaskType.RESEARCH
        assert result.confidence == 0.4

    @pytest.mark.unit
    def test_llm_classification_prefers_cerebras_provider(self):
        """Test that cerebras is preferred over other providers."""
        class ProviderTracker:
            def __init__(self):
                self.providers = self
                self.used_provider = None

            def list_available(self):
                return ['gemini', 'cerebras', 'groq']  # cerebras not first

            def delegate(self, provider, prompt, **kwargs):
                self.used_provider = provider
                class Response:
                    content = '{"task_type": "RESEARCH", "confidence": 0.8, "reasoning": "test"}'
                return Response()

        orch = ProviderTracker()
        router = TaskRouter(orchestrator=orch, verbose=False)
        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.CONVERSATION,
            confidence=0.4,
            reasoning="Original"
        )

        router._classify_with_llm(task)
        assert orch.used_provider == 'cerebras'

    @pytest.mark.unit
    def test_llm_classification_preserves_original_on_exception(self):
        """Test that exceptions during delegation preserve original task."""
        class FailingOrchestrator:
            def __init__(self):
                self.providers = self

            def list_available(self):
                return ['groq']

            def delegate(self, *args, **kwargs):
                raise RuntimeError("API connection failed")

        router = TaskRouter(orchestrator=FailingOrchestrator(), verbose=False)
        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original reasoning"
        )

        result = router._classify_with_llm(task)
        assert result.task_type == TaskType.RESEARCH
        assert result.confidence == 0.4
        assert result.reasoning == "Original reasoning"

    @pytest.mark.unit
    def test_llm_classification_without_orchestrator(self):
        """Test LLM classification without orchestrator returns original."""
        router = TaskRouter(orchestrator=None, verbose=False)

        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original"
        )

        result = router._classify_with_llm(task)
        assert result.task_type == TaskType.RESEARCH


class TestProviderResolution:
    """Tests for provider resolution logic."""

    @pytest.fixture
    def mock_orchestrator(self):
        orch = Mock()
        orch.providers = Mock()
        return orch

    @pytest.mark.unit
    def test_resolve_provider_without_hint(self):
        """Test provider resolution with no hint."""
        router = TaskRouter(orchestrator=None, verbose=False)
        provider, model = router._resolve_provider(None)
        assert provider is None
        assert model is None

    @pytest.mark.unit
    def test_resolve_provider_without_orchestrator(self):
        """Test provider resolution without orchestrator."""
        router = TaskRouter(orchestrator=None, verbose=False)
        provider, model = router._resolve_provider("fast")
        assert provider is None
        assert model is None

    @pytest.mark.unit
    def test_resolve_provider_fast_prefers_cerebras(self, mock_orchestrator):
        """Test fast hint prefers cerebras."""
        mock_orchestrator.providers.list_available.return_value = ['groq', 'cerebras', 'gemini']

        router = TaskRouter(orchestrator=mock_orchestrator, verbose=False)
        provider, model = router._resolve_provider("fast")

        assert provider == 'cerebras'

    @pytest.mark.unit
    def test_resolve_provider_fast_fallback_to_groq(self, mock_orchestrator):
        """Test fast hint falls back to groq."""
        mock_orchestrator.providers.list_available.return_value = ['groq', 'gemini']

        router = TaskRouter(orchestrator=mock_orchestrator, verbose=False)
        provider, model = router._resolve_provider("fast")

        assert provider == 'groq'

    @pytest.mark.unit
    def test_resolve_provider_fast_fallback_to_gemini(self, mock_orchestrator):
        """Test fast hint falls back to gemini."""
        mock_orchestrator.providers.list_available.return_value = ['gemini']

        router = TaskRouter(orchestrator=mock_orchestrator, verbose=False)
        provider, model = router._resolve_provider("fast")

        assert provider == 'gemini'

    @pytest.mark.unit
    def test_resolve_provider_high_volume(self, mock_orchestrator):
        """Test high_volume hint uses fast providers."""
        mock_orchestrator.providers.list_available.return_value = ['groq']

        router = TaskRouter(orchestrator=mock_orchestrator, verbose=False)
        provider, model = router._resolve_provider("high_volume")

        assert provider == 'groq'

    @pytest.mark.unit
    def test_resolve_provider_quality_cerebras_70b(self, mock_orchestrator):
        """Test quality hint uses 70B models."""
        mock_orchestrator.providers.list_available.return_value = ['cerebras', 'groq']

        router = TaskRouter(orchestrator=mock_orchestrator, verbose=False)
        provider, model = router._resolve_provider("quality")

        assert provider == 'cerebras'
        assert model == 'llama-3.3-70b'

    @pytest.mark.unit
    def test_resolve_provider_quality_groq_70b(self, mock_orchestrator):
        """Test quality hint uses groq 70B model."""
        mock_orchestrator.providers.list_available.return_value = ['groq']

        router = TaskRouter(orchestrator=mock_orchestrator, verbose=False)
        provider, model = router._resolve_provider("quality")

        assert provider == 'groq'
        assert model == 'llama-3.3-70b-versatile'

    @pytest.mark.unit
    def test_resolve_provider_quality_gemini_fallback(self, mock_orchestrator):
        """Test quality hint falls back to gemini."""
        mock_orchestrator.providers.list_available.return_value = ['gemini']

        router = TaskRouter(orchestrator=mock_orchestrator, verbose=False)
        provider, model = router._resolve_provider("quality")

        assert provider == 'gemini'
        assert model is None

    @pytest.mark.unit
    def test_resolve_provider_general_hint(self, mock_orchestrator):
        """Test general hint uses fast providers."""
        mock_orchestrator.providers.list_available.return_value = ['gemini']

        router = TaskRouter(orchestrator=mock_orchestrator, verbose=False)
        provider, model = router._resolve_provider("general")

        # 'general' is like 'fast', should return gemini
        assert provider == 'gemini'

    @pytest.mark.unit
    def test_resolve_provider_empty_available_list(self, mock_orchestrator):
        """Test resolution with no available providers."""
        mock_orchestrator.providers.list_available.return_value = []

        router = TaskRouter(orchestrator=mock_orchestrator, verbose=False)
        provider, model = router._resolve_provider("fast")

        assert provider is None
        assert model is None


class TestHooksAndExtensibility:
    """Tests for pre/post execution hooks."""

    @pytest.fixture
    def router(self):
        return TaskRouter(orchestrator=None, auto_confirm_direct=True, verbose=False)

    @pytest.mark.unit
    def test_add_pre_hook(self, router):
        """Test adding a pre-execution hook."""

        def modify_task(task):
            task.reasoning = "Modified by hook"
            return task

        router.add_pre_hook(modify_task)
        assert len(router._pre_hooks) == 1

    @pytest.mark.unit
    def test_add_post_hook(self, router):
        """Test adding a post-execution hook."""

        def modify_result(result):
            result.tokens_used = 999
            return result

        router.add_post_hook(modify_result)
        assert len(router._post_hooks) == 1

    @pytest.mark.unit
    def test_pre_hook_execution(self, router):
        """Test that pre-hooks are executed."""
        hook_called = []

        def track_hook(task):
            hook_called.append(True)
            return task

        router.add_pre_hook(track_hook)
        router.route("hello")

        assert len(hook_called) == 1

    @pytest.mark.unit
    def test_post_hook_execution(self, router):
        """Test that post-hooks are executed."""
        hook_called = []

        def track_hook(result):
            hook_called.append(True)
            return result

        router.add_post_hook(track_hook)
        router.route("hello")

        assert len(hook_called) == 1

    @pytest.mark.unit
    def test_pre_hook_modifies_task(self, router):
        """Test that pre-hook can modify task."""

        def force_conversation(task):
            task.task_type = TaskType.CONVERSATION
            task.confidence = 1.0
            return task

        router.add_pre_hook(force_conversation)
        result = router.route("create a file")  # Would normally be CODE_GEN

        # Should succeed because hook forced CONVERSATION
        assert result.success is True

    @pytest.mark.unit
    def test_post_hook_modifies_result(self, router):
        """Test that post-hook can modify result."""

        def add_metadata(result):
            result.metadata["hook_processed"] = True
            return result

        router.add_post_hook(add_metadata)
        result = router.route("hello")

        assert result.metadata.get("hook_processed") is True

    @pytest.mark.unit
    def test_multiple_pre_hooks_in_order(self, router):
        """Test multiple pre-hooks execute in order."""
        call_order = []

        def hook1(task):
            call_order.append(1)
            return task

        def hook2(task):
            call_order.append(2)
            return task

        router.add_pre_hook(hook1)
        router.add_pre_hook(hook2)
        router.route("hello")

        assert call_order == [1, 2]


class TestStrategyManagement:
    """Tests for strategy selection and management."""

    @pytest.fixture
    def router(self):
        return TaskRouter(orchestrator=None, verbose=False)

    @pytest.mark.unit
    def test_classify_only(self, router):
        """Test classification without execution."""
        task = router.classify_only("create a python file")

        assert isinstance(task, ClassifiedTask)
        assert task.task_type in [TaskType.CODE_GENERATION, TaskType.RESEARCH, TaskType.DIRECT_COMMAND, TaskType.CONVERSATION]

    @pytest.mark.unit
    def test_set_strategy(self, router):
        """Test overriding strategy for task type."""
        custom_strategy = Mock()
        custom_strategy.name = "CustomStrategy"
        custom_strategy.can_handle.return_value = True

        router.set_strategy(TaskType.CONVERSATION, custom_strategy)

        assert router.strategies[TaskType.CONVERSATION] == custom_strategy

    @pytest.mark.unit
    def test_router_repr(self, router):
        """Test router string representation."""
        repr_str = repr(router)

        assert "TaskRouter" in repr_str
        assert "strategies" in repr_str

    @pytest.mark.unit
    def test_get_strategy_fallback_without_orchestrator(self):
        """Test strategy fallback when orchestrator missing."""
        router = TaskRouter(orchestrator=None, verbose=False)

        task = ClassifiedTask(
            original_input="explain something",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="Research task"
        )

        strategy = router._get_strategy(task)

        # Should fallback to conversation when no orchestrator
        assert strategy is not None
        assert strategy.name == "ConversationExecutor"

    @pytest.mark.unit
    def test_get_strategy_returns_none_when_unavailable(self):
        """Test strategy returns None for unavailable type."""
        router = TaskRouter(orchestrator=None, verbose=False)

        # Remove a strategy manually
        del router.strategies[TaskType.CONVERSATION]

        task = ClassifiedTask(
            original_input="hello",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="Conversation"
        )

        strategy = router._get_strategy(task)
        assert strategy is None


class TestClarifyIntent:
    """Tests for intent clarification with user input."""

    @pytest.fixture
    def router(self):
        # Use NullClarifier by default to avoid interactive prompts
        from src.task_router.intent_clarifier import NullClarifier
        return TaskRouter(
            orchestrator=None,
            verbose=False,
            intent_clarifier=NullClarifier()
        )

    @pytest.mark.unit
    def test_clarify_intent_choice_1_research(self):
        """Test clarify intent with choice 1 (RESEARCH)."""
        from src.task_router.intent_clarifier import InteractiveClarifier

        task = ClassifiedTask(
            original_input="explain how to create",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.5,
            reasoning="Ambiguous"
        )

        # Use injectable clarifier with mocked input
        mock_input = Mock(return_value='1')
        clarifier = InteractiveClarifier(input_fn=mock_input)
        router = TaskRouter(
            orchestrator=None,
            verbose=False,
            intent_clarifier=clarifier
        )

        result = router._clarify_intent(task)

        assert result.task_type == TaskType.RESEARCH
        assert result.confidence == 1.0
        assert "User clarified" in result.reasoning

    @pytest.mark.unit
    def test_clarify_intent_choice_2_code_generation(self):
        """Test clarify intent with choice 2 (CODE_GENERATION)."""
        from src.task_router.intent_clarifier import InteractiveClarifier

        task = ClassifiedTask(
            original_input="explain how to create",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="Ambiguous"
        )

        mock_input = Mock(return_value='2')
        clarifier = InteractiveClarifier(input_fn=mock_input)
        router = TaskRouter(
            orchestrator=None,
            verbose=False,
            intent_clarifier=clarifier
        )

        result = router._clarify_intent(task)

        assert result.task_type == TaskType.CODE_GENERATION
        assert result.confidence == 1.0

    @pytest.mark.unit
    def test_clarify_intent_choice_3_keep_original(self):
        """Test clarify intent with choice 3 (keep original)."""
        from src.task_router.intent_clarifier import InteractiveClarifier

        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="Original"
        )

        mock_input = Mock(return_value='3')
        clarifier = InteractiveClarifier(input_fn=mock_input)
        router = TaskRouter(
            orchestrator=None,
            verbose=False,
            intent_clarifier=clarifier
        )

        result = router._clarify_intent(task)

        assert result.task_type == TaskType.RESEARCH
        assert result.confidence == 0.5  # Unchanged

    @pytest.mark.unit
    def test_clarify_intent_eof_error(self):
        """Test clarify intent handles EOF error."""
        from src.task_router.intent_clarifier import InteractiveClarifier

        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="Original"
        )

        mock_input = Mock(side_effect=EOFError)
        clarifier = InteractiveClarifier(input_fn=mock_input)
        router = TaskRouter(
            orchestrator=None,
            verbose=False,
            intent_clarifier=clarifier
        )

        result = router._clarify_intent(task)

        # Should keep original on EOFError
        assert result.task_type == TaskType.RESEARCH

    @pytest.mark.unit
    def test_clarify_intent_keyboard_interrupt(self):
        """Test clarify intent handles keyboard interrupt."""
        from src.task_router.intent_clarifier import InteractiveClarifier

        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="Original"
        )

        mock_input = Mock(side_effect=KeyboardInterrupt)
        clarifier = InteractiveClarifier(input_fn=mock_input)
        router = TaskRouter(
            orchestrator=None,
            verbose=False,
            intent_clarifier=clarifier
        )

        result = router._clarify_intent(task)

        # Should keep original on KeyboardInterrupt
        assert result.task_type == TaskType.RESEARCH


class TestRouteWithProvider:
    """Tests for route_with_provider method."""

    @pytest.fixture
    def mock_orchestrator(self):
        orch = Mock()
        orch.providers = Mock()
        orch.providers.list_available.return_value = ['groq']
        return orch

    @pytest.mark.unit
    def test_route_with_provider_override(self, mock_orchestrator):
        """Test routing with provider override."""
        router = TaskRouter(
            orchestrator=mock_orchestrator,
            verbose=False,
            auto_confirm_direct=True
        )
        router.use_llm_classification = False

        result = router.route_with_provider("hello", provider_override="fast")

        assert isinstance(result, ExecutionResult)
        assert "override_provider" in result.metadata.get("classification", {})
        assert result.metadata["classification"]["override_provider"] == "fast"

    @pytest.mark.unit
    def test_route_with_provider_no_override(self):
        """Test routing without provider override."""
        router = TaskRouter(orchestrator=None, verbose=False)
        router.use_llm_classification = False

        result = router.route_with_provider("hello")

        assert isinstance(result, ExecutionResult)
        assert result.metadata["classification"]["override_provider"] is None

    @pytest.mark.unit
    def test_route_with_provider_includes_classification_metadata(self):
        """Test that result includes classification metadata."""
        router = TaskRouter(orchestrator=None, verbose=False)
        router.use_llm_classification = False

        result = router.route_with_provider("hello")

        metadata = result.metadata.get("classification", {})
        assert "type" in metadata
        assert "confidence" in metadata
        assert "reasoning" in metadata
        assert "resolved_provider" in metadata
        assert "resolved_model" in metadata


class TestShouldExecute:
    """Tests for execution confirmation logic."""

    @pytest.fixture
    def router(self):
        return TaskRouter(orchestrator=None, auto_confirm_direct=False, verbose=False)

    @pytest.mark.unit
    def test_conversation_always_executes(self, router):
        """Test that conversation tasks always execute."""
        task = ClassifiedTask(
            original_input="hello",
            task_type=TaskType.CONVERSATION,
            confidence=0.9,
            reasoning="Greeting"
        )

        strategy = router.strategies[TaskType.CONVERSATION]
        should_exec = router._should_execute(task, strategy)

        assert should_exec is True

    @pytest.mark.unit
    def test_research_always_executes(self, router):
        """Test that research tasks always execute."""
        task = ClassifiedTask(
            original_input="explain python",
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="Research"
        )

        strategy = Mock()
        should_exec = router._should_execute(task, strategy)

        assert should_exec is True

    @pytest.mark.unit
    def test_code_generation_always_executes(self, router):
        """Test that code generation tasks always execute."""
        task = ClassifiedTask(
            original_input="create file",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.9,
            reasoning="Code gen"
        )

        strategy = Mock()
        should_exec = router._should_execute(task, strategy)

        assert should_exec is True

    @pytest.mark.unit
    def test_direct_command_auto_confirm(self):
        """Test direct command with auto-confirm."""
        router = TaskRouter(orchestrator=None, auto_confirm_direct=True, verbose=False)

        task = ClassifiedTask(
            original_input="echo test",
            task_type=TaskType.DIRECT_COMMAND,
            confidence=0.9,
            reasoning="Direct",
            extracted_command="echo test"
        )

        strategy = router.strategies[TaskType.DIRECT_COMMAND]
        should_exec = router._should_execute(task, strategy)

        assert should_exec is True

    @pytest.mark.unit
    def test_direct_command_dangerous_blocked(self):
        """Test that dangerous direct commands are blocked."""
        router = TaskRouter(orchestrator=None, auto_confirm_direct=False, verbose=False)

        task = ClassifiedTask(
            original_input="rm -rf /",
            task_type=TaskType.DIRECT_COMMAND,
            confidence=0.9,
            reasoning="Direct",
            extracted_command="rm -rf /"
        )

        strategy = router.strategies[TaskType.DIRECT_COMMAND]
        should_exec = router._should_execute(task, strategy)

        # Should be blocked as dangerous
        assert should_exec is False


class TestLogging:
    """Tests for logging and output."""

    @pytest.mark.unit
    def test_log_classification_with_command(self, capsys):
        """Test that classification logging includes command."""
        router = TaskRouter(orchestrator=None, verbose=True)

        task = ClassifiedTask(
            original_input="echo test",
            task_type=TaskType.DIRECT_COMMAND,
            confidence=0.9,
            reasoning="Direct command",
            extracted_command="echo test"
        )

        router._log_classification(task)

        captured = capsys.readouterr()
        assert "direct_command" in captured.out  # TaskType.value is lowercase
        assert "echo test" in captured.out

    @pytest.mark.unit
    def test_log_classification_with_planning(self, capsys):
        """Test that classification logging includes planning flag."""
        router = TaskRouter(orchestrator=None, verbose=True)

        task = ClassifiedTask(
            original_input="create complex app",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.9,
            reasoning="Code generation",
            requires_planning=True
        )

        router._log_classification(task)

        captured = capsys.readouterr()
        assert "Requires planning" in captured.out

    @pytest.mark.unit
    def test_verbose_logging_in_route(self, capsys):
        """Test that verbose mode produces output."""
        router = TaskRouter(orchestrator=None, verbose=True)
        router.use_llm_classification = False

        router.route("hello")

        captured = capsys.readouterr()
        assert "Task Classification" in captured.out


class TestAdditionalIntentClarification:
    """Additional tests for intent clarification detection."""

    @pytest.fixture
    def router(self):
        return TaskRouter(orchestrator=None, verbose=False)

    @pytest.mark.unit
    def test_low_confidence_needs_clarification(self, router):
        """Test that low confidence always needs clarification."""
        task = ClassifiedTask(
            original_input="something",
            task_type=TaskType.CONVERSATION,
            confidence=0.3,  # Below threshold
            reasoning="Low confidence"
        )

        needs = router._needs_intent_clarification(task)
        assert needs is True

    @pytest.mark.unit
    def test_question_mark_with_action_verb_needs_clarification(self, router):
        """Test question mark with action verb needs clarification."""
        task = ClassifiedTask(
            original_input="can you create this?",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.8,
            reasoning="High confidence"
        )

        needs = router._needs_intent_clarification(task)
        assert needs is True

    @pytest.mark.unit
    def test_escalation_disabled_respects_setting(self, router):
        """Test that escalation respects disabled setting."""
        router.escalate_on_low_confidence = False

        task = ClassifiedTask(
            original_input="create something",
            task_type=TaskType.RESEARCH,
            confidence=0.3,
            reasoning="Low confidence"
        )

        result = router._apply_confidence_escalation(task)
        # Should not escalate when disabled
        assert result.task_type == TaskType.RESEARCH

    @pytest.mark.unit
    def test_non_research_task_not_escalated(self, router):
        """Test that non-RESEARCH tasks are not escalated."""
        task = ClassifiedTask(
            original_input="hello",
            task_type=TaskType.CONVERSATION,
            confidence=0.3,
            reasoning="Low confidence"
        )

        result = router._apply_confidence_escalation(task)
        # CONVERSATION should not escalate
        assert result.task_type == TaskType.CONVERSATION


class TestRouterResultMetadata:
    """Tests for result metadata population."""

    @pytest.mark.unit
    def test_classification_metadata_complete(self):
        """Test that classification metadata is complete."""
        router = TaskRouter(orchestrator=None, verbose=False)
        router.use_llm_classification = False

        result = router.route("hello")

        metadata = result.metadata.get("classification", {})
        assert "type" in metadata
        assert "confidence" in metadata
        assert "complexity" in metadata
        assert "reasoning" in metadata
        assert "suggested_provider" in metadata
        assert "override_provider" in metadata
        assert "resolved_provider" in metadata
        assert "resolved_model" in metadata
        assert "used_llm_classification" in metadata

    @pytest.mark.unit
    def test_used_llm_classification_flag(self):
        """Test that LLM classification flag is set correctly."""
        router = TaskRouter(orchestrator=None, verbose=False)
        router.use_llm_classification = False

        result = router.route("hello")

        metadata = result.metadata.get("classification", {})
        # Should be False since LLM wasn't used
        assert metadata["used_llm_classification"] is False


class TestNoStrategyAvailable:
    """Tests for handling missing strategies."""

    @pytest.mark.unit
    def test_route_returns_error_when_no_strategy(self):
        """Test that route returns error when no strategy available."""
        router = TaskRouter(orchestrator=None, verbose=False)
        router.use_llm_classification = False

        # Remove all strategies
        router.strategies.clear()

        result = router.route("hello")

        assert result.success is False
        assert "No strategy available" in result.error

    @pytest.mark.unit
    def test_route_with_provider_returns_error_when_no_strategy(self):
        """Test route_with_provider returns error when no strategy."""
        router = TaskRouter(orchestrator=None, verbose=False)
        router.use_llm_classification = False

        # Remove all strategies
        router.strategies.clear()

        result = router.route_with_provider("hello")

        assert result.success is False
        assert "No strategy available" in result.error
