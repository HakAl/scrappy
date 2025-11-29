"""Tests for ToolResult __str__ and __rich__ methods."""

import pytest
from rich.syntax import Syntax
from rich.text import Text

from src.agent_tools.tools.base import ToolResult


class TestToolResultStr:
    """Tests for ToolResult.__str__() method."""

    def test_str_returns_output(self):
        """str() returns the output string directly."""
        result = ToolResult(success=True, output="Line 1\nLine 2")
        assert str(result) == "Line 1\nLine 2"

    def test_str_excludes_dataclass_repr(self):
        """str() does not include dataclass repr format."""
        result = ToolResult(success=True, output="some output")
        assert "ToolResult" not in str(result)
        assert "success=" not in str(result)

    def test_str_with_error_returns_error_message(self):
        """str() returns formatted error when error is present."""
        result = ToolResult(success=False, output="", error="Something failed")
        assert str(result) == "Error: Something failed"

    def test_str_preserves_newlines(self):
        """str() preserves newlines in output (no escaping)."""
        result = ToolResult(success=True, output="a\nb\nc")
        output = str(result)
        assert output.count("\n") == 2
        assert "\\n" not in output

    def test_str_empty_output(self):
        """str() handles empty output gracefully."""
        result = ToolResult(success=True, output="")
        assert str(result) == ""


class TestToolResultRich:
    """Tests for ToolResult.__rich__() method."""

    def test_rich_returns_text_for_plain_output(self):
        """__rich__() returns Text for plain text output."""
        result = ToolResult(success=True, output="plain text")
        rich_output = result.__rich__()
        assert isinstance(rich_output, Text)

    def test_rich_returns_syntax_for_code_with_language(self):
        """__rich__() returns Syntax when language metadata is set."""
        result = ToolResult(
            success=True,
            output="def foo():\n    pass",
            metadata={"language": "python"},
        )
        rich_output = result.__rich__()
        assert isinstance(rich_output, Syntax)

    def test_rich_returns_text_for_single_line_code(self):
        """__rich__() returns Text for single-line code (no multiline)."""
        result = ToolResult(
            success=True,
            output="x = 1",
            metadata={"language": "python"},
        )
        rich_output = result.__rich__()
        # Single line code doesn't get Syntax highlighting
        assert isinstance(rich_output, Text)

    def test_rich_returns_styled_error(self):
        """__rich__() returns styled Text for errors."""
        result = ToolResult(success=False, output="", error="Failed")
        rich_output = result.__rich__()
        assert isinstance(rich_output, Text)
        # Check that the error text is styled with bold red
        assert "bold #ff0000" in str(rich_output.style)

    def test_rich_error_message_format(self):
        """__rich__() error text contains proper message."""
        result = ToolResult(success=False, output="", error="Connection timeout")
        rich_output = result.__rich__()
        assert "Error: Connection timeout" in str(rich_output)

    def test_rich_no_language_metadata_returns_text(self):
        """__rich__() returns Text when no language in metadata."""
        result = ToolResult(
            success=True,
            output="some\nmultiline\ntext",
            metadata={},
        )
        rich_output = result.__rich__()
        assert isinstance(rich_output, Text)

    def test_rich_text_language_returns_text(self):
        """__rich__() returns Text when language is 'text'."""
        result = ToolResult(
            success=True,
            output="some\nmultiline\ntext",
            metadata={"language": "text"},
        )
        rich_output = result.__rich__()
        assert isinstance(rich_output, Text)
