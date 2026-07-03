"""Undo system for safe rollback of agent runs.

This module provides a shadow ref-based undo mechanism that safely captures
and restores git state before/after agent operations.

Key concepts:
- Before agent runs, create a "snapshot" as a shadow ref (refs/scrappy/undo/<id>)
- If working directory is dirty, commit it temporarily (WIP commit)
- User can undo with scrappy undo - restores exact pre-agent state

Note:
    Restoring a dirty state will result in all changes being unstaged,
    regardless of their staged/unstaged status before the agent run.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
import warnings
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from scrappy import __version__


class UndoError(Exception):
    """Raised when undo operations fail."""

    pass


@dataclass
class UndoState:
    """Represents a snapshot of git state that can be restored.

    Attributes:
        ref: Git ref path (refs/scrappy/undo/<timestamp>)
        branch: Original branch name, or None if detached HEAD
        original_head: If detached, the original commit SHA
        is_wip: Whether we created a WIP commit for dirty state
        worktree_path: Path where undo point was created (for validation)
        created_at: When the undo point was created
        scrappy_version: Version of scrappy that created this point
    """

    ref: str
    branch: Optional[str]
    original_head: Optional[str]
    is_wip: bool
    worktree_path: str
    created_at: datetime
    scrappy_version: str


# Lock configuration
LOCK_TIMEOUT = 30  # seconds


def _run(cmd: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the result.

    Args:
        cmd: The command to run
        check: Whether to raise on non-zero exit

    Returns:
        CompletedProcess with stdout/stderr

    Raises:
        subprocess.CalledProcessError: If check=True and command fails
    """
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        check=check,
        stdin=subprocess.DEVNULL,  # Prevent terminal interaction in TUI worker threads
    )
    return result


# =============================================================================
# Git Metadata Path Resolution
# =============================================================================
#
# Never build git metadata paths from a literal ".git/" prefix: in a linked
# git worktree, <worktree>/.git is a FILE containing a "gitdir:" pointer, and
# the real metadata lives elsewhere. Resolution rules used here:
#
# Per-worktree git dir (git rev-parse --git-dir):
#   MERGE_HEAD, REBASE_HEAD, CHERRY_PICK_HEAD, rebase-merge, rebase-apply
#   (in-progress operation state is tracked per worktree), plus scrappy's
#   own lock and undo-state files (an undo point captures per-worktree
#   state: HEAD, branch, and working tree).
#
# Common git dir shared by all worktrees (git rev-parse --git-common-dir):
#   shallow (a clone-wide property).
#
# In a normal clone both resolve to ".git", so behavior there is unchanged.


def _resolve_git_dir(flag: str) -> Path:
    """Resolve a git metadata directory via git rev-parse.

    Args:
        flag: Either "--git-dir" or "--git-common-dir".

    Raises:
        UndoError: If the current directory is not inside a git repository.
    """
    result = _run(f"git rev-parse {flag}", check=False)
    if result.returncode != 0:
        raise UndoError(
            f"Cannot resolve git directory ({flag}): "
            f"not inside a git repository?"
        )
    return Path(result.stdout.strip())


def _git_dir() -> Path:
    """Per-worktree git dir (".git" in a normal clone)."""
    return _resolve_git_dir("--git-dir")


def _git_common_dir() -> Path:
    """Git dir shared across worktrees (same as _git_dir in a normal clone)."""
    return _resolve_git_dir("--git-common-dir")


def _lock_path() -> Path:
    """Location of the scrappy undo lock file."""
    return _git_dir() / "scrappy.lock"


def _undo_state_path() -> Path:
    """Location of the persisted undo states file."""
    return _git_dir() / "scrappy" / "undo-states.json"


# =============================================================================
# Helper Functions
# =============================================================================


def get_current_branch() -> Optional[str]:
    """Return current branch name, or None if detached HEAD."""
    result = _run("git symbolic-ref --short HEAD", check=False)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def get_head_sha() -> str:
    """Return current HEAD commit SHA."""
    return _run("git rev-parse HEAD").stdout.strip()


def is_dirty() -> bool:
    """Check for staged or unstaged changes."""
    result = _run("git diff --quiet", check=False)
    if result.returncode != 0:
        return True
    result = _run("git diff --cached --quiet", check=False)
    return result.returncode != 0


def has_untracked() -> bool:
    """Check for untracked files (excluding ignored)."""
    result = _run("git ls-files --others --exclude-standard")
    return bool(result.stdout.strip())


