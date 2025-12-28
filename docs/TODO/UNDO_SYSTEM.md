# Undo System Design

**Status**: v4 FINAL (ready for implementation)
**Issue**: scrappy-3zhu
**Reviewer**: Reba (QA)

## Problem Statement

The current code suggests `git reset --hard` to users for rollback after agent runs:

```python
# src/scrappy/cli/commands.py:575
click.echo(f"\nTo rollback changes: git reset --hard {checkpoint_hash}")
```

This is dangerous because:
1. No warning about data loss
2. Destroys uncommitted work
3. Can corrupt wrong branch if agent switched branches

## Solution: Shadow Ref Undo with WIP Commits

### Core Concept

1. Before agent runs, create a "snapshot" of the current state
2. Store snapshot as a shadow ref (`refs/scrappy/undo/<id>`)
3. If working directory is dirty, commit it temporarily (WIP commit)
4. Agent does its work (can do anything - commits, resets, clean)
5. User can undo with `scrappy undo` - restores exact pre-agent state

### Why WIP Commits Instead of Stash

| Aspect | Stash | WIP Commit |
|--------|-------|------------|
| `git clean -fd` proof | No | Yes (files in tree) |
| Conflict risk | High | None |
| External state needed | UUID tracking | None |
| Stack management | Complex | None |

## Data Model

```python
@dataclass
class UndoState:
    ref: str                     # refs/scrappy/undo/<timestamp>
    branch: Optional[str]        # Original branch name, None if detached
    original_head: Optional[str] # If detached, the original commit SHA
    is_wip: bool                 # Whether we created a WIP commit
    worktree_path: str           # For validation (--force to bypass)
    created_at: datetime         # For display and cleanup
    scrappy_version: str         # For forward compatibility
```

### Storage

State persisted to `.git/scrappy/undo-states.json`:

```json
{
  "states": [
    {
      "ref": "refs/scrappy/undo/20250128-143022-123456",
      "branch": "main",
      "original_head": null,
      "is_wip": true,
      "worktree_path": "/home/user/project",
      "created_at": "2025-01-28T14:30:22.123456",
      "scrappy_version": "0.1.0"
    }
  ]
}
```

## Implementation

### Precondition Checks

```python
def check_undo_preconditions() -> None:
    """Refuse to create undo point in unsafe states."""

    # Cannot create undo during merge/rebase/cherry-pick
    problem_indicators = [
        (".git/MERGE_HEAD", "merge"),
        (".git/REBASE_HEAD", "rebase"),
        (".git/CHERRY_PICK_HEAD", "cherry-pick"),
        (".git/rebase-merge", "interactive rebase"),
        (".git/rebase-apply", "rebase/am"),
    ]

    for path, operation in problem_indicators:
        if Path(path).exists():
            raise UndoError(
                f"Cannot create undo point during active {operation}. "
                f"Complete or abort the {operation} first."
            )
```

### Lock Management

```python
LOCK_PATH = Path(".git/scrappy.lock")
LOCK_TIMEOUT = 30  # seconds

@contextmanager
def undo_lock():
    """Prevent concurrent undo operations using atomic file creation."""
    start = time.time()

    while True:
        try:
            # Atomic file creation - fails if file exists (no TOCTOU race)
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break  # Lock acquired
        except FileExistsError:
            if time.time() - start > LOCK_TIMEOUT:
                raise UndoError(
                    f"Another scrappy process holds the lock. "
                    f"If this is stale, remove {LOCK_PATH}"
                )
            time.sleep(0.1)

    try:
        yield
    finally:
        LOCK_PATH.unlink(missing_ok=True)
```

### Helper Functions

```python
def get_current_branch() -> Optional[str]:
    """Return current branch name, or None if detached HEAD."""
    result = run("git symbolic-ref --short HEAD", check=False)
    if result.returncode == 0:
        return result.stdout.strip()
    return None

def get_head_sha() -> str:
    """Return current HEAD commit SHA."""
    return run("git rev-parse HEAD").stdout.strip()

def is_dirty() -> bool:
    """Check for staged or unstaged changes."""
    result = run("git diff --quiet", check=False)
    if result.returncode != 0:
        return True
    result = run("git diff --cached --quiet", check=False)
    return result.returncode != 0

def has_untracked() -> bool:
    """Check for untracked files (excluding ignored)."""
    result = run("git ls-files --others --exclude-standard")
    return bool(result.stdout.strip())

def has_staged_changes() -> bool:
    """Check if there are actually staged changes to commit."""
    result = run("git diff --cached --quiet", check=False)
    return result.returncode != 0

def is_shallow_clone() -> bool:
    """Check if this is a shallow clone."""
    return Path(".git/shallow").exists()
```

### Create Undo Point

