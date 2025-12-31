# LangGraph Migration Plan

**Status:** Ready for Approval
**Last Updated:** Reba's review incorporated

---

## Summary

Transform scrappy from hand-rolled state machine to LangGraph-based agent.

**Goals:**
- Replace ~40,000 lines (task_router + agent + orchestrator + context) with ~2,000 lines
- Add Docker sandboxing for safe command execution
- Add Langfuse observability (self-hosted, free)
- Simplify CLI

**Key Findings from Research:**
- LiteLLM + Instructor already integrated and comprehensive
- Textual uses `@work(thread=True)` pattern - LangGraph can run via `asyncio.run()` in worker
- `ThreadSafeAsyncBridge` already solves confirmation problem

---

## Phase 0: Foundation

**Goal:** Set up dependencies, verify LiteLLM coverage, define state model.

### Task 0.1: Add Dependencies

**Description:** Add LangGraph, LangFuse, and Docker SDK.

**Files:**
- `pyproject.toml`

**Acceptance Criteria:**
- [ ] `pip install -e .` succeeds
- [ ] `from langgraph.graph import StateGraph` works
- [ ] `import langfuse` works
- [ ] `import docker` works

---

### Task 0.2: Verify LiteLLM Covers Orchestrator Capabilities

**Description:** Audit what orchestrator/ does, verify LiteLLM can replace it.

**Orchestrator capabilities to verify:**
- [ ] Model selection (fast/quality tiers) - LiteLLMService has this
- [ ] Provider fallback - LiteLLM Router handles this
- [ ] Rate limiting - LiteLLMService has throttling
- [ ] Streaming with cancellation - LiteLLMService.stream_completion()
- [ ] Structured output - LiteLLMService.completion_structured() via Instructor
- [ ] Context window escalation - LiteLLMService handles this

**Acceptance Criteria:**
- [ ] Document any gaps
- [ ] Plan how to address gaps (if any)
- [ ] GO/NO-GO decision before proceeding

**Verification:** Checklist review, test calls through LiteLLMService

---

### Task 0.3: Define State Model

**Description:** Create Pydantic state model.

**Files:**
- `src/scrappy/graph/state.py` (new)

**Fields (per Neo's design + Reba's review):**
```python
class AgentState(BaseModel):
    # Core
    input: str                          # Current input
    original_task: str                  # Preserved original task
    messages: list[dict] = []           # Conversation history

    # Execution tracking
    iteration: int = 0
    done: bool = False
    error_count: int = 0
    last_error: str | None = None       # For error node context

    # Model selection
    current_tier: str = "fast"          # "fast" or "quality"

    # File tracking
    files_changed: list[str] = []
    working_dir: str = "."

    # Checkpointing
    checkpoint: str | None = None

    # Human-in-the-loop
    pending_confirmation: dict | None = None  # For interrupt handling

    # Tool results (separate from messages for easier access)
    tool_results: list[dict] = []
```

**Note:** Cancellation and streaming callbacks are NOT in state - they're passed to the graph runner as runtime config, not persisted in checkpoints.

**Acceptance Criteria:**
- [ ] Pydantic BaseModel
- [ ] All fields documented
- [ ] **Fully JSON-serializable** (required for SqliteSaver persistence)
- [ ] Unit test for state creation, updates, and JSON round-trip

---

### Task 0.4: Set Up Langfuse Tracing

**Description:** Configure Langfuse for observability from day 1 (self-hosted, free).

**Files:**
- `src/scrappy/graph/tracing.py` (new)
- `docker-compose.yml` (add Langfuse services)
- `.env.example` - add LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY

**Acceptance Criteria:**
- [ ] Langfuse runs via docker-compose alongside sandbox
- [ ] Tracing enabled when Langfuse available
- [ ] Traces appear in Langfuse dashboard
- [ ] Graceful fallback when Langfuse not running (local dev without Docker)

---

### Task 0.5: Create Graph Module Structure

