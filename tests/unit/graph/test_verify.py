"""
Unit tests for the Verify node.

Tests verification step including:
- Python file filtering
- File path sanitization (security)
- Ruff execution
- Mypy execution
- Error handling
- State updates
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

from scrappy.graph.nodes.verify import (
    filter_python_files,
    run_mypy,
    run_ruff,
    sanitize_file_paths,
    verify_node,
)
from scrappy.graph.state import AgentState, Message


# =============================================================================
# Test Helpers
# =============================================================================


def create_test_state(
    input_text: str = "Test task",
    working_dir: str = "/tmp/test",
    messages: Optional[list[Message]] = None,
    files_changed: Optional[list[str]] = None,
    files_verified: bool = False,
    error_count: int = 0,
    last_error: Optional[str] = None,
) -> AgentState:
    """Create a test AgentState."""
    return AgentState(
        input=input_text,
        original_task=input_text,
        working_dir=working_dir,
        messages=messages or [],
        files_changed=files_changed or [],
        files_verified=files_verified,
        error_count=error_count,
        last_error=last_error,
    )


# =============================================================================
# Filter Python Files Tests
# =============================================================================


class TestFilterPythonFiles:
    """Tests for Python file filtering."""

    def test_filters_python_files(self) -> None:
        """Should keep only .py files."""
        files = ["/src/main.py", "/src/data.json", "/src/util.py", "/readme.md"]
        result = filter_python_files(files)
        assert result == ["/src/main.py", "/src/util.py"]

    def test_empty_list_returns_empty(self) -> None:
        """Empty list should return empty."""
        assert filter_python_files([]) == []

    def test_no_python_files(self) -> None:
        """List with no Python files should return empty."""
        files = ["/data.json", "/config.yaml", "/readme.md"]
        result = filter_python_files(files)
        assert result == []

    def test_all_python_files(self) -> None:
        """List with all Python files should return all."""
        files = ["/a.py", "/b.py", "/c.py"]
        result = filter_python_files(files)
        assert result == files


# =============================================================================
# Sanitize File Paths Tests (Security)
# =============================================================================


class TestSanitizeFilePaths:
    """Tests for file path sanitization (security)."""

    def test_valid_relative_paths(self) -> None:
        """Relative paths within working_dir should be accepted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("# test")

            valid, skipped = sanitize_file_paths(["test.py"], tmpdir)

            assert len(valid) == 1
            assert len(skipped) == 0
            # Use resolve() to handle Windows 8.3 short names vs long names
            assert Path(valid[0]).resolve() == test_file.resolve()

    def test_nonexistent_files_skipped(self) -> None:
        """Non-existent files should be skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            valid, skipped = sanitize_file_paths(["missing.py"], tmpdir)

            assert len(valid) == 0
            assert len(skipped) == 1
            assert "missing.py" in skipped

    def test_path_traversal_blocked(self) -> None:
        """Path traversal attempts should be blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file outside the working dir
            parent_dir = Path(tmpdir).parent
            outside_file = parent_dir / "outside.py"
            if not outside_file.exists():
                outside_file.write_text("# outside")

            try:
                valid, skipped = sanitize_file_paths(
                    ["../outside.py"],
                    tmpdir,
                )

                assert len(valid) == 0
                assert len(skipped) == 1
            finally:
                if outside_file.exists():
                    outside_file.unlink()

    def test_absolute_paths_outside_working_dir_blocked(self) -> None:
        """Absolute paths outside working_dir should be blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            valid, skipped = sanitize_file_paths(
                ["/etc/passwd"],
                tmpdir,
            )

            assert len(valid) == 0
            assert len(skipped) == 1

    def test_returns_absolute_paths(self) -> None:
        """Valid files should be returned as absolute paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "script.py"
            test_file.write_text("# test")

            valid, skipped = sanitize_file_paths(["script.py"], tmpdir)

            assert len(valid) == 1
            assert Path(valid[0]).is_absolute()

    def test_mixed_valid_and_invalid(self) -> None:
        """Should handle mix of valid and invalid paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create one valid file
            valid_file = Path(tmpdir) / "valid.py"
            valid_file.write_text("# valid")

            valid, skipped = sanitize_file_paths(
                ["valid.py", "missing.py", "../outside.py"],
                tmpdir,
            )

            assert len(valid) == 1
            assert len(skipped) == 2

    def test_empty_list_returns_empty(self) -> None:
        """Empty file list should return empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            valid, skipped = sanitize_file_paths([], tmpdir)

            assert valid == []
            assert skipped == []

    def test_invalid_working_dir(self) -> None:
        """Invalid working_dir should skip all files."""
        valid, skipped = sanitize_file_paths(
            ["test.py"],
            "/nonexistent/path/that/does/not/exist",
        )

        # Files are skipped when working_dir is invalid
        assert len(valid) == 0
        assert len(skipped) == 1


