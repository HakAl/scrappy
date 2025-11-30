"""
Shared I/O protocol for CLI operations.

This module provides the protocol definition for CLI I/O operations.
By placing it in the shared protocols layer, both agent and CLI modules
can depend on it without creating circular dependencies.

Architecture:
- src/protocols/io.py - Defines CLIIOProtocol (this file)
- src/cli/io_interface.py - Provides TestIO implementation
- src/agent/core.py - Uses CLIIOProtocol for dependency injection
- src/context/* - Uses CLIIOProtocol for progress reporting

This follows the Dependency Inversion Principle:
Both high-level (agent) and low-level (CLI) modules depend on
abstractions (protocols), not on each other.
"""

from typing import Protocol, Optional, List


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
        """Output a message to the console.

        Args:
            message: The text to output
            nl: Whether to append a newline (default True)
        """
        ...

    def secho(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Output a styled message with color and formatting.

        Args:
            message: The text to output
            fg: Foreground color (e.g., 'red', 'green', 'cyan')
            bold: Whether to make text bold
            nl: Whether to append a newline (default True)
        """
        ...

    def styled_echo(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Alias for secho() for backwards compatibility."""
        ...

    def style(
        self,
        text: str,
        fg: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Return styled text for inline use.

        Args:
            text: The text to style
            fg: Foreground color
            bold: Whether to make text bold

        Returns:
            The styled text string
        """
        ...

    def prompt(
        self,
        text: str,
        default: str = "",
        show_default: bool = True
    ) -> str:
        """Get user input with a prompt.

        Args:
            text: The prompt text to display
            default: Default value if user enters nothing
            show_default: Whether to show the default in the prompt

        Returns:
            The user's input or default value
        """
        ...

    def confirm(
        self,
        text: str,
        default: bool = False
    ) -> bool:
        """Get yes/no confirmation from user.

        Args:
            text: The confirmation prompt
            default: Default value if user just presses enter

        Returns:
            True for yes, False for no
        """
        ...

    def input_line(self) -> str:
        """Read a raw line of input.

        Returns:
            The input line (without trailing newline)
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
            headers: List of column header strings
            rows: List of row data (each row is a list of strings)
            title: Optional table title
        """
        ...

    def panel(
        self,
        content: str,
        title: Optional[str] = None,
        border_style: str = "blue"
    ) -> None:
        """Display content in a panel with optional title.

        Args:
            content: The content to display in the panel
            title: Optional panel title
            border_style: Border color/style (default 'blue')
        """
        ...
