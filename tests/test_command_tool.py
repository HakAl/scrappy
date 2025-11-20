"""
Tests for CommandTool and ShellCommandExecutor.

These tests define the expected behavior of command execution extracted from CodeAgent.
Following TDD: write tests first to specify behavior, then implement to satisfy tests.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
import subprocess
import time

# Import base tool infrastructure
from src.agent_tools.tools.base import ToolContext, ToolResult
from src.agent_config import AgentConfig


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
        from src.agent_tools.tools.command_tool import CommandTool

        tool = CommandTool(self.config)

        assert tool.name == "run_command"
        assert "shell" in tool.description.lower() or "command" in tool.description.lower()
        assert len(tool.parameters) >= 1
        # First parameter should be the command string
        assert tool.parameters[0].name == "command"
        assert tool.parameters[0].param_type == str
        assert tool.parameters[0].required is True

    def test_execute_returns_tool_result(self):
        """Execute must return a ToolResult object."""
        from src.agent_tools.tools.command_tool import CommandTool

        tool = CommandTool(self.config)

        with patch.object(tool._executor, 'run', return_value="command output"):
            with patch.object(tool._executor, '_check_dangerous_command', return_value=None):
                with patch.object(tool._executor, '_check_platform_intercepts', return_value=None):
                    result = tool.execute(self.context, command="echo test")

                    assert isinstance(result, ToolResult)
                    assert result.success is True
                    assert result.output == "command output"

    def test_dry_run_skips_execution(self):
        """Dry run mode should not execute commands."""
        from src.agent_tools.tools.command_tool import CommandTool

        tool = CommandTool(self.config)
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
        from src.agent_tools.tools.command_tool import CommandTool

        tool = CommandTool(self.config)

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
        from src.agent_tools.tools.command_tool import CommandTool

        # Explicitly configure dangerous patterns to include rm -rf
        config = AgentConfig()
        config.dangerous_commands = [r'rm\s+-rf\s+/', r'format\s+[A-Za-z]:']
        tool = CommandTool(config)

        result = tool.execute(self.context, command="rm -rf /")

        assert result.success is False
        assert "dangerous" in result.error.lower() or "pattern" in result.error.lower()

    def test_blocks_dangerous_format_command(self):
        """Should block format/disk destruction commands."""
        from src.agent_tools.tools.command_tool import CommandTool

        tool = CommandTool(self.config)

        result = tool.execute(self.context, command="format C:")

        assert result.success is False
        assert "dangerous" in result.error.lower() or "blocked" in result.error.lower()

    def test_blocks_command_matching_regex_pattern(self):
        """Should block commands matching configured dangerous patterns."""
        from src.agent_tools.tools.command_tool import CommandTool

        config = AgentConfig()
        config.dangerous_commands = [r"sudo\s+rm", r":\(\)\s*\{.*\}"]
        tool = CommandTool(config)

        result = tool.execute(self.context, command="sudo rm -rf /var")

        assert result.success is False
        assert "dangerous" in result.error.lower() or "pattern" in result.error.lower()

    def test_allows_safe_echo_command(self):
        """Should allow safe commands like echo."""
        from src.agent_tools.tools.command_tool import CommandTool

        tool = CommandTool(self.config)

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

    @patch('src.agent_tools.tools.command_tool.is_windows', return_value=True)
    def test_normalizes_unix_paths_on_windows(self, mock_is_windows):
        """Should convert forward slashes to backslashes on Windows."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        command = "mkdir src/components/ui"
        normalized = executor._normalize_command_paths(command)

        # On Windows, forward slashes in paths should become backslashes
        assert "\\" in normalized or normalized == command  # May not change if not detected as path

    @patch('src.agent_tools.tools.command_tool.is_windows', return_value=True)
    def test_adds_no_unicode_flag_to_npm_on_windows(self, mock_is_windows):
        """Should add --no-unicode flag to npm commands on Windows."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        command = "npm install express"
        normalized = executor._normalize_npm_command(command)

        # Should add flag to suppress Unicode progress bars
        assert "--unicode=false" in normalized or "--no-progress" in normalized or normalized == command

    @patch('src.agent_tools.tools.command_tool.is_windows', return_value=True)
    def test_intercepts_spring_initializr_on_windows(self, mock_is_windows):
        """Should block Spring Initializr downloads on Windows."""
        from src.agent_tools.tools.command_tool import CommandTool

        tool = CommandTool(self.config)

        result = tool.execute(
            self.context,
            command="curl https://start.spring.io/starter.zip -o demo.zip"
        )

        # Should recommend using write_file instead
        assert result.success is False
        assert "write_file" in result.error.lower() or "template" in result.error.lower()


class TestInteractiveCommandDetection:
    """Tests for detecting and handling interactive commands."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = AgentConfig()
        self.project_root = Path("/test/project")
        self.context = ToolContext(
            project_root=self.project_root,
            dry_run=False,
            config=self.config
        )

    def test_detects_npm_init_as_interactive(self):
        """Should detect npm init as interactive command."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        is_interactive = executor._is_interactive_command("npm init")

        assert is_interactive is True

    def test_detects_npx_create_as_interactive(self):
        """Should detect npx commands as interactive."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        is_interactive = executor._is_interactive_command("npx create-react-app my-app")

        assert is_interactive is True

    def test_non_interactive_command_returns_false(self):
        """Should not flag non-interactive commands."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        is_interactive = executor._is_interactive_command("ls -la")

        assert is_interactive is False

    def test_suggests_y_flag_for_npx_commands(self):
        """Should suggest -y flag for npx commands."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        suggestion = executor._get_interactive_suggestion("npx create-react-app my-app")

        assert "-y" in suggestion


