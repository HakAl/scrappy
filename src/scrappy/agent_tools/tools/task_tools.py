"""Task management tools for agent progress tracking.

Provides persistent task tracking via markdown files, enabling the agent
to maintain state across complex multi-step operations.
"""

import re
from pathlib import Path

from scrappy.cli.protocols import (
    Task,
    TaskStatus,
    TaskPriority,
    TaskStorageProtocol,
)

from .base import ToolBase, ToolContext, ToolParameter, ToolResult


# Pattern for parsing markdown task lines
# Matches: - [ ] description, - [x] description, - [>] description
# With optional priority: - [ ] [HIGH] description
TASK_PATTERN = re.compile(
    r"^[\s]*[-*]\s*\[([ xX>])\]\s*(?:\[(HIGH|MED|LOW)\]\s*)?(.+)$"
)


class MarkdownTaskStorage:
    """File-based task storage using markdown checkboxes.

    Format:
        # Agent Tasks
        - [x] Completed task
        - [>] [HIGH] In-progress task
        - [ ] Pending task

    Markers:
        - [ ] = pending
        - [>] = in progress
        - [x] = done
    """

    def __init__(self, file_path: Path) -> None:
        """Initialize storage with file path.

        Args:
            file_path: Path to the markdown file.
        """
        self._path = file_path

    def read_tasks(self) -> list[Task]:
        """Load all tasks from the markdown file.

        Returns:
            List of Task objects, empty if file doesn't exist.
        """
        if not self._path.exists():
            return []

        tasks = []
        content = self._path.read_text(encoding="utf-8")

        for line in content.splitlines():
            task = self._parse_line(line)
            if task:
                tasks.append(task)

        return tasks

    def write_tasks(self, tasks: list[Task]) -> None:
        """Persist all tasks to the markdown file.

        Uses atomic write (temp file + rename) for safety.

        Args:
            tasks: List of tasks to save.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)

        content = self._format_tasks(tasks)
        temp = self._path.with_suffix(".tmp")
        temp.write_text(content, encoding="utf-8")
        temp.replace(self._path)

    def exists(self) -> bool:
        """Check if the task file exists."""
        return self._path.exists()

    def clear(self) -> None:
        """Delete the task file."""
        if self._path.exists():
            self._path.unlink()

    def _parse_line(self, line: str) -> Task | None:
        """Parse a single line into a Task.

        Args:
            line: A line from the markdown file.

        Returns:
            Task if line matches pattern, None otherwise.
        """
        match = TASK_PATTERN.match(line)
        if not match:
            return None

        marker = match.group(1).lower()
        if marker == "x":
            status = TaskStatus.DONE
        elif marker == ">":
            status = TaskStatus.IN_PROGRESS
        else:
            status = TaskStatus.PENDING

        priority_str = match.group(2)
        priority = TaskPriority(priority_str) if priority_str else None

        description = match.group(3).strip()

        return Task(
            description=description,
            status=status,
            priority=priority,
        )

    def _format_tasks(self, tasks: list[Task]) -> str:
        """Format tasks as markdown content.

        Args:
            tasks: List of tasks to format.

        Returns:
            Markdown string with task list.
        """
        lines = ["# Agent Tasks", ""]

        for task in tasks:
            if task.status == TaskStatus.DONE:
                checkbox = "[x]"
            elif task.status == TaskStatus.IN_PROGRESS:
                checkbox = "[>]"
            else:
                checkbox = "[ ]"

            priority = f"[{task.priority.value}] " if task.priority else ""
            lines.append(f"- {checkbox} {priority}{task.description}")

        return "\n".join(lines) + "\n"


class TaskTool(ToolBase):
    """Tool for managing agent task lists.

    Provides commands to add, list, update, delete, and clear tasks.
    Tasks are persisted to a markdown file for human readability.
    """

    def __init__(self, storage: TaskStorageProtocol | None = None) -> None:
        """Initialize the task tool.

        Args:
            storage: Optional storage implementation for testing.
                     If not provided, uses MarkdownTaskStorage.
        """
        self._injected_storage = storage

    @property
    def name(self) -> str:
        return "task"

    @property
    def description(self) -> str:
        return "Manage the agent task list for tracking progress."

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                "command",
                str,
                "Command: add, list, update, delete, clear",
                required=True,
            ),
            ToolParameter(
                "description",
                str,
                "Task description (for add)",
                required=False,
            ),
            ToolParameter(
                "task_id",
                int,
                "1-based task index (for update, delete)",
                required=False,
            ),
            ToolParameter(
                "status",
                str,
                "Status: pending, in_progress, done (for update)",
                required=False,
            ),
            ToolParameter(
                "priority",
                str,
                "Priority: high, med, low (for add)",
                required=False,
            ),
            ToolParameter(
                "filter",
                str,
                "Filter: all, pending, in_progress, done (for list)",
                required=False,
                default="all",
            ),
        ]

    def _get_storage(self, context: ToolContext) -> TaskStorageProtocol:
        """Get the storage implementation.

        Priority order:
        1. Injected storage (for testing)
        2. Context task_storage (session-scoped HUD)
        3. File-based markdown storage (legacy fallback)

        Args:
            context: Tool context with project root.

        Returns:
            TaskStorageProtocol implementation.
        """
        # 1. Test injection takes priority
        if self._injected_storage:
            return self._injected_storage

        # 2. Session-scoped storage from context (HUD)
        if context.task_storage is not None:
            return context.task_storage

        # 3. Legacy file-based storage
        from scrappy.infrastructure.paths import ScrappyPathProvider
        path_provider = ScrappyPathProvider(context.project_root)
        return MarkdownTaskStorage(path_provider.todo_file())

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        """Execute a task command.

        Args:
            context: Tool context with project root.
            **kwargs: Command parameters.

        Returns:
            ToolResult with command output.
        """
        command = kwargs.get("command", "").lower()
        storage = self._get_storage(context)

        handlers = {
            "add": self._handle_add,
            "list": self._handle_list,
            "update": self._handle_update,
            "delete": self._handle_delete,
            "clear": self._handle_clear,
        }

        handler = handlers.get(command)
        if not handler:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown command '{command}'. Use: add, list, update, delete, clear.",
            )

        return handler(storage, **kwargs)

    def _handle_add(
        self, storage: TaskStorageProtocol, **kwargs
    ) -> ToolResult:
        """Add a new task."""
        description = kwargs.get("description", "").strip()
        if not description:
            return ToolResult(
                success=False,
                output="",
                error="Task description cannot be empty.",
            )

        priority_str = kwargs.get("priority", "").upper()
        priority = None
        if priority_str:
            try:
                # Handle full names
                if priority_str == "HIGH":
                    priority = TaskPriority.HIGH
                elif priority_str in ("MED", "MEDIUM"):
                    priority = TaskPriority.MEDIUM
                elif priority_str == "LOW":
                    priority = TaskPriority.LOW
                else:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Invalid priority '{priority_str}'. Use: high, med, low.",
                    )
            except ValueError:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid priority '{priority_str}'. Use: high, med, low.",
                )

        tasks = storage.read_tasks()
        new_task = Task(
            description=description,
            status=TaskStatus.PENDING,
            priority=priority,
        )
        tasks.append(new_task)
        storage.write_tasks(tasks)

        task_num = len(tasks)
        pending_count = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
        priority_tag = f"[{priority.value}] " if priority else ""

        return ToolResult(
            success=True,
            output=f"Added task #{task_num}: {priority_tag}{description} ({pending_count} pending)",
            metadata={"tasks_changed": True, "tasks": tasks},
        )

    def _handle_list(
        self, storage: TaskStorageProtocol, **kwargs
    ) -> ToolResult:
        """List tasks with optional filtering."""
        if not storage.exists():
            return ToolResult(
                success=True,
                output="No tasks found. Use `task add` to create one.",
            )

        tasks = storage.read_tasks()
        if not tasks:
            return ToolResult(
                success=True,
                output="No tasks found. Use `task add` to create one.",
            )

        filter_by = kwargs.get("filter", "all").lower()

        if filter_by == "pending":
            filtered = [
                (i, t)
                for i, t in enumerate(tasks, 1)
                if t.status == TaskStatus.PENDING
            ]
        elif filter_by == "in_progress":
            filtered = [
                (i, t)
                for i, t in enumerate(tasks, 1)
                if t.status == TaskStatus.IN_PROGRESS
            ]
        elif filter_by == "done":
            filtered = [
                (i, t)
                for i, t in enumerate(tasks, 1)
                if t.status == TaskStatus.DONE
            ]
        else:
            filtered = list(enumerate(tasks, 1))

        if not filtered:
            return ToolResult(
                success=True,
                output=f"No {filter_by} tasks found.",
            )

        lines = []
        for idx, task in filtered:
            if task.status == TaskStatus.DONE:
                checkbox = "[x]"
            elif task.status == TaskStatus.IN_PROGRESS:
                checkbox = "[>]"
            else:
                checkbox = "[ ]"
            priority = f"[{task.priority.value}] " if task.priority else ""
            marker = " <--" if task.status == TaskStatus.IN_PROGRESS else ""
            lines.append(f"{idx}. {checkbox} {priority}{task.description}{marker}")

        return ToolResult(
            success=True,
            output="\n".join(lines),
        )

    def _handle_update(
        self, storage: TaskStorageProtocol, **kwargs
    ) -> ToolResult:
        """Update a task's status."""
        task_id = kwargs.get("task_id")
        if task_id is None:
            return ToolResult(
                success=False,
                output="",
                error="task_id is required for update.",
            )

        status_str = kwargs.get("status", "").lower()
        if not status_str:
            return ToolResult(
                success=False,
                output="",
                error="status is required for update. Use: pending, in_progress, done.",
            )

        status_map = {
            "pending": TaskStatus.PENDING,
            "in_progress": TaskStatus.IN_PROGRESS,
            "done": TaskStatus.DONE,
        }
        new_status = status_map.get(status_str)
        if new_status is None:
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid status '{status_str}'. Use: pending, in_progress, done.",
            )

        tasks = storage.read_tasks()
        if not tasks:
            return ToolResult(
                success=False,
                output="",
                error="No tasks found.",
            )

        if task_id < 1 or task_id > len(tasks):
            return ToolResult(
                success=False,
                output="",
                error=f"Task #{task_id} not found. Run `task list` to see valid IDs.",
            )

        task = tasks[task_id - 1]
        task.status = new_status
        storage.write_tasks(tasks)

        if new_status == TaskStatus.DONE:
            action = "Completed"
        elif new_status == TaskStatus.IN_PROGRESS:
            action = "Started"
        else:
            action = "Reset"

        return ToolResult(
            success=True,
            output=f"{action} task #{task_id}: {task.description}",
            metadata={"tasks_changed": True, "tasks": tasks},
        )

    def _handle_delete(
        self, storage: TaskStorageProtocol, **kwargs
    ) -> ToolResult:
        """Delete a task."""
        task_id = kwargs.get("task_id")
        if task_id is None:
            return ToolResult(
                success=False,
                output="",
                error="task_id is required for delete.",
            )

        tasks = storage.read_tasks()
        if not tasks:
            return ToolResult(
                success=False,
                output="",
                error="No tasks found.",
            )

        if task_id < 1 or task_id > len(tasks):
            return ToolResult(
                success=False,
                output="",
                error=f"Task #{task_id} not found. Run `task list` to see valid IDs.",
            )

        deleted_task = tasks.pop(task_id - 1)
        storage.write_tasks(tasks)

        remaining = len(tasks)
        return ToolResult(
            success=True,
            output=f"Deleted task #{task_id}: {deleted_task.description} ({remaining} remaining)",
            metadata={"tasks_changed": True, "tasks": tasks},
        )

    def _handle_clear(
        self, storage: TaskStorageProtocol, **kwargs
    ) -> ToolResult:
        """Clear all tasks."""
        if not storage.exists():
            return ToolResult(
                success=True,
                output="No tasks to clear.",
            )

        tasks = storage.read_tasks()
        if not tasks:
            return ToolResult(
                success=True,
                output="No tasks to clear.",
            )

        count = len(tasks)
        storage.clear()

        return ToolResult(
            success=True,
            output=f"Cleared {count} tasks",
            metadata={"tasks_changed": True, "tasks": []},
        )
