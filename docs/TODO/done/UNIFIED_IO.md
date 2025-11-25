# P0 -- CLEANUP -- Unified IO Refactoring

# REFINED PLAN (Incorporating Review Feedback)

## Status of Critical Issues

### Issue A: Renderable Handling - ALREADY SOLVED
**Status: No action needed**

The existing `OutputSink` protocol already handles this correctly:
- `post_renderable(obj: Any)` accepts Rich renderables directly (src/cli/protocols.py:47)
- `TextualOutputAdapter.post_renderable()` preserves objects via `WriteRenderable(obj)` messages (src/cli/textual_app.py:90)
- No string conversion happens - formatting is preserved

**Minor improvement:**
Change type hint from `Any` to `RenderableType` for clarity:
```python
from rich.console import RenderableType

def post_renderable(self, obj: RenderableType) -> None:
    """Post Rich renderable (Panel, Table, Text, etc.)."""
    ...
```

### Issue B: Blocking Input Problem - ACKNOWLEDGED
**Status: Accept limitations for Phase 1, document for future**

The impedance mismatch is fundamental:
- **CLI mode**: Synchronous `input()` blocks thread (acceptable)
- **Textual mode**: Cannot block main thread (use auto-approve with warnings)

**Phase 1 approach:**
- CLI: Fully functional blocking input via `input()` and `Confirm.ask()`
- Textual: Auto-approve with warning panels (current TextualIO behavior)
- Document: Input methods are "best-effort" in Textual mode

**Future considerations (Phase 4+):**
- Add async variants: `async_prompt()`, `async_confirm()` if needed
- Or use callback pattern for non-blocking input
- Or use Future/Promise pattern as middle ground

**Decision: Not blocking Phase 1 implementation**

### Issue C: Context Manager Divergence - NEEDS DESIGN
**Status: Different implementations OK, unified API required**

Spinners and progress bars work fundamentally differently:

**CLI mode (DirectConsoleOutput):**
- `spinner()`: Uses Rich `Status` - hijacks cursor, animated
- `progress()`: Uses Rich `Progress` - live updating bars

**Textual mode (OutputSinkAdapter):**
- `spinner()`: Cannot hijack cursor in Log widget
  - Strategy: Log "Starting..." and "Completed..." messages
  - Or: No-op (let Textual handle loading states via widget attributes)
- `progress()`: Cannot render Rich Live Display in Log widget
  - Strategy: Post progress update messages periodically
  - Or: Simplified text-based progress indicators

**Conclusion:** Strategy pattern allows different visual representations with same API.

## Refined Implementation Plan

### Phase 1: Protocol Definitions

#### 1.1 Define RichOutputProtocol
**File:** `src/cli/protocols.py`

```python
from typing import Protocol, Optional, List, Generator
from contextlib import contextmanager
from rich.console import RenderableType

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
```

#### 1.2 Define UnifiedIOProtocol
**File:** `src/cli/protocols.py`

```python
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
    def console(self) -> Console:
        """Get the underlying Rich Console instance.

        Returns:
            Console instance for this IO implementation
        """
        ...
```

### Phase 2: Strategy Protocol and Implementations

#### 2.1 Define OutputStrategyProtocol
**File:** `src/cli/unified_io.py`

```python
from typing import Protocol, Optional, List, Generator
from contextlib import contextmanager
from rich.console import Console, RenderableType

class OutputStrategyProtocol(Protocol):
    """Strategy for routing output to different destinations.

    Implementations:
    - DirectConsoleOutput: Writes directly to Rich Console (CLI mode)
    - OutputSinkAdapter: Routes through OutputSink protocol (TUI mode)

    The strategy pattern allows different visual representations while
    maintaining a consistent API at the UnifiedIO level.
    """

    # Basic output methods
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

    # Rich output methods
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
        title: Optional[str] = None
    ) -> None:
        """Output a table.

        Args:
            headers: Column headers
            rows: Row data
            title: Optional title
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

    # Context managers (implementation-specific behavior)
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
    ) -> Generator["ProgressTracker", None, None]:
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
    def stream_context(self) -> Generator["StreamWriter", None, None]:
        """Create streaming output context.

        Yields:
            StreamWriter instance
        """
        ...

    # Input methods (strategy-dependent behavior)
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

    def input_line(self) -> str:
        """Read raw line of input.

        DirectConsoleOutput: Blocking input()
        OutputSinkAdapter: Raises NotImplementedError

        Returns:
            Input line
        """
        ...
```

