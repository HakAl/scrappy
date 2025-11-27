# P1 Issues Implementation Plan

This document outlines the implementation plan to correct all P1 (Critical/Blocking) issues identified in ISSUES_PRIORITIZED.md.

---

## Implementation Status

| Issue | Description | Status | Completed |
|-------|-------------|--------|-----------|
| 1.1 | Agent continues after user denies | DONE | 2025-11-26 |
| 1.2 | Duplicate audit logs | DONE | 2025-11-26 |
| 1.3 | Multiline input not supported | DONE (already implemented) | 2025-11-26 |

---

## Summary

| Issue | Description | Complexity | Files Changed |
|-------|-------------|------------|---------------|
| 1.1 | Agent continues after user denies | Medium | 8 files |
| 1.2 | Duplicate audit logs | Low | 3 files |
| 1.3 | Multiline input not supported | Medium | 5 files |

**Note:** This plan has been reviewed against CLAUDE.md and the codebase. All corrections and clarifications are marked with `[CORRECTION]` or `[CLARIFICATION]`.

---

## Issue 1.1: Agent Keeps Trying After User Declines [COMPLETED 2025-11-26]

### Problem Statement

When a user denies an action (answers "no" to approval prompt), the agent continues attempting changes instead of offering a clear exit path. 
The loop message explicitly tells the agent to "try a different approach" rather than asking if the user wants to stop entirely.

### Root Cause Analysis

**Current Flow:**
1. `ActionExecutor.execute()` returns `ActionResult(approved=False)` when user denies (line 98-106)
2. `AgentLoop.update_conversation()` calls `_handle_denied_action()` (lines 466-483)
3. `_handle_denied_action()` adds message: "Please try a different approach..."
4. `AgentLoop.evaluate()` (lines 311-375) does NOT check the `approved` field
5. Loop continues because no exit condition exists for denials

**[CLARIFICATION] Main Loop Line Numbers:**
- Main loop is at lines 621-663 (not 621-656 as previously stated)
- Order of operations: think -> plan -> execute -> evaluate -> update_conversation
- Denial check will be added AFTER update_conversation but BEFORE next iteration

**Missing Logic:**
- No "stop entirely" option presented to user after denial
- `evaluate()` ignores `ActionResult.approved` field
- No denial count tracking for repeated denial scenarios

### Architecture Alignment

Per CLAUDE.md guidelines:
- Need protocol-first design for denial handling strategy
- Inject denial handler behavior rather than hardcode
- Single responsibility: separate "handle denial message" from "stop decision"

### Implementation Steps

#### Step 1: Create DenialHandlerProtocol

**File:** `src/agent/protocols.py`

Add new protocol after existing `DuplicateDetectorProtocol`:

```python
@runtime_checkable
class DenialHandlerProtocol(Protocol):
    """
    Protocol for handling user denials of actions.

    Abstracts denial handling to enable different strategies:
    - Ask user if they want to stop entirely
    - Track denial count and auto-stop
    - Continue with different approach (current behavior)
    """

    def handle_denial(
        self,
        action: str,
        denial_count: int,
    ) -> DenialHandlerResult:
        """
        Handle a user denial of an action.

        Args:
            action: The action that was denied
            denial_count: Number of times similar actions have been denied

        Returns:
            DenialHandlerResult with should_stop flag and message
        """
        ...
```

#### Step 2: Create DenialHandlerResult Type

**File:** `src/agent/types.py`

Add after `EvaluationResult`:

```python
@dataclass
class DenialHandlerResult:
    """Result from handling a user denial."""
    should_stop: bool
    message: str
    ask_user: bool = False  # Whether to prompt user for stop decision
```

#### Step 3: Implement InteractiveDenialHandler

**File:** `src/agent/denial_handler.py` (new file)

