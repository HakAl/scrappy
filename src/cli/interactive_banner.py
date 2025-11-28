"""
Rich-enhanced welcome banner for interactive mode.

Provides a styled welcome banner using Rich Panel with ASCII art
and mode status display.
"""

from typing import TYPE_CHECKING
from rich.panel import Panel
from rich.text import Text

from src.infrastructure.output_mode import OutputModeContext

if TYPE_CHECKING:
    from src.cli.protocols import UnifiedIOProtocol


def display_banner(io: "UnifiedIOProtocol") -> None:
    """Display banner using appropriate IO.

    The TextualConsole automatically detects Panel as a renderable
    and posts it via the message queue, ensuring thread-safe display.

    Args:
        io: UnifiedIO instance with console property for Rich renderables
    """
    # Build banner content
    title_text = Text()
    title_text.append("SCRAPPY", style="bold cyan")
    title_text.append(" - ", style="dim")
    title_text.append("Interactive Mode", style="bold white")

    # Quick commands section
    commands_text = Text()
    commands_text.append("\nQuick Commands:\n", style="bold")
    commands_text.append("  /help", style="yellow")
    commands_text.append("    - Show all commands\n")
    commands_text.append("  /auto", style="yellow")
    commands_text.append("    - Toggle auto-routing\n")
    commands_text.append("  /plan", style="yellow")
    commands_text.append(" <task> - Create a task plan\n")
    commands_text.append("  /agent", style="yellow")
    commands_text.append(" <task> - Run code agent\n")
    commands_text.append("  /smart", style="yellow")
    commands_text.append(" <q>   - Research-first query\n")
    commands_text.append("  /status", style="yellow")
    commands_text.append("  - Show system status\n")
    commands_text.append("  /quit", style="yellow")
    commands_text.append("    - Exit the CLI\n")
    commands_text.append("\n  ", style="")
    commands_text.append("(any text)", style="bright_white")
    commands_text.append(" - Chat with current brain")

    # Combine content
    title_text.append("\n")
    content = Text()
    content.append_text(title_text)
    content.append_text(commands_text)

    # Create and display panel
    panel = Panel(
        content,
        title="[bold cyan]Welcome[/bold cyan]",
        border_style="cyan",
        padding=(1, 2)
    )

    # Route through appropriate output channel based on mode
    # Check both io.is_tui_mode and OutputModeContext for consistency
    is_tui = (hasattr(io, 'is_tui_mode') and io.is_tui_mode) or OutputModeContext.is_tui_mode()

    if is_tui:
        # TUI mode: post renderable through OutputSink for thread-safe display
        # Validate that output_sink is available
        output_sink = getattr(io, 'output_sink', None) or OutputModeContext.get_output_sink()
        if output_sink is None:
            raise RuntimeError(
                "TUI mode detected but no output_sink available. "
                "Ensure OutputModeContext.set_tui_mode() was called with a valid sink, "
                "or pass an IO with output_sink property."
            )
        output_sink.post_renderable(panel)
    elif hasattr(io, 'console'):
        # CLI mode: print directly to Rich Console
        io.console.print(panel)
    else:
        # Last resort: echo the text content (for non-standard IO implementations)
        io.echo(str(content))


def render_welcome_banner(io: "UnifiedIOProtocol") -> None:
    """Render the welcome banner as a Rich Panel.

    Args:
        io: UnifiedIO instance for output
    """
    # Display main banner
    display_banner(io)

    # Display tips
    io.secho("Tip: End line with \\ to continue on next line", fg="cyan")
    io.echo()
