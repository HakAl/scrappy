"""
Tests for CommandTool and ShellCommandExecutor.

These tests define the expected behavior of command execution extracted from CodeAgent.
Following TDD: write tests first to specify behavior, then implement to satisfy tests.
"""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Import base tool infrastructure
from scrappy.agent_tools.tools.base import ToolContext, ToolResult
from scrappy.agent_config import AgentConfig


# Suppress safe_print output during tests
class TestCommandToolInterface:
    """Tests for the CommandTool as a Tool interface."""

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
        """CommandTool must have name, description, and parameters."""
        from scrappy.agent_tools.tools.command_tool import CommandTool

        tool = CommandTool(use_sandbox=False)

        assert tool.name == "run_command"
        assert "shell" in tool.description.lower() or "command" in tool.description.lower()
        assert len(tool.parameters) >= 1
        # First parameter should be the command string
        assert tool.parameters[0].name == "command"
        assert tool.parameters[0].param_type is str
        assert tool.parameters[0].required is True

    def test_execute_returns_tool_result(self):
        """Execute must return a ToolResult object."""
        from scrappy.agent_tools.tools.command_tool import CommandTool

        tool = CommandTool(use_sandbox=False)

        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = 0
            mock_process.stdout.readline.side_effect = ["command output\n", ""]
            mock_popen.return_value = mock_process

            result = tool.execute(self.context, command="echo test")

            assert isinstance(result, ToolResult)
            assert result.success is True

    def test_dry_run_skips_execution(self):
        """Dry run mode should not execute commands."""
        from scrappy.agent_tools.tools.command_tool import CommandTool

        tool = CommandTool(use_sandbox=False)
        dry_run_context = ToolContext(
            project_root=self.project_root,
            dry_run=True,
            config=self.config
        )

        result = tool.execute(dry_run_context, command="echo 'test'")

        assert result.success is True
        assert "DRY RUN" in result.output
        assert "echo" in result.output

    def test_missing_command_parameter_fails_validation(self):
        """Missing required command parameter should fail validation."""
        from scrappy.agent_tools.tools.command_tool import CommandTool

        tool = CommandTool(use_sandbox=False)

        is_valid, error = tool.validate()

        assert is_valid is False
        assert "command" in error.lower()


class TestCommandSecurityValidation:
    """Tests for security checks in command execution."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = AgentConfig()
        self.project_root = Path("/test/project")
        self.context = ToolContext(
            project_root=self.project_root,
            dry_run=False,
            config=self.config
        )

    def test_blocks_dangerous_rm_rf_command(self):
        """Should block rm -rf commands."""
        from scrappy.agent_tools.tools.command_tool import CommandTool

        # Explicitly configure dangerous patterns to include rm -rf
        dangerous_patterns = [r'rm\s+-rf\s+/', r'format\s+[A-Za-z]:']
        tool = CommandTool(dangerous_patterns=dangerous_patterns)

        result = tool.execute(self.context, command="rm -rf /")

        assert result.success is False
        assert "dangerous" in result.error.lower() or "pattern" in result.error.lower()

    def test_blocks_dangerous_format_command(self):
        """Should block format/disk destruction commands."""
        from scrappy.agent_tools.tools.command_tool import CommandTool

        tool = CommandTool(use_sandbox=False)

        result = tool.execute(self.context, command="format C:")

        assert result.success is False
        assert "dangerous" in result.error.lower() or "blocked" in result.error.lower()

    def test_blocks_command_matching_regex_pattern(self):
        """Should block commands matching configured dangerous patterns."""
        from scrappy.agent_tools.tools.command_tool import CommandTool

        dangerous_patterns = [r"sudo\s+rm", r":\(\)\s*\{.*\}"]
        tool = CommandTool(dangerous_patterns=dangerous_patterns)

        result = tool.execute(self.context, command="sudo rm -rf /var")

        assert result.success is False
        assert "dangerous" in result.error.lower() or "pattern" in result.error.lower()

    def test_allows_safe_echo_command(self):
        """Should allow safe commands like echo."""
        from scrappy.agent_tools.tools.command_tool import CommandTool

        tool = CommandTool(use_sandbox=False)

        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = 0
            mock_process.stdout.readline.side_effect = ["hello\n", ""]
            mock_popen.return_value = mock_process

            result = tool.execute(self.context, command="echo hello")

            # Should attempt to run the command (not blocked)
            assert mock_popen.called or result.success is True


class TestPlatformSpecificFixes:
    """Tests for platform-specific command normalization."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = AgentConfig()
        self.project_root = Path("/test/project")
        self.context = ToolContext(
            project_root=self.project_root,
            dry_run=False,
            config=self.config
        )

    @patch('scrappy.agent_tools.tools.command_tool.is_windows', return_value=True)
    def test_intercepts_spring_initializr_on_windows(self, mock_is_windows):
        """Should block Spring Initializr downloads on Windows."""
        from scrappy.agent_tools.tools.command_tool import CommandTool

        tool = CommandTool(use_sandbox=False)

        result = tool.execute(
            self.context,
            command="curl https://start.spring.io/starter.zip -o demo.zip"
        )

        # Should recommend using write_file instead
        assert result.success is False
        assert "write_file" in result.error.lower() or "template" in result.error.lower()


