# TextArea Input Redesign

## Overview

Replace Textual's single-line `Input` widget with `TextArea` to enable multiline paste and fix the /exit crash.

**Priority Order:**
1. Bug 3: Fix KeyError crash on /exit (immediate)
2. Replace Input with TextArea (enables multiline)
3. Enable right-click paste support

---

## Scope Analysis Summary

### Files Requiring Modification

| File | Changes Required | Risk |
|------|-----------------|------|
| `src/cli/textual_app.py` | Widget replacement, event handlers, API migration | HIGH |
| `src/cli/scrappy.tcss` | CSS selector updates, height adjustments | MEDIUM |
| `src/cli/input_capture.py` | Defensive null checks only | LOW |

### Files NOT Requiring Changes (Verified)

- `src/cli/interactive.py` - Uses UnifiedIO abstraction, widget-agnostic
- `src/cli/input_handler.py` - Separate from TUI input path
- `src/cli/unified_io.py` - IO abstraction layer, no widget references
- `src/cli/protocols.py` - Protocol definitions only
- `tests/cli/test_input_capture.py` - Tests capture manager, not widget

---

## Problem 1: KeyError Crash on /exit (Bug 3)

### Symptom

App crashes with KeyError when typing `/exit`:

```
KeyError: 'de690f35-d2b2-4660-bd3e-ccb23e6a33ee'
```

### Stack Trace

```
textual_app.py:665 in on_input_submitted
  -> self._handle_captured_input(user_input)

textual_app.py:682 in _handle_captured_input
  -> self.capture_manager.handle_captured_input(user_input)

input_capture.py:139 in handle_captured_input
  -> self._bridge.provide_result(self._id, result)

textual_app.py:208 in provide_result
  -> self._pending_prompts[prompt_id].set()  # KeyError here
```

### Root Cause

Race condition between `InputCaptureManager` and `ThreadSafeAsyncBridge`:

1. Worker thread registers prompt in `_pending_prompts` (textual_app.py:145)
2. Worker blocks on `event.wait()` (textual_app.py:151)
3. Main thread enters capture mode, stores `prompt_id` in `InputCaptureManager._id`
4. User submits input
5. Worker wakes, **deletes** `_pending_prompts[prompt_id]` (textual_app.py:156)
6. But `InputCaptureManager` still has `_mode=True` and stale `_id`
7. Next input sees `is_capturing=True`, calls `provide_result` with stale ID
8. KeyError because prompt was already cleaned up

**Alternative trigger:** Message ordering issue where `enter_capture_mode` is called but corresponding `_pending_prompts` entry doesn't exist yet.

### Solution

Add defensive check in `provide_result()`:

```python
# textual_app.py - ThreadSafeAsyncBridge.provide_result()
def provide_result(self, prompt_id: str, result: Any) -> None:
    """Called from main thread after input captured."""
    with self._lock:
        if prompt_id not in self._pending_prompts:
            # Stale prompt - already cleaned up or never registered
            logger.warning(f"provide_result: unknown prompt_id {prompt_id}, ignoring")
            return
        self._prompt_results[prompt_id] = result
        self._pending_prompts[prompt_id].set()
```

Additionally, add null checks in `InputCaptureManager`:

```python
# input_capture.py - handle_captured_input()
def handle_captured_input(self, user_input: str) -> None:
    """Process input and provide result to bridge."""
    if self._id is None:
        logger.warning("handle_captured_input called with no active capture")
        return
    # ... rest of method

# input_capture.py - cancel()
def cancel(self) -> None:
    """Cancel current capture (escape/ctrl+c)."""
    if self._id is None:
        logger.warning("cancel called with no active capture")
        return
    # ... rest of method
```

### Files to Modify

- `src/cli/textual_app.py`: Add defensive check in `provide_result()` (line 206-208)
- `src/cli/input_capture.py`: Add null check in `handle_captured_input()` (line 128) and `cancel()` (line 141)

---

## Problem 2: Single-Line Input Cannot Capture Multiline Paste (Bug 2)

### Symptom

Pasting multiline content only captures the first line. Remaining lines are lost.

### Root Cause

Textual's `Input` widget is single-line by design:

```python
# textual_app.py:533
yield Input(
    id="input",
    placeholder="Type your message or command...",
)
```

The widget cannot accept content containing newlines.

### Solution

Replace `Input` with `TextArea` widget.

---

## Detailed Change Specification

### 1. Import Statement (textual_app.py:15)

**Before:**
```python
from textual.widgets import Input, RichLog, Label, ProgressBar
```

**After:**
```python
from textual.widgets import TextArea, RichLog, Label, ProgressBar
```

### 2. Widget Instantiation (textual_app.py:533-536)

**Before:**
```python
yield Input(
    id="input",
    placeholder="Type your message or command...",
)
```

**After:**
```python
yield TextArea(
    id="input",
    language=None,  # Plain text, no syntax highlighting
    show_line_numbers=False,
    soft_wrap=True,
)
```

**Note:** TextArea DOES support `placeholder` parameter per official docs.

### 3. Widget Caching (textual_app.py:547)

**Before:**
```python
self._input = self.query_one(Input)
```

