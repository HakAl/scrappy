# Agent UX Improvements (WIP)

## Problem

Agent output is overwhelming - dumps everything too fast. Users can't follow what's happening.

## Current State

- Agent shows: thinking, tool requests (full params), results, errors
- All verbose, no way to reduce
- Hard step limit (max_steps=10) feels arbitrary
- Step counter [3/10] meaningless if task needs 15 steps

## Proposed UX

### 1. Compact Output (Default)

Status bar shows loading state:
```
Agent working...
```

Log shows one line per action:
```
[Step 1] read_file: src/main.py... 245 lines
[Step 2] write_file: src/utils.py... done
[Step 3] run_command: pytest... 3 passed
[Step 4] Complete: Added utility function
```

No thoughts, no full params, no verbose results.

### 2. Verbose Mode (Opt-in)

User runs `/verbose agent` or config option.
Shows full output: thinking, params, results.

### 3. Remove Hard Step Limit

Replace max_steps with smarter guardrails:

- **Loop detection** - catch repeated actions
- **User control** - Ctrl+C always works
- **Soft checkpoint** - after N steps, prompt: "Still working. Continue? (y/n)"

Show `[Step N]` without countdown - user knows they can stop.

## Implementation

### AgentUI Changes

```python
class AgentUI:
    def __init__(self, io, theme=None, verbose=False):
        self.verbose = verbose
        self.current_step = 0

    def show_thinking(self, text):
        if not self.verbose:
            return  # Skip in compact mode
        # ... existing code

    def show_tool_request(self, tool_name, params):
        self.current_step += 1
        if not self.verbose:
            # Hierarchy of display preference with fallback
            target = (
                params.get('path') or
                params.get('command') or
                params.get('query') or  # for search tools
                str(list(params.values())[0]) if params else ''  # fallback
            )
            # Truncate if target is massive
            if len(target) > 50:
                target = target[:47] + "..."
            self.io.echo(f"[Step {self.current_step}] {tool_name}: {target}")
            return
        # ... existing verbose code
```

### Status Bar

Update status during agent run:
```python
self.io.update_status("Agent working...")
# ... after completion
self.io.update_status("")  # Clear
```

### Soft Checkpoint

After N steps (configurable, default 15), show context before prompting:
```python
if state.iteration > 0 and state.iteration % checkpoint_interval == 0:
    self._ui.show_system_message(f"Paused: Agent has run {state.iteration} steps.")
    if not self._ui.prompt_confirm("Continue execution?", default=True):
        return {'success': False, 'result': 'Stopped by user at checkpoint'}
```

## Research Results

### Existing Guardrails (Comprehensive!)

**1. Loop Detection - EXISTS**
- `DuplicateDetector` in `agent/duplicate_detector.py`
- 3-action lookback window
- Blocks exact duplicate action+params
- Tracks failed commands separately

**2. Repeated Action Handling - EXISTS**
- `MAX_COMMAND_FAILURES = 3` - blocks command after 3 failures
- Categorizes by approach (npm, pip, make, etc.)
- Injects warnings into next prompt to force different strategy

**3. Premature Completion Detection - EXISTS**
- Agent can't declare "done" without meaningful actions
- Tracks `meaningful_actions` list (write_file, run_command, etc.)

**4. Safety/Confirmation - EXISTS**
- Safe actions auto-approved (read_file, list_files, etc.)
- Unsafe actions require confirmation (write_file, run_command)
- DenialHandler stops after N denials (default 3)

**5. Command Security - EXISTS**
- Dangerous patterns blocked (rm -rf /, format, fork bombs)
- Timeout per command (30s default)
- Output limits (10KB default)

**6. Audit Logging - EXISTS**
- Every action logged immediately
- Crash recovery via signal handlers

**7. Cost/Token Limits - PARTIAL**
- Max tokens per response (LLM level)
- Rate limiting per provider
- NO cumulative cost tracking (gap)
- NOTE: Rate limit data already persisted to file - cost tracking is easy future win

### Guardrail Architecture

```
Layer 1: Command Security (dangerous patterns, timeouts)
Layer 2: Action Validation (safety checker, duplicate detector)
Layer 3: Loop Control (max iterations, meaningful action tracking)
Layer 4: Human Control (confirmation prompts, denial handling)
Layer 5: Observability (audit logging, crash recovery)
```

### Conclusion

**max_steps is largely redundant** given existing guardrails:
- Duplicates blocked after 3-action window
- Commands blocked after 3 failures
- User can Ctrl+C anytime
- Denial handler stops after 3 denials

**Recommendation:**
- Remove hard max_steps limit OR increase significantly (50+)
- Add soft checkpoint as UX feature, not safety feature
- Rely on existing guardrails for actual protection

## Cancellation Mechanism

### Requirements
- Both `Esc` and `Ctrl+C` must cancel agent execution
- Cancellation must be graceful (save audit log, clean state)
- User sees confirmation that agent was cancelled