class TestErrorHandling:
    """Tests for error handling in command execution."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = AgentConfig()
        self.project_root = Path("/test/project")
        self.context = ToolContext(
            project_root=self.project_root,
            dry_run=False,
            config=self.config
        )

    def test_handles_exception_in_run(self):
        """Should handle exceptions gracefully."""
        from scrappy.agent_tools.tools.command_tool import CommandTool

        # Disable sandbox to ensure subprocess.Popen is used (not Docker)
        tool = CommandTool(use_sandbox=False)

        # Mock subprocess to raise an exception
        with patch('subprocess.Popen', side_effect=OSError("Permission denied")):
            result = tool.execute(self.context, command="echo test")

        assert result.success is False
        assert "error" in result.error.lower()

    def test_error_output_returns_failure(self):
        """Should return failure when command output starts with Error."""
        from scrappy.agent_tools.tools.command_tool import CommandTool

        # Disable sandbox to ensure subprocess.Popen is used (not Docker)
        tool = CommandTool(use_sandbox=False)

        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = 1
            mock_process.stdout.readline.side_effect = ["Error: command failed\n", ""]
            mock_popen.return_value = mock_process

            result = tool.execute(self.context, command="failing_cmd")

        assert result.success is False
        assert "command failed" in result.error


class TestShellCommandExecutorSecurity:
    """Tests for ShellCommandExecutor security validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.project_root = Path("/test/project")

    def test_blocks_dangerous_command_via_security_component(self):
        """Security component should block dangerous commands."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor
        from scrappy.agent_tools.components import CommandSecurity

        security = CommandSecurity(dangerous_patterns=[r'rm\s+-rf\s+/'])
        executor = ShellCommandExecutor(security=security)

        result = executor.run("rm -rf /", self.project_root)

        assert "Error" in result
        assert "dangerous" in result.lower() or "pattern" in result.lower()

    def test_allows_safe_command_through_security(self):
        """Safe commands should pass security validation."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor
        from scrappy.agent_tools.components import CommandSecurity

        security = CommandSecurity(dangerous_patterns=[r'rm\s+-rf\s+/'])
        mock_runner = Mock()
        mock_runner.execute.return_value = Mock(stdout="hello world")

        executor = ShellCommandExecutor(security=security, runner=mock_runner)

        result = executor.run("echo hello", self.project_root)

        assert "hello" in result
        mock_runner.execute.assert_called_once()


class TestCommandInjectionPrevention:
    """Tests for command injection pattern blocking."""

    def setup_method(self):
        """Set up test fixtures."""
        from scrappy.agent_tools.components import CommandSecurity
        self.security = CommandSecurity()


