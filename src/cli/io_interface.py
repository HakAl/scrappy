"""
I/O abstraction layer for CLI operations.

This module provides a protocol for CLI I/O operations and implementations
for both real CLI usage (ClickIO) and testing (TestIO).

Usage:
    # In production code
    from src.cli.io_interface import ClickIO
    io = ClickIO()
    io.styled_echo("Hello!", fg="green")

    # In tests
    from src.cli.io_interface import TestIO
    io = TestIO(inputs=["user input"], confirmations=[True])
    result = my_function(io)
    assert "expected" in io.get_output()
"""

from typing import Protocol, Optional, List, Dict, Any
import click


class CLIIOProtocol(Protocol):
    """Protocol defining CLI I/O operations.

    This protocol abstracts all CLI input/output operations to enable
    testability and potential future alternative implementations.
    """

    def echo(self, message: str = "", nl: bool = True) -> None:
        """Output a message to the console.

        Args:
            message: The text to output
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
        """Output a styled message with color and formatting.

        Args:
            message: The text to output
            fg: Foreground color (e.g., 'red', 'green', 'cyan')
            bold: Whether to make text bold
            nl: Whether to append a newline (default True)
        """
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


class TestIO:
    """Test implementation of CLIIOProtocol for testing CLI code.

    Captures all output and provides preset inputs for deterministic testing.

    Usage:
        io = TestIO(
            inputs=["user response", "another input"],
            confirmations=[True, False]
        )

        # Run code that uses io
        my_cli_function(io)

        # Verify output
        assert "expected text" in io.get_output()
        assert io.get_styled_outputs()[0]['fg'] == 'green'
    """

    def __init__(
        self,
        inputs: Optional[List[str]] = None,
        confirmations: Optional[List[bool]] = None
    ):
        """Initialize TestIO with preset inputs and confirmations.

        Args:
            inputs: List of input strings to return from prompt/input_line
            confirmations: List of boolean values to return from confirm
        """
        self._inputs: List[str] = list(inputs) if inputs else []
        self._confirmations: List[bool] = list(confirmations) if confirmations else []
        self._output_buffer: List[str] = []
        self._styled_outputs: List[Dict[str, Any]] = []
        self._input_index = 0
        self._confirm_index = 0

    def echo(self, message: str = "", nl: bool = True) -> None:
        """Capture output to internal buffer."""
        if nl:
            self._output_buffer.append(message + "\n")
        else:
            self._output_buffer.append(message)

    def styled_echo(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Capture styled output and record styling info."""
        # Record styling for verification
        self._styled_outputs.append({
            'text': message,
            'fg': fg,
            'bold': bold,
            'nl': nl
        })

        # Also add to output buffer
        if nl:
            self._output_buffer.append(message + "\n")
        else:
            self._output_buffer.append(message)

    def style(
        self,
        text: str,
        fg: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Return text unchanged (no actual styling in tests)."""
        return text

    def prompt(
        self,
        text: str,
        default: str = "",
        show_default: bool = True
    ) -> str:
        """Return preset input or default."""
        if self._input_index < len(self._inputs):
            result = self._inputs[self._input_index]
            self._input_index += 1
            return result
        return default

    def confirm(
        self,
        text: str,
        default: bool = False
    ) -> bool:
        """Return preset confirmation or default."""
        if self._confirm_index < len(self._confirmations):
            result = self._confirmations[self._confirm_index]
            self._confirm_index += 1
            return result
        return default

    def input_line(self) -> str:
        """Return preset input or empty string."""
        if self._input_index < len(self._inputs):
            result = self._inputs[self._input_index]
            self._input_index += 1
            return result
        return ""

    def get_output(self) -> str:
        """Get all captured output as a single string."""
        return "".join(self._output_buffer)

    def get_output_lines(self) -> List[str]:
        """Get captured output as list of lines."""
        full_output = self.get_output()
        return full_output.split("\n") if full_output else []

    def get_styled_outputs(self) -> List[Dict[str, Any]]:
        """Get list of all styled output records.

        Returns:
            List of dicts with 'text', 'fg', 'bold', 'nl' keys
        """
        return self._styled_outputs

    def clear_output(self) -> None:
        """Clear all captured output."""
        self._output_buffer = []
        self._styled_outputs = []

    def add_input(self, value: str) -> None:
        """Add an input value to the queue."""
        self._inputs.append(value)

    def add_confirmation(self, value: bool) -> None:
        """Add a confirmation value to the queue."""
        self._confirmations.append(value)


class ClickIO:
    """Real CLI implementation using click library.

    This is the production implementation that actually outputs to
    the terminal and reads user input.
    """

    def echo(self, message: str = "", nl: bool = True) -> None:
        """Output message using click.echo."""
        click.echo(message, nl=nl)

    def styled_echo(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Output styled message using click.secho."""
        click.secho(message, fg=fg, bold=bold, nl=nl)

    def style(
        self,
        text: str,
        fg: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Return styled text using click.style."""
        return click.style(text, fg=fg, bold=bold)

    def prompt(
        self,
        text: str,
        default: str = "",
        show_default: bool = True
    ) -> str:
        """Get user input using click.prompt."""
        return click.prompt(text, default=default, show_default=show_default)

    def confirm(
        self,
        text: str,
        default: bool = False
    ) -> bool:
        """Get confirmation using click.confirm."""
        return click.confirm(text, default=default)

    def input_line(self) -> str:
        """Read raw input line."""
        return input()
