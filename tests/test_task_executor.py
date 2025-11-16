"""
Tests for TaskExecutor - planning, reasoning, and synthesis operations.
"""
import pytest
from unittest.mock import Mock, MagicMock
from src.orchestrator.task_executor import TaskExecutor
from src.providers import LLMResponse


class TestTaskExecutorSimpleTaskDetection:
    """Test the _is_simple_task heuristic."""

    @pytest.fixture
    def executor(self):
        """Create a TaskExecutor with mock dependencies."""
        mock_brain = Mock()
        mock_brain_name = Mock(return_value="test_brain")
        mock_record = Mock()
        return TaskExecutor(
            get_brain_provider=lambda: mock_brain,
            get_brain_name=mock_brain_name,
            record_task=mock_record
        )

    @pytest.mark.unit
    def test_short_simple_task_detected(self, executor):
        """Short tasks without multi-step indicators are simple."""
        assert executor._is_simple_task("Open file") is True
        assert executor._is_simple_task("Save changes") is True
        assert executor._is_simple_task("Read config") is True
        assert executor._is_simple_task("Delete temp files") is True

    @pytest.mark.unit
    def test_task_with_and_is_complex(self, executor):
        """Tasks with 'and' conjunction are complex."""
        assert executor._is_simple_task("Open file and save") is False
        assert executor._is_simple_task("Read and process data") is False

    @pytest.mark.unit
    def test_task_with_then_is_complex(self, executor):
        """Tasks with 'then' are complex (sequential steps)."""
        assert executor._is_simple_task("Open file then edit") is False
        assert executor._is_simple_task("Build then deploy") is False

    @pytest.mark.unit
    def test_task_with_enumeration_is_complex(self, executor):
        """Tasks with numbering indicators are complex."""
        assert executor._is_simple_task("1. Do this first") is False
        assert executor._is_simple_task("Step 1: initialize") is False
        assert executor._is_simple_task("First, open the file") is False

    @pytest.mark.unit
    def test_long_task_is_complex(self, executor):
        """Tasks over 8 words or 50 chars are complex."""
        long_task = "Implement a user authentication system with JWT tokens"
        assert executor._is_simple_task(long_task) is False
        # 8 words but 57 chars (over 50 char limit)
        assert len(long_task) > 50

    @pytest.mark.unit
    def test_short_but_multi_step_is_complex(self, executor):
        """Short tasks with multiple steps indicators are complex."""
        assert executor._is_simple_task("Do multiple things") is False
        assert executor._is_simple_task("Handle several cases") is False

    @pytest.mark.unit
    def test_edge_case_exactly_8_words_simple(self, executor):
        """Exactly 8 words without indicators is simple."""
        task = "Read the config file from disk now"  # 7 words
        assert executor._is_simple_task(task) is True

    @pytest.mark.unit
    def test_temporal_words_are_complex(self, executor):
        """Tasks with temporal ordering words are complex."""
        assert executor._is_simple_task("Do this after that") is False
        assert executor._is_simple_task("Do before lunch") is False
        assert executor._is_simple_task("Do next thing") is False


