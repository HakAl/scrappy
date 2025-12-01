"""
Tests for OutputParser component.

Tests output parsing, truncation, and format detection following TDD principles.
"""

import pytest
from scrappy.agent_tools.components.output_parser import OutputParser


class TestOutputParserBasicParsing:
    """Test basic output parsing functionality."""

    def test_returns_output_unchanged_for_plain_text(self):
        """Should return plain text unchanged."""
        parser = OutputParser()
        output = "This is plain text output"
        result = parser.parse(output)
        assert "This is plain text output" in result

    def test_handles_empty_output(self):
        """Should handle empty output."""
        parser = OutputParser()
        result = parser.parse("")
        assert result == ""

    def test_handles_no_output_marker(self):
        """Should handle (no output) marker unchanged."""
        parser = OutputParser()
        result = parser.parse("(no output)")
        assert result == "(no output)"


class TestOutputParserTruncation:
    """Test output truncation functionality."""

    def test_truncates_long_output(self):
        """Should truncate output exceeding max_length."""
        parser = OutputParser()
        long_output = "x" * 50000
        result = parser.parse(long_output, max_length=1000)
        assert len(result) < 50000
        assert "truncated" in result.lower()

    def test_does_not_truncate_short_output(self):
        """Should not truncate output within max_length."""
        parser = OutputParser()
        short_output = "x" * 500
        result = parser.parse(short_output, max_length=1000)
        assert len(result) == 500
        assert "truncated" not in result.lower()

    def test_truncation_shows_last_portion(self):
        """Truncation should show the last portion of output."""
        parser = OutputParser()
        output = "start" + ("x" * 1000) + "end_marker"
        result = parser.parse(output, max_length=100)
        assert "end_marker" in result
        assert "start" not in result


class TestOutputParserEdgeCases:
    """Test edge cases and boundaries."""

    def test_handles_unicode_characters(self):
        """Should handle Unicode characters correctly."""
        parser = OutputParser()
        unicode_output = "Hello 你好 مرحبا"
        result = parser.parse(unicode_output)
        assert unicode_output in result

    def test_handles_newlines_and_special_chars(self):
        """Should preserve newlines and special characters."""
        parser = OutputParser()
        output_with_newlines = "Line 1\nLine 2\nLine 3"
        result = parser.parse(output_with_newlines)
        assert "\n" in result

    def test_handles_very_long_single_line(self):
        """Should handle very long single lines."""
        parser = OutputParser()
        long_line = "x" * 100000
        result = parser.parse(long_line, max_length=1000)
        assert len(result) < 100000
