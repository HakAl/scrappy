# Stability Bugs Analysis - Root Causes and Patterns

## Summary

12 stability bugs analyzed. 3 systemic root causes identified. Phased fix plan proposed.

---

## The Session/Context Gap

We have three layers of "context" but the middle one is missing:

| Layer | Current Implementation | Purpose |
|-------|------------------------|---------|
| **CLI Session** | `SessionContext` | Conversation history, modes, persistence |
| **Agent Run** | **MISSING** | Model affinity, file cache, provider health |
| **Per-Task** | `GraphContextFactory` | RAG context, search strategy |

### Related Beads

| ID | Priority | Description |
|----|----------|-------------|
| scrappy-vpa2 | P2 | Design session abstraction for agent run context |
| scrappy-b6gg | P1 | Session model affinity - prevent provider switching mid-run |
| scrappy-iq9k | P2 | Redundant file reads - blog.html read 6 times |

### Dependencies

```
scrappy-vpa2 (session abstraction)
    ↑
    ├── scrappy-b6gg (model affinity) - needs run context to track provider
    └── scrappy-iq9k (file cache) - needs run context to cache reads
```

### What AgentRunContext Should Track

From scrappy-vpa2 description:
1. **Model affinity** - stick with provider unless explicit fallback
2. **Read cache** - files already read this session
3. **Provider state** - rate limits, response times, health
4. **Timeout handling** - clean separation between slow response and actual timeout

This would also help with:
- Coordinating state resets on cancellation (scrappy-lj2w)
- Tracking iterations across error recovery (scrappy-9li9)

---

## Bug Groups

### UX Input Bugs

#### scrappy-lj2w: Up/down arrows don't navigate history after cancelling agent

**Root Cause**: When agent cancellation occurs, `InputCaptureManager.cancel()` clears only the prompt/confirm state, but never calls `CommandHistory.reset_position()`. The history position remains stale, causing next up-arrow navigation to start from wrong position.

**Files**:
- `src/scrappy/cli/command_history.py:154-156` - `reset_position()` method exists but unused
- `src/scrappy/cli/input_capture.py:157-170` - `cancel()` doesn't notify history
- `src/scrappy/cli/screens/main_screen.py` - Creates both managers but no coordinator

**Systemic Issue**: No state coordinator. Multiple independent state managers operate without synchronization hooks.

---

#### scrappy-nhgp: Keys unresponsive after command history navigation

**Root Cause**: TextArea widget's `clear()` + `insert()` pattern leaves cursor/document state inconsistent. After using up/down arrows to navigate history, the TextArea's internal state is corrupted - left/right arrows and backspace stop working.

**Files**:
- `src/scrappy/cli/screens/main_screen.py:256-283` - History navigation methods using clear()+insert()

**Fix Applied**: Use `text` setter instead of `clear()` + `insert()`:
```python
# Before (broken)
self._layout.input.clear()
self._layout.input.insert(previous)

# After (fixed)
self._layout.input.text = previous
```

**Systemic Issue**: Textual widget APIs have subtle state management requirements not obvious from documentation.

---

### UX Display Bugs

#### scrappy-p17i: Scroll container content doesn't wrap correctly on resize

**Root Cause**: `DisplayManager` uses Rich's `Live()` context manager but never refreshes on terminal resize. Rich requires explicit refresh on SIGWINCH, but no handler exists.

**Files**:
- `src/scrappy/cli/display_manager.py:187-207` - Creates Live display but no SIGWINCH handler
- `update_live_display()` method exists but never called on resize

**Systemic Issue**: Display coordination layer missing lifecycle hooks for terminal events.

---

#### scrappy-mit3: Error recovery messages not shown to user

**Root Cause**: `graceful_degrade()` function (lines 93-121) accepts optional io parameter. When io is None (common case), degradation occurs silently - messages logged only.

**Files**:
- `src/scrappy/cli/error_recovery/fallback.py:93-121` - Optional io parameter
- Multiple call sites pass None or omit io entirely

**Systemic Issue**: Error recovery abstractions designed for logging, not user-facing communication.

---

#### scrappy-ubpo: Tier escalation not visible to user

**Root Cause**: `error_node()` escalates model tier (lines 244-250) and logs only. No system message appended to messages list, so user never sees the escalation.

**Files**:
- `src/scrappy/graph/nodes/error.py:244-250` - Logs escalation but doesn't add system message

**Systemic Issue**: Internal state changes not propagated to message layer for UI display.

---

### Agent Bugs

#### scrappy-gicf: Agent minifies JSON when writing files

**Root Cause**: `convert_tool_calls()` in think.py (line 119) uses `json.dumps(tc_args)` with no indent parameter. This minifies JSON. Agent sees minified format, reproduces it, creating feedback loop.

**Files**:
- `src/scrappy/graph/nodes/think.py:119` - Default json.dumps()
- `src/scrappy/agent_tools/tools/web_tools.py:121,187` - Uses indent=2
- `src/scrappy/cli/command_history.py:100` - Different formatting

**Systemic Issue**: No canonical JSON formatting layer.

---

#### scrappy-9li9: No max_iterations check in confirm/error/verify nodes

**Root Cause**: `MAX_ITERATIONS` (line 32 of edges.py) is only checked in `should_continue()` routing function. Confirm, error, and verify nodes run without incrementing or checking iteration. Users can loop indefinitely through error recovery.

