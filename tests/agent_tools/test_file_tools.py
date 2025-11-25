import pytest
import os
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from src.agent_tools.tools.file_tools import (
    ReadFileTool,
    WriteFileTool,
    ListFilesTool,
    ListDirectoryTool
)
from src.agent_tools.tools.base import ToolContext


# --- Fixtures ---

@pytest.fixture
def mock_context(tmp_path):
    """
    Creates a context backed by a real temporary directory.
    """
    context = MagicMock(spec=ToolContext)
    context.project_root = tmp_path

    # Default: assume all paths provided in tests are safe unless specified otherwise
    context.is_safe_path = Mock(return_value=True)

    # Mock Memory and Config
    context.remember_file_read = Mock()
    context.dry_run = False

    context.config = Mock()
    context.config.max_file_read_size = 1000
    context.config.max_file_listing = 10
    context.config.max_directory_tree_lines = 50
    context.config.skip_directories = ['.git', '__pycache__']
    context.config.allowed_hidden_files = ['.gitignore']

    return context


# --- ReadFileTool Tests ---

class TestReadFileTool:
    def test_read_existing_file(self, mock_context):
        """Should read content and return success."""
        tool = ReadFileTool()
        file_path = mock_context.project_root / "test.txt"
        file_path.write_text("Hello World", encoding="utf-8")

        result = tool.execute(mock_context, path="test.txt")

        assert result.success
        assert result.output == "Hello World"
        assert result.metadata["lines"] == 1
        # Verify memory storage
        mock_context.remember_file_read.assert_called_once()

    def test_read_nonexistent_file(self, mock_context):
        """Should fail gracefully if file doesn't exist."""
        tool = ReadFileTool()
        result = tool.execute(mock_context, path="ghost.txt")

        assert not result.success
        assert "does not exist" in result.error

    def test_prevent_unsafe_path_read(self, mock_context):
        """Should prevent reading outside project root."""
        tool = ReadFileTool()
        mock_context.is_safe_path.return_value = False

        result = tool.execute(mock_context, path="../secret.txt")

        assert not result.success
        assert "outside project directory" in result.error

    def test_truncate_large_file(self, mock_context):
        """Should truncate content exceeding max_file_read_size."""
        tool = ReadFileTool()
        # limit is 1000 in fixture
        large_content = "A" * 1500
        (mock_context.project_root / "large.txt").write_text(large_content)

        result = tool.execute(mock_context, path="large.txt")

        assert result.success
        assert len(result.output) < 1500
        assert "... [truncated]" in result.output


# --- WriteFileTool Tests ---

class TestWriteFileTool:
    def test_basic_write(self, mock_context):
        """Should write content and create parents if needed."""
        tool = WriteFileTool()
        path = "subdir/result.txt"
        content = "Success"

        result = tool.execute(mock_context, path=path, content=content)

        assert result.success
        assert (mock_context.project_root / "subdir" / "result.txt").read_text() == "Success"
        assert "verified" in result.metadata

    def test_dry_run_does_not_write(self, mock_context):
        """Should not touch filesystem in dry_run mode."""
        tool = WriteFileTool()
        mock_context.dry_run = True
        path = "dry.txt"

        result = tool.execute(mock_context, path=path, content="stuff")

        assert result.success
        assert "[DRY RUN]" in result.output
        assert not (mock_context.project_root / path).exists()

    def test_block_empty_content(self, mock_context):
        """Should reject empty strings to prevent accidental wiping."""
        tool = WriteFileTool()
        result = tool.execute(mock_context, path="empty.txt", content="")

        assert not result.success
        assert "empty content" in result.error

    @pytest.mark.parametrize("abs_path", [
        "/etc/passwd",  # Unix absolute
        "C:\\Windows\\System32",  # Windows absolute
        "D:/Users/Data",  # Windows mixed
        "\\\\Server\\Share"  # UNC
    ])
    def test_security_reject_absolute_paths(self, mock_context, abs_path):
        """Should reject absolute paths regardless of current OS."""
        tool = WriteFileTool()
        result = tool.execute(mock_context, path=abs_path, content="hack")

        assert not result.success
        assert "Absolute path" in result.error

    def test_validate_short_code_content(self, mock_context):
        """Should warn if writing tiny content to code files."""
        tool = WriteFileTool()
        # Writing just "pass" to a python file is suspicious
        result = tool.execute(mock_context, path="script.py", content="pass")

        assert not result.success
        assert "Content too short" in result.error

    def test_validate_requirements_txt(self, mock_context):
        """Should prevent adding stdlib modules to requirements.txt."""
        tool = WriteFileTool()
        bad_reqs = "requests==2.0.0\nos\njson>=1.0"

        result = tool.execute(mock_context, path="requirements.txt", content=bad_reqs)

        assert not result.success
        assert "standard library modules" in result.error
        assert "os" in result.error
        assert "json" in result.error

    def test_write_verification_failure(self, mock_context):
        """Should detect if written content does not match input."""
        tool = WriteFileTool()
        test_file = mock_context.project_root / "test.txt"

        # Track call count to return different values on subsequent reads
        read_count = [0]
        original_read_text = Path.read_text

        def mock_read_text(self, *args, **kwargs):
            read_count[0] += 1
            # First read (if file exists check) - file doesn't exist yet so won't be called
            # After write, return corrupted data to trigger verification failure
            if self == test_file:
                return "Corrupted Data"
            return original_read_text(self, *args, **kwargs)

        # Patch only the read_text for verification, let write_text work normally
        with patch.object(Path, 'read_text', mock_read_text):
            result = tool.execute(mock_context, path="test.txt", content="Expected Data that is long enough")

        assert not result.success
        assert "verification failed" in result.error


