import pytest
import subprocess
from unittest.mock import MagicMock, Mock, patch
from pathlib import Path

from src.agent_tools.tools.git_tools import (
    GitTool, GitLogTool, GitStatusTool,
    GitDiffTool, GitBlameTool, GitShowTool,
    GitRecentChangesTool
)
from src.agent_tools.tools.base import ToolContext


# --- Fixtures ---

@pytest.fixture
def mock_context(tmp_path):
    """Creates a tool context with mocked config and memory."""
    context = MagicMock(spec=ToolContext)
    context.project_root = tmp_path
    context.is_safe_path = Mock(return_value=True)
    context.remember_git_operation = Mock()

    # Mock Configuration
    context.config = Mock()
    context.config.git_timeout = 10
    context.config.max_git_diff_size = 100
    context.config.max_git_blame_size = 100
    context.config.max_git_show_size = 100
    context.config.max_recent_commits = 5
    context.config.max_recent_changes_size = 200
    context.config.git_diff_timeout = 20

    return context


@pytest.fixture
def mock_subprocess():
    """Patches subprocess.run to prevent actual execution."""
    with patch("subprocess.run") as mock_run:
        # Default successful response
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "mock output"
        mock_run.return_value.stderr = ""
        yield mock_run


# --- Core GitTool Tests ---

class TestGitCore:
    """Tests the underlying _run_git_command logic shared by all tools."""

    def test_run_command_success(self, mock_context, mock_subprocess):
        tool = GitLogTool()  # Using LogTool to access the base method

        mock_subprocess.return_value.stdout = "success"

        success, output = tool._run_git_command(mock_context, ['status'])

        assert success is True
        assert output == "success"
        mock_subprocess.assert_called_with(
            ['git', 'status'],
            cwd=mock_context.project_root,
            capture_output=True,
            text=True,
            timeout=10  # From fixture config
        )

    def test_run_command_failure(self, mock_context, mock_subprocess):
        tool = GitLogTool()
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "fatal: not a git repository"

        success, output = tool._run_git_command(mock_context, ['status'])

        assert success is False
        assert "fatal" in output

    def test_run_command_timeout(self, mock_context, mock_subprocess):
        tool = GitLogTool()
        mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd='git', timeout=10)

        success, output = tool._run_git_command(mock_context, ['status'])

        assert success is False
        assert "timed out" in output


# --- Tool Specific Tests ---

class TestGitLogTool:
    def test_log_defaults(self, mock_context, mock_subprocess):
        tool = GitLogTool()
        tool.execute(mock_context)

        # Check default args
        args = mock_subprocess.call_args[0][0]
        assert args == ['git', 'log', '-10', '--oneline', '--decorate']

    def test_log_specific_file(self, mock_context, mock_subprocess):
        tool = GitLogTool()
        tool.execute(mock_context, n=5, file="src/main.py")

        args = mock_subprocess.call_args[0][0]
        # Check argument order
        assert '-5' in args
        assert '--' in args
        assert 'src/main.py' in args

    def test_log_unsafe_path(self, mock_context, mock_subprocess):
        tool = GitLogTool()
        mock_context.is_safe_path.return_value = False

        result = tool.execute(mock_context, file="../secret.txt")

        assert not result.success
        assert "outside project" in result.error
        mock_subprocess.assert_not_called()


class TestGitStatusTool:
    def test_status_standard(self, mock_context, mock_subprocess):
        tool = GitStatusTool()
        mock_subprocess.return_value.stdout = "M file.py"

        result = tool.execute(mock_context)

        assert result.success
        assert "M file.py" in result.output
        assert mock_subprocess.call_args[0][0] == ['git', 'status']

    def test_status_short(self, mock_context, mock_subprocess):
        tool = GitStatusTool()
        tool.execute(mock_context, short=True)

        args = mock_subprocess.call_args[0][0]
        assert '--short' in args

    def test_status_clean(self, mock_context, mock_subprocess):
        """Handle empty output (clean working directory)."""
        tool = GitStatusTool()
        mock_subprocess.return_value.stdout = ""

        result = tool.execute(mock_context)

        assert result.success
        assert "No changes" in result.output


