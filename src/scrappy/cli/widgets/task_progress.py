"""TaskProgressWidget - Displays agent task progress above input."""

from textual.reactive import reactive
from textual.widgets import Static
from rich.console import RenderableType
from rich.text import Text

from scrappy.protocols.tasks import Task, TaskStatus


class TaskProgressWidget(Static):
    """Displays agent task progress above input.

    Shows/hides automatically based on task presence.
    Updates reactively when tasks change.

    Display format:
        [x] Completed task
        [>] In-progress task  <--
        [ ] Pending task
    """

    DEFAULT_CSS = """
    TaskProgressWidget {
        height: auto;
        max-height: 8;
        padding: 0 1;
        display: none;
        color: $text-muted;
        background: $background;
        border: none;
    }

    TaskProgressWidget.active {
        display: block;
        border: none;
    }
    """

    tasks: reactive[list[Task]] = reactive(list, always_update=True)

    def __init__(self) -> None:
        """Initialize the task progress widget."""
        super().__init__(id="task_progress")
        self._visible = False

    def render(self) -> RenderableType:
        """Render the task list.

        Returns:
            Rich Text object with formatted task list.
        """
        if not self.tasks:
            return ""

        text = Text()
        for i, task in enumerate(self.tasks):
            if i > 0:
                text.append("\n")

            # Checkbox based on status
            if task.status == TaskStatus.DONE:
                text.append("[x] ", style="green")
            elif task.status == TaskStatus.IN_PROGRESS:
                text.append("[>] ", style="yellow")
            else:
                text.append("[ ] ", style="dim")

            # Priority tag if present
            if task.priority:
                text.append(f"[{task.priority.value}] ", style="bold")

            # Description
            text.append(task.description)

            # In-progress marker
            if task.status == TaskStatus.IN_PROGRESS:
                text.append("  <--", style="yellow bold")

        return text

    def watch_tasks(self, tasks: list[Task]) -> None:
        """React to task list changes.

        Args:
            tasks: The new task list.
        """
        should_show = len(tasks) > 0
        if should_show and not self._visible:
            self.add_class("active")
            self._visible = True
        elif not should_show and self._visible:
            self.remove_class("active")
            self._visible = False

    def update_tasks(self, tasks: list[Task]) -> None:
        """Update the displayed tasks.

        Convenience method for external callers.

        Args:
            tasks: New list of tasks to display.
        """
        self.tasks = tasks
