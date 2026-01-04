# LangGraph UX Integration Plan

**Status:** Draft - Awaiting Approval
**Created:** 2026-01-03
**Scope:** Fix graph edge cases + wire UX features for LangGraph agent

---

## Summary

Transform the silent LangGraph agent execution into a visible, trustworthy experience with activity indicators, tool call display, diffs, and proper completion signaling.

**UX Approach:** Streaming log with refinements (Option A)
- Terse start: Just `Task: {task}`
- Activity line: Current action + elapsed time
- Tool calls: `[tool] name: key_param` - one line each
- Diffs: Compact unified diff after file writes
- Completion: Clear summary with file list

---

## Phase 1: Graph Edge Cases (Blockers)

### Task 1.1: Fix unconditional think->execute edge (scrappy-mpyx)

**Description:** Add conditional routing after think node. When `last_error` is set, route to error node instead of execute.

**Files:**
- `src/scrappy/graph/agent.py` - change edge from unconditional to conditional
- `src/scrappy/graph/edges.py` - add `route_after_think()` function

**Acceptance Criteria:**
- [ ] think node errors route directly to error node (not through execute)
- [ ] Normal think output still routes to execute
- [ ] Unit test: think with last_error -> error node
- [ ] Unit test: think without error -> execute node

**Verification:** `python -m pytest tests/unit/graph/test_edges.py -v`

---

### Task 1.2: Fix infinite loop when LLM not configured (scrappy-x3cs)

**Description:** Handle NotConfiguredError explicitly in think node. Set `done=True` and surface clear error message instead of looping.

**Files:**
- `src/scrappy/graph/nodes/think.py` - add NotConfiguredError handler

**Acceptance Criteria:**
- [ ] NotConfiguredError caught explicitly (not generic Exception)
- [ ] Sets `done=True` to stop graph execution
- [ ] Sets `last_error` with clear message: "LLM not configured. Run /setup"
- [ ] Unit test: NotConfiguredError -> done=True, clear message

**Verification:** `python -m pytest tests/unit/graph/test_think.py -v`

---

### Task 1.3: Edge case audit - graph termination paths

**Description:** Audit all graph nodes and edges for cases that could cause infinite loops or hangs. Document findings and create beads for any issues found.

**Files to audit:**
- `src/scrappy/graph/agent.py` - graph structure
- `src/scrappy/graph/edges.py` - routing logic
- `src/scrappy/graph/nodes/*.py` - all node implementations

**Audit checklist:**
- [ ] Examine existing agent to understand current TUI/UX gotchas
- [ ] All nodes have path to END (no dead ends)
- [ ] All error conditions set appropriate state for routing
- [ ] Max iterations check cannot be bypassed
- [ ] Confirmation denial has clear exit path
- [ ] Tool execution failures don't cause loops

**Acceptance Criteria:**
- [ ] Audit document created with findings
- [ ] Beads created for any issues found
- [ ] No infinite loop paths exist in graph

**Verification:** Manual review + integration test covering all paths

---

## Phase 2: Concurrency & Completion Bugs

### Task 2.1: Add concurrency guard (scrappy-jr4z)

**Description:** Prevent starting second agent run while one is active. Guard `run_agent()` to reject concurrent calls.

**Files:**
- `src/scrappy/cli/textual/langgraph_bridge.py` - add `_is_running` guard

**Acceptance Criteria:**
- [ ] `_is_running` flag set at start, cleared at end (including exceptions)
- [ ] Second call while running returns early with warning
- [ ] Cancel only called once (fixes 4x "Cancelling agent..." bug)
- [ ] Unit test: concurrent call rejected

**Verification:** Manual test - rapid double-submit should not cause issues

---

### Task 2.2: Fix agent completion signaling

**Description:** Investigate why agent shows "Task Completed Successfully!" but doesn't return control to user. Likely issue with worker thread not signaling completion.

**Files:**
- `src/scrappy/cli/textual/langgraph_bridge.py` - run_agent return path
- `src/scrappy/cli/agent_manager.py` - _run_langgraph_agent completion handling

**Acceptance Criteria:**
- [ ] Agent run completes without requiring manual cancel
- [ ] Activity indicator hides on completion
- [ ] Input field re-enabled after completion
- [ ] Cancellation token cleared properly

**Verification:** Manual test - run agent task, verify prompt returns

