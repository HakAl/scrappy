# AgentRunContext Design Document

**Status**: Ready for Implementation
**Related Beads**: scrappy-vpa2, scrappy-b6gg, scrappy-iq9k, scrappy-lj2w, scrappy-9li9

---

## Problem Statement

We have three layers of context but the middle one is missing:

| Layer | Current | Purpose |
|-------|---------|---------|
| CLI Session | `SessionContext` | Conversation history, modes, persistence |
| Agent Run | **MISSING** | Model affinity, file cache, iteration tracking |
| Per-Task | `GraphContextFactory` | RAG context, search strategy |

This gap causes multiple bugs:
- **scrappy-b6gg**: Provider switches mid-run (no model affinity)
- **scrappy-iq9k**: Same file read 6 times (no run-level cache)
- **scrappy-9li9**: Infinite loops in error recovery (iteration tracking incomplete)
- **scrappy-lj2w**: State not reset on cancellation (no lifecycle hooks)

---

## Research Findings Summary

### Ownership Chain
```
ScrappyApp
    -> creates LangGraphBridge (with llm_service, tool_adapter)
    -> creates CLIAgentManager (with langgraph_bridge)

LangGraphBridge.run_agent()  # lines 536-599
    -> creates AgentRunContext (NEW)
    -> creates graph via create_agent_runner()
    -> passes run_context via config["configurable"]
    -> runs graph.stream()
```

### Cancellation Flow
```
WorkerCancelled exception raised
    -> except block (lines 717-729): logs, returns cancelled result
    -> finally block (lines 743-749): clears activity, provider status

AgentRunContext.on_cancel() should be called in finally block.
```

### Key Injection Points
- **ToolContext**: Created in `execute_node` via `context_factory` parameter (line 345)
- **Graph Config**: `config["configurable"]` passed to all nodes
- **State Updates**: All state changes flow through `state.model_copy(update={...})`

---

## Proposed Protocol

```python
from typing import Protocol, Optional, Callable, Literal
from dataclasses import dataclass, field

@runtime_checkable
class AgentRunContextProtocol(Protocol):
    """Context for a single agent run (task execution).

    Lifecycle:
    - Created at start of run_agent()
    - Passed to nodes via config["configurable"]["run_context"]
    - Destroyed when run completes or is cancelled
    - NOT persisted with checkpoints (ephemeral)
    """

    # === Model Affinity ===

    @property
    def preferred_provider(self) -> Optional[str]:
        """Provider that succeeded first - stick with it unless handoff triggered."""
        ...

    def record_provider_success(self, provider: str, model: str) -> None:
        """Record successful response - sets affinity if first success."""
        ...

    def record_provider_error(self, provider: str, error_category: str) -> None:
        """Record provider error - may trigger handoff based on category."""
        ...

    def should_handoff(self) -> bool:
        """Check if we should try a different provider."""
        ...

    def get_handoff_reason(self) -> Optional[str]:
        """Get reason for handoff (for logging/display)."""
        ...

    # === File Caching ===

    def get_cached_file(self, path: str) -> Optional[str]:
        """Get file content if already read this run. Returns None if not cached."""
        ...

    def cache_file(self, path: str, content: str) -> None:
        """Cache file content for this run. Limited to MAX_CACHE_SIZE."""
        ...

    def invalidate_file(self, path: str) -> None:
        """Remove file from cache (call after write/edit)."""
        ...

    # === Status Updates ===

    def update_status(self, message: str) -> None:
        """Update status bar with current state (uses registered callback)."""
        ...

    # === Lifecycle ===

    def on_cancel(self) -> None:
        """Called when run is cancelled - cleanup and notify dependents."""
        ...

    def on_complete(self, success: bool) -> None:
        """Called when run completes - cleanup."""
        ...
```

---

## Detailed Design Decisions

### 1. File Cache Strategy

**Decision**: File cache lives in AgentRunContext, accessed via ToolContext.

**Why not in ToolContext directly?**
- ToolContext is recreated each iteration (via context_factory)
- Run context persists across iterations
- Cache must survive iteration boundaries

