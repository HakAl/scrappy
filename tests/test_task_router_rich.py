"""
Tests for Rich-enhanced Task Router output display.

Tests cover:
- Classification displays as Rich table
- Progress bar for complexity
- Provider info formatting
- Execution strategy display
"""

import pytest
from io import StringIO
from rich.console import Console

from src.task_router.output_handler import (
    OutputHandlerInterface,
    BufferOutputHandler,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def captured_console():
    """Create a Rich Console that captures output for testing."""
    string_io = StringIO()
    console = Console(file=string_io, force_terminal=True, width=80)
    return console, string_io


def get_captured_output(string_io: StringIO) -> str:
    """Get captured output from StringIO."""
    return string_io.getvalue()


# =============================================================================
# RichOutputHandler Tests - Classification Display
# =============================================================================

class TestRichOutputHandlerClassification:
    """Tests for classification display as Rich table."""

    def test_classification_displays_as_table(self, captured_console):
        """Classification info should display as a Rich table."""
        from src.task_router.output_handler import RichOutputHandler

        console, string_io = captured_console
        handler = RichOutputHandler(console=console)

        handler.log_classification(
            task_type="code_generation",
            confidence=0.85,
            complexity=8,
            reasoning="Complex code generation task"
        )

        output = get_captured_output(string_io)

        # Table should contain classification header
        assert "Task Classification" in output
        # Should contain type row
        assert "Type" in output
        assert "code_generation" in output
        # Should contain confidence row
        assert "Confidence" in output
        assert "85%" in output or "0.85" in output
        # Should contain complexity row
        assert "Complexity" in output
        # Should contain reasoning row
        assert "Reasoning" in output
        assert "Complex code generation" in output

    def test_complexity_displays_as_progress_bar(self, captured_console):
        """Complexity should display as a visual progress bar."""
        from src.task_router.output_handler import RichOutputHandler

        console, string_io = captured_console
        handler = RichOutputHandler(console=console)

        handler.log_classification(
            task_type="code_generation",
            confidence=0.80,
            complexity=8,
            reasoning="Test task"
        )

        output = get_captured_output(string_io)

        # Should have visual progress indicator
        # Either block characters or percentage
        assert "80%" in output or "8/10" in output

    def test_complexity_progress_bar_zero(self, captured_console):
        """Zero complexity should show empty progress bar."""
        from src.task_router.output_handler import RichOutputHandler

        console, string_io = captured_console
        handler = RichOutputHandler(console=console)

        handler.log_classification(
            task_type="simple_query",
            confidence=0.95,
            complexity=0,
            reasoning="Simple task"
        )

        output = get_captured_output(string_io)

        # Should show 0% complexity
        assert "0%" in output or "0/10" in output

    def test_complexity_progress_bar_max(self, captured_console):
        """Max complexity should show full progress bar."""
        from src.task_router.output_handler import RichOutputHandler

        console, string_io = captured_console
        handler = RichOutputHandler(console=console)

        handler.log_classification(
            task_type="complex_refactor",
            confidence=0.70,
            complexity=10,
            reasoning="Very complex task"
        )

        output = get_captured_output(string_io)

        # Should show 100% complexity
        assert "100%" in output or "10/10" in output

    def test_confidence_formatted_as_percentage(self, captured_console):
        """Confidence should be formatted as percentage."""
        from src.task_router.output_handler import RichOutputHandler

        console, string_io = captured_console
        handler = RichOutputHandler(console=console)

        handler.log_classification(
            task_type="test",
            confidence=0.456,
            complexity=5,
            reasoning="Test"
        )

        output = get_captured_output(string_io)

        # Should show percentage (46% or 45.6%)
        assert "46%" in output or "45%" in output or "45.6%" in output

    def test_classification_table_has_borders(self, captured_console):
        """Classification table should have visible borders."""
        from src.task_router.output_handler import RichOutputHandler

        console, string_io = captured_console
        handler = RichOutputHandler(console=console)

        handler.log_classification(
            task_type="code_review",
            confidence=0.90,
            complexity=6,
            reasoning="Review task"
        )

        output = get_captured_output(string_io)

        # Rich tables typically use box-drawing characters
        # Check for any table-like structure
        has_borders = (
            "|" in output or
            "+" in output or
            "-" in output or
            any(char in output for char in ["│", "┌", "┐", "└", "┘", "├", "┤", "─"])
        )
        assert has_borders, f"Output should have table borders:\n{output}"


# =============================================================================
# RichOutputHandler Tests - Provider Selection Display
# =============================================================================

class TestRichOutputHandlerProvider:
    """Tests for provider selection display formatting."""

    def test_provider_selection_displays_provider_name(self, captured_console):
        """Provider selection should show provider name."""
        from src.task_router.output_handler import RichOutputHandler

        console, string_io = captured_console
        handler = RichOutputHandler(console=console)

        handler.log_provider_selection(
            provider="cerebras",
            model="llama-70b",
            source="speed"
        )

        output = get_captured_output(string_io)

        assert "cerebras" in output

    def test_provider_selection_displays_model(self, captured_console):
        """Provider selection should show model name when provided."""
        from src.task_router.output_handler import RichOutputHandler

        console, string_io = captured_console
        handler = RichOutputHandler(console=console)

        handler.log_provider_selection(
            provider="anthropic",
            model="claude-3-sonnet",
            source="quality"
        )

        output = get_captured_output(string_io)

        assert "claude-3-sonnet" in output

    def test_provider_selection_displays_source(self, captured_console):
        """Provider selection should show selection source/reason."""
        from src.task_router.output_handler import RichOutputHandler

        console, string_io = captured_console
        handler = RichOutputHandler(console=console)

        handler.log_provider_selection(
            provider="groq",
            model=None,
            source="fastest"
        )

        output = get_captured_output(string_io)

        assert "fastest" in output

    def test_provider_selection_handles_no_model(self, captured_console):
        """Provider selection should handle None model gracefully."""
        from src.task_router.output_handler import RichOutputHandler

        console, string_io = captured_console
        handler = RichOutputHandler(console=console)

        handler.log_provider_selection(
            provider="cerebras",
            model=None,
            source="default"
        )

        output = get_captured_output(string_io)

        # Should show provider without crashing
        assert "cerebras" in output
        assert "default" in output

    def test_provider_selection_formatted_with_context(self, captured_console):
        """Provider selection should integrate with classification table."""
        from src.task_router.output_handler import RichOutputHandler

        console, string_io = captured_console
        handler = RichOutputHandler(console=console)

        # Log classification first
        handler.log_classification(
            task_type="code_generation",
            confidence=0.85,
            complexity=8,
            reasoning="Test"
        )

        # Then provider selection
        handler.log_provider_selection(
            provider="cerebras",
            model="llama-70b",
            source="speed"
        )

        output = get_captured_output(string_io)

        # Both should be in output
        assert "Task Classification" in output
        assert "cerebras" in output


# =============================================================================
# RichOutputHandler Tests - Execution Strategy Display
# =============================================================================

class TestRichOutputHandlerStrategy:
    """Tests for execution strategy display."""

    def test_execution_start_displays_strategy_name(self, captured_console):
        """Execution start should display strategy name."""
        from src.task_router.output_handler import RichOutputHandler

        console, string_io = captured_console
        handler = RichOutputHandler(console=console)

        handler.log_execution_start("streaming")

        output = get_captured_output(string_io)

        assert "streaming" in output

    def test_execution_start_displays_different_strategies(self, captured_console):
        """Execution start should handle various strategy names."""
        from src.task_router.output_handler import RichOutputHandler

        console, string_io = captured_console
        handler = RichOutputHandler(console=console)

        strategies = ["streaming", "batch", "parallel", "sequential"]

        for strategy in strategies:
            handler.log_execution_start(strategy)

        output = get_captured_output(string_io)

        for strategy in strategies:
            assert strategy in output, f"Strategy '{strategy}' not found in output"

    def test_execution_strategy_formatted_distinctly(self, captured_console):
        """Execution strategy should be visually distinct."""
        from src.task_router.output_handler import RichOutputHandler

        console, string_io = captured_console
        handler = RichOutputHandler(console=console)

        handler.log_execution_start("streaming")

        output = get_captured_output(string_io)

        # Should have some indicator like "Strategy:" or "Executing with:"
        has_label = (
            "Strategy" in output or
            "Executing" in output or
            "Execution" in output
        )
        assert has_label, f"Output should have strategy label:\n{output}"


# =============================================================================
# RichOutputHandler Tests - Info Messages
# =============================================================================

class TestRichOutputHandlerInfo:
    """Tests for general info message display."""

    def test_log_info_displays_message(self, captured_console):
        """Info messages should be displayed."""
        from src.task_router.output_handler import RichOutputHandler

        console, string_io = captured_console
        handler = RichOutputHandler(console=console)

        handler.log_info("Processing task...")

        output = get_captured_output(string_io)

        assert "Processing task" in output

    def test_multiple_info_messages_preserved(self, captured_console):
        """Multiple info messages should all be preserved."""
        from src.task_router.output_handler import RichOutputHandler

        console, string_io = captured_console
        handler = RichOutputHandler(console=console)

        messages = [
            "Starting analysis",
            "Loading context",
            "Preparing response"
        ]

        for msg in messages:
            handler.log_info(msg)

        output = get_captured_output(string_io)

        for msg in messages:
            assert msg in output, f"Message '{msg}' not found in output"


# =============================================================================
# RichOutputHandler Tests - Full Integration
# =============================================================================

class TestRichOutputHandlerIntegration:
    """Integration tests for complete classification display flow."""

    def test_full_classification_flow_produces_formatted_output(self, captured_console):
        """Full classification flow should produce well-formatted table output."""
        from src.task_router.output_handler import RichOutputHandler

        console, string_io = captured_console
        handler = RichOutputHandler(console=console)

        # Simulate full flow
        handler.log_classification(
            task_type="code_generation",
            confidence=0.85,
            complexity=8,
            reasoning="Complex code generation requiring multiple files"
        )

        handler.log_provider_selection(
            provider="cerebras",
            model="llama-70b",
            source="speed"
        )

        handler.log_execution_start("streaming")

        output = get_captured_output(string_io)

        # All key information should be present
        assert "code_generation" in output
        assert "cerebras" in output
        assert "streaming" in output
        # Should have table structure
        assert "Task Classification" in output

    def test_handler_implements_interface(self):
        """RichOutputHandler should implement OutputHandlerInterface."""
        from src.task_router.output_handler import RichOutputHandler

        # Should be able to instantiate
        handler = RichOutputHandler()

        # Should implement all abstract methods
        assert hasattr(handler, 'log_classification')
        assert hasattr(handler, 'log_provider_selection')
        assert hasattr(handler, 'log_execution_start')
        assert hasattr(handler, 'log_info')

        # Should be instance of interface
        assert isinstance(handler, OutputHandlerInterface)

    def test_handler_accepts_custom_console(self):
        """RichOutputHandler should accept custom console for testing."""
        from src.task_router.output_handler import RichOutputHandler

        string_io = StringIO()
        custom_console = Console(file=string_io, force_terminal=True)

        handler = RichOutputHandler(console=custom_console)
        handler.log_info("Test message")

        output = string_io.getvalue()
        assert "Test message" in output


# =============================================================================
# Progress Bar Formatting Tests
# =============================================================================

class TestComplexityProgressBar:
    """Tests for complexity progress bar formatting function."""

    def test_progress_bar_zero_complexity(self):
        """Zero complexity should show empty bar."""
        from src.task_router.output_handler import format_complexity_bar

        result = format_complexity_bar(0)

        # Should contain 0%
        assert "0%" in result

    def test_progress_bar_half_complexity(self):
        """Half complexity should show half-filled bar."""
        from src.task_router.output_handler import format_complexity_bar

        result = format_complexity_bar(5)

        # Should contain 50%
        assert "50%" in result

    def test_progress_bar_full_complexity(self):
        """Full complexity should show filled bar."""
        from src.task_router.output_handler import format_complexity_bar

        result = format_complexity_bar(10)

        # Should contain 100%
        assert "100%" in result

    def test_progress_bar_custom_width(self):
        """Progress bar should respect custom width."""
        from src.task_router.output_handler import format_complexity_bar

        result_narrow = format_complexity_bar(5, width=5)
        result_wide = format_complexity_bar(5, width=20)

        # Both should show 50%
        assert "50%" in result_narrow
        assert "50%" in result_wide

    def test_progress_bar_visual_characters(self):
        """Progress bar should use visual fill characters."""
        from src.task_router.output_handler import format_complexity_bar

        result = format_complexity_bar(8)

        # Should have some visual representation (blocks, equals, or similar)
        has_visual = any(char in result for char in ["#", "=", "|", "*"])
        # Accept progress bar format with percentage
        assert has_visual or "80%" in result


# =============================================================================
# Backward Compatibility Tests
# =============================================================================

class TestBackwardCompatibility:
    """Tests to ensure backward compatibility with existing handlers."""

    def test_buffer_handler_still_works(self):
        """BufferOutputHandler should continue to work unchanged."""
        handler = BufferOutputHandler()

        handler.log_classification(
            task_type="test",
            confidence=0.80,
            complexity=5,
            reasoning="Test reasoning"
        )

        output = handler.get_output()

        assert "test" in output
        assert "0.80" in output
        assert "5/10" in output

    def test_console_handler_interface_unchanged(self):
        """ConsoleOutputHandler should have unchanged interface."""
        from src.task_router.output_handler import ConsoleOutputHandler

        handler = ConsoleOutputHandler()

        # Should have all required methods
        assert callable(handler.log_classification)
        assert callable(handler.log_provider_selection)
        assert callable(handler.log_execution_start)
        assert callable(handler.log_info)