```python
"""
Denial handler implementation.

Provides interactive denial handling that asks user if they want to stop.
"""

from dataclasses import dataclass
from typing import Protocol

from .protocols import DenialHandlerProtocol, AgentUIProtocol
from .types import DenialHandlerResult


class InteractiveDenialHandler:
    """
    Interactive denial handler that asks user if they want to stop.

    Implements DenialHandlerProtocol.
    """

    def __init__(self, ui: AgentUIProtocol):
        self._ui = ui

    def handle_denial(
        self,
        action: str,
        denial_count: int,
    ) -> DenialHandlerResult:
        """Handle denial by asking user if they want to stop."""
        # [CORRECTION] Use prompt_confirm() not confirm() - matches AgentUIProtocol
        # AgentUIProtocol.prompt_confirm() is defined in src/agent/protocols.py:674-689
        stop_entirely = self._ui.prompt_confirm(
            f"You denied the '{action}' action. Stop the task entirely?",
            default=False
        )

        if stop_entirely:
            return DenialHandlerResult(
                should_stop=True,
                message="Task stopped by user after denying action.",
            )
        else:
            return DenialHandlerResult(
                should_stop=False,
                message=(
                    f"User denied the {action} action but wants to continue. "
                    "Please try a different approach."
                ),
            )


class AutoStopDenialHandler:
    """
    Denial handler that auto-stops after N denials.

    Useful for automated/testing scenarios.
    """

    def __init__(self, max_denials: int = 3):
        self._max_denials = max_denials

    def handle_denial(
        self,
        action: str,
        denial_count: int,
    ) -> DenialHandlerResult:
        """Handle denial by auto-stopping after max denials."""
        if denial_count >= self._max_denials:
            return DenialHandlerResult(
                should_stop=True,
                message=f"Task stopped after {denial_count} denied actions.",
            )
        return DenialHandlerResult(
            should_stop=False,
            message=(
                f"User denied the {action} action. "
                f"({denial_count}/{self._max_denials} denials) "
                "Please try a different approach."
            ),
        )
```

#### Step 4: Update AgentLoop to Use DenialHandler

**File:** `src/agent/agent_loop.py`

**4a. Add denial_handler to constructor:**

```python
def __init__(
    self,
    ...
    denial_handler: Optional[DenialHandlerProtocol] = None,
):
    ...
    self._denial_handler = denial_handler
    self._denial_count = 0  # Track denials in current session
```

**4b. Update `_handle_denied_action()` (lines 466-483):**

```python
def _handle_denied_action(
    self,
    state: ConversationState,
    thought: AgentThought,
    result: ActionResult,
) -> DenialHandlerResult:
    """Handle action denied by user."""
    self._denial_count += 1

    # Use denial handler if available
    if self._denial_handler:
        denial_result = self._denial_handler.handle_denial(
            action=result.action,
            denial_count=self._denial_count,
        )
    else:
        # Default behavior: ask to continue
        denial_result = DenialHandlerResult(
            should_stop=False,
            message=(
                f"User denied the {result.action} action. "
                "Please try a different approach or explain why this action is necessary."
            ),
        )

    # Update conversation with denial message
    state.messages.append({
        'role': 'assistant',
        'content': thought.raw_response,
    })
    state.messages.append({
        'role': 'user',
        'content': denial_result.message,
    })

    return denial_result
```

**4c. Update `update_conversation()` to return denial result:**

**[CLARIFICATION] Breaking Change:** This changes the return type from `None` to `Optional[DenialHandlerResult]`.
If external code depends on this method returning `None`, it will need updates.

```python
def update_conversation(
    self,
    state: ConversationState,
    thought: AgentThought,
    action: AgentAction,
    result: ActionResult,
) -> Optional[DenialHandlerResult]:
    """Update conversation and return denial result if action was denied.

    [CORRECTION] Return type changed from None to Optional[DenialHandlerResult].
    This is a breaking change to the interface.
    """
    ...
    elif not result.approved and action.action in self._tools:
        return self._handle_denied_action(state, thought, result)
    ...
    return None
```

**4d. Update main loop to check denial result (lines 621-663):**