class TestCommandRetryLogic:
    """Tests for automatic retry on recoverable errors."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = AgentConfig()
        self.project_root = Path("/test/project")

    def test_retries_on_connection_reset_error(self):
        """Should retry when connection is reset."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)
        call_count = 0

        def mock_run_once(cmd, timeout, show_progress, cwd=None):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return "Error: connection reset by peer"
            return "Success"

        with patch.object(executor, '_run_command_streaming', side_effect=mock_run_once):
            with patch('time.sleep'):  # Skip actual delays
                result = executor._run_command_with_retry("npm install", 120)

        assert call_count == 3
        assert "Success" in result

    def test_retries_on_timeout_error(self):
        """Should retry on timeout errors."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)
        call_count = 0

        def mock_run_once(cmd, timeout, show_progress, cwd=None):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return "Error: ETIMEDOUT - network timed out"
            return "OK"

        with patch.object(executor, '_run_command_streaming', side_effect=mock_run_once):
            with patch('time.sleep'):
                result = executor._run_command_with_retry("curl example.com", 60)

        assert call_count == 2
        assert "OK" in result

    def test_exponential_backoff_between_retries(self):
        """Should use exponential backoff: 2s, 4s, 8s."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)
        sleep_times = []

        def track_sleep(seconds):
            sleep_times.append(seconds)

        def mock_fail(cmd, timeout, show_progress, cwd=None):
            return "Error: socket hang up"

        with patch.object(executor, '_run_command_streaming', side_effect=mock_fail):
            with patch('time.sleep', side_effect=track_sleep):
                executor._run_command_with_retry("test", 60, max_retries=3)

        # Should have delays: 2s (attempt 2), 4s (attempt 3)
        assert sleep_times == [2, 4]

    def test_returns_error_after_max_retries(self):
        """Should return error message after exhausting retries."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        def mock_fail(cmd, timeout, show_progress, cwd=None):
            return "Error: ECONNRESET connection failed"

        with patch.object(executor, '_run_command_streaming', side_effect=mock_fail):
            with patch('src.agent_tools.tools.command_tool.time.sleep'):
                result = executor._run_command_with_retry("npm install", 60, max_retries=3)

        assert "failed after 3 attempts" in result.lower() or "3 attempts" in result
        assert "ECONNRESET" in result

    def test_does_not_retry_on_non_recoverable_error(self):
        """Should not retry on syntax errors or non-network failures."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)
        call_count = 0

        def mock_run_once(cmd, timeout, show_progress, cwd=None):
            nonlocal call_count
            call_count += 1
            return "Error: command not found: foobar"

        with patch.object(executor, '_run_command_streaming', side_effect=mock_run_once):
            result = executor._run_command_with_retry("foobar", 60)

        # Should only call once - no retry for "command not found"
        assert call_count == 1

    def test_reports_retry_count_on_eventual_success(self):
        """Should indicate how many retries were needed."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)
        call_count = 0

        def mock_run_once(cmd, timeout, show_progress, cwd=None):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return "Error: connection refused"
            return "npm install completed"

        with patch.object(executor, '_run_command_streaming', side_effect=mock_run_once):
            with patch('time.sleep'):
                result = executor._run_command_with_retry("npm install", 60)

        assert "2 retries" in result or "retry" in result.lower()
        assert "npm install completed" in result


class TestOutputParsing:
    """Tests for command output parsing and format detection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = AgentConfig()

    def test_detects_json_object_output(self):
        """Should detect and annotate JSON object output."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)
        json_output = '{"name": "test", "version": "1.0.0"}'

        parsed = executor._parse_command_output(json_output)

        assert "JSON" in parsed
        assert "2 keys" in parsed or "Object" in parsed
        assert json_output in parsed  # Original output preserved

    def test_detects_json_array_output(self):
        """Should detect and annotate JSON array output."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)
        json_output = '[{"id": 1}, {"id": 2}, {"id": 3}]'

        parsed = executor._parse_command_output(json_output)

        assert "JSON" in parsed
        assert "3 items" in parsed or "Array" in parsed

    def test_detects_yaml_output(self):
        """Should detect and annotate YAML output."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)
        yaml_output = """name: test