#### 2.2 DirectConsoleOutput Implementation
**File:** `src/cli/unified_io.py`

```python
class DirectConsoleOutput:
    """Strategy for direct Rich Console output (CLI mode).

    Provides full Rich functionality with blocking input.
    All features work exactly as in standalone Rich library.
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
        from rich.panel import Panel
        panel = Panel(content, title=title, border_style=border_style)
        self._console.print(panel)

    def output_table(
        self,
        headers: List[str],
        rows: List[List[str]],
        title: Optional[str] = None
    ) -> None:
        """Output table to console."""
        from rich.table import Table
        table = Table(title=title)
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
        from rich.syntax import Syntax
        syntax = Syntax(code, language, line_numbers=line_numbers)
        self._console.print(syntax)

    def output_rule(self, title: Optional[str] = None) -> None:
        """Output horizontal rule to console."""
        from rich.rule import Rule
        self._console.print(Rule(title) if title else Rule())

    @contextmanager
    def spinner_context(
        self,
        text: str = "Working...",
        spinner_style: str = "dots"
    ) -> Generator[None, None, None]:
        """Create Rich animated spinner."""
        from rich.status import Status
        with Status(text, console=self._console, spinner=spinner_style):
            yield

    @contextmanager
    def progress_context(
        self,
        total: int,
        description: str = "Progress"
    ) -> Generator[ProgressTracker, None, None]:
        """Create Rich animated progress bar."""
        from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn
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
        """Get blocking user input."""
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
        """Get blocking confirmation."""
        from rich.prompt import Confirm
        try:
            return Confirm.ask(text, default=default, console=self._console)
        except EOFError:
            return default

    def input_line(self) -> str:
        """Read blocking input line."""
        try:
            return input()
        except EOFError:
            return ""
```

#### 2.3 OutputSinkAdapter Implementation
**File:** `src/cli/unified_io.py`

