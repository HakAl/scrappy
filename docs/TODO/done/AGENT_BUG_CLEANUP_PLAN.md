# Agent/TUI Bug Cleanup - Implementation Plan

## STATUS: COMPLETED (2025-11-26)

All phases have been implemented and tested. The TUI/Agent bug that caused freezing due to blocking prompts in worker threads has been resolved via:

1. **Protocol-First Design**: `UserInteractionProtocol` abstracts user prompts/confirmations
2. **Three Implementations**: CLI (blocking), TUI (modal dialogs via bridge), AutoApprove (fallback)
3. **Dependency Injection**: Handlers receive interaction strategy via constructor
4. **Bridge Wiring**: `TextualInteractiveMode.run()` reinitializes handlers with TUI bridge

**Test Results**: 31 tests pass in `test_user_interaction.py`, 18 tests pass in `test_multiprovider.py`

---

## ADDED SCOPE: IO Path Verification

Before implementation, verify the IO instance flows correctly from ScrappyApp to CLIAgentManager:

### Phase 0: Trace and Verify IO Flow [COMPLETED 2025-11-26]

**Objective:** Confirm that the `io` instance used by `CLIAgentManager` is the TUI-enabled `UnifiedIO` with the correct `output_sink`.

**Verification Results:**

| Check | Result |
|-------|--------|
| `io.is_tui_mode` | `True` |
| `io.output_sink` | Not None (TextualOutputAdapter) |
| Bridge wired | Yes (`bridge=WIRED`) |
| Modal dialogs | Working (user clicked through them) |

**Diagnostic output:**
```
[DIAG] IO verification: TUI mode, bridge=WIRED
```

**Conclusion:** The existing IO infrastructure is working correctly. The `UnifiedIO` instance flows properly from `CLI.__init__` through `initialize_cli_handlers` to `CLIAgentManager`, and the bridge is correctly injected by `TextualInteractiveMode.run()` before any commands execute.

**IO Flow (verified):**
1. `CLI.__init__` creates `UnifiedIO` with `TextualOutputAdapter` (core.py:68)
2. `initialize_cli_handlers(orchestrator, session_start, io)` receives this io (core.py:79)
3. `CLIAgentManager(orchestrator, io)` receives io and stores as `self.io` (cli_factory.py:145)
4. `TextualInteractiveMode.run()` calls `self.io.set_bridge(app.bridge)` (textual_interactive.py:124)
5. `CLIAgentManager.run_agent()` uses `self.io` which now has bridge wired

**Next Steps:** Proceed to Phase 1 (Define Protocols)

---

## Analysis Summary

### Current State

The codebase has:
1. **Mode detection infrastructure** (`UnifiedIO.is_tui_mode`, `mode_utils.is_tui_mode()`)
2. **ThreadSafeAsyncBridge** in `textual_app.py` with `blocking_prompt()` and `blocking_confirm()`
3. **UnifiedIO.set_bridge()** method for wiring up modal support
4. **TestIO** for testing CLI components

But the actual command handlers (`CLIAgentManager`, `CLIMultiProvider`) do NOT use this infrastructure - they call `io.confirm()` and `io.prompt()` directly, causing deadlocks in TUI mode.

### Root Cause

Worker thread calls `io.confirm()` -> UnifiedIO.confirm() uses blocking input() -> Deadlock

The bridge exists but is not wired to UnifiedIO during command execution.

---

## Recommended Approach: Protocol-First

Per CLAUDE.md architectural principles, we need:
1. Protocol-first design (define interface before implementation)
2. Dependency injection (inject mode-aware IO/confirmation handling)
3. Single responsibility (separate CLI vs TUI confirmation strategies)

### Why?
- Clean separation of concerns
- Handlers don't know about mode - they use injected dependencies
- Testable with TestIO (already exists)
- Follows existing `CLIHandlerProtocol` pattern

---

## Implementation Plan

### Phase 1: Define Protocols

**File:** `src/cli/protocols.py`

Add the following protocols:

```python
class UserInteractionProtocol(Protocol):
    """Protocol for user interactions that may block.

    This abstraction allows CLI mode to use blocking prompts
    while TUI mode uses modal dialogs or sensible defaults.
    """

    def confirm(self, question: str, default: bool = False) -> bool:
        """Get yes/no confirmation from user."""
        ...

    def prompt(self, message: str, default: str = "") -> str:
        """Get text input from user."""
        ...


class AgentManagerProtocol(Protocol):
    """Protocol for code agent management."""

    orchestrator: "Orchestrator"

    def run_agent(self, task: str) -> None:
        """Run the code agent on a task."""
        ...


class MultiProviderProtocol(Protocol):
    """Protocol for multi-provider operations."""

    orchestrator: "Orchestrator"

    def synthesize_mode(self) -> None:
        """Interactive synthesis mode."""
        ...

    def delegate_mode(self, args: str) -> None:
        """Delegate to specific provider."""
        ...
```

### Phase 2: Create Mode-Aware Interaction Implementations

**File:** `src/cli/user_interaction.py` (NEW)

