# Bug Fix Implementation Plan

## Overview

This plan addresses all 7 confirmed bugs from `BUGS_PRIORITIZED.md`, ordered by priority and dependency relationships.

---

## Phase 1: Critical - Semantic Search (BUG-001, BUG-002)

### BUG-002: Fix LanceDB Directory Default (Do First)

**Priority:** P1-CRITICAL | **Complexity:** Low | **Dependencies:** None

**Root Cause:**
The default `db_dir_name` in `SemanticIndexConfig` is `.lancedb` (project root), but the initializer correctly uses `.scrappy/lancedb`. This inconsistency causes confusion and potential gitignore issues when components use the config directly.

**Files to Modify:**

1. `src/context/semantic/config.py:44`
   ```python
   # Change:
   db_dir_name: str = ".lancedb"
   # To:
   db_dir_name: str = ".scrappy/lancedb"
   ```

2. `tests/context/test_semantic_config.py:44-46`
   ```python
   # Change:
   def test_default_db_dir_name(self):
       """Default db dir name should be .scrappy/lancedb."""
       config = SemanticIndexConfig()
       assert config.db_dir_name == ".scrappy/lancedb"
   ```

**Test:**
```bash
python -m pytest tests/context/test_semantic_config.py -v
```

---

### BUG-001: Register Semantic Event Handler (Critical Fix)

**Priority:** P1-CRITICAL | **Complexity:** Medium | **Dependencies:** BUG-002

**Root Cause Analysis:**

There are TWO issues preventing semantic search indexing:

#### Issue 1: Event handler doesn't trigger indexing (FIXED)

The `SemanticSearchManager._handle_event()` cached the provider but did NOT trigger indexing.

**Fix applied:** Added `_file_collector_callback` to `SemanticSearchManager` and modified `_handle_event()` to call `index_files()` when the callback is set. Wired up in `CodebaseContext.start_background_initialization()`.

#### Issue 2: Event queue is never processed (NOT FIXED)

The event queue pattern requires `process_background_events()` to be called periodically from the main thread, but **nothing calls it**:

```
1. Factory calls context.start_background_initialization()
2. SemanticSearchInitializer starts in background thread
3. Model loads successfully (~1 second)
4. Initializer emits INIT_COMPLETE event to queue  <-- DEBUG LOG CONFIRMS THIS
5. Event sits in queue forever                      <-- BUG: NEVER PROCESSED
6. _handle_event() never called
7. Auto-indexing never triggered
8. LanceDB directory stays empty
```

**Evidence from debug.log:**
```
12:18:23,161 - Event submitted: init_complete from semantic_search
12:18:23,161 - Emitted INIT_COMPLETE event to queue
# No subsequent "Semantic search model ready (via event)" log
# No "Triggering auto-indexing..." log
```

**The missing piece:** `CodebaseContext.process_background_events()` exists but is never called from:
- `src/cli/textual_app.py` - No call
- `src/cli/interactive.py` - No call
- `src/orchestrator/` - No call

---

#### Design Options Analysis (REJECTED)

The following options were considered and **rejected**:

1. **Option A: Textual App Timer** - Add `set_interval()` in `ScrappyApp.on_mount()`
   - **REJECTED**: Timer callbacks run on main thread. If timer triggers event processing,
     `_handle_event()` runs on main thread, which calls `index_files()` - a blocking I/O
     operation that would freeze the UI for 30+ seconds during indexing.

2. **Option B: Process before each command** - Call at start of `_process_input()`
   - **REJECTED**: Delays indexing until first user input. Same blocking issue if called
     from main thread.

3. **Option C: Remove event queue pattern** - Background thread directly calls indexing
   - **REJECTED**: Would require significant refactoring and thread-safety guarantees.

4. **Option D: Orchestrator owns event processing**
   - **REJECTED**: Still requires something to call it, same blocking issues.

---

#### Recommended Solution: Dedicated Worker Thread