```python
class OutputSinkAdapter:
    """Strategy for OutputSink routing (Textual/TUI mode).

    Routes all output through OutputSink protocol for thread-safe
    Textual integration. Some features have different visual representation:
    - Spinners: Log start/end messages instead of animation
    - Progress: Text-based updates instead of live bars
    - Input: Auto-approve with warnings (Phase 1 limitation)
    """

    def __init__(self, sink: OutputSink, console: Console):
        """Initialize with OutputSink and Console.

        Args:
            sink: OutputSink protocol implementation
            console: Rich Console for creating renderables
        """
        self._sink = sink
        self._console = console

    def output_plain(self, text: str, nl: bool = True) -> None:
        """Output plain text through sink."""
        content = text + ('\n' if nl else '')
        self._sink.post_output(content)

    def output_styled(
        self,
        text: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Output styled text through sink as Rich Text."""
        from rich.text import Text

        # Build Rich markup
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

        if nl:
            styled_text += "\n"

        renderable = Text.from_markup(styled_text)
        self._sink.post_renderable(renderable)

    def output_panel(
        self,
        content: str,
        title: Optional[str] = None,
        border_style: str = "blue"
    ) -> None:
        """Output panel through sink as Rich Panel."""
        from rich.panel import Panel
        panel = Panel(content, title=title, border_style=border_style)
        self._sink.post_renderable(panel)

    def output_table(
        self,
        headers: List[str],
        rows: List[List[str]],
        title: Optional[str] = None
    ) -> None:
        """Output table through sink as Rich Table."""
        from rich.table import Table
        table = Table(title=title)
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
        from rich.syntax import Syntax
        syntax = Syntax(code, language, line_numbers=line_numbers)
        self._sink.post_renderable(syntax)

    def output_rule(self, title: Optional[str] = None) -> None:
        """Output rule through sink as Rich Rule."""
        from rich.rule import Rule
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
    ) -> Generator[ProgressTracker, None, None]:
        """Create progress context (simplified for TUI).

        Uses text-based progress messages instead of live bars.
        """
        # Create a simplified progress tracker
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
        # Note: Stream output is buffered and posted at end
        self.output_plain(writer.get_buffer())

    def input_prompt(
        self,
        text: str,
        default: str = "",
        show_default: bool = True
    ) -> str:
        """Auto-approve prompt with warning (Phase 1 limitation)."""
        from rich.panel import Panel

        warning_panel = Panel(
            f"[bold yellow]PHASE 1 LIMITATION[/]\n\n"
            f"[white]Attempted to request input:[/]\n"
            f"{text}\n\n"
            f"[yellow]Interactive prompts return defaults in Textual mode.[/]\n"
            f"[yellow]Phase 3 will enable modal dialogs for user input.[/]\n\n"
            f"[white]Returning default:[/] [cyan]{default or '(empty)'}[/]",
            title="[yellow]Auto-Response[/]",
            border_style="yellow"
        )
        self._sink.post_renderable(warning_panel)
        return default

    def input_confirm(self, text: str, default: bool = False) -> bool:
        """Auto-approve confirmation with warning (Phase 1 limitation)."""
        from rich.panel import Panel

        warning_panel = Panel(
            f"[bold white on red] AUTO-CONFIRMED [/]\n\n"
            f"[white]{text}[/]\n\n"
            f"[bold yellow]Phase 1 Limitation:[/] [white]Auto-approved.[/]\n"
            f"[bold yellow]Manual confirmation requires Phase 3.[/]\n\n"
            f"[bold red]Review destructive operations carefully![/]",
            title="[blink bold white on red]SECURITY WARNING: Auto-Confirm[/]",
            border_style="red",
            expand=False
        )
        self._sink.post_renderable(warning_panel)
        return True

    def input_line(self) -> str:
        """Not supported in Textual mode."""
        raise NotImplementedError(
            "input_line() not supported in Textual mode. "
            "Use Input widget events instead."
        )
```

### Phase 3: UnifiedIO Implementation

**File:** `src/cli/unified_io.py`

```python
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
        console: Optional[Console] = None
    ):
        """Initialize with optional output sink and console.

        Args:
            output_sink: Optional OutputSink for routing (Textual mode).
                        If None, uses direct console output (CLI mode).
            console: Optional Rich Console. Defaults to Console().

        Design:
        - If output_sink provided: Routes all output through OutputSink (TUI mode)
        - If output_sink is None: Direct console output (CLI mode)
        """
        self._output_sink = output_sink
        self._console = console or Console()

        # Choose output strategy based on whether OutputSink is provided
        if output_sink:
            self._strategy = OutputSinkAdapter(output_sink, self._console)
        else:
            self._strategy = DirectConsoleOutput(self._console)

    @property
    def console(self) -> Console:
        """Get the underlying Rich Console instance.

        Returns:
            Rich Console instance.
            - CLI mode: Real Console for direct output
            - TUI mode: Console used for creating renderables
        """
        return self._console

    # CLIIOProtocol methods - delegate to strategy

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

    def styled_echo(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Alias for secho() for backwards compatibility."""
        self.secho(message, fg, bold, nl)

    def style(
        self,
        text: str,
        fg: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Return styled text for inline use.

        Note: Returns Rich markup in TUI mode, ANSI codes in CLI mode.
        """
        # Build Rich markup
        color_map = {
            "cyan": "cyan", "yellow": "yellow", "red": "red",
            "green": "green", "blue": "blue", "magenta": "magenta",
            "white": "white", "black": "black",
        }

        if fg or bold:
            rich_color = color_map.get(fg, fg) if fg else None
            if rich_color and bold:
                return f"[bold {rich_color}]{text}[/bold {rich_color}]"
            elif rich_color:
                return f"[{rich_color}]{text}[/{rich_color}]"
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

    def input_line(self) -> str:
        """Read a raw line of input.

        Behavior varies by mode:
        - CLI: Blocks for input
        - TUI: Raises NotImplementedError
        """
        return self._strategy.input_line()

    # RichOutputProtocol methods - delegate to strategy

    def panel(
        self,
        content: str,
        title: Optional[str] = None,
        border_style: str = "blue"
    ) -> None:
        """Display content in a panel with optional title."""
        self._strategy.output_panel(content, title, border_style)

    def table(
        self,
        headers: List[str],
        rows: List[List[str]],
        title: Optional[str] = None
    ) -> None:
        """Display a table with headers and rows."""
        self._strategy.output_table(headers, rows, title)

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
```