**[CORRECTION]** Line numbers corrected from 621-656 to 621-663.

```python
# Update conversation history and check for denial stop
denial_result = self.update_conversation(state, thought, action, result)

# Check if user wants to stop after denial
if denial_result and denial_result.should_stop:
    return {
        'success': False,
        'result': denial_result.message,
        'iterations': state.iteration,
    }

# Check evaluation result
if evaluation.is_complete:
    ...
```

#### Step 5: Update AgentLoopConfig

**File:** `src/agent/config.py`

Add denial handler configuration:

```python
@dataclass
class AgentLoopConfig:
    ...
    denial_handler_type: str = "interactive"  # "interactive", "auto_stop", "continue"
    max_denials_before_stop: int = 3  # For auto_stop handler
```

#### Step 6: Wire Up in Factory/Core

**File:** `src/agent/core.py` or factory

```python
def _create_denial_handler(self) -> DenialHandlerProtocol:
    """Create denial handler based on config."""
    if self._config.denial_handler_type == "interactive":
        return InteractiveDenialHandler(self._ui)
    elif self._config.denial_handler_type == "auto_stop":
        return AutoStopDenialHandler(self._config.max_denials_before_stop)
    else:
        return None  # Use default continue behavior
```

#### Step 7: Add Tests

**File:** `tests/agent/test_denial_handler.py` (new file)

```python
"""Tests for denial handler implementations."""

import pytest
from src.agent.denial_handler import InteractiveDenialHandler, AutoStopDenialHandler
from src.agent.types import DenialHandlerResult
# [CORRECTION] StubAgentUI does not exist in tests/helpers.py - must be created
# See "Prerequisites" section below for the required stub implementation
from tests.helpers import StubAgentUI


class TestInteractiveDenialHandler:
    """Tests for InteractiveDenialHandler."""

    def test_user_confirms_stop_returns_should_stop_true(self):
        """When user confirms stop, should_stop is True."""
        # [CORRECTION] StubAgentUI uses prompt_confirm_responses, not confirm_responses
        ui = StubAgentUI(prompt_confirm_responses=[True])
        handler = InteractiveDenialHandler(ui)

        result = handler.handle_denial("write_file", denial_count=1)

        assert result.should_stop is True
        assert "stopped by user" in result.message.lower()

    def test_user_declines_stop_returns_should_stop_false(self):
        """When user declines stop, should_stop is False."""
        ui = StubAgentUI(prompt_confirm_responses=[False])
        handler = InteractiveDenialHandler(ui)

        result = handler.handle_denial("write_file", denial_count=1)

        assert result.should_stop is False
        assert "different approach" in result.message.lower()


class TestAutoStopDenialHandler:
    """Tests for AutoStopDenialHandler."""

    def test_stops_after_max_denials(self):
        """Should stop after reaching max denials."""
        handler = AutoStopDenialHandler(max_denials=3)

        result = handler.handle_denial("write_file", denial_count=3)

        assert result.should_stop is True

    def test_continues_before_max_denials(self):
        """Should continue before reaching max denials."""
        handler = AutoStopDenialHandler(max_denials=3)

        result = handler.handle_denial("write_file", denial_count=2)

        assert result.should_stop is False
```

**File:** `tests/agent/test_agent_loop.py`

Add tests for denial flow:

```python
class TestDenialHandling:
    """Tests for agent loop denial handling."""

    def test_loop_stops_when_denial_handler_returns_should_stop(self):
        """Loop should stop when denial handler returns should_stop=True."""
        ...

    def test_loop_continues_when_denial_handler_returns_should_continue(self):
        """Loop should continue when denial handler returns should_stop=False."""
        ...

    def test_denial_count_increments_on_each_denial(self):
        """Denial count should increment with each denied action."""
        ...
```

### Files Modified