**After:**
```python
self._input = self.query_one(TextArea)
```

### 4. Click Handler Type Check (textual_app.py:581)

**Before:**
```python
if clicked_widget is not None and not isinstance(clicked_widget, Input):
```

**After:**
```python
if clicked_widget is not None and not isinstance(clicked_widget, TextArea):
```

### 5. Cursor Position Update (textual_app.py:584-586)

**Before:**
```python
def clear_selection():
    self._input.cursor_position = len(self._input.value)
self.call_after_refresh(clear_selection)
```

**After:**
```python
def clear_selection():
    # TextArea uses (row, col) tuple for cursor_location
    # Move to end of document
    end_location = self._input.document.end
    self._input.cursor_location = end_location
self.call_after_refresh(clear_selection)
```

### 6. has_focus Check (textual_app.py:612)

**No change required** - TextArea inherits `has_focus` from Widget base class.

### 7. Event Handler Migration (textual_app.py:650-673)

**Before:**
```python
def on_input_submitted(self, event: Input.Submitted) -> None:
    """Handle user input submission."""
    user_input = event.value.strip()

    # Clear input immediately
    self._input.value = ""

    # Handle capture mode
    if self.capture_manager.is_capturing:
        self._handle_captured_input(user_input)
        return

    # Normal command processing
    if not user_input:
        return

    # Process in worker thread
    self.process_command(user_input)
```

**After:**
```python
# Add binding to class
BINDINGS = [
    ("ctrl+enter", "submit_input", "Submit"),
]

def action_submit_input(self) -> None:
    """Handle Ctrl+Enter to submit input."""
    user_input = self._input.text.strip()

    # Clear input immediately
    self._input.clear()

    # Handle capture mode
    if self.capture_manager.is_capturing:
        self._handle_captured_input(user_input)
        return

    # Normal command processing
    if not user_input:
        return

    # Process in worker thread
    self.process_command(user_input)
```

**DELETE:** The `on_input_submitted` method entirely.

### 8. Placeholder Updates (textual_app.py:788-793, 799)

**Note:** TextArea DOES support `.placeholder` property per official docs.

**Before (line 790):**
```python
self._input.placeholder = "Type y or n..."
```

**After:** No change needed - TextArea supports placeholder.

**Before (line 793):**
```python
self._input.placeholder = f"Enter value{hint}..."
```

**After:** No change needed - TextArea supports placeholder.

**Before (line 799):**
```python
self._input.placeholder = "Type your message or command..."
```

**After:** No change needed - TextArea supports placeholder.

### 9. CSS Changes (scrappy.tcss:50-64)

**Before:**
```css
/* User input field */
Input {
    width: 1fr;
    height: 1;
    border: none;
    background: transparent;
}

/* Defensive !important for known Textual specificity issues */
Input > .input--placeholder {
    color: $text-muted !important;
}

Input > .input--cursor {
    color: $text !important;
}
```

**After:**
```css
/* User input field - TextArea for multiline support */
TextArea {
    width: 1fr;
    height: auto;
    min-height: 1;
    max-height: 5;
    border: none;
    background: transparent;
}

/* TextArea placeholder styling */
TextArea > .text-area--placeholder {
    color: $text-muted !important;
}

/* TextArea cursor styling */
TextArea > .text-area--cursor {
    color: $text !important;
}
```

**Note:** CSS class names need verification - TextArea may use different internal class names than Input. Test and adjust.

---

## API Differences: Input vs TextArea (Verified)

| Feature | Input | TextArea | Migration Notes |
|---------|-------|----------|-----------------|
| Get content | `.value` | `.text` | Property rename |
| Set content | `.value = ""` | `.clear()` or `.text = ""` | Use `.clear()` method |
| Submit event | `Input.Submitted` | None - use key binding | Add `BINDINGS` |
| Placeholder | `placeholder=` param | `placeholder=` param | Same API |
| Focus | `.focus()` | `.focus()` | Same API |
| has_focus | `.has_focus` | `.has_focus` | Same API |
| Cursor position | `int` | `(row, col)` tuple | Use `.cursor_location` |
| Change event | `Input.Changed` | `TextArea.Changed` | Different event class |
| Single line | Yes | No (multiline) | This is the point |

---

## Problem 3: Right-Click Paste Not Working (Bug 1)

### POC
```python
from textual.app import App, ComposeResult
from textual.widgets import TextArea, Label
from textual import events
import pyperclip

class PasteTextArea(TextArea):
    def on_click(self, event: events.Click) -> None:
        if event.button == 3:
            try:
                text = pyperclip.paste()
                if text:
                    # Replace the current selection with the clipboard text.
                    # If no text is selected, this simply inserts at the cursor.
                    self.replace(
                        text, 
                        self.selection.start, 
                        self.selection.end, 
                        maintain_selection_offset=True
                    )
            except Exception:
                pass
```


### Symptom

Right-click paste does nothing in the TUI.

### Root Cause (Suspected)

Textual may be intercepting mouse events or not forwarding terminal paste events correctly. The `Input` widget's single-line nature compounds this.

### Solution