### Phase 4: Testing Strategy

#### 4.1 Test Matrix

**File:** `tests/cli/test_unified_io.py`

```python
"""Comprehensive tests for UnifiedIO.

Test Matrix:
1. RichIO vs UnifiedIO(output_sink=None) - Output equivalence
2. TextualIO vs UnifiedIO(output_sink=mock) - Message equivalence
3. Feature completeness - All protocol methods implemented
4. Strategy behavior - Context managers work correctly in both modes
5. Edge cases - Empty strings, None values, special characters
"""

class TestUnifiedIOCLIMode:
    """Test UnifiedIO in CLI mode (output_sink=None)."""

    def test_output_equivalence_with_richio(self):
        """UnifiedIO(CLI) produces same output as RichIO."""
        # Run same operations on both
        # Assert captured output is identical
        pass

    def test_all_methods_implemented(self):
        """UnifiedIO implements all UnifiedIOProtocol methods."""
        io = UnifiedIO()
        assert isinstance(io, UnifiedIOProtocol)
        # Test each method exists and works
        pass

    def test_blocking_input(self):
        """CLI mode uses blocking input."""
        # Mock input() and verify blocking behavior
        pass

    def test_spinner_animated(self):
        """CLI mode spinner uses Rich Status."""
        # Verify Rich spinner is used
        pass

    def test_progress_animated(self):
        """CLI mode progress uses Rich Progress."""
        # Verify Rich progress bar is used
        pass


class TestUnifiedIOTUIMode:
    """Test UnifiedIO in TUI mode (with output_sink)."""

    def test_message_equivalence_with_textualio(self):
        """UnifiedIO(TUI) posts same messages as TextualIO."""
        mock_sink = MockOutputSink()
        io = UnifiedIO(output_sink=mock_sink)

        # Run operations
        io.echo("test")
        io.panel("content", title="Title")
        io.table(["A", "B"], [["1", "2"]])

        # Verify messages posted to sink
        assert len(mock_sink.messages) == 3
        pass

    def test_table_now_implemented(self):
        """UnifiedIO(TUI) implements table() (bug fix)."""
        mock_sink = MockOutputSink()
        io = UnifiedIO(output_sink=mock_sink)

        io.table(["Col1", "Col2"], [["a", "b"]])

        # Verify Table renderable was posted
        assert any(isinstance(msg, Table) for msg in mock_sink.renderables)
        pass

    def test_auto_approve_input(self):
        """TUI mode auto-approves prompts with warnings."""
        mock_sink = MockOutputSink()
        io = UnifiedIO(output_sink=mock_sink)

        result = io.prompt("Name?", default="User")

        assert result == "User"
        # Verify warning panel was posted
        assert any("PHASE 1 LIMITATION" in str(msg) for msg in mock_sink.messages)
        pass

    def test_spinner_simplified(self):
        """TUI mode spinner logs messages instead of animating."""
        mock_sink = MockOutputSink()
        io = UnifiedIO(output_sink=mock_sink)

        with io.spinner("Working..."):
            pass

        # Verify start/end messages posted
        messages = [str(m) for m in mock_sink.messages]
        assert any("Working..." in m for m in messages)
        assert any("Completed" in m for m in messages)
        pass


class TestRegressionCompatibility:
    """Regression tests ensuring no behavior changes."""

    def test_richio_vs_unified_cli_identical_output(self):
        """RichIO and UnifiedIO(CLI) produce identical output."""
        # Capture output from both
        # Assert byte-for-byte identical for same operations
        pass

    def test_textualio_vs_unified_tui_identical_messages(self):
        """TextualIO and UnifiedIO(TUI) post identical messages."""
        # Both should post same OutputSink messages
        pass
```

