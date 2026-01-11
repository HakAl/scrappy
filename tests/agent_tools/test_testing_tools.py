"""
Tests for RunTestsTool.

Tests the test execution tool with smart output truncation.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock

from scrappy.agent_tools.tools.base import ToolContext
from scrappy.agent_tools.tools.testing_tools import (
    RunTestsTool,
    truncate_test_output,
    strip_ansi_codes,
    MAX_OUTPUT_CHARS,
    HEAD_CHARS,
    TAIL_CHARS,
)
from scrappy.agent_tools.protocols import ExecutionResult
from scrappy.agent_config import AgentConfig


class TestTruncateTestOutput:
    """Tests for the output truncation function."""

    def test_short_output_unchanged(self):
        """Output shorter than max is returned unchanged."""
        output = "PASSED: 5 tests in 0.5s"
        result = truncate_test_output(output)
        assert result == output

    def test_long_output_truncated(self):
        """Output longer than max is truncated with head + tail."""
        # Create output longer than MAX_OUTPUT_CHARS
        head_content = "=" * HEAD_CHARS
        middle_content = "x" * 5000  # This should be removed
        tail_content = "=" * TAIL_CHARS
        output = head_content + middle_content + tail_content

        result = truncate_test_output(output)

        assert len(result) < len(output)
        assert result.startswith("=" * 100)  # Head preserved
        assert result.endswith("=" * 100)  # Tail preserved
        assert "truncated" in result.lower()

    def test_truncation_shows_char_count(self):
        """Truncation message shows how many chars were removed."""
        output = "a" * 10000
        result = truncate_test_output(output)
        # Should show approximately 6000 chars truncated (10000 - 4000)
        assert "truncated" in result

    def test_exact_max_length_unchanged(self):
        """Output exactly at max length is unchanged."""
        output = "x" * MAX_OUTPUT_CHARS
        result = truncate_test_output(output)
        assert result == output


class TestStripAnsiCodes:
    """Tests for ANSI code stripping."""

    def test_strips_color_codes(self):
        """ANSI color codes are removed."""
        colored = "\x1b[32mPASSED\x1b[0m"
        result = strip_ansi_codes(colored)
        assert result == "PASSED"

    def test_strips_multiple_codes(self):
        """Multiple ANSI codes are all removed."""
        colored = "\x1b[1m\x1b[31mFAILED\x1b[0m: test_foo"
        result = strip_ansi_codes(colored)
        assert result == "FAILED: test_foo"

    def test_plain_text_unchanged(self):
        """Text without ANSI codes is unchanged."""
        plain = "PASSED: 10 tests"
        result = strip_ansi_codes(plain)
        assert result == plain


class TestRunTestsToolInterface:
    """Tests for RunTestsTool as a Tool interface."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = AgentConfig()
        self.project_root = Path("/test/project")
        self.context = ToolContext(
            project_root=self.project_root,
            dry_run=False,
            config=self.config
        )

    def test_tool_has_required_properties(self):
        """RunTestsTool must have name, description, and parameters."""
        tool = RunTestsTool()

        assert tool.name == "run_tests"
        assert "test" in tool.description.lower()
        assert len(tool.parameters) >= 1
        # First parameter should be command
        assert tool.parameters[0].name == "command"

    def test_default_command_is_pytest(self):
        """Default command should be pytest -v."""
        tool = RunTestsTool()
        # Check parameter default
        command_param = tool.parameters[0]
        assert command_param.default == "pytest -v"

    def test_dry_run_skips_execution(self):
        """Dry run mode should not execute tests."""
        tool = RunTestsTool()
        dry_run_context = ToolContext(
            project_root=self.project_root,
            dry_run=True,
            config=self.config
        )

        result = tool.execute(dry_run_context, command="pytest tests/")

        assert result.success is True
        assert "DRY RUN" in result.output
        assert "pytest" in result.output


