"""
Output formatting for agent tool results.

Provides injectable formatters to colorize and style output.
"""

from typing import Protocol, Optional, TYPE_CHECKING

# Rich imports only for RichDirectoryFormatter
try:
    from rich.console import Console
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    Console = None
    Text = None

if TYPE_CHECKING:
    from src.infrastructure.console_factory import ConsoleFactoryProtocol


class OutputFormatter(Protocol):
    """Protocol for output formatters."""

    def format(self, output: str, output_type: str = "default") -> str:
        """Format the output string."""
        ...


class NullFormatter:
    """Formatter that returns output unchanged."""

    def format(self, output: str, output_type: str = "default") -> str:
        """Return output unchanged."""
        return output


class GitOutputFormatter:
    """
    Colorizes git command output for better readability.

    Supports output types: log, diff, blame, show
    """

    def __init__(self, output_interface=None):
        """Initialize formatter with output interface.

        Args:
            output_interface: Output interface for styling. If None, returns unstyled output.
        """
        self._output = output_interface

    def format(self, output: str, output_type: str = "log") -> str:
        """
        Add colors to git output for better readability.

        Args:
            output: Raw git command output
            output_type: Type of git output (log, diff, blame, show)

        Returns:
            Colorized output string (or unchanged if no output interface)
        """
        if not self._output:
            return output

        lines = output.split('\n')
        colored_lines = []

        for line in lines:
            colored_line = self._colorize_line(line, output_type)
            colored_lines.append(colored_line)

        return '\n'.join(colored_lines)

    def _colorize_line(self, line: str, output_type: str) -> str:
        """Colorize a single line based on output type."""
        if output_type == "log":
            return self._colorize_log_line(line)
        elif output_type == "diff":
            return self._colorize_diff_line(line)
        elif output_type == "blame":
            return self._colorize_blame_line(line)
        elif output_type == "show":
            return self._colorize_show_line(line)
        else:
            return line

    def _colorize_log_line(self, line: str) -> str:
        """Colorize git log output."""
        # Color commit hashes and decorations
        if line and len(line) > 7 and line[:7].replace(' ', '').isalnum():
            parts = line.split(' ', 1)
            if len(parts) >= 1:
                # Commit hash in yellow
                colored = self._output.style(parts[0], color='yellow')
                if len(parts) > 1:
                    colored += ' ' + parts[1]
                return colored
        return line

    def _colorize_diff_line(self, line: str) -> str:
        """Colorize git diff output."""
        if line.startswith('+++') or line.startswith('---'):
            return self._output.style(line, color='cyan', bold=True)
        elif line.startswith('+'):
            return self._output.style(line, color='green')
        elif line.startswith('-'):
            return self._output.style(line, color='red')
        elif line.startswith('@@'):
            return self._output.style(line, color='cyan')
        elif line.startswith('diff --git'):
            return self._output.style(line, color='bright_white', bold=True)
        return line

    def _colorize_blame_line(self, line: str) -> str:
        """Colorize git blame output."""
        if line and '^' in line or (len(line) > 8 and line[:8].replace(' ', '').isalnum()):
            parts = line.split(' ', 1)
            if len(parts) >= 1:
                colored = self._output.style(parts[0], color='yellow')
                if len(parts) > 1:
                    colored += ' ' + parts[1]
                return colored
        return line

    def _colorize_show_line(self, line: str) -> str:
        """Colorize git show output."""
        if line.startswith('commit '):
            return self._output.style(line, color='yellow', bold=True)
        elif line.startswith('Author:'):
            return self._output.style(line, color='cyan')
        elif line.startswith('Date:'):
            return self._output.style(line, color='cyan')
        elif line.startswith('=== COMMIT'):
            return self._output.style(line, color='yellow', bold=True)
        elif line.startswith('Message:'):
            return self._output.style(line, color='bright_white', bold=True)
        elif '|' in line and ('+' in line or '-' in line):
            # File stat lines
            return self._output.style(line, color='cyan')
        elif line.startswith('+'):
            return self._output.style(line, color='green')
        elif line.startswith('-'):
            return self._output.style(line, color='red')
        return line