---

### Task 2.3: Investigate copy/paste disabled bug

**Description:** Determine why copy/paste doesn't work. We built Likely focus or capture mode issue.

**Files:**
- `src/scrappy/cli/screens/main_screen.py` - input handling
- `src/scrappy/cli/textual/app.py` - key handlers
- 'src/scrappy/cli/widgets/selectable_log.py'

**Acceptance Criteria:**
- [ ] Root cause identified and documented
- [ ] Copy/paste works during agent execution
- [ ] Selection in output log still works

---

## Phase 3: UX Features (scrappy-h51l)

### Task 3.1: Terse startup message

**Description:** Replace verbose config dump with simple task display.

**Current:**
```
Code Agent - Task: how to hello world in java?
------------------------------------------------------------
LangGraph Agent Configuration:
  Mode: LangGraph (new architecture)
  Working directory: C:\Users\anyth\MINE\dev\abcde

Starting task: how to hello world in java?...
```

**Desired:**
```
Task: how to hello world in java?
```

**Files:**
- `src/scrappy/cli/agent_manager.py` - `_run_langgraph_agent()` output
- `src/scrappy/cli/textual/langgraph_bridge.py` - `_output_callback` at start

**Acceptance Criteria:**
- [ ] Single line task display at start
- [ ] No config dump (move to verbose/debug mode if needed)
- [ ] Docker status shown separately (see Task 3.6)

---

### Task 3.2: Wire activity indicator to graph execution

**Description:** Post `ActivityStateChange` messages during graph node execution to show activity in UI.

**Files:**
- `src/scrappy/cli/textual/langgraph_bridge.py` - add activity callbacks
- `src/scrappy/graph/agent.py` - expose node execution hooks (or use stream events)

**Implementation approach:**
```python
# In _run_with_streaming, after each node:
for node_name, node_output in event.items():
    # Map node name to activity state
    if node_name == "think":
        self._activity_callback(ActivityState.THINKING, "thinking...")
    elif node_name == "execute":
        self._activity_callback(ActivityState.TOOL_EXECUTION, "executing...")
    # etc.
```

**Acceptance Criteria:**
- [ ] Activity indicator shows during graph execution
- [ ] State changes: thinking -> executing -> (verify) -> complete
- [ ] Elapsed time updates every 500ms
- [ ] Indicator hides on completion/cancel

**Verification:** Visual inspection during agent run

---

### Task 3.3: Tool call display

**Description:** Show tool calls as they execute with name and key parameters.

**Format:** `[tool] tool_name: key_param_value`

**Examples:**
- `[tool] write_file: src/HelloWorld.java`
- `[tool] read_file: package.json`
- `[tool] run_command: npm install`

**Files:**
- `src/scrappy/cli/textual/langgraph_bridge.py` - add tool call output
- `src/scrappy/graph/nodes/execute.py` - expose tool call info (or extract from state)

**Acceptance Criteria:**
- [ ] Each tool call displayed on one line
- [ ] Shows tool name + primary parameter
- [ ] Truncate long paths (>50 chars) with ellipsis
- [ ] Use consistent prefix: `[tool]`

---

### Task 3.4: Tool result display

**Description:** Show tool results/errors after execution, truncated for readability.

**Format:**
- Success: Show first 3 lines or 200 chars, whichever is less
- Error: Show full error message with `[error]` prefix

**Files:**
- `src/scrappy/cli/textual/langgraph_bridge.py` - add result output
- `src/scrappy/graph/nodes/execute.py` - results already in state.tool_results

**Acceptance Criteria:**
- [ ] Results shown after tool call line
- [ ] Truncated with "..." if exceeds limit
- [ ] Errors highlighted with `[error]` prefix
- [ ] Indented under tool call for visual grouping

---

### Task 3.5: Diff display after file changes

**Description:** Show unified diff after write_file/edit_file operations.

**Format:**
```
[tool] write_file: src/HelloWorld.java
  +public class HelloWorld {
  +    public static void main(String[] args) {
  +        System.out.println("Hello World");
  +    }
  +}
```

**Files:**
- `src/scrappy/cli/textual/langgraph_bridge.py` - add diff generation
- May need to track file state before/after or use git diff

**Implementation options:**
1. Use `git diff` after each file write (requires git)
2. Track file content before tool execution, diff after
3. For new files, show full content as additions

