"""
Tests for refactored TaskRouter components - demonstrates TDD approach.

These tests are written FIRST to demonstrate expected behavior,
then we refactor the code to make them pass.
"""
import pytest
from unittest.mock import Mock

from scrappy.task_router.classifier import ClassifiedTask, TaskType


class TestIntentClarifier:
    """
    Tests for IntentClarifier - demonstrates injectable interface pattern.

    CRITICAL: These tests demonstrate expected behavior BEFORE implementation.
    We're testing that:
    1. Clarifier can be injected (testable)
    2. Different implementations can be swapped (flexibility)
    3. No direct I/O in business logic (separation of concerns)
    """

    @pytest.mark.unit
    def test_interactive_clarifier_asks_user_and_returns_research(self):
        """Test that interactive clarifier can return RESEARCH when user chooses option 1."""
        # This test demonstrates the INTERFACE we want
        from scrappy.task_router.intent_clarifier import InteractiveClarifier

        task = ClassifiedTask(
            original_input="explain how to create a file",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.5,
            reasoning="Ambiguous intent"
        )

        # Mock the input source (dependency injection!)
        mock_io = Mock()
        mock_io.prompt = Mock(return_value="1")  # User chooses "explain"
        mock_io.output = Mock()
        clarifier = InteractiveClarifier(io=mock_io)

        result = clarifier.clarify(task)

        # Verify behavior
        assert result.task_type == TaskType.RESEARCH
        assert result.confidence == 1.0
        assert "User clarified" in result.reasoning
        # Verify the mock was called (user was prompted)
        mock_io.prompt.assert_called_once()

    @pytest.mark.unit
    def test_interactive_clarifier_asks_user_and_returns_code_generation(self):
        """Test that interactive clarifier can return CODE_GENERATION when user chooses option 2."""
        from scrappy.task_router.intent_clarifier import InteractiveClarifier

        task = ClassifiedTask(
            original_input="create a file",
            task_type=TaskType.RESEARCH,
            confidence=0.6,
            reasoning="Low confidence"
        )

        mock_io = Mock()
        mock_io.prompt = Mock(return_value="2")  # User chooses "do it"
        mock_io.output = Mock()
        clarifier = InteractiveClarifier(io=mock_io)

        result = clarifier.clarify(task)

        assert result.task_type == TaskType.CODE_GENERATION
        assert result.confidence == 1.0
        assert "User clarified" in result.reasoning

    @pytest.mark.unit
    def test_interactive_clarifier_keeps_original_when_user_chooses_3(self):
        """Test that clarifier keeps original classification when user chooses option 3."""
        from scrappy.task_router.intent_clarifier import InteractiveClarifier

        task = ClassifiedTask(
            original_input="something ambiguous",
            task_type=TaskType.RESEARCH,
            confidence=0.55,
            reasoning="Original reasoning"
        )

        mock_io = Mock()
        mock_io.prompt = Mock(return_value="3")  # User chooses "keep current"
        mock_io.output = Mock()
        clarifier = InteractiveClarifier(io=mock_io)

        result = clarifier.clarify(task)

        # Should be unchanged
        assert result.task_type == TaskType.RESEARCH
        assert result.confidence == 0.55
        assert result.reasoning == "Original reasoning"

    @pytest.mark.unit
    def test_interactive_clarifier_handles_eof_error_gracefully(self):
        """Test that clarifier handles EOF (Ctrl+D) by keeping original."""
        from scrappy.task_router.intent_clarifier import InteractiveClarifier

        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.4,
            reasoning="Original"
        )

        mock_io = Mock()
        mock_io.prompt = Mock(side_effect=EOFError)
        mock_io.output = Mock()
        clarifier = InteractiveClarifier(io=mock_io)

        result = clarifier.clarify(task)

        # Should gracefully keep original
        assert result.task_type == TaskType.RESEARCH
        assert result.confidence == 0.4

    @pytest.mark.unit
    def test_interactive_clarifier_handles_keyboard_interrupt(self):
        """Test that clarifier handles Ctrl+C by keeping original."""
        from scrappy.task_router.intent_clarifier import InteractiveClarifier

        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.7,
            reasoning="Original"
        )

        mock_io = Mock()
        mock_io.prompt = Mock(side_effect=KeyboardInterrupt)
        mock_io.output = Mock()
        clarifier = InteractiveClarifier(io=mock_io)

        result = clarifier.clarify(task)

        assert result.task_type == TaskType.CODE_GENERATION
        assert result.confidence == 0.7

    @pytest.mark.unit
    def test_interactive_clarifier_handles_invalid_choice(self):
        """Test that clarifier handles invalid input by keeping original."""
        from scrappy.task_router.intent_clarifier import InteractiveClarifier

        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="Original"
        )

        mock_io = Mock()
        mock_io.prompt = Mock(return_value="99")  # Invalid choice
        mock_io.output = Mock()
        clarifier = InteractiveClarifier(io=mock_io)

        result = clarifier.clarify(task)

        # Should keep original on invalid input
        assert result.task_type == TaskType.RESEARCH

    @pytest.mark.unit
    def test_auto_clarifier_always_escalates_to_code_generation(self):
        """
        Test AutoClarifier that always escalates to CODE_GENERATION.

        This demonstrates that we can swap implementations easily.
        Useful for CI/CD where we don't want interactive prompts.
        """
        from scrappy.task_router.intent_clarifier import AutoClarifier

        task = ClassifiedTask(
            original_input="create something",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="Low confidence"
        )

        clarifier = AutoClarifier(default_action="escalate")
        result = clarifier.clarify(task)

        # Auto-escalates to CODE_GENERATION when ambiguous
        assert result.task_type == TaskType.CODE_GENERATION
        assert result.confidence == 0.5  # Keeps original confidence
        assert "Auto-escalated" in result.reasoning

    @pytest.mark.unit
    def test_auto_clarifier_keeps_original_when_configured(self):
        """Test AutoClarifier can be configured to keep original."""
        from scrappy.task_router.intent_clarifier import AutoClarifier

        task = ClassifiedTask(
            original_input="something",
            task_type=TaskType.RESEARCH,
            confidence=0.5,
            reasoning="Original"
        )

        clarifier = AutoClarifier(default_action="keep")
        result = clarifier.clarify(task)

        assert result.task_type == TaskType.RESEARCH
        assert result.confidence == 0.5

    @pytest.mark.unit
    def test_null_clarifier_never_modifies_task(self):
        """
        Test NullClarifier that never modifies tasks.

        Useful when clarification is disabled entirely.
        """
        from scrappy.task_router.intent_clarifier import NullClarifier

        task = ClassifiedTask(
            original_input="test",
            task_type=TaskType.CODE_GENERATION,
            confidence=0.3,
            reasoning="Very low confidence"
        )

        clarifier = NullClarifier()
        result = clarifier.clarify(task)

        # Should be completely unchanged
        assert result is task  # Same object reference
        assert result.task_type == TaskType.CODE_GENERATION
        assert result.confidence == 0.3