**Implementation**:
```python
@dataclass
class AgentRunContext:
    # File cache with size limit
    _file_cache: Dict[str, str] = field(default_factory=dict)
    _cache_size_bytes: int = 0
    MAX_CACHE_SIZE_BYTES: int = 5 * 1024 * 1024  # 5MB limit

    def get_cached_file(self, path: str) -> Optional[str]:
        return self._file_cache.get(path)

    def cache_file(self, path: str, content: str) -> None:
        content_size = len(content.encode('utf-8'))

        # Evict oldest entries if over limit
        while self._cache_size_bytes + content_size > self.MAX_CACHE_SIZE_BYTES:
            if not self._file_cache:
                break  # Can't evict, single file too large
            oldest_path = next(iter(self._file_cache))
            self._evict(oldest_path)

        self._file_cache[path] = content
        self._cache_size_bytes += content_size

    def invalidate_file(self, path: str) -> None:
        """Call after write_file or edit_file to invalidate stale cache."""
        if path in self._file_cache:
            self._cache_size_bytes -= len(self._file_cache[path].encode('utf-8'))
            del self._file_cache[path]
```

**Integration with read_file tool**:
```python
# In ReadFileTool.execute():
def execute(self, context: ToolContext, **kwargs) -> ToolResult:
    path = kwargs["path"]

    # Check run-level cache first
    if context.run_context:
        cached = context.run_context.get_cached_file(path)
        if cached is not None:
            return ToolResult(True, cached, metadata={"cached": True})

    # ... existing read logic ...

    # Cache for this run
    if context.run_context:
        context.run_context.cache_file(path, content)

    return ToolResult(True, content)
```

**Cache invalidation on writes**:
```python
# In WriteFileTool.execute():
def execute(self, context: ToolContext, **kwargs) -> ToolResult:
    # ... write logic ...

    # Invalidate cache after successful write
    if context.run_context:
        context.run_context.invalidate_file(path)
```

---

### 2. Iteration Tracking Relationship

**Decision**: Keep `AgentState.iteration` as authoritative source. AgentRunContext observes for safety limits.

**Why not replace?**
- AgentState.iteration is checkpointed (resumable)
- AgentRunContext is ephemeral (fresh on resume)
- Iteration count should survive checkpoint/resume

**Relationship**:
```python
# AgentState.iteration: The counter, incremented by think_node
# AgentRunContext: Observes via routing functions for cross-node limits

def _route_after_error(state: AgentState, config: RunnableConfig) -> str:
    run_context = config["configurable"].get("run_context")

    # Check run-level limit (catches error->think loops)
    if run_context and run_context.is_over_total_limit():
        logger.warning("Run-level iteration limit exceeded")
        return END

    # Existing per-path limit
    if state.iteration >= MAX_ITERATIONS:
        return END

    return "think"
```

**AgentRunContext tracks total node visits** (not just think iterations):
```python
@dataclass
class AgentRunContext:
    _total_node_visits: int = 0
    MAX_TOTAL_VISITS: int = 100  # Safety limit across ALL nodes

    def record_node_visit(self, node_name: str) -> None:
        self._total_node_visits += 1

    def is_over_total_limit(self) -> bool:
        return self._total_node_visits >= self.MAX_TOTAL_VISITS
```

---

### 3. Tool Access Pattern

**Decision**: Inject run_context into ToolContext via context_factory.

**Implementation**:
```python
# In execute_node:
def execute_node(
    state: AgentState,
    tool_adapter: ToolAdapterProtocol,
    config: RunnableConfig,  # Add config parameter
    context_factory: Optional[ToolContextFactory] = None,
    working_memory: Optional[WorkingMemoryProtocol] = None,
) -> AgentState:
    # Get run context from config
    run_context = config["configurable"].get("run_context")

    # Create context with run_context injected
    if context_factory:
        context = context_factory(state.working_dir, working_memory)
    else:
        context = _create_default_context(state.working_dir, working_memory)

    # Inject run context
    context.run_context = run_context
```

**Updated ToolContext**:
```python
@dataclass
class ToolContext:
    project_root: Path
    dry_run: bool = False
    config: Optional["AgentConfig"] = None
    orchestrator: Optional[MemoryProvider] = None

    # NEW: Run-level context for caching and affinity
    run_context: Optional["AgentRunContextProtocol"] = None
```

---

### 4. Status Callback Integration

