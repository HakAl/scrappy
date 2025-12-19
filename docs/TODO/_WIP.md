# Agent HUD (Heads-Up Display) Implementation Plan

## Problem Statement

LLMs suffer from **Semantic Drift** - forgetting the original goal after 5-6 turns of debugging.
Currently, the agent must explicitly call `task list` to see its own task state, and task data
persists across sessions causing stale/confusing context.

## Solution: Session-Scoped HUD

Inject dynamic state as a user message every iteration, with task storage scoped to the
current session via ToolContext.

---

## Architecture

### Current Flow
```
TaskTool._get_storage()
    -> MarkdownTaskStorage(.scrappy/TODO.md)  # Persists across sessions (dangerous)

AgentContextFactory.build_context()
    -> No task/file/outcome state injected
```

### Proposed Flow
```
CodeAgent.run(task)
    -> Seeds task_storage with initial user task (HUD never empty on Turn 0)

AgentLoop (each iteration)
    -> Increments tool_context.turn
    -> AgentContextFactory.build_context()
        -> Reads from ToolContext:
            - task_storage (current tasks)
            - working_set (files touched with line ranges)
        -> Reads from ConversationState:
            - recent_outcomes (last 3 tool results)
        -> Injects HUD as USER message (recency bias)
```

---

## HUD Format

Injected as a **user message** before conversation history (exploits LLM recency bias):

```markdown
=== CURRENT STATE ===

[OBJECTIVE]
- [>] Fix the login bug (in progress)

[TASKS]
- [x] Read existing auth implementation
- [ ] Update tests for new auth flow

[WORKING SET]
- src/auth/controller.py (Read L10-50 @ Turn 2, Modified @ Turn 4)
- tests/test_auth.py (Read full file @ Turn 3)

[RECENT OUTCOMES]
- Turn 4: write_file src/auth/controller.py - Success
- Turn 3: run_command pytest - Failed: "...AssertionError: expected 200 but got 401"
```

---

## Design Decisions (Resolved)

| Decision | Answer | Rationale |
|----------|--------|-----------|
| Working set limit | 5 files | Cognitive load: 5 files + 3 tasks + 3 outcomes = ~11 items max |
| Outcome trail depth | 3 items | Enough to detect loops: [Fail, Fail, Fail] |
| Outcome truncation | 150 chars (tail) | Stack traces bury the lead at the end |
| Success truncation | Short "(Success)" | No detail needed |
| File persistence | No | Audit logs are persistence; avoid stale TODO.md |
| Turn tracking | ToolContext.turn | Increment in AgentLoop, cleaner than kwargs |
| HUD placement | User message | Recency bias - end of system prompt gets ignored |
| Initial task | Auto-seed from user prompt | HUD never empty on Turn 0 |
| Line tracking | Yes, track line windows | Prevents "I know the whole file" hallucination |

---

## Implementation Phases

### Phase 1: Session-Scoped Task Storage + Turn Tracking

**Files to modify:**

1. `src/scrappy/agent_tools/tools/base.py`
   ```python
   @dataclass
   class ToolContext:
       # ... existing fields ...
       task_storage: Optional[TaskStorageProtocol] = None
       working_set: Optional[WorkingSet] = None
       turn: int = 0  # Incremented each iteration
   ```

2. `src/scrappy/agent_tools/tools/task_tools.py`
   ```python
   class InMemoryTaskStorage:
       """Session-scoped task storage."""
       def __init__(self, initial_task: Optional[str] = None):
           self._tasks: List[Task] = []
           if initial_task:
               self._tasks.append(Task(
                   description=initial_task,
                   status=TaskStatus.IN_PROGRESS
               ))

       def read_tasks(self) -> List[Task]: ...
       def write_tasks(self, tasks: List[Task]) -> None: ...
       def exists(self) -> bool: return True
       def clear(self) -> None: self._tasks.clear()
   ```
   - Update `TaskTool._get_storage()` to prefer `context.task_storage`

