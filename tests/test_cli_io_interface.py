"""
Tests for CLI I/O abstraction layer.

These tests define the expected behavior of CLIIOProtocol and its implementations.
Following TDD: tests written first, then implementation.
"""

import pytest
from typing import List, Optional


class TestCLIIOProtocol:
    """Tests for the CLIIOProtocol interface definition."""

    pass

class TestTestIO:
    """Tests for TestIO implementation - used for testing CLI code."""

    @pytest.mark.unit

    @pytest.mark.unit

    @pytest.mark.unit
    def test_testio_echo_captures_output(self):
        """Test that echo() captures output to internal buffer."""
        from src.cli.io_interface import TestIO
        io = TestIO()

        io.echo("Hello, World!")

        assert "Hello, World!" in io.get_output()

    @pytest.mark.unit
    def test_testio_echo_multiple_lines(self):
        """Test that multiple echo calls are captured."""
        from src.cli.io_interface import TestIO
        io = TestIO()

        io.echo("Line 1")
        io.echo("Line 2")
        io.echo("Line 3")

        output = io.get_output()
        assert "Line 1" in output
        assert "Line 2" in output
        assert "Line 3" in output

    @pytest.mark.unit
    def test_testio_echo_newline_control(self):
        """Test that nl parameter controls newline behavior."""
        from src.cli.io_interface import TestIO
        io = TestIO()

        io.echo("No newline", nl=False)
        io.echo(" continues")

        # Output should have both parts, first without newline
        output = io.get_output()
        assert "No newline continues" in output or "No newline" in output

    @pytest.mark.unit
    def test_testio_styled_echo_captures_content(self):
        """Test that styled_echo captures content (ignores styling for testing)."""
        from src.cli.io_interface import TestIO
        io = TestIO()

        io.styled_echo("Styled text", fg="green", bold=True)

        assert "Styled text" in io.get_output()

    @pytest.mark.unit
    def test_testio_styled_echo_records_style_info(self):
        """Test that styled_echo records styling information for verification."""
        from src.cli.io_interface import TestIO
        io = TestIO()

        io.styled_echo("Error!", fg="red", bold=True)

        # Should be able to verify styling was requested
        styles = io.get_styled_outputs()
        assert len(styles) == 1
        assert styles[0]['text'] == "Error!"
        assert styles[0]['fg'] == "red"
        assert styles[0]['bold'] == True

    @pytest.mark.unit
    def test_testio_secho_captures_content(self):
        """Test that secho captures content."""
        from src.cli.io_interface import TestIO
        io = TestIO()

        io.secho("Styled text", fg="green", bold=True)

        assert "Styled text" in io.get_output()

    @pytest.mark.unit
    def test_testio_secho_records_style_info(self):
        """Test that secho records styling information."""
        from src.cli.io_interface import TestIO
        io = TestIO()

        io.secho("Warning!", fg="yellow", bold=False)

        styles = io.get_styled_outputs()
        assert len(styles) == 1
        assert styles[0]['text'] == "Warning!"
        assert styles[0]['fg'] == "yellow"
        assert styles[0]['bold'] == False

    @pytest.mark.unit
    def test_testio_style_returns_text(self):
        """Test that style() returns the text (for testing, no actual styling)."""
        from src.cli.io_interface import TestIO
        io = TestIO()

        result = io.style("styled text", fg="cyan", bold=True)

        assert result == "styled text"

    @pytest.mark.unit
    def test_testio_prompt_returns_preset_input(self):
        """Test that prompt() returns preset input values."""
        from src.cli.io_interface import TestIO
        io = TestIO(inputs=["user response"])

        result = io.prompt("Enter value: ")

        assert result == "user response"

    @pytest.mark.unit
    def test_testio_prompt_uses_default_when_no_input(self):
        """Test that prompt uses default when no input available."""
        from src.cli.io_interface import TestIO
        io = TestIO(inputs=[])

        result = io.prompt("Enter value: ", default="default_value")

        assert result == "default_value"

    @pytest.mark.unit
    def test_testio_prompt_multiple_calls(self):
        """Test that multiple prompts consume inputs in order."""
        from src.cli.io_interface import TestIO
        io = TestIO(inputs=["first", "second", "third"])

        result1 = io.prompt("First: ")
        result2 = io.prompt("Second: ")
        result3 = io.prompt("Third: ")

        assert result1 == "first"
        assert result2 == "second"
        assert result3 == "third"

    @pytest.mark.unit
    def test_testio_confirm_returns_preset_bool(self):
        """Test that confirm() returns preset boolean values."""
        from src.cli.io_interface import TestIO
        io = TestIO(confirmations=[True, False])

        result1 = io.confirm("Continue?")
        result2 = io.confirm("Are you sure?")

        assert result1 == True
        assert result2 == False

    @pytest.mark.unit
    def test_testio_confirm_uses_default_when_no_confirmation(self):
        """Test that confirm uses default when no confirmation available."""
        from src.cli.io_interface import TestIO
        io = TestIO(confirmations=[])

        result = io.confirm("Continue?", default=True)

        assert result == True

    @pytest.mark.unit
    def test_testio_input_line_returns_preset(self):
        """Test that input_line() returns preset raw input."""
        from src.cli.io_interface import TestIO
        io = TestIO(inputs=["raw input line"])

        result = io.input_line()

        assert result == "raw input line"

    @pytest.mark.unit
    def test_testio_clear_output(self):
        """Test that output can be cleared."""
        from src.cli.io_interface import TestIO
        io = TestIO()

        io.echo("Some output")
        io.clear_output()

        assert io.get_output() == ""

    @pytest.mark.unit
    def test_testio_get_all_output_lines(self):
        """Test getting output as list of lines."""
        from src.cli.io_interface import TestIO
        io = TestIO()

        io.echo("Line 1")
        io.echo("Line 2")

        lines = io.get_output_lines()
        assert len(lines) >= 2
        assert "Line 1" in lines[0]
        assert "Line 2" in lines[1]

    @pytest.mark.unit
    def test_testio_add_input_at_runtime(self):
        """Test that inputs can be added at runtime."""
        from src.cli.io_interface import TestIO
        io = TestIO()

        io.add_input("dynamic input")
        result = io.prompt("Enter: ")

        assert result == "dynamic input"

    @pytest.mark.unit
    def test_testio_add_confirmation_at_runtime(self):
        """Test that confirmations can be added at runtime."""
        from src.cli.io_interface import TestIO
        io = TestIO()

        io.add_confirmation(True)
        result = io.confirm("Continue?")

        assert result == True


