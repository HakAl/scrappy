"""
Behavior tests for undo git metadata path resolution.

These tests run real git against hermetic repos under tmp_path to prove
undo works in both git repository layouts:

- normal clone: .git is a directory
- linked worktree: .git is a FILE containing a "gitdir:" pointer, and
  metadata lives under <main>/.git/worktrees/<name>

Regression coverage for scrappy-undo-broken-in-git-worktrees-aqzv: the old
code built paths from a literal ".git/" prefix, so create_undo_point()
raised NotADirectoryError inside a worktree, and merge/rebase detection
probed files that never exist there.
"""

import subprocess

import pytest

from scrappy.undo import (
    UndoError,
    check_undo_preconditions,
    create_undo_point,
    is_shallow_clone,
    load_undo_states,
    undo,
)


def _git(cwd, *args):
    """Run git in cwd, raising on failure. Returns stripped stdout."""
    result = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A real git repository with one commit (normal .git directory layout)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "file.txt").write_text("base\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


@pytest.fixture
def worktree(repo, tmp_path):
    """A linked git worktree of repo (.git is a file, not a directory)."""
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", str(wt), "-b", "wt-branch")
    return wt


class TestNormalCloneLayout:
    """Undo behavior is preserved where .git is a plain directory."""

    @pytest.mark.unit
    def test_create_and_undo_round_trip(self, repo, monkeypatch):
        """Dirty state survives create_undo_point + agent changes + undo."""
        monkeypatch.chdir(repo)
        (repo / "file.txt").write_text("user edit\n")

        create_undo_point()

        # Simulate agent work: commit on top of the WIP snapshot
        (repo / "file.txt").write_text("agent edit\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-q", "-m", "agent")

        undo()

        assert (repo / "file.txt").read_text() == "user edit\n"
        assert _git(repo, "symbolic-ref", "--short", "HEAD") == "main"

    @pytest.mark.unit
    def test_state_file_written_under_git_dir(self, repo, monkeypatch):
        """Undo states land in .git/scrappy/, same location as before the fix."""
        monkeypatch.chdir(repo)

        create_undo_point()

        assert (repo / ".git" / "scrappy" / "undo-states.json").exists()
        # Lock is released after the operation
        assert not (repo / ".git" / "scrappy.lock").exists()

    @pytest.mark.unit
    def test_merge_in_progress_blocks_undo_point(self, repo, monkeypatch):
        """An active merge (MERGE_HEAD present) blocks undo point creation."""
        monkeypatch.chdir(repo)
        (repo / ".git" / "MERGE_HEAD").write_text("deadbeef\n")

        with pytest.raises(UndoError, match="merge"):
            check_undo_preconditions()


class TestWorktreeLayout:
    """Regression tests: these fail on code that hardcodes '.git/...' paths."""

    @pytest.mark.unit
    def test_create_undo_point_in_worktree(self, worktree, monkeypatch):
        """
        create_undo_point works where .git is a file.

        Old code raised NotADirectoryError('.git/scrappy.lock') here.
        """
        assert (worktree / ".git").is_file()  # worktree layout precondition

        monkeypatch.chdir(worktree)
        (worktree / "file.txt").write_text("wt edit\n")

        state = create_undo_point()

        assert state.branch == "wt-branch"
        assert state.is_wip is True

    @pytest.mark.unit
    def test_undo_round_trip_in_worktree(self, worktree, monkeypatch):
        """Full create + undo cycle restores dirty state inside a worktree."""
        monkeypatch.chdir(worktree)
        (worktree / "file.txt").write_text("wt edit\n")

        create_undo_point()

        (worktree / "file.txt").write_text("agent edit\n")
        _git(worktree, "add", ".")
        _git(worktree, "commit", "-q", "-m", "agent")

        undo()

        assert (worktree / "file.txt").read_text() == "wt edit\n"
        assert _git(worktree, "symbolic-ref", "--short", "HEAD") == "wt-branch"

    @pytest.mark.unit
    def test_state_files_in_per_worktree_git_dir(self, repo, worktree, monkeypatch):
        """Lock and undo states go to .git/worktrees/<name>/, not the .git file."""
        monkeypatch.chdir(worktree)

        create_undo_point()

        wt_git_dir = repo / ".git" / "worktrees" / "wt"
        assert (wt_git_dir / "scrappy" / "undo-states.json").exists()
        # Lock is released after the operation
        assert not (wt_git_dir / "scrappy.lock").exists()

    @pytest.mark.unit
    def test_merge_detected_in_worktree(self, repo, worktree, monkeypatch):
        """
        An active merge inside a worktree blocks undo point creation.

        MERGE_HEAD lives in the per-worktree git dir. Old code probed
        '.git/MERGE_HEAD', which never exists in a worktree, so an active
        merge went undetected.
        """
        monkeypatch.chdir(worktree)
        (repo / ".git" / "worktrees" / "wt" / "MERGE_HEAD").write_text("deadbeef\n")

        with pytest.raises(UndoError, match="merge"):
            check_undo_preconditions()

    @pytest.mark.unit
    def test_shallow_probe_uses_common_git_dir(self, repo, worktree, monkeypatch):
        """
        The shallow marker is clone-wide: it lives in the common git dir
        and must be visible from inside a worktree.
        """
        monkeypatch.chdir(worktree)
        assert not is_shallow_clone()

        (repo / ".git" / "shallow").write_text("deadbeef\n")
        assert is_shallow_clone()

    @pytest.mark.unit
    def test_undo_states_isolated_per_worktree(self, repo, worktree, monkeypatch):
        """Undo points created in a worktree are not visible from the main clone."""
        monkeypatch.chdir(worktree)
        (worktree / "file.txt").write_text("wt edit\n")
        create_undo_point()
        assert len(load_undo_states()) == 1

        monkeypatch.chdir(repo)
        assert load_undo_states() == []
