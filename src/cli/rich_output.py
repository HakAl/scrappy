"""
Rich-based I/O implementation for CLI operations.

This module provides RichIO, a Rich library implementation of CLIIOProtocol
that replaces ClickIO with enhanced terminal output capabilities.

Usage:
    from src.cli.rich_output import RichIO

    io = RichIO()
    io.secho("Hello!", fg="green")
    io.panel("Content", title="Panel Title")
    io.table(["Col1", "Col2"], [["a", "b"]])
"""

from typing import Optional, List, Generator
from contextlib import contextmanager
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.rule import Rule
from rich.text import Text
from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn, SpinnerColumn
from rich.status import Status


class ProgressTracker:
    """Wrapper for tracking progress within a context manager."""

    def __init__(self, progress: Progress, task_id):
        """Initialize progress tracker.

        Args:
            progress: Rich Progress instance
            task_id: Task ID for this progress bar
        """
        self._progress = progress
        self._task_id = task_id
        self._current = 0
        self._total = progress.tasks[task_id].total or 0

    @property
    def total(self) -> int:
        """Get total progress value."""
        return self._total

    @property
    def current(self) -> int:
        """Get current progress value."""
        return self._current

    @property
    def completed(self) -> bool:
        """Check if progress is complete."""
        return self._current >= self._total

    def advance(self, amount: int = 1) -> None:
        """Advance progress by specified amount.

        Args:
            amount: Amount to advance (can be negative)
        """
        self._progress.advance(self._task_id, amount)
        self._current += amount
        if self._current < 0:
            self._current = 0

    def update_description(self, description: str) -> None:
        """Update the progress bar description.

        Args:
            description: New description text
        """
        self._progress.update(self._task_id, description=description)


class StreamWriter:
    """Writer for streaming output without buffering."""

    def __init__(self, console: Console):
        """Initialize stream writer.

        Args:
            console: Rich Console instance
        """
        self._console = console

    def write(self, text: str, style: Optional[str] = None) -> None:
        """Write text without newline.

        Args:
            text: Text to write
            style: Optional Rich style string
        """
        if style:
            self._console.print(text, style=style, end='')
        else:
            self._console.print(text, end='')

    def writeline(self, text: str = "", style: Optional[str] = None) -> None:
        """Write text with newline.

        Args:
            text: Text to write
            style: Optional Rich style string
        """
        if style:
            self._console.print(text, style=style)
        else:
            self._console.print(text)

    def flush(self) -> None:
        """Flush any buffered output."""
        # Rich console doesn't buffer, but provide method for interface
        pass


class MultiProgressManager:
    """Manager for multiple concurrent progress bars."""

    def __init__(self, progress: Progress):
        """Initialize multi-progress manager.

        Args:
            progress: Rich Progress instance
        """
        self._progress = progress

    def add_task(self, description: str, total: int = 100) -> int:
        """Add a new progress task.

        Args:
            description: Task description
            total: Total progress value

        Returns:
            Task ID for tracking
        """
        return self._progress.add_task(description, total=total)

    def advance(self, task_id: int, amount: int = 1) -> None:
        """Advance a task by specified amount.

        Args:
            task_id: Task ID to advance
            amount: Amount to advance
        """
        self._progress.advance(task_id, amount)

    def update(self, task_id: int, **kwargs) -> None:
        """Update task properties.

        Args:
            task_id: Task ID to update
            **kwargs: Properties to update (e.g., completed=5, description="New")
        """
        self._progress.update(task_id, **kwargs)


