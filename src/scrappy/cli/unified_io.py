"""
Unified I/O implementation supporting both CLI and TUI modes.

This module provides UnifiedIO, a single IO implementation that uses the Strategy
Pattern to support both direct console output (CLI mode) and OutputSink routing
(Textual/TUI mode).

Usage:
    # CLI mode (direct console)
    io = UnifiedIO()
    io.echo("Hello")
    io.panel("Content", title="Title")
    name = io.prompt("Name?", default="User")  # Blocks for input

    # TUI mode (OutputSink routing)
    io = UnifiedIO(output_sink=textual_adapter)
    io.echo("Hello")  # Routes through OutputSink
    io.panel("Content", title="Title")  # Posts Panel renderable
    name = io.prompt("Name?", default="User")  # Auto-approves with warning
"""

from typing import Protocol, Optional, List, Generator, Any
from contextlib import contextmanager
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.rule import Rule
from rich.text import Text
from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn
from rich.status import Status
from rich.prompt import Confirm

from .protocols import OutputSink
from scrappy.infrastructure.output_mode import OutputModeContext
from scrappy.infrastructure.theme import ThemeProtocol, DEFAULT_THEME


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
        self._buffer: List[str] = []

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
        self._buffer.append(text)

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
        self._buffer.append(text + "\n")

    def flush(self) -> None:
        """Flush any buffered output."""
        pass

    def get_buffer(self) -> str:
        """Get buffered content as string.

        Returns:
            All buffered content
        """
        return "".join(self._buffer)


class SimplifiedProgressTracker:
    """Simplified progress tracker for TUI mode.

    Logs text-based progress messages instead of animated progress bars.
    """

    def __init__(self, sink: OutputSink, total: int, description: str):
        """Initialize simplified progress tracker.

        Args:
            sink: OutputSink for posting messages
            total: Total number of steps
            description: Progress description
        """
        self._sink = sink
        self._total = total
        self._description = description
        self._current = 0

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
        """Advance progress and post update message.

        Args:
            amount: Amount to advance
        """
        self._current += amount
        if self._current < 0:
            self._current = 0

        if self._current > self._total:
            self._current = self._total

        message = f"{self._description}: {self._current}/{self._total}\n"
        self._sink.post_output(message)

    def update_description(self, description: str) -> None:
        """Update the progress description.

        Args:
            description: New description text
        """
        self._description = description


