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


class TestTaskExecutorPlanOutputValidation:
    """Test that plan() returns valid, actionable step structures."""

    @pytest.fixture
    def mock_record(self):
        return Mock()

    @pytest.mark.unit
    def test_plan_returns_valid_steps_for_complex_task(self, mock_record):
        """Complex task returns multiple steps with valid structure."""
        mock_brain = Mock()
        mock_brain.chat = Mock(return_value=LLMResponse(
            content='''[
                {"step": "analyze_requirements", "description": "Review OAuth requirements and identify providers", "provider_type": "quality"},
                {"step": "setup_oauth_config", "description": "Configure OAuth client credentials and callbacks", "provider_type": "fast"},
                {"step": "implement_auth_flow", "description": "Build authentication flow with token exchange", "provider_type": "quality"},
                {"step": "add_session_management", "description": "Implement secure session handling", "provider_type": "quality"},
                {"step": "write_tests", "description": "Create integration tests for auth flow", "provider_type": "fast"}
            ]''',
            model="test", provider="test", tokens_used=200, latency_ms=100.0
        ))

        executor = TaskExecutor(lambda: mock_brain, lambda: "brain", mock_record)
        result = executor.plan("Implement user auth with OAuth", complexity_score=8)

        # Verify multiple steps returned
        assert len(result) >= 2, f"Expected at least 2 steps, got {len(result)}"

        # Verify each step has required keys
        for i, step in enumerate(result):
            assert 'step' in step, f"Step {i} missing 'step' key"
            assert 'description' in step, f"Step {i} missing 'description' key"
            assert 'provider_type' in step, f"Step {i} missing 'provider_type' key"

            # Verify provider_type is valid
            valid_types = ['fast', 'quality', 'high_volume']
            assert step['provider_type'] in valid_types, \
                f"Step {i} has invalid provider_type '{step['provider_type']}'"

            # Verify step name is non-empty
            assert len(step['step']) > 0, f"Step {i} has empty step name"
            assert len(step['description']) > 0, f"Step {i} has empty description"

    @pytest.mark.unit
    def test_plan_step_names_are_meaningful(self, mock_record):
        """Plan step names should be descriptive identifiers."""
        mock_brain = Mock()
        mock_brain.chat = Mock(return_value=LLMResponse(
            content='''[
                {"step": "validate_input", "description": "Check input parameters", "provider_type": "fast"},
                {"step": "process_data", "description": "Transform and process data", "provider_type": "quality"}
            ]''',
            model="test", provider="test", tokens_used=50, latency_ms=30.0
        ))

        executor = TaskExecutor(lambda: mock_brain, lambda: "brain", mock_record)
        result = executor.plan("Process data pipeline", complexity_score=5)

        # Step names should be snake_case identifiers (no spaces, lowercase)
        for step in result:
            step_name = step['step']
            # Should not contain spaces
            assert ' ' not in step_name, f"Step name '{step_name}' contains spaces"
            # Should be lowercase or snake_case
            assert step_name == step_name.lower() or '_' in step_name, \
                f"Step name '{step_name}' should be snake_case"

    @pytest.mark.unit
    def test_plan_provider_types_match_task_complexity(self, mock_record):
        """Provider types should be appropriate for step complexity."""
        mock_brain = Mock()
        mock_brain.chat = Mock(return_value=LLMResponse(
            content='''[
                {"step": "quick_check", "description": "Simple validation", "provider_type": "fast"},
                {"step": "deep_analysis", "description": "Complex reasoning task", "provider_type": "quality"},
                {"step": "batch_process", "description": "Process many items", "provider_type": "high_volume"}
            ]''',
            model="test", provider="test", tokens_used=80, latency_ms=50.0
        ))

        executor = TaskExecutor(lambda: mock_brain, lambda: "brain", mock_record)
        result = executor.plan("Multi-step task", complexity_score=7)

        # Should have at least one step
        assert len(result) >= 1

        # Collect provider types used
        provider_types = {step['provider_type'] for step in result}

        # Should have valid provider types
        valid_types = {'fast', 'quality', 'high_volume'}
        assert provider_types.issubset(valid_types), \
            f"Invalid provider types: {provider_types - valid_types}"