class TestTaskExecutorPlanSkipLogic:
    """Test the plan() method skip logic for simple tasks."""

    @pytest.fixture
    def mock_brain(self):
        """Create a mock brain provider."""
        brain = Mock()
        brain.chat = Mock(return_value=LLMResponse(
            content='[{"step": "analyze", "description": "analyze the task", "provider_type": "quality"}]',
            model="test-model",
            provider="test",
            tokens_used=100,
            latency_ms=50.0
        ))
        return brain

    @pytest.fixture
    def executor(self, mock_brain):
        """Create a TaskExecutor with mock dependencies."""
        mock_record = Mock()
        return TaskExecutor(
            get_brain_provider=lambda: mock_brain,
            get_brain_name=lambda: "test_brain",
            record_task=mock_record
        )

    @pytest.mark.unit
    def test_low_complexity_score_skips_planning(self, executor, mock_brain):
        """When complexity_score <= 3, planning is skipped."""
        result = executor.plan("Open file", complexity_score=2)

        # Should return single-step plan
        assert len(result) == 1
        assert result[0]['step'] == 'execute_task'
        assert result[0]['description'] == 'Open file'
        assert result[0]['provider_type'] == 'fast'

        # Should NOT call the brain
        mock_brain.chat.assert_not_called()

    @pytest.mark.unit
    def test_complexity_score_3_skips_planning(self, executor, mock_brain):
        """Complexity score of exactly 3 should skip planning."""
        result = executor.plan("Save document", complexity_score=3)

        assert len(result) == 1
        assert result[0]['provider_type'] == 'fast'
        mock_brain.chat.assert_not_called()

    @pytest.mark.unit
    def test_complexity_score_4_does_not_skip(self, executor, mock_brain):
        """Complexity score > 3 should call the brain for planning."""
        result = executor.plan("Implement feature", complexity_score=4)

        # Should call the brain
        mock_brain.chat.assert_called_once()

        # Should return parsed plan from brain
        assert len(result) >= 1
        assert result[0]['step'] == 'analyze'

    @pytest.mark.unit
    def test_no_score_simple_task_skips_planning(self, executor, mock_brain):
        """Without complexity score, simple tasks skip planning via heuristic."""
        result = executor.plan("Open file")

        assert len(result) == 1
        assert result[0]['step'] == 'execute_task'
        assert result[0]['description'] == 'Open file'
        mock_brain.chat.assert_not_called()

    @pytest.mark.unit
    def test_no_score_complex_task_uses_brain(self, executor, mock_brain):
        """Without complexity score, complex tasks use the brain."""
        result = executor.plan("Implement user authentication with JWT and OAuth support")

        # Should call the brain for complex task
        mock_brain.chat.assert_called_once()

    @pytest.mark.unit
    def test_explicit_score_overrides_heuristic(self, executor, mock_brain):
        """Explicit complexity_score takes precedence over heuristic."""
        # Simple task text but high complexity score
        result = executor.plan("Open file", complexity_score=5)

        # High score should trigger brain call despite simple text
        mock_brain.chat.assert_called_once()

    @pytest.mark.unit
    def test_skip_plan_structure_is_valid(self, executor):
        """Skipped plans have correct structure."""
        result = executor.plan("Test task", complexity_score=1)

        # Validate structure
        assert isinstance(result, list)
        assert len(result) == 1
        step = result[0]
        assert 'step' in step
        assert 'description' in step
        assert 'provider_type' in step
        assert step['provider_type'] in ['fast', 'quality', 'high_volume']


class TestTaskExecutorPlanParsing:
    """Test plan() JSON parsing and error handling."""

    @pytest.fixture
    def mock_record(self):
        return Mock()

    @pytest.mark.unit
    def test_plan_parses_json_array(self, mock_record):
        """Plan correctly parses JSON array response."""
        mock_brain = Mock()
        mock_brain.chat = Mock(return_value=LLMResponse(
            content='[{"step": "step1", "description": "do thing", "provider_type": "fast"}]',
            model="test", provider="test", tokens_used=10, latency_ms=10.0
        ))

        executor = TaskExecutor(lambda: mock_brain, lambda: "brain", mock_record)
        result = executor.plan("Complex task", complexity_score=10)

        assert len(result) == 1
        assert result[0]['step'] == 'step1'

    @pytest.mark.unit
    def test_plan_handles_markdown_code_block(self, mock_record):
        """Plan extracts JSON from markdown code blocks."""
        mock_brain = Mock()
        mock_brain.chat = Mock(return_value=LLMResponse(
            content='```json\n[{"step": "extracted", "description": "from markdown", "provider_type": "quality"}]\n```',
            model="test", provider="test", tokens_used=10, latency_ms=10.0
        ))

        executor = TaskExecutor(lambda: mock_brain, lambda: "brain", mock_record)
        result = executor.plan("Complex task", complexity_score=10)

        assert result[0]['step'] == 'extracted'

    @pytest.mark.unit
    def test_plan_handles_json_decode_error(self, mock_record):
        """Plan handles malformed JSON gracefully."""
        mock_brain = Mock()
        mock_brain.chat = Mock(return_value=LLMResponse(
            content='This is not valid JSON at all',
            model="test", provider="test", tokens_used=10, latency_ms=10.0
        ))

        executor = TaskExecutor(lambda: mock_brain, lambda: "brain", mock_record)
        result = executor.plan("Complex task", complexity_score=10)

        # Should fall back to single step with raw content
        assert len(result) == 1
        assert result[0]['step'] == 'execute_task'
        assert 'not valid JSON' in result[0]['description']