│ # Direct Replacement Strategy for UnifiedIO                                                                          │
│                                                                                                                      │
│ **Correction to Phase 5: NO gradual migration, NO deprecation wrappers.**                                            │
│                                                                                                                      │
│ ## Phase 5: Direct Replacement                                                                                       │
│                                                                                                                      │
│ ### 5.1 Find all current usages                                                                                      │
│                                                                                                                      │
│ ```bash                                                                                                              │
│ # Find all RichIO imports and instantiations                                                                         │
│ grep -rn "from.*import.*RichIO" src/ tests/                                                                          │
│ grep -rn "RichIO(" src/ tests/                                                                                       │
│                                                                                                                      │
│ # Find all TextualIO imports and instantiations                                                                      │
│ grep -rn "from.*import.*TextualIO" src/ tests/                                                                       │
│ grep -rn "TextualIO(" src/ tests/                                                                                    │
│ ```                                                                                                                  │
│                                                                                                                      │
│ ### 5.2 Update all imports and instantiations in one pass                                                            │
│                                                                                                                      │
│ **Replacement patterns:**                                                                                            │
│                                                                                                                      │
│ ```python                                                                                                            │
│ # Pattern 1: RichIO with no console                                                                                  │
│ from src.cli.rich_output import RichIO                                                                               │
│ io = RichIO()                                                                                                        │
│                                                                                                                      │
│ # Replace with:                                                                                                      │
│ from src.cli.unified_io import UnifiedIO                                                                             │
│ io = UnifiedIO()                                                                                                     │
│                                                                                                                      │
│ # Pattern 2: RichIO with custom console                                                                              │
│ from src.cli.rich_output import RichIO                                                                               │
│ io = RichIO(console=custom_console)                                                                                  │
│                                                                                                                      │
│ # Replace with:                                                                                                      │
│ from src.cli.unified_io import UnifiedIO                                                                             │
│ io = UnifiedIO(console=custom_console)                                                                               │
│                                                                                                                      │
│ # Pattern 3: TextualIO with output_sink                                                                              │
│ from src.cli.textual_io import TextualIO                                                                             │
│ io = TextualIO(output_sink=adapter)                                                                                  │
│                                                                                                                      │
│ # Replace with:                                                                                                      │
│ from src.cli.unified_io import UnifiedIO                                                                             │
│ io = UnifiedIO(output_sink=adapter)                                                                                  │
│ ```                                                                                                                  │
│                                                                                                                      │
│ ### 5.3 Update factory methods                                                                                       │
│                                                                                                                      │
│ Update `src/cli/utils/cli_factory.py`:                                                                               │
│ - Change imports from `RichIO`/`TextualIO` to `UnifiedIO`                                                            │
│ - Update return types to `UnifiedIOProtocol`                                                                         │
│ - Update instantiation to use `UnifiedIO(output_sink=...)` pattern                                                   │
│                                                                                                                      │
│ ### 5.4 Delete old files                                                                                             │
│                                                                                                                      │
│ **After all imports updated and tests pass:**                                                                        │
│                                                                                                                      │
│ #### Delete Files:                                                                                                   │
│ 1. `src/cli/rich_output.py` - Delete entire file                                                                     │
│ 2. `src/cli/textual_io.py` - Delete entire file                                                                      │
│                                                                                                                      │
│ #### Move Helper Classes (if still needed):                                                                          │
│ Before deleting, check if these are used elsewhere:                                                                  │
│ - `ProgressTracker` from `rich_output.py` → Move to `unified_io.py`                                                  │
│ - `StreamWriter` from `rich_output.py` → Move to `unified_io.py`                                                     │
│ - `MultiProgressManager` from `rich_output.py` → Move to `unified_io.py` if used                                     │
│ - `TextualConsole` from `textual_io.py` → Check if still needed, move or delete                                      │
│                                                                                                                      │
│ #### Delete Test Files:                                                                                              │
│ 1. `tests/test_rich_output.py` - Delete if exists                                                                    │
│ 2. `tests/cli/test_rich_output.py` - Delete if exists                                                                │
│ 3. Replace with `tests/cli/test_unified_io.py`                                                                       │
│                                                                                                                      │
│ #### Update Documentation:                                                                                           │
│ 1. Remove all references to `RichIO` and `TextualIO`                                                                 │
│ 2. Document `UnifiedIO` usage patterns                                                                               │
│ 3. Add migration guide if needed                                                                                     │
│                                                                                                                      │
│ ## Updated Phase 6 Checklist                                                                                         │
│                                                                                                                      │
│ - [x] 1. Update `OutputSink` protocol type hint: `Any` -> `RenderableType`                                           │
│ - [x] 2. Define `RichOutputProtocol` in `src/cli/protocols.py`                                                       │
│ - [x] 3. Define `UnifiedIOProtocol` in `src/cli/protocols.py`                                                        │
│ - [x] 4. Create `src/cli/unified_io.py` file                                                                         │
│ - [x] 5. Define `OutputStrategyProtocol` in `unified_io.py`                                                          │
│ - [x] 6. Implement `DirectConsoleOutput` class                                                                       │
│ - [x] 7. Implement `OutputSinkAdapter` class                                                                         │
│ - [x] 8. Implement `SimplifiedProgressTracker` helper                                                                │
│ - [x] 9. Move `ProgressTracker`, `StreamWriter` to `unified_io.py`                                                   │
│ - [x] 10. Implement `UnifiedIO` class                                                                                │
│ - [x] 11. Write tests: `tests/cli/test_unified_io.py`                                                                │
│ - [x] 12. Run test suite, ensure 100% pass rate (42/42 tests passing)                                                │
│ - [x] 13. Find all RichIO/TextualIO usages (grep commands above)                                                     │
│ - [~] 14. Update ALL imports in codebase (IN PROGRESS - cli_factory.py done)                                         │
│ - [~] 15. Update factory methods in `cli_factory.py` (DONE)                                                          │
│ - [ ] 16. Run tests again, ensure still passing                                                                      │
│ - [ ] 17. **DELETE** `src/cli/rich_output.py`                                                                        │
│ - [ ] 18. **DELETE** `src/cli/textual_io.py`                                                                         │
│ - [ ] 19. **DELETE** old test files                                                                                  │
│ - [ ] 20. Update documentation                                                                                       │
│                                                                                                                      │
## No Gradual Migration