class TestOutputHandler:
    """
    Tests for OutputHandler - demonstrates injectable logging/output.

    CRITICAL: Demonstrates separation of business logic from I/O.
    We're testing that:
    1. Output can be captured/redirected (testable)
    2. Different outputs can be swapped (console, file, null)
    3. No print() in business logic
    """

    @pytest.mark.unit
    def test_console_output_handler_prints_to_stdout(self):
        """Test that ConsoleOutputHandler writes to provided IO."""
        from scrappy.task_router.output_handler import ConsoleOutputHandler
        from tests.helpers import MockIO

        mock_io = MockIO()
        handler = ConsoleOutputHandler(io=mock_io)
        handler.log_classification(
            task_type="RESEARCH",
            confidence=0.85,
            complexity=3,
            reasoning="Test reasoning"
        )

        output = mock_io.get_output()
        assert "RESEARCH" in output
        assert "0.85" in output
        assert "Test reasoning" in output

    @pytest.mark.unit
    def test_console_output_handler_logs_provider_selection(self):
        """Test that provider selection is logged."""
        from scrappy.task_router.output_handler import ConsoleOutputHandler
        from tests.helpers import MockIO

        mock_io = MockIO()
        handler = ConsoleOutputHandler(io=mock_io)
        handler.log_provider_selection(
            provider="cerebras",
            model="llama-3.3-70b",
            source="hint"
        )

        output = mock_io.get_output()
        assert "cerebras" in output
        assert "llama-3.3-70b" in output

    @pytest.mark.unit
    def test_console_output_handler_logs_execution_start(self):
        """Test that execution start is logged."""
        from scrappy.task_router.output_handler import ConsoleOutputHandler
        from tests.helpers import MockIO

        mock_io = MockIO()
        handler = ConsoleOutputHandler(io=mock_io)
        handler.log_execution_start(strategy_name="DirectExecutor")

        output = mock_io.get_output()
        assert "DirectExecutor" in output

    @pytest.mark.unit
    def test_buffer_output_handler_captures_output(self):
        """
        Test BufferOutputHandler captures output for testing.

        This is crucial for testing - we can verify what would be printed
        without actually printing to console.
        """
        from scrappy.task_router.output_handler import BufferOutputHandler

        handler = BufferOutputHandler()
        handler.log_classification(
            task_type="CODE_GENERATION",
            confidence=0.9,
            complexity=7,
            reasoning="Complex task"
        )
        handler.log_provider_selection(
            provider="groq",
            model=None,
            source="override"
        )

        # Can retrieve and verify all output
        output = handler.get_output()
        assert "CODE_GENERATION" in output
        assert "0.9" in output
        assert "groq" in output
        assert "override" in output

    @pytest.mark.unit
    def test_buffer_output_handler_can_be_cleared(self):
        """Test that buffer can be cleared."""
        from scrappy.task_router.output_handler import BufferOutputHandler

        handler = BufferOutputHandler()
        handler.log_classification("RESEARCH", 0.8, 2, "test")

        assert len(handler.get_output()) > 0

        handler.clear()
        assert handler.get_output() == ""

    @pytest.mark.unit
    def test_null_output_handler_produces_no_output(self, capsys):
        """
        Test NullOutputHandler produces no output.

        Useful for silent mode or when output is disabled.
        """
        from scrappy.task_router.output_handler import NullOutputHandler

        handler = NullOutputHandler()
        handler.log_classification("RESEARCH", 0.8, 2, "test")
        handler.log_provider_selection("cerebras", "model", "hint")
        handler.log_execution_start("DirectExecutor")

        captured = capsys.readouterr()
        assert captured.out == ""