**Decision**: Use existing ProviderStatus component via callback.

**Implementation**:
```python
@dataclass
class AgentRunContext:
    _status_callback: Optional[Callable[[str], None]] = None

    def set_status_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for status updates (called by LangGraphBridge)."""
        self._status_callback = callback

    def update_status(self, message: str) -> None:
        """Update status bar."""
        if self._status_callback:
            self._status_callback(message)
```

**In LangGraphBridge.run_agent()**:
```python
def run_agent(self, task: str, working_dir: str, ...):
    # Create run context
    run_context = AgentRunContext()

    # Connect to status bar
    run_context.set_status_callback(self._show_provider_status)

    # Include in config
    config = {
        "configurable": {
            "thread_id": thread_id,
            "run_context": run_context,
        },
        ...
    }
```

**In think_node** (after successful response):
```python
# Update status with actual model used
if run_context and response.provider and response.model:
    run_context.record_provider_success(response.provider, response.model)
    run_context.update_status(f"{response.provider}: {response.model}")
```

---

### 5. Cancellation Hook Implementation

**Decision**: Direct call in finally block, notify registered components.

**Implementation**:
```python
@dataclass
class AgentRunContext:
    _cancel_callbacks: list[Callable[[], None]] = field(default_factory=list)

    def register_cancel_callback(self, callback: Callable[[], None]) -> None:
        """Register component to be notified on cancel."""
        self._cancel_callbacks.append(callback)

    def on_cancel(self) -> None:
        """Called from finally block - notify all registered components."""
        for callback in self._cancel_callbacks:
            try:
                callback()
            except Exception as e:
                logger.warning(f"Cancel callback failed: {e}")
        self._cancel_callbacks.clear()
```

**In LangGraphBridge.run_agent()**:
```python
finally:
    # Notify run context of completion/cancellation
    if run_context:
        run_context.on_cancel()  # Safe to call even on success

    # Existing cleanup
    self._post_activity(ActivityState.IDLE)
    self._hide_provider_status()
```

**Registering CommandHistory** (in MainAppScreen):
```python
def process_command(self, user_input: str):
    # ... existing code ...

    # Register history reset on cancel
    if run_context := self._get_current_run_context():
        run_context.register_cancel_callback(self._history.reset_position)
```

---

### 6. Handoff Strategy

**Decision**: Explicit rules based on error category. Extend existing CATEGORY_RETRY_CONFIGS pattern.

**Implementation**:
```python
# Handoff triggers - when to try a different provider
HANDOFF_TRIGGERS: dict[str, bool | int] = {
    # Always handoff immediately
    "rate_limit": True,
    "auth_error": True,
    "quota_exceeded": True,
    "model_not_found": True,

    # Handoff after N consecutive errors
    "server_error": 3,
    "timeout": 2,
    "context_length_exceeded": True,  # Need smaller model or truncation

    # Never handoff (retry same provider)
    "network": False,  # Transient, retry
    "parse": False,    # Model issue, not provider
}

@dataclass
class AgentRunContext:
    preferred_provider: Optional[str] = None
    _provider_errors: dict[str, list[str]] = field(default_factory=dict)
    _handoff_triggered: bool = False
    _handoff_reason: Optional[str] = None

    def record_provider_error(self, provider: str, error_category: str) -> None:
        if provider not in self._provider_errors:
            self._provider_errors[provider] = []
        self._provider_errors[provider].append(error_category)

        # Check if handoff should trigger
        trigger = HANDOFF_TRIGGERS.get(error_category)
        if trigger is True:
            self._handoff_triggered = True
            self._handoff_reason = f"{error_category} from {provider}"
        elif isinstance(trigger, int):
            # Count consecutive errors of this category
            recent = self._provider_errors[provider][-trigger:]
            if len(recent) >= trigger and all(e == error_category for e in recent):
                self._handoff_triggered = True
                self._handoff_reason = f"{trigger}x {error_category} from {provider}"

    def should_handoff(self) -> bool:
        return self._handoff_triggered

    def get_handoff_reason(self) -> Optional[str]:
        return self._handoff_reason

    def clear_handoff(self) -> None:
        """Call after successful handoff to new provider."""
        self._handoff_triggered = False
        self._handoff_reason = None
```

