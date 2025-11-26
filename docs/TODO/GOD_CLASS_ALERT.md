# God Class Refactoring Plan

## Current State Analysis

| File | Lines | Status | Priority |
|------|-------|--------|----------|
| `src/agent/core.py` | 766 | REFACTORED (was 1107) | DONE |
| `src/context/codebase_context.py` | 960 | NEEDS REFACTOR | MEDIUM |
| `src/orchestrator/core.py` | 779 | ALREADY REFACTORED | LOW |
| `src/task_router/router.py` | 581 | ACCEPTABLE | LOW |

### Key Finding: Orchestrator is Already Well-Structured

The `AgentOrchestrator` (779 lines) is **not a god class** - it's actually a well-designed facade:
- Uses dependency injection via protocols
- Has `OrchestratorFactory` for component creation
- Delegates to focused components: `DelegationManager`, `TaskExecutor`, `ContextCoordinator`, etc.
- Most methods are thin wrappers delegating to injected dependencies

**No further refactoring needed for orchestrator.**

---

## Priority 1: CodeAgent Refactoring (src/agent/core.py)

### Current Problems

The `CodeAgent` class (1107 lines) violates Single Responsibility:

1. **Provider Selection Logic** (lines 215-266)
   - Mixed with initialization
   - Complex conditional logic for dynamic vs static selection
   - Should be extracted to `ProviderSelectionStrategy`

2. **Command Execution** (lines 381-465)
   - `_tool_run_command` handles interactive mode detection
   - `_run_command_interactive` is agent-specific but mixed with tool execution
   - Should delegate more to `ShellCommandExecutor`

3. **Agent Loop Stages** (lines 563-1058)
   - `_think`, `_plan_action`, `_execute`, `_evaluate`, `_update_conversation`
   - These are well-separated but live in one massive class
   - Could be extracted to `AgentLoop` coordinator

4. **Backward Compatibility Wrappers** (lines 481-560)
   - 10+ wrapper methods that just delegate to `self.ui`
   - These add noise but are needed for backward compat

### Refactoring Plan

#### Phase 1: Extract AgentLoop (Highest Impact)

Create `src/agent/agent_loop.py`:

```python
# Protocol first
class AgentLoopProtocol(Protocol):
    """Coordinates the think-plan-execute-evaluate cycle."""

    def run(self, task: str, state: ConversationState) -> EvaluationResult: ...
    def think(self, state: ConversationState) -> AgentThought: ...
    def plan(self, thought: AgentThought) -> AgentAction: ...
    def execute(self, action: AgentAction, state: ConversationState) -> ActionResult: ...
    def evaluate(self, action: AgentAction, result: ActionResult, state: ConversationState) -> EvaluationResult: ...


class AgentLoop:
    """
    Coordinates the agent's think-plan-execute-evaluate cycle.

    Single Responsibility: Run the agent loop, nothing else.
    """

    def __init__(
        self,
        orchestrator: OrchestratorAdapter,
        action_executor: ActionExecutorProtocol,
        response_parser: ResponseParserProtocol,
        ui: AgentUIProtocol,
        tool_registry: ToolRegistryProtocol,
        config: AgentConfig,
    ):
        self._orchestrator = orchestrator
        self._action_executor = action_executor
        self._response_parser = response_parser
        self._ui = ui
        self._tool_registry = tool_registry
        self._config = config
```

**Benefits:**
- `CodeAgent.__init__` drops from 200 lines to ~50 lines
- Agent loop logic is testable in isolation
- Clear separation of initialization vs execution

#### Phase 2: Extract ProviderSelectionStrategy

Create `src/agent/provider_strategy.py`:

```python
class ProviderSelectionStrategyProtocol(Protocol):
    """Strategy for selecting LLM providers for agent tasks."""

    def get_planner(self) -> Optional[str]: ...
    def get_executor(self) -> Optional[str]: ...
    def supports_dynamic_selection(self) -> bool: ...


class DynamicProviderStrategy:
    """Uses orchestrator's rate-limit-aware selection."""

    def __init__(self, orchestrator: OrchestratorAdapter):
        self._orchestrator = orchestrator

    def get_planner(self) -> Optional[str]:
        return self._orchestrator.get_recommended_provider('planning')

    def get_executor(self) -> Optional[str]:
        return self._orchestrator.get_recommended_provider('execution')

    def supports_dynamic_selection(self) -> bool:
        return True


class StaticProviderStrategy:
    """Uses fixed provider preferences from config."""

    def __init__(self, config: AgentConfig, available_providers: list[str]):
        self._config = config
        self._available = available_providers

    def get_planner(self) -> Optional[str]:
        for pref in self._config.planner_preferences:
            if pref in self._available:
                return pref
        return self._available[0] if self._available else None
```