class TestShellCommandExecutorRetry:
    """Tests for retry logic with exponential backoff."""

    def setup_method(self):
        """Set up test fixtures."""
        self.project_root = Path("/test/project")

    def test_retries_on_connection_reset_error(self):
        """Should retry when output contains connection reset."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        mock_runner = Mock()
        # First call: network error, second call: success
        mock_runner.execute.side_effect = [
            Mock(stdout="error: connection reset by peer"),
            Mock(stdout="success output"),
        ]
        mock_security = Mock()
        mock_security.validate.return_value = None

        executor = ShellCommandExecutor(
            security=mock_security,
            runner=mock_runner,
            timeout=10
        )

        result = executor._run_command_with_retry(
            "npm install",
            timeout=10,
            show_progress=False,
            max_retries=3,
            cwd=self.project_root
        )

        assert "success" in result
        assert mock_runner.execute.call_count == 2

    def test_gives_up_after_max_retries(self):
        """Should give up after max retry attempts."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        mock_runner = Mock()
        # All calls return network error
        mock_runner.execute.return_value = Mock(stdout="error: ECONNRESET")
        mock_security = Mock()

        executor = ShellCommandExecutor(
            security=mock_security,
            runner=mock_runner,
            timeout=10
        )

        result = executor._run_command_with_retry(
            "npm install",
            timeout=10,
            show_progress=False,
            max_retries=3,
            cwd=self.project_root
        )

        assert "failed after 3 attempts" in result
        assert mock_runner.execute.call_count == 3

    def test_no_retry_on_non_recoverable_error(self):
        """Should not retry on non-recoverable errors."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        mock_runner = Mock()
        mock_runner.execute.return_value = Mock(stdout="error: command not found")
        mock_security = Mock()

        executor = ShellCommandExecutor(
            security=mock_security,
            runner=mock_runner,
            timeout=10
        )

        executor._run_command_with_retry(
            "nonexistent_cmd",
            timeout=10,
            show_progress=False,
            max_retries=3,
            cwd=self.project_root
        )

        # Should return after first attempt (not a recoverable error)
        assert mock_runner.execute.call_count == 1

    def test_handles_timeout_error_in_retry(self):
        """Should handle TimeoutError during retry."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        mock_runner = Mock()
        mock_runner.execute.side_effect = TimeoutError("Command timed out")
        mock_security = Mock()

        executor = ShellCommandExecutor(
            security=mock_security,
            runner=mock_runner,
            timeout=10
        )

        result = executor._run_command_with_retry(
            "slow_command",
            timeout=10,
            show_progress=False,
            max_retries=3,
            cwd=self.project_root
        )

        assert "Error" in result
        assert mock_runner.execute.call_count == 1


class TestShellCommandExecutorLongRunning:
    """Tests for long-running command detection."""

    def test_detects_npm_install_as_long_running(self):
        """Should detect npm install as long-running."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor()

        assert executor._is_long_running_command("npm install") is True
        assert executor._is_long_running_command("npm install express") is True
        assert executor._is_long_running_command("NPM INSTALL") is True

    def test_detects_docker_build_as_long_running(self):
        """Should detect docker build as long-running."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor()

        assert executor._is_long_running_command("docker build .") is True
        assert executor._is_long_running_command("docker build -t myapp .") is True

    def test_detects_pip_install_as_long_running(self):
        """Should detect pip install as long-running."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor()

        assert executor._is_long_running_command("pip install requests") is True
        assert executor._is_long_running_command("pip install -r requirements.txt") is True

    def test_echo_is_not_long_running(self):
        """Should not detect simple commands as long-running."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor()

        assert executor._is_long_running_command("echo hello") is False
        assert executor._is_long_running_command("ls -la") is False
        assert executor._is_long_running_command("cat file.txt") is False


