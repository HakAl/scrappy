"""Unit tests for git isolation."""

import subprocess
from datetime import datetime
from unittest.mock import patch

import pytest

from scrappy.sandbox.git_isolation import (
    BranchInfo,
    GitError,
    GitIsolation,
    _run_git,
    create_git_isolation,
    generate_branch_name,
)


class TestGenerateBranchName:
    """Tests for branch name generation."""

    def test_includes_date_prefix(self):
        """Branch name includes date prefix."""
        timestamp = datetime(2025, 1, 15, 10, 30, 0)
        name = generate_branch_name("test task", timestamp)
        assert name.startswith("scrappy/20250115-")

    def test_includes_task_hash(self):
        """Branch name includes task hash suffix."""
        name = generate_branch_name("test task")
        parts = name.split("-")
        assert len(parts[-1]) == 6  # 6 char hash

    def test_same_task_same_hash(self):
        """Same task produces same hash."""
        timestamp = datetime(2025, 1, 15)
        name1 = generate_branch_name("fix login bug", timestamp)
        name2 = generate_branch_name("fix login bug", timestamp)
        assert name1 == name2

    def test_different_task_different_hash(self):
        """Different task produces different hash."""
        timestamp = datetime(2025, 1, 15)
        name1 = generate_branch_name("fix login bug", timestamp)
        name2 = generate_branch_name("add user profile", timestamp)
        assert name1 != name2

    def test_uses_current_time_by_default(self):
        """Uses current time when no timestamp provided."""
        name = generate_branch_name("test")
        today = datetime.now().strftime("%Y%m%d")
        assert today in name


class TestRunGit:
    """Tests for _run_git helper."""

    def test_runs_git_command(self, tmp_path):
        """Runs git command and returns result."""
        # Initialize a git repo
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)

        result = _run_git(["status"], tmp_path, check=False)
        assert result.returncode == 0

    def test_no_raise_on_failure_without_check(self, tmp_path):
        """Does not raise on failure when check=False."""
        result = _run_git(["status"], tmp_path, check=False)
        # Not a git repo, so status fails
        assert result.returncode != 0


