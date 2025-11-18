"""
Input handler module for CLI.

Handles multiline input reading and command parsing.
"""

from typing import Tuple
from .io_interface import CLIIOProtocol


class InputHandler:
    """Handles user input parsing and multiline input reading."""

    def __init__(self, io: CLIIOProtocol):
        """
        Initialize InputHandler with IO interface.

        Args:
            io: The IO interface for reading/writing.
        """
        self.io = io

    def read_multiline_input(self, prompt_text: str = "... ") -> str:
        """
        Read multiline input from user until they enter a blank line or 'END'.

        Args:
            prompt_text: The prompt to display for continuation lines.

        Returns:
            The complete multiline string, or empty string on exception.
        """
        self.io.secho("Enter your multiline input (blank line or 'END' to finish):", fg="cyan")
        lines = []

        while True:
            try:
                line = self.io.prompt(prompt_text, default="", show_default=False)

                # Check for termination
                if line.strip() == "" or line.strip().upper() == "END":
                    break

                lines.append(line)

            except Exception:
                self.io.echo("\nMultiline input cancelled.")
                return ""

        return "\n".join(lines)

    def parse_command(self, input_str: str) -> Tuple[str, str]:
        """
        Parse a command string into command name and arguments.

        Args:
            input_str: The full input string (e.g., "/plan create feature").

        Returns:
            Tuple of (command, args) where command is lowercased.
        """
        if not input_str:
            return ("", "")

        parts = input_str.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        return (cmd, args)

    def is_command(self, input_str: str) -> bool:
        """
        Check if input string is a command (starts with /).

        Args:
            input_str: The input string to check.

        Returns:
            True if the string starts with /, False otherwise.
        """
        if not input_str:
            return False

        return input_str.startswith("/")

    def read_interactive_input(self, multiline_mode: bool = False) -> str:
        """
        Read input from user in interactive mode.

        Args:
            multiline_mode: Whether to enable multiline input mode.

        Returns:
            The user input string, stripped.
        """
        if multiline_mode:
            # Multiline input mode - read until blank line or complete input
            self.io.secho("You> ", fg="green", bold=True, nl=False)
            lines = []
            first_line = True

            while True:
                try:
                    if first_line:
                        line = self.io.prompt("", default="", show_default=False)
                        first_line = False

                        # If first line is a command, process it immediately
                        if line.strip().startswith("/"):
                            return line.strip()

                        # If line doesn't end with continuation marker (\), treat as complete
                        if not line.rstrip().endswith("\\"):
                            lines.append(line)
                            break
                        else:
                            # Remove the continuation marker and continue reading
                            lines.append(line.rstrip()[:-1])
                    else:
                        self.io.secho("... ", fg="green", nl=False)
                        line = self.io.prompt("", default="", show_default=False)

                        # Blank line terminates input
                        if line.strip() == "":
                            break

                        # Check for continuation marker
                        if line.rstrip().endswith("\\"):
                            lines.append(line.rstrip()[:-1])
                        else:
                            lines.append(line)
                            break

                except Exception:
                    return ""

            return "\n".join(lines).strip()
        else:
            # Single-line input mode
            result = self.io.prompt(
                self.io.style("You", fg="green", bold=True),
                default="",
                show_default=False
            )
            return result.strip()
