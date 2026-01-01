"""
Git branch isolation for safe agent execution.

Provides automatic branch creation for agent work with:
- Working branch creation before agent starts
- Branch naming: scrappy/<timestamp>-<short-task-hash>
- Handling of existing branches
- Easy rollback via git checkout main
- Cleanup of old scrappy branches
"""

import hashlib
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass
class BranchInfo:
    """Information about a created branch."""

    name: str
    base_branch: str
    created: bool
    already_existed: bool = False


class GitError(Exception):
    """Error during git operation."""

    pass


class GitIsolationProtocol(Protocol):
    """Protocol for git isolation implementations."""

    def create_working_branch(self, task: str) -> BranchInfo:
        """Create a working branch for the task."""
        ...

    def rollback(self) -> bool:
        """Rollback to base branch, discarding changes."""
        ...

    def cleanup_old_branches(self, max_age_days: int) -> int:
        """Clean up old scrappy branches."""
        ...

    def get_current_branch(self) -> str:
        """Get the current branch name."""
        ...


def _run_git(
    args: list[str],
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """
    Run a git command.

    Args:
        args: Git command arguments (without 'git')
        cwd: Working directory
        check: Raise exception on non-zero exit

    Returns:
        CompletedProcess with stdout/stderr

    Raises:
        GitError: If command fails and check=True
    """
    cmd = ["git"] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if check and result.returncode != 0:
            raise GitError(f"Git command failed: {' '.join(cmd)}\n{result.stderr}")
        return result
    except subprocess.TimeoutExpired:
        raise GitError(f"Git command timed out: {' '.join(cmd)}")
    except FileNotFoundError:
        raise GitError("Git is not installed or not in PATH")


def generate_branch_name(task: str, timestamp: Optional[datetime] = None) -> str:
    """
    Generate a branch name for a task.

    Format: scrappy/<YYYYMMDD>-<short-hash>

    Args:
        task: Task description to hash
        timestamp: Optional timestamp (default: now)

    Returns:
        Branch name string
    """
    timestamp = timestamp or datetime.now()
    date_str = timestamp.strftime("%Y%m%d")

    # Generate short hash from task
    task_hash = hashlib.sha256(task.encode()).hexdigest()[:6]

    return f"scrappy/{date_str}-{task_hash}"


class GitIsolation:
    """
    Git branch isolation for safe agent execution.

    Creates a working branch before agent starts, allowing easy
    rollback if something goes wrong. Provides cleanup of old
    scrappy branches.

    Usage:
        isolation = GitIsolation(project_dir)
        branch_info = isolation.create_working_branch("Fix login bug")

        # ... agent does work ...

        # If something goes wrong:
        isolation.rollback()

        # Clean up old branches:
        isolation.cleanup_old_branches(max_age_days=7)
    """

    # Prefix for all scrappy branches
    BRANCH_PREFIX = "scrappy/"

    def __init__(
        self,
        project_dir: str,
        base_branch: Optional[str] = None,
    ):
        """
        Initialize git isolation.

        Args:
            project_dir: Path to git repository
            base_branch: Base branch to branch from (default: current branch)
        """
        self._project_dir = Path(project_dir).resolve()
        self._base_branch = base_branch
        self._current_branch: Optional[str] = None
        self._working_branch: Optional[str] = None

    def _ensure_git_repo(self) -> None:
        """Verify we're in a git repository."""
        git_dir = self._project_dir / ".git"
        if not git_dir.exists():
            raise GitError(f"Not a git repository: {self._project_dir}")

    def _get_base_branch(self) -> str:
        """Get the base branch to branch from."""
        if self._base_branch:
            return self._base_branch

        # Get current branch
        result = _run_git(
            ["rev-parse", "--abbrev-ref", "HEAD"],
            self._project_dir,
        )
        return result.stdout.strip()

    def get_current_branch(self) -> str:
        """Get the current branch name."""
        result = _run_git(
            ["rev-parse", "--abbrev-ref", "HEAD"],
            self._project_dir,
        )
        return result.stdout.strip()

    def _branch_exists(self, branch_name: str) -> bool:
        """Check if a branch exists."""
        result = _run_git(
            ["branch", "--list", branch_name],
            self._project_dir,
            check=False,
        )
        return bool(result.stdout.strip())

    def _find_available_branch_name(self, base_name: str) -> str:
        """
        Find an available branch name.

        If base_name exists, appends -1, -2, etc.

        Args:
            base_name: Desired branch name

        Returns:
            Available branch name
        """
        if not self._branch_exists(base_name):
            return base_name

        # Try suffixes up to 99
        for i in range(1, 100):
            candidate = f"{base_name}-{i}"
            if not self._branch_exists(candidate):
                return candidate

        raise GitError(f"Too many branches with prefix: {base_name}")

    def create_working_branch(self, task: str) -> BranchInfo:
        """
        Create a working branch for the task.

        Creates a new branch named scrappy/<date>-<hash> based on
        the current branch. If the branch already exists, appends
        a suffix (-1, -2, etc.).

        Args:
            task: Task description (used for hash generation)

        Returns:
            BranchInfo with branch details

        Raises:
            GitError: If branch creation fails
        """
        self._ensure_git_repo()

        # Get base branch
        base_branch = self._get_base_branch()
        self._current_branch = base_branch

        # Generate branch name
        desired_name = generate_branch_name(task)
        branch_name = self._find_available_branch_name(desired_name)
        already_existed = branch_name != desired_name

        # Create and checkout branch
        _run_git(
            ["checkout", "-b", branch_name],
            self._project_dir,
        )

        self._working_branch = branch_name

        logger.info(
            "Created working branch '%s' from '%s'%s",
            branch_name,
            base_branch,
            " (with suffix - original existed)" if already_existed else "",
        )

        return BranchInfo(
            name=branch_name,
            base_branch=base_branch,
            created=True,
            already_existed=already_existed,
        )

    def rollback(self) -> bool:
        """
        Rollback to base branch, discarding changes on working branch.

        Checks out the base branch and optionally deletes the working
        branch if it was created by this instance.

        Returns:
            True if rollback succeeded

        Raises:
            GitError: If rollback fails
        """
        if not self._current_branch:
            logger.warning("No base branch recorded, cannot rollback")
            return False

        self._ensure_git_repo()

        # Discard any uncommitted changes to tracked files
        _run_git(
            ["checkout", "--", "."],
            self._project_dir,
            check=False,  # May fail if no changes
        )

        # Remove untracked files and directories
        _run_git(
            ["clean", "-fd"],
            self._project_dir,
            check=False,  # May fail if nothing to clean
        )

        # Checkout base branch
        _run_git(
            ["checkout", self._current_branch],
            self._project_dir,
        )

        logger.info("Rolled back to '%s'", self._current_branch)

        # Optionally delete working branch
        if self._working_branch:
            try:
                _run_git(
                    ["branch", "-D", self._working_branch],
                    self._project_dir,
                )
                logger.info("Deleted working branch '%s'", self._working_branch)
            except GitError as e:
                logger.warning("Failed to delete working branch: %s", e)

        return True

    def cleanup_old_branches(self, max_age_days: int = 7) -> int:
        """
        Clean up old scrappy branches.

        Deletes scrappy/* branches older than max_age_days.

        Args:
            max_age_days: Maximum age in days to keep branches

        Returns:
            Number of branches deleted

        Raises:
            GitError: If cleanup fails
        """
        self._ensure_git_repo()

        # Get all scrappy branches with their commit dates
        result = _run_git(
            [
                "for-each-ref",
                "--sort=committerdate",
                "--format=%(refname:short) %(committerdate:unix)",
                f"refs/heads/{self.BRANCH_PREFIX}*",
            ],
            self._project_dir,
        )

        if not result.stdout.strip():
            logger.info("No scrappy branches to clean up")
            return 0

        cutoff = datetime.now() - timedelta(days=max_age_days)
        cutoff_timestamp = cutoff.timestamp()

        deleted_count = 0
        current = self.get_current_branch()

        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue

            parts = line.strip().split()
            if len(parts) != 2:
                continue

            branch_name, timestamp_str = parts

            try:
                branch_timestamp = float(timestamp_str)
            except ValueError:
                continue

            # Skip current branch
            if branch_name == current:
                continue

            # Delete if older than cutoff
            if branch_timestamp < cutoff_timestamp:
                try:
                    _run_git(
                        ["branch", "-D", branch_name],
                        self._project_dir,
                    )
                    deleted_count += 1
                    logger.info("Deleted old branch '%s'", branch_name)
                except GitError as e:
                    logger.warning("Failed to delete branch '%s': %s", branch_name, e)

        logger.info("Cleaned up %d old scrappy branches", deleted_count)
        return deleted_count

    def list_scrappy_branches(self) -> list[str]:
        """
        List all scrappy branches.

        Returns:
            List of branch names
        """
        self._ensure_git_repo()

        result = _run_git(
            [
                "for-each-ref",
                "--format=%(refname:short)",
                f"refs/heads/{self.BRANCH_PREFIX}*",
            ],
            self._project_dir,
        )

        if not result.stdout.strip():
            return []

        return [
            line.strip()
            for line in result.stdout.strip().split("\n")
            if line.strip()
        ]


def create_git_isolation(
    project_dir: str,
    base_branch: Optional[str] = None,
) -> GitIsolation:
    """
    Factory function for creating GitIsolation.

    Args:
        project_dir: Path to git repository
        base_branch: Base branch to branch from

    Returns:
        Configured GitIsolation instance
    """
    return GitIsolation(
        project_dir=project_dir,
        base_branch=base_branch,
    )
