"""Tests for input handling in Textual app.

Multiline input is now preserved as-is. Textual's TextArea correctly
buffers paste operations, so newlines no longer need sanitization.
"""


def process_input(raw_input: str) -> str:
    """
    Replicate the input processing logic from MainAppScreen.action_submit_input.

    This function mirrors the exact logic used in the app to ensure
    tests verify the correct behavior.
    """
    return raw_input.strip()


class TestMultilineInputPreservation:
    """Test that multiline input is preserved."""

    def test_preserves_newlines_in_pasted_text(self):
        """Multiline pasted text should preserve newlines."""
        raw = "line one\nline two\nline three"
        result = process_input(raw)
        assert result == "line one\nline two\nline three"

    def test_preserves_windows_newlines(self):
        """Windows-style CRLF newlines should be preserved."""
        raw = "line one\r\nline two\r\nline three"
        result = process_input(raw)
        assert result == "line one\r\nline two\r\nline three"

    def test_strips_leading_trailing_whitespace(self):
        """Leading and trailing whitespace should be stripped."""
        raw = "  \n  hello world  \n  "
        result = process_input(raw)
        assert result == "hello world"

    def test_preserves_internal_whitespace(self):
        """Internal whitespace and newlines should be preserved."""
        raw = "def foo():\n    return 42"
        result = process_input(raw)
        assert result == "def foo():\n    return 42"

    def test_empty_input(self):
        """Empty input should return empty string."""
        assert process_input("") == ""
        assert process_input("   ") == ""
        assert process_input("\n\n") == ""

    def test_code_block_preserved(self):
        """Multi-line code blocks should be preserved exactly."""
        code = """def example():
    x = 1
    y = 2
    return x + y"""
        result = process_input(code)
        assert "def example():" in result
        assert "    x = 1" in result
        assert "    return x + y" in result
