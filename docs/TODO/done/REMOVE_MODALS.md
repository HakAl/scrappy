# Remove Modal Dialogs from TUI

## Problem

Modal dialogs (`PromptScreen`, `ConfirmScreen`) are inappropriate for a CLI/TUI app:
- They overlay the entire screen, hiding context
- They break the natural terminal flow
- They feel jarring and out of place

## Current Architecture

### Components Involved

1. **`textual_app.py`** - Contains modal classes and threading bridge:
   - `PromptScreen(ModalScreen[str])` - Modal for text input (lines 220-262)
   - `ConfirmScreen(ModalScreen[bool])` - Modal for yes/no confirmation (lines 264-295)
   - `ThreadSafeAsyncBridge` - Coordinates worker thread blocking with main thread UI (lines 102-218)
   - `ShowPromptModal` / `ShowConfirmModal` - Messages to trigger modals (lines 62-100)
   - `on_show_prompt_modal()` / `on_show_confirm_modal()` - Handlers that push modal screens (lines 778-813)

2. **`unified_io.py`** - `OutputSinkAdapter` uses the bridge:
   - `input_prompt()` calls `self._bridge.blocking_prompt()` (line 709)
   - `input_confirm()` calls `self._bridge.blocking_confirm()` (line 733)

3. **`scrappy.tcss`** - Modal styling (lines 113-157)

### Call Sites (All Prompt/Confirm Usages)

These are all the locations where user prompts flow through the modal system:

**Confirmation Prompts (`io.confirm()`):**
| File | Line | Purpose |
|------|------|---------|
| `src/cli/core.py` | 320 | Session restore confirmation |
| `src/cli/agent_manager.py` | 71 | Dry-run mode confirmation |
| `src/cli/agent_manager.py` | 72 | Git checkpoint confirmation |
| `src/cli/agent_manager.py` | 124 | Save audit log confirmation |
| `src/cli/agent_manager.py` | 130 | Rollback to checkpoint confirmation |
| `src/cli/command_router.py` | 205 | Start working on plan confirmation |
| `src/cli/codebase.py` | 136 | Save summary to file confirmation |
| `src/cli/rate_limiter.py` | 110 | Reset provider rate limit confirmation |
| `src/cli/rate_limiter.py` | 115 | Reset all rate limits confirmation |
| `src/task_router/router.py` | 530 | Via `_input_handler.confirm()` |
| `src/agent/ui.py` | 131 | Agent UI confirmation |

**Text Prompts (`io.prompt()`):**
| File | Line | Purpose |
|------|------|---------|
| `src/cli/input_handler.py` | 38 | Multiline input continuation |
| `src/cli/input_handler.py` | 105 | Interactive input (first line) |
| `src/cli/input_handler.py` | 121 | Interactive input (continuation) |
| `src/cli/input_handler.py` | 140 | Single-line input mode |
| `src/cli/state_manager.py` | 226 | Planning session choice prompt |
| `src/task_router/intent_clarifier.py` | 82 | Intent clarification choice [1/2/3] |
| `src/cli/multiprovider.py` | 44 | Enter question prompt |
| `src/cli/multiprovider.py` | 52 | Providers selection prompt |
| `src/cli/multiprovider.py` | 122 | Provider name prompt |
| `src/cli/multiprovider.py` | 123 | Prompt text prompt |

### Threading Model (Keep This)

The `ThreadSafeAsyncBridge` pattern is correct and must be preserved:
1. Worker thread (running `process_command`) needs user input
2. Worker posts message to main thread
3. Worker blocks on `threading.Event`
4. Main thread handles input, calls `bridge.provide_result()`
5. Worker unblocks with result

## Solution: Inline Input Mode

Replace modals with inline input using the existing `Input` widget.

### New Flow

1. Worker thread calls `blocking_prompt()` or `blocking_confirm()`
2. Bridge posts `RequestInlineInput` message (replaces `ShowPromptModal`/`ShowConfirmModal`)
3. Main thread:
   - Displays prompt/question in RichLog output
   - Sets app into "input capture mode" (new reactive state)
   - Adds visual feedback (yellow prompt color)
   - Changes input placeholder to show expected input type
   - For confirms: show "[y/n]" hint
