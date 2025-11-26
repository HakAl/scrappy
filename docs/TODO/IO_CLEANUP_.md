# IO Injection Cleanup - Deadlock Risk Analysis

## Overview

During the fix for `AGENT_BUG_CLEANUP.md`, a codebase scan revealed additional sites where `CodeAgent` is instantiated without the bridged `io` instance. This document catalogs these findings for future cleanup.

---

## Root Cause Pattern

When `CodeAgent` is created without an `io` parameter, it falls back to creating a new `UnifiedIO()` instance (via `_create_default_io()`). In TUI mode, this new instance is unbridged - it has no `OutputSink` connection to the Textual UI. When the agent requests user confirmation for tool execution, the unbridged io blocks waiting for console input that will never come, causing a deadlock.

---

## Findings

### 1. `src/task_router/strategies/agent_executor.py:67`

**Risk Level:** MEDIUM

**Code:**
```python
agent = CodeAgent(
    orchestrator=adapter,
    project_path=str(self.project_root)
)
```

**Problem:**
- `AgentExecutor` creates `CodeAgent` without `io`
- `AgentExecutor` itself doesn't receive `io` in its constructor
- `TaskRouter` creates `AgentExecutor` without `io` (line 173 in `router.py`)
- If a task is routed to `CODE_GENERATION` via TUI, and `require_approval=True` (default), deadlock occurs

**Call Chain:**
```
TUI Mode
  -> CLITaskRouterHandler.handle_auto_route()
     -> TaskRouter.route()
        -> AgentExecutor.execute()      # No io in AgentExecutor
           -> CodeAgent(orchestrator)   # No io - creates unbridged RichIO
              -> agent.run()
                 -> ActionExecutor needs approval
                    -> self.ui.prompt_confirm()
                       -> self.io.confirm()  # DEADLOCK
```

**Fix Required:**
1. Add `io: Optional[CLIIOProtocol] = None` to `AgentExecutor.__init__`
2. Store and pass `io` to `CodeAgent` in `AgentExecutor.execute()`
3. Add `io` parameter to `TaskRouter.__init__`
4. Pass `io` when `TaskRouter` creates `AgentExecutor` in `_create_default_strategies()`
5. Pass `io` from `CLITaskRouterHandler` to `TaskRouter`

---

### 2. `src/cli/smart_query.py:123`

**Risk Level:** LOW

**Code:**
```python
agent = CodeAgent(self.orchestrator)
```

**Problem:**
- Creates `CodeAgent` without `io`
- `CLISmartQuery` has `io` available via `self.display`

**Mitigating Factors:**
- This agent is used for read-only research operations
- It does NOT call `agent.run()` - only uses tools for data gathering
- The handlers call `handler.execute(agent, classification, io)` which uses agent tools directly
- No approval loop is triggered

**Recommendation:**
- Low priority, but should still pass `io` for consistency and future safety
- Simple fix: `agent = CodeAgent(self.orchestrator, io=self.display.get_io())`

---

### 3. `src/cli/commands.py:457`

**Risk Level:** NONE

**Code:**
```python
code_agent = CodeAgent(orchestrator)
```

**Mitigating Factors:**
- This is the CLI-only `scrappy agent` command
- Lines 438-441 explicitly block interactive mode:
  ```python
  if not auto_confirm and not dry_run:
      click.secho("Error: Agent command requires --auto-confirm or --dry-run in one-off mode", fg="red")
      click.echo("For interactive approvals, use: scrappy (then /agent <task>)")
      sys.exit(1)
  ```
- Never runs in TUI mode
- Uses `click.echo()` directly (not the io abstraction)

**Recommendation:**
- No fix needed - intentionally CLI-only with explicit safeguards

---

## Priority Order

| Priority | Location | Effort | Risk if Unfixed |
|----------|----------|--------|-----------------|
| 1 | `agent_executor.py` | Medium (multi-file) | Deadlock on `/auto` command in TUI |
| 2 | `smart_query.py` | Low (one line) | Theoretical future risk |
| 3 | `commands.py` | None | No risk - by design |

---

## Implementation Plan for AgentExecutor Fix

### Phase 1: Add io to AgentExecutor

**File:** `src/task_router/strategies/agent_executor.py`

```python
class AgentExecutor(ProviderAwareStrategy):
    def __init__(
        self,
        orchestrator: OrchestratorLike,
        project_root: Optional[Path] = None,
        max_iterations: int = 10,
        require_approval: bool = True,
        io: Optional[Any] = None,  # Add this
    ):
        super().__init__(orchestrator)
        self.project_root = project_root or Path.cwd()
        self.max_iterations = max_iterations
        self.require_approval = require_approval
        self.io = io  # Store it

    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        # ...
        agent = CodeAgent(
            orchestrator=adapter,
            project_path=str(self.project_root),
            io=self.io,  # Pass it
        )
```

### Phase 2: Add io to TaskRouter

**File:** `src/task_router/router.py`

```python
class TaskRouter:
    def __init__(
        self,
        orchestrator: Optional[OrchestratorLike] = None,
        project_root: Optional[Path] = None,
        # ... existing params ...
        io: Optional[Any] = None,  # Add this
    ):
        self.io = io
        # ...

    def _create_default_strategies(self) -> Dict[TaskType, ExecutionStrategyProtocol]:
        # ...
        strategies[TaskType.CODE_GENERATION] = AgentExecutor(
            orchestrator=self.orchestrator,
            project_root=self.project_root,
            max_iterations=10,
            require_approval=True,
            io=self.io,  # Pass it
        )
```

### Phase 3: Pass io from CLITaskRouterHandler

**File:** `src/cli/task_router_handler.py`

```python
def _create_default_router(self) -> TaskRouter:
    # ...
    return TaskRouter(
        orchestrator=self.orchestrator,
        project_root=self.project_root,
        # ... existing params ...
        io=self.io,  # Add this
    )
```

---

## Testing After Fix

1. Launch TUI: `python -m src.cli --tui`
2. Run `/auto "create a hello world function"` (should route to CODE_GENERATION)
3. Verify modal dialogs appear for tool approvals
4. Verify no deadlock occurs

---

## Related Files

- `src/cli/agent_manager.py` - FIXED in AGENT_BUG_CLEANUP.md
- `src/task_router/strategies/agent_executor.py` - Needs fix
- `src/task_router/router.py` - Needs fix
- `src/cli/task_router_handler.py` - Needs fix
- `src/cli/smart_query.py` - Low priority fix
- `src/cli/commands.py` - No fix needed