**Files:**
- `src/scrappy/graph/__init__.py`
- `src/scrappy/graph/nodes/` (directory)
- `src/scrappy/graph/edges.py`

**Acceptance Criteria:**
- [ ] Clean module structure
- [ ] No imports from old task_router or agent

---

## Phase 1: Core Agent Loop

**Goal:** Build LangGraph state machine with nodes.

### Task 1.1: Create Tool Registry Adapter

**Description:** Adapt existing agent_tools to work with LangGraph.

**Rationale (Neo):** Need this BEFORE Execute node, not in Phase 3.

**Files:**
- `src/scrappy/graph/tools.py` (new)

**Acceptance Criteria:**
- [ ] Wraps existing ToolRegistry
- [ ] Provides tool schemas for Instructor/function calling
- [ ] Provides execute method for Execute node
- [ ] Supports List[ToolCall] (multi-tool)
- [ ] No changes to agent_tools/ internals

---

### Task 1.2: Implement Think Node

**Description:** LLM reasoning step using LiteLLMService.

**Files:**
- `src/scrappy/graph/nodes/think.py` (new)

**Acceptance Criteria:**
- [ ] Takes AgentState, calls LLM, returns AgentState with new message
- [ ] Uses LiteLLMService.completion_sync() or stream
- [ ] Uses Instructor for structured output (tool calls)
- [ ] **Streaming from day 1** (not optional)
- [ ] **Context Sanitization:** Before LLM call, trim messages if approaching token limit
  - Use `trim_messages` utility: summarize older messages or drop middle if too long
  - Prevents hard crash from 128k/200k token limits

**Verification:** Unit test with mocked LLM response

---

### Task 1.3: Implement Execute Node

**Description:** Tool execution step.

**Files:**
- `src/scrappy/graph/nodes/execute.py` (new)

**Acceptance Criteria:**
- [ ] Parses tool calls from last message
- [ ] **Handles List[ToolCall]** (multi-tool support)
- [ ] **Sequential execution** (not parallel - avoids concurrent file write conflicts)
- [ ] Executes tools via adapter from Task 1.1
- [ ] Appends tool results to messages
- [ ] Tracks files_changed for write operations
- [ ] **Output Truncation:** If tool output exceeds 20k chars, truncate center and append `...[truncated X chars]...`
- [ ] **Binary File Guard:** If reading non-text file, return `[Binary file: X bytes]` instead of crashing on utf-8 decode

---

### Task 1.4: Implement Verify Node

**Description:** Run linting/testing on changed files.

**Files:**
- `src/scrappy/graph/nodes/verify.py` (new)

**Acceptance Criteria:**
- [ ] Runs ruff on changed Python files
- [ ] Runs mypy on changed Python files
- [ ] **Batches verification** (not per-file)
- [ ] Updates error_count in state
- [ ] Appends errors to messages
- [ ] Ideal, not hard target: ~50 lines code

---

### Task 1.5: Spike - Verify interrupt_before Pattern

**Description:** Verify LangGraph's interrupt_before works with ThreadSafeAsyncBridge.

**Rationale (Reba):** Don't commit to interrupt_before without proving it works.

**Acceptance Criteria:**
- [ ] Create minimal spike: LangGraph graph with interrupt_before
- [ ] Verify it blocks graph execution
- [ ] Verify ThreadSafeAsyncBridge can provide response
- [ ] Document: does interrupt_before work, or do we need custom node?
- [ ] GO/NO-GO: proceed with interrupt_before or pivot to custom confirm node

---

### Task 1.6: Implement Human-in-the-Loop Node

**Description:** Confirmation prompts for dangerous operations.

**Rationale (Neo):** Safety is MVP.

**Files:**
- `src/scrappy/graph/nodes/confirm.py` (new)

**Acceptance Criteria:**
- [ ] Uses pattern validated in Task 1.5
- [ ] Integrates with ThreadSafeAsyncBridge for Textual
- [ ] Supports: command confirmation, file overwrite, etc.
- [ ] Handles denial (update state, continue or abort)

---

### Task 1.7: Implement Routing Logic

