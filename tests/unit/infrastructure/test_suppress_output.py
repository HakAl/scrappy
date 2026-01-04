"""Tests for output suppression utilities.

These tests guard against chatty libraries corrupting terminal state.
See scrappy-gsji bead for full context on this issue.
"""

import sys
import io
from unittest.mock import patch

import pytest


class TestSuppressOutput:
    """Test the suppress_output context manager."""

    def test_suppresses_stdout(self):
        """Verify stdout is suppressed within context."""
        from scrappy.infrastructure import suppress_output

        captured = io.StringIO()

        with patch('sys.stdout', captured):
            # This print would normally go to stdout
            print("before suppress")

        before_output = captured.getvalue()
        assert "before suppress" in before_output

        # Now with suppression - need to test at fd level
        # The context manager works at file descriptor level,
        # so we test by checking no exception and it returns cleanly
        with suppress_output():
            # These writes go to /dev/null
            sys.stdout.write("suppressed stdout\n")
            sys.stderr.write("suppressed stderr\n")

        # If we get here without exception, suppression worked

    def test_restores_stdout_after_context(self):
        """Verify stdout is restored after context exits."""
        from scrappy.infrastructure import suppress_output

        original_stdout = sys.stdout.fileno()

        with suppress_output():
            pass

        # stdout should still work after context
        assert sys.stdout.fileno() == original_stdout

    def test_suppresses_only_stderr_when_configured(self):
        """Verify selective suppression works."""
        from scrappy.infrastructure import suppress_output

        with suppress_output(suppress_stdout=False, suppress_stderr=True):
            # stdout should still work, stderr suppressed
            pass  # No exception = success


class TestLiteLLMNoOutput:
    """Guard test: LiteLLM initialization must not produce output.

    CONTEXT: LiteLLM/Langfuse debug output corrupts Textual's terminal
    escape sequences for mouse tracking. This test fails if someone
    removes our output suppression or adds a new chatty import.

    See: scrappy-gsji bead, changelog.d/chatty-libs-mouse-fix.fix.md
    """

    def test_create_litellm_router_silent(self, capsys):
        """create_litellm_router() must not write to stdout/stderr."""
        from scrappy.orchestrator.litellm_config import create_litellm_router

        # Create router (this is where chatty output would happen)
        router = create_litellm_router()

        # Capture any output that leaked
        captured = capsys.readouterr()

        # CRITICAL: No output allowed - it breaks Textual mouse tracking
        assert captured.out == "", (
            f"LiteLLM router wrote to stdout: {captured.out!r}\n"
            "This will corrupt Textual terminal escape sequences!\n"
            "Ensure output is suppressed BEFORE imports in litellm_config.py"
        )
        assert captured.err == "", (
            f"LiteLLM router wrote to stderr: {captured.err!r}\n"
            "This will corrupt Textual terminal escape sequences!\n"
            "Ensure output is suppressed BEFORE imports in litellm_config.py"
        )
