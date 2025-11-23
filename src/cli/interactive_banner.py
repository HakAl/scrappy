"""
Rich-enhanced welcome banner for interactive mode.

Provides a styled welcome banner using Rich Panel with ASCII art
and mode status display.
"""

from typing import Any
from rich.panel import Panel
from rich.text import Text


def display_banner(io: Any) -> None:
    """Display banner using appropriate IO.

    The TextualConsole automatically detects Panel as a renderable
    and posts it via the message queue, ensuring thread-safe display.

    Args:
        io: IO instance with console property (TextualIO or RichIO)
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

    # The console.print() now routes correctly
    # TextualConsole detects Panel as renderable and posts it
    io.console.print(panel)
    io.echo()


def render_welcome_banner(
    io: Any,
    multiline_mode: bool = True,
    auto_route_mode: bool = False
) -> None:
    """Render the welcome banner as a Rich Panel.

    Legacy function for compatibility. New code should use display_banner().

    Args:
        io: IO instance for output
        multiline_mode: Whether multiline input is enabled
        auto_route_mode: Whether auto-routing is enabled
    """
    # Display main banner
    display_banner(io)

    # Display mode statuses
    if multiline_mode:
        io.secho(
            "Multiline input: ON (end line with \\ to continue, /ml to toggle)",
            fg="green"
        )
    else:
        io.secho("Multiline input: OFF (/ml to toggle)", fg="yellow")

    if auto_route_mode:
        io.secho("Auto-routing: ON (task-aware execution)", fg="green")
    else:
        io.secho("Auto-routing: OFF (/auto to enable)", fg="yellow")

    io.echo()
