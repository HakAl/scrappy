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

        # Mock subprocess to raise an exception
        with patch('subprocess.Popen', side_effect=OSError("Permission denied")):
            result = tool.execute(self.context, command="echo test")

        assert result.success is False
        assert "error" in result.error.lower()

    def test_error_output_returns_failure(self):
        """Should return failure when command output starts with Error."""
        from src.agent_tools.tools.command_tool import CommandTool

        tool = CommandTool(self.config)

        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = 1
            mock_process.stdout.readline.side_effect = ["Error: command failed\n", ""]
            mock_popen.return_value = mock_process

            result = tool.execute(self.context, command="failing_cmd")

        assert result.success is False
        assert "command failed" in result.error
