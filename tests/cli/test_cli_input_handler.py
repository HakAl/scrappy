"""
Tests for CLI input handler module.

TDD: Tests written first for the input_handler.py module which handles
multiline input reading and command parsing.
"""

import pytest
from tests.helpers import MockIO


class TestInputHandler:
    """Tests for InputHandler class."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.input_handler import InputHandler
        self.InputHandler = InputHandler

    # =========================================================================
    # Multiline Input Tests
    # =========================================================================

    def test_read_multiline_input_single_line(self):
        """Should read single line input when no continuation."""
        io = MockIO(inputs=["hello world", ""])
        handler = self.InputHandler(io)

        result = handler.read_multiline_input()

        assert result == "hello world"

    def test_read_multiline_input_with_continuation(self):
        """Should read multiple lines when continuation marker used."""
        io = MockIO(inputs=["line one\\", "line two\\", "line three", ""])
        handler = self.InputHandler(io)

        result = handler.read_multiline_input()

        assert "line one" in result
        assert "line two" in result
        assert "line three" in result

    def test_read_multiline_input_blank_line_terminates(self):
        """Should terminate on blank line."""
        io = MockIO(inputs=["first", "second", ""])
        handler = self.InputHandler(io)

        result = handler.read_multiline_input()

        # Should contain first line but not more after blank
        assert "first" in result

    def test_read_multiline_input_end_keyword_terminates(self):
        """Should terminate on 'END' keyword."""
        io = MockIO(inputs=["line 1", "END"])
        handler = self.InputHandler(io)

        result = handler.read_multiline_input()

        assert "line 1" in result
        assert "END" not in result

    def test_read_multiline_input_end_case_insensitive(self):
        """END keyword should be case insensitive."""
        io = MockIO(inputs=["line 1", "end"])
        handler = self.InputHandler(io)

        result = handler.read_multiline_input()

        assert "line 1" in result
        assert "end" not in result

    def test_read_multiline_input_preserves_continuation_marker(self):
        """Should preserve continuation marker in lines (it's just text)."""
        io = MockIO(inputs=["continue\\", ""])
        handler = self.InputHandler(io)

        result = handler.read_multiline_input()

        # read_multiline_input reads until blank line, preserving content as-is
        assert result == "continue\\"
        assert "\\" in result

    def test_read_multiline_input_returns_empty_on_exception(self):
        """Should return empty string on exception."""
        io = MockIO(inputs=[])  # Empty inputs will cause exception
        handler = self.InputHandler(io)

        # Mock to raise exception
        io.prompt = lambda *args, **kwargs: (_ for _ in ()).throw(Exception("test"))

        result = handler.read_multiline_input()

        assert result == ""

    def test_read_multiline_input_shows_instruction(self):
        """Should display multiline input instruction."""
        io = MockIO(inputs=["test", ""])
        handler = self.InputHandler(io)

        handler.read_multiline_input()

        output = io.get_output()
        assert "multiline" in output.lower()

    def test_read_multiline_input_custom_prompt(self):
        """Should accept custom prompt text."""
        io = MockIO(inputs=["data", ""])
        handler = self.InputHandler(io)

        result = handler.read_multiline_input(prompt_text=">>> ")

        assert result == "data"

    def test_read_multiline_input_preserves_newlines(self):
        """Should preserve newlines between lines."""
        io = MockIO(inputs=["line1\\", "line2", ""])
        handler = self.InputHandler(io)

        result = handler.read_multiline_input()

        assert "\n" in result

    # =========================================================================
    # Command Parsing Tests
    # =========================================================================

    def test_parse_command_extracts_command_name(self):
        """Should extract command name from input."""
        io = MockIO()
        handler = self.InputHandler(io)

        cmd, args = handler.parse_command("/help")

        assert cmd == "/help"
        assert args == ""

    def test_parse_command_extracts_args(self):
        """Should extract args from input."""
        io = MockIO()
        handler = self.InputHandler(io)

        cmd, args = handler.parse_command("/plan create a new feature")

        assert cmd == "/plan"
        assert args == "create a new feature"

    def test_parse_command_lowercase_command(self):
        """Should lowercase the command name."""
        io = MockIO()
        handler = self.InputHandler(io)

        cmd, args = handler.parse_command("/HELP")

        assert cmd == "/help"

    def test_parse_command_preserves_args_case(self):
        """Should preserve case in args."""
        io = MockIO()
        handler = self.InputHandler(io)

        cmd, args = handler.parse_command("/agent Build Feature X")

        assert args == "Build Feature X"

    def test_parse_command_handles_no_args(self):
        """Should handle commands with no arguments."""
        io = MockIO()
        handler = self.InputHandler(io)

        cmd, args = handler.parse_command("/status")

        assert cmd == "/status"
        assert args == ""

    def test_parse_command_handles_extra_whitespace(self):
        """Should handle extra whitespace in input."""
        io = MockIO()
        handler = self.InputHandler(io)

        cmd, args = handler.parse_command("/plan   lots of spaces")

        assert cmd == "/plan"
        # Args may have leading space stripped
        assert "lots of spaces" in args

    def test_parse_command_empty_string(self):
        """Should handle empty string input."""
        io = MockIO()
        handler = self.InputHandler(io)

        cmd, args = handler.parse_command("")

        assert cmd == ""
        assert args == ""

    # =========================================================================
    # Is Command Detection Tests
    # =========================================================================

    def test_is_command_detects_slash_commands(self):
        """Should detect strings starting with / as commands."""
        io = MockIO()
        handler = self.InputHandler(io)

        assert handler.is_command("/help") is True
        assert handler.is_command("/plan task") is True
        assert handler.is_command("/quit") is True

    def test_is_command_rejects_non_commands(self):
        """Should reject strings not starting with /."""
        io = MockIO()
        handler = self.InputHandler(io)

        assert handler.is_command("hello") is False
        assert handler.is_command("help me") is False
        assert handler.is_command(" /help") is False  # Leading space

    def test_is_command_handles_empty_string(self):
        """Should return False for empty string."""
        io = MockIO()
        handler = self.InputHandler(io)

        assert handler.is_command("") is False

    # =========================================================================
    # Interactive Input Reading Tests
    # =========================================================================

    def test_read_interactive_input_single_line(self):
        """Should handle single line input (no continuation)."""
        io = MockIO(inputs=["user input"])
        handler = self.InputHandler(io)

        result = handler.read_interactive_input()

        assert result == "user input"

    def test_read_interactive_input_continuation(self):
        """Should continue on backslash."""
        io = MockIO(inputs=["first\\", "second", ""])
        handler = self.InputHandler(io)

        result = handler.read_interactive_input()

        assert "first" in result
        assert "second" in result

    def test_read_interactive_input_command_immediate_return(self):
        """Should return immediately if first line is a command."""
        io = MockIO(inputs=["/help"])
        handler = self.InputHandler(io)

        result = handler.read_interactive_input()

        assert result == "/help"

    def test_read_interactive_input_blank_line_terminates(self):
        """Should terminate on blank line after continuation."""
        io = MockIO(inputs=["first\\", "second\\", ""])
        handler = self.InputHandler(io)

        result = handler.read_interactive_input()

        assert "first" in result
        assert "second" in result

    def test_read_interactive_input_returns_stripped(self):
        """Should return stripped input."""
        io = MockIO(inputs=["  input with spaces  "])
        handler = self.InputHandler(io)

        result = handler.read_interactive_input()

        # Should be stripped
        assert result.strip() == result or "input with spaces" in result

    def test_read_interactive_input_rejects_too_long(self):
        """Should reject input exceeding max length."""
        from src.cli.input_handler import InputTooLongError
        from src.cli.config.defaults import MAX_INPUT_CHARS

        # Create input just over the limit
        long_input = "x" * (MAX_INPUT_CHARS + 1)
        io = MockIO(inputs=[long_input])
        handler = self.InputHandler(io)

        with pytest.raises(InputTooLongError) as exc_info:
            handler.read_interactive_input()

        assert exc_info.value.char_count == MAX_INPUT_CHARS + 1
        assert exc_info.value.max_chars == MAX_INPUT_CHARS

    def test_read_interactive_input_rejects_too_many_lines(self):
        """Should reject input exceeding max lines."""
        from src.cli.input_handler import InputTooLongError
        from src.cli.config.defaults import MAX_INPUT_LINES

        # Create input with too many continuation lines
        lines = ["line\\"] * (MAX_INPUT_LINES + 1) + [""]
        io = MockIO(inputs=lines)
        handler = self.InputHandler(io)

        with pytest.raises(InputTooLongError) as exc_info:
            handler.read_interactive_input()

        assert exc_info.value.line_count > MAX_INPUT_LINES

    def test_read_interactive_input_accepts_at_limit(self):
        """Should accept input exactly at max length."""
        from src.cli.config.defaults import MAX_INPUT_CHARS

        # Create input exactly at the limit
        at_limit_input = "x" * MAX_INPUT_CHARS
        io = MockIO(inputs=[at_limit_input])
        handler = self.InputHandler(io)

        result = handler.read_interactive_input()
        assert len(result) == MAX_INPUT_CHARS


class TestInputHandlerModuleStructure:
    """Tests for input_handler module structure."""