# =============================================================================
# Run Ruff Tests
# =============================================================================


class TestRunRuff:
    """Tests for ruff execution."""

    @patch("scrappy.graph.nodes.verify._revalidate_paths", side_effect=lambda f, w: f)
    @patch("scrappy.graph.nodes.verify.subprocess.run")
    def test_ruff_success(self, mock_run: MagicMock, mock_revalidate: MagicMock):
        """Successful ruff check should return (True, output)."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="All checks passed!\n",
            stderr="",
        )

        success, output = run_ruff(["/test.py"], "/tmp")

        assert success is True
        assert "All checks passed" in output
        mock_run.assert_called_once()

    @patch("scrappy.graph.nodes.verify._revalidate_paths", side_effect=lambda f, w: f)
    @patch("scrappy.graph.nodes.verify.subprocess.run")
    def test_ruff_failure(self, mock_run: MagicMock, mock_revalidate: MagicMock):
        """Failed ruff check should return (False, output)."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="test.py:10:1: E501 line too long\n",
        )

        success, output = run_ruff(["/test.py"], "/tmp")

        assert success is False
        assert "E501" in output

    @patch("scrappy.graph.nodes.verify._revalidate_paths", side_effect=lambda f, w: f)
    @patch("scrappy.graph.nodes.verify.subprocess.run")
    def test_ruff_not_installed(self, mock_run: MagicMock, mock_revalidate: MagicMock):
        """Missing ruff should return (True, '') - graceful skip."""
        mock_run.side_effect = FileNotFoundError()

        success, output = run_ruff(["/test.py"], "/tmp")

        assert success is True
        assert output == ""

    @patch("scrappy.graph.nodes.verify._revalidate_paths", side_effect=lambda f, w: f)
    @patch("scrappy.graph.nodes.verify.subprocess.run")
    def test_ruff_timeout(self, mock_run: MagicMock, mock_revalidate: MagicMock):
        """Timeout should return (False, error message)."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ruff", timeout=60)

        success, output = run_ruff(["/test.py"], "/tmp")

        assert success is False
        assert "timed out" in output


# =============================================================================
# Run Mypy Tests
# =============================================================================


class TestRunMypy:
    """Tests for mypy execution."""

    @patch("scrappy.graph.nodes.verify._revalidate_paths", side_effect=lambda f, w: f)
    @patch("scrappy.graph.nodes.verify.subprocess.run")
    def test_mypy_success(self, mock_run: MagicMock, mock_revalidate: MagicMock):
        """Successful mypy check should return (True, output)."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Success: no issues found\n",
            stderr="",
        )

        success, output = run_mypy(["/test.py"], "/tmp")

        assert success is True
        assert "Success" in output

    @patch("scrappy.graph.nodes.verify._revalidate_paths", side_effect=lambda f, w: f)
    @patch("scrappy.graph.nodes.verify.subprocess.run")
    def test_mypy_failure(self, mock_run: MagicMock, mock_revalidate: MagicMock):
        """Failed mypy check should return (False, output)."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="test.py:5: error: Incompatible types\n",
            stderr="",
        )

        success, output = run_mypy(["/test.py"], "/tmp")

        assert success is False
        assert "error" in output

    @patch("scrappy.graph.nodes.verify._revalidate_paths", side_effect=lambda f, w: f)
    @patch("scrappy.graph.nodes.verify.subprocess.run")
    def test_mypy_not_installed(self, mock_run: MagicMock, mock_revalidate: MagicMock):
        """Missing mypy should return (True, '') - graceful skip."""
        mock_run.side_effect = FileNotFoundError()

        success, output = run_mypy(["/test.py"], "/tmp")

        assert success is True
        assert output == ""

    @patch("scrappy.graph.nodes.verify._revalidate_paths", side_effect=lambda f, w: f)
    @patch("scrappy.graph.nodes.verify.subprocess.run")
    def test_mypy_timeout(self, mock_run: MagicMock, mock_revalidate: MagicMock):
        """Timeout should return (False, error message)."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="mypy", timeout=120)

        success, output = run_mypy(["/test.py"], "/tmp")

        assert success is False
        assert "timed out" in output


