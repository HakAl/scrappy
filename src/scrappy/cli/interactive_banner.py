"""
Welcome banner for interactive mode.

Displays ASCII art logo with provider status and workspace information.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from rich.text import Text

from scrappy import __version__
from scrappy.infrastructure.config.api_keys import (
    ApiKeyConfigServiceProtocol,
    create_api_key_service,
)
from scrappy.infrastructure.paths import ScrappyPathProvider
from scrappy.orchestrator.litellm_config import get_configured_models

if TYPE_CHECKING:
    from scrappy.cli.protocols import UnifiedIOProtocol


# ASCII art banner - SCRAPPY in block letters
BANNER_ART = """\
[bold #ff9900]     Welcome to[/]
[bold cyan]███████╗ ██████╗██████╗  █████╗ ██████╗ ██████╗ ██╗   ██╗[/]
[bold cyan]██╔════╝██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔══██╗╚██╗ ██╔╝[/]
[bold cyan]███████╗██║     ██████╔╝███████║██████╔╝██████╔╝ ╚████╔╝[/]
[bold cyan]╚════██║██║     ██╔══██╗██╔══██║██╔═══╝ ██╔═══╝   ╚██╔╝[/]
[bold cyan]███████║╚██████╗██║  ██║██║  ██║██║     ██║        ██║[/]
[bold cyan]╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝        ╚═╝[/]
                                              [bold #ff9900]CLI Version {version}[/]"""


def _print_rich(io: "UnifiedIOProtocol", markup: str) -> None:
    """Print Rich markup text, handling both CLI and TUI modes.

    Args:
        io: UnifiedIO instance
        markup: Rich markup string to print
    """
    # Create Text object from markup
    text = Text.from_markup(markup)

    # Route through output_sink for TUI mode, direct console for CLI
    if hasattr(io, 'output_sink') and io.output_sink:
        io.output_sink.post_renderable(text)
    else:
        io.console.print(text)


def _get_configured_provider_names(
    api_key_service: ApiKeyConfigServiceProtocol,
) -> list[str]:
    """Get list of configured provider names.

    Args:
        api_key_service: Service for checking API key configuration

    Returns:
        List of provider names with API keys configured
    """
    configured_models = get_configured_models(api_key_service)
    # Get unique provider names, preserving order
    seen = set()
    providers = []
    for model in configured_models:
        if model.provider not in seen:
            seen.add(model.provider)
            providers.append(model.provider.capitalize())
    return providers


def display_banner(
    io: "UnifiedIOProtocol",
    api_key_service: Optional[ApiKeyConfigServiceProtocol] = None,
    path_provider: Optional[ScrappyPathProvider] = None,
) -> None:
    """Display welcome banner with ASCII art, providers, and workspace.

    Args:
        io: UnifiedIO instance with console property and theme
        api_key_service: Optional service for checking API keys (for testing)
        path_provider: Optional path provider (for testing)
    """
    # Use provided dependencies or create defaults
    if api_key_service is None:
        api_key_service = create_api_key_service()
    if path_provider is None:
        path_provider = ScrappyPathProvider(Path.cwd())

    # Display ASCII art banner
    banner = BANNER_ART.format(version=__version__)
    _print_rich(io, banner)
    io.echo()

    # Tagline and help hint
    io.echo("Scrappy can write, test, and debug code right from your terminal.")
    _print_rich(io, "Describe a task to get started or enter [cyan]/help[/] for commands.")
    io.echo()

    # Show configured providers
    providers = _get_configured_provider_names(api_key_service)
    if providers:
        provider_list = ", ".join(f"[cyan]{p}[/]" for p in providers)
        _print_rich(io, f"[green]●[/] Providers: {provider_list}")
    else:
        _print_rich(io, "[yellow]●[/] No providers configured. Run [cyan]/setup[/] to add API keys.")

    # Show workspace
    workspace = path_provider.workspace_display()
    _print_rich(io, f"[green]●[/] Workspace: [cyan]{workspace}[/]")
    io.echo()