```python
def create_undo_point() -> UndoState:
    """
    Create a snapshot of current state before agent runs.

    Returns:
        UndoState that can be used to restore this exact state.

    Raises:
        UndoError: If in an unsafe git state (merge/rebase in progress).

    Note:
        Restoring a dirty state will result in all changes being unstaged,
        regardless of their staged/unstaged status before the agent run.
    """
    # 1. Precondition checks
    check_undo_preconditions()

    # Warn about shallow clone limitations
    if is_shallow_clone():
        import warnings
        warnings.warn(
            "This is a shallow clone. Undo may fail for points "
            "beyond the shallow boundary.",
            UserWarning,
        )

    with undo_lock():
        # 2. Capture current state
        branch = get_current_branch()
        original_head = None if branch else get_head_sha()

        # 3. Snapshot dirty state as WIP commit
        is_wip = False
        if is_dirty() or has_untracked():
            run("git add -A")

            # Only commit if there's actually something staged
            # (git add -A on all-ignored files results in nothing staged)
            if has_staged_changes():
                # --no-verify: bypass pre-commit hooks for internal commit
                run("git commit --no-verify -m 'scrappy:wip'")
                is_wip = True
            else:
                # Nothing to commit - unstage and continue
                run("git reset HEAD")

        # 4. Create unique ref (no worktree ID - lock handles concurrency)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:20]
        ref = f"refs/scrappy/undo/{ts}"
        run(f"git update-ref {ref} HEAD")

        # 5. Build state object
        state = UndoState(
            ref=ref,
            branch=branch,
            original_head=original_head,
            is_wip=is_wip,
            worktree_path=os.getcwd(),
            created_at=datetime.now(),
            scrappy_version=VERSION,
        )

        # 6. Persist and prune
        persist_undo_state(state)
        prune_old_undo_states(keep=10)

        return state
```

### Undo

```python
def undo(n: int = 1, force: bool = False) -> None:
    """
    Restore state from n-th most recent undo point.

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

    if n > len(states):
        raise UndoError(f"Only {len(states)} undo points available")

    # Get n-th most recent (states are ordered oldest-first)
    state = states[-n]

    # Verify we're in the right worktree (unless --force)
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
                result = run(f"git checkout -f {state.branch}", check=False)
                if result.returncode != 0:
                    # Branch was deleted by agent - recreate it at the ref
                    run(f"git checkout -b {state.branch} {state.ref}")
            elif state.original_head:
                # Was in detached HEAD - restore exact position
                run(f"git checkout --detach {state.original_head}")
            else:
                # Fallback - detach at the ref
                run(f"git checkout --detach {state.ref}")

            # 2. Hard reset to snapshot
            run(f"git reset --hard {state.ref}")

            # 3. Unwrap WIP commit to restore dirty state
            if state.is_wip:
                # Handle root commit edge case: check if HEAD~1 exists
                result = run("git rev-parse --verify HEAD~1", check=False)
                if result.returncode == 0:
                    # Normal case: parent exists
                    run("git reset --mixed HEAD~1")
                else:
                    # Root commit case: WIP is the only commit
                    # Move HEAD back and unstage manually
                    run("git update-ref -d HEAD")
                    run("git reset")

            # 4. Cleanup this undo point
            remove_undo_state(state)
            run(f"git update-ref -d {state.ref}")

        except subprocess.CalledProcessError as e:
            raise UndoError(
                f"Undo failed during git operation: {e}. "
                f"Repository may be in inconsistent state. "
                f"Run 'git status' to check."
            )
```

### Persistence

```python
UNDO_STATE_PATH = Path(".git/scrappy/undo-states.json")

def persist_undo_state(state: UndoState) -> None:
    """Add state to persistent storage."""
    UNDO_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    states = load_undo_states()
    states.append(state)

    data = {
        "states": [asdict(s) for s in states]
    }
    UNDO_STATE_PATH.write_text(json.dumps(data, indent=2, default=str))

def load_undo_states() -> list[UndoState]:
    """Load all undo states from storage."""
    if not UNDO_STATE_PATH.exists():
        return []

    data = json.loads(UNDO_STATE_PATH.read_text())
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
    UNDO_STATE_PATH.write_text(json.dumps(data, indent=2, default=str))

def get_undo_limit() -> int:
    """Get configured undo limit from env var or default."""
    return int(os.environ.get("SCRAPPY_UNDO_LIMIT", "10"))

def prune_old_undo_states(keep: Optional[int] = None) -> None:
    """Remove oldest undo states, keeping only the most recent N."""
    if keep is None:
        keep = get_undo_limit()

    states = load_undo_states()

    if len(states) <= keep:
        return

    # Remove oldest states (and their refs)
    to_remove = states[:-keep]
    for state in to_remove:
        run(f"git update-ref -d {state.ref}", check=False)

    # Keep only newest
    states = states[-keep:]
    data = {"states": [asdict(s) for s in states]}
    UNDO_STATE_PATH.write_text(json.dumps(data, indent=2, default=str))
```

### CLI Commands