# --- ListFilesTool Tests ---

class TestListFilesTool:
    def test_list_files_basic(self, mock_context):
        """Should list files in directory."""
        tool = ListFilesTool()
        (mock_context.project_root / "a.txt").touch()
        (mock_context.project_root / "b.py").touch()

        result = tool.execute(mock_context, directory=".")

        assert result.success
        assert "a.txt" in result.output
        assert "b.py" in result.output

    def test_list_files_pattern(self, mock_context):
        """Should filter by glob pattern."""
        tool = ListFilesTool()
        (mock_context.project_root / "src").mkdir()
        (mock_context.project_root / "src/main.py").touch()
        (mock_context.project_root / "src/readme.md").touch()

        result = tool.execute(mock_context, directory="src", pattern="*.py")

        assert result.success
        assert "main.py" in result.output
        assert "readme.md" not in result.output

    def test_list_files_truncation(self, mock_context):
        """Should truncate if too many files found."""
        tool = ListFilesTool()
        # limit is 10 in fixture
        for i in range(15):
            (mock_context.project_root / f"file_{i}.txt").touch()

        result = tool.execute(mock_context)

        assert result.success
        assert "truncated" in result.output
        assert result.metadata["truncated"] is True


# --- ListDirectoryTool Tests ---

class TestListDirectoryTool:
    def test_generate_tree_structure(self, mock_context):
        """Should generate a visual tree of the directory."""
        tool = ListDirectoryTool()

        # Setup: root -> src -> main.py
        src = mock_context.project_root / "src"
        src.mkdir()
        (src / "main.py").write_text("print('hi')")
        (mock_context.project_root / "README.md").touch()

        result = tool.execute(mock_context)

        assert result.success
        # Check for tree connectors
        assert "|-- src/" in result.output
        assert "`-- README.md" in result.output
        # Check if file size is roughly present
        assert "(11B)" in result.output or "(11.0B)" in result.output

    def test_respect_depth_limit(self, mock_context):
        """Should stop traversing at specified depth."""
        tool = ListDirectoryTool()

        # root/level1/level2/level3
        d = mock_context.project_root / "level1" / "level2" / "level3"
        d.mkdir(parents=True)

        # Implementation: depth=1 means traverse up to current_depth=1
        # - depth 0: shows level1/, recurses (0 < 1 is true)
        # - depth 1: shows level2/, does NOT recurse (1 < 1 is false)
        # So level3/ should not appear because we don't enter level2/
        result = tool.execute(mock_context, depth=1)

        assert "level1/" in result.output
        assert "level2/" in result.output  # Shown at depth 1
        assert "level3/" not in result.output  # Not shown - recursion stopped

    def test_skip_ignored_directories(self, mock_context):
        """Should not list contents of ignored directories like .git."""
        tool = ListDirectoryTool()

        git_dir = mock_context.project_root / ".git"
        git_dir.mkdir()
        (git_dir / "config").touch()

        result = tool.execute(mock_context)

        assert ".git" not in result.output

    def test_output_interface_styling(self, mock_context):
        """Should verify that output interface methods are called if provided."""
        mock_ui = Mock()
        mock_ui.style.side_effect = lambda x, **kwargs: f"[{x}]"

        tool = ListDirectoryTool(output_interface=mock_ui)
        (mock_context.project_root / "test.py").touch()

        result = tool.execute(mock_context)

        assert result.success
        # Verify style was called for the directory and the file
        assert mock_ui.style.call_count >= 2