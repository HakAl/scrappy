# Bug Fix Implementation Plan

## Overview

This plan addresses all 7 confirmed bugs from `BUGS_PRIORITIZED.md`, ordered by priority and dependency relationships.

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

From docs analysis, the audit log system has **auto-save enabled by default** via `enable_auto_save()` in `CodeAgent.run()`. 
The prompt at `agent_manager.py:144` only controls whether the user sees the "Saved to:" message, not whether saving occurs.

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

**Alternative:** If code cleanup is preferred, these methods can be moved to a separate `LegacyInteractiveMode` class 
or removed entirely with appropriate test updates.

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