```python
"""Mode-aware user interaction implementations."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .io_interface import CLIIOProtocol


class CLIUserInteraction:
    """CLI mode - uses blocking prompts."""

    def __init__(self, io: "CLIIOProtocol"):
        self._io = io

    def confirm(self, question: str, default: bool = False) -> bool:
        return self._io.confirm(question, default=default)

    def prompt(self, message: str, default: str = "") -> str:
        return self._io.prompt(message, default=default)


class TUIUserInteraction:
    """TUI mode - uses modal dialogs via bridge."""

    def __init__(self, bridge: "ThreadSafeAsyncBridge"):
        self._bridge = bridge

    def confirm(self, question: str, default: bool = False) -> bool:
        return self._bridge.blocking_confirm(question)

    def prompt(self, message: str, default: str = "") -> str:
        return self._bridge.blocking_prompt(message, default=default)


class AutoApproveInteraction:
    """Fallback - auto-approves with sensible defaults.

    Used when modal dialogs are not available in TUI mode.
    Logs decisions for audit trail.
    """

    def __init__(self, io: "CLIIOProtocol"):
        self._io = io

    def confirm(self, question: str, default: bool = False) -> bool:
        self._io.echo(f"[Auto-approved: {question}] -> {default}")
        return default

    def prompt(self, message: str, default: str = "") -> str:
        self._io.echo(f"[Auto-input: {message}] -> '{default}'")
        return default
```

### Phase 3: Refactor Agent Manager [COMPLETED 2025-11-26]

**File:** `src/cli/agent_manager.py`

```python
class CLIAgentManager:
    """Manages code agent execution with human-in-the-loop approval."""

    def __init__(
        self,
        orchestrator,
        io: CLIIOProtocol,
        user_interaction: Optional[UserInteractionProtocol] = None,
    ):
        self.orchestrator = orchestrator
        self.display = DisplayManager(io=io, dashboard_enabled=False)
        # Inject user interaction - defaults to CLI mode
        self._interaction = user_interaction or CLIUserInteraction(io)

    def run_agent(self, task: str):
        io = self.display.get_io()
        # ... existing setup code ...

        # Use injected interaction instead of io.confirm()
        dry_run = self._interaction.confirm(
            "Run in dry-run mode? (no actual changes)",
            default=False
        )
        create_checkpoint = self._interaction.confirm(
            "Create git checkpoint before running?",
            default=True
        )

        # ... rest of method unchanged ...

        # Later prompts also use self._interaction
        if self._interaction.confirm("Save audit log to file?", default=False):
            log_path = agent.save_audit_log()
            io.secho(f"Saved to: {log_path}", fg="green")
```

### Phase 4: Refactor Multi-Provider [COMPLETED 2025-11-26]

**File:** `src/cli/multiprovider.py`

```python
class CLIMultiProvider:
    """Handles multi-provider coordination operations."""

    def __init__(
        self,
        orchestrator,
        io: CLIIOProtocol,
        user_interaction: Optional[UserInteractionProtocol] = None,
    ):
        self.orchestrator = orchestrator
        self.io = io
        self._interaction = user_interaction or CLIUserInteraction(io)

    def synthesize_mode(self):
        # Use injected interaction
        prompt = self._interaction.prompt("Enter your question")
        # ...
        providers_input = self._interaction.prompt(
            "Providers to query (comma-separated, or 'all')"
        )
```

### Phase 5: Update Factory Functions [COMPLETED 2025-11-26]

**File:** `src/cli/utils/cli_factory.py`

```python
def get_user_interaction(io: CLIIOProtocol, bridge=None) -> UserInteractionProtocol:
    """Get appropriate user interaction handler for current mode.

    Args:
        io: IO interface (used for mode detection)
        bridge: Optional ThreadSafeAsyncBridge for TUI mode

    Returns:
        UserInteractionProtocol implementation
    """
    from ..mode_utils import is_tui_mode
    from ..user_interaction import (
        CLIUserInteraction,
        TUIUserInteraction,
        AutoApproveInteraction
    )

    if not is_tui_mode(io):
        return CLIUserInteraction(io)

    if bridge is not None:
        return TUIUserInteraction(bridge)

    # Fallback: TUI mode without bridge -> auto-approve with logging
    return AutoApproveInteraction(io)


def initialize_cli_handlers(
    orchestrator: "Orchestrator",
    session_start: datetime,
    io: CLIIOProtocol,
    bridge=None,  # NEW parameter
) -> Dict[str, Any]:
    """Create and return all CLI component handlers."""

    # Get mode-aware interaction handler
    interaction = get_user_interaction(io, bridge)

    # ... existing handler creation ...

    return {
        # ... existing handlers ...
        'agent_mgr': CLIAgentManager(orchestrator, io, interaction),
        'multiprovider': CLIMultiProvider(orchestrator, io, interaction),
        # ...
    }
```

### Phase 6: Wire Bridge in TUI Mode [COMPLETED 2025-11-26]

**File:** `src/cli/textual_app.py` and `src/cli/textual_interactive.py`

Ensure bridge is passed through to factory when creating handlers:

```python
class ScrappyApp(App):
    def __init__(self, cli_instance):
        super().__init__()
        self._cli = cli_instance
        self._bridge = ThreadSafeAsyncBridge(self)

    def on_mount(self):
        # Wire bridge to CLI handlers
        if hasattr(self._cli, 'reinitialize_handlers_with_bridge'):
            self._cli.reinitialize_handlers_with_bridge(self._bridge)
```

---

## File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `src/cli/protocols.py` | ADD | Add UserInteractionProtocol, AgentManagerProtocol, MultiProviderProtocol |
| `src/cli/user_interaction.py` | NEW | CLIUserInteraction, TUIUserInteraction, AutoApproveInteraction |
| `src/cli/agent_manager.py` | MODIFY | Inject UserInteractionProtocol, use self._interaction |
| `src/cli/multiprovider.py` | MODIFY | Inject UserInteractionProtocol, use self._interaction |
| `src/cli/utils/cli_factory.py` | MODIFY | Add get_user_interaction(), update initialize_cli_handlers() |
| `src/cli/textual_app.py` | MODIFY | Wire bridge through to handlers |
| `tests/cli/test_agent_manager.py` | ADD | Tests with TestIO/mock interaction |
| `tests/cli/test_user_interaction.py` | ADD | Tests for all interaction implementations |

---

## Testing Strategy

### Unit Tests

1. **CLIUserInteraction** - verify delegates to io
2. **TUIUserInteraction** - verify delegates to bridge
3. **AutoApproveInteraction** - verify returns defaults, logs

### Integration Tests

1. **CLIAgentManager with TestIO** - verify prompts called correctly
2. **CLIMultiProvider with TestIO** - verify prompts called correctly

### Manual Tests

1. Run `/agent test task` in CLI mode -> prompts work
2. Run `/agent test task` in TUI mode -> modals appear (or auto-approve logs)
3. Run `/synthesize` in both modes

---

## Implementation Order

### Phase 0: IO Path Verification (Do First)

0. Add temporary diagnostic assertions to verify IO flow (see ADDED SCOPE section)
1. Run `/agent test` in TUI and verify assertions pass
2. Confirm `io.is_tui_mode == True` and `io.output_sink is not None`
3. Remove diagnostic assertions after verification

### Phase 1: Core Implementation [COMPLETED 2025-11-26]

1. [x] Add protocols to `protocols.py` - Added UserInteractionProtocol, AgentManagerProtocol, MultiProviderProtocol
2. [x] Create `user_interaction.py` with all 3 implementations - CLIUserInteraction, TUIUserInteraction, AutoApproveInteraction
3. [x] Add `get_user_interaction()` to factory - Added to cli_factory.py
4. [x] Refactor `CLIAgentManager` to use injected interaction - Uses self._interaction
5. [x] Write tests for agent manager - 25 tests in test_user_interaction.py
6. [x] Refactor `CLIMultiProvider` to use injected interaction - Uses self._interaction
7. [x] Write tests for multi-provider - 18 existing tests still pass
8. [x] Update `initialize_cli_handlers()` with bridge parameter - Added optional bridge param

### Phase 2: Bridge Wiring [COMPLETED 2025-11-26]

9. [x] Wire bridge in CLI and TextualInteractiveMode
   - Added `CLI.reinitialize_handlers_with_bridge(bridge)` method
   - Updated `TextualInteractiveMode.__init__()` to accept optional CLI reference
   - Updated `TextualInteractiveMode.run()` to call `cli.reinitialize_handlers_with_bridge()`
   - Command router's `agent_mgr` and `multiprovider` references updated after reinitialization
10. [x] Added tests for bridge wiring (6 new tests in `TestBridgeWiring` class)
11. [x] End-to-end testing - Manual verification in TUI mode
    - Tested `/agent please create a db repo for the api`
    - Modal dialogs appeared for dry-run, checkpoint, and save audit log prompts
    - User clicked Yes to all - agent completed successfully in ~24 seconds
    - No freezing or deadlocks - bridge wiring working correctly

---

## Edge Cases and Considerations

### What if bridge is not available in TUI mode?

Use `AutoApproveInteraction` with sensible defaults:
- dry_run = False (user wants action)
- create_checkpoint = True (safety first)
- save_audit_log = False (avoid file clutter)
- rollback = False (preserve changes)

### What about existing tests?

`TestIO` already provides `confirm()` and `prompt()` with preset values.
Tests can inject `CLIUserInteraction(TestIO(...))` or use a mock `UserInteractionProtocol`.

### Thread Safety

- `CLIUserInteraction`: Only safe in CLI mode (main thread)
- `TUIUserInteraction`: Thread-safe via bridge's Event synchronization
- `AutoApproveInteraction`: Thread-safe (no blocking, just logging)

---

## Success Criteria

1. `/agent` command works in CLI mode with blocking prompts
2. `/agent` command works in TUI mode without freezing
3. `/synthesize` command works in both modes
4. `/delegate` command works in both modes
5. All existing tests pass
6. New unit tests cover all interaction implementations
7. Code follows CLAUDE.md architectural principles