class OutputStrategyProtocol(Protocol):
    """Strategy for routing output to different destinations.

    Implementations:
    - DirectConsoleOutput: Writes directly to Rich Console (CLI mode)
    - OutputSinkAdapter: Routes through OutputSink protocol (TUI mode)

    The strategy pattern allows different visual representations while
    maintaining a consistent API at the UnifiedIO level.
    """

    def output_plain(self, text: str, nl: bool = True) -> None:
        """Output plain text.

        Args:
            text: Text to output
            nl: Whether to append newline
        """
        ...

    def output_styled(
        self,
        text: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Output styled text with color and formatting.

        Args:
            text: Text to output
            fg: Foreground color
            bold: Whether to make text bold
            nl: Whether to append newline
        """
        ...

    def output_panel(
        self,
        content: str,
        title: Optional[str] = None,
        border_style: str = "blue"
    ) -> None:
        """Output a panel.

        Args:
            content: Panel content
            title: Optional title
            border_style: Border color/style
        """
        ...

    def output_table(
        self,
        headers: List[str],
        rows: List[List[str]],
        title: Optional[str] = None,
        title_style: Optional[str] = None,
        header_style: Optional[str] = None,
        border_style: Optional[str] = None,
    ) -> None:
        """Output a table.

        Args:
            headers: Column headers
            rows: Row data
            title: Optional title
            title_style: Style for title
            header_style: Style for headers
            border_style: Style for borders
        """
        ...

    def output_syntax(
        self,
        code: str,
        language: str = "python",
        line_numbers: bool = False
    ) -> None:
        """Output syntax-highlighted code.

        Args:
            code: Code to highlight
            language: Programming language
            line_numbers: Whether to show line numbers
        """
        ...

    def output_rule(self, title: Optional[str] = None) -> None:
        """Output a horizontal rule.

        Args:
            title: Optional title
        """
        ...

    @contextmanager
    def spinner_context(
        self,
        text: str = "Working...",
        spinner_style: str = "dots"
    ) -> Generator[None, None, None]:
        """Create spinner context for this output strategy.

        DirectConsoleOutput: Rich animated spinner
        OutputSinkAdapter: Log start/end messages or no-op

        Args:
            text: Spinner text
            spinner_style: Spinner animation style (CLI only)

        Yields:
            None
        """
        ...

    @contextmanager
    def progress_context(
        self,
        total: int,
        description: str = "Progress"
    ) -> Generator[ProgressTracker, None, None]:
        """Create progress context for this output strategy.

        DirectConsoleOutput: Rich animated progress bar
        OutputSinkAdapter: Text-based progress messages

        Args:
            total: Total steps
            description: Progress description

        Yields:
            ProgressTracker instance
        """
        ...

    @contextmanager
    def stream_context(self) -> Generator[StreamWriter, None, None]:
        """Create streaming output context.

        Yields:
            StreamWriter instance
        """
        ...

    def input_prompt(
        self,
        text: str,
        default: str = "",
        show_default: bool = True
    ) -> str:
        """Get user input with prompt.

        DirectConsoleOutput: Blocking input()
        OutputSinkAdapter: Auto-approve with warning (Phase 1)

        Args:
            text: Prompt text
            default: Default value
            show_default: Whether to show default

        Returns:
            User input or default
        """
        ...

    def input_confirm(self, text: str, default: bool = False) -> bool:
        """Get yes/no confirmation.

        DirectConsoleOutput: Blocking Confirm.ask()
        OutputSinkAdapter: Auto-approve with warning (Phase 1)

        Args:
            text: Confirmation text
            default: Default value

        Returns:
            Confirmation result
        """
        ...

    def input_checkpoint(self, message: str, default: str = "c") -> str:
        """Get checkpoint choice (activity bar only, no log output).

        DirectConsoleOutput: Blocking input with validation
        OutputSinkAdapter: Routes through bridge with input_type="checkpoint"

        Args:
            message: Checkpoint prompt message with options
            default: Default choice

        Returns:
            User's choice
        """
        ...

    def input_line(self) -> str:
        """Read raw line of input.

        DirectConsoleOutput: Blocking input()
        OutputSinkAdapter: Raises NotImplementedError

        Returns:
            Input line
        """
        ...

    def supports_color(self) -> bool:
        """Check if output supports ANSI color codes.

        Returns:
            True if terminal supports colors, False otherwise.
        """
        ...


class DirectConsoleOutput:
    """Strategy for direct Rich Console output (CLI mode).

    WARNING: CLI MODE ONLY. This strategy is only selected when
    output_sink is None in UnifiedIO. Never instantiate directly
    for TUI mode - use OutputSinkAdapter instead.

    Provides full Rich functionality with blocking input.
    All features work exactly as in standalone Rich library.

    Input methods (prompt, confirm, input_line) use blocking calls
    that will hang worker threads in TUI mode.
    """

    def __init__(self, console: Console):
        """Initialize with Rich Console.

        Args:
            console: Rich Console instance
        """
        self._console = console

    def output_plain(self, text: str, nl: bool = True) -> None:
        """Output plain text to console."""
        self._console.print(text, end='\n' if nl else '')

    def output_styled(
        self,
        text: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Output styled text to console."""
        style_parts = []
        if bold:
            style_parts.append('bold')
        if fg:
            style_parts.append(fg)
        style = ' '.join(style_parts) if style_parts else None

        self._console.print(text, style=style, end='\n' if nl else '')

    def output_panel(
        self,
        content: str,
        title: Optional[str] = None,
        border_style: str = "blue"
    ) -> None:
        """Output panel to console."""
        panel = Panel(content, title=title, border_style=border_style, expand=False)
        self._console.print(panel)

    def output_table(
        self,
        headers: List[str],
        rows: List[List[str]],
        title: Optional[str] = None,
        title_style: Optional[str] = None,
        header_style: Optional[str] = None,
        border_style: Optional[str] = None,
    ) -> None:
        """Output table to console."""
        table = Table(
            title=title,
            title_style=title_style,
            header_style=header_style,
            border_style=border_style,
        )
        for header in headers:
            table.add_column(header)
        for row in rows:
            table.add_row(*row)
        self._console.print(table)

    def output_syntax(
        self,
        code: str,
        language: str = "python",
        line_numbers: bool = False
    ) -> None:
        """Output syntax-highlighted code to console."""
        syntax = Syntax(code, language, line_numbers=line_numbers)
        self._console.print(syntax)

    def output_rule(self, title: Optional[str] = None) -> None:
        """Output horizontal rule to console."""
        self._console.print(Rule(title) if title else Rule())

    @contextmanager
    def spinner_context(
        self,
        text: str = "Working...",
        spinner_style: str = "dots"
    ) -> Generator[None, None, None]:
        """Create Rich animated spinner."""
        with Status(text, console=self._console, spinner=spinner_style):
            yield

    @contextmanager
    def progress_context(
        self,
        total: int,
        description: str = "Progress"
    ) -> Generator[ProgressTracker, None, None]:
        """Create Rich animated progress bar."""
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
    def stream_context(self) -> Generator[StreamWriter, None, None]:
        """Create streaming output context."""
        writer = StreamWriter(self._console)
        yield writer
        writer.writeline()

    def input_prompt(
        self,
        text: str,
        default: str = "",
        show_default: bool = True
    ) -> str:
        """Get blocking user input.

        WARNING: CLI MODE ONLY. Uses blocking input() that will hang
        in TUI worker threads. In TUI mode, OutputSinkAdapter.input_prompt()
        routes through Textual's modal input system.

        Raises:
            RuntimeError: If called in TUI mode
        """
        if OutputModeContext.is_tui_mode():
            raise RuntimeError(
                "DirectConsoleOutput.input_prompt() called in TUI mode. "
                "Use OutputSinkAdapter or UnifiedIO with output_sink instead."
            )
        prompt_text = text
        if show_default and default:
            prompt_text = f"{text} [{default}]"

        self._console.print(prompt_text, end=' ')
        try:
            user_input = input()
            return user_input if user_input else default
        except EOFError:
            return default

    def input_confirm(self, text: str, default: bool = False) -> bool:
        """Get blocking confirmation.

        WARNING: CLI MODE ONLY. Uses blocking Confirm.ask() that will hang
        in TUI worker threads. In TUI mode, OutputSinkAdapter.input_confirm()
        routes through Textual's modal confirmation system.

        Raises:
            RuntimeError: If called in TUI mode
        """
        if OutputModeContext.is_tui_mode():
            raise RuntimeError(
                "DirectConsoleOutput.input_confirm() called in TUI mode. "
                "Use OutputSinkAdapter or UnifiedIO with output_sink instead."
            )
        try:
            return Confirm.ask(text, default=default, console=self._console)
        except EOFError:
            return default

    def input_checkpoint(self, message: str, default: str = "c") -> str:
        """Get blocking checkpoint choice.

        WARNING: CLI MODE ONLY. In CLI mode, this displays the checkpoint
        message and prompts for input, validating the choice.

        Raises:
            RuntimeError: If called in TUI mode
        """
        if OutputModeContext.is_tui_mode():
            raise RuntimeError(
                "DirectConsoleOutput.input_checkpoint() called in TUI mode. "
                "Use OutputSinkAdapter or UnifiedIO with output_sink instead."
            )
        # In CLI mode, display the message and get input
        self._console.print(message)
        self._console.print(f"Choice [c/g/a/s] [{default}]", end=' ')
        try:
            user_input = input().lower().strip()
            if user_input in ('c', 'g', 'a', 's'):
                return user_input
            return default
        except EOFError:
            return default

    def input_line(self) -> str:
        """Read blocking input line.

        WARNING: CLI MODE ONLY. Uses blocking input() that will hang
        in TUI worker threads. In TUI mode, OutputSinkAdapter.input_line()
        routes through Textual's Input widget.

        Raises:
            RuntimeError: If called in TUI mode
        """
        if OutputModeContext.is_tui_mode():
            raise RuntimeError(
                "DirectConsoleOutput.input_line() called in TUI mode. "
                "Use OutputSinkAdapter or UnifiedIO with output_sink instead."
            )
        try:
            return input()
        except EOFError:
            return ""

    def supports_color(self) -> bool:
        """Check if console supports ANSI color codes.

        Returns:
            True if the Rich Console has color support enabled.
        """
        return self._console.is_terminal and not self._console.no_color


class OutputSinkAdapter:
    """Strategy for OutputSink routing (Textual/TUI mode).

    Routes all output through OutputSink protocol for thread-safe
    Textual integration. Some features have different visual representation:
    - Spinners: Log start/end messages instead of animation
    - Progress: Text-based updates instead of live bars
    - Input: Uses ThreadSafeAsyncBridge for modal dialogs (Phase 3)
    """

    def __init__(self, sink: OutputSink, console: Console):
        """Initialize with OutputSink and Console.

        Args:
            sink: OutputSink protocol implementation
            console: Rich Console for creating renderables
        """
        self._sink = sink
        self._console = console
        self._bridge: Optional[Any] = None  # Set by TextualInteractiveMode after app creation

    def set_bridge(self, bridge: Any) -> None:
        """Set the ThreadSafeAsyncBridge for modal dialogs.

        Called by TextualInteractiveMode after ScrappyApp is created,
        enabling interactive prompts and confirmations.

        Args:
            bridge: ThreadSafeAsyncBridge instance from ScrappyApp
        """
        self._bridge = bridge

    def output_plain(self, text: str, nl: bool = True) -> None:
        """Output plain text through sink.

        Note: RichLog.write() handles line breaks automatically,
        so we don't add extra newlines to avoid double-spacing.
        """
        self._sink.post_output(text)

    def output_styled(
        self,
        text: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Output styled text through sink as Rich Text.

        Note: RichLog.write() handles line breaks automatically,
        so we don't add extra newlines to avoid double-spacing.
        """
        color_map = {
            "cyan": "cyan", "yellow": "yellow", "red": "red",
            "green": "green", "blue": "blue", "magenta": "magenta",
            "white": "white", "black": "black",
        }

        styled_text = text
        if fg or bold:
            rich_color = color_map.get(fg, fg) if fg else None
            if rich_color and bold:
                styled_text = f"[bold {rich_color}]{text}[/bold {rich_color}]"
            elif rich_color:
                styled_text = f"[{rich_color}]{text}[/{rich_color}]"
            elif bold:
                styled_text = f"[bold]{text}[/bold]"

        renderable = Text.from_markup(styled_text)
        self._sink.post_renderable(renderable)

    def output_panel(
        self,
        content: str,
        title: Optional[str] = None,
        border_style: str = "blue"
    ) -> None:
        """Output panel through sink as Rich Panel."""
        panel = Panel(content, title=title, border_style=border_style, expand=False)
        self._sink.post_renderable(panel)

    def output_table(
        self,
        headers: List[str],
        rows: List[List[str]],
        title: Optional[str] = None,
        title_style: Optional[str] = None,
        header_style: Optional[str] = None,
        border_style: Optional[str] = None,
    ) -> None:
        """Output table through sink as Rich Table."""
        table = Table(
            title=title,
            title_style=title_style,
            header_style=header_style,
            border_style=border_style,
        )
        for header in headers:
            table.add_column(header)
        for row in rows:
            table.add_row(*row)
        self._sink.post_renderable(table)

    def output_syntax(
        self,
        code: str,
        language: str = "python",
        line_numbers: bool = False
    ) -> None:
        """Output syntax through sink as Rich Syntax."""
        syntax = Syntax(code, language, line_numbers=line_numbers)
        self._sink.post_renderable(syntax)

    def output_rule(self, title: Optional[str] = None) -> None:
        """Output rule through sink as Rich Rule."""
        rule = Rule(title) if title else Rule()
        self._sink.post_renderable(rule)

    @contextmanager
    def spinner_context(
        self,
        text: str = "Working...",
        spinner_style: str = "dots"
    ) -> Generator[None, None, None]:
        """Create spinner context (simplified for TUI).

        Logs start and completion messages instead of animated spinner.
        """
        self.output_plain(f"{text}\n")
        try:
            yield
        finally:
            self.output_plain("Completed.\n")

    @contextmanager
    def progress_context(
        self,
        total: int,
        description: str = "Progress"
    ) -> Generator[SimplifiedProgressTracker, None, None]:
        """Create progress context (simplified for TUI).

        Uses text-based progress messages instead of live bars.
        """
        tracker = SimplifiedProgressTracker(self._sink, total, description)
        self.output_plain(f"{description}: 0/{total}\n")
        try:
            yield tracker
        finally:
            self.output_plain(f"{description}: Complete\n")

    @contextmanager
    def stream_context(self) -> Generator[StreamWriter, None, None]:
        """Create streaming output context."""
        writer = StreamWriter(self._console)
        yield writer
        self.output_plain(writer.get_buffer())

    def input_prompt(
        self,
        text: str,
        default: str = "",
        show_default: bool = True
    ) -> str:
        """Get user input via modal dialog (Phase 3).

        Uses ThreadSafeAsyncBridge to show modal in main thread
        while blocking worker thread. Falls back to auto-approve
        if bridge not available.
        """
        if self._bridge is not None:
            # Phase 3: Use modal dialog via bridge
            prompt_text = text
            if show_default and default:
                prompt_text = f"{text} [{default}]"
            return self._bridge.blocking_prompt(prompt_text, default)

        # Fallback: Auto-approve with warning (bridge not set)
        warning_panel = Panel(
            f"[bold yellow]BRIDGE NOT INITIALIZED[/]\n\n"
            f"[white]Attempted to request input:[/]\n"
            f"{text}\n\n"
            f"[yellow]Bridge not available - returning default.[/]\n\n"
            f"[white]Returning default:[/] [cyan]{default or '(empty)'}[/]",
            title="[yellow]Auto-Response[/]",
            border_style="yellow"
        )
        self._sink.post_renderable(warning_panel)
        return default

    def input_confirm(self, text: str, default: bool = False) -> bool:
        """Get yes/no confirmation via modal dialog (Phase 3).

        Uses ThreadSafeAsyncBridge to show modal in main thread
        while blocking worker thread. Falls back to auto-approve
        or auto-deny based on the provided default when bridge is not available.
        """
        if self._bridge is not None:
            # Flush pending output so it renders before confirmation prompt
            if hasattr(self._sink, 'flush'):
                self._sink.flush(timeout=5.0)
            # Phase 3: Use modal dialog via bridge
            return self._bridge.blocking_confirm(text)

        # Fallback: respect the provided default when bridge is unavailable.
        # Non-destructive operations (session restore, checkpoint creation, etc.)
        # should continue to behave according to their default preference.
        is_routine = (
            "restore" in text.lower() and "session" in text.lower()
        ) or default is True

        if is_routine:
            # Simple dim message for routine operations
            outcome = "auto-confirmed" if default else "auto-denied"
            message = Text.from_markup(f"{text} [dim]({outcome})[/dim]")
            self._sink.post_renderable(message)
            return default

        # Destructive operations - block safely and make it obvious why.
        warning_panel = Panel(
            f"[bold white on red] CONFIRMATION UNAVAILABLE [/]\n\n"
            f"[white]{text}[/]\n\n"
            f"[bold yellow]Bridge not initialized:[/] [white]Using default response.[/]\n\n"
            f"[bold red]Returned:[/] [white]{default}[/]",
            title="[bold white on red]SECURITY BLOCK: Missing Confirmation[/]",
            border_style="red",
            expand=False
        )
        self._sink.post_renderable(warning_panel)
        return default

    def input_checkpoint(self, message: str, default: str = "c") -> str:
        """Get checkpoint choice via activity bar only (no log output).

        Uses ThreadSafeAsyncBridge with input_type="checkpoint" which
        displays in the activity bar but skips writing to the chat log.
        """
        if self._bridge is not None:
            # Flush pending output so it renders before checkpoint prompt
            if hasattr(self._sink, 'flush'):
                self._sink.flush(timeout=5.0)
            return self._bridge.blocking_checkpoint(message, default)

        # Fallback: Auto-approve with warning (bridge not set)
        warning_panel = Panel(
            f"[bold yellow]BRIDGE NOT INITIALIZED[/]\n\n"
            f"[white]Attempted checkpoint prompt:[/]\n"
            f"{message}\n\n"
            f"[yellow]Bridge not available - returning default.[/]\n\n"
            f"[white]Returning default:[/] [cyan]{default}[/]",
            title="[yellow]Auto-Response[/]",
            border_style="yellow"
        )
        self._sink.post_renderable(warning_panel)
        return default

    def input_line(self) -> str:
        """Not supported in Textual mode."""
        raise NotImplementedError(
            "input_line() not supported in Textual mode. "
            "Use Input widget events instead."
        )

    def supports_color(self) -> bool:
        """Check if TUI output supports colors.

        Returns:
            True - Textual TUI always supports Rich markup/colors.
        """
        return True


class UnifiedIO:
    """Single IO implementation supporting both direct console and OutputSink routing.

    Uses Strategy Pattern for output routing:
    - DirectConsoleOutput: Writes directly to Rich Console (blocking CLI mode)
    - OutputSinkAdapter: Routes through OutputSink protocol (non-blocking TUI mode)

    Follows SOLID principles:
    - Single Responsibility: IO operations only, delegates to strategy
    - Open/Closed: Extensible via OutputSink implementations
    - Liskov Substitution: Implements UnifiedIOProtocol completely
    - Interface Segregation: Clean protocol hierarchy (CLIIOProtocol + RichOutputProtocol)
    - Dependency Inversion: Depends on OutputSink abstraction, not concrete implementations

    Usage:
        # CLI mode (direct console)
        io = UnifiedIO()
        io.echo("Hello")
        io.panel("Content", title="Title")
        name = io.prompt("Name?", default="User")  # Blocks for input

        # TUI mode (OutputSink routing)
        io = UnifiedIO(output_sink=textual_adapter)
        io.echo("Hello")  # Routes through OutputSink
        io.panel("Content", title="Title")  # Posts Panel renderable
        name = io.prompt("Name?", default="User")  # Auto-approves with warning
    """

    def __init__(
        self,
        output_sink: Optional[OutputSink] = None,
        console: Optional[Console] = None,
        theme: Optional[ThemeProtocol] = None
    ):
        """Initialize with optional output sink, console, and theme.

        Args:
            output_sink: Optional OutputSink for routing (Textual mode).
                        If None, uses direct console output (CLI mode).
            console: Optional Rich Console. Defaults to Console().
            theme: Optional theme for styling. Defaults to DEFAULT_THEME.

        Design:
        - If output_sink provided: Routes all output through OutputSink (TUI mode)
        - If output_sink is None: Direct console output (CLI mode)
        """
        self._output_sink = output_sink
        self._console = console or Console()
        self._theme = theme or DEFAULT_THEME

        if output_sink:
            self._strategy: OutputStrategyProtocol = OutputSinkAdapter(output_sink, self._console)
        else:
            self._strategy = DirectConsoleOutput(self._console)

    @property
    def is_tui_mode(self) -> bool:
        """Check if running in TUI (Textual) mode.

        This is the single source of truth for mode detection.
        Returns True when output_sink is not None, indicating
        output should be routed through Textual.

        Returns:
            True if in TUI mode, False for CLI mode.
        """
        return self._output_sink is not None

    @property
    def console(self) -> Console:
        """Get the underlying Rich Console instance.

        Returns:
            Rich Console instance.
            - CLI mode: Real Console for direct output
            - TUI mode: Console used for creating renderables
        """
        return self._console

    @property
    def output_sink(self) -> Optional[OutputSink]:
        """Get the OutputSink if in TUI mode.

        Returns:
            OutputSink instance if in TUI mode, None otherwise.
        """
        return self._output_sink

    @output_sink.setter
    def output_sink(self, sink: Optional[OutputSink]) -> None:
        """Set the OutputSink (for wizard screen swapping).

        Updates both the stored sink and the strategy's sink reference.

        Args:
            sink: New OutputSink to use, or None
        """
        self._output_sink = sink
        # Also update strategy's sink if using OutputSinkAdapter
        if isinstance(self._strategy, OutputSinkAdapter) and sink is not None:
            self._strategy._sink = sink

    @property
    def theme(self) -> ThemeProtocol:
        """Get the current theme.

        Returns:
            Theme instance for styling.
        """
        return self._theme

    def set_bridge(self, bridge: Any) -> None:
        """Set the ThreadSafeAsyncBridge for modal dialogs (Phase 3).

        Only effective in TUI mode (when OutputSinkAdapter is used).
        Enables prompt() and confirm() to show modal dialogs instead
        of auto-approving.

        Args:
            bridge: ThreadSafeAsyncBridge instance from ScrappyApp
        """
        if isinstance(self._strategy, OutputSinkAdapter):
            self._strategy.set_bridge(bridge)

    def echo(self, message: str = "", nl: bool = True) -> None:
        """Output a message to the console."""
        self._strategy.output_plain(message, nl)

    def secho(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Output a styled message with color and formatting."""
        self._strategy.output_styled(message, fg, bold, nl)

    def style(
        self,
        text: str,
        fg: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Return styled text for inline use.

        Supports both color names (cyan, red) and hex values (#00ffff, #ff0000).
        Returns Rich markup that will be rendered by the output strategy.

        Args:
            text: Text to style
            fg: Color name or hex value (e.g., "cyan" or "#00ffff")
            bold: Whether to make text bold

        Returns:
            Rich markup string
        """
        if fg or bold:
            if fg and bold:
                return f"[bold {fg}]{text}[/bold {fg}]"
            elif fg:
                return f"[{fg}]{text}[/{fg}]"
            elif bold:
                return f"[bold]{text}[/bold]"

        return text

    def prompt(
        self,
        text: str,
        default: str = "",
        show_default: bool = True
    ) -> str:
        """Get user input with a prompt.

        Behavior varies by mode:
        - CLI: Blocks for user input
        - TUI: Auto-approves with warning panel (Phase 1 limitation)
        """
        return self._strategy.input_prompt(text, default, show_default)

    def confirm(
        self,
        text: str,
        default: bool = False
    ) -> bool:
        """Get yes/no confirmation from user.

        Behavior varies by mode:
        - CLI: Blocks for user confirmation
        - TUI: Auto-approves with security warning (Phase 1 limitation)
        """
        return self._strategy.input_confirm(text, default)

    def checkpoint_prompt(self, message: str, default: str = "c") -> str:
        """Get checkpoint choice from user (activity bar only in TUI).

        Behavior varies by mode:
        - CLI: Displays message and prompts for choice
        - TUI: Shows in activity bar only (no log output)
        """
        return self._strategy.input_checkpoint(message, default)

    def input_line(self) -> str:
        """Read a raw line of input.

        Behavior varies by mode:
        - CLI: Blocks for input
        - TUI: Raises NotImplementedError
        """
        return self._strategy.input_line()

    def panel(
        self,
        content: str,
        title: Optional[str] = None,
        border_style: Optional[str] = None
    ) -> None:
        """Display content in a panel with optional title.

        Args:
            content: Panel content
            title: Optional title
            border_style: Border color/style. Defaults to theme.info.
        """
        style = border_style or self._theme.info
        self._strategy.output_panel(content, title, style)

    def table(
        self,
        headers: List[str],
        rows: List[List[str]],
        title: Optional[str] = None
    ) -> None:
        """Display a table with headers and rows."""
        self._strategy.output_table(
            headers, rows, title,
            title_style=self._theme.primary,
            header_style=self._theme.accent,
            border_style=self._theme.text_muted,
        )

    def syntax(
        self,
        code: str,
        language: str = "python",
        line_numbers: bool = False
    ) -> None:
        """Display syntax-highlighted code."""
        self._strategy.output_syntax(code, language, line_numbers)

    def rule(self, title: Optional[str] = None) -> None:
        """Display a horizontal rule."""
        self._strategy.output_rule(title)

    @contextmanager
    def progress(
        self,
        total: int,
        description: str = "Progress"
    ) -> Generator[ProgressTracker, None, None]:
        """Create a progress bar context manager.

        Visual representation varies by mode:
        - CLI: Rich animated progress bar
        - TUI: Text-based progress messages
        """
        with self._strategy.progress_context(total, description) as tracker:
            yield tracker

    @contextmanager
    def spinner(
        self,
        text: str = "Working...",
        spinner_style: str = "dots"
    ) -> Generator[None, None, None]:
        """Create a spinner for indeterminate operations.

        Visual representation varies by mode:
        - CLI: Rich animated spinner
        - TUI: Start/end messages
        """
        with self._strategy.spinner_context(text, spinner_style):
            yield

    @contextmanager
    def stream(self) -> Generator[StreamWriter, None, None]:
        """Create a streaming output context."""
        with self._strategy.stream_context() as writer:
            yield writer

    def supports_color(self) -> bool:
        """Check if output supports ANSI color codes.

        Returns:
            True if the output destination supports colors.
            - CLI mode: Based on terminal capabilities
            - TUI mode: Always True (Rich/Textual supports colors)
        """
        return self._strategy.supports_color()