# =============================================================================
# Verify Node Tests
# =============================================================================


class TestVerifyNode:
    """Tests for the main verify_node function."""

    def test_skip_if_no_files_changed(self):
        """Should skip verification if no files changed."""
        state = create_test_state(files_changed=[], files_verified=False)

        result = verify_node(state)

        assert result.files_verified is False  # Unchanged
        assert result.error_count == 0

    def test_skip_if_already_verified(self):
        """Should skip verification if already verified."""
        state = create_test_state(
            files_changed=["/test.py"],
            files_verified=True,
        )

        result = verify_node(state)

        assert result.files_verified is True
        assert result.error_count == 0

    def test_skip_non_python_files(self):
        """Should mark verified if no Python files in changed."""
        state = create_test_state(
            files_changed=["/data.json", "/readme.md"],
            files_verified=False,
        )

        result = verify_node(state)

        assert result.files_verified is True

    @patch("scrappy.graph.nodes.verify.sanitize_file_paths")
    @patch("scrappy.graph.nodes.verify.run_mypy")
    @patch("scrappy.graph.nodes.verify.run_ruff")
    def test_success_sets_verified(
        self,
        mock_ruff: MagicMock,
        mock_mypy: MagicMock,
        mock_sanitize: MagicMock,
    ) -> None:
        """Successful verification should set files_verified = True."""
        mock_sanitize.return_value = (["/src/main.py"], [])
        mock_ruff.return_value = (True, "")
        mock_mypy.return_value = (True, "")

        state = create_test_state(
            files_changed=["/src/main.py"],
            files_verified=False,
        )

        result = verify_node(state)

        assert result.files_verified is True
        assert result.error_count == 0
        assert result.last_error is None

    @patch("scrappy.graph.nodes.verify.sanitize_file_paths")
    @patch("scrappy.graph.nodes.verify.run_mypy")
    @patch("scrappy.graph.nodes.verify.run_ruff")
    def test_ruff_failure_updates_error(
        self,
        mock_ruff: MagicMock,
        mock_mypy: MagicMock,
        mock_sanitize: MagicMock,
    ) -> None:
        """Ruff failure should increment error_count and set last_error."""
        mock_sanitize.return_value = (["/src/main.py"], [])
        mock_ruff.return_value = (False, "E501 line too long")
        mock_mypy.return_value = (True, "")

        state = create_test_state(
            files_changed=["/src/main.py"],
            files_verified=False,
            error_count=0,
        )

        result = verify_node(state)

        assert result.files_verified is False
        assert result.error_count == 1
        assert "E501" in (result.last_error or "")

    @patch("scrappy.graph.nodes.verify.sanitize_file_paths")
    @patch("scrappy.graph.nodes.verify.run_mypy")
    @patch("scrappy.graph.nodes.verify.run_ruff")
    def test_mypy_failure_updates_error(
        self,
        mock_ruff: MagicMock,
        mock_mypy: MagicMock,
        mock_sanitize: MagicMock,
    ) -> None:
        """Mypy failure should increment error_count and set last_error."""
        mock_sanitize.return_value = (["/src/main.py"], [])
        mock_ruff.return_value = (True, "")
        mock_mypy.return_value = (False, "Incompatible types")

        state = create_test_state(
            files_changed=["/src/main.py"],
            files_verified=False,
            error_count=0,
        )

        result = verify_node(state)

        assert result.files_verified is False
        assert result.error_count == 1
        assert "Incompatible types" in (result.last_error or "")

    @patch("scrappy.graph.nodes.verify.sanitize_file_paths")
    @patch("scrappy.graph.nodes.verify.run_mypy")
    @patch("scrappy.graph.nodes.verify.run_ruff")
    def test_both_failures_combined(
        self,
        mock_ruff: MagicMock,
        mock_mypy: MagicMock,
        mock_sanitize: MagicMock,
    ) -> None:
        """Both failures should be combined in error message."""
        mock_sanitize.return_value = (["/src/main.py"], [])
        mock_ruff.return_value = (False, "ruff error")
        mock_mypy.return_value = (False, "mypy error")

        state = create_test_state(
            files_changed=["/src/main.py"],
            files_verified=False,
        )

        result = verify_node(state)

        assert result.files_verified is False
        assert result.error_count == 1
        assert "ruff" in (result.last_error or "")
        assert "mypy" in (result.last_error or "")

    @patch("scrappy.graph.nodes.verify.sanitize_file_paths")
    @patch("scrappy.graph.nodes.verify.run_mypy")
    @patch("scrappy.graph.nodes.verify.run_ruff")
    def test_failure_appends_to_messages(
        self,
        mock_ruff: MagicMock,
        mock_mypy: MagicMock,
        mock_sanitize: MagicMock,
    ) -> None:
        """Failure should append error message to messages."""
        mock_sanitize.return_value = (["/src/main.py"], [])
        mock_ruff.return_value = (False, "lint error")
        mock_mypy.return_value = (True, "")

        state = create_test_state(
            files_changed=["/src/main.py"],
            files_verified=False,
            messages=[{"role": "user", "content": "hello"}],
        )

        result = verify_node(state)

        assert len(result.messages) == 2
        assert result.messages[1]["role"] == "system"
        assert "Verification failed" in result.messages[1]["content"]
        assert "lint error" in result.messages[1]["content"]

    @patch("scrappy.graph.nodes.verify.sanitize_file_paths")
    @patch("scrappy.graph.nodes.verify.run_mypy")
    @patch("scrappy.graph.nodes.verify.run_ruff")
    def test_skip_mypy_when_disabled(
        self,
        mock_ruff: MagicMock,
        mock_mypy: MagicMock,
        mock_sanitize: MagicMock,
    ) -> None:
        """Should skip mypy when run_mypy_check=False."""
        mock_sanitize.return_value = (["/src/main.py"], [])
        mock_ruff.return_value = (True, "")
        mock_mypy.return_value = (True, "")

        state = create_test_state(
            files_changed=["/src/main.py"],
            files_verified=False,
        )

        result = verify_node(state, run_mypy_check=False)

        assert result.files_verified is True
        mock_ruff.assert_called_once()
        mock_mypy.assert_not_called()

    @patch("scrappy.graph.nodes.verify.sanitize_file_paths")
    @patch("scrappy.graph.nodes.verify.run_mypy")
    @patch("scrappy.graph.nodes.verify.run_ruff")
    def test_verifies_multiple_python_files(
        self,
        mock_ruff: MagicMock,
        mock_mypy: MagicMock,
        mock_sanitize: MagicMock,
    ) -> None:
        """Should verify all Python files in batch."""
        # Sanitize returns the Python files (json filtered out earlier)
        mock_sanitize.return_value = (["/src/a.py", "/src/b.py"], [])
        mock_ruff.return_value = (True, "")
        mock_mypy.return_value = (True, "")

        state = create_test_state(
            files_changed=["/src/a.py", "/src/b.py", "/data.json"],
            files_verified=False,
        )

        verify_node(state)

        # Check ruff was called with both Python files
        ruff_call_args = mock_ruff.call_args[0]
        assert "/src/a.py" in ruff_call_args[0]
        assert "/src/b.py" in ruff_call_args[0]

    @patch("scrappy.graph.nodes.verify.sanitize_file_paths")
    @patch("scrappy.graph.nodes.verify.run_mypy")
    @patch("scrappy.graph.nodes.verify.run_ruff")
    def test_increments_existing_error_count(
        self,
        mock_ruff: MagicMock,
        mock_mypy: MagicMock,
        mock_sanitize: MagicMock,
    ) -> None:
        """Should increment existing error_count."""
        mock_sanitize.return_value = (["/src/main.py"], [])
        mock_ruff.return_value = (False, "error")
        mock_mypy.return_value = (True, "")

        state = create_test_state(
            files_changed=["/src/main.py"],
            files_verified=False,
            error_count=2,
        )

        result = verify_node(state)

        assert result.error_count == 3

    def test_all_files_skipped_by_sanitization_marks_verified(self) -> None:
        """When all files are skipped by sanitization, should mark verified."""
        state = create_test_state(
            files_changed=["/etc/passwd", "../../../etc/shadow"],
            files_verified=False,
        )

        result = verify_node(state)

        # Files outside working_dir are skipped, verification passes
        assert result.files_verified is True
        assert result.error_count == 0