class RichIO:
    """Rich library implementation of CLIIOProtocol.

    Provides styled terminal output using Rich library features
    including panels, tables, syntax highlighting, and color support.

    This class implements CLIIOProtocol for compatibility with existing
    CLI code while providing enhanced Rich-specific functionality.
    """

    # Map click color names to Rich color names
    # Most colors are the same, but we handle any variations
    COLOR_MAP = {
        'black': 'black',
        'red': 'red',
        'green': 'green',
        'yellow': 'yellow',
        'blue': 'blue',
        'magenta': 'magenta',
        'cyan': 'cyan',
        'white': 'white',
        'bright_black': 'bright_black',
        'bright_red': 'bright_red',
        'bright_green': 'bright_green',
        'bright_yellow': 'bright_yellow',
        'bright_blue': 'bright_blue',
        'bright_magenta': 'bright_magenta',
        'bright_cyan': 'bright_cyan',
        'bright_white': 'bright_white',
    }

    def __init__(self, console: Optional[Console] = None):
        """Initialize RichIO with optional custom console.

        Args:
            console: Optional Rich Console instance. If not provided,
                    a default console will be created.
        """
        self._console = console if console is not None else Console()

    @property
    def console(self) -> Console:
        """Get the underlying Rich Console instance."""
        return self._console

    def _map_color(self, color: Optional[str]) -> Optional[str]:
        """Map click color name to Rich color name.

        Args:
            color: Click color name (e.g., 'green', 'bright_red')

        Returns:
            Rich color name or None if no color
        """
        if color is None:
            return None
        return self.COLOR_MAP.get(color, color)

    def _build_style(self, fg: Optional[str] = None, bold: bool = False) -> str:
        """Build a Rich style string from parameters.

        Args:
            fg: Foreground color
            bold: Whether to make text bold

        Returns:
            Rich style string
        """
        parts = []

        if bold:
            parts.append('bold')

        color = self._map_color(fg)
        if color:
            parts.append(color)

        return ' '.join(parts) if parts else ''

    def echo(self, message: str = "", nl: bool = True) -> None:
        """Output a message to the console.

        Args:
            message: The text to output
            nl: Whether to append a newline (default True)
        """
        self._console.print(message, end='\n' if nl else '')

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
        style = self._build_style(fg, bold)

        if style:
            self._console.print(message, style=style, end='\n' if nl else '')
        else:
            self._console.print(message, end='\n' if nl else '')

    def styled_echo(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Alias for secho() for backwards compatibility."""
        self.secho(message, fg=fg, bold=bold, nl=nl)

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
            The styled text string (with ANSI codes if terminal supports it)
        """
        style_str = self._build_style(fg, bold)

        if style_str:
            styled_text = Text(text, style=style_str)
            # Render to string with ANSI codes
            with self._console.capture() as capture:
                self._console.print(styled_text, end='')
            return capture.get()

        return text

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
        prompt_text = text
        if show_default and default:
            prompt_text = f"{text} [{default}]"

        self._console.print(prompt_text, end=' ')

        try:
            user_input = input()
            return user_input if user_input else default
        except EOFError:
            return default

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
        default_str = "Y/n" if default else "y/N"
        prompt_text = f"{text} [{default_str}]"

        self._console.print(prompt_text, end=' ')

        try:
            user_input = input().strip().lower()

            if not user_input:
                return default

            return user_input in ('y', 'yes', 'true', '1')
        except EOFError:
            return default

    def input_line(self) -> str:
        """Read a raw line of input.

        Returns:
            The input line (without trailing newline)
        """
        try:
            return input()
        except EOFError:
            return ""

    # Extended Rich-specific methods

    def panel(
        self,
        content: str,
        title: Optional[str] = None,
        border_style: str = "blue"
    ) -> None:
        """Render content in a panel with optional title.

        Args:
            content: The content to display in the panel
            title: Optional panel title
            border_style: Border color/style (default 'blue')
        """
        panel = Panel(
            content,
            title=title,
            border_style=border_style
        )
        self._console.print(panel)

    def table(
        self,
        headers: List[str],
        rows: List[List[str]],
        title: Optional[str] = None
    ) -> None:
        """Render a table with headers and rows.

        Args:
            headers: List of column header strings
            rows: List of row data (each row is a list of strings)
            title: Optional table title
        """
        table = Table(title=title)

        # Add columns
        for header in headers:
            table.add_column(header)

        # Add rows
        for row in rows:
            table.add_row(*row)

        self._console.print(table)

    def syntax(
        self,
        code: str,
        language: str = "python",
        line_numbers: bool = False
    ) -> None:
        """Render syntax-highlighted code.

        Args:
            code: The code to highlight
            language: Programming language for highlighting
            line_numbers: Whether to show line numbers
        """
        syntax = Syntax(
            code,
            language,
            line_numbers=line_numbers
        )
        self._console.print(syntax)

    def rule(self, title: Optional[str] = None) -> None:
        """Render a horizontal rule.

        Args:
            title: Optional title to display in the rule
        """
        if title:
            self._console.print(Rule(title))
        else:
            self._console.print(Rule())

    # Progress and streaming context managers

    @contextmanager
    def progress(
        self,
        total: int,
        description: str = "Progress"
    ) -> Generator[ProgressTracker, None, None]:
        """Create a progress bar context manager.

        Args:
            total: Total number of steps
            description: Description text for the progress bar

        Yields:
            ProgressTracker for updating progress
        """
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self._console,
            transient=False
        ) as progress:
            task_id = progress.add_task(description, total=total)
            tracker = ProgressTracker(progress, task_id)
            yield tracker

    @contextmanager
    def spinner(
        self,
        text: str = "Working...",
        spinner_style: str = "dots"
    ) -> Generator[None, None, None]:
        """Create a spinner for indeterminate operations.

        Args:
            text: Text to display next to spinner
            spinner_style: Spinner animation style (dots, line, etc.)

        Yields:
            None (spinner runs automatically)
        """
        # Print the status text so it's visible in output
        self._console.print(text, end='')
        try:
            with Status(text, console=self._console, spinner=spinner_style) as status:
                yield
        finally:
            # Ensure we move to new line after spinner completes
            self._console.print()

    @contextmanager
    def stream(self) -> Generator[StreamWriter, None, None]:
        """Create a streaming output context.

        Yields:
            StreamWriter for streaming text output
        """
        writer = StreamWriter(self._console)
        yield writer
        # Ensure newline at end if content was written
        writer.writeline()

    @contextmanager
    def multi_progress(self) -> Generator[MultiProgressManager, None, None]:
        """Create a multi-progress bar context manager.

        Yields:
            MultiProgressManager for managing multiple progress bars
        """
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self._console,
            transient=False
        ) as progress:
            manager = MultiProgressManager(progress)
            yield manager
