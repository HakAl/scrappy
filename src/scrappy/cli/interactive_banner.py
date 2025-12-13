"""
Condensed welcome banner for interactive mode.

Provides a minimal welcome banner with essential commands and safety disclaimer.
"""

from typing import TYPE_CHECKING

from scrappy.infrastructure.output_mode import OutputModeContext

if TYPE_CHECKING:
    from scrappy.cli.protocols import UnifiedIOProtocol


def display_banner(
    io: "UnifiedIOProtocol"
) -> None:
    """Display condensed welcome banner.

    Args:
        io: UnifiedIO instance with console property and theme
    """
    theme = io.theme

    # Condensed welcome - no panel, just essential info
    io.secho("Welcome to Scrappy!", fg=theme.primary, bold=True)
    io.echo(f"  {io.style('/help', fg=theme.accent)}   - Show all commands")
    io.echo(f"  {io.style('/agent', fg=theme.accent)}  - Run code agent")
    io.echo("Type a message to chat, or use a slash command.")


def display_disclaimer(io: "UnifiedIOProtocol") -> None:
    """Display safety disclaimer warning.

    Args:
        io: UnifiedIO instance for output
    """
    io.secho(
        "WARNING: This tool can modify files and execute commands.",
        fg="yellow"
    )
    io.secho(
        "Review actions carefully before confirming.",
        fg="yellow"
    )
    io.echo()


def render_welcome_banner(
    io: "UnifiedIOProtocol"
) -> None:
    """Render the welcome banner with disclaimer.

    Args:
        io: UnifiedIO instance with theme for output
    """
    io.echo()

    # Display safety disclaimer first
    display_disclaimer(io)

    # Display condensed banner
    display_banner(io)

    io.echo()
