# Semantic Search Architecture Plan

## Problem Summary

When the model finishes downloading, the initializer emits `INIT_COMPLETE` to the event queue. But nothing calls `process_pending()` to deliver the event, so `_handle_event` never runs and indexing never starts. Additionally, progress callbacks are never wired up to the TUI.

## Design Principles

1. **Indexing is core functionality** - happens regardless of callbacks
2. **Callbacks are observer pattern** - subscribe for updates, but work happens anyway
3. **Push model** - background thread pushes to subscribers, no polling
4. **Clean lifecycle** - starts on app init, stops on app exit
5. **Graceful shutdown first, daemon as safety net** - try nice, kill if stuck

---

## 0. Fix Indexing Trigger (CRITICAL)

**Root Cause:** Event queue requires polling via `process_pending()`, but nothing polls it.

**Fix:** Call `index_files()` directly from background thread when model ready. No event queue needed for this path.

### File: `src/context/semantic/initializer.py`

Add callback field and setter:
```python
def __init__(self, ...):
    ...
    self._on_ready_callback = None

def set_on_ready_callback(self, callback) -> None:
    """Set callback to invoke when model is ready.

    Args:
        callback: Function taking the search_provider as argument
    """
    self._on_ready_callback = callback
```

In `_initialize_worker()`, after model loads successfully (around line 317), call the callback:
```python
# After: self._emit_completion_event(search_provider)
# Add:
if self._on_ready_callback:
    try:
        self._on_ready_callback(search_provider)
    except Exception as e:
        logger.warning(f"Error in on_ready_callback: {e}")
```

### File: `src/context/semantic_manager.py`

Update `start_background_init()` to set the callback:
```python
def start_background_init(self) -> None:
    if not self._initializer:
        self._initializer = self._create_default_initializer()

    if self._initializer:
        logger.debug("Starting background semantic search initialization")

        # Set callback for when model is ready (called from background thread)
        if hasattr(self._initializer, 'set_on_ready_callback'):
            self._initializer.set_on_ready_callback(self._on_model_ready)

        # Keep event handler registration for backward compatibility
        self._event_queue.register_handler(
            "semantic_search",
            self._handle_event,
        )

        self._initializer.start()
    else:
        logger.debug("No semantic initializer available")
```

Add the callback handler:
```python
def _on_model_ready(self, search_provider) -> None:
    """Called from background thread when model finishes loading.

    Args:
        search_provider: The initialized SemanticSearchProtocol instance
    """
    logger.info("Semantic search model ready (via callback)")
    self._semantic_search = search_provider
    self._notify_progress("Semantic search ready")

    # Trigger indexing (runs on background thread)
    if self._file_collector_callback:
        self._notify_progress("Starting file indexing...")
        try:
            file_collector = self._file_collector_callback()
            if file_collector:
                self.index_files(file_collector)
            else:
                logger.debug("File collector callback returned None")
        except Exception as e:
            logger.warning(f"Auto-indexing failed: {e}")
            self._notify_progress(f"Indexing failed: {e}")
```

---

## 1. Wire Up Progress Callback (CRITICAL - CURRENTLY MISSING)

**Root Cause:** `set_codebase_context()` stores the context but never registers a progress callback. The docstring claims it does, but the implementation doesn't.

### File: `src/cli/textual_app.py`

Update `set_codebase_context()` to actually register the callback:
```python
def set_codebase_context(self, context: "CodebaseContext") -> None:
    """Set codebase context for semantic search indexing.

    Called by TextualInteractiveMode to wire up the context.
    Registers a thread-safe progress callback that posts messages to the UI.

    Args:
        context: The CodebaseContext instance with semantic search manager
    """
    self._codebase_context = context

    def progress_callback(message: str) -> None:
        # Guard against post-shutdown race condition
        # Called from background thread, posts to main thread via message queue
        if self.is_running and not self._should_stop_consumer:
            self.post_message(IndexingProgress(message=message))

    context.set_indexing_progress_callback(progress_callback)
```

---

## 2. Shutdown Chain

### File: `src/context/protocols.py`

Add `shutdown()` to `SemanticSearchManagerProtocol`:
```python
def shutdown(self) -> None:
    """Signal background tasks to stop and clean up resources."""
    ...
```

### File: `src/context/semantic_manager.py`

Add to `SemanticSearchManager`:
```python
def shutdown(self) -> None:
    """Signal background tasks to stop and clean up resources."""
    # Break reference cycle to allow GC
    self._progress_callback = None
    self._file_collector_callback = None

    if self._initializer is not None:
        self._initializer.shutdown()
```

