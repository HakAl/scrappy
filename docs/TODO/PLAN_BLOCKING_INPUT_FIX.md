# Plan: Fix Blocking Input Calls for Textual UI

## Problem Statement

The Textual app freezes when processing certain inputs because code paths contain direct `input()` calls that block forever in worker threads. Since Textual is the primary UI (not CLI), all input handling must be non-blocking and route through the established IO protocol architecture.

## Root Cause Analysis

### Identified Blocking Calls

1. **TaskRouter._should_execute()** (`src/task_router/router.py:496`)
   ```python
   response = input("  Execute? [y/N]: ").strip().lower()
   ```
   Called when `DIRECT_COMMAND` tasks require confirmation.

2. **InteractiveClarifier.clarify()** (`src/task_router/intent_clarifier.py:80`)
   ```python
   choice = self.input_fn("\nChoice [1/2/3]: ").strip()
   ```
   Called when task classification has low confidence (< 0.65). Default `input_fn` is `builtins.input`.

### Why These Are Problematic

- Textual runs its event loop on the main thread
- User commands are processed in `@work(thread=True)` worker threads
- Worker threads calling `input()` block forever waiting for stdin
- Textual's Input widget handles stdin, not Python's `input()`

### Execution Flow That Triggers Hang

```
User types in Textual Input widget
    |
    v
on_input_submitted() clears input, calls process_command()
    |
    v
@work(thread=True) process_command() - worker thread
    |
    v
InteractiveMode._process_input()
    |
    v
task_router.handle_auto_route() [if auto_route_mode or needs_tool_support]
    |
    v
TaskRouter.route()
    |
    v
_classify_with_llm() [if low confidence] - calls orchestrator.delegate() - WORKS
    |
    v
_clarify_intent() [if still low confidence]
    |
    v
InteractiveClarifier.clarify() - calls input() - HANGS FOREVER
```

---

## Architectural Principles

### 1. All Input MUST Go Through CLIIOProtocol

The existing architecture has a clean protocol for input:
- `CLIIOProtocol.prompt()` - text input
- `CLIIOProtocol.confirm()` - yes/no confirmation
- `CLIIOProtocol.input_line()` - raw line input

These are already correctly implemented in `UnifiedIO` with Textual support via `OutputSinkAdapter` which auto-approves with warnings.

### 2. No Direct `input()` Calls in Business Logic

Any component that might run in Textual mode must:
- Accept an IO protocol via dependency injection
- Use `io.prompt()` / `io.confirm()` instead of `input()`
- Never assume stdin is available

### 3. Protocol-Based Input for Task Router Components

The `TaskRouter` and its collaborators need an `InputProtocol` injected that:
- Matches the CLIIOProtocol input methods
- Can be satisfied by `UnifiedIO` in production
- Can be mocked in tests

---

## Implementation Plan

### Phase 1: Define InputProtocol for Task Router

**File:** `src/task_router/protocols.py` (new or extend existing)

Create a minimal protocol that task router components need:

```python
class TaskRouterInputProtocol(Protocol):
    """Protocol for user input in task router components."""

    def prompt(self, text: str, default: str = "") -> str:
        """Get text input from user."""
        ...

    def confirm(self, text: str, default: bool = False) -> bool:
        """Get yes/no confirmation from user."""
        ...

    def output(self, message: str) -> None:
        """Output a message to user."""
        ...
```

This is deliberately minimal - just what the task router needs.

### Phase 2: Refactor IntentClarifier

**File:** `src/task_router/intent_clarifier.py`

#### 2.1 Update InteractiveClarifier to use protocol

```python
class InteractiveClarifier(IntentClarifierInterface):
    def __init__(self, io: Optional[TaskRouterInputProtocol] = None):
        """
        Initialize interactive clarifier.

        Args:
            io: Input protocol for user interaction. If None, creates
                a default console-based implementation (for backwards
                compatibility with non-Textual usage).
        """
        self._io = io or _DefaultConsoleInput()

    def clarify(self, task: ClassifiedTask) -> ClassifiedTask:
        self._io.output(f"\nIntent Clarification Needed")
        self._io.output(f"   Classified as: {task.task_type.value} ...")
        # ... display options ...

        try:
            choice = self._io.prompt("\nChoice [1/2/3]: ", default="3")
        except (EOFError, KeyboardInterrupt):
            return task

        # ... handle choice ...
```

#### 2.2 Create default console implementation (fallback)

```python
class _DefaultConsoleInput:
    """Fallback input for non-Textual contexts (one-shot commands)."""

    def prompt(self, text: str, default: str = "") -> str:
        try:
            result = input(text)
            return result if result else default
        except EOFError:
            return default

    def confirm(self, text: str, default: bool = False) -> bool:
        try:
            result = input(f"{text} [y/N]: ").strip().lower()
            return result in ('y', 'yes')
        except EOFError:
            return default

    def output(self, message: str) -> None:
        print(message)
```

### Phase 3: Refactor TaskRouter._should_execute()

**File:** `src/task_router/router.py`

#### 3.1 Add input protocol to TaskRouter

```python
class TaskRouter:
    def __init__(
        self,
        orchestrator: Optional[OrchestratorLike] = None,
        project_root: Optional[Path] = None,
        auto_confirm_direct: bool = False,
        verbose: bool = True,
        intent_clarifier: Optional[IntentClarifierInterface] = None,
        output_handler: Optional[OutputHandlerInterface] = None,
        input_handler: Optional[TaskRouterInputProtocol] = None,  # NEW
        # ... rest of params ...
    ):
        # ...
        self._input_handler = input_handler or _DefaultConsoleInput()
```

