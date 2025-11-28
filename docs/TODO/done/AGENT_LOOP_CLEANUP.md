# Agent Loop Cleanup: Eliminate Inline Tool Hacks

## Problem

`agent_loop.py:207-250` manually appends `run_command` and `complete` tool schemas inline, bypassing the registry:

```python
# Current hack in _delegate_with_tools():
tools = self._tool_registry.to_openai_schema()

# Add run_command tool (not in registry, manual schema)
tools.append({
    "type": "function",
    "function": {
        "name": "run_command",
        ...
    },
})

# Add "complete" tool for task completion
tools.append({
    "type": "function",
    "function": {
        "name": "complete",
        ...
    },
})
```

This violates the principle that the registry should be the single source of truth for tool schemas.

## Current State

| Tool | Class Exists? | Registered in Registry? | Inline Hack? |
|------|---------------|------------------------|--------------|
| `run_command` | Yes - `CommandTool` in `command_tool.py:544` | NO | Yes - `agent_loop.py:207-231` |
| `complete` | NO | NO | Yes - `agent_loop.py:233-250` |

The `CommandTool` class exists but was never registered, so someone added the inline hack as a workaround.

## Completion Flow Analysis

Understanding how completion currently works (and why it might be fragile):

### Two Paths for Tool Discovery

1. **Native tool calling path** (`agent_loop.py:144-148`):
   - Uses `_delegate_with_tools()` which calls `to_openai_schema()`
   - Inline hack appends `complete` tool schema
   - LLM sees `complete` as a callable tool

2. **JSON fallback path** (`agent_loop.py:150-171`):
   - Uses regular `delegate()` with system prompt
   - LLM learns about `complete` from `system_prompt_builder.py:247-253` JSON example
   - No actual tool schema, just format instructions

### Completion Detection Chain

When LLM calls `complete` tool:

1. `NativeToolCallParser.parse()` (`response_parser.py:270`):
   ```python
   is_complete = tool_call.name == "complete"
   ```

2. `ActionExecutor.execute()` (`action_executor.py:83-91`):
   ```python
   if action.action == 'complete':
       return ActionResult(success=True, output=action.result_text, ...)
   ```
   **Note:** This short-circuits before hitting the tool registry. `complete` is never actually "executed" as a tool.

3. `AgentLoop.evaluate()` (`agent_loop.py:338`):
   ```python
   if action.is_complete or action.action == 'complete':
   ```

### Why This Might Cause Completion Issues

- `complete` isn't a real registered tool - it's handled as a special case
- The `stop_loop` metadata pattern (from original TODO) is never actually checked
- If the inline hack is missing/broken, native tool calling path has no `complete` tool
- If system prompt is customized, JSON path might lose the format example
- Fragile: completion logic is scattered across 4 files with string matching

## Solution

### Step 1: Create `CompleteTool` class

**File:** `src/agent_tools/tools/control_tools.py` (new file)

```python
"""
Control tools for agent loop management.

These tools control agent behavior (completion, etc.) rather than
performing actions on the codebase.
"""

from .base import ToolBase, ToolParameter, ToolResult, ToolContext


class CompleteTool(ToolBase):
    """Tool to signal task completion."""

    @property
    def name(self) -> str:
        return "complete"

    @property
    def description(self) -> str:
        return "Mark the task as complete and provide final result."

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("result", str, "Final result or summary of completed task")
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        return ToolResult(True, kwargs["result"], metadata={"stop_loop": True})
```

### Step 2: Update `registry_factory.py`

Register both `CommandTool` and `CompleteTool`:

```python
from .tools.command_tool import CommandTool
from .tools.control_tools import CompleteTool

def create_default_registry(
    include_web: bool = True,
    include_git: bool = True,
    config: Optional["AgentConfig"] = None,  # NEW: needed for CommandTool
) -> ToolRegistry:
    registry = ToolRegistry()

    # ... existing registrations ...

    # Register control tools
    if config:
        registry.register(CommandTool(config))
    registry.register(CompleteTool())

    return registry
```

### Step 3: Clean up `agent_loop.py`

Remove lines 207-250. The method becomes:

```python
def _delegate_with_tools(
    self, provider: str, prompt: str, system_prompt: str
) -> Any:
    """Delegate to orchestrator with native tool calling."""

    # CLEAN: Registry is the single source of truth
    tools = self._tool_registry.to_openai_schema()

    return self._orchestrator.delegate_with_tools(
        provider_name=provider,
        prompt=prompt,
        tools=tools,
        system_prompt=system_prompt,
        max_tokens=self._config.default_max_tokens,
        temperature=self._config.default_temperature,
        tool_choice="auto",
    )
```

### Step 4: Remove static fallback from `system_prompt_builder.py`

Remove the static tool list fallback (lines 225-253). Force registry usage:

```python
def _build_tools_section(self) -> str:
    """Build available tools section."""
    if self.tool_registry is None:
        raise ValueError("ToolRegistry is required - no fallback supported")

    if hasattr(self, '_use_native_tools') and self._use_native_tools:
        return f"\n## Available Tools\n\n{self.tool_registry.generate_descriptions()}"
    else:
        return f"\n## Available Tools\n\n{self.tool_registry.get_full_prompt_section()}"
```

