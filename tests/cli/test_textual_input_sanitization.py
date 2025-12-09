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