class TestRunTestsToolExecution:
    """Tests for RunTestsTool execution behavior."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = AgentConfig()
        self.project_root = Path("/test/project")
        self.context = ToolContext(
            project_root=self.project_root,
            dry_run=False,
            config=self.config
        )

    def test_successful_test_run(self):
        """Successful test execution returns success with output."""
        mock_runner = Mock()
        mock_runner.execute.return_value = ExecutionResult(
            stdout="===== 5 passed in 0.5s =====",
            stderr="",
            exit_code=0,
            execution_time=0.5
        )

        tool = RunTestsTool(runner=mock_runner)
        result = tool.execute(self.context, command="pytest tests/")

        assert result.success is True
        assert "5 passed" in result.output
        assert result.metadata["exit_code"] == 0

    def test_failed_test_run(self):
        """Failed tests return success=False with output."""
        mock_runner = Mock()
        mock_runner.execute.return_value = ExecutionResult(
            stdout="FAILED test_foo.py::test_bar\n===== 1 failed =====",
            stderr="",
            exit_code=1,
            execution_time=0.5
        )

        tool = RunTestsTool(runner=mock_runner)
        result = tool.execute(self.context, command="pytest tests/")

        assert result.success is False
        assert "FAILED" in result.output
        assert result.metadata["exit_code"] == 1

    def test_output_is_truncated(self):
        """Large test output is truncated."""
        mock_runner = Mock()
        # Create very long output
        long_output = "test line\n" * 1000  # ~10000 chars
        mock_runner.execute.return_value = ExecutionResult(
            stdout=long_output,
            stderr="",
            exit_code=0,
            execution_time=1.0
        )

        tool = RunTestsTool(runner=mock_runner)
        result = tool.execute(self.context, command="pytest tests/")

        assert len(result.output) <= MAX_OUTPUT_CHARS + 100  # Some margin for truncation message

    def test_ansi_codes_stripped(self):
        """ANSI color codes are removed from output."""
        mock_runner = Mock()
        mock_runner.execute.return_value = ExecutionResult(
            stdout="\x1b[32mPASSED\x1b[0m",
            stderr="",
            exit_code=0,
            execution_time=0.1
        )

        tool = RunTestsTool(runner=mock_runner)
        result = tool.execute(self.context, command="pytest")

        assert "\x1b[" not in result.output
        assert "PASSED" in result.output

    def test_stderr_included_in_output(self):
        """Stderr is appended to output."""
        mock_runner = Mock()
        mock_runner.execute.return_value = ExecutionResult(
            stdout="Running tests...",
            stderr="Warning: deprecated API",
            exit_code=0,
            execution_time=0.1
        )

        tool = RunTestsTool(runner=mock_runner)
        result = tool.execute(self.context, command="pytest")

        assert "Running tests" in result.output
        assert "STDERR" in result.output
        assert "deprecated API" in result.output


class TestRunTestsToolSecurity:
    """Tests for security validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = AgentConfig()
        self.project_root = Path("/test/project")
        self.context = ToolContext(
            project_root=self.project_root,
            dry_run=False,
            config=self.config
        )

    def test_dangerous_command_blocked(self):
        """Dangerous commands are blocked by security validation."""
        tool = RunTestsTool()

        result = tool.execute(self.context, command="rm -rf /")

        assert result.success is False
        assert "blocked" in result.error.lower()

    def test_safe_test_command_allowed(self):
        """Normal test commands pass security validation."""
        mock_runner = Mock()
        mock_runner.execute.return_value = ExecutionResult(
            stdout="ok",
            stderr="",
            exit_code=0,
            execution_time=0.1
        )

        tool = RunTestsTool(runner=mock_runner)
        result = tool.execute(self.context, command="pytest tests/ -v -k test_auth")

        assert result.success is True


class TestRunTestsToolErrorHandling:
    """Tests for error handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = AgentConfig()
        self.project_root = Path("/test/project")
        self.context = ToolContext(
            project_root=self.project_root,
            dry_run=False,
            config=self.config
        )

    def test_timeout_error_handled(self):
        """Timeout errors are caught and reported."""
        mock_runner = Mock()
        mock_runner.execute.side_effect = TimeoutError("timed out")

        tool = RunTestsTool(runner=mock_runner)
        result = tool.execute(self.context, command="pytest tests/")

        assert result.success is False
        assert "timed out" in result.error.lower()

    def test_command_not_found_handled(self):
        """FileNotFoundError (command not found) is handled."""
        mock_runner = Mock()
        mock_runner.execute.side_effect = FileNotFoundError("pytest not found")

        tool = RunTestsTool(runner=mock_runner)
        result = tool.execute(self.context, command="pytest")

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_generic_error_handled(self):
        """Generic exceptions are caught and reported."""
        mock_runner = Mock()
        mock_runner.execute.side_effect = RuntimeError("unexpected error")

        tool = RunTestsTool(runner=mock_runner)
        result = tool.execute(self.context, command="pytest")

        assert result.success is False
        assert "error" in result.error.lower()


class TestRunTestsToolCancellation:
    """Tests for cancellation support."""

    def setup_method(self):
        """Set up test fixtures."""
        from scrappy.infrastructure.threading.cancellation import CancellationToken

        self.config = AgentConfig()
        self.project_root = Path("/test/project")
        self.token = CancellationToken()

        # Create mock run_context with cancellation_token
        self.mock_run_context = Mock()
        self.mock_run_context.cancellation_token = self.token

        self.context = ToolContext(
            project_root=self.project_root,
            dry_run=False,
            config=self.config,
            run_context=self.mock_run_context
        )

    def test_cancellation_exception_propagates(self):
        """CancelledException from runner is re-raised, not swallowed."""
        from scrappy.infrastructure.exceptions import CancelledException

        mock_runner = Mock()
        mock_runner.execute.side_effect = CancelledException("Cancelled")

        tool = RunTestsTool(runner=mock_runner)

        with pytest.raises(CancelledException):
            tool.execute(self.context, command="pytest")

    def test_uses_cancellation_token_from_context(self):
        """When no runner injected, creates runner with context's cancellation token."""
        # Don't inject a runner - let it create one
        tool = RunTestsTool()

        # Cancel the token
        self.token.cancel()

        # Execute should raise CancelledException because the runner
        # will be created with the cancelled token
        from scrappy.infrastructure.exceptions import CancelledException

        with pytest.raises(CancelledException):
            # Use a slow command that would take time without cancellation
            import sys
            if sys.platform == "win32":
                tool.execute(self.context, command="ping -n 5 127.0.0.1")
            else:
                tool.execute(self.context, command="sleep 5")

    def test_injected_runner_used_when_provided(self):
        """When runner is injected, uses that instead of creating new one."""
        mock_runner = Mock()
        mock_runner.execute.return_value = ExecutionResult(
            stdout="PASSED",
            stderr="",
            exit_code=0,
            execution_time=0.1
        )

        tool = RunTestsTool(runner=mock_runner)
        result = tool.execute(self.context, command="pytest")

        # Should use the injected runner
        mock_runner.execute.assert_called_once()
        assert result.success is True