### Current State
- `Ctrl+C` works via KeyboardInterrupt (caught in agent_manager.py:162)
- No `Esc` binding exists
- Agent runs in worker thread - KeyboardInterrupt doesn't propagate from TUI

### Implementation

**1. Add CancellationToken**

```python
# agent/cancellation.py
import threading

class CancellationToken:
    """Thread-safe cancellation signal for agent operations."""

    def __init__(self):
        self._cancelled = threading.Event()

    def cancel(self):
        """Signal cancellation."""
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        """Check if cancelled."""
        return self._cancelled.is_set()

    def reset(self):
        """Reset for reuse."""
        self._cancelled.clear()
```

**2. Wire into AgentLoop**

```python
# agent/agent_loop.py
class AgentLoop:
    def __init__(self, ..., cancellation_token: CancellationToken = None):
        self._cancel_token = cancellation_token

    def run(self, ...):
        while state.iteration < state.max_iterations:
            # Check cancellation at start of each iteration
            if self._cancel_token and self._cancel_token.is_cancelled():
                self._ui.show_warning("Agent cancelled by user")
                return {'success': False, 'result': 'Cancelled', ...}

            # ... rest of loop
```

**3. Add Escape Binding**

```python
# cli/screens/main_screen.py
BINDINGS = [
    Binding("enter", "submit_input", "Submit", priority=True),
    Binding("escape", "cancel_operation", "Cancel", priority=True),
    ...
]

def action_cancel_operation(self):
    """Handle Escape key - cancel running agent."""
    if self._agent_cancel_token:
        self._agent_cancel_token.cancel()
        self.output_adapter.post_output("Cancelling agent...")
```

**4. Pass Token Through**

```
MainScreen
  -> InteractiveMode
    -> CLIAgentManager
      -> CodeAgent
        -> AgentLoop (checks token each iteration)
```

### Files to Modify
1. `agent/cancellation.py` - NEW: CancellationToken class
2. `agent/agent_loop.py` - Check token between iterations
3. `agent/core.py` - Accept and pass token
4. `cli/agent_manager.py` - Create and pass token
5. `cli/screens/main_screen.py` - Escape binding, store token reference

## Decisions (Locked In)

| Question | Decision |
|----------|----------|
| Checkpoint interval | 15 steps |
| Skip prompts flag | Yes - `--no-checkpoint` skips soft checkpoint |
| Status bar text | `Agent working -- Step [x]` |
| Verbose mode toggle | Config option (persistent) |
| Compact thinking | One line summary |
| Compact results | `done (123 lines)` format |
| Dry run prompt | Remove - make opt-in via `--dry-run` flag only |
| Checkpoint prompt | Keep - already works well |

## Implementation Order

1. **Cancellation** (safety first)
   - CancellationToken
   - Wire through to AgentLoop
   - Escape binding
   - Add "Cancelling... waiting for current step" UI feedback

2. **Enhance Audit Logging** (before UI goes dark)

   **Current state:**
   - `AuditLogger.log_action()` captures: timestamp, action, params, result, approved
   - Results truncated to 1000 chars (`max_result_length`)
   - Saved to `~/.scrappy/data/audit.json`

   **Missing:**
   - LLM thinking/reasoning (no way to debug "why did it do that?")
   - Full results (truncated loses context)
   - Token usage per step

   **Changes needed:**
   - Add optional `thinking` param to `log_action()`
   - AgentLoop passes thinking text when available
   - Increase `max_result_length` to 5000 or make configurable
   - Consider: add `tokens_used` field per action

   **Files:**
   - `agent/audit.py` - Add thinking field to log_action()
   - `agent/agent_loop.py` - Pass thinking to audit logger

3. **Compact Output** (biggest UX win)
   - Add verbose flag to AgentUI
   - Modify show_thinking, show_tool_request, show_result
   - Status bar update
   - Show stderr on errors even in compact mode

4. **Remove Hard Step Limit**
   - Remove/raise max_iterations
   - Add soft checkpoint at 15 steps
   - Consider: bump DuplicateDetector lookback 3->5

5. **Cleanup**
   - Config option for verbose mode

6. **Remove Dry Run Prompt** (2 checks is annoying)

   **Current:** Agent asks "Dry run?" before every execution (`agent_manager.py:87-89`)
   ```python
   dry_run = self._interaction.confirm(
       "Run in dry-run mode? (no actual changes)", default=False
   )
   ```

   **Desired:** No prompt. Dry run only via `--dry-run` flag or `/agent --dry-run <task>`

   **Changes:**
   - `cli/agent_manager.py` - Remove prompt, accept `dry_run` as parameter (default False)
   - `cli/command_router.py` - Parse `--dry-run` flag from args, pass to agent_mgr
   - Keep all dry_run logic in agent/tools (just remove the prompt)
