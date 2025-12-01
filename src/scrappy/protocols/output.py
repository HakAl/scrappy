"""
Unified output protocol hierarchy.

This module defines a clean protocol hierarchy for all output abstractions,
enabling consistent behavior across CLI, TUI, and test modes.

Protocol Hierarchy:
- BaseOutputProtocol: Core message-level logging (info, warn, error, success)
- FormattedOutputProtocol: Extends BaseOutputProtocol with styled output and user interaction
- RichRenderableProtocol: Rich-specific rendering for TUI mode

Following SOLID principles:
- Interface Segregation: Each protocol is focused and minimal
- Dependency Inversion: Consumers depend on protocols, not implementations
- Open/Closed: New implementations can be added without modifying existing code
"""

from typing import Protocol, Optional, runtime_checkable

# TYPE_CHECKING import for RenderableType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import RenderableType


@runtime_checkable
class BaseOutputProtocol(Protocol):
    """Core output protocol for message-level logging.

    This is the minimal contract for any output implementation.
    All output abstractions should support at least these four
    message types.

    Implementations:
    - ConsoleOutput: Logs to Python logging
    - NullOutput: Discards all messages
    - CapturingOutput: Captures messages for testing
    - OrchestratorOutputAdapter: Routes to Textual OutputSink

    Example:
        def notify(output: BaseOutputProtocol, message: str, is_error: bool) -> None:
            if is_error:
                output.error(message)
            else:
                output.info(message)
    """

    def info(self, message: str) -> None:
        """Output an informational message.

        Args:
            message: Information message to output
        """
        ...

    def warn(self, message: str) -> None:
        """Output a warning message.

        Args:
            message: Warning message to output
        """
        ...

    def error(self, message: str) -> None:
        """Output an error message.

        Args:
            message: Error message to output
        """
        ...

    def success(self, message: str) -> None:
        """Output a success message.

        Args:
            message: Success message to output
        """
        ...


@runtime_checkable
class FormattedOutputProtocol(BaseOutputProtocol, Protocol):
    """Extended protocol for formatted output with styling and user interaction.

    Extends BaseOutputProtocol with:
    - Styled text output (colors, bold)
    - User prompts and confirmations

    This protocol is suitable for CLI applications that need both
    operational logging and interactive user communication.

    Implementations:
    - RichOutput: Uses Rich library for styling
    - ClickOutput: Uses Click library for styling
    - TestOutput: Captures output for testing
    - Output: Factory-delegating implementation

    Example:
        def greet(output: FormattedOutputProtocol) -> None:
            output.print("Welcome!", color="green", bold=True)
            name = output.prompt("What is your name?", default="User")
            output.success(f"Hello, {name}!")
    """

    def print(
        self,
        text: str = "",
        color: Optional[str] = None,
        bold: bool = False,
        newline: bool = True
    ) -> None:
        """Print text with optional styling.

        Args:
            text: Text to print
            color: Color name (red, green, yellow, cyan, etc.)
            bold: Whether to make text bold
            newline: Whether to append newline
        """
        ...

    def style(
        self,
        text: str,
        color: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Return styled text for inline use.

        Args:
            text: Text to style
            color: Color name
            bold: Whether to make text bold

        Returns:
            Styled text string (format depends on implementation)
        """
        ...

    def prompt(
        self,
        text: str,
        default: str = ""
    ) -> str:
        """Get user input with prompt.

        Args:
            text: Prompt text
            default: Default value if no input

        Returns:
            User input or default
        """
        ...

    def confirm(
        self,
        text: str,
        default: bool = False
    ) -> bool:
        """Get yes/no confirmation.

        Args:
            text: Confirmation prompt
            default: Default value

        Returns:
            True for yes, False for no
        """
        ...


@runtime_checkable
class RichRenderableProtocol(Protocol):
    """Protocol for Rich-specific renderable output.

    This protocol enables posting Rich renderables (Panel, Table, Text, etc.)
    to output implementations that support them, such as Textual TUI.

    Note: This protocol is separate from BaseOutputProtocol because not all
    output implementations support Rich renderables. Use this protocol when
    you specifically need Rich rendering capabilities.

    Implementations:
    - TextualOutputAdapter: Posts to Textual app via messages
    - OutputSink (from cli/protocols.py): Abstract TUI output

    Example:
        def show_panel(output: RichRenderableProtocol, content: str) -> None:
            from rich.panel import Panel
            panel = Panel(content, title="Info")
            output.post_renderable(panel)
    """

    def post_output(self, content: str) -> None:
        """Post plain text output.

        Args:
            content: Plain text string to display
        """
        ...

    def post_renderable(self, obj: "RenderableType") -> None:
        """Post Rich renderable (Panel, Table, Text, etc.).

        Rich renderables preserve formatting, colors, and structure.
        Examples: Panel with borders, Table with columns, styled Text.

        Args:
            obj: Rich renderable object (Panel, Table, Text, etc.)
        """
        ...