With `TextArea`, paste should work natively. The app already has `ENABLE_MOUSE = False` (line 487) which should allow native terminal paste.

If paste still doesn't work after TextArea implementation:

1. **Verify ENABLE_MOUSE setting** - already False, good
2. **Test bracketed paste mode** - TextArea should handle this natively
3. **Terminal-specific testing** - Windows Terminal, PowerShell, CMD may behave differently

### Testing

After TextArea implementation:
1. Test Ctrl+V paste (should work)
2. Test right-click paste (terminal-dependent)
3. Test Shift+Insert paste (Windows alternative)

---

## Implementation Plan

### Phase 1: Fix Bug 3 (Crash) - COMPLETE

**Changes (DONE):**

1. `src/cli/textual_app.py` line 206-210:
   - Added defensive check in `provide_result()` - checks if prompt_id exists before accessing

2. `src/cli/input_capture.py` line 137-139:
   - Added null check at start of `handle_captured_input()` - returns early if `_id` is None

3. `src/cli/input_capture.py` line 150-152:
   - Added null check at start of `cancel()` - returns early if `_id` is None

4. Added logging import to `input_capture.py` for warning messages

**Tests Added:**
- `tests/cli/test_input_capture.py`: 4 new defensive null check tests
- `tests/cli/test_async_bridge.py`: New file with 2 tests for provide_result safety

**Testing:**
- [x] All 33 input capture tests pass
- [x] All 2 async bridge tests pass
- [ ] Manual: Type `/exit` command, verify no crash
- [ ] Manual: Enter capture mode, cancel with Escape, verify no crash

### Phase 2: Replace Input with TextArea - COMPLETE

**Changes (DONE):**

**src/cli/textual_app.py:**
1. Line 14: Added `from textual.binding import Binding`
2. Line 15: Changed import `Input` to `TextArea`
3. Lines 498-501: Added priority binding `Binding("enter", "submit_input", "Submit", priority=True)`
4. Lines 539-547: Replaced `Input()` with `TextArea()` constructor (language=None, show_line_numbers=False, soft_wrap=True)
5. Line 555: Changed `query_one(Input)` to `query_one(TextArea)`
6. Line 589: Changed `isinstance(clicked_widget, Input)` to `isinstance(clicked_widget, TextArea)`
7. Lines 595-599: Updated cursor positioning to use `document.end` and `cursor_location`
8. Lines 666-685: Replaced `on_input_submitted()` with `action_submit_input()` using `.text` and `.clear()`

**src/cli/scrappy.tcss:**
1. Lines 49-67: Replaced `Input` selector with `TextArea`
2. Changed height from `1` to `auto` with `min-height: 1; max-height: 5`
3. Updated CSS class names to `.text-area--placeholder` and `.text-area--cursor`

**Testing:**
- [x] All 1014 CLI tests pass
- [x] Manual: Enter submits input
- [x] Manual: Multiline paste works
- [ ] Manual: Verify capture mode (prompts/confirms) still works

**Note:** Shift+Enter for newlines does not work on Windows Terminal (terminal limitation). Enter always submits.

### Phase 3: Verify Paste Support

**Testing:**
1. Ctrl+V paste with multiline content
2. Right-click paste (if terminal supports it)
3. Shift+Insert paste (Windows)
4. Large paste (verify MAX_INPUT_CHARS limit applies)

**If paste doesn't work:**
1. Check `ENABLE_MOUSE` setting (should be False)
2. Test with different terminals
3. Document any terminal-specific limitations

---

## Risks and Mitigations

### Risk 1: UX Change (Enter no longer submits) - RESOLVED

**Impact:** N/A - Enter still submits via priority binding

**Resolution:** Used Textual priority binding to intercept Enter before TextArea processes it. Enter submits as expected. Shift+Enter does not create newlines (Windows Terminal limitation).

### Risk 2: TextArea visual styling differs from Input

**Impact:** MEDIUM - May look different

**Mitigation:**
- CSS customization to match current look
- Test with different terminal sizes
- Adjust min-height/max-height as needed

### Risk 3: TextArea CSS class names differ

**Impact:** LOW - Styling may not apply

**Mitigation:**
- Test and verify actual class names used by TextArea
- Use Textual devtools to inspect widget structure
- Update CSS selectors as needed

### Risk 4: Performance with large paste

**Impact:** LOW - Already have limits

**Mitigation:**
- Existing `MAX_INPUT_CHARS = 50000` limit applies
- Existing `MAX_INPUT_LINES = 1000` limit applies
- Validate before processing in `action_submit_input()`

---

## Success Criteria

1. `/exit` command works without crash
2. Multiline content can be pasted and submitted
3. Ctrl+Enter submits input reliably
4. Single-line input still works (just use Ctrl+Enter)
5. Capture mode (prompts/confirms) works correctly
6. All existing tests pass
7. CSS styling looks acceptable
8. Placeholder text displays correctly

---

## Rollback Plan

If issues arise after deployment:

1. Revert `textual_app.py` to use `Input` widget
2. Revert `scrappy.tcss` CSS changes
3. Keep defensive null checks in `input_capture.py` (these are safe)

The changes are isolated to two files, making rollback straightforward.