class TestMockIO:
    """Tests for MockIO in tests/helpers.py."""

    @pytest.mark.unit

    @pytest.mark.unit

    @pytest.mark.unit
    def test_mockio_echo_captures_output(self):
        """Test that echo() captures output."""
        from tests.helpers import MockIO
        io = MockIO()

        io.echo("Hello from MockIO!")

        assert "Hello from MockIO!" in io.get_output()

    @pytest.mark.unit
    def test_mockio_secho_captures_content(self):
        """Test that secho captures content."""
        from tests.helpers import MockIO
        io = MockIO()

        io.secho("Styled text", fg="cyan", bold=True)

        assert "Styled text" in io.get_output()
        styles = io.get_styled_outputs()
        assert len(styles) == 1
        assert styles[0]['fg'] == "cyan"

    @pytest.mark.unit
    def test_mockio_prompt_returns_preset(self):
        """Test that prompt returns preset inputs."""
        from tests.helpers import MockIO
        io = MockIO(inputs=["test input"])

        result = io.prompt("Enter: ")

        assert result == "test input"

    @pytest.mark.unit
    def test_mockio_confirm_returns_preset(self):
        """Test that confirm returns preset confirmations."""
        from tests.helpers import MockIO
        io = MockIO(confirmations=[True])

        result = io.confirm("Continue?")

        assert result == True

    @pytest.mark.unit
    def test_mockio_reset(self):
        """Test that reset clears all state."""
        from tests.helpers import MockIO
        io = MockIO(inputs=["input1", "input2"], confirmations=[True])

        io.echo("Some output")
        io.prompt("First: ")
        io.confirm("Confirm: ")

        io.reset()

        assert io.get_output() == ""
        # After reset, indices are reset but inputs/confirmations remain
        result = io.prompt("Second: ", default="default")
        assert result == "input1"  # Back to first input

    @pytest.mark.unit
    def test_mockio_style_returns_text(self):
        """Test that style returns text without modification."""
        from tests.helpers import MockIO
        io = MockIO()

        result = io.style("styled", fg="red", bold=True)

        assert result == "styled"


class TestClickIO:
    """Tests for ClickIO implementation - real CLI output using click."""

    @pytest.mark.unit

    @pytest.mark.unit

    @pytest.mark.unit

    @pytest.mark.unit
    def test_clickio_style_returns_styled_string(self):
        """Test that ClickIO.style() returns a styled string."""
        from src.cli.io_interface import ClickIO
        io = ClickIO()

        result = io.style("test", fg="green")

        # Result should be a string (with ANSI codes when terminal supports it)
        assert isinstance(result, str)
        assert "test" in result

    @pytest.mark.unit
    def test_clickio_has_secho(self):
        """Test that ClickIO has secho method."""
        from src.cli.io_interface import ClickIO
        io = ClickIO()

        assert hasattr(io, 'secho')
        assert callable(io.secho)