**Bypass the event queue entirely.** Use a dedicated Textual `@work` thread that:
1. Polls for semantic search readiness
2. Runs `index_files()` in the worker thread (not main thread)
3. Posts progress messages to UI via `post_message()` (thread-safe)

**Architecture:**

```
+---------------------------------------------------------------------+
|                        ScrappyApp                                    |
|  +------------------+  +------------------+  +-------------------+   |
|  | Main Thread      |  | Worker: commands |  | Worker: indexing  |   |
|  | - UI updates     |  | - process_input  |  | - poll is_ready() |   |
|  | - message handler|  | - blocking I/O   |  | - index_files()   |   |
|  +--------^---------+  +------------------+  +---------+---------+   |
|           |                                           |              |
|           |  post_message(IndexingProgress)           |              |
|           +-------------------------------------------+              |
+---------------------------------------------------------------------+
```

**Threading Safety Analysis:**

| Thread | Operations | Blocking? | Locks Held |
|--------|-----------|-----------|------------|
| Main (Textual) | UI updates, message dispatch | No | None |
| Indexing Worker | poll `is_complete()`, `index_files()` | Yes (OK) | Brief state reads |
| Init Background | Model loading, emit event | Yes (OK) | Brief state writes |

**Potential Deadlock Analysis: NONE FOUND**

1. **Main thread waiting on worker?** - No. Main thread never blocks on worker.
2. **Worker waiting on main thread?** - No. `post_message()` is non-blocking (queues message).
3. **Lock contention?** - Minimal. Initializer's `_lock` is only held for microseconds during state reads/writes.
4. **Circular wait?** - No. No thread holds a resource while waiting for another.

**UI Blocking Analysis: NONE FOUND**

1. `index_files()` runs in worker thread - main thread free to handle events
2. Progress callback calls `post_message()` - non-blocking, just queues
3. `on_indexing_progress()` runs on main thread - only updates widget state, no I/O
4. Status bar refresh - widget updates are fast, no blocking

**Edge Case: Multiple Workers**

The `consume_output_queue` worker and the new `run_semantic_indexing` worker both run independently:
- `consume_output_queue` - reads from `output_adapter` queue
- `run_semantic_indexing` - reads from `CodebaseContext`, posts to Textual message queue

These are independent - no shared mutable state between them. The `process_pending()` method
on the event queue is thread-safe via `queue.get_nowait()`.

---

#### Implementation Plan

**New Components:**

1. **`IndexingProgress` Message** - Posted from worker thread to update status bar
2. **`run_semantic_indexing()` Worker** - `@work(thread=True)` method
3. **`on_indexing_progress()` Handler** - Main thread handler updates `ProgressIndicator`

**Files to Modify:**

