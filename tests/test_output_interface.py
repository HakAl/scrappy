"""
Tests for generic output interface abstraction.

Tests written FIRST to define expected behavior of library-agnostic output layer.
Implementation library (click, rich, or anything else) should be completely hidden.
"""

import pytest


class TestOutputForTesting:
    """Tests for test-mode output that captures instead of printing."""

    @pytest.mark.unit
    def test_test_output_captures_print(self):
        """Test that TestOutput captures print calls."""
        from scrappy.cli.output import TestOutput
        output = TestOutput()

        output.print("Test message")

        assert "Test message" in output.get_output()

    @pytest.mark.unit
    def test_test_output_captures_styled_print(self):
        """Test that TestOutput captures styled print calls."""
        from scrappy.cli.output import TestOutput
        output = TestOutput()

        output.print("Error!", color="red", bold=True)

        assert "Error!" in output.get_output()

    @pytest.mark.unit
    def test_test_output_tracks_style_info(self):
        """Test that TestOutput records style parameters for verification."""
        from scrappy.cli.output import TestOutput
        output = TestOutput()

        output.print("Warning", color="yellow", bold=True)

        styles = output.get_styled_calls()
        assert len(styles) == 1
        assert styles[0]['text'] == "Warning"
        assert styles[0]['color'] == "yellow"
        assert styles[0]['bold'] == True

    @pytest.mark.unit
    def test_test_output_style_returns_text(self):
        """Test that style() returns unstyled text in test mode."""
        from scrappy.cli.output import TestOutput
        output = TestOutput()

        result = output.style("text", color="green")

        assert result == "text"

    @pytest.mark.unit
    def test_test_output_preset_inputs(self):
        """Test that TestOutput can provide preset inputs for testing."""
        from scrappy.cli.output import TestOutput
        output = TestOutput(inputs=["user input"])

        result = output.prompt("Enter value: ")

        assert result == "user input"

    @pytest.mark.unit
    def test_test_output_preset_confirmations(self):
        """Test that TestOutput can provide preset confirmations."""
        from scrappy.cli.output import TestOutput
        output = TestOutput(confirmations=[True, False])

        result1 = output.confirm("Continue?")
        result2 = output.confirm("Are you sure?")

        assert result1 == True
        assert result2 == False

    @pytest.mark.unit
    def test_test_output_clear(self):
        """Test that TestOutput can clear captured output."""
        from scrappy.cli.output import TestOutput
        output = TestOutput()

        output.print("Some output")
        output.clear()

        assert output.get_output() == ""


class TestOutputUsage:
    """Tests demonstrating how code should use the output interface."""

    @pytest.mark.unit
    def test_function_uses_output_without_knowing_library(self):
        """Test that functions use Output without knowing implementation."""
        from scrappy.cli.output import TestOutput

        # Example function - never imports click or rich
        def display_message(output, message: str, is_error: bool = False):
            """Function that uses output abstraction."""
            if is_error:
                output.print(message, color="red", bold=True)
            else:
                output.print(message)

        # Test it
        test_output = TestOutput()
        display_message(test_output, "Success!", is_error=False)
        display_message(test_output, "Error occurred", is_error=True)

        captured = test_output.get_output()
        assert "Success!" in captured
        assert "Error occurred" in captured

        # Verify styling was requested
        styles = test_output.get_styled_calls()
        error_style = [s for s in styles if s['text'] == "Error occurred"][0]
        assert error_style['color'] == "red"
        assert error_style['bold'] == True

    @pytest.mark.unit
    def test_formatter_uses_output_abstraction(self):
        """Test that formatters use generic output interface."""
        from scrappy.cli.output import TestOutput

        # Example formatter - no library knowledge
        def format_git_diff(output, diff_line: str) -> str:
            """Format git diff line using generic output abstraction."""
            if diff_line.startswith('+'):
                return output.style(diff_line, color="green")
            elif diff_line.startswith('-'):
                return output.style(diff_line, color="red")
            else:
                return diff_line

        # Test it
        test_output = TestOutput()

        added = format_git_diff(test_output, "+ new line")
        removed = format_git_diff(test_output, "- old line")
        context = format_git_diff(test_output, "  context")

        # In test mode, returns unstyled text
        assert added == "+ new line"
        assert removed == "- old line"
        assert context == "  context"

    @pytest.mark.unit
    def test_tool_receives_output_instance(self):
        """Test that tools receive output instance, not library."""
        from scrappy.cli.output import TestOutput

        # Example tool - completely library-agnostic
        class FileLister:
            pass
            def __init__(self, output):
                self.output = output

            def list_directory(self, path: str):
                """List directory using output abstraction."""
                self.output.print(f"Contents of {path}:", bold=True)
                # Simulate file listing
                files = ["file1.py", "file2.js", "README.md"]
                for f in files:
                    if f.endswith('.py'):
                        styled = self.output.style(f, color="green")
                    elif f.endswith('.js'):
                        styled = self.output.style(f, color="yellow")
                    else:
                        styled = f
                    self.output.print(f"  {styled}")

        # Test it
        test_output = TestOutput()
        lister = FileLister(test_output)
        lister.list_directory("/project")

        output = test_output.get_output()
        assert "Contents of /project:" in output
        assert "file1.py" in output
        assert "file2.js" in output


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing CLIIOProtocol."""

    @pytest.mark.unit
    def test_echo_method_exists(self):
        """Test that echo() method exists for compatibility."""
        from scrappy.cli.output import TestOutput

        output = TestOutput()
        output.echo("test")

        assert "test" in output.get_output()

    @pytest.mark.unit
    def test_secho_method_exists(self):
        """Test that secho() method exists for compatibility."""
        from scrappy.cli.output import TestOutput

        output = TestOutput()
        output.secho("test", fg="green")

        assert "test" in output.get_output()


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.unit
    def test_output_style_with_no_color(self):
        """Test style with no color specified."""
        from scrappy.cli.output import TestOutput

        output = TestOutput()
        result = output.style("text", color=None)

        assert result == "text"

    @pytest.mark.unit
    def test_output_prompt_with_default(self):
        """Test prompt with default value when no input."""
        from scrappy.cli.output import TestOutput

        output = TestOutput(inputs=[])
        result = output.prompt("Enter: ", default="default_value")

        assert result == "default_value"

    @pytest.mark.unit
    def test_output_confirm_with_default(self):
        """Test confirm with default value when no confirmation."""
        from scrappy.cli.output import TestOutput

        output = TestOutput(confirmations=[])
        result = output.confirm("Continue?", default=True)

        assert result == True