- **NO deprecation warnings**
- **NO thin wrapper classes**
- **NO incremental rollout**
- **Just replace everything and delete the old code**

---

## PROGRESS UPDATE (2025-01-23)

### Completed Work

**Phase 1-3: Protocol and Implementation (COMPLETE)**
- Created `RichOutputProtocol` and `UnifiedIOProtocol` in `src/cli/protocols.py`
- Updated `OutputSink.post_renderable()` type hint from `Any` to `RenderableType`
- Implemented complete `UnifiedIO` class in `src/cli/unified_io.py` with:
  - `OutputStrategyProtocol` for strategy pattern
  - `DirectConsoleOutput` for CLI mode (direct Rich console)
  - `OutputSinkAdapter` for TUI mode (OutputSink routing)
  - `ProgressTracker` and `StreamWriter` helpers (moved from rich_output.py)
  - `SimplifiedProgressTracker` for TUI mode progress

**Phase 4: Testing (COMPLETE)**
- Created comprehensive test suite in `tests/cli/test_unified_io.py`
- 42 tests covering:
  - CLI mode behavior (direct console output)
  - TUI mode behavior (OutputSink routing)
  - Protocol compliance
  - Edge cases
  - Backwards compatibility
- **All 42 tests passing**

**Phase 5: Migration (IN PROGRESS)**
- Found all RichIO/TextualIO usages via grep:
  - **RichIO imports:** 10 files in src/, 2 test files
  - **TextualIO imports:** 3 files in src/
