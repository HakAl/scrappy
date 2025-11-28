"""Tests for input sanitization in Textual app.

BUG-004: Sanitize Newlines in Command Input
The TextArea widget allows multiline input, but validators reject newlines.
This tests the sanitization logic that converts newlines to spaces.
"""

import re


def sanitize_input(raw_input: str) -> str:
    """
    Replicate the sanitization logic from ScrappyApp.action_submit_input.

    This function mirrors the exact logic used in the app to ensure
    tests verify the correct behavior.
    """
    user_input = raw_input.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ').strip()
    user_input = re.sub(r'\s+', ' ', user_input)
    return user_input


class TestInputSanitization:
    """Test newline sanitization in input."""

    def test_multiline_input_sanitized_to_single_line(self):
        """Newlines should be converted to spaces."""
        raw = "hello\nworld"
        expected = "hello world"
        assert sanitize_input(raw) == expected

    def test_crlf_sanitized(self):
        """Windows-style CRLF should be sanitized."""
        raw = "hello\r\nworld"
        assert sanitize_input(raw) == "hello world"

    def test_cr_only_sanitized(self):
        """Old Mac-style CR should be sanitized."""
        raw = "hello\rworld"
        assert sanitize_input(raw) == "hello world"

    def test_multiple_newlines_collapsed(self):
        """Multiple newlines should become single space."""
        raw = "hello\n\n\nworld"
        assert sanitize_input(raw) == "hello world"

    def test_mixed_newlines_collapsed(self):
        """Mixed newline types should become single space."""
        raw = "hello\r\n\n\rworld"
        assert sanitize_input(raw) == "hello world"

    def test_leading_trailing_whitespace_stripped(self):
        """Leading and trailing whitespace should be stripped."""
        raw = "  hello world  "
        assert sanitize_input(raw) == "hello world"

    def test_leading_trailing_newlines_stripped(self):
        """Leading and trailing newlines should be stripped."""
        raw = "\n\nhello world\n\n"
        assert sanitize_input(raw) == "hello world"

    def test_tabs_normalized(self):
        """Tabs should be normalized to single space."""
        raw = "hello\t\tworld"
        assert sanitize_input(raw) == "hello world"

    def test_mixed_whitespace_normalized(self):
        """Mixed whitespace (tabs, spaces, newlines) should collapse to single space."""
        raw = "hello  \t\n  world"
        assert sanitize_input(raw) == "hello world"

    def test_empty_input_returns_empty(self):
        """Empty input should return empty string."""
        assert sanitize_input("") == ""

    def test_whitespace_only_returns_empty(self):
        """Whitespace-only input should return empty string."""
        assert sanitize_input("   \n\t\r\n   ") == ""

    def test_single_word_unchanged(self):
        """Single word without whitespace should be unchanged."""
        assert sanitize_input("hello") == "hello"

    def test_normal_spaces_preserved(self):
        """Normal single spaces between words should be preserved."""
        assert sanitize_input("hello world foo bar") == "hello world foo bar"

    def test_pasted_multiline_code_becomes_single_line(self):
        """Simulates pasting multiline content (common use case)."""
        pasted = """def hello():
    print("world")
    return True"""
        # All newlines become spaces, multiple spaces collapse
        result = sanitize_input(pasted)
        assert "\n" not in result
        assert result == 'def hello(): print("world") return True'

    def test_pasted_url_with_accidental_newline(self):
        """URLs accidentally split across lines should be joined."""
        pasted = "https://example.com/path\n/to/resource"
        assert sanitize_input(pasted) == "https://example.com/path /to/resource"