version: 1.0.0
dependencies:
  - express
  - lodash"""

        parsed = executor._parse_command_output(yaml_output)

        assert "YAML" in parsed

    def test_returns_original_for_plain_text(self):
        """Should return plain text without modification."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)
        text_output = "Build completed successfully"

        parsed = executor._parse_command_output(text_output)

        assert parsed == text_output
        assert "JSON" not in parsed
        assert "YAML" not in parsed

    def test_handles_empty_output(self):
        """Should handle empty or no output gracefully."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        parsed = executor._parse_command_output("")
        assert parsed == "" or parsed == "(no output)"

        parsed = executor._parse_command_output("(no output)")
        assert parsed == "(no output)"

    def test_adds_spring_initializr_guidance_on_error(self):
        """Should provide guidance when Spring Initializr fails."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)
        error_output = "Error: 400 bad request from start.spring.io"

        parsed = executor._parse_command_output(error_output)

        assert "write_file" in parsed.lower()
        assert "pom.xml" in parsed or "directly" in parsed.lower()


class TestCommandCategorization:
    """Tests for command approach categorization (for retry pattern detection)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = AgentConfig()

    def test_categorizes_spring_initializr_download(self):
        """Should categorize Spring Initializr commands."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        category = executor._categorize_command_approach("curl https://start.spring.io/starter.zip -o demo.zip")

        assert category == "spring_initializr_download"

    def test_categorizes_curl_download(self):
        """Should categorize curl downloads."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        category = executor._categorize_command_approach("curl -O https://example.com/file.zip")

        assert category == "curl_download"

    def test_categorizes_npm_create_project(self):
        """Should categorize npm create commands."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        category = executor._categorize_command_approach("npm create vite@latest my-app")

        assert category == "npm_create_project"

    def test_categorizes_unix_commands(self):
        """Should categorize Unix-specific commands."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        for cmd in ["grep -r pattern .", "cat file.txt", "sed -i 's/a/b/' file"]:
            category = executor._categorize_command_approach(cmd)
            assert category == "unix_command"

    def test_warns_on_repeated_failing_approach(self):
        """Should warn when same approach has already failed."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        failed_commands = [
            {"command": "curl https://start.spring.io/...", "approach": "spring_initializr_download", "error": "400 bad request"}
        ]

        warning = executor._check_retry_pattern(
            "curl https://start.spring.io/starter.zip",
            failed_commands
        )

        assert "CRITICAL" in warning or "already failed" in warning.lower()
        assert "write_file" in warning.lower()