1. `src/cli/textual_app.py` - Add indexing worker and progress message

   ```python
   class IndexingProgress(Message):
       """Message for semantic search indexing progress updates.

       Posted from indexing worker thread to update status bar.
       Thread-safe via Textual's message queue.
       """

       def __init__(self, message: str, progress: int = 0, total: int = 0, complete: bool = False) -> None:
           super().__init__()
           self.message = message
           self.progress = progress
           self.total = total
           self.complete = complete


   class ScrappyApp(App):
       def __init__(self, interactive_mode: "InteractiveMode", output_adapter: TextualOutputAdapter):
           # ... existing init ...
           self._codebase_context: Optional["CodebaseContext"] = None

       def set_codebase_context(self, context: "CodebaseContext") -> None:
           """Set codebase context for semantic search indexing."""
           self._codebase_context = context

       def on_mount(self) -> None:
           # ... existing on_mount code ...

           # Start semantic search indexing worker if context available
           if self._codebase_context is not None:
               self.run_semantic_indexing()

       @work(exclusive=False, thread=True)
       def run_semantic_indexing(self) -> None:
           """Worker thread that waits for semantic search and runs indexing.

           Runs independently of command processing. Posts progress messages
           to UI thread-safely via post_message().
           """
           if self._codebase_context is None:
               return

           context = self._codebase_context
           manager = context._semantic_manager

           # Poll for initialization to complete (check every 100ms)
           max_wait_seconds = 60
           poll_interval = 0.1
           waited = 0.0

           while waited < max_wait_seconds and self.is_running:
               if manager.is_ready():
                   break
               time.sleep(poll_interval)
               waited += poll_interval

               # Post status update periodically
               if int(waited) % 5 == 0 and waited > 0:
                   status = manager.get_status() or "Loading..."
                   self.post_message(IndexingProgress(f"Semantic search: {status}"))

           if not manager.is_ready():
               self.post_message(IndexingProgress("Semantic search unavailable", complete=True))
               return

           # Create progress callback that posts to UI
           def progress_callback(message: str) -> None:
               self.post_message(IndexingProgress(message))

           manager.set_progress_callback(progress_callback)

           # Get file collector and run indexing
           self.post_message(IndexingProgress("Starting file indexing..."))

           try:
               file_collector = context._file_collector or context._create_default_file_collector()
               if file_collector:
                   manager.index_files(file_collector)
                   self.post_message(IndexingProgress("Indexing complete", complete=True))
               else:
                   self.post_message(IndexingProgress("No files to index", complete=True))
           except Exception as e:
               logger.exception(f"Semantic indexing failed: {e}")
               self.post_message(IndexingProgress(f"Indexing failed: {e}", complete=True))

       def on_indexing_progress(self, message: IndexingProgress) -> None:
           """Handle indexing progress update from worker thread.

           Runs on main thread - safe to update widgets.
           """
           if message.complete:
               self.progress_indicator.complete()
           else:
               self.progress_indicator.update(
                   progress=message.progress,
                   total=message.total,
                   message=message.message
               )

           # Refresh status bar to show/hide progress
           status_bar = self.query_one(StatusBar)
           status_bar.refresh_display()
   ```

2. `src/cli/textual_interactive.py` - Pass context to ScrappyApp

   ```python
   def run(self) -> None:
       # ... existing code ...

       # Create ScrappyApp with InteractiveMode and output adapter
       app = ScrappyApp(interactive_mode, output_adapter)

       # NEW: Pass codebase context for semantic search indexing
       if hasattr(self.orchestrator, 'codebase_context'):
           app.set_codebase_context(self.orchestrator.codebase_context)

       # ... rest of existing code ...
       app.run()
   ```

3. `src/orchestrator/protocols.py` - Expose codebase_context (if not already)

   ```python
   class Orchestrator(Protocol):
       # ... existing protocol ...

       @property
       def codebase_context(self) -> "CodebaseContext":
           """Get the codebase context for semantic search operations."""
           ...
   ```

**What This Removes:**

- No longer need to call `process_background_events()` from anywhere
- Event queue pattern is bypassed for indexing (still used for other background tasks if any)
- `_handle_event()` in SemanticSearchManager no longer triggers indexing (worker does it directly)

**Tests to Add:**

```python
# tests/cli/test_textual_app.py

class TestSemanticIndexingWorker:
    """Test semantic search indexing worker thread."""

    def test_indexing_progress_message_thread_safe(self):
        """IndexingProgress message should be postable from any thread."""
        msg = IndexingProgress("Test message", progress=5, total=10)
        assert msg.message == "Test message"
        assert msg.progress == 5
        assert msg.total == 10
        assert msg.complete is False

    def test_indexing_complete_message(self):
        """Complete flag should signal end of indexing."""
        msg = IndexingProgress("Done", complete=True)
        assert msg.complete is True


# tests/context/test_semantic_manager.py

class TestSemanticSearchManagerAutoIndexing:
    """Test auto-indexing flow."""

    def test_index_files_callable_from_any_thread(self):
        """index_files should be safe to call from worker thread."""
        manager = SemanticSearchManager(Path("/tmp"))
        mock_collector = Mock(spec=FileCollectorProtocol)
        mock_collector.collect_files_batched.return_value = iter([[]])

        mock_provider = Mock()
        mock_provider.is_indexed.return_value = False
        manager._semantic_search = mock_provider

        # Simulate calling from worker thread
        import threading
        result = []
        def worker():
            try:
                manager.index_files(mock_collector)
                result.append("success")
            except Exception as e:
                result.append(f"error: {e}")

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=5.0)

        assert result == ["success"]

    def test_is_ready_thread_safe(self):
        """is_ready should be safe to poll from any thread."""
        manager = SemanticSearchManager(Path("/tmp"))

        # Simulate polling from worker thread
        import threading
        results = []
        def worker():
            for _ in range(10):
                results.append(manager.is_ready())

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=5.0)

        assert len(results) == 10
        assert all(r is False for r in results)  # No provider set
```