#### 3.2 Update _should_execute()

```python
def _should_execute(self, task: ClassifiedTask, strategy: ExecutionStrategy) -> bool:
    # ... existing logic ...

    if action == "confirm":
        if self.verbose:
            self.output_handler.log_info(f"Command: {task.extracted_command}")

        # Use injected input handler instead of direct input()
        return self._input_handler.confirm(
            f"Execute '{task.extracted_command}'?",
            default=False
        )

    return True
```

### Phase 4: Update CLITaskRouterHandler Factory

**File:** `src/cli/task_router_handler.py`

Create adapter and inject into TaskRouter:

```python
class CLIIOInputAdapter:
    """Adapts CLIIOProtocol to TaskRouterInputProtocol."""

    def __init__(self, io: CLIIOProtocol):
        self._io = io

    def prompt(self, text: str, default: str = "") -> str:
        return self._io.prompt(text, default=default)

    def confirm(self, text: str, default: bool = False) -> bool:
        return self._io.confirm(text, default=default)

    def output(self, message: str) -> None:
        self._io.echo(message)


class CLITaskRouterHandler:
    def _create_default_router(self) -> TaskRouter:
        from src.task_router import CLIIOOutputHandler, InteractiveClarifier

        # Create input adapter that routes through UnifiedIO
        input_adapter = CLIIOInputAdapter(self.io)

        return TaskRouter(
            orchestrator=self.orchestrator,
            project_root=self.project_root,
            auto_confirm_direct=self.auto_confirm,
            verbose=True,
            output_handler=CLIIOOutputHandler(self.io),
            input_handler=input_adapter,  # NEW
            intent_clarifier=InteractiveClarifier(io=input_adapter),  # Pass io
        )
```

### Phase 5: Update Tests

**Files:**
- `tests/task_router/test_intent_clarifier.py`
- `tests/task_router/test_task_router.py`

Tests already use mocks for the clarifier, but need to verify:
1. `InteractiveClarifier` works with injected IO
2. `TaskRouter._should_execute()` uses injected input handler
3. No direct `input()` calls remain in testable paths

### Phase 6: Audit for Other Blocking Calls

Search for remaining direct `input()` calls:
- `src/cli/output.py:312` - In `RichOutput.prompt()` - OK, this IS the IO layer
- `src/cli/output.py:142` - In `ConsoleOutput.input_line()` - OK, this IS the IO layer
- `src/cli/unified_io.py:506,521` - In `DirectConsoleOutput` - OK, only used in non-Textual mode

These are all in the IO layer itself, which is correct.

---

## File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `src/task_router/protocols.py` | Create/Extend | Add `TaskRouterInputProtocol` |
| `src/task_router/intent_clarifier.py` | Modify | Inject IO protocol, remove direct `input()` |
| `src/task_router/router.py` | Modify | Add `input_handler` param, fix `_should_execute()` |
| `src/cli/task_router_handler.py` | Modify | Add `CLIIOInputAdapter`, inject into router |
| `tests/task_router/test_intent_clarifier.py` | Modify | Test with mock IO |
| `tests/task_router/test_task_router.py` | Modify | Test input handler injection |

---

## Behavioral Changes

### Before (Broken)
- Low confidence task -> `InteractiveClarifier` calls `input()` -> **HANG**
- Direct command needing confirmation -> `input()` -> **HANG**

### After (Fixed)
- Low confidence task -> `InteractiveClarifier` calls `io.prompt()` -> `UnifiedIO` -> `OutputSinkAdapter.input_prompt()` -> auto-approve with warning panel -> **WORKS**
- Direct command needing confirmation -> `io.confirm()` -> `UnifiedIO` -> `OutputSinkAdapter.input_confirm()` -> auto-approve with warning panel -> **WORKS**

### Phase 1 Behavior (Current UnifiedIO)
The existing `OutputSinkAdapter` already handles input requests by:
1. Posting a warning panel explaining the auto-approval
2. Returning the default value immediately

This is documented as "Phase 1 Limitation" in the code. Future phases can add modal dialogs for true user interaction.

---

## Testing Strategy

### Unit Tests
1. `InteractiveClarifier` with mock IO returns correct task types
2. `TaskRouter._should_execute()` with mock IO confirms/denies correctly
3. No hanging in any code path

### Integration Tests
1. `CLITaskRouterHandler` creates router with correct input adapter
2. End-to-end: Textual app processes low-confidence task without hanging
3. End-to-end: Direct command confirmation flows through UI

### Manual Testing
1. Start Textual app
2. Type ambiguous query that triggers intent clarification
3. Verify warning panel appears, no hang
4. Type direct command (e.g., "run ls")
5. Verify confirmation warning panel appears, command executes

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking non-Textual usage | Medium | Default implementations fall back to console `input()` |
| Tests that rely on mock `input()` | Low | Tests should mock the IO protocol, not builtins |
| Missing other blocking calls | High | Audit via grep, add tests that timeout on blocking |
| Auto-approve is too permissive | Medium | Existing behavior - Phase 3 will add proper dialogs |

---

## Success Criteria

1. No `input()` calls in `src/task_router/` except in fallback `_DefaultConsoleInput`
2. Textual app never hangs on any user input
3. All existing tests pass
4. New tests verify IO protocol injection
5. Warning panels appear for auto-approved confirmations

---

## Future Work (Out of Scope)

- **Phase 3 Modal Dialogs**: Replace auto-approve with actual Textual modal screens
- **Async Input Methods**: Non-blocking input that waits for user response
- **Input Request Queue**: Bi-directional communication between worker and UI threads

These require more significant architectural changes and are tracked separately.