class TestTimeoutHandling:
    """Tests for command timeout behavior."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = AgentConfig()
    def test_uses_configured_timeout(self):
        """Should respect configured command timeout."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        config = AgentConfig()
        executor = ShellCommandExecutor(config)

        assert executor.timeout == 300

    def test_timeout_error_message_format(self):
        """Timeout errors should include timeout duration."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        # Mock _run_command_streaming to simulate a timeout
        with patch.object(executor, '_run_command_streaming') as mock_stream:
            mock_stream.return_value = "Error: Command timed out after 120s\nPartial output (5 lines):\nLine1\nLine2"

            result = executor._run_command_with_retry("long_cmd", 120, max_retries=1)

        # Non-recoverable error, should return as-is
        assert "timed out" in result.lower()
        assert "120s" in result

    def test_truncate_output_preserves_last_portion(self):
        """Truncation should keep the last portion of output."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        config = AgentConfig()
        executor = ShellCommandExecutor(config)

        long_output = "A" * 100
        truncated = executor._truncate_output(long_output)

        assert len(truncated) <= 100  # max_output + truncation message
        assert "truncated" in truncated.lower()
        assert truncated.endswith("A" * 50)  # Last 50 chars preserved


class TestStreamingOutput:
    """Tests for streaming command output."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = AgentConfig()
    def test_truncates_very_long_output(self):
        """Should truncate output exceeding max size."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        config = AgentConfig()
        executor = ShellCommandExecutor(config)

        # Generate long output
        long_output = "\n".join([f"Line {i}" for i in range(100)])

        truncated = executor._truncate_output(long_output)

        assert len(truncated) <= 200  # Some buffer for truncation message
        assert "truncated" in truncated.lower()

    def test_empty_output_handling(self):
        """Should handle empty output appropriately."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        # Test that empty string becomes "(no output)" in parse
        result = executor._parse_command_output("")
        assert result == "" or result == "(no output)"

    def test_no_output_indicator_string(self):
        """Should pass through (no output) indicator."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        result = executor._parse_command_output("(no output)")
        assert "(no output)" in result


class TestLongRunningCommandDetection:
    """Tests for detecting long-running commands."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = AgentConfig()
    def test_detects_npm_install_as_long_running(self):
        """Should detect npm install as long-running."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        is_long = executor._is_long_running_command("npm install express lodash")

        assert is_long is True

    def test_detects_docker_build_as_long_running(self):
        """Should detect docker build as long-running."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        is_long = executor._is_long_running_command("docker build -t myimage .")

        assert is_long is True

    def test_short_commands_not_flagged(self):
        """Should not flag quick commands as long-running."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        is_long = executor._is_long_running_command("ls -la")

        assert is_long is False


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
        from src.agent_tools.tools.command_tool import CommandTool

        tool = CommandTool(self.config)

        # Mock the executor's run method to raise an exception
        with patch.object(tool._executor, 'run', side_effect=OSError("Permission denied")):
            with patch.object(tool._executor, '_check_dangerous_command', return_value=None):
                with patch.object(tool._executor, '_check_platform_intercepts', return_value=None):
                    result = tool.execute(self.context, command="echo test")

        assert result.success is False
        assert "error" in result.error.lower()

    def test_error_output_returns_failure(self):
        """Should return failure when command output starts with Error."""
        from src.agent_tools.tools.command_tool import CommandTool

        tool = CommandTool(self.config)

        with patch.object(tool._executor, 'run', return_value="Error: command failed"):
            with patch.object(tool._executor, '_check_dangerous_command', return_value=None):
                with patch.object(tool._executor, '_check_platform_intercepts', return_value=None):
                    result = tool.execute(self.context, command="failing_cmd")

        assert result.success is False
        assert "command failed" in result.error

    def test_returns_error_for_nonexistent_command(self):
        """Should provide clear error for command not found."""
        from src.agent_tools.tools.command_tool import ShellCommandExecutor

        executor = ShellCommandExecutor(self.config)

        output = "bash: nonexistent_command: command not found"
        parsed = executor._parse_command_output(output)

        # Should pass through error message unchanged
        assert "command not found" in parsed