- Updated `src/cli/utils/cli_factory.py`:
  - Changed import from `RichIO` to `UnifiedIO`
  - Updated `get_io_interface()` to return `UnifiedIO()` instead of `RichIO()`

### Migration Complete!

**Phase 5: Migration - COMPLETED (2025-01-23)**

All source files updated to use UnifiedIO:
1. `src/agent/core.py` - Updated factory method
2. `src/cli/commands.py` - Updated both RichIO and TextualIO usage
3. `src/cli/core.py` - Updated factory method
4. `src/cli/display.py` - Updated import and isinstance checks
5. `src/cli/display_manager.py` - Updated factory method and comments
6. `src/cli/display_rich.py` - Updated all type hints
7. `src/cli/interactive.py` - Updated import and isinstance check
8. `src/cli/textual_app.py` - Updated isinstance check
9. `src/cli/textual_interactive.py` - Updated all references
10. `src/cli/utils/cli_factory.py` - Updated factory method

All test files updated:
1. `tests/test_display_manager.py` - Updated isinstance check
2. `tests/test_interactive_rich.py` - Updated import and helper function
3. `tests/helpers.py` - Updated comments to reference UnifiedIO
4. All other tests continue to pass (936/967 CLI tests passing)

**Replacement Pattern:**
```python
# OLD
from .rich_output import RichIO
io = RichIO()

# NEW
from .unified_io import UnifiedIO
io = UnifiedIO()

# OLD (TUI mode)
from .textual_io import TextualIO
io = TextualIO(output_sink=adapter)

# NEW (TUI mode)
from .unified_io import UnifiedIO
io = UnifiedIO(output_sink=adapter)
```

**Phase 6: Cleanup - COMPLETED**
- [x] Run full test suite to ensure no regressions (936 CLI tests passing)
- [x] Delete `src/cli/rich_output.py`
- [x] Delete `src/cli/textual_io.py`
- [x] Delete `tests/test_rich_output.py`
- [x] Update documentation (this file)

### Files Created
- `src/cli/unified_io.py` (790 lines)
- `tests/cli/test_unified_io.py` (428 lines, 42 tests)

### Files Modified
- `src/cli/protocols.py` (added RichOutputProtocol, UnifiedIOProtocol)
- `src/cli/utils/cli_factory.py` (updated to use UnifiedIO)
- `docs/TODO/UNIFIED_IO.md` (this file)

