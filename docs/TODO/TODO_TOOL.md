# TODO Tool

## 1. Objective

Enable the agent to maintain persistent state of its progress. Critical for complex refactors or multi-file features where the agent "forgets" what it has done or what comes next.

## 2. Storage Strategy

- **File Path:** `.scrappy/.todo.md` (consistent everywhere)
- **Format:** Standard Markdown checkbox syntax (readable by both agent and user in IDE)

```markdown
# Agent Tasks
- [x] Analyze project structure
- [>] [HIGH] Create database schema
- [ ] Write API endpoints
```

Format:
- `[x]` = done
- `[>]` = in progress
- `[ ]` = pending
- Priority markers use text tags `[HIGH]`, `[MED]`, `[LOW]` - no emojis

## 3. Architecture (Protocol-First)

### 3.1 Protocol Definition

```python
from dataclasses import dataclass
from typing import Protocol
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskPriority(Enum):
    HIGH = "HIGH"
    MEDIUM = "MED"
    LOW = "LOW"


@dataclass
class Task:
    description: str
    status: TaskStatus
    priority: TaskPriority | None = None


class TaskStorageProtocol(Protocol):
    """Contract for task persistence."""

    def read_tasks(self) -> list[Task]:
        """Load all tasks from storage."""
        ...

    def write_tasks(self, tasks: list[Task]) -> None:
        """Persist all tasks to storage."""
        ...

    def exists(self) -> bool:
        """Check if task storage exists."""
        ...
```

### 3.2 File Implementation

```python
class MarkdownTaskStorage:
    """File-based task storage using markdown checkboxes."""

    def __init__(self, file_path: Path):
        self._path = file_path

    def read_tasks(self) -> list[Task]:
        # Parse markdown, return Task objects
        ...

    def write_tasks(self, tasks: list[Task]) -> None:
        # Atomic write to markdown
        ...

    def exists(self) -> bool:
        return self._path.exists()
```

### 3.3 Dependency Injection

```python
class TaskTool(ToolBase):
    def __init__(self, storage: TaskStorageProtocol | None = None):
        self._storage = storage  # Injected for testing

    def _get_storage(self, context: ToolContext) -> TaskStorageProtocol:
        if self._storage:
            return self._storage
        path = context.project_root / ".scrappy" / ".todo.md"
        return MarkdownTaskStorage(path)
```

## 4. File Location

- **New File:** `src/scrappy/agent_tools/tools/task_tools.py`

## 5. Tool Design: Single Tool with Commands

One tool with a `command` parameter reduces context usage vs three separate tools.

### TaskTool

- **Name:** `task`
- **Description:** "Manage the agent task list for tracking progress."
- **Parameters:**
  - `command` (str, required): One of `add`, `list`, `update`, `delete`, `clear`
  - `description` (str): Task text (for `add`)
  - `task_id` (int): 1-based task index (for `update`, `delete`)
  - `status` (str): `pending`, `in_progress`, or `done` (for `update`)
  - `priority` (str): `high`, `med`, `low` (for `add`)
  - `filter` (str): `all`, `pending`, `in_progress`, `done` (for `list`, default: `all`)

### Command Behaviors

**add:**
```
task(command="add", description="Write unit tests", priority="high")
-> "Added task #4: [HIGH] Write unit tests (3 pending)"
```

**list:**
```
task(command="list", filter="pending")
-> "1. [ ] Create database schema
   2. [ ] [HIGH] Write unit tests"
```

**update:**
```
task(command="update", task_id=1, status="in_progress")
-> "Started task #1: Create database schema"

task(command="update", task_id=1, status="done")
-> "Completed task #1: Create database schema"
```

**delete:**
```
task(command="delete", task_id=2)
-> "Deleted task #2: Write unit tests (2 remaining)"
```

**clear:**
```
task(command="clear")
-> "Cleared 3 tasks"
```

## 6. Implementation Details

### 6.1 Parser (Forgiving)

Handles user manual edits gracefully:
- Accepts `*` or `-` bullets
- Tolerates extra whitespace
- Preserves non-task lines (headers, notes)

