"""
I/O abstraction layer for CLI operations.

This module provides test implementations of CLIIOProtocol for testing.
The protocol itself is defined in scrappy/protocols/io.py to avoid circular dependencies.

Usage:
    # In tests
    from scrappy.cli.io_interface import TestIO
    # or from tests.helpers import MockIO
    io = TestIO(inputs=["user input"], confirmations=[True])
    result = my_function(io)
    assert "expected" in io.get_output()
"""

from typing import Optional, List, Dict, Any

# Re-export the protocol from cli protocols (canonical location); many modules
# import CLIIOProtocol from this module. The redundant alias marks the re-export
# as intentional so lint does not strip it.
from .protocols import CLIIOProtocol as CLIIOProtocol


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

    def secho(
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

    def table(
        self,
        headers: List[str],
        rows: List[List[str]],
        title: Optional[str] = None
    ) -> None:
        """Display a table (captured as text output)."""
        if title:
            self._output_buffer.append(f"{title}\n")

        # Simple table formatting
        self._output_buffer.append(" | ".join(headers) + "\n")
        self._output_buffer.append("-" * (len(" | ".join(headers))) + "\n")
        for row in rows:
            self._output_buffer.append(" | ".join(row) + "\n")

    def panel(
        self,
        content: str,
        title: Optional[str] = None,
        border_style: str = "blue"
    ) -> None:
        """Display a panel (captured as text output)."""
        if title:
            self._output_buffer.append(f"=== {title} ===\n")
        self._output_buffer.append(content + "\n")