3. `src/scrappy/agent/core.py`
   ```python
   def _create_default_tool_context(self, initial_task: Optional[str] = None):
       return ToolContext(
           # ... existing ...
           task_storage=InMemoryTaskStorage(initial_task=initial_task),
           working_set=WorkingSet(),
           turn=0,
       )
   ```

4. `src/scrappy/agent/agent_loop.py`
   - Increment `self._tool_context.turn` at start of each iteration

### Phase 2: Working Set with Line Tracking

**Data structures:**

```python
@dataclass
class FileAccess:
    path: str
    line_start: Optional[int] = None  # None = full file
    line_end: Optional[int] = None
    read_turn: Optional[int] = None
    write_turn: Optional[int] = None

@dataclass
class WorkingSet:
    _files: Dict[str, FileAccess] = field(default_factory=dict)
    _max_files: int = 5

    def record_read(self, path: str, turn: int,
                    line_start: Optional[int] = None,
                    line_end: Optional[int] = None) -> None:
        """Record file read, tracking line window."""
        if path in self._files:
            access = self._files[path]
            access.read_turn = turn
            access.line_start = line_start
            access.line_end = line_end
        else:
            self._files[path] = FileAccess(
                path=path, line_start=line_start, line_end=line_end,
                read_turn=turn
            )
        self._enforce_limit()

    def record_write(self, path: str, turn: int) -> None:
        """Record file write."""
        if path in self._files:
            self._files[path].write_turn = turn
        else:
            self._files[path] = FileAccess(path=path, write_turn=turn)
        self._enforce_limit()

    def remove_deleted(self, path: str) -> None:
        """Remove file from working set (ghost file prevention)."""
        self._files.pop(path, None)

    def get_recent(self) -> List[FileAccess]:
        """Get files ordered by most recent access."""
        return sorted(
            self._files.values(),
            key=lambda f: max(f.read_turn or 0, f.write_turn or 0),
            reverse=True
        )[:self._max_files]

    def _enforce_limit(self) -> None:
        """Drop oldest files beyond limit."""
        if len(self._files) > self._max_files:
            oldest = sorted(
                self._files.items(),
                key=lambda kv: max(kv[1].read_turn or 0, kv[1].write_turn or 0)
            )[0][0]
            del self._files[oldest]
```

**Files to modify:**

1. `src/scrappy/agent_tools/tools/file_tools.py`
   ```python
   # In ReadFileTool.execute():
   if context.working_set:
       context.working_set.record_read(
           path, context.turn,
           line_start=offset, line_end=offset+limit if limit else None
       )

   # In WriteFileTool.execute():
   if context.working_set:
       context.working_set.record_write(path, context.turn)
   ```

### Phase 3: Outcome Trail

**Data structures:**

```python
@dataclass
class OutcomeRecord:
    turn: int
    tool: str
    success: bool
    summary: str  # Smart-truncated output

def smart_truncate(output: str, success: bool) -> str:
    """Truncate output - tail for errors (stack traces)."""
    if success:
        return "(Success)"
    if len(output) <= 150:
        return output
    return "..." + output[-147:]  # Tail is more important
```

**Files to modify:**

1. `src/scrappy/agent/types.py`
   ```python
   @dataclass
   class ConversationState:
       # ... existing ...
       recent_outcomes: List[OutcomeRecord] = field(default_factory=list)
   ```

2. `src/scrappy/agent/agent_loop.py`
   ```python
   def _handle_action_executed(self, ...):
       # ... existing ...

       # Record outcome for HUD
       outcome = OutcomeRecord(
           turn=state.iteration,
           tool=result.action,
           success=result.success,
           summary=smart_truncate(result.output, result.success)
       )
       state.recent_outcomes.append(outcome)

       # Keep only last 3
       if len(state.recent_outcomes) > 3:
           state.recent_outcomes = state.recent_outcomes[-3:]
   ```

### Phase 4: HUD Injection

**Files to modify:**

