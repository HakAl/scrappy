"""
Input handler module for CLI.

Handles multiline input reading and command parsing.
"""

from typing import Optional, Tuple, TYPE_CHECKING
from .io_interface import CLIIOProtocol
from .config.defaults import MAX_INPUT_CHARS, MAX_INPUT_LINES

if TYPE_CHECKING:
    from .command_history import CommandHistoryProtocol


class InputTooLongError(Exception):
    """Raised when user input exceeds maximum allowed length."""

    def __init__(self, char_count: int, line_count: int, max_chars: int, max_lines: int):
        self.char_count = char_count
        self.line_count = line_count
        self.max_chars = max_chars
        self.max_lines = max_lines
        super().__init__(
            f"Input too long: {char_count:,} chars ({max_chars:,} max) "
            f"or {line_count} lines ({max_lines} max)"
        )


class InputHandler:
    """Handles user input parsing and multiline input reading.

    Note: Command history navigation is handled by ScrappyApp in TUI mode,
    not by this class. The _history attribute is kept for compatibility
    but is not used for navigation.
    """

    def __init__(
        self,
        io: CLIIOProtocol,
        history: Optional["CommandHistoryProtocol"] = None
    ):
        """
        Initialize InputHandler with IO interface.

        Args:
            io: The IO interface for reading/writing.
            history: Optional command history (unused, kept for compatibility).
        """
        self.io = io
        self._history = history

    def read_multiline_input(self, prompt_text: str = "... ") -> str:
        """
        Read multiline input from user until they enter a blank line or 'END'.

        Args:
            prompt_text: The prompt to display for continuation lines.

        Returns:
            The complete multiline string, or empty string on exception.
        """
        self.io.secho("Enter your multiline input (blank line or 'END' to finish):", fg=self.io.theme.primary)
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

    def _read_first_line(self) -> str:
        """Read the first line of input with history support if available.

        Returns:
            The first line of user input
        """
        if self._history:
            # Use prompt_toolkit with history navigation
            # The green "You> " prompt is part of the message
            try:
                return self._history.prompt_with_history(
                    message="\x1b[32;1mYou> \x1b[0m",  # Green bold
                    default=""
                )
            except (EOFError, KeyboardInterrupt):
                return ""
        else:
            # Fall back to standard IO
            self.io.secho("You> ", fg=self.io.theme.accent, bold=True, nl=False)
            return self.io.prompt("", default="", show_default=False)

    def read_interactive_input(self) -> str:
        """
        Read input from user in interactive mode.

        If command history is configured, supports:
        - Up/Down arrows: Navigate through command history
        - Ctrl+R: Reverse search through history

        Always supports multiline via backslash continuation.

        Returns:
            The user input string, stripped.

        Raises:
            InputTooLongError: If input exceeds MAX_INPUT_CHARS or MAX_INPUT_LINES.
        """
        lines = []
        first_line = True

        while True:
            try:
                if first_line:
                    line = self._read_first_line()
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
                    # Continuation lines use standard IO (no history nav)
                    self.io.secho("... ", fg=self.io.theme.accent, nl=False)
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

        result = "\n".join(lines).strip()

        # Validate length before returning
        if len(result) > MAX_INPUT_CHARS:
            raise InputTooLongError(
                char_count=len(result),
                line_count=len(lines),
                max_chars=MAX_INPUT_CHARS,
                max_lines=MAX_INPUT_LINES
            )
        if len(lines) > MAX_INPUT_LINES:
            raise InputTooLongError(
                char_count=len(result),
                line_count=len(lines),
                max_chars=MAX_INPUT_CHARS,
                max_lines=MAX_INPUT_LINES
            )

        return result