This ensures tool definitions come from ONE source (the registry) regardless of which path is taken.

### Step 5: Update `__init__.py` exports

**File:** `src/agent_tools/tools/__init__.py`

Add export for `CompleteTool`:

```python
from .control_tools import CompleteTool
```

## Files to Modify

| File | Action | Description |
|------|--------|-------------|
| `src/agent_tools/tools/control_tools.py` | CREATE | CompleteTool class |
| `src/agent_tools/registry_factory.py` | EDIT | Add config param, register CommandTool and CompleteTool |
| `src/agent/core.py` | EDIT | Update _create_default_tool_registry() to pass config |
| `src/agent/agent_loop.py` | EDIT | Remove inline schema hacks (lines 207-250), update evaluate() metadata check |
| `src/agent/system_prompt_builder.py` | EDIT | Remove static fallback (lines 225-253) |
| `src/agent_tools/tools/__init__.py` | EDIT | Export CompleteTool |
| `src/agent/types.py` | EDIT | Add metadata field to ActionResult |
| `src/agent/action_executor.py` | EDIT | Remove complete short-circuit (lines 83-91) |
| `src/agent/safety_checker.py` | REVIEW | Verify complete special case still needed/works |

## Architecture Analysis

### Why CommandTool Needs Config

`CommandTool` requires `AgentConfig` because `ShellCommandExecutor` uses:
- `config.command_timeout` - timeout for command execution
- `config.max_command_output` - max output size to capture
- `config.dangerous_commands` - patterns for dangerous commands (security)

Without config, the tool can't enforce security checks or resource limits.

### Why include_web and include_git Flags Exist

These flags enable environment-specific registry creation:
- `include_web=False` - for offline mode (no internet access)
- `include_git=False` - for non-git projects (git tools would fail)

NOT for user permissions - these are context-based optimizations.

### Config Flow is Already Perfect

The dependency injection flow is ideal:

```
CLI → CodeAgent(orchestrator, config=None)
  ↓
  __init__: self.config = config or AgentConfig()  [line 158]
  ↓
  _create_default_tool_registry()  [line 177, 309-311]
  ↓
  create_default_registry(config=self.config)  [CHANGE NEEDED]
  ↓
  CommandTool(config) registered
```

**Key insight:** Config is initialized BEFORE registry (line 158 before 177), so we can safely pass `self.config` to the factory.

**Impact:** Only ONE line needs to change in CodeAgent:

```python
# core.py:309-311 - CHANGE THIS:
def _create_default_tool_registry(self):
    """Create default tool registry."""
    return create_default_registry()

# TO THIS:
def _create_default_tool_registry(self):
    """Create default tool registry."""
    return create_default_registry(config=self.config)
```

All CLI code automatically inherits this change. Tests that call `create_default_registry()` directly without config will simply skip `run_command` registration (fine for unit tests).

## Decisions (All Resolved)

All architectural decisions have been finalized. Implementation can proceed.

### 1. CommandTool config dependency

**RESOLVED:** Make config optional in factory signature.

`CommandTool` requires `AgentConfig` in its constructor. The solution:

```python
def create_default_registry(
    config: Optional["AgentConfig"] = None,  # Optional for backward compat
    include_web: bool = True,
    include_git: bool = True
) -> ToolRegistry:
    # ... register other tools ...

    # Only register CommandTool if config provided
    if config:
        registry.register(CommandTool(config))

    # CompleteTool doesn't need config - always register
    registry.register(CompleteTool())
```

**Why this works:**
- CodeAgent passes `config=self.config` (line 158 ensures it exists)
- Tests without config skip `run_command` registration (acceptable for unit tests)
- No breaking changes to existing test code
- Follows DI principles - explicit dependency injection

### 2. Should `CompleteTool.execute()` actually run?

**RESOLVED:** Option B - Treat `complete` as a real tool, not a special case.

Currently `ActionExecutor` short-circuits at line 83-91 before tool execution. We will remove this special case.

**Why Option B:**
- Removes special-case code from ActionExecutor (follows Single Responsibility Principle)
- Makes completion flow through normal tool execution path
- Allows `stop_loop` metadata to control behavior (cleaner architecture)
- Uniform tool handling (follows SOLID principles - no special cases)
- Easier to test and maintain

**Implementation:**
1. Add to `types.py` ActionResult:
   ```python
   metadata: Dict[str, Any] = field(default_factory=dict)
   ```
2. Remove `action_executor.py:83-91` (the short-circuit for complete)
3. Update `agent_loop.py:evaluate()` to check `result.metadata.get("stop_loop", False)` in addition to existing `action.is_complete` check
4. Keep `action.is_complete` check for backward compatibility during transition
5. Update `ActionResult(...)` instantiations throughout codebase to pass through metadata from tool results

### 3. What about `registry.py:get_response_format()`?

**RESOLVED:** Leave as-is.

This method (lines 140-162) has hardcoded JSON format with `"action": "complete"`. Used for JSON-mode prompts.