```python
TASK_PATTERN = re.compile(
    r'^[\s]*[-*]\s*\[([ xX>])\]\s*(?:\[(HIGH|MED|LOW)\]\s*)?(.+)$'
)

def parse_line(line: str) -> Task | None:
    match = TASK_PATTERN.match(line)
    if not match:
        return None
    marker = match.group(1).lower()
    if marker == 'x':
        status = TaskStatus.DONE
    elif marker == '>':
        status = TaskStatus.IN_PROGRESS
    else:
        status = TaskStatus.PENDING
    priority = TaskPriority(match.group(2)) if match.group(2) else None
    description = match.group(3).strip()
    return Task(
        description=description,
        status=status,
        priority=priority
    )
```

### 6.2 Atomic Write

```python
def write_tasks(self, tasks: list[Task]) -> None:
    self._path.parent.mkdir(parents=True, exist_ok=True)
    temp = self._path.with_suffix('.tmp')
    temp.write_text(self._format_tasks(tasks), encoding='utf-8')
    temp.replace(self._path)  # Atomic on POSIX, near-atomic on Windows
```

## 7. Edge Cases

| Scenario | Behavior |
|----------|----------|
| File missing | `list` returns "No tasks found. Use `task add` to create one." |
| Invalid task_id | Error: "Task #5 not found. Run `task list` to see valid IDs." |
| Empty description | Error: "Task description cannot be empty." |
| Invalid command | Error: "Unknown command 'foo'. Use: add, list, update, delete, clear." |
| Clear empty list | "No tasks to clear." |
| Concurrent edit | Last write wins (acceptable for single-agent use) |

## 8. Registry Integration

In `registry_factory.py`:

```python
from .tools.task_tools import TaskTool

def create_registry(...) -> ToolRegistry:
    registry = ToolRegistry()
    # ... existing tools ...
    registry.register(TaskTool())
    return registry
```

## 9. Testing Strategy

```python
class InMemoryTaskStorage:
    """Test double for TaskStorageProtocol."""

    def __init__(self, initial: list[Task] | None = None):
        self._tasks = initial or []

    def read_tasks(self) -> list[Task]:
        return self._tasks.copy()

    def write_tasks(self, tasks: list[Task]) -> None:
        self._tasks = tasks.copy()

    def exists(self) -> bool:
        return len(self._tasks) > 0


class TestTaskToolAdd:
    def test_adds_task_to_empty_list(self):
        storage = InMemoryTaskStorage()
        tool = TaskTool(storage=storage)
        result = tool.execute(ctx, command="add", description="Do thing")
        assert result.success
        assert len(storage.read_tasks()) == 1

    def test_rejects_empty_description(self):
        storage = InMemoryTaskStorage()
        tool = TaskTool(storage=storage)
        result = tool.execute(ctx, command="add", description="")
        assert not result.success
        assert "cannot be empty" in result.error
```

## 10. UI Integration

### 10.1 Layout Position

Tasks display between `ActivityIndicator` and `input_container` in `ChatLayout`:

```
output_container (SelectableLog)
ActivityIndicator          <-- "thinking... (1.5s)"
TaskProgressWidget         <-- NEW: task list display
input_container
StatusBar
```

### 10.2 TaskProgressWidget

New widget in `src/scrappy/cli/widgets/task_progress.py`:

```python
class TaskProgressWidget(Static):
    """Displays agent task progress above input.

    Shows/hides automatically based on task presence.
    Updates reactively when tasks change.
    """

    tasks: reactive[list[Task]] = reactive(list, always_update=True)

    def __init__(self) -> None:
        super().__init__(id="task_progress")
        self._visible = False

    def render(self) -> RenderableType:
        if not self.tasks:
            return ""

        lines = []
        for i, task in enumerate(self.tasks, 1):
            if task.status == TaskStatus.DONE:
                checkbox = "[x]"
            elif task.status == TaskStatus.IN_PROGRESS:
                checkbox = "[>]"
            else:
                checkbox = "[ ]"
            priority = f"[{task.priority.value}] " if task.priority else ""
            marker = " <--" if task.status == TaskStatus.IN_PROGRESS else ""
            lines.append(f"{checkbox} {priority}{task.description}{marker}")

        return "\n".join(lines)

    def watch_tasks(self, tasks: list[Task]) -> None:
        """React to task list changes."""
        should_show = len(tasks) > 0
        if should_show and not self._visible:
            self.add_class("active")
            self._visible = True
        elif not should_show and self._visible:
            self.remove_class("active")
            self._visible = False
```

