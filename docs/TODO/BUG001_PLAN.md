# BUG-001: Thread-Safe Shutdown for Semantic Search

## Problem

When the TUI app exits, background threads (semantic search initialization, indexing) must terminate cleanly. The current infrastructure has the pieces but they're not wired up, and the previous plan relied on timeouts which are tech debt.

**Root cause:** `on_unmount()` doesn't signal the background threads to stop.

## Architecture (Already Exists)

```
ManagedThread
  - shutdown_requested: bool (via threading.Event)
  - stop() -> sets event, joins thread
  - Worker checks shutdown_requested periodically

SemanticSearchInitializer
  - Uses ManagedThread internally
  - shutdown() -> calls thread.stop()
  - Worker has shutdown checkpoints throughout

SemanticSearchManager
  - Holds reference to initializer
  - Missing: shutdown() method

CodebaseContext
  - Holds reference to manager
  - Missing: shutdown() method
```

## Solution: Propagate Shutdown Signal

Add `shutdown()` methods that propagate the stop signal down the chain. **No timeouts** - the threads are designed to check `shutdown_requested` at regular intervals and exit cooperatively.

### Step 1: Protocol Update

**File:** `src/context/protocols.py`

Add to `SemanticSearchManagerProtocol`:

```python
def shutdown(self) -> None:
    """
    Signal background tasks to stop.

    Non-blocking. Sets shutdown flag that background workers check.
    Workers will exit at their next checkpoint.
    """
    ...
```

### Step 2: SemanticSearchManager.shutdown()

**File:** `src/context/semantic_manager.py`

```python
def shutdown(self) -> None:
    """Signal background initialization to stop."""
    if self._initializer is not None:
        # ManagedThread.stop() sets shutdown_requested event
        # Worker checks this and exits cooperatively
        self._initializer.shutdown()
```

Add to `NullSemanticSearchManager`:

```python
def shutdown(self) -> None:
    """No-op - nothing to shut down."""
    pass
```

### Step 3: CodebaseContext.shutdown()

**File:** `src/context/codebase_context.py`

```python
def shutdown(self) -> None:
    """Signal all background tasks to stop."""
    self._semantic_manager.shutdown()
```

### Step 4: Wire Up in TUI

**File:** `src/cli/textual_app.py`

Update `on_unmount()`:

```python
def on_unmount(self) -> None:
    """Called when app is about to close."""
    self._should_stop_consumer = True
    OutputModeContext.set_tui_mode(False)

    # Signal background threads to stop
    if self._codebase_context is not None:
        self._codebase_context.shutdown()
```

### Step 5: Fix SemanticSearchInitializer.shutdown()

**File:** `src/context/semantic/initializer.py`

The current implementation has a timeout parameter which is tech debt. Change to:

```python
def shutdown(self) -> None:
    """
    Signal background thread to stop.

    Non-blocking. The worker checks shutdown_requested and exits
    at its next checkpoint.
    """
    if self._managed_thread is None:
        return

    logger.debug("Requesting shutdown of semantic search initializer")
    # Just set the flag - don't wait
    self._managed_thread._shutdown_event.set()
```

**Why no join/timeout?**
- The `ManagedThread` worker checks `shutdown_requested` at multiple points
- When app exits, Python will wait for non-daemon threads anyway
- If the thread is stuck in model loading, it will exit at the next checkpoint
- No arbitrary timeout that might be too short or too long

## Thread Safety Analysis

**Shutdown sequence:**
1. User closes app (Ctrl+C, quit command, etc.)
2. Textual calls `on_unmount()`
3. `on_unmount()` calls `codebase_context.shutdown()`
4. This propagates to `semantic_manager.shutdown()`
5. Which calls `initializer.shutdown()`
6. Which sets `ManagedThread._shutdown_event`
7. Worker sees `shutdown_requested == True` at next checkpoint
8. Worker exits cleanly

**Thread-safe because:**
- `threading.Event.set()` is thread-safe
- Worker reads `shutdown_requested` at defined checkpoints
- No shared mutable state between shutdown signal and worker

## Dead Code to Remove

| File | Code | Reason |
|------|------|--------|
| `factory.py:233-235` | Orphan initializer creation | Creates unused initializer |
| `codebase_context.py:138` | `_semantic_initializer` field | Backward compat shim |
| `initializer.py` | `timeout` parameter in `shutdown()` | Tech debt pattern |

## What NOT to Do

1. **No timeouts** - They're arbitrary and hide bugs
2. **No daemon threads** - They get killed mid-operation
3. **No polling loops** - The event mechanism is cleaner
4. **No blocking waits** - App should exit promptly

## Changes Summary

| File | Change |
|------|--------|
| `protocols.py` | Add `shutdown()` to `SemanticSearchManagerProtocol` |
| `semantic_manager.py` | Add `shutdown()` method |
| `semantic_manager.py` | Add `shutdown()` to `NullSemanticSearchManager` |
| `codebase_context.py` | Add `shutdown()` method |
| `textual_app.py` | Call `shutdown()` in `on_unmount()` |
| `initializer.py` | Remove timeout from `shutdown()` |
