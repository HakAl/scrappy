"""
Tests for the undo system.

This module tests the shadow ref-based undo mechanism that safely captures
and restores git state before/after agent operations.

CRITICAL: All git commands are mocked - no real git calls in tests.
"""

import json
import os
import pytest
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

from scrappy.undo import (
    UndoError,
    UndoState,
    check_undo_preconditions,
    create_undo_point,
    get_current_branch,
    get_head_sha,
    get_undo_limit,
    has_untracked,
    is_dirty,
    load_undo_states,
    undo,
    undo_lock,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_git_dir(tmp_path):
    """Create a temporary directory simulating a git repo."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    scrappy_dir = git_dir / "scrappy"
    scrappy_dir.mkdir()
    return tmp_path


@pytest.fixture
def mock_git_run():
    """
    Factory fixture for mocking subprocess.run calls to git.

    Returns a configurable mock that can be set up for different git commands.
    """

    def _create_mock(command_results=None):
        """
        Create a mock that returns specified results for git commands.

        Args:
            command_results: Dict mapping command substring to (returncode, stdout).
                             e.g., {"rev-parse HEAD": (0, "abc123")}
        """
        command_results = command_results or {}

        def side_effect(cmd, **kwargs):
            result = MagicMock()
            cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)

            # Find matching command result
            for pattern, (returncode, stdout) in command_results.items():
                if pattern in cmd_str:
                    result.returncode = returncode
                    result.stdout = stdout
                    result.stderr = ""
                    return result

            # Default: success with empty output
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        return side_effect

    return _create_mock


@pytest.fixture
def sample_undo_state(temp_git_dir):
    """Create a sample UndoState for testing."""
    return UndoState(
        ref="refs/scrappy/undo/20250128-143022-123456",
        branch="main",
        original_head=None,
        is_wip=True,
        worktree_path=str(temp_git_dir),
        created_at=datetime(2025, 1, 28, 14, 30, 22, 123456),
        scrappy_version="0.1.0",
    )


@pytest.fixture
def sample_detached_state(temp_git_dir):
    """Create a sample UndoState for detached HEAD testing."""
    return UndoState(
        ref="refs/scrappy/undo/20250128-150000-000000",
        branch=None,
        original_head="abc123def456",
        is_wip=False,
        worktree_path=str(temp_git_dir),
        created_at=datetime(2025, 1, 28, 15, 0, 0),
        scrappy_version="0.1.0",
    )


# =============================================================================
# Precondition Tests
# =============================================================================


class TestCheckPreconditions:
    """Tests for check_undo_preconditions function."""

    @pytest.mark.unit
    def test_check_preconditions_clean(self, temp_git_dir):
        """
        Precondition check should pass on a clean repo.

        When there is no merge, rebase, or cherry-pick in progress,
        the function should complete without raising an error.
        """
        git_dir = temp_git_dir / ".git"

        # Ensure no problem indicators exist
        assert not (git_dir / "MERGE_HEAD").exists()
        assert not (git_dir / "REBASE_HEAD").exists()
        assert not (git_dir / "CHERRY_PICK_HEAD").exists()
        assert not (git_dir / "rebase-merge").exists()
        assert not (git_dir / "rebase-apply").exists()

        # Should not raise
        with patch("scrappy.undo.Path") as mock_path:
            mock_path.return_value.exists.return_value = False
            check_undo_preconditions()

    @pytest.mark.unit
    def test_check_preconditions_merge(self, temp_git_dir):
        """
        Precondition check should raise during active merge.

        When MERGE_HEAD exists, creating an undo point is unsafe.
        """
        git_dir = temp_git_dir / ".git"
        merge_head = git_dir / "MERGE_HEAD"
        merge_head.write_text("abc123\n")

        with patch("scrappy.undo.Path") as mock_path:

            def path_exists(p):
                return ".git/MERGE_HEAD" in str(p)

            mock_path.return_value.exists.side_effect = lambda: path_exists(
                mock_path.call_args[0][0] if mock_path.call_args else ""
            )

            # Direct test - create actual file structure
            with patch.object(Path, "exists", return_value=True):
                with pytest.raises(UndoError) as exc_info:
                    # Create a path object that will return True for exists()
                    with patch("scrappy.undo.Path") as mock_p:
                        mock_instance = MagicMock()
                        mock_instance.exists.return_value = True
                        mock_p.return_value = mock_instance
                        check_undo_preconditions()

                assert "merge" in str(exc_info.value).lower()

    @pytest.mark.unit
    def test_check_preconditions_rebase(self, temp_git_dir):
        """
        Precondition check should raise during active rebase.
        """
        with patch("scrappy.undo.Path") as mock_path:
            # First call returns False (MERGE_HEAD), second returns True (REBASE_HEAD)
            mock_instance = MagicMock()
            exists_returns = [False, True]  # Skip MERGE_HEAD, catch REBASE_HEAD
            mock_instance.exists.side_effect = lambda: exists_returns.pop(
                0
            ) if exists_returns else False
            mock_path.return_value = mock_instance

            with pytest.raises(UndoError) as exc_info:
                check_undo_preconditions()

            assert "rebase" in str(exc_info.value).lower()


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for git helper functions."""

    @pytest.mark.unit
    def test_get_current_branch_on_branch(self, mock_git_run):
        """get_current_branch returns branch name when on a branch."""
        command_results = {
            "symbolic-ref --short HEAD": (0, "main\n"),
        }

        with patch("scrappy.undo.subprocess.run", side_effect=mock_git_run(command_results)):
            result = get_current_branch()
            assert result == "main"

    @pytest.mark.unit
    def test_get_current_branch_detached(self, mock_git_run):
        """get_current_branch returns None when detached."""
        command_results = {
            "symbolic-ref --short HEAD": (128, ""),
        }

        with patch("scrappy.undo.subprocess.run", side_effect=mock_git_run(command_results)):
            result = get_current_branch()
            assert result is None

    @pytest.mark.unit
    def test_get_head_sha(self, mock_git_run):
        """get_head_sha returns current HEAD commit."""
        command_results = {
            "rev-parse HEAD": (0, "abc123def456\n"),
        }

        with patch("scrappy.undo.subprocess.run", side_effect=mock_git_run(command_results)):
            result = get_head_sha()
            assert result == "abc123def456"

    @pytest.mark.unit
    def test_is_dirty_clean(self, mock_git_run):
        """is_dirty returns False when working directory is clean."""
        command_results = {
            "diff --quiet": (0, ""),
            "diff --cached --quiet": (0, ""),
        }

        with patch("scrappy.undo.subprocess.run", side_effect=mock_git_run(command_results)):
            assert not is_dirty()

    @pytest.mark.unit
    def test_is_dirty_unstaged(self, mock_git_run):
        """is_dirty returns True when there are unstaged changes."""
        command_results = {
            "diff --quiet": (1, ""),  # Has unstaged
            "diff --cached --quiet": (0, ""),
        }

        with patch("scrappy.undo.subprocess.run", side_effect=mock_git_run(command_results)):
            assert is_dirty()

    @pytest.mark.unit
    def test_is_dirty_staged(self, mock_git_run):
        """is_dirty returns True when there are staged changes."""

        def smart_side_effect(cmd, **kwargs):
            result = MagicMock()
            cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
            result.stderr = ""

            if "diff --quiet" in cmd_str and "--cached" not in cmd_str:
                result.returncode = 0  # No unstaged
                result.stdout = ""
            elif "diff --cached --quiet" in cmd_str:
                result.returncode = 1  # Has staged
                result.stdout = ""
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        with patch("scrappy.undo.subprocess.run", side_effect=smart_side_effect):
            assert is_dirty()

    @pytest.mark.unit
    def test_has_untracked_none(self, mock_git_run):
        """has_untracked returns False when no untracked files."""
        command_results = {
            "ls-files --others": (0, ""),
        }

        with patch("scrappy.undo.subprocess.run", side_effect=mock_git_run(command_results)):
            assert not has_untracked()

    @pytest.mark.unit
    def test_has_untracked_some(self, mock_git_run):
        """has_untracked returns True when untracked files exist."""
        command_results = {
            "ls-files --others": (0, "new_file.txt\n"),
        }

        with patch("scrappy.undo.subprocess.run", side_effect=mock_git_run(command_results)):
            assert has_untracked()

    @pytest.mark.unit
    def test_is_shallow_clone_false(self, temp_git_dir):
        """is_shallow_clone returns False for normal clones."""
        with patch("scrappy.undo.Path") as mock_path:
            mock_path.return_value.exists.return_value = False
            # Actually test against temp dir
            assert not (temp_git_dir / ".git" / "shallow").exists()

    @pytest.mark.unit
    def test_is_shallow_clone_true(self, temp_git_dir):
        """is_shallow_clone returns True for shallow clones."""
        shallow_file = temp_git_dir / ".git" / "shallow"
        shallow_file.write_text("abc123\n")

        with patch("scrappy.undo.Path") as mock_path:
            mock_path.return_value.exists.return_value = True
            # Actually test against temp dir
            assert shallow_file.exists()


# =============================================================================
# Persistence Tests
# =============================================================================


class TestUndoStatePersistence:
    """Tests for undo state persistence."""

    @pytest.mark.unit
    def test_undo_state_persistence_roundtrip(self, temp_git_dir, sample_undo_state):
        """
        Save and load should preserve all fields including datetime.

        The state should be identical after serialization/deserialization.
        """
        state_file = temp_git_dir / ".git" / "scrappy" / "undo-states.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        # Serialize state
        state_dict = asdict(sample_undo_state)
        state_dict["created_at"] = sample_undo_state.created_at.isoformat()

        data = {"states": [state_dict]}
        state_file.write_text(json.dumps(data, indent=2))

        # Deserialize and verify
        loaded_data = json.loads(state_file.read_text())
        loaded_dict = loaded_data["states"][0]
        loaded_dict["created_at"] = datetime.fromisoformat(loaded_dict["created_at"])
        loaded_state = UndoState(**loaded_dict)

        assert loaded_state.ref == sample_undo_state.ref
        assert loaded_state.branch == sample_undo_state.branch
        assert loaded_state.original_head == sample_undo_state.original_head
        assert loaded_state.is_wip == sample_undo_state.is_wip
        assert loaded_state.worktree_path == sample_undo_state.worktree_path
        assert loaded_state.created_at == sample_undo_state.created_at
        assert loaded_state.scrappy_version == sample_undo_state.scrappy_version

    @pytest.mark.unit
    def test_load_undo_states_empty(self, temp_git_dir):
        """load_undo_states returns empty list when file doesn't exist."""
        with patch("scrappy.undo.UNDO_STATE_PATH", temp_git_dir / ".git" / "scrappy" / "undo-states.json"):
            result = load_undo_states()
            assert result == []

    @pytest.mark.unit
    def test_get_undo_limit_default(self):
        """get_undo_limit returns 10 by default."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove SCRAPPY_UNDO_LIMIT if set
            os.environ.pop("SCRAPPY_UNDO_LIMIT", None)
            assert get_undo_limit() == 10

    @pytest.mark.unit
    def test_get_undo_limit_custom(self):
        """get_undo_limit respects SCRAPPY_UNDO_LIMIT env var."""
        with patch.dict(os.environ, {"SCRAPPY_UNDO_LIMIT": "5"}):
            assert get_undo_limit() == 5


# =============================================================================
# Lock Tests
# =============================================================================


class TestUndoLock:
    """Tests for concurrent operation locking."""

    @pytest.mark.unit
    def test_lock_creates_file(self, temp_git_dir):
        """Lock should create lock file during context."""
        lock_path = temp_git_dir / ".git" / "scrappy.lock"

        with patch("scrappy.undo.LOCK_PATH", lock_path):
            with patch("scrappy.undo.LOCK_TIMEOUT", 1):
                with undo_lock():
                    assert lock_path.exists()

        # Lock should be released after context
        assert not lock_path.exists()

    @pytest.mark.unit
    def test_lock_cleanup_on_exception(self, temp_git_dir):
        """Lock file should be removed even on exception."""
        lock_path = temp_git_dir / ".git" / "scrappy.lock"

        with patch("scrappy.undo.LOCK_PATH", lock_path):
            try:
                with undo_lock():
                    assert lock_path.exists()
                    raise ValueError("test error")
            except ValueError:
                pass

        assert not lock_path.exists()


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestUndoEdgeCases:
    """Additional edge case tests."""

    @pytest.mark.unit
    def test_no_undo_points_available(self, temp_git_dir):
        """Undo should raise helpful error when no points exist."""
        state_file = temp_git_dir / ".git" / "scrappy" / "undo-states.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text('{"states": []}')

        with patch("scrappy.undo.UNDO_STATE_PATH", state_file):
            with pytest.raises(UndoError) as exc_info:
                undo()
            assert "No undo points" in str(exc_info.value)

    @pytest.mark.unit
    def test_undo_n_greater_than_available(self, temp_git_dir, sample_undo_state):
        """Undo(n) should fail if n > available points."""
        state_file = temp_git_dir / ".git" / "scrappy" / "undo-states.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        state_dict = asdict(sample_undo_state)
        state_dict["created_at"] = sample_undo_state.created_at.isoformat()
        data = {"states": [state_dict]}  # Only 1 state
        state_file.write_text(json.dumps(data))

        with patch("scrappy.undo.UNDO_STATE_PATH", state_file):
            with pytest.raises(UndoError) as exc_info:
                undo(n=5)  # Request 5th point but only 1 exists
            assert "Only 1 undo points available" in str(exc_info.value)

    @pytest.mark.unit
    def test_undo_wrong_worktree(self, temp_git_dir, sample_undo_state):
        """Undo should fail when run from wrong worktree."""
        state_file = temp_git_dir / ".git" / "scrappy" / "undo-states.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        state_dict = asdict(sample_undo_state)
        state_dict["created_at"] = sample_undo_state.created_at.isoformat()
        data = {"states": [state_dict]}
        state_file.write_text(json.dumps(data))

        wrong_path = "/some/other/path"

        with patch("scrappy.undo.UNDO_STATE_PATH", state_file):
            with patch("os.getcwd", return_value=wrong_path):
                with pytest.raises(UndoError) as exc_info:
                    undo()
                assert "worktree" in str(exc_info.value).lower()
                assert "--force" in str(exc_info.value)


# =============================================================================
# Create Undo Point Tests (Behavior)
# =============================================================================


class TestCreateUndoPointBehavior:
    """Tests for create_undo_point behavior."""

    @pytest.mark.unit
    def test_create_undo_point_captures_branch(self, mock_git_run, temp_git_dir):
        """create_undo_point should capture current branch name."""
        lock_path = temp_git_dir / ".git" / "scrappy.lock"
        state_path = temp_git_dir / ".git" / "scrappy" / "undo-states.json"

        command_results = {
            "symbolic-ref --short HEAD": (0, "feature-branch\n"),
            "rev-parse HEAD": (0, "abc123\n"),
            "diff --quiet": (0, ""),
            "diff --cached --quiet": (0, ""),
            "ls-files --others": (0, ""),
            "update-ref": (0, ""),
        }

        with patch("scrappy.undo.LOCK_PATH", lock_path):
            with patch("scrappy.undo.UNDO_STATE_PATH", state_path):
                with patch("scrappy.undo.check_undo_preconditions"):
                    with patch("scrappy.undo.is_shallow_clone", return_value=False):
                        with patch("scrappy.undo.subprocess.run", side_effect=mock_git_run(command_results)):
                            with patch("os.getcwd", return_value=str(temp_git_dir)):
                                state = create_undo_point()

                                assert state.branch == "feature-branch"
                                assert state.original_head is None
                                assert not state.is_wip

    @pytest.mark.unit
    def test_create_undo_point_captures_detached_head(self, mock_git_run, temp_git_dir):
        """create_undo_point should capture SHA when in detached HEAD."""
        lock_path = temp_git_dir / ".git" / "scrappy.lock"
        state_path = temp_git_dir / ".git" / "scrappy" / "undo-states.json"

        command_results = {
            "symbolic-ref --short HEAD": (128, ""),  # Detached HEAD
            "rev-parse HEAD": (0, "abc123def456\n"),
            "diff --quiet": (0, ""),
            "diff --cached --quiet": (0, ""),
            "ls-files --others": (0, ""),
            "update-ref": (0, ""),
        }

        with patch("scrappy.undo.LOCK_PATH", lock_path):
            with patch("scrappy.undo.UNDO_STATE_PATH", state_path):
                with patch("scrappy.undo.check_undo_preconditions"):
                    with patch("scrappy.undo.is_shallow_clone", return_value=False):
                        with patch("scrappy.undo.subprocess.run", side_effect=mock_git_run(command_results)):
                            with patch("os.getcwd", return_value=str(temp_git_dir)):
                                state = create_undo_point()

                                assert state.branch is None
                                assert state.original_head == "abc123def456"

    @pytest.mark.unit
    def test_create_undo_point_dirty_creates_wip(self, mock_git_run, temp_git_dir):
        """create_undo_point should create WIP commit when dirty."""
        lock_path = temp_git_dir / ".git" / "scrappy.lock"
        state_path = temp_git_dir / ".git" / "scrappy" / "undo-states.json"

        # Track which commands were called
        commands_called = []

        def tracking_side_effect(cmd, **kwargs):
            commands_called.append(cmd)
            result = MagicMock()
            cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
            result.stderr = ""

            if "symbolic-ref --short HEAD" in cmd_str:
                result.returncode = 0
                result.stdout = "main\n"
            elif "diff --quiet" in cmd_str and "--cached" not in cmd_str:
                result.returncode = 1  # Has unstaged changes
                result.stdout = ""
            elif "diff --cached --quiet" in cmd_str:
                # After git add -A, has staged changes
                result.returncode = 1
                result.stdout = ""
            elif "ls-files --others" in cmd_str:
                result.returncode = 0
                result.stdout = ""
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        with patch("scrappy.undo.LOCK_PATH", lock_path):
            with patch("scrappy.undo.UNDO_STATE_PATH", state_path):
                with patch("scrappy.undo.check_undo_preconditions"):
                    with patch("scrappy.undo.is_shallow_clone", return_value=False):
                        with patch("scrappy.undo.subprocess.run", side_effect=tracking_side_effect):
                            with patch("os.getcwd", return_value=str(temp_git_dir)):
                                state = create_undo_point()

                                assert state.is_wip is True
                                # Verify git add -A and git commit were called
                                cmd_str = " ".join(commands_called)
                                assert "git add -A" in cmd_str
                                assert "git commit --no-verify" in cmd_str

    @pytest.mark.unit
    def test_create_undo_point_untracked_creates_wip(self, mock_git_run, temp_git_dir):
        """create_undo_point should include untracked files in WIP."""
        lock_path = temp_git_dir / ".git" / "scrappy.lock"
        state_path = temp_git_dir / ".git" / "scrappy" / "undo-states.json"

        commands_called = []

        def tracking_side_effect(cmd, **kwargs):
            commands_called.append(cmd)
            result = MagicMock()
            cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
            result.stderr = ""

            if "symbolic-ref --short HEAD" in cmd_str:
                result.returncode = 0
                result.stdout = "main\n"
            elif "diff --quiet" in cmd_str and "--cached" not in cmd_str:
                result.returncode = 0  # No unstaged changes
                result.stdout = ""
            elif "diff --cached --quiet" in cmd_str:
                # After git add -A, has staged changes (from untracked)
                result.returncode = 1
                result.stdout = ""
            elif "ls-files --others" in cmd_str:
                result.returncode = 0
                result.stdout = "new_file.txt\n"  # Has untracked
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        with patch("scrappy.undo.LOCK_PATH", lock_path):
            with patch("scrappy.undo.UNDO_STATE_PATH", state_path):
                with patch("scrappy.undo.check_undo_preconditions"):
                    with patch("scrappy.undo.is_shallow_clone", return_value=False):
                        with patch("scrappy.undo.subprocess.run", side_effect=tracking_side_effect):
                            with patch("os.getcwd", return_value=str(temp_git_dir)):
                                state = create_undo_point()

                                assert state.is_wip is True


# =============================================================================
# Undo n Validation Tests
# =============================================================================


class TestUndoNValidation:
    """Tests for n parameter validation."""

    @pytest.mark.unit
    def test_undo_n_equals_zero(self, temp_git_dir, sample_undo_state):
        """undo(n=0) should raise helpful error."""
        state_file = temp_git_dir / ".git" / "scrappy" / "undo-states.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        state_dict = asdict(sample_undo_state)
        state_dict["created_at"] = sample_undo_state.created_at.isoformat()
        data = {"states": [state_dict]}
        state_file.write_text(json.dumps(data))

        with patch("scrappy.undo.UNDO_STATE_PATH", state_file):
            with pytest.raises(UndoError) as exc_info:
                undo(n=0)
            assert "n must be >= 1" in str(exc_info.value)

    @pytest.mark.unit
    def test_undo_n_negative(self, temp_git_dir, sample_undo_state):
        """undo(n=-1) should raise helpful error."""
        state_file = temp_git_dir / ".git" / "scrappy" / "undo-states.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        state_dict = asdict(sample_undo_state)
        state_dict["created_at"] = sample_undo_state.created_at.isoformat()
        data = {"states": [state_dict]}
        state_file.write_text(json.dumps(data))

        with patch("scrappy.undo.UNDO_STATE_PATH", state_file):
            with pytest.raises(UndoError) as exc_info:
                undo(n=-1)
            assert "n must be >= 1" in str(exc_info.value)


# =============================================================================
# Undo WIP Unwrap Tests
# =============================================================================


class TestUndoWipUnwrap:
    """Tests for WIP commit unwrapping during undo."""

    @pytest.mark.unit
    def test_undo_unwraps_wip_commit(self, temp_git_dir, sample_undo_state, mock_git_run):
        """undo should run reset --mixed HEAD~1 for WIP commits."""
        assert sample_undo_state.is_wip is True

        state_file = temp_git_dir / ".git" / "scrappy" / "undo-states.json"
        lock_path = temp_git_dir / ".git" / "scrappy.lock"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        state_dict = asdict(sample_undo_state)
        state_dict["created_at"] = sample_undo_state.created_at.isoformat()
        data = {"states": [state_dict]}
        state_file.write_text(json.dumps(data))

        commands_called = []

        def tracking_side_effect(cmd, **kwargs):
            commands_called.append(cmd)
            result = MagicMock()
            cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
            result.stderr = ""
            result.returncode = 0
            result.stdout = ""

            if "rev-parse --verify HEAD~1" in cmd_str:
                result.returncode = 0  # Parent exists
                result.stdout = "parent123\n"

            return result

        with patch("scrappy.undo.UNDO_STATE_PATH", state_file):
            with patch("scrappy.undo.LOCK_PATH", lock_path):
                with patch("os.getcwd", return_value=str(temp_git_dir)):
                    with patch("scrappy.undo.subprocess.run", side_effect=tracking_side_effect):
                        undo()

                        # Verify reset --mixed HEAD~1 was called
                        cmd_str = " ".join(commands_called)
                        assert "reset --mixed HEAD~1" in cmd_str