| File | Change Type | Description |
|------|-------------|-------------|
| `src/agent/protocols.py` | Add | DenialHandlerProtocol |
| `src/agent/types.py` | Add | DenialHandlerResult dataclass |
| `src/agent/denial_handler.py` | New | InteractiveDenialHandler, AutoStopDenialHandler |
| `src/agent/agent_loop.py` | Modify | Use denial handler, return denial result |
| `src/agent/config.py` | Add | denial_handler_type, max_denials_before_stop |
| `src/agent/core.py` | Modify | Wire up denial handler creation |
| `tests/agent/test_denial_handler.py` | New | Tests for denial handlers |
| `tests/agent/test_agent_loop.py` | Add | Tests for denial flow |
| `tests/helpers.py` | Add | StubAgentUI test double (see Prerequisites) |

### Prerequisites: Add StubAgentUI to tests/helpers.py

**[CORRECTION]** The tests reference `StubAgentUI` which does not exist. Add this stub to `tests/helpers.py`:

```python
class StubAgentUI:
    """
    Test double for AgentUIProtocol.

    Implements the minimum interface needed for testing denial handling.

    Example:
        ui = StubAgentUI(prompt_confirm_responses=[True, False])
        result1 = ui.prompt_confirm("Stop?")  # Returns True
        result2 = ui.prompt_confirm("Stop?")  # Returns False
    """

    def __init__(
        self,
        prompt_confirm_responses: Optional[List[bool]] = None,
    ):
        """
        Initialize stub with preset responses.

        Args:
            prompt_confirm_responses: List of booleans to return from prompt_confirm()
        """
        self._prompt_confirm_responses = list(prompt_confirm_responses) if prompt_confirm_responses else []
        self._prompt_confirm_index = 0
        self._shown_messages: List[str] = []

    def prompt_confirm(self, message: str = "Allow?", default: bool = False) -> bool:
        """Return preset confirmation or default."""
        self._shown_messages.append(message)
        if self._prompt_confirm_index < len(self._prompt_confirm_responses):
            result = self._prompt_confirm_responses[self._prompt_confirm_index]
            self._prompt_confirm_index += 1
            return result
        return default

    def show_thinking(self, text: str) -> None:
        """Record thinking message."""
        self._shown_messages.append(f"[thinking] {text}")

    def show_tool_request(self, tool_name: str, params: Dict[str, Any]) -> None:
        """Record tool request."""
        self._shown_messages.append(f"[tool] {tool_name}")

    def show_command(self, command: str) -> None:
        """Record command."""
        self._shown_messages.append(f"[command] {command}")

    def show_error(self, message: str) -> None:
        """Record error."""
        self._shown_messages.append(f"[error] {message}")

    def show_result(self, result: str, title: str = "Result", is_error: bool = False) -> None:
        """Record result."""
        self._shown_messages.append(f"[result] {result}")

    def show_warning(self, message: str) -> None:
        """Record warning."""
        self._shown_messages.append(f"[warning] {message}")

    def show_progress(self, message: str) -> None:
        """Record progress."""
        self._shown_messages.append(f"[progress] {message}")

    def show_provider_status(self, provider: str, message: str, color: str = "cyan") -> None:
        """Record provider status."""
        self._shown_messages.append(f"[provider:{provider}] {message}")

    def show_rule(self, title: Optional[str] = None) -> None:
        """Record rule."""
        self._shown_messages.append(f"[rule] {title or ''}")

    def get_shown_messages(self) -> List[str]:
        """Get all recorded messages for verification."""
        return self._shown_messages.copy()
```

---

## Issue 1.2: Duplicate Audit Logs Created Outside .scrappy/ [COMPLETED 2025-11-26]

### Problem Statement

Two audit log files are created:
- `.agent_audit.json` (project root) - from hardcoded default in `save_audit_log()`
- `.scrappy/audit.json` (correct location) - from auto-save via path_provider

### Root Cause Analysis