class RichDirectoryFormatter:
    """
    Rich-based formatter for directory tree output.

    Provides Rich-styled directory tree output as alternative to click.style.
    Handles directories, files with extension-based coloring, and file sizes.

    NOTE: This class uses a Rich Console internally for RENDERING text with
    ANSI codes, not for output. The console.print() call is wrapped in
    console.capture() to convert Rich Text objects to strings. Actual output
    happens elsewhere when these strings are displayed via the IO interface.

    This means this class is safe to use in both CLI and TUI modes - it only
    generates formatted strings, it does not output them.
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        console_factory: Optional["ConsoleFactoryProtocol"] = None,
    ):
        """Initialize with optional Rich console or factory.

        Args:
            console: Optional Rich Console instance for rendering text.
                    If not provided, will use console_factory or create default.
                    The console is used only for string rendering via capture(),
                    not for direct output.
            console_factory: Optional ConsoleFactoryProtocol for creating console.
                           Used when console is not provided.
        """
        if not HAS_RICH:
            raise ImportError("Rich library is required for RichDirectoryFormatter")

        if console is not None:
            self._console = console
        elif console_factory is not None:
            self._console, _ = console_factory.create_string_console()
        else:
            self._console = self._create_default_console()

    def _create_default_console(self) -> Console:
        """Create default Rich console for string rendering.

        Creates a Console that renders to StringIO buffer for
        ANSI code generation without writing to stdout.
        """
        from io import StringIO
        return Console(file=StringIO(), force_terminal=True)

    def format_directory_name(self, name: str) -> str:
        """Format directory name in cyan with bold.

        Args:
            name: Directory name (e.g., "src/")

        Returns:
            Formatted string with ANSI codes
        """
        text = Text(name, style="bold cyan")
        return self._render_text(text)

    def format_file_name(self, name: str, extension: str = "") -> str:
        """Format file name with color based on extension.

        Args:
            name: File name
            extension: File extension (e.g., ".py", ".js")

        Returns:
            Formatted string with ANSI codes
        """
        # Color mapping by extension
        if extension in ['.py']:
            style = "green"
        elif extension in ['.js', '.ts', '.jsx', '.tsx']:
            style = "yellow"
        elif extension in ['.md', '.txt', '.rst']:
            style = "white"
        elif extension in ['.json', '.yaml', '.yml', '.toml']:
            style = "magenta"
        else:
            # No special color for other files
            return name

        text = Text(name, style=style)
        return self._render_text(text)

    def format_file_size(self, size_str: str) -> str:
        """Format file size display in dim color.

        Args:
            size_str: Size string (e.g., "(1.2KB)")

        Returns:
            Formatted string with ANSI codes
        """
        text = Text(size_str, style="bright_black")
        return self._render_text(text)

    def format_tree_line(self, line: str, is_directory: bool = False, file_extension: str = "") -> str:
        """Format a single line of directory tree output with Rich styling.

        Args:
            line: The line to format (e.g., "|-- file.py")
            is_directory: Whether this line represents a directory
            file_extension: File extension for extension-based coloring

        Returns:
            Formatted line with Rich ANSI codes
        """
        # This method is provided for compatibility but typically
        # formatting is done per-component (name, size, etc.)
        # For now, return the line as-is since formatting happens
        # at the component level in the actual usage
        return line

    def _render_text(self, text: Text) -> str:
        """Render Rich Text object to string with ANSI codes.

        Args:
            text: Rich Text object

        Returns:
            String with ANSI escape codes
        """
        # Use console to render text with ANSI codes
        with self._console.capture() as capture:
            self._console.print(text, end='')
        return capture.get()