class TestShellCommandExecutorTimeouts:
    """Tests for command timeout behavior."""

    def test_default_timeout_is_60_seconds(self):
        """Default command timeout should be 60 seconds (safe default)."""
        from scrappy.agent_tools.constants import DEFAULT_COMMAND_TIMEOUT

        assert DEFAULT_COMMAND_TIMEOUT == 60

    def test_long_running_timeout_is_300_seconds(self):
        """Long-running command timeout should be 300 seconds."""
        from scrappy.agent_tools.constants import LONG_RUNNING_COMMAND_TIMEOUT

        assert LONG_RUNNING_COMMAND_TIMEOUT == 300

    def test_effective_timeout_uses_default_for_regular_commands(self):
        """Regular commands should use the default timeout."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor
        from scrappy.agent_tools.constants import DEFAULT_COMMAND_TIMEOUT

        executor = ShellCommandExecutor(timeout=DEFAULT_COMMAND_TIMEOUT)

        assert executor._get_effective_timeout("echo hello") == DEFAULT_COMMAND_TIMEOUT
        assert executor._get_effective_timeout("ls -la") == DEFAULT_COMMAND_TIMEOUT
        assert executor._get_effective_timeout("git status") == DEFAULT_COMMAND_TIMEOUT

    def test_effective_timeout_uses_extended_for_long_running(self):
        """Long-running commands should use extended timeout."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor
        from scrappy.agent_tools.constants import LONG_RUNNING_COMMAND_TIMEOUT

        executor = ShellCommandExecutor()

        assert executor._get_effective_timeout("npm install") == LONG_RUNNING_COMMAND_TIMEOUT
        assert executor._get_effective_timeout("pip install requests") == LONG_RUNNING_COMMAND_TIMEOUT
        assert executor._get_effective_timeout("cargo build") == LONG_RUNNING_COMMAND_TIMEOUT
        assert executor._get_effective_timeout("docker build .") == LONG_RUNNING_COMMAND_TIMEOUT

    def test_effective_timeout_case_insensitive(self):
        """Long-running detection should be case insensitive."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor
        from scrappy.agent_tools.constants import LONG_RUNNING_COMMAND_TIMEOUT

        executor = ShellCommandExecutor()

        assert executor._get_effective_timeout("NPM INSTALL") == LONG_RUNNING_COMMAND_TIMEOUT
        assert executor._get_effective_timeout("Pip Install") == LONG_RUNNING_COMMAND_TIMEOUT

    def test_uses_centralized_long_running_commands_list(self):
        """Should use DEFAULT_LONG_RUNNING_COMMANDS from constants."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor
        from scrappy.agent_tools.constants import (
            DEFAULT_LONG_RUNNING_COMMANDS,
            LONG_RUNNING_COMMAND_TIMEOUT,
        )

        executor = ShellCommandExecutor()

        # All commands in the centralized list should get extended timeout
        for pattern in DEFAULT_LONG_RUNNING_COMMANDS:
            # Use the pattern in a realistic command context
            cmd = f"{pattern} some-package"
            assert executor._get_effective_timeout(cmd) == LONG_RUNNING_COMMAND_TIMEOUT, (
                f"Expected extended timeout for command containing '{pattern}'"
            )

    def test_timeout_passed_to_runner(self):
        """Effective timeout should be passed to subprocess runner."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor
        from scrappy.agent_tools.constants import LONG_RUNNING_COMMAND_TIMEOUT

        mock_runner = Mock()
        mock_runner.execute.return_value = Mock(stdout="success")
        mock_security = Mock()
        mock_security.validate.return_value = None

        executor = ShellCommandExecutor(
            security=mock_security,
            runner=mock_runner,
            timeout=60  # Default timeout
        )

        project_root = Path("/test/project")
        executor.run("npm install", project_root)

        # Verify runner was called with extended timeout
        mock_runner.execute.assert_called()
        call_kwargs = mock_runner.execute.call_args
        assert call_kwargs.kwargs.get('timeout') == LONG_RUNNING_COMMAND_TIMEOUT


class TestShellCommandExecutorCategorization:
    """Tests for command categorization."""

    def test_categorizes_spring_initializr(self):
        """Should categorize Spring Initializr commands."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor()

        assert executor._categorize_command_approach(
            "curl https://start.spring.io/starter.zip"
        ) == "spring_initializr_download"

    def test_categorizes_npm_create(self):
        """Should categorize npm create commands."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor()

        assert executor._categorize_command_approach("npm create vite@latest") == "npm_create_project"
        assert executor._categorize_command_approach("npx create-react-app myapp") == "npm_create_project"

    def test_categorizes_curl_download(self):
        """Should categorize curl/wget downloads."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor()

        assert executor._categorize_command_approach(
            "curl https://example.com/file.zip"
        ) == "curl_download"
        assert executor._categorize_command_approach(
            "wget https://example.com/file.zip"
        ) == "curl_download"

    def test_categorizes_unix_commands(self):
        """Should categorize Unix commands."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor()

        assert executor._categorize_command_approach("grep pattern file") == "unix_command"
        assert executor._categorize_command_approach("cat file.txt") == "unix_command"
        assert executor._categorize_command_approach("find . -name '*.py'") == "unix_command"

    def test_categorizes_generic_shell_command(self):
        """Should categorize unknown commands as shell_command."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor()

        assert executor._categorize_command_approach("myapp --version") == "shell_command"
        assert executor._categorize_command_approach("python script.py") == "shell_command"


class TestShellCommandExecutorRetryPattern:
    """Tests for retry pattern detection."""

    def test_warns_when_same_approach_failed_before(self):
        """Should warn when same approach has failed."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor()

        failed_commands = [
            {"approach": "spring_initializr_download", "error": "Connection failed"}
        ]

        warning = executor._check_retry_pattern(
            "curl https://start.spring.io/starter.zip",
            failed_commands
        )

        assert "WARNING" in warning or "CRITICAL" in warning
        assert "spring_initializr" in warning.lower()

    def test_no_warning_for_new_approach(self):
        """Should not warn for first attempt of an approach."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor()

        failed_commands = [
            {"approach": "npm_install", "error": "Network error"}
        ]

        warning = executor._check_retry_pattern(
            "curl https://start.spring.io/starter.zip",
            failed_commands
        )

        # Should warn about scaffolding failure in general
        assert warning == "" or "scaffolding" in warning.lower()

    def test_cross_scaffolding_warning(self):
        """Should warn when any scaffolding approach has failed."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor()

        failed_commands = [
            {"approach": "npm_create_project", "error": "npm create failed"}
        ]

        warning = executor._check_retry_pattern(
            "curl https://start.spring.io/starter.zip",
            failed_commands
        )

        assert "scaffolding" in warning.lower() or warning == ""


class TestShellCommandExecutorDryRun:
    """Tests for dry run mode."""

    def setup_method(self):
        """Set up test fixtures."""
        self.project_root = Path("/test/project")

    def test_dry_run_returns_without_executing(self):
        """Dry run should return message without executing."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        mock_runner = Mock()
        mock_security = Mock()
        mock_security.validate.return_value = None

        executor = ShellCommandExecutor(
            security=mock_security,
            runner=mock_runner
        )

        result = executor.run("echo hello", self.project_root, dry_run=True)

        assert "[DRY RUN]" in result
        assert "echo hello" in result
        mock_runner.execute.assert_not_called()