**Current Flow:**
1. `core.py:764` has hardcoded default: `def save_audit_log(self, path: str = ".agent_audit.json")`
2. `audit.py` `save()` method (lines 211-235) correctly uses `path_provider.audit_file()`
3. BUT `core.py` passes the hardcoded path to `save()`, bypassing path_provider

**[CORRECTION] Additional Bug: Parameter Mismatch**

The current `core.py:764-766` has another bug - parameter order mismatch:

```python
# Current code in core.py:
def save_audit_log(self, path: str = ".agent_audit.json"):
    return self._audit_logger.save(self.project_root, path)

# But audit.py:211 expects:
def save(self, path: Optional[Path] = None, filename: Optional[str] = None) -> str:
```

The call `self._audit_logger.save(self.project_root, path)` passes:
- `self.project_root` as `path` (directory)
- `path` (the ".agent_audit.json" string) as `filename`

This is confusing and relies on implicit behavior. The fix removes this entirely.

**The Fix:**
The `audit.py` `save()` method already supports being called without arguments when `path_provider` is set. The issue is `core.py` passing a hardcoded default.

### Implementation Steps

#### Step 1: Update core.py save_audit_log()

**File:** `src/agent/core.py` (line 764)

**Before:**
```python
def save_audit_log(self, path: str = ".agent_audit.json"):
    """Save audit log to file."""
    return self._audit_logger.save(self.project_root, path)
```

**After:**
```python
def save_audit_log(self) -> str:
    """
    Save audit log to file.

    Uses path_provider to determine correct location (.scrappy/audit.json).

    Returns:
        Path to the saved audit log file.
    """
    return self._audit_logger.save()
```

#### Step 2: Verify audit.py save() Handles No Arguments

**File:** `src/agent/audit.py` (lines 211-235)

Current implementation already handles this correctly:
```python
def save(self, path: Optional[Path] = None, filename: Optional[str] = None) -> str:
    if self._path_provider:
        self._path_provider.ensure_data_dir()
        log_path = self._path_provider.audit_file()
    elif path:
        ...
```

No changes needed to audit.py.

#### Step 3: Update examples/agent_demo.py

**File:** `examples/agent_demo.py` (line 284)

**Before:**
```python
log_path = code_agent.save_audit_log(".agent_audit.json")
```

**After:**
```python
log_path = code_agent.save_audit_log()
```

#### Step 4: Add Test Coverage

**File:** `tests/agent/test_core.py` or `tests/agent/test_audit.py`

```python
class TestAuditLogPath:
    """Tests for audit log file location."""

    def test_save_audit_log_uses_path_provider(self, tmp_path):
        """save_audit_log() should use path_provider, not hardcoded path."""
        # Setup agent with path_provider pointing to tmp_path/.scrappy/
        agent = create_test_agent(project_root=tmp_path)
        agent._audit_logger.log_action("test", {}, "result", True)

        # Save and check location
        saved_path = agent.save_audit_log()

        assert ".scrappy" in saved_path
        assert saved_path.endswith("audit.json")
        assert not Path(tmp_path / ".agent_audit.json").exists()

    def test_no_duplicate_audit_files_created(self, tmp_path):
        """Only one audit file should be created in .scrappy/."""
        agent = create_test_agent(project_root=tmp_path)
        agent._audit_logger.enable_auto_save()
        agent._audit_logger.log_action("test", {}, "result", True)
        agent.save_audit_log()

        # Check only .scrappy/audit.json exists
        assert (tmp_path / ".scrappy" / "audit.json").exists()
        assert not (tmp_path / ".agent_audit.json").exists()
```

### Files Modified

| File | Change Type | Description |
|------|-------------|-------------|
| `src/agent/core.py` | Modify | Remove hardcoded default path |
| `examples/agent_demo.py` | Modify | Remove explicit path argument |
| `tests/agent/test_audit.py` | Add | Tests for correct audit log location |

---

## Issue 1.3: Multiline Input Not Supported [COMPLETED 2025-11-26 - Already Implemented]

### Problem Statement

