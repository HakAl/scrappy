"""
Rich-enhanced welcome banner for interactive mode.

Provides a styled welcome banner using Rich Panel with ASCII art
and mode status display.
"""

from typing import Optional
from rich.panel import Panel
from rich.text import Text
from rich.console import Group

from .rich_output import RichIO


def render_welcome_banner(
    io: RichIO,
    multiline_mode: bool = True,
    auto_route_mode: bool = False
) -> None:
    """Render the welcome banner as a Rich Panel.

    Args:
        io: RichIO instance for output
        multiline_mode: Whether multiline input is enabled
        auto_route_mode: Whether auto-routing is enabled
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

    # Combine content - use Group for multiple renderables
    # Title centered, commands left-aligned
    title_text.append("\n")  # Add newline after title
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
    io.console.print(panel)

    # Display mode statuses
    _render_mode_statuses(io, multiline_mode, auto_route_mode)


def _render_mode_statuses(
    io: RichIO,
    multiline_mode: bool,
    auto_route_mode: bool
) -> None:
    """Render the current mode status indicators.

    Args:
        io: RichIO instance for output
        multiline_mode: Whether multiline input is enabled
        auto_route_mode: Whether auto-routing is enabled
    """
    # Multiline mode status
    if multiline_mode:
        io.secho(
            "Multiline input: ON (end line with \\ to continue, /ml to toggle)",
            fg="green"
        )
    else:
        io.secho("Multiline input: OFF (/ml to toggle)", fg="yellow")

    # Auto-routing mode status
    if auto_route_mode:
        io.secho("Auto-routing: ON (task-aware execution)", fg="green")
    else:
        io.secho("Auto-routing: OFF (/auto to enable)", fg="yellow")

    io.echo()