class TestGitDiffTool:
    def test_diff_truncation(self, mock_context, mock_subprocess):
        """Should truncate output exceeding max_git_diff_size."""
        tool = GitDiffTool()
        # Config max is 100 (set in fixture)
        long_output = "A" * 200
        mock_subprocess.return_value.stdout = long_output

        result = tool.execute(mock_context)

        assert result.success
        assert len(result.output) < 200
        assert "truncated" in result.output
        assert result.metadata["truncated"] is True

    def test_diff_with_ref_and_file(self, mock_context, mock_subprocess):
        tool = GitDiffTool()
        tool.execute(mock_context, ref="HEAD~1", file="test.py")

        args = mock_subprocess.call_args[0][0]
        # git diff HEAD~1 -- test.py
        assert args == ['git', 'diff', 'HEAD~1', '--', 'test.py']


class TestGitBlameTool:
    def test_blame_lines_argument(self, mock_context, mock_subprocess):
        """Test -L argument construction."""
        tool = GitBlameTool()
        tool.execute(mock_context, file="test.py", lines="10,20")

        args = mock_subprocess.call_args[0][0]
        assert '-L' in args
        assert '10,20' in args

    def test_blame_unsafe_path(self, mock_context, mock_subprocess):
        tool = GitBlameTool()
        mock_context.is_safe_path.return_value = False

        result = tool.execute(mock_context, file="/etc/passwd")

        assert not result.success
        assert "outside project" in result.error


class TestGitShowTool:
    def test_show_validation_valid(self, mock_context, mock_subprocess):
        """Should accept valid commit hashes and refs."""
        tool = GitShowTool()
        valid_refs = ["a1b2c3d", "HEAD", "HEAD~1", "HEAD^", "master", "feature-branch"]

        for ref in valid_refs:
            tool.execute(mock_context, commit=ref)
            # Should verify call was made
            assert mock_subprocess.call_args[0][0][-1] == ref

    def test_show_validation_invalid(self, mock_context, mock_subprocess):
        """Should reject shell injection attempts."""
        tool = GitShowTool()
        invalid_refs = ["; rm -rf", "HEAD | cat", "test && echo"]

        for ref in invalid_refs:
            mock_subprocess.reset_mock()
            result = tool.execute(mock_context, commit=ref)

            assert not result.success
            assert "Invalid commit" in result.error
            # Subprocess should NEVER be called
            mock_subprocess.assert_not_called()


class TestGitRecentChangesTool:
    def test_enforce_commit_limit(self, mock_context, mock_subprocess):
        """Should clamp 'n' to config.max_recent_commits."""
        tool = GitRecentChangesTool()
        # Request 100, but limit is 5 (fixture)
        tool.execute(mock_context, n=100)

        args = mock_subprocess.call_args[0][0]
        # Should use -5, not -100
        assert '-5' in args

    def test_uses_diff_timeout(self, mock_context, mock_subprocess):
        """Should use the longer timeout setting for recent changes."""
        tool = GitRecentChangesTool()
        tool.execute(mock_context)

        # Fixture sets git_diff_timeout = 20
        assert mock_subprocess.call_args[1]['timeout'] == 20

    def test_format_output(self, mock_context, mock_subprocess):
        """Should handle the custom pretty format."""
        tool = GitRecentChangesTool()
        mock_subprocess.return_value.stdout = "=== COMMIT 123 ===\nChanges..."

        result = tool.execute(mock_context)

        assert result.success
        # The formatter is usually a mock in unit tests or acts on the string
        # We just verify the raw output passed through or was processed
        assert "=== COMMIT" in result.output