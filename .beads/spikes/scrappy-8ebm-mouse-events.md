# Spike: SelectableLog Mouse Events Stop Working (scrappy-8ebm)

## Problem Statement

After `/agent` completes with undo enabled (pressing 'y'), text selection AND scrolling stop working in the chat log. Both behaviors rely on the SelectableLog widget receiving mouse events.

## Environment

- Windows terminal
- Textual TUI mode
- Triggered by: `/agent <task>` -> press 'y' for undo -> task completes

## Observed Behavior

1. User runs `/agent create a .gitignore with .idea in it`
2. Prompt: "Create undo point?" -> User presses 'y'
3. Undo point created successfully
4. Agent executes task (write_file tool, etc.)
5. Task completes with message: "To undo changes: scrappy undo"
6. **BUG**: Log is no longer scrollable, text cannot be selected

## Key Observation

Both scrolling AND selection break simultaneously. This suggests:
- The SelectableLog widget is NOT receiving mouse events at all
- OR the widget's virtual_size/geometry is corrupted
- OR another widget is capturing all mouse events

## Code Path Traced

### /agent Command Flow
```
1. User input -> main_screen.on_submit()
2. process_command() [worker thread, @work(exclusive=True)]
3. interactive_mode._process_input()
4. command_router.route() -> _handle_agent()
5. agent_mgr.run_agent(task)
   - TUIUserInteraction.confirm() -> bridge.blocking_confirm()
   - Posts RequestInlineInput -> capture mode
   - User types 'y' -> capture mode exits
   - create_undo_point()
   - _run_langgraph_agent()
     - langgraph_bridge.run_agent()
     - Tool confirmations via blocking_confirm_yna()
     - Agent completes
   - io.echo("To undo changes: scrappy undo")
6. process_command finally: post ActivityStateChange(IDLE)
```

### SelectableLog Mouse Handling
```python
# selectable_log.py:246-266
def on_mouse_down(self, event: MouseDown) -> None:
    self._selection_start = self._mouse_to_scroll_coords(event)
    self._selection_end = None
    self._is_selecting = True
    self.capture_mouse()  # Captures mouse to this widget
    self.refresh()

def on_mouse_up(self, event: MouseUp) -> None:
    self._is_selecting = False
    self.release_mouse()  # Releases mouse capture
```

### Capture Mode Flow (y/n prompts)
```python
# input_capture.py - manages capture mode state
# bridge.py - blocking_confirm() posts RequestInlineInput
# main_screen.py - enter_capture_mode() / _exit_capture_ui()
```

## Files Examined

| File | Relevant Code |
|------|---------------|
| `selectable_log.py` | Mouse event handlers (lines 246-266) |
| `main_screen.py` | on_click (152-179), update_activity (471-494) |
| `langgraph_bridge.py` | run_agent cleanup (797-830) |
| `agent_manager.py` | run_agent flow, final io.echo (line 171) |
| `bridge.py` | blocking_confirm (73-101) |
| `input_capture.py` | Capture mode state management |
| `unified_io.py` | OutputSinkAdapter routing |
| `output_adapter.py` | Queue-based message passing |

## Hypotheses

### H1: Mouse Capture Not Released
- SelectableLog uses `capture_mouse()` / `release_mouse()` for drag selection
- If capture is held by another widget, events won't reach SelectableLog
- **Counter-evidence**: No other widget in the flow calls `capture_mouse()`

### H2: Focus State Corrupted
- After capture mode exits, focus might not return properly
- **Counter-evidence**: `on_click` handler explicitly allows SelectableLog clicks

### H3: Virtual Size Reset to Zero
- If `virtual_size` becomes (0, 0), scrolling would be disabled
- **Counter-evidence**: Test shows virtual_size persists after IDLE

### H4: Worker Thread Timing Issue
- Race condition between worker thread cleanup and main thread UI
- `io.echo()` queues message, then IDLE is posted immediately after
- Message processing order might affect widget state

### H5: Textual Framework Bug
- Mouse event routing issue after `@work(exclusive=True)` completes
- Something in Textual's internal state gets corrupted

### H6: Terminal-Specific Issue
- Windows Terminal mouse event handling quirk
- Mouse mode not properly restored after some operation

## Test Results

### Tests That PASS (bug NOT reproduced)
```
test_click_on_log_sets_selection_start - PASSED
test_mouse_after_rapid_writes_and_idle - PASSED
test_mouse_after_capture_mode_exit - PASSED
test_virtual_size_set_after_writes - PASSED
test_virtual_size_not_zero_after_idle - PASSED
```

### Tests That Were Skipped
```
test_click_on_log_in_real_app - SKIPPED (SelectableLog not found)
test_click_after_simulated_agent_in_real_app - SKIPPED (not on MainAppScreen)
```

## What's Missing from Tests

The tests don't reproduce the bug because they lack:

1. **Real worker thread execution** - Tests use `pilot.pause()` not actual threading
2. **Actual command router flow** - Tests mock `_process_input`
3. **Real IO/output adapter chain** - Tests write directly to widget
4. **Multiple capture mode cycles** - Undo prompt + tool confirmations
5. **Full ScrappyApp initialization** - Tests can't get past wizard screen

## Reproduction Steps (Manual)

```bash
# 1. Start scrappy in a git repo
cd ~/MINE/dev/test_repo
scrappy

# 2. Run agent with undo
/agent create a .gitignore with .idea in it

# 3. Press 'y' for undo prompt

# 4. Wait for task to complete

# 5. Try to:
#    - Click and drag to select text -> FAILS
#    - Scroll the log with mouse wheel -> FAILS
```

## Debugging Suggestions

### Option A: Add Logging
```python
# In selectable_log.py
def on_mouse_down(self, event: MouseDown) -> None:
    import logging
    logging.getLogger(__name__).info(f"MOUSE_DOWN: {event}")
    # ... rest of method
```

### Option B: Visual Debug Indicator
```python
# In selectable_log.py
def on_mouse_down(self, event: MouseDown) -> None:
    self.styles.border = ("solid", "red")  # Visual feedback
    # ... rest of method
```

### Option C: Check Mouse Capture State
```python
# Add method to SelectableLog
def debug_state(self) -> dict:
    return {
        "is_selecting": self._is_selecting,
        "selection_start": self._selection_start,
        "virtual_size": self.virtual_size,
        "has_focus": self.has_focus,
        "mouse_captured": self._mouse_captured,  # If accessible
    }
```

### Option D: Terminal Mouse Mode Check
Check if terminal mouse mode is being disabled:
```python
# In the app, after bug triggers
print(app.console._mouse)  # Check Rich console mouse state
```

## Next Steps

1. **Add instrumentation** to SelectableLog to log all mouse events
2. **Run real app** and trigger the bug
3. **Check logs** to see if events are received at all
4. **Compare** mouse event flow before/after bug triggers
5. **Identify** the exact point where events stop arriving

## Related Code Patterns

The bug might be related to how Textual handles:
- `ScrollView` mouse event routing
- `capture_mouse()` / `release_mouse()` lifecycle
- Worker thread message posting
- Focus management after modal interactions

## References

- Textual ScrollView: https://textual.textualize.io/api/scroll_view/
- Textual Mouse Events: https://textual.textualize.io/events/mouse/
- Issue: scrappy-8ebm