**Description:** Conditional edges for the graph.
has error node. Should include "error".

**Files:**
- `src/scrappy/graph/edges.py`

**Acceptance Criteria:**
- [ ] `should_continue(state)` returns: "think", "verify", "confirm", "error", or "end"
- [ ] Ends when: done=True, iteration > max, error_count > max_retries
- [ ] Routes to verify when files_changed is non-empty
- [ ] Routes to confirm for dangerous operations
- [ ] Ideal, not hard target: ~50 lines code

---

### Task 1.8: Wire Up the Graph

**Description:** Assemble nodes and edges into StateGraph.

**Files:**
- `src/scrappy/graph/agent.py` (new)

**Graph Structure:**
```
START -> think -> execute -> (conditional)
                     |
         +-----------+-----------+-----------+
         |           |           |           |
      verify      confirm      error        end
         |           |           |
         +-----------+-----------+
                     |
                  think
```

**Acceptance Criteria:**
- [ ] Entry point: think (no separate classify - LLM decides)
- [ ] Conditional edges from execute
- [ ] **Error node** handles tool failures, routes back to think with error context
- [ ] Compiled with MemorySaver checkpointer

---

### Task 1.9: Integration Test - All Paths

**Description:** End-to-end tests covering all graph paths.

**Acceptance Criteria:**
- [ ] Happy path: think -> execute -> verify -> end
- [ ] Verify failure: think -> execute -> verify (fails) -> think -> ... -> end
- [ ] Confirm denied: think -> execute -> confirm (denied) -> end
- [ ] Tool error: think -> execute -> error -> think -> ...
- [ ] Cancellation: graph stops cleanly on cancel
- [ ] Langfuse traces visible

---

### Task 1.10: Persistence Strategy

**Description:** Decide and implement session persistence approach.

**Context:** `MemorySaver` loses state if process dies (SIGINT) or user restarts CLI.

**Options:**
1. **Ephemeral only** - `MemorySaver`, sessions don't survive restart (simpler)
2. **Persistent** - `SqliteSaver`, users can resume after closing terminal (more complex)

**Acceptance Criteria:**
- [ ] Decision documented: ephemeral or persistent?
- [ ] If persistent: SqliteSaver configured with path in user config dir
- [ ] If ephemeral: Document limitation clearly in user-facing docs
- [ ] Test: state survives/doesn't survive process restart (per decision)

---

## Phase 2: Docker Sandbox

**Goal:** Safe command execution in isolated container.

### Task 2.1: Create Docker Executor

**Description:** Sandboxed shell command execution with container reuse.

**Rationale (Neo):** Container-per-command is too slow. Reuse container.

**Files:**
- `src/scrappy/sandbox/__init__.py` (new)
- `src/scrappy/sandbox/docker_executor.py` (new)
- `Dockerfile.sandbox` (new)

**Acceptance Criteria:**
- [ ] **Persistent container** - start on agent init, reuse for commands
- [ ] Project directory mounted read-write
- [ ] Network isolated by default
- [ ] Timeout enforced per-command
- [ ] Output captured and returned
- [ ] Container cleanup on agent exit
- [ ] **Fallback to host execution** with warning if Docker unavailable
- [ ] **Windows support:** Handle path translation (C:\ <-> /mnt/c/) for WSL2/Hyper-V

---

### Task 2.2: Integrate Sandbox with Execute Node

**Files:**
- `src/scrappy/graph/nodes/execute.py` (modify)

**Acceptance Criteria:**
- [ ] run_command tool uses Docker executor
- [ ] File operations work via mounted volume
- [ ] Graceful fallback with warning if Docker unavailable

---

### Task 2.3: Git Branch Isolation

**Files:**
- `src/scrappy/sandbox/git_isolation.py` (new)

**Acceptance Criteria:**
- [ ] Creates working branch before agent starts
- [ ] Branch naming: `scrappy/<timestamp>-<short-task-hash>` (e.g., `scrappy/20250101-a1b2c3`)
- [ ] Handles existing branch: append `-1`, `-2`, etc. or fail with clear error
- [ ] Easy rollback via git checkout main
- [ ] Cleans up old scrappy branches (configurable retention)