**Decision:** Keep the hardcoded format example.
- It's documentation/example format, not the source of truth
- The actual tool schemas come from the registry (which is what matters)
- Dynamically generating examples adds complexity for minimal benefit
- The format is stable and unlikely to change

## Testing

### New tests needed

**File:** `tests/agent_tools/test_control_tools.py`

```python
class TestCompleteTool:
    def test_name(self):
        tool = CompleteTool()
        assert tool.name == "complete"

    def test_execute_returns_stop_loop_metadata(self):
        tool = CompleteTool()
        context = ToolContext(project_root=Path("."))
        result = tool.execute(context, result="Task done")
        assert result.success is True
        assert result.output == "Task done"
        assert result.metadata.get("stop_loop") is True

    def test_registered_in_default_registry(self):
        from src.agent_tools.registry_factory import create_default_registry
        registry = create_default_registry(config=mock_config)
        assert registry.exists("complete")
        assert registry.exists("run_command")

    def test_schema_in_openai_format(self):
        from src.agent_tools.registry_factory import create_default_registry
        registry = create_default_registry(config=mock_config)
        schemas = registry.to_openai_schema()
        names = [s["function"]["name"] for s in schemas]
        assert "complete" in names
        assert "run_command" in names
```

### Run existing tests

```bash
python -m pytest tests/ -v -k "tool"
python -m pytest tests/agent/ -v
python -m pytest tests/test_tool_registry_factory.py -v
```

### Verify

- [ ] `to_openai_schema()` includes both `run_command` and `complete`
- [ ] Agent loop functions correctly with native tool calling
- [ ] No duplicate tool definitions
- [ ] Completion detection works in both native and JSON modes
- [ ] No regressions in existing tests

## Summary

### What We're Fixing

Two tools are currently added via inline hacks instead of being registered:
1. `run_command` - has a class (`CommandTool`) but was never registered because it needs config
2. `complete` - doesn't have a class, is handled as a special case in multiple places

### Root Cause

`CommandTool` needs `AgentConfig` but `create_default_registry()` didn't accept a config parameter. Rather than fixing the architecture, someone added inline schema hacks as a workaround.

### The Fix

**Phase 1: Register the tools properly**
1. Add `config` parameter to `create_default_registry()`
2. Update `CodeAgent._create_default_tool_registry()` to pass `self.config`
3. Create `CompleteTool` class in new `control_tools.py`
4. Register both tools in the factory
5. Remove inline hacks from `agent_loop.py`

**Phase 2: Clean up special cases (if Decision #2 = Option B)**
6. Add `metadata` field to `ActionResult`
7. Remove `complete` short-circuit from `action_executor.py`
8. Update `evaluate()` to check `stop_loop` metadata

**Phase 3: Remove fallbacks**
9. Remove static tool list from `system_prompt_builder.py`

### Impact

- **Zero breaking changes** to CLI or production code
- **Minimal test impact** - tests without config simply won't get `run_command` tool
- **Cleaner architecture** - registry is single source of truth
- **Easier to maintain** - no more special cases scattered across files

### Key Architectural Insight

The app already has perfect dependency flow:
```
CLI → CodeAgent → config → registry → tools
```

We just need to connect the last link by passing config through to the registry factory.

## Implementation Checklist

All decisions resolved. Ready to implement.

### Phase 1: Register Tools Properly
- [ ] Create `src/agent_tools/tools/control_tools.py` with `CompleteTool` class
- [ ] Update `src/agent_tools/tools/__init__.py` to export `CompleteTool`
- [ ] Update `src/agent_tools/registry_factory.py`:
  - [ ] Add `config: Optional["AgentConfig"] = None` parameter
  - [ ] Import `CommandTool` and `CompleteTool`
  - [ ] Register `CommandTool(config)` if config provided
  - [ ] Register `CompleteTool()` always
- [ ] Update `src/agent/core.py:309-311` to pass `config=self.config`
- [ ] Remove inline hacks from `src/agent/agent_loop.py:207-250`

### Phase 2: Clean Up Special Cases
- [ ] Add `metadata: Dict[str, Any] = field(default_factory=dict)` to `src/agent/types.py` ActionResult
- [ ] Remove short-circuit from `src/agent/action_executor.py:83-91`
- [ ] Update `src/agent/agent_loop.py` evaluate() to check `result.metadata.get("stop_loop", False)`
- [ ] Update all `ActionResult(...)` calls to pass through metadata

### Phase 3: Remove Fallbacks
- [ ] Remove static tool list from `src/agent/system_prompt_builder.py:225-253`
- [ ] Review `src/agent/safety_checker.py:64` - verify complete special case handling

### Testing
- [ ] Create `tests/agent_tools/test_control_tools.py` with CompleteTool tests
- [ ] Run `python -m pytest tests/test_tool_registry_factory.py -v`
- [ ] Run `python -m pytest tests/agent/ -v`
- [ ] Run `python -m pytest tests/ -v -k "tool"`
- [ ] Verify `to_openai_schema()` includes `run_command` and `complete`
- [ ] Verify agent loop completes tasks correctly
- [ ] Verify no regressions