def has_staged_changes() -> bool:
    """Check if there are actually staged changes to commit."""
    result = _run("git diff --cached --quiet", check=False)
    return result.returncode != 0


def is_shallow_clone() -> bool:
    """Check if this is a shallow clone."""
    return (_git_common_dir() / "shallow").exists()


# =============================================================================
# Lock Management
# =============================================================================


@contextmanager
def undo_lock() -> Iterator[None]:
    """Prevent concurrent undo operations using atomic file creation.

    Uses os.open with O_CREAT | O_EXCL for atomic lock acquisition,
    avoiding TOCTOU race conditions.

    Raises:
        UndoError: If lock cannot be acquired within LOCK_TIMEOUT seconds
    """
    lock_path = _lock_path()
    start = time.time()

    while True:
        try:
            # Atomic file creation - fails if file exists (no TOCTOU race)
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break  # Lock acquired
        except FileExistsError:
            if time.time() - start > LOCK_TIMEOUT:
                raise UndoError(
                    f"Another scrappy process holds the lock. "
                    f"If this is stale, remove {lock_path}"
                )
            time.sleep(0.1)

    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


# =============================================================================
# Precondition Checks
# =============================================================================


def check_undo_preconditions() -> None:
    """Refuse to create undo point in unsafe states.

    Raises:
        UndoError: If in the middle of a merge, rebase, or cherry-pick
    """
    # Cannot create undo during merge/rebase/cherry-pick.
    # These all live in the per-worktree git dir.
    git_dir = _git_dir()
    problem_indicators = [
        ("MERGE_HEAD", "merge"),
        ("REBASE_HEAD", "rebase"),
        ("CHERRY_PICK_HEAD", "cherry-pick"),
        ("rebase-merge", "interactive rebase"),
        ("rebase-apply", "rebase/am"),
    ]

    for name, operation in problem_indicators:
        if (git_dir / name).exists():
            raise UndoError(
                f"Cannot create undo point during active {operation}. "
                f"Complete or abort the {operation} first."
            )


# =============================================================================
# Create Undo Point
# =============================================================================


def create_undo_point() -> UndoState:
    """Create a snapshot of current state before agent runs.

    Returns:
        UndoState that can be used to restore this exact state.

    Raises:
        UndoError: If in an unsafe git state (merge/rebase in progress),
            or if git operations fail (e.g., not a git repository).

    Note:
        Restoring a dirty state will result in all changes being unstaged,
        regardless of their staged/unstaged status before the agent run.
    """
    # 1. Precondition checks
    check_undo_preconditions()

    # Warn about shallow clone limitations
    if is_shallow_clone():
        warnings.warn(
            "This is a shallow clone. Undo may fail for points "
            "beyond the shallow boundary.",
            UserWarning,
        )

    try:
        with undo_lock():
            # 2. Capture current state
            branch = get_current_branch()
            original_head = None if branch else get_head_sha()

            # 3. Snapshot dirty state as WIP commit
            is_wip = False
            if is_dirty() or has_untracked():
                _run("git add -A")

                # Only commit if there is actually something staged
                # (git add -A on all-ignored files results in nothing staged)
                if has_staged_changes():
                    # --no-verify: bypass pre-commit hooks for internal commit
                    _run("git commit --no-verify -m 'scrappy:wip'")
                    is_wip = True
                else:
                    # Nothing to commit - unstage and continue
                    _run("git reset HEAD")

            # 4. Create unique ref (no worktree ID - lock handles concurrency)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:20]
            ref = f"refs/scrappy/undo/{ts}"
            _run(f"git update-ref {ref} HEAD")

            # 5. Build state object
            state = UndoState(
                ref=ref,
                branch=branch,
                original_head=original_head,
                is_wip=is_wip,
                worktree_path=os.getcwd(),
                created_at=datetime.now(),
                scrappy_version=__version__,
            )

            # 6. Persist and prune
            persist_undo_state(state)
            prune_old_undo_states(keep=10)

            return state
    except subprocess.CalledProcessError as e:
        # Wrap git errors in UndoError for consistent error handling
        raise UndoError(
            f"Git operation failed: {e.cmd} returned exit status {e.returncode}"
        ) from e


# =============================================================================
# Undo
# =============================================================================


