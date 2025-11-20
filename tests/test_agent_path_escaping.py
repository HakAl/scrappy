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
    def test_mkdir_forward_slashes_normalized(self, mock_is_win):
        """mkdir command with forward slashes should be normalized to backslashes."""
        command = 'mkdir frontend/src/components'
        normalized, was_modified, msg = normalize_command_paths(command)

        assert was_modified is True
        assert 'frontend\\src\\components' in normalized
        assert '/' not in normalized

    @pytest.mark.unit
    @patch('src.platform_utils.is_windows', return_value=True)
    def test_copy_command_paths_normalized(self, mock_is_win):
        """copy command paths should be normalized."""
        command = 'copy src/file.txt dest/file.txt'
        normalized, was_modified, msg = normalize_command_paths(command)

        assert was_modified is True
        assert 'src\\file.txt' in normalized
        assert 'dest\\file.txt' in normalized

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

    @pytest.mark.unit
    @patch('src.platform_utils.is_windows', return_value=True)
    def test_quoted_path_with_spaces_preserved(self, mock_is_win):
        """Paths with spaces in quotes should be preserved."""
        command = 'mkdir "my project/src/main"'
        normalized, was_modified, msg = normalize_command_paths(command)

        assert 'my project' in normalized
        assert '\\' in normalized or '/' not in normalized

    @pytest.mark.unit
    @patch('src.platform_utils.is_windows', return_value=True)
    def test_url_not_normalized(self, mock_is_win):
        """URLs should not have slashes converted."""
        command = 'curl https://example.com/api/data'
        normalized, was_modified, msg = normalize_command_paths(command)

        # URLs should be preserved
        assert 'https://example.com/api/data' in normalized


class TestPathNormalizationUnix:
    """Test path normalization on Unix/Mac platforms."""

    @pytest.mark.unit
    @patch('src.platform_utils.is_windows', return_value=False)
    def test_backslashes_normalized_to_forward_slashes(self, mock_is_win):
        """On Unix, backslashes in paths should become forward slashes."""
        path = 'frontend\\src\\components'
        normalized = normalize_path_for_shell(path)

        assert '/' in normalized
        assert '\\' not in normalized
        assert normalized == 'frontend/src/components'

    @pytest.mark.unit
    @patch('src.platform_utils.is_windows', return_value=False)
    def test_mkdir_on_unix_keeps_forward_slashes(self, mock_is_win):
        """Unix mkdir should keep forward slashes."""
        command = 'mkdir -p frontend/src/components'
        normalized, was_modified, msg = normalize_command_paths(command)

        # Should not be modified on Unix
        assert '/' in normalized
        assert '\\' not in normalized

    @pytest.mark.unit
    @patch('src.platform_utils.is_windows', return_value=False)
    def test_unix_commands_validated(self, mock_is_win):
        """Unix commands should be valid on Unix platform."""
        commands = [
            'mkdir -p frontend/src',
            'cp -r src/ dest/',
            'rm -rf build/',
            'ls -la src/',
        ]

        for cmd in commands:
            is_valid, warning = validate_command_for_platform(cmd)
            assert is_valid is True, f"Unix command '{cmd}' rejected on Unix: {warning}"


class TestPowerShellCmdletHandling:
    """Test handling of PowerShell-specific cmdlets."""

    @pytest.mark.unit
    @patch('src.platform_utils.is_windows', return_value=True)
    def test_new_item_cmdlet_not_handled(self, mock_is_win):
        """BUG: New-Item PowerShell cmdlet is not rejected or converted - should FAIL."""
        ps_command = 'New-Item -ItemType Directory -Path "frontend\\src\\components" -Force'

        is_valid, warning = validate_command_for_platform(ps_command)
        fallback = get_python_fallback(ps_command, '/fake/path')

        # Either must be rejected OR have a fallback
        # Currently neither is true, so command fails with "not recognized"
        has_handling = (not is_valid) or (fallback is not None)

        assert has_handling, (
            f"New-Item cmdlet passes validation ({is_valid}) "
            f"but has no fallback ({fallback}). "
            f"Will fail with 'not recognized' in cmd.exe"
        )

    @pytest.mark.unit
    @patch('src.platform_utils.is_windows', return_value=True)
    def test_remove_item_cmdlet_not_handled(self, mock_is_win):
        """Remove-Item PowerShell cmdlet should be handled."""
        ps_command = 'Remove-Item -Path "frontend\\src\\components" -Recurse'

        is_valid, warning = validate_command_for_platform(ps_command)
        fallback = get_python_fallback(ps_command, '/fake/path')

        has_handling = (not is_valid) or (fallback is not None)
        assert has_handling, "Remove-Item not handled"

    @pytest.mark.unit
    @patch('src.platform_utils.is_windows', return_value=True)
    def test_copy_item_cmdlet_not_handled(self, mock_is_win):
        """Copy-Item PowerShell cmdlet should be handled."""
        ps_command = 'Copy-Item -Path "src.txt" -Destination "dest.txt"'

        is_valid, warning = validate_command_for_platform(ps_command)
        fallback = get_python_fallback(ps_command, '/fake/path')

        has_handling = (not is_valid) or (fallback is not None)
        assert has_handling, "Copy-Item not handled"

    @pytest.mark.unit
    @patch('src.platform_utils.is_windows', return_value=True)
    def test_cmd_mkdir_is_valid(self, mock_is_win):
        """Standard cmd.exe mkdir should be valid."""
        cmd_command = 'mkdir frontend\\src\\components'

        is_valid, warning = validate_command_for_platform(cmd_command)
        assert is_valid is True, f"cmd.exe mkdir rejected: {warning}"


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