**Benefits:**
- Removes 50 lines of conditional logic from `__init__`
- Provider selection is testable independently
- Easy to add new strategies (e.g., cost-optimized)

#### Phase 3: Consolidate Interactive Command Handling

Move to `src/agent_tools/tools/command_tool.py`:

```python
class InteractiveCommandHandler:
    """Handles interactive command detection and execution."""

    def __init__(self, config: AgentConfig, ui: AgentUIProtocol):
        self._config = config
        self._ui = ui

    def is_interactive(self, command: str) -> bool:
        cmd_lower = command.lower()
        return any(p in cmd_lower for p in self._config.interactive_commands)

    def run_interactive(self, command: str, cwd: Path) -> str:
        # Current _run_command_interactive logic
        ...

    def suggest_workaround(self, command: str) -> Optional[str]:
        if 'npx' in command.lower():
            return "Add '-y' flag to skip prompts: npx -y ..."
        return None
```

**Benefits:**
- Interactive command logic moves to where command execution lives
- `CodeAgent._tool_run_command` becomes a thin wrapper
- Removes ~80 lines from CodeAgent

#### Phase 4: Remove Backward Compatibility Wrappers

Current state:
```python
def _show_thinking(self, text: str) -> None:
    self.ui.show_thinking(text)

def _show_tool_request(self, tool_name: str, params: dict) -> None:
    self.ui.show_tool_request(tool_name, params)
# ... 8 more identical wrappers
```

Options:
1. **Keep as-is** - They're small and document the interface
2. **Remove and update callers** - Search for `agent._show_*` and replace with `agent.ui.show_*`
3. **Use `__getattr__`** - Dynamic delegation (adds complexity)

**Recommendation:** Keep for now. They're only ~40 lines and provide backward compat.

### Final CodeAgent Structure (After Refactoring)

```
src/agent/
  core.py              # CodeAgent: ~400 lines (down from 1107)
  agent_loop.py        # AgentLoop: ~300 lines (extracted)
  provider_strategy.py # Provider selection: ~100 lines (extracted)
  protocols.py         # Add new protocols

src/agent_tools/tools/
  command_tool.py      # + InteractiveCommandHandler: ~100 lines
```

---

## Priority 2: CodebaseContext Refactoring (src/context/codebase_context.py)

## NEW CHANGES TO CONSIDER
EVENT QUEUE
EVENT CALLBACK / HANDLERS event_queue , _handle_semantic_event, process_background_events etc

### Current Problems

The `CodebaseContext` class (960 lines) has multiple responsibilities:

1. **File Scanning** - Delegates to `FileScanner` (good)
2. **Semantic Search Management** (lines 207-278, 589-714)
   - Complex background initialization
   - Lazy indexing
   - Progress callbacks
   - ~200 lines that could be extracted

3. **Context Augmentation** (lines 410-468)
   - `augment_prompt` - builds context blocks
   - Could be `ContextAugmenter` class

4. **Project Detection** - Delegates to `ProjectDetector` (good)

### Refactoring Plan

#### Phase 1: Extract SemanticSearchManager

Create `src/context/semantic_manager.py`:

```python
class SemanticSearchManagerProtocol(Protocol):
    """Manages semantic search lifecycle."""

    def start_background_init(self) -> None: ...
    def is_ready(self) -> bool: ...
    def get_status(self) -> Optional[str]: ...
    def search(self, query: str, max_tokens: int) -> Optional[SearchResult]: ...
    def index_files(self, file_collector: FileCollectorProtocol) -> None: ...


class SemanticSearchManager:
    """
    Manages semantic search initialization and indexing.

    Single Responsibility: Coordinate semantic search lifecycle.
    """

    def __init__(
        self,
        project_path: Path,
        initializer: Optional[BackgroundInitializerProtocol] = None,
        file_collector: Optional[FileCollectorProtocol] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ):
        self._project_path = project_path
        self._initializer = initializer
        self._file_collector = file_collector
        self._progress_callback = progress_callback
        self._search_provider = None
```

**Benefits:**
- Removes ~200 lines from CodebaseContext
- Semantic search is testable independently
- Clearer separation of concerns

#### Phase 2: Extract ContextAugmenter

Create `src/context/augmenter.py`:

```python
class ContextAugmenterProtocol(Protocol):
    """Augments prompts with codebase context."""

    def augment(self, prompt: str, include_files: bool = False) -> str: ...
    def get_relevant_context(self, query: str, max_tokens: int) -> str: ...


class ContextAugmenter:
    """
    Builds context blocks for prompt augmentation.

    Single Responsibility: Format context for prompts.
    """

    def __init__(
        self,
        summary_provider: Callable[[], Optional[str]],
        structure_provider: Callable[[], dict],
        git_history_provider: Callable[[], dict],
        file_index_provider: Callable[[], dict],
        semantic_search: Optional[SemanticSearchManagerProtocol] = None,
    ):
        ...
```