class TestGitIsolation:
    """Tests for GitIsolation class."""

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a temporary git repository."""
        subprocess.run(
            ["git", "init"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        # Create initial commit
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(
            ["git", "add", "."],
            cwd=str(tmp_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        return tmp_path  # Should not raise

    def test_get_current_branch(self, git_repo):
        """Returns current branch name."""
        isolation = GitIsolation(str(git_repo))
        branch = isolation.get_current_branch()
        assert branch in ["main", "master"]

    def test_create_working_branch_creates_branch(self, git_repo):
        """Creates a new working branch."""
        isolation = GitIsolation(str(git_repo))
        info = isolation.create_working_branch("test task")

        assert info.created is True
        assert info.name.startswith("scrappy/")
        assert isolation.get_current_branch() == info.name

    def test_create_working_branch_records_base(self, git_repo):
        """Records the base branch for rollback."""
        isolation = GitIsolation(str(git_repo))
        original_branch = isolation.get_current_branch()

        info = isolation.create_working_branch("test task")

        assert info.base_branch == original_branch

    def test_create_working_branch_handles_existing(self, git_repo):
        """Appends suffix when branch already exists."""
        isolation = GitIsolation(str(git_repo))

        # Create first branch
        info1 = isolation.create_working_branch("test task")
        first_branch = info1.name

        # Checkout back to main
        subprocess.run(
            ["git", "checkout", info1.base_branch],
            cwd=str(git_repo),
            capture_output=True,
        )

        # Create second branch with same task (same date/hash)
        isolation2 = GitIsolation(str(git_repo))
        info2 = isolation2.create_working_branch("test task")

        assert info2.name == f"{first_branch}-1"
        assert info2.already_existed is True

    def test_rollback_returns_to_base_branch(self, git_repo):
        """Rollback returns to base branch."""
        isolation = GitIsolation(str(git_repo))
        original_branch = isolation.get_current_branch()

        isolation.create_working_branch("test task")
        isolation.rollback()

        assert isolation.get_current_branch() == original_branch

    def test_rollback_deletes_working_branch(self, git_repo):
        """Rollback deletes the working branch."""
        isolation = GitIsolation(str(git_repo))
        info = isolation.create_working_branch("test task")
        working_branch = info.name

        isolation.rollback()

        # Branch should be deleted
        assert not isolation._branch_exists(working_branch)

    def test_rollback_discards_changes(self, git_repo):
        """Rollback discards uncommitted changes."""
        isolation = GitIsolation(str(git_repo))
        isolation.create_working_branch("test task")

        # Make a change
        (git_repo / "new_file.txt").write_text("content")

        isolation.rollback()

        # File should not exist after rollback
        assert not (git_repo / "new_file.txt").exists()

    def test_rollback_returns_false_without_base(self, git_repo):
        """Returns False if no base branch recorded."""
        isolation = GitIsolation(str(git_repo))
        # Don't create a working branch
        assert isolation.rollback() is False

    def test_list_scrappy_branches(self, git_repo):
        """Lists all scrappy branches."""
        isolation = GitIsolation(str(git_repo))

        # Create some branches
        info1 = isolation.create_working_branch("task 1")
        subprocess.run(
            ["git", "checkout", info1.base_branch],
            cwd=str(git_repo),
            capture_output=True,
        )

        isolation2 = GitIsolation(str(git_repo))
        info2 = isolation2.create_working_branch("task 2")

        branches = isolation2.list_scrappy_branches()

        assert len(branches) == 2
        assert info1.name in branches
        assert info2.name in branches

    def test_cleanup_old_branches_deletes_old(self, git_repo):
        """Cleans up branches older than max_age_days."""
        isolation = GitIsolation(str(git_repo))

        # Create a branch
        info = isolation.create_working_branch("old task")

        # Go back to main
        subprocess.run(
            ["git", "checkout", info.base_branch],
            cwd=str(git_repo),
            capture_output=True,
        )

        # Cleanup with 0 days should delete it
        isolation2 = GitIsolation(str(git_repo))
        deleted = isolation2.cleanup_old_branches(max_age_days=0)

        assert deleted == 1
        assert not isolation2._branch_exists(info.name)

    def test_cleanup_preserves_recent_branches(self, git_repo):
        """Does not delete recent branches."""
        isolation = GitIsolation(str(git_repo))

        # Create a branch
        info = isolation.create_working_branch("recent task")

        # Go back to main
        subprocess.run(
            ["git", "checkout", info.base_branch],
            cwd=str(git_repo),
            capture_output=True,
        )

        # Cleanup with 7 days should not delete it
        isolation2 = GitIsolation(str(git_repo))
        deleted = isolation2.cleanup_old_branches(max_age_days=7)

        assert deleted == 0
        assert isolation2._branch_exists(info.name)

    def test_cleanup_skips_current_branch(self, git_repo):
        """Does not delete current branch."""
        isolation = GitIsolation(str(git_repo))
        info = isolation.create_working_branch("current task")

        # Don't checkout back to main - stay on scrappy branch
        deleted = isolation.cleanup_old_branches(max_age_days=0)

        assert deleted == 0
        assert isolation._branch_exists(info.name)


class TestBranchInfo:
    """Tests for BranchInfo dataclass."""

    def test_created_branch(self):
        """Created branch has correct fields."""
        info = BranchInfo(
            name="scrappy/20250115-abc123",
            base_branch="main",
            created=True,
        )
        assert info.name == "scrappy/20250115-abc123"
        assert info.base_branch == "main"
        assert info.created is True
        assert info.already_existed is False

    def test_existing_branch(self):
        """Existing branch variant has already_existed=True."""
        info = BranchInfo(
            name="scrappy/20250115-abc123-1",
            base_branch="main",
            created=True,
            already_existed=True,
        )
        assert info.already_existed is True


class TestCreateGitIsolation:
    """Tests for factory function."""

    def test_creates_isolation_instance(self, tmp_path):
        """Factory creates GitIsolation instance."""
        isolation = create_git_isolation(str(tmp_path))
        assert isinstance(isolation, GitIsolation)

    def test_passes_base_branch(self, tmp_path):
        """Passes base_branch to GitIsolation."""
        isolation = create_git_isolation(str(tmp_path), base_branch="develop")
        assert isolation._base_branch == "develop"