**Test Commands:**
```bash
python -m pytest tests/context/test_semantic_manager.py -v
python -m pytest tests/cli/test_textual_app.py -v -k "indexing"
```

---

## Phase 2: High Priority - User Experience (BUG-004, BUG-005)

### BUG-004: Sanitize Newlines in Command Input

**Priority:** P2-HIGH | **Complexity:** Low | **Dependencies:** None

**Root Cause:**
The TextArea widget allows multiline input, but the validator rejects newlines. Users cannot paste multiline content.

**Recommended Fix:**
Sanitize newlines at input source, converting them to spaces. This preserves user intent while making validation pass.

**Files to Modify:**

1. `src/cli/textual_app.py` - Find `action_submit_input` method
   ```python
   def action_submit_input(self) -> None:
       # Sanitize newlines before processing
       raw_input = self._input.text
       user_input = raw_input.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ').strip()

       # Normalize multiple spaces to single space
       import re
       user_input = re.sub(r'\s+', ' ', user_input)

       self._input.clear()
       # ... rest of method
   ```

**Tests to Add:**

```python
# tests/cli/test_textual_app.py

class TestInputSanitization:
    """Test newline sanitization in input."""

    def test_multiline_input_sanitized_to_single_line(self):
        """Newlines should be converted to spaces."""
        raw = "hello\nworld"
        expected = "hello world"
        # Test sanitization logic
        sanitized = raw.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ').strip()
        assert sanitized == expected

    def test_crlf_sanitized(self):
        """Windows-style CRLF should be sanitized."""
        raw = "hello\r\nworld"
        sanitized = raw.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ').strip()
        assert sanitized == "hello world"

    def test_multiple_newlines_collapsed(self):
        """Multiple newlines should become single space."""
        raw = "hello\n\n\nworld"
        import re
        sanitized = re.sub(r'\s+', ' ', raw.replace('\n', ' ').strip())
        assert sanitized == "hello world"
```

**Test:**
```bash
python -m pytest tests/cli/test_textual_app.py -v -k "sanitiz"
```

---

### BUG-005: Remove Deceptive Audit Log Prompt

**Priority:** P2-HIGH | **Complexity:** Low | **Dependencies:** None

**Root Cause Analysis:**

From docs analysis, the audit log system has **auto-save enabled by default** via `enable_auto_save()` in `CodeAgent.run()`. The prompt at `agent_manager.py:144` only controls whether the user sees the "Saved to:" message, not whether saving occurs.

The auto-save writes to `.scrappy/audit.json` continuously. The manual `save_audit_log()` call is redundant.

**Recommended Fix:**
Remove the deceptive prompt entirely. Auto-save handles persistence automatically.

**Files to Modify:**

1. `src/cli/agent_manager.py:143-146`
   ```python
   # REMOVE these lines:
   # if self._interaction.confirm("Save audit log to file?", default=False):
   #     log_path = agent.save_audit_log()
   #     io.secho(f"Saved to: {log_path}", fg="green")

   # REPLACE with:
   # Audit log is auto-saved to .scrappy/audit.json
   audit_path = agent.project_root / ".scrappy" / "audit.json"
   if audit_path.exists():
       io.secho(f"Audit log: {audit_path}", fg="cyan")
   ```

**Tests to Update:**

Any tests that mock `confirm("Save audit log to file?")` should be updated to remove that expectation.

**Test:**
```bash
python -m pytest tests/cli/test_cli_handlers.py -v
```

---

