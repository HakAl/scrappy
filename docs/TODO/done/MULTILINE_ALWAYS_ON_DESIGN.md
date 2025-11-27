# Multiline Always-On: Architectural Design

## Implementation Status: FAILED - SCOPE WAS WRONG

**Assessment Date:** 2025-11-27

**Implemented:** Code changes completed, tests passing (3732 tests).

**Reality Check:** The intended feature (multiline paste) does not work. Zero of the intended UX improvements are functional.

### Blocking Issues (All Critical)

| Bug | Symptom | Root Cause | Severity |
|-----|---------|------------|----------|
| Bug 1 | Right-click paste not working | Textual `Input` widget does not receive paste events | Critical |
| Bug 2 | Multi-line paste truncated to single line | Textual `Input` is single-line widget by design | Critical |
| Bug 3 | KeyError crash on /exit | Race condition in input capture bridge | Critical |

### Architecture Note

**There is NO CLI-only interactive mode.** Per `core.py:158`: "CLI always uses Textual". All interactive input goes through TUI (Textual's `Input` widget). Click is only used for one-shot commands, not interactive mode.

### Scope Reassessment

**Original Assumption:** "This is a simplification task" - WRONG

**Reality:** This requires replacing the TUI input infrastructure:

1. **Textual's `Input` widget is single-line by design.** It cannot capture multiline paste. The widget is fundamentally designed for single-line text entry.

2. **The backslash continuation is useless for paste.** Users paste content that doesn't have `\` at line ends. The continuation feature only helps manual typing.

3. **Right-click paste may not work at all** in Textual's `Input` widget - paste events may not be forwarded correctly to the widget.

### Recommendation

** Replace Input with TextArea**
- Use Textual's `TextArea` widget (multiline native)
- New UX: Show 5-10 lines of input, scroll if longer
- Need new submit mechanism (button or Ctrl+Enter)
- Estimated scope: Medium


---

## Executive Summary

This is a **simplification task** that removes toggleable state.
No new protocols, abstractions, or patterns are needed. The change follows SOLID principles by removing unnecessary complexity.

---

## Design Principles Applied

### Single Responsibility Principle (SRP)
- `InputHandler.read_interactive_input()` currently has two behaviors controlled by a flag
- After: One behavior - always multiline. The method has one job.

### Interface Segregation Principle (ISP)
- `SessionContextProtocol` currently exposes `multiline_mode` that not all consumers need
- After: Smaller protocol surface area

### Open/Closed Principle (OCP)
- The multiline behavior is "closed" - it's how input works, not a configurable strategy
- If future extension is needed (e.g., prompt_toolkit), that would be a new implementation

---

## Component Changes

### 1. InputHandler (src/cli/input_handler.py)

**Before:**
```python
def read_interactive_input(self, multiline_mode: bool = False) -> str:
    if multiline_mode:
        # multiline logic
    else:
        # single-line logic
```

**After:**
```python
def read_interactive_input(self) -> str:
    """Read input from user. Always supports multiline via backslash continuation."""
    # Only multiline logic - the else branch is deleted
```

**Rationale:**
- Remove conditional branching (simpler, fewer code paths)
- Remove dead code (single-line mode is unused when multiline is default)
- The `read_multiline_input()` method remains unchanged (used for explicit multiline prompts)

---

### 2. SessionContext (src/cli/session_context.py)

**Protocol Change:**
```python
# REMOVE from SessionContextProtocol:
@property
def multiline_mode(self) -> bool: ...
@multiline_mode.setter
def multiline_mode(self, value: bool) -> None: ...
```

**Class Change:**
```python
# REMOVE from SessionContext.__init__():
multiline_mode: bool = True,  # parameter
self._multiline_mode = multiline_mode  # assignment

# REMOVE property methods:
@property
def multiline_mode(self) -> bool: ...
@multiline_mode.setter
def multiline_mode(self, value: bool) -> None: ...
```

**Rationale:**
- SessionContext should not track state that has no toggle
- Reduces protocol surface area
- Simpler constructor

---

### 3. CommandRouter (src/cli/command_router.py)

**Remove from registry:**
```python
"/paste": self._handle_multiline,  # DELETE
"/ml": self._handle_multiline,      # DELETE
"/multiline": self._handle_multiline, # DELETE
```

**Remove method:**
```python
def _handle_multiline(self, args: str) -> bool:  # DELETE entirely
```

**Rationale:**
- No toggle = no command to toggle it
- Commands `/paste`, `/ml`, `/multiline` become invalid (validator will reject)

---

### 4. InteractiveMode (src/cli/interactive.py)

**Change call site (line 170-172):**
```python
# Before:
user_input = self.input_handler.read_interactive_input(
    multiline_mode=self.session_context.multiline_mode
)

# After:
user_input = self.input_handler.read_interactive_input()
```

**Change banner call (line 114):**
```python
# Before:
render_welcome_banner(io, self.session_context.multiline_mode, self.session_context.auto_route_mode)

# After:
render_welcome_banner(io, self.session_context.auto_route_mode)
```

**Change fallback banner (lines 130-134):**
```python
# REMOVE these lines:
if self.session_context.multiline_mode:
    io.secho("Multiline input: ON", fg="green")
else:
    io.secho("Multiline input: OFF", fg="yellow")

# REPLACE with:
io.secho("Tip: End line with \\ to continue", fg="cyan")
```

---

### 5. Interactive Banner (src/cli/interactive_banner.py)

**Change signature:**
```python
# Before:
def render_welcome_banner(
    io: "UnifiedIOProtocol",
    multiline_mode: bool = True,
    auto_route_mode: bool = False
) -> None:

# After:
def render_welcome_banner(
    io: "UnifiedIOProtocol",
    auto_route_mode: bool = False
) -> None:
```

**Change mode status display (lines 108-116):**
```python
# REMOVE:
if multiline_mode:
    io.secho(
        "Multiline input: ON (end line with \\ to continue, /ml to toggle)",
        fg="green"
    )
else:
    io.secho("Multiline input: OFF (/ml to toggle)", fg="yellow")

# REPLACE with:
io.secho("Tip: End line with \\ to continue on next line", fg="cyan")
```

---

## Test Changes

### tests/cli/test_cli_input_handler.py

**Update tests to remove multiline_mode parameter:**

```python
def test_read_interactive_input_single_line(self):
    """Should handle single line input (no continuation)."""
    io = MockIO(inputs=["user input"])
    handler = self.InputHandler(io)
    result = handler.read_interactive_input()  # No parameter
    assert result == "user input"

def test_read_interactive_input_continuation(self):
    """Should continue on backslash."""
    io = MockIO(inputs=["first\\", "second", ""])
    handler = self.InputHandler(io)
    result = handler.read_interactive_input()  # No parameter
    assert "first" in result
    assert "second" in result
```

**Remove test:**
- `test_read_interactive_input_single_line_mode` (tests non-multiline mode)

---

### tests/cli/test_cli_interactive.py

**Remove assertion (line 91):**
```python
# DELETE:
assert mode.session_context.multiline_mode is True
```

**Update banner test (line 149):**
```python
# Change assertion to check for tip instead of mode status
assert "Tip" in output or "\\" in output
```

---

### tests/integration/test_cli_flows.py

**Delete tests:**
- `test_toggle_multiline_mode` (lines 437-449)
- `test_toggle_multiline_shows_instructions` (lines 451-463)

**Update test (lines 786-811):**
```python
def test_mode_switch_workflow(self):
    """Complete workflow: toggle modes and verify state changes."""
    # REMOVE multiline references:
    # - initial_multiline = router.session_context.multiline_mode
    # - router.route("/ml", "")
    # - assert router.session_context.multiline_mode != initial_multiline
    # - router.route("/ml", "")
    # - assert router.session_context.multiline_mode == initial_multiline
```

---

### tests/cli/test_validator_integration.py

**Delete test:**
- `test_multiline_toggle_works` (lines 127-132)

---

### tests/test_interactive_rich.py

**Update test (line 117):**
```python
# Before:
render_welcome_banner(io, multiline_mode=True, auto_route_mode=False)

# After:
render_welcome_banner(io, auto_route_mode=False)

# Update assertion:
# Change from checking "Multiline" to checking for tip
assert "Tip" in output or "\\" in output
```

---

## Validation Commands

After changes, validate with:

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific affected test modules
python -m pytest tests/cli/test_cli_input_handler.py -v
python -m pytest tests/cli/test_cli_interactive.py -v
python -m pytest tests/integration/test_cli_flows.py -v
python -m pytest tests/cli/test_validator_integration.py -v
python -m pytest tests/test_interactive_rich.py -v

# Manual verification
scrappy interactive
# Then test:
# 1. Single line input -> should submit immediately
# 2. Line ending with \ -> should prompt for continuation
# 3. Blank line after continuation -> should submit
# 4. /help -> should still work immediately
# 5. /ml -> should show "Unknown command"
```

---

## Risk Assessment

**Risk Level: LOW**

- Multiline was already default ON
- No functional change to input behavior
- Purely removal of toggle mechanism
- Easy rollback (revert commits)

**Potential Issues:**
1. Tests that explicitly test toggle will fail (expected - delete them)
2. Users habituated to `/ml` will see "Unknown command" (acceptable)
3. Any external tools depending on SessionContext.multiline_mode (unlikely)

---

## Input Length Validation (Bug Fix)

Currently there is **no upper bound** on input length. This is a bug that should be fixed as part of this work since we're modifying the input path.

### Design Decision: Reject vs Truncate

**Recommendation: Reject with clear message**

Rationale:
- Truncation silently loses user data - bad UX
- User may not realize input was truncated
- Rejection is explicit and lets user decide how to handle
- User can split input manually or use file-based input

### Constants (src/cli/config/defaults.py)

Add to defaults.py:
```python
# Input length limits
MAX_INPUT_CHARS = 50000  # ~50KB, approximately 12,500 tokens
MAX_INPUT_LINES = 1000   # Sanity limit on line count
```

**Why 50,000 characters?**
- Typical LLM context windows: 4K-128K tokens
- 4 chars per token average = 50K chars is ~12.5K tokens
- Leaves room for system prompt, context, and response
- Large enough for substantial code pastes
- Small enough to prevent accidental full-file pastes

### Protocol (src/cli/input_handler.py)

Add validation to `read_interactive_input()`:

```python
from src.cli.config.defaults import MAX_INPUT_CHARS, MAX_INPUT_LINES

class InputTooLongError(Exception):
    """Raised when user input exceeds maximum allowed length."""
    def __init__(self, char_count: int, line_count: int, max_chars: int, max_lines: int):
        self.char_count = char_count
        self.line_count = line_count
        self.max_chars = max_chars
        self.max_lines = max_lines
        super().__init__(
            f"Input too long: {char_count:,} chars ({max_chars:,} max) "
            f"or {line_count} lines ({max_lines} max)"
        )

def read_interactive_input(self) -> str:
    """Read input from user. Always supports multiline via backslash continuation.

    Raises:
        InputTooLongError: If input exceeds MAX_INPUT_CHARS or MAX_INPUT_LINES
    """
    # ... existing multiline logic ...

    result = "\n".join(lines).strip()

    # Validate length before returning
    if len(result) > MAX_INPUT_CHARS:
        raise InputTooLongError(
            char_count=len(result),
            line_count=len(lines),
            max_chars=MAX_INPUT_CHARS,
            max_lines=MAX_INPUT_LINES
        )
    if len(lines) > MAX_INPUT_LINES:
        raise InputTooLongError(
            char_count=len(result),
            line_count=len(lines),
            max_chars=MAX_INPUT_CHARS,
            max_lines=MAX_INPUT_LINES
        )

    return result
```

### Error Handling (src/cli/interactive.py)

Update `_main_loop` to handle the new exception:

```python
from src.cli.input_handler import InputTooLongError

def _main_loop(self) -> None:
    while True:
        try:
            user_input = self.input_handler.read_interactive_input()
            # ... rest of loop ...
        except InputTooLongError as e:
            self.io.secho(
                f"Input too long: {e.char_count:,} characters "
                f"(max {e.max_chars:,})",
                fg="red"
            )
            self.io.echo("Tip: Split your input into smaller chunks or use file input.")
            continue
        except KeyboardInterrupt:
            # ... existing handling ...
```

### Tests (tests/cli/test_cli_input_handler.py)

Add tests for length validation:

```python
def test_read_interactive_input_rejects_too_long(self):
    """Should reject input exceeding max length."""
    from src.cli.input_handler import InputTooLongError
    from src.cli.config.defaults import MAX_INPUT_CHARS

    # Create input just over the limit
    long_input = "x" * (MAX_INPUT_CHARS + 1)
    io = MockIO(inputs=[long_input])
    handler = self.InputHandler(io)

    with pytest.raises(InputTooLongError) as exc_info:
        handler.read_interactive_input()

    assert exc_info.value.char_count == MAX_INPUT_CHARS + 1
    assert exc_info.value.max_chars == MAX_INPUT_CHARS

def test_read_interactive_input_rejects_too_many_lines(self):
    """Should reject input exceeding max lines."""
    from src.cli.input_handler import InputTooLongError
    from src.cli.config.defaults import MAX_INPUT_LINES

    # Create input with too many continuation lines
    lines = ["line\\"] * (MAX_INPUT_LINES + 1) + [""]
    io = MockIO(inputs=lines)
    handler = self.InputHandler(io)

    with pytest.raises(InputTooLongError) as exc_info:
        handler.read_interactive_input()

    assert exc_info.value.line_count > MAX_INPUT_LINES

def test_read_interactive_input_accepts_at_limit(self):
    """Should accept input exactly at max length."""
    from src.cli.config.defaults import MAX_INPUT_CHARS

    # Create input exactly at the limit
    at_limit_input = "x" * MAX_INPUT_CHARS
    io = MockIO(inputs=[at_limit_input])
    handler = self.InputHandler(io)

    result = handler.read_interactive_input()
    assert len(result) == MAX_INPUT_CHARS
```

---

## Root Cause Analysis

### Bug 1: Right-click paste not working

**Symptom:** Right-click paste does nothing.

**Root Cause:** Textual's `Input` widget (line 533 of `textual_app.py`) may not properly receive or forward paste events from the terminal.

```python
# textual_app.py:533
yield Input(
    id="input",
    placeholder="Type your message or command...",
)
```

The `Input` widget:
- Is designed for single-line input only
- May not handle terminal paste events correctly
- Does not support bracketed paste mode

**Fix Required:** Replace `Input` with `TextArea` widget, which natively supports multiline and may handle paste better. Alternatively, investigate Textual's paste event handling.

---

### Bug 2: Multi-line paste truncated to single line

**Symptom:** Pasting multiline content only captures the first line.

**Root Cause:** Textual's `Input` widget is single-line by design. It cannot accept multiline content.

**Architecture context:** There is no CLI-only interactive mode. Per `core.py:158`, "CLI always uses Textual". All interactive input flows through:
1. `InputHandler.read_interactive_input()` calls `self.io.prompt()`
2. `UnifiedIO.prompt()` delegates to `OutputSinkAdapter.input_prompt()`
3. Which routes through Textual's `Input` widget

**Why backslash continuation doesn't help:**

The design assumed users would paste content with `\` at line ends. Real pasted content looks like:

```
line 1
line 2
line 3
```

NOT like:

```
line 1\
line 2\
line 3
```

The continuation logic (lines 128-133 of input_handler.py) only works for manually-typed input.

**Fix Options:**

1. **TextArea widget:** Replace `Input` with Textual's `TextArea` for multiline support
2. **Double-Enter semantics:** Change so Enter continues, blank line/double-Enter submits
3. **Accept limitation:** Document that paste is single-line only

---

### Bug 3: KeyError on /exit in TUI Mode

**Symptom:** App crashes with KeyError when typing `/exit`.

```
KeyError: 'de690f35-d2b2-4660-bd3e-ccb23e6a33ee'
```

**Root Cause:** Race condition between `InputCaptureManager` and `ThreadSafeAsyncBridge`.

**The bug flow:**

1. Some earlier operation triggered capture mode (`is_capturing = True`)
2. User types `/exit`
3. `on_input_submitted` (line 664-665) sees `is_capturing=True`, routes to `_handle_captured_input`
4. `handle_captured_input` calls `self._bridge.provide_result(self._id, result)` (input_capture.py:139)
5. BUT `self._id` references a prompt that was already cleaned up from `_pending_prompts`

**Why prompt_id is missing:**

Looking at `ThreadSafeAsyncBridge`:
- `blocking_prompt/blocking_confirm` registers prompt in `_pending_prompts` (lines 145, 184)
- Worker thread blocks on `event.wait()` (lines 151, 190)
- When result provided, worker wakes and **deletes** the entry (lines 156, 195)

The bug occurs when:
1. Worker thread wakes up and deletes `_pending_prompts[prompt_id]`
2. But `InputCaptureManager` still has `self._id` set and `_mode=True`
3. Next input triggers `provide_result` with stale `prompt_id`

**Alternatively:** The capture manager's `_mode` becomes True without a corresponding `_pending_prompts` entry (e.g., message ordering issue between threads).

**Fix Required:**

1. Add defensive check in `provide_result()`:
```python
def provide_result(self, prompt_id: str, result: Any) -> None:
    with self._lock:
        if prompt_id not in self._pending_prompts:
            logger.warning(f"provide_result called with unknown prompt_id: {prompt_id}")
            return
        self._prompt_results[prompt_id] = result
        self._pending_prompts[prompt_id].set()
```

2. Ensure `exit_capture_mode()` is always called before `provide_result` completes
3. Add thread synchronization between capture manager and bridge

---

## Implementation Order

1. **Add constants** - MAX_INPUT_CHARS, MAX_INPUT_LINES to defaults.py
2. **Add InputTooLongError** - New exception class in input_handler.py
3. **Update InputHandler** - Remove parameter, delete single-line branch, add validation
4. **Update InteractiveMode** - Handle InputTooLongError in main loop
5. **Update SessionContext** - Remove property from protocol and class
6. **Update CommandRouter** - Remove /ml command and handler
7. **Update Banner** - Change messaging
8. **Update Tests** - Remove/update tests, add length validation tests
9. **Run full test suite** - Verify no regressions

This order minimizes broken intermediate states.

---

## Implementation Log

**Date:** 2025-11-27

### Changes Made

1. **src/cli/config/defaults.py**
   - Added `MAX_INPUT_CHARS = 50000`
   - Added `MAX_INPUT_LINES = 1000`

2. **src/cli/input_handler.py**
   - Added `InputTooLongError` exception class
   - Removed `multiline_mode` parameter from `read_interactive_input()`
   - Deleted single-line input branch (else clause)
   - Added input length validation

3. **src/cli/interactive.py**
   - Removed `multiline_mode` parameter from `read_interactive_input()` call
   - Added `InputTooLongError` handling in `_main_loop()`
   - Updated fallback banner to show tip instead of multiline toggle status

4. **src/cli/session_context.py**
   - Removed `multiline_mode` from `SessionContextProtocol`
   - Removed `multiline_mode` parameter from `SessionContext.__init__()`
   - Removed `_multiline_mode` attribute and property methods

5. **src/cli/command_router.py**
   - Removed `/paste`, `/ml`, `/multiline` from command registry
   - Removed `_handle_multiline()` method

6. **src/cli/interactive_banner.py**
   - Removed `multiline_mode` parameter from `render_welcome_banner()`
   - Changed display to show tip about backslash continuation

7. **src/cli/core.py**
   - Updated docstring to remove `multiline_mode` reference

### Test Changes

1. **tests/cli/test_cli_input_handler.py**
   - Updated `read_interactive_input` tests to remove `multiline_mode` parameter
   - Added `test_read_interactive_input_rejects_too_long`
   - Added `test_read_interactive_input_rejects_too_many_lines`
   - Added `test_read_interactive_input_accepts_at_limit`

2. **tests/cli/test_cli_interactive.py**
   - Removed `multiline_mode` assertion from `test_initializes_with_default_modes`
   - Updated `test_run_shows_mode_statuses` to check for tip instead

3. **tests/integration/test_cli_flows.py**
   - Renamed `test_startup_with_multiline_on_shows_status` to `test_startup_shows_continuation_tip`
   - Removed `test_toggle_multiline_mode` and `test_toggle_multiline_shows_instructions`
   - Updated `test_mode_switch_workflow` to remove multiline references

4. **tests/cli/test_validator_integration.py**
   - Removed `test_multiline_toggle_works`

5. **tests/test_interactive_rich.py**
   - Updated `test_welcome_banner_shows_mode_statuses` to remove `multiline_mode` parameter

### Test Results

- 146 specific affected tests: ALL PASSED
- 1093 CLI/integration tests: ALL PASSED
- 3732 full test suite: ALL PASSED (556 errors unrelated - Windows temp directory permissions)
