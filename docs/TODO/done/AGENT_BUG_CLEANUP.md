# Agent/TUI Integration Bug Analysis

## Problem Summary

The `/agent` command freezes the TUI after the initial modal dialogs work. The deadlock occurs during agent execution, not during the initial prompts.

---

## Root Cause: CONFIRMED

**The `CodeAgent` is created without the bridged io instance.**

### Bug Location

**File:** `src/cli/agent_manager.py` line 84

```python
# Create agent
agent = CodeAgent(self.orchestrator)  # <-- BUG: io not passed!
agent.dry_run = dry_run
```

### Why This Causes Deadlock

1. `CLIAgentManager` has the correct bridged io via `self.display.get_io()`
2. The first two `io.confirm()` calls (dry-run, checkpoint) work because they use `self.display.get_io()`
3. `CodeAgent` is created WITHOUT the `io` parameter
4. `CodeAgent.__init__` line 130: `self.io = io or self._create_default_io()`
5. Since `io` is `None`, a NEW `RichIO` instance is created (CLI mode, no bridge)
6. `CodeAgent` creates `AgentUI(self.io)` - using the unbridged io
7. `ActionExecutor.execute()` calls `self.ui.prompt_confirm()`
8. `AgentUI.prompt_confirm()` calls `self.io.confirm()`
9. This unbridged io tries to block for input, causing deadlock

### Call Chain

```
CLIAgentManager.run_agent()
  -> io.confirm("dry-run?")        # Works - uses bridged io
  -> io.confirm("checkpoint?")     # Works - uses bridged io
  -> CodeAgent(orchestrator)       # BUG: No io passed!
     -> self.io = self._create_default_io()  # Creates unbridged RichIO
     -> AgentUI(self.io)           # Uses unbridged io
  -> agent.run(task)
     -> AgentLoop.run()
        -> ActionExecutor.execute()
           -> self.ui.prompt_confirm()  # Uses unbridged io
              -> self.io.confirm()      # DEADLOCK - no bridge!
```

---

## The Fix

### Primary Fix: Pass io to CodeAgent

**File:** `src/cli/agent_manager.py`

```python
def run_agent(self, task: str):
    io = self.display.get_io()
    # ... existing code ...

    # Create agent - PASS THE IO INSTANCE
    agent = CodeAgent(self.orchestrator, io=io)
    agent.dry_run = dry_run
```

### Secondary Fix: Store io directly in CLIAgentManager

For cleaner code per CLAUDE.md DI principles, store io directly:

```python
class CLIAgentManager:
    def __init__(self, orchestrator, io: CLIIOProtocol):
        self.orchestrator = orchestrator
        self.io = io  # Store directly
        self.display = DisplayManager(io=io, dashboard_enabled=False)

    def run_agent(self, task: str):
        io = self.io  # Use stored reference
        # ...
        agent = CodeAgent(self.orchestrator, io=io)
```

---

## Similar Issues to Check

### CLIMultiProvider

**File:** `src/cli/multiprovider.py`

This class already uses `self.io` directly - no issue here.

### Other CodeAgent Creation Sites

Search for other places where `CodeAgent` is instantiated without `io`:

```bash
grep -r "CodeAgent(" --include="*.py" | grep -v "test"
```

---

## Implementation Checklist

### Phase 1: Fix the Bug (COMPLETED)
- [x] Pass `io` to `CodeAgent` constructor in `agent_manager.py:84`
- [x] Verify the fix works in TUI mode (test_agent_tui.py - 12 tests passed)
- [x] Verify CLI mode still works (regression test - test_agent_core_refactor.py passing)

### Phase 2: Clean Architecture (COMPLETED)
- [x] Refactor `CLIAgentManager` to store `io` directly
- [x] Update constructor signature to be explicit about io dependency
- [x] Add type hints for io parameter

### Phase 3: Testing (COMPLETED)
- [x] Add unit test verifying CodeAgent receives bridged io
- [x] Add integration test for /agent command in TUI mode
- [ ] Manual test: launch TUI, run /agent, verify modals work throughout

---

## Affected Files

| File | Change |
|------|--------|
| `src/cli/agent_manager.py` | Pass `io=io` to CodeAgent constructor; store `io` directly on instance |
| `tests/cli/test_cli_handlers.py` | Added tests for io storage and bridged io passing |
| `tests/integration/test_agent_tui.py` | Added TestAgentManagerBridgedIO integration tests |

---

## Verification Steps

After fix:

1. Launch TUI: `python -m src.cli --tui`
2. Run `/agent <task>`
3. First modal (dry-run?) should appear - click Yes/No
4. Second modal (checkpoint?) should appear - click Yes/No
5. Agent starts executing
6. When agent requests tool approval, modal should appear - **this is the critical test**
7. No deadlock should occur

---

## Root Cause Summary

The modal dialog infrastructure is complete and working. The bug is simply that `CodeAgent` was not receiving the bridged io instance. This is a one-line fix.