1. `src/scrappy/agent/context_factory.py`
   ```python
   def __init__(self, ..., tool_context: ToolContext):
       self._tool_context = tool_context

   def build_hud_message(self, state: ConversationState) -> dict:
       """Build HUD as a user message for recency bias."""
       lines = ["=== CURRENT STATE ===", ""]

       # Tasks
       if self._tool_context.task_storage:
           tasks = self._tool_context.task_storage.read_tasks()
           if tasks:
               lines.append("[TASKS]")
               for task in tasks:
                   marker = {"done": "[x]", "in_progress": "[>]", "pending": "[ ]"}
                   lines.append(f"- {marker[task.status.value]} {task.description}")
               lines.append("")

       # Working Set
       if self._tool_context.working_set:
           files = self._tool_context.working_set.get_recent()
           if files:
               lines.append("[WORKING SET]")
               for f in files:
                   parts = [f.path]
                   if f.read_turn:
                       if f.line_start is not None:
                           parts.append(f"Read L{f.line_start}-{f.line_end} @ Turn {f.read_turn}")
                       else:
                           parts.append(f"Read full @ Turn {f.read_turn}")
                   if f.write_turn:
                       parts.append(f"Modified @ Turn {f.write_turn}")
                   lines.append(f"- {parts[0]} ({', '.join(parts[1:])})")
               lines.append("")

       # Recent Outcomes
       if state.recent_outcomes:
           lines.append("[RECENT OUTCOMES]")
           for o in reversed(state.recent_outcomes):  # Most recent first
               status = "Success" if o.success else f"Failed: {o.summary}"
               lines.append(f"- Turn {o.turn}: {o.tool} - {status}")

       return {"role": "user", "content": "\n".join(lines)}
   ```

2. `src/scrappy/agent/core.py`
   - Pass `tool_context` to AgentContextFactory

3. `src/scrappy/agent/agent_loop.py`
   - Insert HUD message at start of conversation each iteration

---

## Safeguards

1. **Ghost File Prevention**
   - In `run_command` result handling, detect `rm`/`del` patterns
   - Call `working_set.remove_deleted(path)` for deleted files

2. **Empty HUD Handling**
   - If no tasks, no files, no outcomes: skip HUD injection entirely
   - Avoids confusing empty state block

3. **Turn 0 Seeding**
   - User's initial task auto-added as in-progress task
   - HUD is meaningful from the first iteration

---

## Test Strategy

1. **InMemoryTaskStorage tests**
   - Session isolation (new storage = empty)
   - Initial task seeding works
   - CRUD operations match MarkdownTaskStorage behavior

2. **WorkingSet tests**
   - Records reads/writes with turn numbers and line ranges
   - Respects size limit (5 files)
   - Orders by recency
   - Ghost file removal works

3. **OutcomeRecord tests**
   - Smart truncation: success = short, failure = 150 char tail
   - Keeps only last 3

4. **HUD formatting tests**
   - Format matches spec
   - Empty sections omitted
   - Line ranges display correctly

5. **Integration test**
   - Full agent run with HUD enabled
   - Verify HUD appears as user message
   - Verify no cross-session pollution

---

## Dependencies (already exist)

- `TaskStorageProtocol` in `src/scrappy/protocols/tasks.py`
- `ConversationState.failed_commands` tracking (extend to outcomes)
- `AgentContextFactory` rebuilds context each iteration
- `ToolContext` created fresh per agent run

---

## Estimated Effort

| Phase | Description | Effort |
|-------|-------------|--------|
| Phase 1 | Session-scoped tasks + turn tracking | 30 min |
| Phase 2 | Working set with line tracking | 45 min |
| Phase 3 | Outcome trail with smart truncation | 30 min |
| Phase 4 | HUD injection as user message | 45 min |
| Testing | Unit + integration tests | 60 min |

**Total: ~3.5 hours**

---

## Rollout Plan

1. Implement Phase 1 (task storage + turn tracking)
2. Implement Phase 2 (working set)
3. Implement Phase 3 (outcome trail)
4. Implement Phase 4 (HUD injection)
5. Run integration tests
6. Deploy and monitor for drift reduction