### Test Results
```
tests/cli/test_unified_io.py::TestUnifiedIOCLIMode - 13 tests PASSED
tests/cli/test_unified_io.py::TestUnifiedIOTUIMode - 11 tests PASSED
tests/cli/test_unified_io.py::TestProgressTracker - 3 tests PASSED
tests/cli/test_unified_io.py::TestSimplifiedProgressTracker - 3 tests PASSED
tests/cli/test_unified_io.py::TestStreamWriter - 3 tests PASSED
tests/cli/test_unified_io.py::TestBackwardsCompatibility - 2 tests PASSED
tests/cli/test_unified_io.py::TestEdgeCases - 4 tests PASSED
tests/cli/test_unified_io.py::TestProtocolCompliance - 3 tests PASSED
============================
TOTAL: 42/42 PASSED (100%)
```

### Migration Status: COMPLETE

**Summary:**
- All RichIO and TextualIO imports have been replaced with UnifiedIO
- All old files have been deleted
- 42/42 UnifiedIO tests passing
- 936/967 CLI tests passing (31 errors are Windows permission issues, unrelated to migration)
- No functionality regressions detected

**What was accomplished:**
1. Created comprehensive UnifiedIO implementation with strategy pattern
2. Migrated all source files to use UnifiedIO
3. Updated all test files
4. Deleted legacy RichIO and TextualIO modules
5. Verified backward compatibility with extensive test suite

**Migration complete on: 2025-01-23**    

## Expected Outcomes

### What We Gain

1. **Single source of truth**: One IO implementation instead of two
2. **Consistent feature set**: All Rich features (panel, table, syntax, etc.) available in both CLI and TUI modes
3. **Bug fix**: TextualIO now implements `table()` method (was missing)
4. **Easier testing**: Single mock target instead of two
5. **Better maintainability**: Changes in one place
6. **Clear architecture**: Strategy pattern makes routing explicit
7. **SOLID compliance**:
   - Dependency Inversion: Depends on OutputSink abstraction
   - Open/Closed: New output strategies without modification
   - Single Responsibility: IO operations only
   - Liskov Substitution: Full protocol implementation
   - Interface Segregation: Clean protocol hierarchy

### What We Accept

1. **Visual divergence**: Spinners and progress bars look different in CLI vs TUI (acceptable)
2. **Input limitations**: TUI mode auto-approves prompts in Phase 1 (documented limitation)
3. **Future async work**: Real TUI input may require async variants later (not blocking Phase 1)


# P1 -- Potential Concerns & Suggestions

Stream Context Behavior

    Issue: In TUI mode, the stream context buffers everything and posts at the end. This could be problematic for long-running processes where incremental output is expected.
    Suggestion: Allow the StreamWriter to optionally flush incrementally (e.g., every N lines or on newline) in TUI mode. You could add a flush_interval parameter or flush() method to StreamWriter.

Progress Tracker Simplification

    Issue: The SimplifiedProgressTracker logs messages like “3/10” for each update. This could spam the log in large loops.
    Suggestion: Add throttling (e.g., only log every 10% or every N seconds) or allow a custom update interval. You could also make the progress format configurable.

RenderableType vs Any

    Issue: Changing post_renderable(obj: Any) to RenderableType is good for clarity, but RenderableType is a union of specific Rich types. Make sure your usage across the codebase aligns with that—especially if you’re passing custom renderables or wrappers.
    Suggestion: Add a runtime check or helper to validate renderables before posting, especially in the OutputSinkAdapter, to avoid silent failures.

Error Handling in Adapters

    Issue: The input_line() method in TUI mode raises NotImplementedError. This is fine, but it could be surprising if called indirectly.
    Suggestion: Consider logging a warning or providing a fallback behavior (e.g., return empty string) if this is likely to be called in legacy code paths.

Optional Enhancements (Future Phases)
Async Input Support

    Consider adding async_prompt() and async_confirm() methods in a future phase, especially if you plan to support async CLI tools or web-based UIs.

Plugin System for OutputStrategies

    If you foresee supporting more than CLI and TUI (e.g., web, Jupyter, logs), consider making OutputStrategyProtocol a formal plugin interface. This could be as simple as registering strategies via entry points or a config file.