4. User types response in the same Input widget they use for commands
5. `on_input_submitted()` checks if in capture mode:
   - If yes: provide result to bridge, exit capture mode
   - If no: process as normal command
6. Worker unblocks with result

### Edge Case Handling

- **Escape key**: Cancels capture, returns default (prompt) or False (confirm)
- **Empty input on confirm**: Treated as "no" (False)
- **Empty input on prompt**: Returns the default value
- **Concurrent prompts**: Queue additional prompts until current one completes
- **Ctrl+C during capture**: Treat as escape (return default/False)
- **Up-arrow/history**: Disable command history during capture mode
- **Worker timeout**: Not applicable (worker blocks indefinitely, same as modal behavior)

## Architectural Considerations

### Protocol-First Design (per CLAUDE.md)

Before implementing, define the contract:

```python
class InputCaptureProtocol(Protocol):
    """Contract for inline input capture behavior."""

    @property
    def is_capturing(self) -> bool:
        """Whether capture mode is currently active."""
        ...

    def enter_capture_mode(
        self,
        prompt_id: str,
        message: str,
        input_type: str,  # "prompt" or "confirm"
        default: str = ""
    ) -> None:
        """Enter capture mode for a pending input request."""
        ...

    def exit_capture_mode(self) -> None:
        """Exit capture mode and restore normal input handling."""
        ...

    def handle_captured_input(self, user_input: str) -> Any:
        """Process captured input and return result to bridge."""
        ...
```

### Single Responsibility Extraction

The current proposal adds state directly to `ScrappyApp`, violating SRP. Extract to dedicated manager:

```python
class InputCaptureManager:
    """Manages inline input capture state and behavior.

    Single Responsibility: Handle capture mode state transitions
    and input processing for prompts/confirms.
    """

    def __init__(self, bridge: ThreadSafeAsyncBridge):
        self._bridge = bridge
        self._mode = False
        self._id: Optional[str] = None
        self._type: Optional[str] = None  # "prompt" or "confirm"
        self._default: str = ""
        self._queue: Queue[RequestInlineInput] = Queue()

    @property
    def is_capturing(self) -> bool:
        return self._mode

    def enter_capture_mode(
        self,
        prompt_id: str,
        message: str,
        input_type: str,
        default: str = ""
    ) -> None:
        """Enter capture mode or queue if already capturing."""
        if self._mode:
            # Queue concurrent request
            self._queue.put(RequestInlineInput(prompt_id, message, input_type, default))
            return

        self._mode = True
        self._id = prompt_id
        self._type = input_type
        self._default = default

    def exit_capture_mode(self) -> Optional[RequestInlineInput]:
        """Exit capture mode. Returns next queued request if any."""
        self._mode = False
        self._id = None
        self._type = None
        self._default = ""

        # Check for queued requests
        try:
            return self._queue.get_nowait()
        except Empty:
            return None

    def handle_captured_input(self, user_input: str) -> None:
        """Process input and provide result to bridge."""
        if self._type == "confirm":
            result = user_input.lower() in ('y', 'yes', '1', 'true')
        else:
            result = user_input if user_input else self._default

        self._bridge.provide_result(self._id, result)

    def cancel(self) -> None:
        """Cancel current capture (escape/ctrl+c)."""
        if self._type == "confirm":
            result = False
        else:
            result = self._default

        self._bridge.provide_result(self._id, result)
```

### Dependency Injection in ScrappyApp

```python
class ScrappyApp(App):
    def __init__(
        self,
        interactive_mode: "InteractiveMode",
        output_adapter: TextualOutputAdapter,
        capture_manager: Optional[InputCaptureManager] = None,  # Injectable for testing
    ):
        super().__init__()
        self.interactive_mode = interactive_mode
        self.output_adapter = output_adapter
        self.bridge = ThreadSafeAsyncBridge(self)
        self.capture_manager = capture_manager or InputCaptureManager(self.bridge)
```

## Implementation Steps

### Step 1: Create InputCaptureManager Class

Create `src/cli/input_capture.py`:

```python
"""Input capture manager for inline prompts/confirms."""

from typing import Optional, Any, TYPE_CHECKING
from queue import Queue, Empty

if TYPE_CHECKING:
    from .textual_app import ThreadSafeAsyncBridge

class InputCaptureManager:
    """Manages inline input capture state and behavior."""

    def __init__(self, bridge: "ThreadSafeAsyncBridge"):
        self._bridge = bridge
        self._mode = False
        self._id: Optional[str] = None
        self._type: Optional[str] = None
        self._default: str = ""
        self._queue: Queue = Queue()

    # ... (full implementation from Architectural Considerations section)
```

### Step 2: Replace Modal Messages

Replace `ShowPromptModal` (lines 62-80) and `ShowConfirmModal` (lines 83-100) with:

```python
class RequestInlineInput(Message):
    """Message to request inline input capture."""
    def __init__(self, prompt_id: str, message: str, input_type: str, default: str = ""):
        super().__init__()
        self.prompt_id = prompt_id
        self.message = message
        self.input_type = input_type  # "prompt" or "confirm"
        self.default = default
```

### Step 3: Update Bridge Methods

Modify `blocking_prompt()` (line 157) and `blocking_confirm()` (line 196) to post `RequestInlineInput` instead of modal messages.

### Step 4: New Handler for Inline Input

```python
def on_request_inline_input(self, message: RequestInlineInput) -> None:
    """Handle inline input request from worker thread."""
    # Delegate to capture manager (handles queuing if already capturing)
    self.capture_manager.enter_capture_mode(
        message.prompt_id,
        message.message,
        message.input_type,
        message.default
    )

    # Only update UI if this is the active capture (not queued)
    if self.capture_manager.is_capturing:
        self._update_capture_ui(message)

def _update_capture_ui(self, message: RequestInlineInput) -> None:
    """Update UI for capture mode."""
    output = self.query_one("#output", RichLog)

    # Display prompt in output area
    if message.input_type == "confirm":
        output.write(f"{message.message} [y/n]")
    else:
        output.write(message.message)

    # Visual feedback - add capture mode class
    input_container = self.query_one("#input_container")
    input_container.add_class("capture-mode")

    # Update placeholder
    if message.input_type == "confirm":
        self._input.placeholder = "Type y or n..."
    else:
        hint = f" (default: {message.default})" if message.default else ""
        self._input.placeholder = f"Enter value{hint}..."

    self._input.focus()
```

### Step 5: Modify on_input_submitted()

```python
def on_input_submitted(self, event: Input.Submitted) -> None:
    """Handle user input submission."""
    user_input = event.value.strip()
    self._input.value = ""

    # Handle capture mode
    if self.capture_manager.is_capturing:
        self._handle_captured_input(user_input)
        return

    # Normal command processing
    if not user_input:
        return
    self.process_command(user_input)

def _handle_captured_input(self, user_input: str) -> None:
    """Process input captured for prompt/confirm."""
    # Delegate to capture manager
    self.capture_manager.handle_captured_input(user_input)

    # Exit capture mode and check for queued requests
    next_request = self.capture_manager.exit_capture_mode()

    if next_request:
        # Process next queued request
        self.capture_manager.enter_capture_mode(
            next_request.prompt_id,
            next_request.message,
            next_request.input_type,
            next_request.default
        )
        self._update_capture_ui(next_request)
    else:
        # Fully exit capture mode
        self._exit_capture_ui()

def _exit_capture_ui(self) -> None:
    """Clean up capture mode UI state."""
    self._input.placeholder = "Type your message or command..."

    # Remove visual feedback
    input_container = self.query_one("#input_container")
    input_container.remove_class("capture-mode")
```

### Step 6: Add Escape Key and Ctrl+C Handling

Modify the existing `on_key()` method:

```python
def on_key(self, event) -> None:
    """Handle key events."""
    # Handle Escape or Ctrl+C in capture mode
    if self.capture_manager.is_capturing:
        if event.key == "escape" or event.key == "ctrl+c":
            self.capture_manager.cancel()
            self._exit_capture_ui()
            event.stop()
            return

        # Block up-arrow history during capture mode
        if event.key == "up":
            event.stop()
            return

    # Existing key handling for auto-focus...
    if self._input.has_focus:
        return
    # ... rest of existing code
```

### Step 7: Delete Modal Classes