def undo(n: int = 1, force: bool = False) -> None:
    """Restore state from n-th most recent undo point.

    Args:
        n: Which undo point (1 = most recent, 2 = second most recent, etc.)
        force: Bypass worktree path check (use if directory was moved).

    Raises:
        UndoError: If no undo points, wrong worktree, or git operation fails.

    Note:
        Restoring a dirty state will result in all changes being unstaged,
        regardless of their staged/unstaged status before the agent run.
    """
    states = load_undo_states()

    if not states:
        raise UndoError("No undo points available")

    if n < 1:
        raise UndoError("n must be >= 1 (1 = most recent)")

    if n > len(states):
        raise UndoError(f"Only {len(states)} undo points available")

    # Get n-th most recent (states are ordered oldest-first)
    state = states[-n]

    # Verify we are in the right worktree (unless --force)
    if os.getcwd() != state.worktree_path and not force:
        raise UndoError(
            f"Undo point was created in {state.worktree_path}. "
            f"Use --force if you moved the directory."
        )

    with undo_lock():
        try:
            # 1. Restore branch context
            if state.branch:
                # Was on a branch - try to restore it
                branch_quoted = shlex.quote(state.branch)
                result = _run(f"git checkout -f {branch_quoted}", check=False)
                if result.returncode != 0:
                    # Branch was deleted by agent - recreate it at the ref
                    _run(f"git checkout -b {branch_quoted} {shlex.quote(state.ref)}")
            elif state.original_head:
                # Was in detached HEAD - restore exact position
                _run(f"git checkout --detach {state.original_head}")
            else:
                # Fallback - detach at the ref
                _run(f"git checkout --detach {state.ref}")

            # 2. Hard reset to snapshot
            _run(f"git reset --hard {state.ref}")

            # 3. Unwrap WIP commit to restore dirty state
            if state.is_wip:
                # Handle root commit edge case: check if HEAD~1 exists
                result = _run("git rev-parse --verify HEAD~1", check=False)
                if result.returncode == 0:
                    # Normal case: parent exists
                    _run("git reset --mixed HEAD~1")
                else:
                    # Root commit case: WIP is the only commit
                    # Move HEAD back and unstage manually
                    _run("git update-ref -d HEAD")
                    _run("git reset")

            # 4. Cleanup this undo point
            remove_undo_state(state)
            _run(f"git update-ref -d {state.ref}")

        except subprocess.CalledProcessError as e:
            raise UndoError(
                f"Undo failed during git operation: {e}. "
                f"Repository may be in inconsistent state. "
                f"Run git status to check."
            )


# =============================================================================
# Persistence Functions
# =============================================================================


def persist_undo_state(state: UndoState) -> None:
    """Add state to persistent storage."""
    state_path = _undo_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)

    states = load_undo_states()
    states.append(state)

    data = {"states": [asdict(s) for s in states]}
    state_path.write_text(json.dumps(data, indent=2, default=str))


def load_undo_states() -> list[UndoState]:
    """Load all undo states from storage."""
    state_path = _undo_state_path()
    if not state_path.exists():
        return []

    data = json.loads(state_path.read_text())
    states = []
    for s in data.get("states", []):
        # Convert datetime string back to datetime object
        if isinstance(s.get("created_at"), str):
            s["created_at"] = datetime.fromisoformat(s["created_at"])
        states.append(UndoState(**s))
    return states


def remove_undo_state(state: UndoState) -> None:
    """Remove a specific state from storage."""
    states = load_undo_states()
    states = [s for s in states if s.ref != state.ref]

    data = {"states": [asdict(s) for s in states]}
    _undo_state_path().write_text(json.dumps(data, indent=2, default=str))


def get_undo_limit() -> int:
    """Get configured undo limit from env var or default."""
    return int(os.environ.get("SCRAPPY_UNDO_LIMIT", "10"))


def prune_old_undo_states(keep: Optional[int] = None) -> None:
    """Remove oldest undo states, keeping only the most recent N.

    Args:
        keep: Number of states to keep. Defaults to get_undo_limit().
    """
    if keep is None:
        keep = get_undo_limit()

    states = load_undo_states()

    if len(states) <= keep:
        return

    # Remove oldest states (and their refs)
    to_remove = states[:-keep]
    for state in to_remove:
        _run(f"git update-ref -d {state.ref}", check=False)

    # Keep only newest
    states = states[-keep:]
    data = {"states": [asdict(s) for s in states]}
    _undo_state_path().write_text(json.dumps(data, indent=2, default=str))