**Benefits:**
- Context formatting logic is isolated
- Easy to add new context sources
- Removes ~100 lines from CodebaseContext

### Final CodebaseContext Structure

```
src/context/
  codebase_context.py  # ~600 lines (down from 960)
  semantic_manager.py  # ~200 lines (extracted)
  augmenter.py         # ~150 lines (extracted)
```

---

## Priority 3: TaskRouter (src/task_router/router.py)

### Assessment: ACCEPTABLE

At 581 lines, `TaskRouter` is reasonable for its complexity:

- Uses dependency injection (protocols for all dependencies)
- Delegates to strategies (`DirectExecutor`, `AgentExecutor`, etc.)
- Uses pure functions for calculation logic
- Has injected `output_handler`, `input_handler`, `validator`, etc.

**Minor improvements possible but not urgent:**

1. `_classify_with_llm` (lines 228-353) could be extracted to `LLMClassifier`
2. But it's only ~125 lines and tightly coupled to classification

**Recommendation:** No immediate refactoring needed.

---

## Implementation Order

### Sprint 1: CodeAgent Core Extraction (Highest Impact) - COMPLETED 2025-11-26

1. **Create protocols first** - DONE
   - `AgentLoopProtocol` - added to `src/agent/protocols.py`
   - `ProviderSelectionStrategyProtocol` - added to `src/agent/protocols.py`

2. **Extract `AgentLoop`** - DONE
   - Created `src/agent/agent_loop.py` (~450 lines)
   - Moved `_think`, `_plan_action`, `_execute`, `_evaluate`, `_update_conversation`
   - Updated `CodeAgent.run()` to delegate to `AgentLoop`
   - Original methods kept as backward-compatibility wrappers

3. **Extract `ProviderSelectionStrategy`** - DONE
   - Created `src/agent/provider_strategy.py` (~100 lines)
   - `DynamicProviderStrategy` - rate-limit-aware selection via orchestrator
   - `StaticProviderStrategy` - fixed provider preferences from config
   - `create_provider_strategy()` factory function

4. **Write tests for extracted components** - DONE
   - `tests/agent/test_agent_loop.py` - 13 tests
   - `tests/agent/test_provider_strategy.py` - 13 tests
   - All 26 tests passing

**Results:**
- `src/agent/core.py`: 1107 lines -> 766 lines (31% reduction)
- Full backward compatibility maintained
- All existing tests continue to pass

### Sprint 2: CodebaseContext Cleanup

1. **Extract `SemanticSearchManager`**
   - Move background init, indexing, search coordination

2. **Extract `ContextAugmenter`**
   - Move `augment_prompt` and `get_relevant_context`

3. **Update tests**

### Sprint 3: Minor Cleanups (If Time Permits)

1. Move `InteractiveCommandHandler` to command_tool.py
2. Review other files in the list for quick wins

---

## Files NOT Requiring Refactoring

These files were listed but are acceptable:

| File | Lines | Why Acceptable |
|------|-------|----------------|
| `src/orchestrator/core.py` | 779 | Already uses DI, protocols, factory |
| `src/orchestrator/cache.py` | ~200 | Focused responsibility |
| `src/orchestrator/rate_limiting/tracker.py` | ~300 | Single purpose |
| `src/task_router/router.py` | 581 | Well-structured with DI |
| `src/cli/exceptions.py` | ~100 | Just exception definitions |
| `src/cli/output.py` | ~200 | Output formatting |
| `src/cli/rich_output.py` | ~300 | Rich-specific output |
| `src/platform/fallback.py` | ~150 | Platform fallbacks |
| `src/platform/translation.py` | ~200 | Command translation |

---

## Success Metrics

### Completed (Sprint 1):

| File | Before | After | Reduction |
|------|--------|-------|-----------|
| `src/agent/core.py` | 1107 | 766 | 31% |

New files created:
- `src/agent/agent_loop.py` (450 lines)
- `src/agent/provider_strategy.py` (100 lines)

New tests created:
- `tests/agent/test_agent_loop.py` (13 tests)
- `tests/agent/test_provider_strategy.py` (13 tests)

### Planned (Sprint 2):

| File | Before | After | Reduction |
|------|--------|-------|-----------|
| `src/context/codebase_context.py` | 960 | ~600 | 37% |

Files to create:
- `src/context/semantic_manager.py` (~200 lines)
- `src/context/augmenter.py` (~150 lines)

**Key benefit:** Each class has a single responsibility and is independently testable.