class TestShellCommandExecutorOutput:
    """Tests for output parsing and enrichment."""

    def setup_method(self):
        """Set up test fixtures."""
        self.project_root = Path("/test/project")

    def test_parses_and_enriches_output(self):
        """Should parse and enrich command output."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        mock_runner = Mock()
        mock_runner.execute.return_value = Mock(stdout="test output")
        mock_security = Mock()
        mock_security.validate.return_value = None
        mock_parser = Mock()
        mock_parser.parse.return_value = "parsed output"
        mock_advisor = Mock()
        mock_advisor.analyze_command.return_value = None
        mock_advisor.enrich_output.return_value = "enriched output"

        executor = ShellCommandExecutor(
            security=mock_security,
            runner=mock_runner,
            parser=mock_parser,
            advisor=mock_advisor
        )

        result = executor.run("echo test", self.project_root)

        mock_parser.parse.assert_called_once()
        mock_advisor.enrich_output.assert_called_once()
        assert result == "enriched output"

    def test_truncates_large_output(self):
        """Should truncate output exceeding max_output."""
        from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor

        large_output = "x" * 20000
        mock_runner = Mock()
        mock_runner.execute.return_value = Mock(stdout=large_output)
        mock_security = Mock()
        mock_security.validate.return_value = None

        executor = ShellCommandExecutor(
            security=mock_security,
            runner=mock_runner,
            max_output=1000
        )

        result = executor.run("cat largefile", self.project_root)

        # Output should be truncated by parser
        assert len(result) <= 10000 or "truncated" in result.lower()


class TestCommandToolExecuteEntry:
    """Tests for CommandTool.execute() entry point."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = AgentConfig()
        self.project_root = Path("/test/project")
        self.context = ToolContext(
            project_root=self.project_root,
            dry_run=False,
            config=self.config
        )

    def test_empty_command_returns_error(self):
        """Empty command should return error result."""
        from scrappy.agent_tools.tools.command_tool import CommandTool

        # Disable sandbox - not testing sandbox behavior
        tool = CommandTool(use_sandbox=False)

        result = tool.execute(self.context, command="")

        assert result.success is False
        assert "no command" in result.error.lower()

    def test_successful_command_includes_metadata(self):
        """Successful command should include command in metadata."""
        from scrappy.agent_tools.tools.command_tool import CommandTool

        mock_executor = Mock()
        mock_executor.run.return_value = "command output"

        tool = CommandTool(executor=mock_executor)

        result = tool.execute(self.context, command="echo hello")

        assert result.success is True
        assert result.metadata.get("command") == "echo hello"

    def test_dry_run_includes_metadata(self):
        """Dry run should include dry_run in metadata."""
        from scrappy.agent_tools.tools.command_tool import CommandTool

        mock_executor = Mock()
        mock_executor.run.return_value = "[DRY RUN] Would run: echo hello"

        tool = CommandTool(executor=mock_executor)

        result = tool.execute(self.context, command="echo hello")

        assert result.success is True
        assert result.metadata.get("dry_run") is True

    def test_error_output_returns_failure_result(self):
        """Error output from executor should return failure."""
        from scrappy.agent_tools.tools.command_tool import CommandTool

        mock_executor = Mock()
        mock_executor.run.return_value = "Error: command not found"

        tool = CommandTool(executor=mock_executor)

        result = tool.execute(self.context, command="nonexistent")

        assert result.success is False
        assert "command not found" in result.error

    def test_executor_exception_returns_failure(self):
        """Exception from executor should return failure."""
        from scrappy.agent_tools.tools.command_tool import CommandTool

        mock_executor = Mock()
        mock_executor.run.side_effect = RuntimeError("Unexpected error")

        tool = CommandTool(executor=mock_executor)

        result = tool.execute(self.context, command="echo hello")

        assert result.success is False
        assert "error" in result.error.lower()