---

## Phase 3: CLI Integration

**Goal:** Wire CLI to new LangGraph agent.

### Task 3.1: Create Agent Entry Point

**Files:**
- `src/scrappy/graph/__init__.py` (modify)

**Acceptance Criteria:**
- [ ] `run_agent(task: str) -> Result` entry point
- [ ] Handles setup (Docker, LangFuse), invocation, cleanup
- [ ] Returns structured result

---

### Task 3.2: Create Textual-LangGraph Bridge

**Description:** Bridge LangGraph async to Textual worker pattern.

**Rationale (Neo):** This is where dragons live. Be explicit.

**Files:**
- `src/scrappy/cli/textual/langgraph_bridge.py` (new)

**Implementation:**
```python
@work(thread=True)
def run_agent_worker(self, task: str):
    """Run LangGraph agent in worker thread."""
    # asyncio.run() creates and cleans up event loop properly
    # Avoids conflicts with LangGraph/LiteLLM internal loops
    return asyncio.run(
        run_agent_async(
            task,
            confirm_callback=self.bridge.blocking_confirm,
            output_callback=self.output_adapter.post_output,
        )
    )
```

**Acceptance Criteria:**
- [ ] LangGraph runs in @work(thread=True) worker
- [ ] Confirmations route through ThreadSafeAsyncBridge
- [ ] Streaming output routes to TextualOutputAdapter
- [ ] Cancellation via Escape/Ctrl+C works

---

### Task 3.3: Wire CLI Commands to New Agent

**Files:**
- `src/scrappy/cli/` (modify relevant files)

**Acceptance Criteria:**
- [ ] `scrappy "task"` uses new LangGraph agent
- [ ] Textual TUI works
- [ ] Rich output works
- [ ] Streaming displays correctly

---

### Task 3.4: Run Old Integration Tests Against New Agent

**Description:** Verify behavioral parity before deletion.

**Rationale (Neo):** Don't delete tests then validate. Validate first.

**Acceptance Criteria:**
- [ ] Run existing agent integration tests
- [ ] Document behavioral differences
- [ ] Decide: port test, delete test, or fix new agent

---

### Task 3.5: Identify CLI Features to Remove

**Description:** Audit and decide what to cut.

**Current CLI features (20k lines):**
- research_handlers/ (various specialized handlers)
- error_recovery/ (circuit breaker, retry, fallback)
- validators/ (input validation)
- screens/ (Textual screens)
- widgets/ (custom widgets)

**Acceptance Criteria:**
- [ ] List features with keep/remove decision
- [ ] User approval on list

**REQUIRES USER INPUT**

---

### Task 3.6: Remove Unnecessary CLI Features

**Files:** TBD based on 3.5

**Acceptance Criteria:**
- [ ] Identified features removed
- [ ] CLI still works for core use cases

---

## Phase 4: Deletion

**Goal:** Remove old code.

### Task 4.1: Delete task_router/

**Lines:** ~8,259

**Acceptance Criteria:**
- [ ] Directory deleted
- [ ] No imports from task_router anywhere
- [ ] **Grep check:** `grep -r "task_router" .` finds no string refs in prompts/comments
- [ ] **Run pytest immediately after** - verify no breakage before next deletion
- [ ] Tests pass or deleted

---

### Task 4.2: Delete Old agent/

**Lines:** ~9,412

**Acceptance Criteria:**
- [ ] Directory deleted
- [ ] No imports from agent anywhere
- [ ] **Grep check:** `grep -r "from.*agent" .` and `grep -r "import agent" .` clean
- [ ] **Run pytest immediately after** - verify no breakage before next deletion
- [ ] Tests pass or deleted

---

### Task 4.3: Delete orchestrator/ (Partial)

**Lines:** ~13,309 (minus LiteLLMService which stays)

**Keep:**
- `litellm_service.py`
- `litellm_config.py`
- `litellm_callbacks.py`