Add to `NullSemanticSearchManager`:
```python
def shutdown(self) -> None:
    """No-op shutdown."""
    pass
```

### File: `src/context/semantic/initializer.py`

Add to `NullInitializer` (currently missing!):
```python
def shutdown(self, timeout: float = 5.0) -> bool:
    """No-op shutdown, always returns True (success)."""
    return True

def is_shutdown_requested(self) -> bool:
    """Always returns False - null initializer is never shutting down."""
    return False
```

### File: `src/context/codebase_context.py`

Add shutdown method:
```python
def shutdown(self) -> None:
    """Shutdown background tasks and clean up resources."""
    self._semantic_manager.shutdown()
```

### File: `src/cli/textual_app.py`

Update `on_unmount()`:
```python
def on_unmount(self) -> None:
    """Called when app is about to close."""
    # Set flag immediately to stop accepting new messages
    self._should_stop_consumer = True

    # Clear TUI mode context
    OutputModeContext.set_tui_mode(False)

    # Trigger shutdown chain for background tasks
    if self._codebase_context is not None:
        self._codebase_context.shutdown()
```

---

## 3. Graceful Exit for index_files Loop

**Issue:** When `index_files` runs in the background thread, it should check for shutdown between batches.

### File: `src/context/semantic/initializer.py`

Add a public method to `SemanticSearchInitializer` to check shutdown status (avoids exposing `_managed_thread`):
```python
def is_shutdown_requested(self) -> bool:
    """Check if shutdown has been requested.

    Returns:
        True if shutdown was requested, False otherwise
    """
    if self._managed_thread:
        return self._managed_thread.shutdown_requested
    return False
```

(Note: `NullInitializer.is_shutdown_requested()` is added in Section 2 above)

### File: `src/context/semantic_manager.py`

The `index_files` method already has `_is_cancelled()` check (line 296). We need to wire it up.

Add a method to set cancellation from the initializer:
```python
def _set_cancellation_from_initializer(self) -> None:
    """Wire up cancellation check to initializer's shutdown state."""
    if self._initializer and hasattr(self._initializer, 'is_shutdown_requested'):
        self.set_cancellation_check(self._initializer.is_shutdown_requested)
```

Call this in `_on_model_ready` before indexing:
```python
def _on_model_ready(self, search_provider) -> None:
    # ... existing code ...

    # Wire up cancellation before indexing
    self._set_cancellation_from_initializer()

    # Trigger indexing
    if self._file_collector_callback:
        # ... existing code ...
```

---

## 4. ManagedThread: daemon=True with Write Protection

**Rationale:** `daemon=False` risks "zombie process" where terminal hangs forever on exit, forcing user to `kill -9`. A manual kill carries the exact same corruption risk as daemon termination. Therefore, use `daemon=True` with explicit `join()` in shutdown.

| Scenario | daemon=False | daemon=True + join() |
| :--- | :--- | :--- |
| **Normal Exit** | Safe (Process waits for thread) | **Safe** (Main thread explicitly waits via `join`) |
| **Worker Stuck (Network)** | **Hang** (User must `kill -9`) | **Clean Exit** (Timeout kills thread) |
| **Worker Stuck (Disk I/O)** | **Hang** (User must `kill -9`) | **Clean Exit** (Timeout kills thread) |
| **Data Integrity** | Safe (unless forced kill) | **Safe** (unless timeout reached) |

### File: `src/infrastructure/threading/managed_thread.py`

Change line 101:
```python
daemon=True,  # Safety net: ensures process exits even if thread stuck in blocking I/O
```

### File: `src/context/semantic/provider.py`

Add write protection flag to `LanceDBSearchProvider.index_files()`:
```python
def index_files(self, files: Dict[str, str], is_batch: bool = False) -> None:
    # ... existing preparation code ...

    # CRITICAL SECTION - protect against mid-write termination
    self._is_writing = True
    try:
        # Write to LanceDB
        self._table.add(records)
    finally:
        self._is_writing = False
```

Add `_is_writing` field to `__init__`:
```python
def __init__(self, ...):
    # ... existing code ...
    self._is_writing = False  # Write protection flag for graceful shutdown
```

---

## 5. Tech Debt Cleanup

### File: `src/context/semantic/initializer.py`

**Remove deprecated `wait_with_callback` method entirely.**

Per CLAUDE.md: "NO deprecation warnings - Just remove or change code directly"

Delete lines 123-154 (the entire `wait_with_callback` method with its `warnings.warn()` call). This method is unused and the event queue pattern has replaced it.

