# Spike: Confirmation UX Architecture

**Bead**: scrappy-63w1
**Blocks**: scrappy-jzws (P0), scrappy-mnhv (P1)
**Status**: Investigation complete

## Problem Statement

Two related UX bugs:
1. **scrappy-jzws (P0)**: Tool info not displayed before Y/N/A confirmation prompt
2. **scrappy-mnhv (P1)**: No diff preview shown before file write confirmation

User sees only status bar prompt "Write to file.py?" with no context about what's being written.

## Current Architecture

```
ToolAdapter._execute_single()
  └─> confirm_callback(tool_name, description)  # "write_file", "Write to test.py"
        └─> LangGraphBridge._tool_confirm_callback()
              └─> blocking_confirm_yna(question)  # Shows Y/N/A in status bar
                    └─> User responds
        └─> Tool executes
        └─> _output_tool_executions()  # Tool info + diff shown AFTER execution
```

**Root cause**: Display happens after execution, confirmation happens before.

## Prior Art

The deleted `src/scrappy/agent/` had this solved:

- `action_executor._generate_diff_preview()` - uses `difflib.unified_diff`
- `ui.show_diff_preview()` - displays colored diff before confirmation
- Flow: generate diff -> show preview -> prompt Y/N/A -> execute

## Architectural Options

### Option A: Expand ConfirmCallback signature (Quick fix)

Add args to callback, display in `_tool_confirm_callback`:

```python
ConfirmCallback = Callable[[str, str, dict[str, Any]], bool]
# (tool_name, description, args) -> confirmed
```

**Pros**: Minimal change, works
**Cons**: Adds ~100 lines to already-1000-line langgraph_bridge.py, mixing concerns

### Option B: Confirmation UI Protocol (Recommended)

Extract confirmation display to dedicated component:

```python
class ToolConfirmationUI(Protocol):
    def show_tool_preview(self, tool_name: str, args: dict) -> None: ...
    def show_diff_preview(self, path: str, diff_lines: list[str]) -> None: ...
    def prompt_yna(self, question: str) -> str: ...

class ToolConfirmationHandler:
    def __init__(self, ui: ToolConfirmationUI, working_dir: str): ...

    def confirm_tool(self, tool_name: str, args: dict) -> bool:
        self.ui.show_tool_preview(tool_name, args)
        if tool_name in FILE_WRITE_TOOLS:
            diff = self._generate_diff(args)
            self.ui.show_diff_preview(path, diff)
        return self.ui.prompt_yna(f"{description}?") in ("y", "a")
```

**Pros**:
- Single responsibility
- Testable in isolation
- Reusable across UI backends
- Keeps langgraph_bridge focused on orchestration

**Cons**: More files, slight indirection

### Option C: Move to ToolAdapter (Alternative)

Let ToolAdapter handle display before calling confirm callback:

```python
class ToolAdapter:
    def __init__(self, registry, display_callback, confirm_callback): ...

    def _execute_single(self, tool_call, context):
        # Display first
        self._display_callback(tool_name, args, self._generate_diff(args))
        # Then confirm
        if not self._confirm_callback(question):
            return denied_result
```

**Pros**: Display logic near the data
**Cons**: ToolAdapter becomes UI-aware, harder to test

## Recommendation

**Option B: ToolConfirmationHandler**

New file: `src/scrappy/cli/textual/tool_confirmation.py`

```
src/scrappy/cli/textual/
  tool_confirmation.py      # NEW: ToolConfirmationHandler + protocol
  langgraph_bridge.py       # Uses ToolConfirmationHandler
```

Changes:
1. Create `ToolConfirmationHandler` with `confirm_tool()` method
2. Move diff generation logic from old agent code
3. LangGraphBridge instantiates handler, passes to ToolAdapter
4. ToolAdapter callback signature unchanged (handler wraps it)

## Implementation Plan

1. Create `tool_confirmation.py` with:
   - `ToolConfirmationUI` protocol
   - `ToolConfirmationHandler` class
   - `_generate_diff_preview()` method (from old agent)
   - `_show_diff_preview()` method (from old agent)

2. Create `TextualConfirmationUI` implementation using output_adapter

3. Update `LangGraphBridge`:
   - Instantiate `ToolConfirmationHandler`
   - Replace `_tool_confirm_callback` with handler.confirm_tool

4. Update tests

## Estimated Scope

- New file: ~150 lines
- LangGraphBridge changes: -30 lines (remove inline callback)
- Tests: ~50 lines