**Acceptance Criteria:**
- [ ] Diff shown after file modification tools
- [ ] Uses unified diff format with +/- prefixes
- [ ] Truncate large diffs (>20 lines) with summary
- [ ] New files show all lines as additions
- [ ] Color coding: green for additions, red for deletions

---

### Task 3.6: Docker status display

**Description:** Show Docker availability at startup and container info during execution.

**Startup banner addition:**
```
Providers: anthropic, openai
Workspace: ~/MINE/dev/abcde
Docker: available (sandbox enabled)
```
or
```
Docker: unavailable (commands run on host)
```

**Runtime indicator:** Include in activity or tool output:
```
[tool] run_command: npm install (docker:abc123)
```

**Files:**
- `src/scrappy/cli/interactive_banner.py` - add Docker status line
- `src/scrappy/sandbox/docker_executor.py` - expose status info
- `src/scrappy/cli/textual/langgraph_bridge.py` - include container ID in output

**Acceptance Criteria:**
- [ ] Startup shows Docker available/unavailable
- [ ] Container ID shown when commands run in Docker
- [ ] Clear indication when falling back to host execution

---

### Task 3.7: Completion summary

**Description:** Show clear completion message with summary of changes.

**Format:**
```
[complete] 3.4s - 2 files changed
  + src/HelloWorld.java (new)
  ~ src/README.md (modified)
```

**Files:**
- `src/scrappy/cli/textual/langgraph_bridge.py` - completion output
- `src/scrappy/cli/agent_manager.py` - may need to pass file list

**Acceptance Criteria:**
- [ ] Shows total elapsed time
- [ ] Lists files created/modified/deleted
- [ ] Uses clear prefix: `[complete]` for success, `[failed]` for errors
- [ ] No verbose "Task Completed Successfully!" banner

---

## Phase 4: Testing & Validation

### Task 4.1: Integration test - full UX flow

**Description:** End-to-end test covering the complete UX flow.

**Test scenarios:**
- [ ] Simple task: shows activity, tool calls, completion
- [ ] File modification: shows diff
- [ ] Error case: shows error, doesn't loop
- [ ] Cancel: stops cleanly, shows cancelled state
- [ ] Docker available: shows container info
- [ ] Docker unavailable: shows fallback warning

**Verification:** `python -m pytest tests/integration/test_langgraph_ux.py -v`

---

### Task 4.2: Manual testing matrix

| Scenario | Expected | Status |
|----------|----------|--------|
| Simple coding task | Activity indicator, tool calls, diff, completion | |
| Multi-file task | Multiple diffs, file list in summary | |
| Command execution | Docker indicator if available | |
| Task with error | Error shown, no infinite loop | |
| Cancel during execution | Clean stop, "cancelled" message | |
| Rapid double-submit | Second rejected, no race condition | |
| Copy text during run | Works normally | |

---

## Dependency Graph

```
Phase 1 (Blockers):
  1.1 (mpyx) ─┬─> 1.2 (x3cs)
              └─> 1.3 (audit)

Phase 2 (Bugs):
  2.1 (concurrency) ──> 2.2 (completion) ──> 2.3 (copy/paste)

Phase 3 (UX) - depends on Phase 1 & 2:
  3.1 (terse start)
  3.2 (activity) ──> 3.3 (tool calls) ──> 3.4 (results)
  3.5 (diffs)
  3.6 (docker)
  3.7 (completion)

Phase 4 (Validation) - depends on Phase 3:
  4.1 (integration tests)
  4.2 (manual testing)
```

---

## Beads to Close on Completion

- [ ] scrappy-mpyx (P1) - unconditional think->execute edge
- [ ] scrappy-x3cs (P0) - infinite loop when LLM not configured
- [ ] scrappy-jr4z (P2) - concurrency guard
- [ ] scrappy-h51l (P1) - Phase 3.3: Wire CLI Commands to New Agent

## New Beads to Create

- [ ] Edge case audit findings (from Task 1.3)
- [ ] Any issues discovered during implementation

---

## Ready for Approval

This plan includes:
- [x] 4 phases with 13 tasks
- [x] Acceptance criteria for each task
- [x] Verification steps defined
- [x] Dependency graph mapped
- [x] Existing beads integrated

**Does this plan capture everything? Any concerns before we finalize?**
