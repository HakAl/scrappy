"""
Protocol definitions for CLI handlers.

This module defines the common interface that all CLI handlers must implement,
enabling consistent behavior, testability, and type checking across the CLI layer.

This is the canonical location for all CLI-related protocols including:
- Activity indicators (ActivityState, ActivityIndicatorProtocol)
- Clipboard integration (ClipboardProtocol)
- CLI I/O operations (CLIIOProtocol)
- Output formatting (BaseOutputProtocol, FormattedOutputProtocol, RichRenderableProtocol)
- Task management (Task, TaskStatus, TaskPriority, TaskStorageProtocol)
- Status bar (StatusBarUpdaterProtocol)
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol, Dict, Any, List, Optional, Callable, runtime_checkable, Generator
from contextlib import contextmanager
from ..orchestrator.protocols import Orchestrator

if TYPE_CHECKING:
    from rich.console import Console, RenderableType
    from textual.widget import Widget
    from .unified_io import ProgressTrackerProtocol, StreamWriter


# =============================================================================
# Activity Protocols (from protocols/activity.py)
# =============================================================================

class ActivityState(Enum):
    """Activity states for UI indicators."""
    IDLE = "idle"
    THINKING = "thinking"
    SYNCING = "syncing"
    TOOL_EXECUTION = "tool_execution"


@runtime_checkable
class ActivityIndicatorProtocol(Protocol):
    """Protocol for activity indicator widgets.

    Defines the contract for UI components that display current activity state
    with elapsed time tracking. Used to show user feedback during long-running
    operations like Q/A processing and codebase re-indexing.
    """

    def show(self, state: ActivityState, message: str = "") -> None:
        """Show the activity indicator with state and message."""
        ...

    def update_elapsed(self, elapsed_ms: int) -> None:
        """Update elapsed time display."""
        ...

    def hide(self) -> None:
        """Hide the activity indicator."""
        ...

    @property
    def is_visible(self) -> bool:
        """Whether indicator is currently visible."""
        ...


# =============================================================================
# Clipboard Protocol
# =============================================================================

@runtime_checkable
class ClipboardProtocol(Protocol):
    """Protocol defining text clipboard operations."""

    def copy_text(self, text: str) -> None:
        """Write text to the system clipboard."""
        ...

    def paste_text(self) -> str:
        """Read text from the system clipboard."""
        ...


@runtime_checkable
class MouseReportingPolicyProtocol(Protocol):
    """Single owner of the terminal mouse-reporting decision."""

    @property
    def selection_mode(self) -> bool:
        """True when mouse reporting is suspended for native selection."""
        ...

    def enable(self) -> None:
        """Assert mouse reporting on unless selection mode is active."""
        ...

    def disable_for_selection(self) -> None:
        """Suspend mouse reporting so the terminal can handle native selection."""
        ...

    def restore(self) -> None:
        """Exit selection mode and re-enable mouse reporting."""
        ...


# =============================================================================
# CLI I/O Protocol (from protocols/io.py)
# =============================================================================

class CLIIOProtocol(Protocol):
    """Protocol defining CLI I/O operations.

    This protocol abstracts all CLI input/output operations to enable
    testability and potential future alternative implementations.

    Implementations:
    - UnifiedIO: Real CLI implementation with Rich formatting
    - TestIO: Test implementation for unit tests
    - MockIO: Mock implementation in tests/helpers.py
    """

    def echo(self, message: str = "", nl: bool = True) -> None:
        """Output a message to the console."""
        ...

    def secho(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Output a styled message with color and formatting."""
        ...

    def style(
        self,
        text: str,
        fg: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Return styled text for inline use."""
        ...

    def prompt(
        self,
        text: str,
        default: str = "",
        show_default: bool = True
    ) -> str:
        """Get user input with a prompt."""
        ...

    def confirm(
        self,
        text: str,
        default: bool = False
    ) -> bool:
        """Get yes/no confirmation from user."""
        ...

    def input_line(self) -> str:
        """Read a raw line of input."""
        ...

    def table(
        self,
        headers: List[str],
        rows: List[List[str]],
        title: Optional[str] = None
    ) -> None:
        """Display a table with headers and rows."""
        ...

    def panel(
        self,
        content: str,
        title: Optional[str] = None,
        border_style: str = "blue"
    ) -> None:
        """Display content in a panel with optional title."""
        ...


# =============================================================================
# Output Protocols (from protocols/output.py)
# =============================================================================

@runtime_checkable
class BaseOutputProtocol(Protocol):
    """Core output protocol for message-level logging.

    This is the minimal contract for any output implementation.
    """

    def info(self, message: str) -> None:
        """Output an informational message."""
        ...

    def warn(self, message: str) -> None:
        """Output a warning message."""
        ...

    def error(self, message: str) -> None:
        """Output an error message."""
        ...

    def success(self, message: str) -> None:
        """Output a success message."""
        ...


@runtime_checkable
class FormattedOutputProtocol(BaseOutputProtocol, Protocol):
    """Extended protocol for formatted output with styling and user interaction."""

    def print(
        self,
        text: str = "",
        color: Optional[str] = None,
        bold: bool = False,
        newline: bool = True
    ) -> None:
        """Print text with optional styling."""
        ...

    def style(
        self,
        text: str,
        color: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Return styled text for inline use."""
        ...

    def prompt(
        self,
        text: str,
        default: str = ""
    ) -> str:
        """Get user input with prompt."""
        ...

    def confirm(
        self,
        text: str,
        default: bool = False
    ) -> bool:
        """Get yes/no confirmation."""
        ...


@runtime_checkable
class RichRenderableProtocol(Protocol):
    """Protocol for Rich-specific renderable output.

    This protocol enables posting Rich renderables (Panel, Table, Text, etc.)
    to output implementations that support them, such as Textual TUI.
    """

    def post_output(self, content: str) -> None:
        """Post plain text output."""
        ...

    def post_renderable(self, obj: "RenderableType") -> None:
        """Post Rich renderable (Panel, Table, Text, etc.)."""
        ...


# Backward compatibility alias
OutputSink = RichRenderableProtocol


@runtime_checkable
class StreamingOutputProtocol(Protocol):
    """Protocol for async streaming output with token-by-token rendering."""

    async def stream_start(self, metadata: Optional[dict[str, Any]] = None) -> None:
        """Signal the start of a streaming response."""
        ...

    async def stream_token(self, token: str) -> None:
        """Output a single token from the stream."""
        ...

    async def stream_end(self, metadata: Optional[dict[str, Any]] = None) -> None:
        """Signal the end of a streaming response."""
        ...


# =============================================================================
# Task Protocols (from protocols/tasks.py)
# =============================================================================

class TaskStatus(Enum):
    """Status of a task in the task list."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskPriority(Enum):
    """Priority level for tasks."""
    HIGH = "HIGH"
    MEDIUM = "MED"
    LOW = "LOW"


@dataclass
class Task:
    """A single task in the agent's task list."""
    description: str
    status: TaskStatus
    priority: TaskPriority | None = None

    def __post_init__(self) -> None:
        """Validate task on creation."""
        if not self.description or not self.description.strip():
            raise ValueError("Task description cannot be empty")


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

    def clear(self) -> None:
        """Remove all tasks and delete storage."""
        ...


class InMemoryTaskStorage:
    """In-memory task storage for session-scoped HUD."""

    def __init__(
        self,
        initial: list[Task] | None = None,
        initial_task: str | None = None,
    ) -> None:
        self._tasks: list[Task] = list(initial) if initial else []
        if initial_task and initial_task.strip():
            self._tasks.insert(0, Task(
                description=initial_task.strip(),
                status=TaskStatus.IN_PROGRESS,
            ))
        self._exists = len(self._tasks) > 0

    def read_tasks(self) -> list[Task]:
        """Return copy of tasks."""
        return list(self._tasks)

    def write_tasks(self, tasks: list[Task]) -> None:
        """Store copy of tasks."""
        self._tasks = list(tasks)
        self._exists = True

    def exists(self) -> bool:
        """Check if storage has been written to."""
        return self._exists

    def clear(self) -> None:
        """Clear all tasks."""
        self._tasks = []
        self._exists = False


# =============================================================================
# Progress Protocol (from protocols/progress.py)
# =============================================================================

@runtime_checkable
class StatusBarUpdaterProtocol(Protocol):
    """Protocol for updating status bar displays.

    This protocol defines the minimal interface needed to update a status bar
    widget. It abstracts the concrete implementation (e.g., Textual widgets)
    to enable infrastructure components to update status without depending
    on the CLI layer.
    """

    def update_status(self, content: str) -> None:
        """Update the status bar content."""
        ...


@runtime_checkable
class CLIHandlerProtocol(Protocol):
    """Protocol defining common interface for all CLI handlers.

    All CLI handlers should implement this protocol to ensure consistent
    behavior and enable proper type checking. The protocol defines:

    - orchestrator: Reference to the Orchestrator for LLM operations
    - Lifecycle methods: initialize() and cleanup()
    - Diagnostic methods: get_status() and reset()

    Example implementation:
        class MyHandler:
            def __init__(self, orchestrator):
                self.orchestrator = orchestrator
                self._state = {}

            def initialize(self) -> None:
                self._state = {'ready': True}

            def cleanup(self) -> None:
                self._state = {}

            def get_status(self) -> Dict[str, Any]:
                return {'name': 'MyHandler', 'state': self._state}

            def reset(self) -> None:
                self._state = {}

            # Additional custom methods specific to this handler
            def do_something(self):
                ...
    """

    orchestrator: Orchestrator

    def initialize(self) -> None:
        """Initialize the handler.

        Called after construction to set up any required state, connections,
        or resources. This is separate from __init__ to allow for deferred
        initialization and easier testing.

        Implementations should:
        - Set up any caches or internal data structures
        - Establish connections to external services if needed
        - Prepare the handler for use
        """
        ...

    def cleanup(self) -> None:
        """Clean up handler resources.

        Called when the handler is being shut down or the CLI session ends.
        Implementations should release any held resources.

        Implementations should:
        - Close any open connections
        - Release any held resources
        - Clear any sensitive data from memory
        """
        ...

    def get_status(self) -> Dict[str, object]:
        """Return handler status and diagnostic information.

        Provides insight into the handler's current state for debugging,
        monitoring, or display purposes.

        Returns:
            Dictionary containing status information. Common keys include:
            - 'name': Handler class name
            - 'initialized': Whether initialize() has been called
            - 'call_count': Number of operations performed
            - 'error_count': Number of errors encountered
            - Additional handler-specific metrics
        """
        ...

    def reset(self) -> None:
        """Reset handler state.

        Clears internal state to initial values without requiring
        reconstruction. Useful for starting fresh within a session
        or between tests.

        Implementations should:
        - Reset counters and metrics to zero
        - Clear caches and histories
        - Return to post-initialize state
        """
        ...


@runtime_checkable
class DisplayFormatterProtocol(Protocol):
    """
    Protocol for display formatting.

    Abstracts display formatting to enable testing without actual
    terminal output and support different output formats.

    Implementations:
    - RichFormatter: Rich text formatting with colors and styles
    - PlainFormatter: Plain text without formatting
    - HTMLFormatter: HTML-formatted output
    - MarkdownFormatter: Markdown-formatted output

    Example:
        def display_results(formatter: DisplayFormatterProtocol, data: Dict[str, Any]) -> str:
            return formatter.format(data)
    """

    def format(self, data: Any, format_type: str = "default") -> str:
        """
        Format data for display.

        Args:
            data: Data to format
            format_type: Type of formatting to apply

        Returns:
            Formatted string
        """
        ...

    def format_table(
        self,
        data: List[Dict[str, Any]],
        columns: Optional[List[str]] = None,
    ) -> str:
        """
        Format data as table.

        Args:
            data: List of row dictionaries
            columns: Column names to display (None for all)

        Returns:
            Formatted table string
        """
        ...

    def format_error(
        self,
        error: Exception,
        include_traceback: bool = False,
    ) -> str:
        """
        Format error message.

        Args:
            error: Exception to format
            include_traceback: Whether to include traceback

        Returns:
            Formatted error string
        """
        ...

    def format_list(
        self,
        items: List[Any],
        numbered: bool = False,
    ) -> str:
        """
        Format list of items.

        Args:
            items: List of items to format
            numbered: Use numbered list instead of bullets

        Returns:
            Formatted list string
        """
        ...

    def format_code(
        self,
        code: str,
        language: Optional[str] = None,
    ) -> str:
        """
        Format code block.

        Args:
            code: Code to format
            language: Programming language for syntax highlighting

        Returns:
            Formatted code string
        """
        ...

    def format_json(
        self,
        data: Dict[str, Any],
        indent: int = 2,
    ) -> str:
        """
        Format JSON data.

        Args:
            data: Dictionary to format as JSON
            indent: Indentation spaces

        Returns:
            Formatted JSON string
        """
        ...


@runtime_checkable
class InputValidatorProtocol(Protocol):
    """
    Protocol for input validation.

    Abstracts input validation to enable testing with controlled
    validation and support different validation strategies.

    Implementations:
    - SchemaValidator: Validates against JSON schema
    - RegexValidator: Validates using regex patterns
    - CustomValidator: Custom validation logic
    - NoOpValidator: Always validates successfully

    Example:
        def validate_user_input(validator: InputValidatorProtocol, input: str) -> bool:
            if not validator.validate(input):
                errors = validator.get_errors()
                raise ValueError(f"Invalid input: {errors}")
            return True
    """

    def validate(
        self,
        value: Any,
        rules: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Validate input value.

        Args:
            value: Value to validate
            rules: Optional validation rules

        Returns:
            True if valid, False otherwise
        """
        ...

    def sanitize(
        self,
        value: str,
        strategy: str = "default",
    ) -> str:
        """
        Sanitize input value.

        Args:
            value: Value to sanitize
            strategy: Sanitization strategy to use

        Returns:
            Sanitized value
        """
        ...

    def get_errors(self) -> List[str]:
        """
        Get validation errors from last validation.

        Returns:
            List of error messages
        """
        ...

    def add_rule(
        self,
        name: str,
        validator_func: Callable[[Any], bool],
        error_message: str,
    ) -> None:
        """
        Add custom validation rule.

        Args:
            name: Rule name
            validator_func: Function that returns True if valid
            error_message: Error message if validation fails
        """
        ...

    def remove_rule(self, name: str) -> bool:
        """
        Remove validation rule.

        Args:
            name: Rule name to remove

        Returns:
            True if rule was removed, False if not found
        """
        ...

    def validate_many(
        self,
        values: List[Any],
        rules: Optional[Dict[str, Any]] = None,
    ) -> Dict[int, List[str]]:
        """
        Validate multiple values.

        Args:
            values: List of values to validate
            rules: Optional validation rules

        Returns:
            Dictionary mapping indices to error lists
            Empty dict if all valid
        """
        ...


@runtime_checkable
class RichOutputProtocol(Protocol):
    """Extended Rich-specific output operations.

    Provides Rich library features: panels, tables, syntax highlighting,
    rules, progress bars, and spinners. Implementations may vary in
    visual representation (CLI vs TUI) but must maintain consistent API.
    """

    def panel(
        self,
        content: str,
        title: Optional[str] = None,
        border_style: str = "blue"
    ) -> None:
        """Display content in a panel with optional title.

        Args:
            content: Content to display in panel
            title: Optional panel title
            border_style: Border color/style (default 'blue')
        """
        ...

    def table(
        self,
        headers: List[str],
        rows: List[List[str]],
        title: Optional[str] = None
    ) -> None:
        """Display a table with headers and rows.

        Args:
            headers: Column header strings
            rows: Row data (each row is a list of strings)
            title: Optional table title
        """
        ...

    def syntax(
        self,
        code: str,
        language: str = "python",
        line_numbers: bool = False
    ) -> None:
        """Display syntax-highlighted code.

        Args:
            code: Code to highlight
            language: Programming language for highlighting
            line_numbers: Whether to show line numbers
        """
        ...

    def rule(self, title: Optional[str] = None) -> None:
        """Display a horizontal rule.

        Args:
            title: Optional title to display in the rule
        """
        ...

    @contextmanager
    def progress(
        self,
        total: int,
        description: str = "Progress"
    ) -> Generator["ProgressTrackerProtocol", None, None]:
        """Create a progress bar context manager.

        Note: Visual representation varies by output mode.
        CLI: Rich animated progress bar
        TUI: Text-based progress messages

        Args:
            total: Total number of steps
            description: Description text

        Yields:
            Progress tracker for updating progress
        """
        ...

    @contextmanager
    def spinner(
        self,
        text: str = "Working...",
        spinner_style: str = "dots"
    ) -> Generator[None, None, None]:
        """Create a spinner for indeterminate operations.

        Note: Visual representation varies by output mode.
        CLI: Rich animated spinner
        TUI: Start/end messages or no-op

        Args:
            text: Text to display next to spinner
            spinner_style: Spinner animation style (CLI only)

        Yields:
            None (spinner runs automatically)
        """
        ...

    @contextmanager
    def stream(self) -> Generator["StreamWriter", None, None]:
        """Create a streaming output context.

        Yields:
            StreamWriter for streaming text output
        """
        ...


@runtime_checkable
class UnifiedIOProtocol(CLIIOProtocol, RichOutputProtocol, Protocol):
    """Complete IO protocol combining basic CLI and Rich features.

    This protocol unifies:
    - Basic CLI operations (echo, secho, style, prompt, confirm, input_line)
    - Rich features (panel, table, syntax, rule)
    - Context managers (progress, spinner, stream)

    Implementations must support both direct console output (CLI mode)
    and OutputSink routing (Textual/TUI mode).
    """

    @property
    def console(self) -> "Console":
        """Get the underlying Rich Console instance.

        Returns:
            Console instance for this IO implementation
        """
        ...


@runtime_checkable
class StatusComponentProtocol(Protocol):
    """Protocol for status bar components that can be dynamically added/removed.

    Status components are displayed in the footer status bar area of the TUI.
    They provide real-time information like progress indicators, token counters,
    or other status information.

    IMPORTANT: Implementations should cache their widget instance and update it
    in place rather than creating new widgets on each call. This prevents
    flickering and improves performance.

    Example implementation:
        class ProgressIndicator:
            def __init__(self):
                self._active = False
                self._widget: Optional[Horizontal] = None

            @property
            def component_id(self) -> str:
                return "progress"

            @property
            def is_visible(self) -> bool:
                return self._active

            @property
            def widget(self) -> Widget:
                if self._widget is None:
                    self._widget = Horizontal(...)
                return self._widget

            def update_widget(self) -> None:
                if self._widget is not None:
                    # Update widget state in place
                    ...
    """

    @property
    def component_id(self) -> str:
        """Unique identifier for this component.

        Returns:
            String identifier used for registration and lookup.
        """
        ...

    @property
    def is_visible(self) -> bool:
        """Whether this component should be displayed.

        Returns:
            True if component should be shown in status bar.
        """
        ...

    @property
    def widget(self) -> "Widget":
        """Return the cached widget instance.

        The widget should be created once and reused. Use update_widget()
        to modify its state rather than recreating it.

        Returns:
            Textual Widget instance for this component.
        """
        ...

    def update_widget(self) -> None:
        """Update widget state without recreating.

        Called when component data changes. Modify the cached widget's
        properties directly (e.g., label.update(), progress.progress = X).
        """
        ...


@runtime_checkable
class UserInteractionProtocol(Protocol):
    """Protocol for user interactions that may block.

    This abstraction allows CLI mode to use blocking prompts
    while TUI mode uses modal dialogs via ThreadSafeAsyncBridge.

    The key insight: in CLI mode, prompt()/confirm() block the main thread.
    In TUI mode, worker threads cannot block - they must use the bridge
    to request modal dialogs from the main thread.

    Implementations:
    - CLIUserInteraction: Blocking prompts for CLI mode
    - TUIUserInteraction: Modal dialogs via bridge for TUI mode
    - AutoApproveInteraction: Fallback with sensible defaults

    Example:
        def get_user_confirmation(interaction: UserInteractionProtocol) -> bool:
            if interaction.confirm("Proceed with changes?", default=False):
                path = interaction.prompt("Enter output path:", default="output.txt")
                return True
            return False
    """

    def confirm(self, question: str, default: bool = False) -> bool:
        """Get yes/no confirmation from user.

        Args:
            question: Question to ask user
            default: Default value if user provides no input

        Returns:
            True for yes/confirm, False for no/cancel
        """
        ...

    def prompt(self, message: str, default: str = "") -> str:
        """Get text input from user.

        Args:
            message: Prompt message to display
            default: Default value if user provides no input

        Returns:
            User's text input or default value
        """
        ...


@runtime_checkable
class AgentManagerProtocol(Protocol):
    """Protocol for code agent management.

    Defines the contract for managing code agent execution with
    human-in-the-loop approval for file operations.

    Implementations should:
    - Initialize the code agent with proper configuration
    - Handle dry-run vs live execution modes
    - Manage git checkpoints for rollback capability
    - Coordinate user approval for file modifications
    - Track and display execution progress

    Example:
        def execute_agent_task(mgr: AgentManagerProtocol, task: str):
            mgr.run_agent(task)
    """

    orchestrator: Orchestrator

    def run_agent(self, task: str) -> None:
        """Run the code agent on a task.

        Args:
            task: Natural language description of the coding task
        """
        ...