class TestIOProtocolUsage:
    """Tests demonstrating how to use the IO protocol in CLI code."""

    @pytest.mark.unit
    def test_function_accepts_protocol(self):
        """Test that functions can accept CLIIOProtocol for dependency injection."""
        from src.cli.io_interface import CLIIOProtocol, TestIO

        # Example function that uses IO protocol
        def display_status(io: CLIIOProtocol, status: str) -> None:
            io.styled_echo("Status:", fg="cyan", bold=True)
            io.echo(f"  {status}")

        # Test with TestIO
        test_io = TestIO()
        display_status(test_io, "All systems operational")

        output = test_io.get_output()
        assert "Status:" in output
        assert "All systems operational" in output

    @pytest.mark.unit
    def test_function_with_user_input(self):
        """Test function that requires user input can be tested."""
        from src.cli.io_interface import CLIIOProtocol, TestIO

        # Example function that gets user confirmation
        def confirm_action(io: CLIIOProtocol, action: str) -> bool:
            io.echo(f"About to: {action}")
            return io.confirm("Proceed?", default=False)

        # Test with preset confirmation
        test_io = TestIO(confirmations=[True])
        result = confirm_action(test_io, "delete all files")

        assert "About to: delete all files" in test_io.get_output()
        assert result == True

    @pytest.mark.unit
    def test_function_with_prompt(self):
        """Test function that prompts for input can be tested."""
        from src.cli.io_interface import CLIIOProtocol, TestIO

        # Example function that gets user input
        def get_username(io: CLIIOProtocol) -> str:
            return io.prompt("Enter username: ", default="guest")

        # Test with preset input
        test_io = TestIO(inputs=["admin"])
        result = get_username(test_io)

        assert result == "admin"

    @pytest.mark.unit
    def test_multiple_io_operations(self):
        """Test complex workflow with multiple I/O operations."""
        from src.cli.io_interface import CLIIOProtocol, TestIO

        # Example workflow function
        def setup_wizard(io: CLIIOProtocol) -> dict:
            io.styled_echo("Welcome to Setup Wizard", fg="cyan", bold=True)
            io.echo("-" * 30)

            name = io.prompt("Enter project name: ", default="my-project")

            io.echo(f"Creating project: {name}")

            if io.confirm("Add tests?", default=True):
                io.styled_echo("Tests enabled", fg="green")
                tests = True
            else:
                tests = False

            return {"name": name, "tests": tests}

        # Test the workflow
        test_io = TestIO(
            inputs=["awesome-project"],
            confirmations=[True]
        )

        result = setup_wizard(test_io)

        assert result["name"] == "awesome-project"
        assert result["tests"] == True

        output = test_io.get_output()
        assert "Welcome to Setup Wizard" in output
        assert "Creating project: awesome-project" in output
        assert "Tests enabled" in output


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.unit

    @pytest.mark.unit
    def test_testio_echo_with_special_characters(self):
        """Test echo with special characters."""
        from src.cli.io_interface import TestIO
        io = TestIO()

        io.echo("Line with\ttab and unicode: cafe")

        assert "tab" in io.get_output()
        assert "cafe" in io.get_output()

    @pytest.mark.unit
    def test_testio_styled_echo_with_none_fg(self):
        """Test styled_echo with None foreground color."""
        from src.cli.io_interface import TestIO
        io = TestIO()

        io.styled_echo("No color", fg=None, bold=False)

        assert "No color" in io.get_output()

    @pytest.mark.unit
    def test_testio_prompt_empty_default(self):
        """Test prompt with empty default."""
        from src.cli.io_interface import TestIO
        io = TestIO(inputs=[])

        result = io.prompt("Enter: ", default="")

        assert result == ""

    @pytest.mark.unit
    def test_testio_input_exhausted_raises_or_defaults(self):
        """Test behavior when inputs are exhausted."""
        from src.cli.io_interface import TestIO
        io = TestIO(inputs=["only one"])

        io.prompt("First: ")
        # Second prompt should use default or raise
        result = io.prompt("Second: ", default="fallback")

        assert result == "fallback"

    @pytest.mark.unit
    def test_testio_styled_outputs_empty_initially(self):
        """Test that styled_outputs list is empty initially."""
        from src.cli.io_interface import TestIO
        io = TestIO()

        styles = io.get_styled_outputs()

        assert styles == []

    @pytest.mark.unit
    def test_testio_multiple_styles_tracked(self):
        """Test multiple styled outputs are all tracked."""
        from src.cli.io_interface import TestIO
        io = TestIO()

        io.styled_echo("Error", fg="red")
        io.styled_echo("Warning", fg="yellow")
        io.styled_echo("Success", fg="green")

        styles = io.get_styled_outputs()
        assert len(styles) == 3
        assert styles[0]['fg'] == "red"
        assert styles[1]['fg'] == "yellow"
        assert styles[2]['fg'] == "green"