```python
# DELETE THIS ENTIRE METHOD:
def wait_with_callback(self, callback, timeout: Optional[float] = None) -> None:
    """
    DEPRECATED: Wait for initialization to complete and call a callback when done.
    ...
    """
    warnings.warn(...)
    ...
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `initializer.py` | Add `_on_ready_callback` field and `set_on_ready_callback()` method |
| `initializer.py` | Call `_on_ready_callback(search_provider)` after model ready |
| `initializer.py` | Add `is_shutdown_requested()` method (public API for shutdown check) |
| `initializer.py` | Add `shutdown()` to `NullInitializer` |
| `initializer.py` | Add `is_shutdown_requested()` to `NullInitializer` |
| `initializer.py` | Delete deprecated `wait_with_callback` method |
| `semantic_manager.py` | Add `_on_model_ready()` callback handler |
| `semantic_manager.py` | In `start_background_init()`, set on_ready_callback |
| `semantic_manager.py` | Add `shutdown()` to `SemanticSearchManager` |
| `semantic_manager.py` | Add `shutdown()` to `NullSemanticSearchManager` |
| `semantic_manager.py` | Add `_set_cancellation_from_initializer()` for graceful loop exit |
| `protocols.py` | Add `shutdown()` to `SemanticSearchManagerProtocol` |
| `codebase_context.py` | Add `shutdown()` method |
| `textual_app.py` | Register guarded progress callback in `set_codebase_context()` |
| `textual_app.py` | Call `shutdown()` in `on_unmount()` |
| `managed_thread.py` | Change `daemon=False` to `daemon=True` |
| `provider.py` | Add `_is_writing` flag for write protection in `index_files()` |

---

## Flow Diagrams

### Startup Flow
```
Factory.create_orchestrator()
  -> CodebaseContext.__init__()
  -> context.start_background_initialization()
     -> SemanticSearchManager.start_background_init()
        -> initializer.set_on_ready_callback(self._on_model_ready)
        -> initializer.start()
           -> ManagedThread starts (daemon=True)
              -> _initialize_worker() runs
                 -> Downloads/loads model
                 -> Calls _on_ready_callback(search_provider)
                    -> _on_model_ready()
                       -> self._semantic_search = search_provider
                       -> self._notify_progress("Semantic search ready")
                       -> self._set_cancellation_from_initializer()
                       -> self.index_files(file_collector)
                          -> For each batch:
                             -> Check _is_cancelled()
                             -> _notify_progress("Indexing batch N...")
                             -> provider.index_files(batch)
                       -> _notify_progress("Indexing complete")
```

### Progress Update Flow
```
Background thread: _notify_progress("message")
  -> self._progress_callback("message")  [if registered]
     -> TUI.progress_callback("message")
        -> Check: self.is_running and not self._should_stop_consumer
        -> self.post_message(IndexingProgress(message="message"))
           -> Textual message queue (thread-safe)

Main thread: on_indexing_progress(message)
  -> self.progress_indicator.update(message=message.message)
  -> status_bar.refresh_display()
```

### Shutdown Flow
```
User closes TUI
  -> TUI.on_unmount()
     -> self._should_stop_consumer = True  # Guards callback immediately
     -> OutputModeContext.set_tui_mode(False)
     -> self._codebase_context.shutdown()
        -> self._semantic_manager.shutdown()
           -> self._progress_callback = None  # Break reference cycle
           -> self._file_collector_callback = None
           -> self._initializer.shutdown(timeout=5.0)
              -> self._managed_thread.stop(timeout=5.0)
                 -> self._shutdown_event.set()  # Signal thread to stop
                 -> self._thread.join(timeout=5.0)
                    -> Thread checks shutdown_requested between batches
                    -> Thread exits gracefully
              -> Returns True if stopped, False if stuck
  -> If thread stuck after timeout, daemon=True ensures process exits
```

---

## Safety Guarantees

1. **threading.Event** - Already used by ManagedThread for stop signal
2. **Guarded callback** - Check `is_running` and `_should_stop_consumer` before `post_message()`
3. **Clear callbacks on shutdown** - Break reference cycles to allow GC
4. **Timeout join** - Don't block forever waiting for thread (5s default)
5. **Cancellation check in loop** - `index_files` checks between batches
6. **daemon=True** - Last resort safety net if thread truly stuck

---

## Testing Checklist

- [ ] Start app, verify model downloads and indexing starts
- [ ] Verify progress messages appear in TUI status bar
- [ ] Close app during model download, verify clean exit
- [ ] Close app during indexing, verify clean exit
- [ ] Verify no "thread still running" warnings on normal exit
- [ ] Verify LanceDB index not corrupted after interrupted indexing