Remove from `textual_app.py`:
- `PromptScreen` class (lines 220-262)
- `ConfirmScreen` class (lines 264-295)
- `ShowPromptModal` class (lines 62-80)
- `ShowConfirmModal` class (lines 83-100)
- `on_show_prompt_modal()` method (lines 778-794)
- `on_show_confirm_modal()` method (lines 796-813)

### Step 8: Update CSS

Remove lines 113-157 (all modal styles) from `scrappy.tcss`.

Add capture mode styling:
```css
/* Capture mode visual feedback - yellow prompt indicates waiting for response */
#input_container.capture-mode #input_prompt {
    color: #ffcc00;
}
```

### Step 9: Add Unit Tests

Create `tests/cli/test_input_capture.py` with behavioral tests:

```python
"""Tests for InputCaptureManager - tests behavior, not implementation."""

import pytest
from unittest.mock import Mock, MagicMock
from src.cli.input_capture import InputCaptureManager


class TestInputCaptureManager:
    """Unit tests for InputCaptureManager."""

    @pytest.fixture
    def mock_bridge(self):
        """Create mock bridge for testing."""
        bridge = Mock()
        bridge.provide_result = Mock()
        return bridge

    @pytest.fixture
    def manager(self, mock_bridge):
        """Create manager with mock bridge."""
        return InputCaptureManager(mock_bridge)

    # --- State Transition Tests ---

    def test_initially_not_capturing(self, manager):
        """Manager starts in non-capturing state."""
        assert manager.is_capturing is False

    def test_enter_capture_mode_sets_capturing(self, manager):
        """Entering capture mode sets is_capturing to True."""
        manager.enter_capture_mode("id1", "Question?", "confirm")
        assert manager.is_capturing is True

    def test_exit_capture_mode_clears_capturing(self, manager):
        """Exiting capture mode clears is_capturing."""
        manager.enter_capture_mode("id1", "Question?", "confirm")
        manager.exit_capture_mode()
        assert manager.is_capturing is False

    # --- Confirm Input Parsing Tests ---

    @pytest.mark.parametrize("input_value", ['y', 'yes', 'Y', 'YES', '1', 'true'])
    def test_confirm_yes_variations_return_true(self, manager, mock_bridge, input_value):
        """All yes variations return True to bridge."""
        manager.enter_capture_mode("id1", "Continue?", "confirm")
        manager.handle_captured_input(input_value)
        mock_bridge.provide_result.assert_called_once_with("id1", True)

    @pytest.mark.parametrize("input_value", ['n', 'no', 'N', 'NO', 'maybe', '', 'anything'])
    def test_confirm_no_variations_return_false(self, manager, mock_bridge, input_value):
        """All non-yes inputs return False to bridge."""
        manager.enter_capture_mode("id1", "Continue?", "confirm")
        manager.handle_captured_input(input_value)
        mock_bridge.provide_result.assert_called_once_with("id1", False)

    # --- Prompt Input Tests ---

    def test_prompt_returns_user_input_when_provided(self, manager, mock_bridge):
        """Non-empty prompt input returns user's value."""
        manager.enter_capture_mode("id1", "Name?", "prompt", default="Guest")
        manager.handle_captured_input("Alice")
        mock_bridge.provide_result.assert_called_once_with("id1", "Alice")

    def test_prompt_returns_default_on_empty_input(self, manager, mock_bridge):
        """Empty prompt input returns default value."""
        manager.enter_capture_mode("id1", "Name?", "prompt", default="Guest")
        manager.handle_captured_input("")
        mock_bridge.provide_result.assert_called_once_with("id1", "Guest")

    # --- Cancel Tests ---

    def test_cancel_confirm_returns_false(self, manager, mock_bridge):
        """Cancelling confirm returns False."""
        manager.enter_capture_mode("id1", "Delete?", "confirm")
        manager.cancel()
        mock_bridge.provide_result.assert_called_once_with("id1", False)

    def test_cancel_prompt_returns_default(self, manager, mock_bridge):
        """Cancelling prompt returns default value."""
        manager.enter_capture_mode("id1", "Name?", "prompt", default="Guest")
        manager.cancel()
        mock_bridge.provide_result.assert_called_once_with("id1", "Guest")

    # --- Queue Tests (Concurrent Prompts) ---

    def test_second_prompt_queued_when_capturing(self, manager):
        """Second prompt is queued, not immediately active."""
        manager.enter_capture_mode("id1", "First?", "confirm")
        manager.enter_capture_mode("id2", "Second?", "prompt")

        # Still on first prompt
        assert manager.is_capturing is True
        # Queue has second prompt (tested via exit returning it)

    def test_exit_returns_queued_request(self, manager):
        """Exiting capture mode returns next queued request."""
        manager.enter_capture_mode("id1", "First?", "confirm")
        manager.enter_capture_mode("id2", "Second?", "prompt", default="default")

        # Handle first and exit
        manager.handle_captured_input("y")
        next_request = manager.exit_capture_mode()

        assert next_request is not None
        assert next_request.prompt_id == "id2"
        assert next_request.input_type == "prompt"

    def test_exit_returns_none_when_queue_empty(self, manager):
        """Exiting with empty queue returns None."""
        manager.enter_capture_mode("id1", "Question?", "confirm")
        manager.handle_captured_input("y")
        next_request = manager.exit_capture_mode()

        assert next_request is None
```