Users cannot paste multiline content - each line runs as a separate command. The multiline infrastructure exists but is disabled by default.

### Root Cause Analysis

**Current State:**
1. `input_handler.py:86` has `read_interactive_input(multiline_mode: bool = False)`
2. Multiline logic exists (lines 96-137) but requires `multiline_mode=True`
3. `output.py:456-462` uses Click's `prompt()` which is single-line only
4. No configuration to enable multiline globally

**Key Finding:** The multiline infrastructure is complete but disabled. Need to:
1. Enable by default OR
2. Provide toggle command OR
3. Add configuration option

### Architecture Alignment

Per CLAUDE.md guidelines:
- Create protocol for input mode strategy
- Inject input mode behavior
- Make it configurable

**[CLARIFICATION]** `src/cli/protocols.py` exists and already contains multiple protocols
(OutputSink, CLIHandlerProtocol, DisplayFormatterProtocol, etc.). The InputModeProtocol will be added to this file after the existing protocols.

### Implementation Steps

#### Step 1: Create InputModeProtocol

**File:** `src/cli/protocols.py`

Add protocol for input mode handling (add after existing protocols around line 1013):

```python
@runtime_checkable
class InputModeProtocol(Protocol):
    """Protocol for input mode handling."""

    @property
    def is_multiline(self) -> bool:
        """Whether multiline mode is enabled."""
        ...

    def toggle(self) -> bool:
        """Toggle multiline mode. Returns new state."""
        ...
```

#### Step 2: Add Multiline Toggle Command

**File:** `src/cli/commands.py`

Add `/multiline` command to toggle multiline input mode:

```python
@cli.command()
def multiline():
    """Toggle multiline input mode."""
    ctx = get_context()
    new_state = ctx.input_handler.toggle_multiline()
    if new_state:
        ctx.io.info("Multiline mode enabled. Use \\ at end of line to continue, blank line to submit.")
    else:
        ctx.io.info("Multiline mode disabled. Single-line input active.")
```

#### Step 3: Update InputHandler

**File:** `src/cli/input_handler.py`

**3a. Add multiline state tracking:**

```python
class InputHandler:
    def __init__(self, io: IOInterface):
        self.io = io
        self._multiline_enabled = False  # Default to single-line

    @property
    def is_multiline(self) -> bool:
        """Whether multiline mode is enabled."""
        return self._multiline_enabled

    def toggle_multiline(self) -> bool:
        """Toggle multiline mode. Returns new state."""
        self._multiline_enabled = not self._multiline_enabled
        return self._multiline_enabled

    def set_multiline(self, enabled: bool) -> None:
        """Set multiline mode explicitly."""
        self._multiline_enabled = enabled
```

**3b. Update read_interactive_input() to use state:**

```python
def read_interactive_input(self, multiline_mode: Optional[bool] = None) -> str:
    """
    Read input from user in interactive mode.

    Args:
        multiline_mode: Override multiline setting. If None, uses instance setting.

    Returns:
        The user input string, stripped.
    """
    use_multiline = multiline_mode if multiline_mode is not None else self._multiline_enabled

    if use_multiline:
        # Existing multiline logic (lines 97-137)
        ...
    else:
        # Single-line logic (lines 139-145)
        ...
```

#### Step 4: Add Configuration Support

**File:** `src/config/schema.py`

Add multiline setting to CLI config:

```python
@dataclass
class CLIConfig:
    ...
    multiline_input: bool = False  # Default to single-line for compatibility
```

**File:** `src/cli/input_handler.py`

Update constructor to accept config:

```python
def __init__(self, io: IOInterface, config: Optional[CLIConfig] = None):
    self.io = io
    self._multiline_enabled = config.multiline_input if config else False
```

#### Step 5: Consider prompt_toolkit Integration (Recommended Enhancement)

**[CLARIFICATION]** Since this is a P1 issue and users CANNOT paste multiline content currently, prompt_toolkit should be considered a **primary solution** rather than optional. The current implementation using Click's `prompt()` has known paste issues on Windows.

