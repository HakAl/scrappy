"""
Thread-safe messages for Textual TUI communication.

These messages enable safe communication between worker threads and
the main Textual event loop. Worker threads post messages, and the
main thread handles them to update UI components.
"""

from typing import TYPE_CHECKING, Any, Optional

from textual.message import Message

from ..protocols import ActivityState

if TYPE_CHECKING:
    from ..core import CLI


class WriteOutput(Message):
    """Message for thread-safe output to RichLog widget."""

    def __init__(self, content: str) -> None:
        super().__init__()
        self.content = content


class WriteRenderable(Message):
    """Message for posting Rich renderables to RichLog widget."""

    def __init__(self, renderable: Any) -> None:
        super().__init__()
        self.renderable = renderable


class RequestInlineInput(Message):
    """Message to request inline input capture."""

    def __init__(
        self,
        prompt_id: str,
        message: str,
        input_type: str,
        default: str = ""
    ) -> None:
        super().__init__()
        self.prompt_id = prompt_id
        self.message = message
        self.input_type = input_type
        self.default = default


class IndexingProgress(Message):
    """Message for semantic search indexing progress updates."""

    def __init__(
        self,
        message: str,
        progress: int = 0,
        total: int = 0,
        complete: bool = False
    ) -> None:
        super().__init__()
        self.message = message
        self.progress = progress
        self.total = total
        self.complete = complete


class ActivityStateChange(Message):
    """Message for thread-safe activity indicator updates.

    Used to communicate activity state changes from worker threads to the main
    thread's ActivityIndicator widget. Supports elapsed time tracking for
    long-running operations like Q/A processing and codebase re-indexing.

    Args:
        state: Current activity state (IDLE, THINKING, SYNCING, TOOL_EXECUTION)
        message: Optional descriptive message for the activity
        elapsed_ms: Elapsed time in milliseconds (0 for new activities)
    """

    def __init__(
        self,
        state: ActivityState,
        message: str = "",
        elapsed_ms: int = 0
    ) -> None:
        super().__init__()
        self.state = state
        self.message = message
        self.elapsed_ms = elapsed_ms


class TasksUpdated(Message):
    """Message for updating the task progress widget.

    Posted when the agent's task list changes (add, update, delete, clear).
    The main thread handles this by updating the TaskProgressWidget.

    Args:
        tasks: Current list of tasks to display.
    """

    def __init__(self, tasks: list) -> None:
        super().__init__()
        self.tasks = tasks


class CLIReady(Message):
    """Message posted when CLI initialization completes in background thread.

    Used by deferred initialization to signal that CLI is ready for use.
    Posted via call_from_thread() to safely update state on main thread.

    Args:
        cli: The fully initialized CLI instance
        error: Error message if initialization failed, None on success
    """

    def __init__(self, cli: Optional["CLI"] = None, error: Optional[str] = None) -> None:
        super().__init__()
        self.cli = cli
        self.error = error


class CancelRequested(Message):
    """Message posted when user presses ESC to cancel operations.

    Screens handle this to perform cleanup (hide activity indicators, etc.).
    The app-level on_key handler posts this after cancelling the agent.
    """
    pass