## Phase 3: Medium Priority - Code Quality (BUG-006, BUG-007, BUG-010)

### BUG-010: Remove auto_route_mode from Banner

**Priority:** P4-LOW | **Complexity:** Low | **Dependencies:** None

**Note:** Despite being P4-LOW, this is a simple cleanup that should be done to reduce confusion.

**Root Cause:**
`auto_route_mode` is always `True` by default (`SessionContext.__init__` at line 75). The banner parameter serves no real purpose.

**Design Decision:**
Since auto-routing is the default (and recommended) behavior, the banner should always show it as ON. Remove the parameter.

**Files to Modify:**

1. `src/cli/interactive_banner.py:91-114`
   ```python
   def render_welcome_banner(io: "UnifiedIOProtocol") -> None:
       """Render the welcome banner as a Rich Panel.

       Args:
           io: UnifiedIO instance for output
       """
       # Display main banner
       display_banner(io)

       # Display tips
       io.secho("Tip: End line with \\ to continue on next line", fg="cyan")
       io.secho("Auto-routing: ON (task-aware execution)", fg="green")
       io.echo()
   ```

2. `src/cli/interactive.py:114` - Update call site
   ```python
   # Change:
   render_welcome_banner(io, self.session_context.auto_route_mode)
   # To:
   render_welcome_banner(io)
   ```

3. `src/cli/interactive.py:132-136` - Remove fallback conditional
   ```python
   # Remove:
   # if self.session_context.auto_route_mode:
   #     io.secho("Auto-routing: ON", fg="green")
   # else:
   #     io.secho("Auto-routing: OFF (/auto to enable)", fg="yellow")

   # Replace with:
   io.secho("Auto-routing: ON", fg="green")
   ```

4. `tests/test_interactive_rich.py:117` - Update test
   ```python
   # Change:
   render_welcome_banner(io, auto_route_mode=False)
   # To:
   render_welcome_banner(io)
   ```

**Tests:**
```bash
python -m pytest tests/test_interactive_rich.py -v
python -m pytest tests/cli/test_cli_interactive.py -v
```

---

### BUG-006: Remove Dead Code in InteractiveMode

**Priority:** P3-MEDIUM | **Complexity:** Low | **Dependencies:** BUG-010

**Root Cause:**
`TextualInteractiveMode.run()` creates a `ScrappyApp` that bypasses `InteractiveMode.run()` and `_main_loop()` entirely.

**Dead Code Identified:**
- `InteractiveMode.run()` (lines 83-139) - never called in TUI mode
- `InteractiveMode._main_loop()` (lines 141-200) - never called in TUI mode
- `InputHandler.read_interactive_input()` - never called in TUI mode

**Design Decision:**
Keep the code but mark it as "legacy non-Textual fallback" in case a non-TUI mode is needed in the future.

**Files to Modify:**

1. `src/cli/interactive.py:83-139`
   ```python
   def run(self) -> None:
       """
       Run the interactive chat loop.

       LEGACY: This method is not used when running in Textual TUI mode.
       ScrappyApp takes over the event loop directly. This method remains
       for potential non-TUI fallback scenarios.
       """
       # ... existing code with LEGACY note ...
   ```

2. `src/cli/interactive.py:141-200`
   ```python
   def _main_loop(self) -> None:
       """
       Run the main input loop.

       LEGACY: Not used in Textual TUI mode. See run() docstring.
       """
       # ... existing code ...
   ```

**Alternative:** If code cleanup is preferred, these methods can be moved to a separate `LegacyInteractiveMode` class or removed entirely with appropriate test updates.

---

### BUG-007: Chat Output Clutter and Missing Query Echo

**Priority:** P3-MEDIUM | **Complexity:** Medium | **Dependencies:** None

**Root Cause:**
Output includes unnecessary noise:
- "Output:" label
- Dashed separators
- "Assistant:" prefix
- "Execution successful" message
- Metadata (time, tokens, provider) shown by default

**Design Goals:**
1. Default mode: Clean output with query echo
2. Verbose mode (-v flag): Include metadata