### 10.3 ChatLayout Integration

In `chat_layout.py`:

```python
def compose(self) -> ComposeResult:
    from ..textual_app import StatusBar, ActivityIndicator
    from ..widgets import TaskProgressWidget

    with Container(id="output_container"):
        yield SelectableLog(id="output", auto_scroll=True)

    yield ActivityIndicator()
    yield TaskProgressWidget()  # NEW

    with Container(id="input_container"):
        yield Label(">", id="input_prompt")
        yield TextArea(id="input", ...)

    if self._show_status_bar:
        yield StatusBar()
```

### 10.4 Update Flow

When `TaskTool.execute()` mutates tasks:

```python
def execute(self, context: ToolContext, **kwargs) -> ToolResult:
    # ... perform task mutation ...

    # Emit message to update UI
    if context.ui_bridge:
        context.ui_bridge.post_message(TasksUpdated(tasks=self._storage.read_tasks()))

    return result
```

The app handles `TasksUpdated` message:

```python
def on_tasks_updated(self, message: TasksUpdated) -> None:
    widget = self.query_one(TaskProgressWidget)
    widget.tasks = message.tasks
```

### 10.5 Styling (scrappy.tcss)

```css
TaskProgressWidget {
    height: auto;
    max-height: 8;  /* Limit to ~8 visible tasks */
    padding: 0 1;
    display: none;  /* Hidden by default */
}

TaskProgressWidget.active {
    display: block;
}

TaskProgressWidget {
    color: $text-muted;
}
```

### 10.6 Display Format

```
thinking... (8.5s)
[x] Add --dry-run flag parsing
[x] Implement CancellationToken
[>] Wire cancellation through AgentLoop  <--
[ ] Add Escape binding to main_screen
[ ] Enhance audit logging
> |
```

- `[x]` = done, `[>]` = in progress, `[ ]` = pending
- The `<--` marker highlights the in-progress task

## 11. System Prompt Addition

> When starting a complex request with multiple steps, use `task add` to create a plan. Mark steps done with `task update` as you complete them. This helps you recover if an error occurs mid-task.

## 12. CLI Integration

### 12.1 Session Start Behavior

When user starts agent with existing tasks, prompt before proceeding:

```
> /agent fix the widget

Found tasks from previous session:
  [ ] Add logout endpoint
  [ ] Write tests

Continue these tasks?  [Yes]  [No, start fresh]
```

- **Yes** - Keep tasks, agent sees them alongside new request
- **No, start fresh** - Clear task file, agent starts clean
- If no existing tasks, no prompt - agent starts immediately

### 12.2 Clear Flag

Skip the prompt and clear tasks directly:

```
/agent --clear fix the widget
```

Behavior:
1. Delete `.scrappy/.todo.md` if exists
2. Start agent with fresh state
3. No confirmation prompt

### 12.3 Implementation Location

Session startup logic in agent entry point (before agent loop):

```python
async def start_agent_session(
    user_request: str,
    clear_tasks: bool = False,  # --clear flag
) -> None:
    storage = MarkdownTaskStorage(project_root / ".scrappy" / ".todo.md")

    if clear_tasks:
        storage.clear()
    elif storage.exists():
        tasks = storage.read_tasks()
        pending = [t for t in tasks if t.status != TaskStatus.DONE]
        if pending:
            continue_tasks = await prompt_continue_tasks(pending)
            if not continue_tasks:
                storage.clear()

    # Start agent loop
    await run_agent_loop(user_request)
```

### 12.4 Prompt UI

Use existing confirmation dialog pattern:

```python
async def prompt_continue_tasks(tasks: list[Task]) -> bool:
    """Show task continuation prompt. Returns True to continue, False to clear."""
    # Display tasks
    output.write("Found tasks from previous session:")
    for task in tasks:
        checkbox = "[x]" if task.status == TaskStatus.DONE else "[ ]"
        output.write(f"  {checkbox} {task.description}")

    # Prompt
    return await confirm("Continue these tasks?", default=True)
```