**Delete:**
- Everything else (old provider system, delegation, etc.)

**Acceptance Criteria:**
- [ ] Old orchestrator code deleted
- [ ] LiteLLMService works standalone
- [ ] **Run pytest immediately after** - verify no breakage before next deletion
- [ ] Tests pass or deleted

---

### Task 4.4: Delete context/

**Lines:** ~8,565

**Acceptance Criteria:**
- [ ] Directory deleted
- [ ] State management via AgentState only
- [ ] **Run pytest immediately after** - verify no breakage before next deletion
- [ ] Tests pass or deleted

---

### Task 4.5: Clean Up Tests

**Acceptance Criteria:**
- [ ] Tests for deleted packages removed
- [ ] Core behavior tests ported to new graph
- [ ] Test suite passes

---

## Phase 5: Validation

**Goal:** Ensure everything works.

### Task 5.1: Run Full Test Suite

**Acceptance Criteria:**
- [ ] `pytest` passes
- [ ] No import errors
- [ ] Coverage acceptable

---

### Task 5.2: Manual Testing Matrix

| Scenario | Expected | Status |
|----------|----------|--------|
| "Write hello world function" | Creates file, passes lint | |
| "Fix this syntax error" | Reads file, fixes, verifies | |
| "Explain this code" | Responds without tools | |
| "Run npm install" | Executes in Docker sandbox | |
| Dangerous command | Prompts for confirmation | |
| Ctrl+C during execution | Cancels cleanly | |
| LLM returns garbage | Retries with error message | |
| Docker unavailable | Falls back with warning | |

---

### Task 5.3: LangFuse Trace Review

**Acceptance Criteria:**
- [ ] All graph invocations traced
- [ ] Can see node execution flow
- [ ] Can debug failed runs

---

### Task 5.4: Performance Validation

**Acceptance Criteria:**
- [ ] Measure baseline
- [ ] Time to first response < 3s
- [ ] Docker command overhead < 1s (container reuse)
- [ ] Full task completion comparable to old agent

---

## Phase 6: Documentation

### Task 6.1: Update CLAUDE.md

**Acceptance Criteria:**
- [ ] Architecture section reflects LangGraph
- [ ] Commands updated
- [ ] New patterns documented

---

### Task 6.2: Update README

**Acceptance Criteria:**
- [ ] Docker requirement documented
- [ ] Usage examples updated

---

## Summary Table

| Phase | Tasks | Est. Lines Deleted | Est. Lines Added |
|-------|-------|--------------------|------------------|
| 0: Foundation | 5 | 0 | ~300 |
| 1: Core Loop | 10 | 0 | ~700 |
| 2: Docker | 3 | 0 | ~400 |
| 3: CLI | 6 | TBD | ~300 |
| 4: Deletion | 5 | ~39,545 | 0 |
| 5: Validation | 4 | 0 | ~100 |
| 6: Docs | 2 | 0 | ~50 |

**Total:** 35 tasks, ~38,000 net lines removed

---

## Escape Hatches

1. **Docker fails:** Fall back to host execution with warning
2. **LangGraph doesn't fit:** Can always use simple while loop (but try LangGraph first)
3. **Textual integration breaks:** Old code on branch until Phase 5 passes
4. **Performance regression:** Profile, optimize, or revert specific nodes

---

## Go/No-Go Checkpoints

| After Phase | Checkpoint |
|-------------|------------|
| 0 | LiteLLM verified, dependencies installed |
| 1 | Basic agent loop works end-to-end |
| 2 | Docker sandbox works, commands isolated |
| 3 | CLI wired, old tests pass on new agent |
| 4 | Deletion complete, no regressions |
| 5 | Full validation passed |

---

## Resolved Questions

1. **CLI features to cut** - Remove unused/obsolete code during Task 3.5 audit
2. **Streaming implementation** - Use existing `LiteLLMService.stream_completion()` directly in Think node
3. **E2B vs Docker** - Docker only (open source project, no paid services)