class TestInputValidator:
    """
    Tests for input validation at boundaries.

    CRITICAL: Demonstrates defensive programming.
    We're testing that:
    1. Invalid inputs are caught early
    2. Meaningful error messages are provided
    3. Edge cases are handled gracefully
    """

    @pytest.mark.unit
    def test_validate_user_input_rejects_none(self):
        """Test that None input is rejected."""
        from scrappy.task_router.validator import InputValidator

        validator = InputValidator()

        is_valid, error = validator.validate_user_input(None)

        assert is_valid is False
        assert "cannot be None" in error

    @pytest.mark.unit
    def test_validate_user_input_rejects_empty_string(self):
        """Test that empty string is rejected."""
        from scrappy.task_router.validator import InputValidator

        validator = InputValidator()

        is_valid, error = validator.validate_user_input("")

        assert is_valid is False
        assert "cannot be empty" in error

    @pytest.mark.unit
    def test_validate_user_input_rejects_whitespace_only(self):
        """Test that whitespace-only input is rejected."""
        from scrappy.task_router.validator import InputValidator

        validator = InputValidator()

        is_valid, error = validator.validate_user_input("   \t\n  ")

        assert is_valid is False
        assert "cannot be empty" in error

    @pytest.mark.unit
    def test_validate_user_input_accepts_valid_input(self):
        """Test that valid input is accepted."""
        from scrappy.task_router.validator import InputValidator

        validator = InputValidator()

        is_valid, error = validator.validate_user_input("create a file")

        assert is_valid is True
        assert error is None

    @pytest.mark.unit
    def test_validate_user_input_rejects_extremely_long_input(self):
        """Test that extremely long input is rejected (DoS protection)."""
        from scrappy.task_router.validator import InputValidator

        validator = InputValidator(max_length=1000)

        very_long_input = "a" * 10000
        is_valid, error = validator.validate_user_input(very_long_input)

        assert is_valid is False
        assert "too long" in error

    @pytest.mark.unit
    def test_validate_user_input_accepts_long_but_valid_input(self):
        """Test that long but valid input is accepted."""
        from scrappy.task_router.validator import InputValidator

        validator = InputValidator(max_length=1000)

        long_input = "a" * 500
        is_valid, error = validator.validate_user_input(long_input)

        assert is_valid is True
        assert error is None

    @pytest.mark.unit
    def test_validate_confidence_rejects_negative(self):
        """Test that negative confidence is rejected."""
        from scrappy.task_router.validator import InputValidator

        validator = InputValidator()

        is_valid, error = validator.validate_confidence(-0.1)

        assert is_valid is False
        assert "between 0.0 and 1.0" in error

    @pytest.mark.unit
    def test_validate_confidence_rejects_greater_than_one(self):
        """Test that confidence > 1.0 is rejected."""
        from scrappy.task_router.validator import InputValidator

        validator = InputValidator()

        is_valid, error = validator.validate_confidence(1.5)

        assert is_valid is False
        assert "between 0.0 and 1.0" in error

    @pytest.mark.unit
    def test_validate_confidence_accepts_valid_values(self):
        """Test that valid confidence values are accepted."""
        from scrappy.task_router.validator import InputValidator

        validator = InputValidator()

        for confidence in [0.0, 0.5, 1.0, 0.123, 0.999]:
            is_valid, error = validator.validate_confidence(confidence)
            assert is_valid is True
            assert error is None

    @pytest.mark.unit
    def test_validate_task_type_rejects_none(self):
        """Test that None task type is rejected."""
        from scrappy.task_router.validator import InputValidator

        validator = InputValidator()

        is_valid, error = validator.validate_task_type(None)

        assert is_valid is False
        assert "cannot be None" in error

    @pytest.mark.unit
    def test_validate_task_type_accepts_all_enum_values(self):
        """Test that all TaskType enum values are accepted."""
        from scrappy.task_router.validator import InputValidator

        validator = InputValidator()

        for task_type in TaskType:
            is_valid, error = validator.validate_task_type(task_type)
            assert is_valid is True
            assert error is None