## Files to Modify

| File | Changes |
|------|---------|
| `src/cli/input_capture.py` | **NEW** - InputCaptureManager class |
| `src/cli/textual_app.py` | Remove modal classes, integrate InputCaptureManager, update handlers |
| `src/cli/scrappy.tcss` | Remove modal CSS (lines 113-157), add capture-mode style |
| `tests/cli/test_input_capture.py` | **NEW** - Unit tests for InputCaptureManager |
| `tests/cli/test_textual_app.py` | Integration tests for capture mode UI |

## Testing

### Manual Testing Checklist

**Basic Confirm Flow:**
1. Run app, trigger a confirm (e.g., session restore prompt)
2. Verify question appears in output area with "[y/n]" hint
3. Verify placeholder changes to "Type y or n..."
4. Verify prompt character (">") turns yellow
5. Type `y` + Enter - verify True returned, normal mode restored
6. Type `n` + Enter - verify False returned
7. Type empty + Enter - verify False returned (empty = no)
8. Press Escape - verify False returned, capture mode exits
9. Press Ctrl+C - verify False returned, capture mode exits

**Basic Prompt Flow:**
1. Trigger a text prompt (e.g., `/plan` task)
2. Verify prompt appears in output area
3. Verify placeholder shows default hint if applicable
4. Type value + Enter - verify value returned
5. Type empty + Enter - verify default returned
6. Press Escape - verify default returned

**Edge Cases:**
1. Press Up-arrow during capture - verify no history navigation
2. Trigger two prompts rapidly (if possible) - verify second queued
3. Verify normal command input works after capture completes
4. Verify focus returns to input after capture

### Unit Tests (in test_input_capture.py)

**State Transition Tests:**
- `test_initially_not_capturing`
- `test_enter_capture_mode_sets_capturing`
- `test_exit_capture_mode_clears_capturing`

**Confirm Parsing Tests:**
- `test_confirm_yes_variations_return_true` (parametrized)
- `test_confirm_no_variations_return_false` (parametrized)

**Prompt Tests:**
- `test_prompt_returns_user_input_when_provided`
- `test_prompt_returns_default_on_empty_input`

**Cancel Tests:**
- `test_cancel_confirm_returns_false`
- `test_cancel_prompt_returns_default`

**Queue Tests:**
- `test_second_prompt_queued_when_capturing`
- `test_exit_returns_queued_request`
- `test_exit_returns_none_when_queue_empty`

## Notes

- The `ThreadSafeAsyncBridge` threading pattern remains unchanged
- `unified_io.py` requires no changes (it just calls bridge methods)
- All existing `.prompt()` and `.confirm()` call sites work unchanged
- UX trade-off: Users must type `y` or `n` instead of using keyboard to navigate Yes/No buttons

## Open Questions

1. **Visual feedback during capture**: Should we also dim/disable the output area scroll during capture mode?
2. **Timeout behavior**: Should there be a timeout for capture mode (e.g., auto-cancel after 60s of inactivity)?
3. **Multi-character shortcuts**: Should we support `yes`/`no` in addition to `y`/`n` for confirms? (Currently yes)