For better paste detection and history, consider adding prompt_toolkit. This would significantly improve UX.

**File:** `requirements.txt`

```
prompt_toolkit>=3.0.0
```

**File:** `src/cli/input_handler.py`

```python
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False


class PromptToolkitInputHandler:
    """Input handler using prompt_toolkit for better multiline/history support."""

    def __init__(self, history_file: str = "~/.scrappy_history"):
        self._session = PromptSession(
            history=FileHistory(os.path.expanduser(history_file)),
            multiline=True,
        )

    def read_interactive_input(self) -> str:
        """Read input with full multiline and history support."""
        return self._session.prompt("You> ")
```

#### Step 6: Add Help Text for Multiline Mode

**File:** `src/cli/input_handler.py`

Update the multiline prompt to show help:

```python
if use_multiline:
    self.io.secho(
        "You> (multiline: \\ to continue, blank line to submit)",
        fg="green",
        bold=True,
        nl=False
    )
```

#### Step 7: Add Tests

**File:** `tests/cli/test_input_handler.py`

```python
class TestMultilineInput:
    """Tests for multiline input mode."""

    def test_multiline_disabled_by_default(self):
        """Multiline mode should be disabled by default."""
        # [CORRECTION] Use MockIO from tests/helpers.py, not StubIO
        handler = InputHandler(MockIO())
        assert handler.is_multiline is False

    def test_toggle_multiline_changes_state(self):
        """toggle_multiline() should change mode state."""
        handler = InputHandler(MockIO())

        result = handler.toggle_multiline()

        assert result is True
        assert handler.is_multiline is True

    def test_multiline_reads_continuation_lines(self):
        """Multiline mode should read lines ending with \\."""
        io = MockIO(inputs=["line1\\", "line2\\", "line3", ""])
        handler = InputHandler(io)
        handler.set_multiline(True)

        result = handler.read_interactive_input()

        assert result == "line1\nline2\nline3"

    def test_config_sets_initial_multiline_state(self):
        """Config should set initial multiline state."""
        config = CLIConfig(multiline_input=True)
        handler = InputHandler(MockIO(), config=config)

        assert handler.is_multiline is True
```

### Files Modified

| File | Change Type | Description |
|------|-------------|-------------|
| `src/cli/protocols.py` | Add | InputModeProtocol |
| `src/cli/input_handler.py` | Modify | Add multiline state, toggle, config support |
| `src/cli/commands.py` | Add | /multiline toggle command |
| `src/config/schema.py` | Add | multiline_input config option |
| `tests/cli/test_input_handler.py` | Add | Tests for multiline mode |

---

## Implementation Order

Recommended order based on dependencies and complexity:

### Phase 1: Quick Wins (Low Risk)

1. **Issue 1.2: Duplicate Audit Logs** - Simple fix, low risk
   - Remove hardcoded default in `core.py`
   - Update example file
   - Add tests

### Phase 2: Core Functionality

2. **Issue 1.1: Agent Denial Handling** - Medium complexity, high value
   - Create DenialHandlerProtocol
   - Implement InteractiveDenialHandler
   - Update AgentLoop
   - Add tests

### Phase 3: UX Improvements

3. **Issue 1.3: Multiline Input** - Medium complexity, good UX improvement
   - Add multiline state to InputHandler
   - Add /multiline toggle command
   - Add configuration support
   - Add tests

---

## Testing Strategy

### Unit Tests

Each implementation step includes specific unit tests. All tests should:
- Use test doubles from `tests/helpers.py`
- NOT make real API calls
- Test behavior, not implementation details
- Cover edge cases

### Integration Tests

After all P1 fixes:

```python
class TestP1Integration:
    """Integration tests for P1 fixes."""

    def test_denial_stops_agent_when_user_confirms(self):
        """End-to-end: denying action and confirming stop ends the loop."""
        ...

    def test_audit_log_only_in_scrappy_directory(self):
        """End-to-end: audit log is only created in .scrappy/."""
        ...

    def test_multiline_input_in_interactive_mode(self):
        """End-to-end: multiline input works in interactive session."""
        ...
```