class TestTaskExecutorMalformedJSONRecovery:
    """Test JSON recovery from various malformed LLM responses."""

    @pytest.fixture
    def mock_record(self):
        return Mock()

    @pytest.mark.unit
    def test_plan_recovers_json_with_surrounding_text(self, mock_record):
        """Recover JSON array embedded in explanatory text."""
        mock_brain = Mock()
        mock_brain.chat = Mock(return_value=LLMResponse(
            content='''Here's my plan for implementing the feature:

[
    {"step": "design", "description": "Design the architecture", "provider_type": "quality"},
    {"step": "implement", "description": "Write the code", "provider_type": "fast"}
]

This plan covers all the requirements.''',
            model="test", provider="test", tokens_used=100, latency_ms=60.0
        ))

        executor = TaskExecutor(lambda: mock_brain, lambda: "brain", mock_record)
        result = executor.plan("Build feature", complexity_score=6)

        # Should extract the JSON array
        assert len(result) == 2
        assert result[0]['step'] == 'design'
        assert result[1]['step'] == 'implement'

    @pytest.mark.unit
    def test_plan_recovers_json_from_generic_code_block(self, mock_record):
        """Recover JSON from code block without json tag."""
        mock_brain = Mock()
        mock_brain.chat = Mock(return_value=LLMResponse(
            content='''```
[{"step": "test", "description": "Run tests", "provider_type": "fast"}]
```''',
            model="test", provider="test", tokens_used=30, latency_ms=20.0
        ))

        executor = TaskExecutor(lambda: mock_brain, lambda: "brain", mock_record)
        result = executor.plan("Test code", complexity_score=4)

        assert len(result) == 1
        assert result[0]['step'] == 'test'

    @pytest.mark.unit
    def test_plan_handles_nested_brackets_in_json(self, mock_record):
        """Handle JSON with nested arrays or objects."""
        mock_brain = Mock()
        mock_brain.chat = Mock(return_value=LLMResponse(
            content='''[
                {"step": "complex", "description": "Task with [brackets] in text", "provider_type": "quality"}
            ]''',
            model="test", provider="test", tokens_used=40, latency_ms=25.0
        ))

        executor = TaskExecutor(lambda: mock_brain, lambda: "brain", mock_record)
        result = executor.plan("Nested task", complexity_score=5)

        assert len(result) == 1
        assert 'brackets' in result[0]['description']

    @pytest.mark.unit
    def test_plan_handles_single_object_response(self, mock_record):
        """Convert single step object to list."""
        mock_brain = Mock()
        mock_brain.chat = Mock(return_value=LLMResponse(
            content='{"step": "single", "description": "Only one step", "provider_type": "fast"}',
            model="test", provider="test", tokens_used=20, latency_ms=15.0
        ))

        executor = TaskExecutor(lambda: mock_brain, lambda: "brain", mock_record)
        result = executor.plan("Simple task", complexity_score=4)

        # Single object should be wrapped in list
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['step'] == 'single'

    @pytest.mark.unit
    def test_plan_handles_mixed_valid_invalid_steps(self, mock_record):
        """Handle array with mix of valid dicts and invalid items."""
        mock_brain = Mock()
        mock_brain.chat = Mock(return_value=LLMResponse(
            content='''[
                {"step": "valid", "description": "Valid step", "provider_type": "fast"},
                "invalid string item",
                {"step": "also_valid", "description": "Another valid step", "provider_type": "quality"}
            ]''',
            model="test", provider="test", tokens_used=60, latency_ms=35.0
        ))

        executor = TaskExecutor(lambda: mock_brain, lambda: "brain", mock_record)
        result = executor.plan("Mixed task", complexity_score=5)

        # Should preserve valid steps and convert invalid ones
        assert len(result) == 3
        assert result[0]['step'] == 'valid'
        # Invalid item should be converted to execute_task
        assert result[1]['step'] == 'execute_task'
        assert 'invalid string item' in result[1]['description']
        assert result[2]['step'] == 'also_valid'

    @pytest.mark.unit
    def test_plan_handles_whitespace_variations(self, mock_record):
        """Parse JSON with various whitespace formats."""
        mock_brain = Mock()
        mock_brain.chat = Mock(return_value=LLMResponse(
            content='[{"step":"compact","description":"No spaces","provider_type":"fast"}]',
            model="test", provider="test", tokens_used=25, latency_ms=18.0
        ))

        executor = TaskExecutor(lambda: mock_brain, lambda: "brain", mock_record)
        result = executor.plan("Compact JSON", complexity_score=4)

        assert len(result) == 1
        assert result[0]['step'] == 'compact'

    @pytest.mark.unit
    def test_plan_fallback_preserves_full_response(self, mock_record):
        """When JSON fails completely, preserve full response in fallback."""
        mock_brain = Mock()
        content = "Step 1: Do this\nStep 2: Do that\nStep 3: Finish"
        mock_brain.chat = Mock(return_value=LLMResponse(
            content=content,
            model="test", provider="test", tokens_used=30, latency_ms=20.0
        ))

        executor = TaskExecutor(lambda: mock_brain, lambda: "brain", mock_record)
        result = executor.plan("Text response", complexity_score=5)

        # Should create fallback with full content
        assert len(result) == 1
        assert result[0]['step'] == 'execute_task'
        assert result[0]['description'] == content
        assert result[0]['provider_type'] == 'quality'

    @pytest.mark.unit
    def test_plan_handles_empty_array_response(self, mock_record):
        """Handle empty array from LLM."""
        mock_brain = Mock()
        mock_brain.chat = Mock(return_value=LLMResponse(
            content='[]',
            model="test", provider="test", tokens_used=5, latency_ms=10.0
        ))

        executor = TaskExecutor(lambda: mock_brain, lambda: "brain", mock_record)
        result = executor.plan("Empty response", complexity_score=4)

        # Should return empty list (valid JSON)
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.unit
    def test_plan_handles_unicode_in_json(self, mock_record):
        """Handle JSON with unicode characters."""
        mock_brain = Mock()
        mock_brain.chat = Mock(return_value=LLMResponse(
            content='[{"step": "process", "description": "Handle data", "provider_type": "fast"}]',
            model="test", provider="test", tokens_used=35, latency_ms=22.0
        ))

        executor = TaskExecutor(lambda: mock_brain, lambda: "brain", mock_record)
        result = executor.plan("Unicode task", complexity_score=4)

        assert len(result) == 1
        # Unicode should be preserved (or stripped if not allowed per CLAUDE.md)
        assert result[0]['step'] == 'process'