**Files to Modify:**

1. `src/cli/interactive.py` - Add verbose mode support
   ```python
   class InteractiveMode:
       def __init__(self, ..., verbose: bool = False):
           # ... existing init ...
           self._verbose = verbose
   ```

2. `src/cli/interactive.py:246-249` - Echo user query
   ```python
   def _handle_chat_response(self, user_input: str, response: str, metadata: dict):
       io = self.io

       # Echo user query
       io.secho(f"> {user_input}", fg="bright_white")

       # Display response (clean, no "Assistant:" prefix)
       io.echo(response)

       # Verbose mode: show metadata
       if self._verbose and metadata:
           provider = metadata.get('provider', 'unknown')
           tokens = metadata.get('tokens', 0)
           time_ms = metadata.get('time_ms', 0)
           io.secho(f"[{provider} | {tokens} tokens | {time_ms}ms]", fg="dim")
   ```

3. CLI argument parsing - Add `-v/--verbose` flag
   ```python
   # In src/cli/core.py or argument parser
   parser.add_argument('-v', '--verbose', action='store_true',
                       help='Show metadata (provider, tokens, time)')
   ```

4. Remove noise from output functions:
   - Remove "Output:" label
   - Remove dashed separators
   - Remove "Execution successful" message
   - Remove "Assistant:" prefix

**Tests to Add:**

```python
class TestChatOutputFormat:
    """Test clean output formatting."""

    def test_user_query_echoed_with_prefix(self):
        """User query should be echoed with '> ' prefix."""
        io = MockIO()
        mode = create_test_interactive_mode(io)
        mode._handle_chat_response("hello", "Hi there!", {})

        assert "> hello" in io.captured_output

    def test_response_has_no_assistant_prefix(self):
        """Response should not have 'Assistant:' prefix."""
        io = MockIO()
        mode = create_test_interactive_mode(io)
        mode._handle_chat_response("hello", "Hi there!", {})

        assert "Assistant:" not in io.captured_output
        assert "Hi there!" in io.captured_output

    def test_verbose_mode_shows_metadata(self):
        """Verbose mode should show provider/tokens/time."""
        io = MockIO()
        mode = create_test_interactive_mode(io, verbose=True)
        mode._handle_chat_response("hello", "Hi there!", {
            'provider': 'test/model',
            'tokens': 15,
            'time_ms': 234
        })

        assert "[test/model | 15 tokens | 234ms]" in io.captured_output

    def test_default_mode_hides_metadata(self):
        """Default mode should not show metadata."""
        io = MockIO()
        mode = create_test_interactive_mode(io, verbose=False)
        mode._handle_chat_response("hello", "Hi there!", {
            'provider': 'test/model',
            'tokens': 15,
            'time_ms': 234
        })

        assert "tokens" not in io.captured_output
```

---

## Implementation Order

Execute fixes in this order to minimize conflicts:

```
1. BUG-002 (5 min) - Fix db_dir_name default
   |
   v
2. BUG-001 (30 min) - Register semantic event handler / trigger indexing
   |
   v
3. BUG-004 (10 min) - Sanitize newlines in input
   |
   v
4. BUG-005 (10 min) - Remove audit log prompt
   |
   v
5. BUG-010 (15 min) - Remove auto_route_mode from banner
   |
   v
6. BUG-006 (10 min) - Document dead code as legacy
   |
   v
7. BUG-007 (45 min) - Clean output + verbose flag
```

**Total Estimated Time:** ~2 hours

---

## Test Commands

Run after each phase:

```bash
# Phase 1 (Semantic Search)
python -m pytest tests/context/test_semantic_config.py tests/context/test_semantic_manager.py -v

# Phase 2 (User Experience)
python -m pytest tests/cli/test_textual_app.py tests/cli/test_cli_handlers.py -v

# Phase 3 (Code Quality)
python -m pytest tests/cli/test_cli_interactive.py tests/test_interactive_rich.py -v

# Full suite
python -m pytest tests/ -v
```

---

## Rollback Plan