### Manual Testing Checklist

- [ ] Deny an action, confirm stop -> agent stops
- [ ] Deny an action, decline stop -> agent tries different approach
- [ ] Run agent task -> audit log only in `.scrappy/audit.json`
- [ ] Toggle `/multiline` -> can paste multiline content
- [ ] Multiline with `\` continuation -> lines joined correctly

---

## Rollback Plan

Each fix is independent. If issues arise:

1. **Issue 1.1:** Revert `agent_loop.py` changes, remove `denial_handler.py`
2. **Issue 1.2:** Restore hardcoded default in `core.py`
3. **Issue 1.3:** Revert `input_handler.py` changes, remove `/multiline` command

---

## Success Criteria

| Issue | Success Criteria |
|-------|-----------------|
| 1.1 | User can stop agent after denying action; tests pass |
| 1.2 | Only one audit log in `.scrappy/`; no `.agent_audit.json` created |
| 1.3 | `/multiline` command toggles mode; multiline paste works |

---

## Appendix: Related Files Reference

### Issue 1.1 Files
- `src/agent/agent_loop.py`
- `src/agent/action_executor.py`
- `src/agent/protocols.py`
- `src/agent/types.py`
- `src/agent/config.py`
- `src/agent/core.py`

### Issue 1.2 Files
- `src/agent/core.py`
- `src/agent/audit.py`
- `examples/agent_demo.py`

### Issue 1.3 Files
- `src/cli/input_handler.py`
- `src/cli/output.py`
- `src/cli/commands.py`
- `src/cli/protocols.py`
- `src/config/schema.py`

---

## Appendix: Review Corrections Summary

This plan was reviewed against CLAUDE.md and the codebase. The following corrections were made:

### Issue 1.1 Corrections

| Location | Original | Corrected |
|----------|----------|-----------|
| Line numbers | 621-656 | 621-663 |
| Method name | `self._ui.confirm()` | `self._ui.prompt_confirm()` |
| Test stub | `StubAgentUI(confirm_responses=[...])` | `StubAgentUI(prompt_confirm_responses=[...])` |
| Test helpers | Referenced non-existent `StubAgentUI` | Added full `StubAgentUI` implementation |
| Breaking change | Not documented | Added `[CLARIFICATION]` for return type change |

### Issue 1.2 Corrections

| Location | Original | Corrected |
|----------|----------|-----------|
| Parameter bug | Not documented | Documented parameter mismatch between `core.py` and `audit.py` |

### Issue 1.3 Corrections

| Location | Original | Corrected |
|----------|----------|-----------|
| Protocol file | Location not verified | Confirmed `src/cli/protocols.py` exists with ~1000 lines of existing protocols |
| Test helper | `StubIO` | `MockIO` (which exists in `tests/helpers.py`) |
| prompt_toolkit | "Optional Enhancement" | "Recommended Enhancement" since this is P1 |

### Additional Prerequisites Added

1. **StubAgentUI** must be added to `tests/helpers.py` before Issue 1.1 tests can run
2. The implementation uses `MockIO` which already exists in `tests/helpers.py`

### CLAUDE.md Alignment Verification

| Principle | Issue 1.1 | Issue 1.2 | Issue 1.3 |
|-----------|-----------|-----------|-----------|
| Protocol-First Design | Yes - DenialHandlerProtocol | N/A | Yes - InputModeProtocol |
| Dependency Injection | Yes - denial_handler injected | N/A | Yes - config injected |
| Single Responsibility | Yes - separate handler from loop | N/A | Yes - separate mode from handler |
| No Side Effects in Constructor | Yes | N/A | Yes |
| Behavior-Focused Tests | Yes | Yes | Yes |
| Test Doubles from helpers.py | Now verified | Yes | Yes |