```python
@cli.command()
@click.argument("n", default=1, type=int)
@click.option("--force", is_flag=True, help="Bypass worktree path check (if directory was moved)")
def undo(n: int, force: bool):
    """Undo the last N agent runs."""
    try:
        undo_module.undo(n, force=force)
        click.secho(f"Restored to state before agent run #{n}", fg="green")
    except UndoError as e:
        click.secho(f"Undo failed: {e}", fg="red")
        raise SystemExit(1)

@cli.command("undo-list")
def undo_list():
    """List available undo points."""
    states = undo_module.load_undo_states()

    if not states:
        click.echo("No undo points available")
        return

    click.echo(f"Available undo points ({len(states)}):\n")
    for i, state in enumerate(reversed(states), 1):
        branch_info = state.branch or f"detached@{state.original_head[:7]}"
        wip_marker = " [dirty]" if state.is_wip else ""
        click.echo(f"  {i}. {state.created_at:%Y-%m-%d %H:%M:%S} on {branch_info}{wip_marker}")

@cli.command("undo-gc")
@click.option("--keep", default=10, help="Number of undo points to keep")
def undo_gc(keep: int):
    """Clean up old undo points."""
    before = len(undo_module.load_undo_states())
    undo_module.prune_old_undo_states(keep=keep)
    after = len(undo_module.load_undo_states())

    removed = before - after
    click.echo(f"Removed {removed} undo points, kept {after}")
```

## Edge Cases and Limitations

### Handled

| Edge Case | How Handled |
|-----------|-------------|
| Empty commit | Check `has_staged_changes()` before commit |
| Pre-commit hooks | Use `--no-verify` flag |
| Detached HEAD | Store `original_head` SHA |
| Merge/rebase in progress | Refuse with clear error |
| Concurrent sessions | Atomic lockfile (O_CREAT\|O_EXCL) with timeout |
| Timestamp collision | Include microseconds in ref |
| Worktree path mismatch | Validate path, `--force` to bypass if moved |
| Crash recovery | State persisted immediately after ref creation |
| Branch deleted by agent | Recreate branch at ref position during undo |
| Partial undo failure | try/except with helpful error message |
| Datetime serialization | Convert string to datetime on load |
| Shallow clone | Warn on create, document limitation |
| Root commit edge case | Check if HEAD~1 exists before reset |

### Documented Limitations (v1)

| Limitation | Reason |
|------------|--------|
| Index fidelity | Staged vs unstaged distinction lost on restore. Better than losing files. |
| Submodules | Dirty state inside submodules not captured. |
| Large binaries | Could be slow/memory-intensive. Add warning for files >50MB. |
| Shallow clones | Undo may fail for points beyond shallow boundary. |
| Ignored files | Files in `.gitignore` are not captured. By design. |

## Test Plan

### Unit Tests

1. `test_check_preconditions_clean` - passes on clean repo
2. `test_check_preconditions_merge` - raises during merge
3. `test_check_preconditions_rebase` - raises during rebase
4. `test_create_undo_point_clean` - creates ref, no WIP
5. `test_create_undo_point_dirty` - creates ref with WIP commit
6. `test_create_undo_point_untracked` - includes untracked files
7. `test_create_undo_point_all_ignored` - handles nothing-to-commit case
8. `test_create_undo_point_detached` - stores original HEAD
9. `test_undo_restores_branch` - restores to original branch
10. `test_undo_restores_detached` - restores detached HEAD position
11. `test_undo_unwraps_wip` - dirty state restored (all unstaged)
12. `test_undo_wrong_worktree` - raises with helpful error
13. `test_undo_wrong_worktree_force` - bypasses with --force flag
14. `test_undo_state_persistence_roundtrip` - save and load preserves all fields including datetime
15. `test_undo_branch_deleted` - recreates branch if agent deleted it
16. `test_undo_partial_failure` - error handling leaves helpful message
17. `test_undo_root_commit` - handles WIP on initial commit

### Integration Tests

1. `test_full_cycle_clean` - create -> agent changes -> undo -> verify state
2. `test_full_cycle_dirty` - dirty files preserved through cycle
3. `test_agent_git_clean` - untracked files survive `git clean -fd`
4. `test_agent_branch_switch` - correct branch restored after switch
5. `test_agent_branch_delete` - branch recreated after deletion
6. `test_multiple_undo_points` - can undo to nth point
7. `test_prune_removes_oldest` - old refs cleaned up
8. `test_shallow_clone_warning` - warning issued on shallow clone

### Manual Test Cases

1. Pre-commit hook rejection with `--no-verify` bypass
2. Concurrent `scrappy` invocations (lock contention)
3. Crash during agent run (state should exist for recovery)
4. Very large repo performance

## Migration

Replace current rollback suggestion:

```python
# Before (dangerous)
click.echo(f"\nTo rollback changes: git reset --hard {checkpoint_hash}")

# After (safe)
click.echo(f"\nTo rollback changes: scrappy undo")
```

## Design Decisions (Resolved)

1. **No undo-of-undo**: Undo does not create its own undo point. Avoids recursion risk.
   If user wants to "redo", use `git reflog` or re-run the agent.

2. **Simple undo-list**: Just show timestamp + branch. The "after" state is gone,
   so computing a diff is not possible. Keep it cheap.

3. **Configurable keep count**: Default 10, configurable via `SCRAPPY_UNDO_LIMIT` env var.
   Users with large binary repos may want to lower this to 3.
