"""Tests for SubprocessRunner cancellation behavior.

Tests cover:
- Cancellation token integration
- Graceful cancellation (SIGTERM)
- Force cancellation (SIGKILL)
- Event.wait() usage instead of polling
"""

import pytest
import sys

from scrappy.agent_tools.components.subprocess_runner import SubprocessRunner
from scrappy.infrastructure.exceptions import CancelledException
from scrappy.infrastructure.threading.cancellation import CancellationToken


class TestSubprocessRunnerCancellation:
    """Tests for subprocess cancellation behavior."""

    def test_runs_normally_without_token(self):
        """Should run commands normally when no cancellation token provided."""
        runner = SubprocessRunner()

        result = runner.execute("echo hello", ".", timeout=10)

        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_runs_normally_with_uncancelled_token(self):
        """Should run commands normally when token is not cancelled."""
        token = CancellationToken()
        runner = SubprocessRunner(cancellation_token=token)

        result = runner.execute("echo hello", ".", timeout=10)

        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_raises_cancelled_exception_when_token_cancelled(self):
        """Should raise CancelledException when token is cancelled."""
        token = CancellationToken()
        runner = SubprocessRunner(cancellation_token=token)

        # Pre-cancel the token
        token.cancel()

        # Try to run a slow command
        with pytest.raises(CancelledException) as exc_info:
            # Use a sleep command that would take time
            if sys.platform == "win32":
                runner.execute("ping -n 5 127.0.0.1", ".", timeout=30)
            else:
                runner.execute("sleep 5", ".", timeout=30)

        assert exc_info.value.force is False

    def test_raises_force_cancelled_exception_on_double_cancel(self):
        """Should raise CancelledException with force=True on double cancel."""
        token = CancellationToken()
        runner = SubprocessRunner(cancellation_token=token)

        # Pre-cancel twice for force cancel
        token.cancel()
        token.cancel()

        with pytest.raises(CancelledException) as exc_info:
            if sys.platform == "win32":
                runner.execute("ping -n 5 127.0.0.1", ".", timeout=30)
            else:
                runner.execute("sleep 5", ".", timeout=30)

        assert exc_info.value.force is True

    def test_cancellation_stops_process(self):
        """Should actually stop the running process on cancellation."""
        import threading
        import time

        token = CancellationToken()
        runner = SubprocessRunner(cancellation_token=token)

        exception_raised = []

        def run_slow_command():
            try:
                if sys.platform == "win32":
                    runner.execute("ping -n 10 127.0.0.1", ".", timeout=30)
                else:
                    runner.execute("sleep 10", ".", timeout=30)
            except CancelledException as e:
                exception_raised.append(e)

        # Start command in background
        thread = threading.Thread(target=run_slow_command)
        thread.start()

        # Wait a bit then cancel
        time.sleep(0.5)
        token.cancel()

        # Wait for thread to finish (should be quick after cancel)
        thread.join(timeout=3)

        assert not thread.is_alive(), "Thread should have finished after cancellation"
        assert len(exception_raised) == 1, "Should have raised CancelledException"


class TestSubprocessRunnerExecuteListCancellation:
    """Tests for execute_list cancellation behavior."""

    def test_execute_list_runs_normally_without_token(self):
        """Should run commands normally when no cancellation token provided."""
        runner = SubprocessRunner()

        if sys.platform == "win32":
            result = runner.execute_list(["cmd", "/c", "echo", "hello"], ".", timeout=10)
        else:
            result = runner.execute_list(["echo", "hello"], ".", timeout=10)

        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_execute_list_runs_normally_with_uncancelled_token(self):
        """Should run commands normally when token is not cancelled."""
        token = CancellationToken()
        runner = SubprocessRunner(cancellation_token=token)

        if sys.platform == "win32":
            result = runner.execute_list(["cmd", "/c", "echo", "hello"], ".", timeout=10)
        else:
            result = runner.execute_list(["echo", "hello"], ".", timeout=10)

        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_execute_list_raises_cancelled_exception_when_token_cancelled(self):
        """Should raise CancelledException when token is cancelled."""
        token = CancellationToken()
        runner = SubprocessRunner(cancellation_token=token)

        # Pre-cancel the token
        token.cancel()

        with pytest.raises(CancelledException) as exc_info:
            if sys.platform == "win32":
                runner.execute_list(["ping", "-n", "5", "127.0.0.1"], ".", timeout=30)
            else:
                runner.execute_list(["sleep", "5"], ".", timeout=30)

        assert exc_info.value.force is False

    def test_execute_list_raises_force_cancelled_on_double_cancel(self):
        """Should raise CancelledException with force=True on double cancel."""
        token = CancellationToken()
        runner = SubprocessRunner(cancellation_token=token)

        # Pre-cancel twice for force cancel
        token.cancel()
        token.cancel()

        with pytest.raises(CancelledException) as exc_info:
            if sys.platform == "win32":
                runner.execute_list(["ping", "-n", "5", "127.0.0.1"], ".", timeout=30)
            else:
                runner.execute_list(["sleep", "5"], ".", timeout=30)

        assert exc_info.value.force is True

    def test_execute_list_cancellation_stops_process(self):
        """Should actually stop the running process on cancellation."""
        import threading
        import time

        token = CancellationToken()
        runner = SubprocessRunner(cancellation_token=token)

        exception_raised = []

        def run_slow_command():
            try:
                if sys.platform == "win32":
                    runner.execute_list(["ping", "-n", "10", "127.0.0.1"], ".", timeout=30)
                else:
                    runner.execute_list(["sleep", "10"], ".", timeout=30)
            except CancelledException as e:
                exception_raised.append(e)

        # Start command in background
        thread = threading.Thread(target=run_slow_command)
        thread.start()

        # Wait a bit then cancel
        time.sleep(0.5)
        token.cancel()

        # Wait for thread to finish (should be quick after cancel)
        thread.join(timeout=3)

        assert not thread.is_alive(), "Thread should have finished after cancellation"
        assert len(exception_raised) == 1, "Should have raised CancelledException"

    def test_execute_list_captures_separate_stdout_stderr(self):
        """Should capture stdout and stderr separately."""
        runner = SubprocessRunner()

        if sys.platform == "win32":
            # Windows: use cmd to echo to stdout, can't easily separate stderr
            result = runner.execute_list(["cmd", "/c", "echo", "out"], ".", timeout=10)
            assert "out" in result.stdout
        else:
            # Unix: use sh -c to write to both streams
            result = runner.execute_list(
                ["sh", "-c", "echo out; echo err >&2"],
                ".",
                timeout=10
            )
            assert "out" in result.stdout
            assert "err" in result.stderr


class TestSubprocessRunnerTokenProperty:
    """Tests for cancellation token property."""

    def test_token_can_be_passed_via_constructor(self):
        """Should accept token via constructor."""
        token = CancellationToken()
        runner = SubprocessRunner(cancellation_token=token)

        assert runner._cancellation_token is token

    def test_no_token_by_default(self):
        """Should have no token by default."""
        runner = SubprocessRunner()

        assert runner._cancellation_token is None