**Integration with error_node**:
```python
def error_node(state: AgentState, config: RunnableConfig) -> AgentState:
    run_context = config["configurable"].get("run_context")

    # Record error in run context
    if run_context and state.error_category:
        run_context.record_provider_error(
            state.last_model_display or "unknown",
            state.error_category
        )

    # Check for handoff
    if run_context and run_context.should_handoff():
        reason = run_context.get_handoff_reason()
        logger.info(f"Provider handoff triggered: {reason}")
        run_context.update_status(f"switching provider ({reason})")
        run_context.clear_handoff()
        # Clear provider affinity to allow fallback
        run_context.preferred_provider = None
```

---

## Corrections to Previous Analysis

### scrappy-nhgp Root Cause (Updated)

**Previous Analysis** (incorrect):
> `prompt_with_history()` doesn't exist in CommandHistory

**Actual Root Cause**:
TextArea widget's `clear()` + `insert()` pattern leaves cursor/document in inconsistent state. Left/right arrows and backspace stop working.

**Fix Applied**:
Use `text` setter instead of `clear()` + `insert()`:
```python
# Before (broken)
self._layout.input.clear()
self._layout.input.insert(previous)

# After (fixed)
self._layout.input.text = previous
```

---

## Implementation Plan

### Phase 1: Core AgentRunContext (Estimated: 1 session)

1. **Create protocol and implementation**
   - `src/scrappy/graph/run_context.py` - AgentRunContextProtocol + AgentRunContext
   - Basic structure: preferred_provider, file_cache, status_callback, on_cancel

2. **Inject in LangGraphBridge**
   - Create in `run_agent()` before try block
   - Add to config["configurable"]
   - Call on_cancel() in finally block

3. **Update ToolContext**
   - Add `run_context: Optional[AgentRunContextProtocol]` field
   - Update context_factory pattern in execute_node

4. **Add tests**
   - Unit tests for AgentRunContext
   - Integration test for cancellation callback

### Phase 2: File Caching (Estimated: 1 session)

1. **Implement cache in AgentRunContext**
   - `get_cached_file()`, `cache_file()`, `invalidate_file()`
   - Size limit with LRU eviction

2. **Update ReadFileTool**
   - Check cache before reading
   - Cache after successful read

3. **Update WriteFileTool / EditFileTool**
   - Invalidate cache after write

4. **Add tests**
   - Cache hit/miss scenarios
   - Invalidation on write
   - Size limit enforcement

### Phase 3: Model Affinity (Estimated: 1 session)

1. **Implement affinity tracking**
   - `record_provider_success()`, `record_provider_error()`
   - `should_handoff()`, `get_handoff_reason()`

2. **Update think_node**
   - Record success with provider info
   - Check affinity before model selection

3. **Update error_node**
   - Record errors with category
   - Trigger handoff when appropriate

4. **Add tests**
   - Affinity sticking
   - Handoff triggers
   - Recovery after handoff

### Phase 4: Cleanup & Polish (Estimated: 0.5 session)

1. Close related beads with implementation notes
2. Update any stale documentation
3. Run full test suite
4. Manual testing of end-to-end flows

---

## Related Files

| File | Role |
|------|------|
| `src/scrappy/graph/run_context.py` | NEW - AgentRunContext implementation |
| `src/scrappy/graph/protocols.py` | Add AgentRunContextProtocol |
| `src/scrappy/cli/textual/langgraph_bridge.py` | Create and inject run context |
| `src/scrappy/graph/nodes/execute.py` | Inject into ToolContext |
| `src/scrappy/agent_tools/tools/base.py` | Add run_context field to ToolContext |
| `src/scrappy/agent_tools/tools/file_tools.py` | Use file cache |
| `src/scrappy/graph/nodes/think.py` | Record provider success |
| `src/scrappy/graph/nodes/error.py` | Record errors, trigger handoff |

---

## Open Items (Deferred)

1. **Checkpoint resume behavior**: Fresh context on resume is acceptable for MVP. May revisit if users report issues.

2. **Multi-provider fallback chain**: Current design handles single fallback. Multi-step chains (A->B->C) would need additional tracking.

3. **Metrics/telemetry**: Could add cache hit rate, handoff frequency to Langfuse. Not required for MVP.