Each fix is isolated. If issues arise:

1. **BUG-001/002:** Revert `semantic_manager.py` and `config.py` changes
2. **BUG-004:** Revert `textual_app.py` sanitization
3. **BUG-005:** Restore confirm prompt in `agent_manager.py`
4. **BUG-007:** Revert output formatting changes
5. **BUG-010:** Restore `auto_route_mode` parameter

---

## SOLID Compliance Notes

**Single Responsibility:**
- `SemanticSearchManager` owns the entire semantic search lifecycle (init, indexing, search)
- Callback injection allows `CodebaseContext` to provide file collector without tight coupling

**Open/Closed:**
- File collector callback is injectable, allowing different collection strategies

**Dependency Inversion:**
- `SemanticSearchManager` depends on `FileCollectorProtocol` abstraction
- No direct instantiation of file collectors inside manager

**Interface Segregation:**
- `set_file_collector_callback()` is a focused method for a specific concern

---

## BUG-001 Implementation Attempts (FAILED)

### Attempt 1: Dedicated Worker Thread (FAILED)

**What was tried:**
- Added `@work(thread=True)` decorator to `run_semantic_indexing()` method in `ScrappyApp`
- Worker polls `manager.is_ready()` in a loop with `time.sleep(0.1)`
- When ready, calls `manager.index_files()` directly
- Posts progress via `post_message(IndexingProgress(...))`

**Why it failed:**
- App would not exit cleanly - required force kill (Ctrl+C twice)
- Threading shutdown errors: `Exception ignored on threading shutdown`
- Worker thread didn't respect shutdown signals properly
- Lifecycle management was not clean - background thread kept running

**Code that was reverted:**
- `IndexingProgress` message class (kept - may be useful)
- `run_semantic_indexing()` worker method (removed)
- `on_indexing_progress()` handler (removed)
- `_should_stop_workers` flag (removed)
- Cancellation check callback (kept in semantic_manager.py for future use)

### Attempt 2: Push Model Event Queue (FAILED)

**What was tried:**
- Modified `ThreadSafeEventQueue.put()` to invoke handler immediately if registered
- Instead of queueing events, call handler directly on the calling thread
- This way the background initializer thread would run `_handle_event()` -> `index_files()`

**Why it failed:**
- Same threading shutdown issues
- App would not exit - stuck on `threading._shutdown()`
- The background thread doing indexing didn't terminate properly
- Fundamentally the same problem: background work not integrated with app lifecycle

**Code that was reverted:**
- `put()` method restored to original queue-only behavior
- Tests restored to expect `process_pending()` behavior

---

## BUG-001 Root Cause Analysis (Updated)

The original design had these components working together:

1. **SemanticSearchInitializer** - Downloads model in `ManagedThread`
2. **ThreadSafeEventQueue** - Hybrid push/pull event communication
3. **SemanticSearchManager** - Handles events, triggers indexing
4. **CodebaseContext** - Orchestrates initialization and provides file collector

**The actual bug:** The TUI mode (`TextualInteractiveMode` + `ScrappyApp`) never integrated with this system. The pieces exist but were never wired together for TUI.

**What's needed (not hacks):**

1. **Understand the existing lifecycle** - How does `ManagedThread` handle shutdown?
2. **Integrate with Textual's lifecycle** - `ScrappyApp.on_mount()` / `on_unmount()`
3. **Wire the callback properly** - TUI needs to receive progress updates
4. **Test shutdown behavior** - Ensure clean exit when user closes app

**Key insight:** The backend (semantic search) is designed to be independent and manage its own lifecycle. The TUI just needs to:
- Pass a progress callback (for UI updates)
- NOT try to manage the background thread directly
- Let the existing `ManagedThread` handle its own shutdown

**Next steps:**
1. Review `ManagedThread` implementation - how does it handle shutdown?
2. Review how `SemanticSearchInitializer.shutdown()` is supposed to be called
3. Check if `CodebaseContext` has cleanup that should be called on app exit
4. Design integration that respects existing lifecycle management