**Files**:
- `src/scrappy/graph/edges.py:102` - Checks MAX_ITERATIONS in should_continue() only
- `src/scrappy/graph/nodes/confirm.py` - No iteration check
- `src/scrappy/graph/nodes/error.py` - No iteration check
- `src/scrappy/graph/nodes/verify.py` - No iteration check

**Systemic Issue**: Iteration tracking only covers think->execute path, not error recovery paths.

---

### API/Tools Bugs

#### scrappy-apj4: web_search doesn't search web, only package registries

**Root Cause**: `WebSearchTool` (lines 242-395) is hardcoded with only `SEARCH_ENDPOINTS` for PyPI, npm, GitHub. No actual web search endpoints.

**Files**:
- `src/scrappy/agent_tools/tools/web_tools.py:246-250` - Only registry endpoints

**Systemic Issue**: Tool misnamed - it's actually `RegistrySearchTool`.

---

#### scrappy-bief: Groq tool response parsing failure

**Root Cause**: NOT a parsing bug. Model confusion from misleading tool name.

Groq model outputs malformed syntax when confused:
```
<function=web_search({"registry": "google", ...})></function>
```

Model tried `registry: "google"` but our `web_search` only supports PyPI/npm/GitHub. When schema doesn't match expectations, model hallucinates and outputs malformed XML-style call.

**Fix**: Rename `web_search` -> `package_search` (scrappy-apj4). This prevents the confusion.

**Dependency**: scrappy-bief depends on scrappy-apj4.

---

#### scrappy-wo29: run_agent_in_worker return type annotation wrong

**Root Cause**: Method has `@work(thread=True)` decorator but return type is `AgentResult`. Textual's decorator wraps return in `Task[AgentResult]`.

**Files**:
- `src/scrappy/cli/textual/langgraph_bridge.py:~460` - Wrong return type

**Systemic Issue**: Type annotations don't match decorator behavior.

---

## Systemic Root Causes

### 1. Fragmented State Management (CRITICAL)

Multiple independent state managers with no coordination:
- `CommandHistory._position` - Keyboard state
- `InputCaptureManager._mode` - Prompt state
- `AgentState.pending_confirmation` - Confirmation state
- `AgentState.error_count/iteration` - Loop prevention

**Affects**: scrappy-lj2w, scrappy-nhgp, scrappy-9li9

**Fix**: Introduce `StateCoordinatorProtocol` with `reset_on_cancellation()`, `on_agent_run_end()` callbacks

---

### 2. Error Recovery is Silent (HIGH)

Error recovery code logs to developers, not users. No system messages, no UI updates.

**Affects**: scrappy-mit3, scrappy-ubpo

**Fix**: All recovery actions must append system messages and update UI layer

---

### 3. Iteration Tracking is Incomplete (HIGH)

Only `should_continue()` checks MAX_ITERATIONS. Confirm/error/verify nodes run without limits.

**Affects**: scrappy-9li9

**Fix**: All nodes doing "work" must check iteration before proceeding

---

## Implementation Plan

### Phase 1: Stop Bleeding (Quick Fixes)

| Bug | Fix | Effort |
|-----|-----|--------|
| scrappy-9li9 | Add iteration checks to confirm/error/verify nodes | Small |
| scrappy-lj2w | Call `history.reset_position()` on cancellation | Small |
| scrappy-apj4 | Delete `web_search` tool, switch default to "optimized" profile (also fixes scrappy-bief) | Small |

### Phase 2: UX Visibility

| Bug | Fix | Effort |
|-----|-----|--------|
| scrappy-mit3 | Append system messages for degradation | Small |
| scrappy-ubpo | Append system messages for tier escalation | Small |
| scrappy-nhgp | Remove dead keyboard handling code | Medium |
| scrappy-p17i | Wire display refresh to terminal resize | Medium |

### Phase 3: AgentRunContext (Unifying Abstraction)

**This is the key architectural fix** - introduces the missing middle layer.

| Bug | How AgentRunContext Helps |
|-----|---------------------------|
| scrappy-vpa2 | IS the session abstraction |
| scrappy-b6gg | Tracks `preferred_provider` for model affinity |
| scrappy-iq9k | Provides `file_cache` dict for read deduplication |
| scrappy-lj2w | Provides `on_cancel()` hook to reset all state |
| scrappy-9li9 | Tracks `total_iterations` across all node types |

```python
@dataclass
class AgentRunContext:
    """Context for a single agent run (task execution)."""

    # Model affinity
    preferred_provider: Optional[str] = None
    fallback_count: int = 0

    # File caching
    file_cache: Dict[str, str] = field(default_factory=dict)

    # Iteration tracking (across ALL nodes)
    total_iterations: int = 0
    max_iterations: int = 25

    # Provider health
    provider_errors: Dict[str, int] = field(default_factory=dict)

    # Lifecycle hooks
    def on_cancel(self) -> None:
        """Called when run is cancelled - reset dependent state."""
        pass

    def on_complete(self) -> None:
        """Called when run completes - cleanup."""
        pass
```

### Phase 4: Cleanup

| Bug | Fix | Effort |
|-----|-----|--------|
| scrappy-gicf | Canonical JSON formatter utility | Small |
| scrappy-wo29 | Fix @work decorator type annotation | Small |
| scrappy-apj4 | Rename WebSearchTool -> RegistrySearchTool | Medium |

---

## Key Insight

Root cause across all bugs: **Lack of coordination abstractions**.

Components operate independently without observing state changes elsewhere. No protocols for lifecycle events (cancellation, resize, errors). Result is cascading failures when one component changes state without notifying dependents.
