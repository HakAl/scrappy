"""
Protocol definitions for CLI handlers.

This module defines the common interface that all CLI handlers must implement,
enabling consistent behavior, testability, and type checking across the CLI layer.
"""

from typing import TYPE_CHECKING, Protocol, Dict, Any, List, Optional, Callable, runtime_checkable, Generator
from contextlib import contextmanager
from enum import Enum
from .io_interface import CLIIOProtocol
from ..orchestrator.protocols import Orchestrator
from ..protocols.output import RichRenderableProtocol

if TYPE_CHECKING:
    from rich.console import Console, RenderableType
    from rich.layout import Layout
    from textual.widget import Widget


# Backward compatibility alias
# OutputSink is now an alias to RichRenderableProtocol from the centralized protocols module
# New code should import RichRenderableProtocol directly from scrappy.protocols.output
OutputSink = RichRenderableProtocol


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

    Implementations should:
    - Show/hide indicator based on activity state
    - Track and display elapsed time during operations
    - Prevent flicker with delayed show threshold
    - Update display without blocking main thread

    Example:
        def show_activity(indicator: ActivityIndicatorProtocol, state: ActivityState):
            indicator.show(state, "Processing query...")
            # ... long operation ...
            indicator.update_elapsed(1500)  # 1.5 seconds
            indicator.hide()
    """

    def show(self, state: ActivityState, message: str = "") -> None:
        """Show the activity indicator with state and message.

        Args:
            state: Current activity state
            message: Optional descriptive message
        """
        ...

    def update_elapsed(self, elapsed_ms: int) -> None:
        """Update elapsed time display.

        Args:
            elapsed_ms: Elapsed time in milliseconds
        """
        ...

    def hide(self) -> None:
        """Hide the activity indicator."""
        ...

    @property
    def is_visible(self) -> bool:
        """Whether indicator is currently visible.

        Returns:
            True if indicator is displayed
        """
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
class DashboardProtocol(Protocol):
    """
    Protocol for live dashboard display.

    Defines the contract for dashboard implementations that provide
    real-time visualization of agent activity across multiple panels.

    Dashboard implementations should support:
    - State management (idle, thinking, executing, scanning)
    - Multi-panel layout (agent state, thought process, terminal, context)
    - Content updates and accumulation
    - Terminal output capture with line limits
    - Context tracking (active files and token usage)
    - Rich Live display integration

    Implementations:
    - RichDashboard: Full Rich-based dashboard with 4 panels
    - MockDashboard: Test double for testing without actual display

    Example:
        def run_agent_with_dashboard(dashboard: DashboardProtocol):
            dashboard.set_state("thinking", "Planning next step...")
            dashboard.update_thought_process("Analyzing requirements...")
            dashboard.append_terminal("$ ls -la")
            dashboard.update_context(["main.py", "test.py"], 1500)

            # Get renderable for Rich.Live
            with Live(dashboard.get_renderable()):
                # Long-running operation
                ...
    """

    console: "Console"

    def get_layout(self) -> "Layout":
        """
        Get the dashboard layout structure.

        Returns:
            Rich Layout object containing all panels
        """
        ...

    def get_panel_names(self) -> List[str]:
        """
        Get list of all panel names in the dashboard.

        Returns:
            List of panel name strings (e.g., ['agent_state', 'thought_process', 'terminal', 'context'])
        """
        ...

    def get_state(self) -> str:
        """
        Get current agent state.

        Returns:
            Current state string (one of: idle, thinking, executing, scanning)
        """
        ...

    def set_state(self, state: str, message: str = "") -> None:
        """
        Set agent state with optional custom message.

        Args:
            state: Agent state (must be one of: idle, thinking, executing, scanning)
            message: Optional custom message to display in agent state panel

        Raises:
            ValueError: If state is not valid
        """
        ...

    def get_panel_title(self, panel_name: str) -> str:
        """
        Get title for a specific panel.

        Args:
            panel_name: Name of the panel

        Returns:
            Panel title string
        """
        ...

    def get_panel_content(self, panel_name: str) -> str:
        """
        Get current content of a panel.

        Args:
            panel_name: Name of the panel

        Returns:
            Current panel content as string
        """
        ...

    def get_panel_style(self, panel_name: str) -> str:
        """
        Get current style for a panel based on state.

        Args:
            panel_name: Name of the panel

        Returns:
            Rich style string (e.g., 'green', 'yellow', 'dim')
        """
        ...

    def update_agent_state(self, content: str) -> None:
        """
        Update agent state panel content directly.

        Args:
            content: New content for agent state panel
        """
        ...

    def update_thought_process(self, content: str) -> None:
        """
        Replace thought process panel content.

        Args:
            content: New content (replaces existing)
        """
        ...

    def append_thought(self, content: str) -> None:
        """
        Append content to thought process panel.

        Args:
            content: Content to append
        """
        ...

    def update_terminal(self, content: str) -> None:
        """
        Replace terminal panel content.

        Args:
            content: New content (replaces existing)
        """
        ...

    def append_terminal(self, content: str) -> None:
        """
        Append content to terminal panel, preserving history.

        Args:
            content: Content to append
        """
        ...

    def update_context(self, active_files: List[str], tokens_used: int) -> None:
        """
        Update context panel with files and token count.

        Args:
            active_files: List of active file paths
            tokens_used: Total tokens consumed
        """
        ...

    def update_active_files(self, files: List[str]) -> None:
        """
        Update only the active files list, preserving token count.

        Args:
            files: List of active file paths
        """
        ...

    def update_tokens(self, tokens: int) -> None:
        """
        Update only the token count, preserving files.

        Args:
            tokens: Total tokens consumed
        """
        ...

    def capture_output(self, content: str, stream: str = "stdout") -> None:
        """
        Capture output from stdout or stderr to terminal panel.

        Args:
            content: Output content to capture
            stream: 'stdout' or 'stderr'
        """
        ...

    def capture_command(self, command: str, output: str) -> None:
        """
        Capture a command and its output to terminal panel.

        Args:
            command: The command that was run
            output: The command's output
        """
        ...

    def clear_terminal(self) -> None:
        """Clear terminal output panel."""
        ...

    def clear_thought_process(self) -> None:
        """Clear thought process panel."""
        ...

    def get_renderable(self) -> "Layout":
        """
        Get renderable layout for use with Rich Live display.

        Returns:
            Rich Layout ready for Live display
        """
        ...

    def reset(self) -> None:
        """Reset dashboard to initial state."""
        ...


@runtime_checkable
class DisplayManagerProtocol(Protocol):
    """
    Protocol for managing display output coordination.

    Coordinates between simple RichIO output and full RichDashboard display,
    allowing seamless switching between modes based on configuration or context.

    The DisplayManager provides:
    - Access to RichIO for standard output
    - Optional RichDashboard for live visualizations
    - Mode detection and switching
    - Context managers for dashboard lifecycle

    Implementations:
    - DisplayManager: Production implementation with mode switching
    - MockDisplayManager: Test double for testing

    Example:
        def run_operation(display: DisplayManagerProtocol):
            io = display.get_io()
            io.echo("Starting...")

            if display.is_dashboard_enabled():
                dashboard = display.get_dashboard()
                dashboard.set_state("executing")

                with display.live_dashboard():
                    # Long-running operation with live updates
                    dashboard.append_terminal("$ command")
    """

    def get_io(self) -> "CLIIOProtocol":
        """
        Get the IO interface for output.

        Returns:
            CLIIOProtocol implementation (typically RichIO)
        """
        ...

    def get_dashboard(self) -> Optional["DashboardProtocol"]:
        """
        Get the dashboard interface if enabled.

        Returns:
            DashboardProtocol implementation or None if dashboard disabled
        """
        ...

    def is_dashboard_enabled(self) -> bool:
        """
        Check if dashboard mode is enabled.

        Returns:
            True if dashboard is available and enabled
        """
        ...

    def enable_dashboard(self) -> None:
        """Enable dashboard mode for this display manager."""
        ...

    def disable_dashboard(self) -> None:
        """Disable dashboard mode for this display manager."""
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
    ) -> Generator["ProgressTracker", None, None]:
        """Create a progress bar context manager.

        Note: Visual representation varies by output mode.
        CLI: Rich animated progress bar
        TUI: Text-based progress messages

        Args:
            total: Total number of steps
            description: Description text

        Yields:
            ProgressTracker for updating progress
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


@runtime_checkable
class MultiProviderProtocol(Protocol):
    """Protocol for multi-provider operations.

    Defines the contract for coordinating queries across multiple
    LLM providers, enabling synthesis and comparison of responses.

    Implementations should:
    - Query multiple providers concurrently
    - Synthesize responses into coherent output
    - Allow delegation to specific providers
    - Handle provider failures gracefully

    Example:
        def multi_query(mp: MultiProviderProtocol, query: str):
            mp.synthesize_mode()  # Interactive synthesis
            # or
            mp.delegate_mode("openai")  # Delegate to specific provider
    """

    orchestrator: Orchestrator

    def synthesize_mode(self) -> None:
        """Interactive synthesis mode.

        Prompts user for query and provider selection, then
        queries multiple providers and synthesizes responses.
        """
        ...

    def delegate_mode(self, args: str) -> None:
        """Delegate to specific provider.

        Args:
            args: Provider specification and optional query
        """
        ...
