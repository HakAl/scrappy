"""
Tests for agent path escaping and command construction.

These tests verify that the agent properly handles paths across different platforms
and shell environments. Each test exercises actual code behavior, not just string
manipulation.

Key issues being tested:
- PowerShell cmdlets failing in cmd.exe subprocess
- Path normalization not handling all command syntaxes
- Platform-specific command validation
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.agent import CodeAgent
from src.platform_utils import (
    normalize_command_paths,
    validate_command_for_platform,
    get_python_fallback,
    normalize_path_for_shell
)
from src.agent_tools.tools.file_tools import WriteFileTool
from src.agent_tools.tools.base import ToolContext


class TestPathNormalizationWindows:
    """Test path normalization on Windows platform."""



    @pytest.mark.unit
    @patch('src.platform_utils.is_windows', return_value=True)
    def test_powershell_path_parameter_not_normalized(self, mock_is_win):
        """BUG: PowerShell -Path syntax is not normalized - this test should FAIL."""
        command = 'New-Item -ItemType Directory -Path "frontend/src/components" -Force'
        normalized, was_modified, msg = normalize_command_paths(command)

        # Extract path from the command
        import re
        match = re.search(r'-Path\s+"([^"]+)"', normalized)
        assert match is not None, f"Could not find -Path in: {normalized}"

        path_value = match.group(1)
        # This SHOULD have backslashes but currently doesn't
        assert '\\' in path_value, f"Path not normalized: {path_value}"
        assert '/' not in path_value, f"Forward slashes still present: {path_value}"




class TestPathNormalizationUnix:
    """Test path normalization on Unix/Mac platforms."""





class TestPowerShellCmdletHandling:
    """Test handling of PowerShell-specific cmdlets."""






class TestCommandExecutionIntegration:
    """Integration tests for command execution through the agent."""

    @pytest.fixture
    def agent(self, temp_project_dir):
        """Create agent for testing."""
        mock_adapter = MagicMock()
        mock_adapter.list_providers.return_value = ["cerebras"]
        mock_adapter.get_preferred_provider.return_value = (None, None)

        return CodeAgent(
            orchestrator=mock_adapter,
            project_path=str(temp_project_dir)
        )

    @pytest.mark.unit
    @patch('src.agent_tools.tools.command_tool.subprocess.Popen')
    def test_command_executes_in_project_directory(self, mock_popen, agent, temp_project_dir):
        """Commands must execute with cwd set to project root."""
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ['', '']
        mock_process.stderr.readline.side_effect = ['', '']
        mock_process.poll.return_value = 0
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        agent._tool_run_command('mkdir test_dir')

        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs['cwd'] == str(temp_project_dir)

    @pytest.mark.unit
    @patch('subprocess.Popen')
    def test_path_not_corrupted_in_execution(self, mock_popen, agent, temp_project_dir):
        """Paths should not be corrupted when passed to subprocess."""
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ['', '']
        mock_process.stderr.readline.side_effect = ['', '']
        mock_process.poll.return_value = 0
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        # Command with nested path
        agent._tool_run_command('mkdir frontend\\src\\components')

        executed_command = mock_popen.call_args[0][0]

        # Path structure must be preserved
        assert 'frontend' in executed_command
        # Should not have absolute path indicators
        assert not executed_command.strip().startswith('\\')
        assert 'C:\\' not in executed_command


class TestFileToolPathSafety:
    """Test file tools handle paths safely."""

    @pytest.fixture
    def context(self, temp_project_dir):
        """Create tool context."""
        return ToolContext(project_root=temp_project_dir, dry_run=False)

    @pytest.mark.unit
    def test_empty_content_rejected(self, context):
        """WriteFileTool must reject empty content."""
        tool = WriteFileTool()
        result = tool.execute(
            context=context,
            path='test/file.txt',
            content=''
        )

        assert result.success is False
        assert 'empty' in result.error.lower() or 'content' in result.error.lower()

    @pytest.mark.unit
    def test_path_traversal_rejected(self, context):
        """Paths attempting to escape project root must be rejected."""
        tool = WriteFileTool()

        # Attempt path traversal
        result = tool.execute(
            context=context,
            path='../../../etc/passwd',
            content='malicious'
        )

        assert result.success is False
        assert 'outside' in result.error.lower() or 'safe' in result.error.lower()

    @pytest.mark.unit
    def test_absolute_path_rejected(self, context):
        """Absolute paths should be rejected on ALL platforms.

        SECURITY: This is a critical security test. Absolute paths in ANY format
        (Windows or Unix) must be rejected regardless of what platform the code
        runs on. On Unix, a Windows path like 'C:\\Windows\\test.txt' would be
        treated as a relative path and could create files with those literal names.
        This is a security hole that must be closed.
        """
        tool = WriteFileTool()

        # Windows absolute path - MUST be rejected on ALL platforms
        result = tool.execute(
            context=context,
            path='C:\\Windows\\System32\\test.txt',
            content='test'
        )
        assert result.success is False
        assert 'absolute' in result.error.lower()

        # Windows path with forward slashes - also absolute
        result = tool.execute(
            context=context,
            path='D:/Users/test.txt',
            content='test'
        )
        assert result.success is False
        assert 'absolute' in result.error.lower()

        # Windows UNC path
        result = tool.execute(
            context=context,
            path='\\\\server\\share\\file.txt',
            content='test'
        )
        assert result.success is False
        assert 'absolute' in result.error.lower()

    @pytest.mark.unit
    def test_unix_absolute_path_rejected(self, context):
        """Unix/Mac absolute paths should be rejected."""
        tool = WriteFileTool()

        # Unix absolute path - should be rejected on ALL platforms
        result = tool.execute(
            context=context,
            path='/etc/passwd',
            content='test'
        )

        assert result.success is False
        assert 'absolute' in result.error.lower() or 'outside' in result.error.lower()

    @pytest.mark.unit
    def test_relative_path_accepted(self, context, temp_project_dir):
        """Valid relative paths should be accepted."""
        tool = WriteFileTool()
        result = tool.execute(
            context=context,
            path='src/test.txt',
            content='valid content'
        )

        assert result.success is True
        # File should be created
        assert (temp_project_dir / 'src' / 'test.txt').exists()


class TestCrossPlatformConsistency:
    """Test that behavior is consistent across platforms."""

    @pytest.mark.unit
    def test_path_separator_detection(self):
        """Path separator should be detected correctly."""
        from src.platform_utils import is_windows
        import os

        # Should match the actual platform
        if os.name == 'nt':
            assert is_windows() is True
        else:
            assert is_windows() is False


