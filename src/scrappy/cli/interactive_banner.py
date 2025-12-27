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

    from typing import Protocol as TypingProtocol

    class OutputSinkProtocol(TypingProtocol):
        """Minimal protocol for TUI output sink."""

        def post_output(self, content: str) -> None:
            """Post text content."""
            ...

        def post_renderable(self, obj: object) -> None:
            """Post a Rich renderable."""
            ...


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


def display_banner_header(io: "UnifiedIOProtocol") -> None:
    """Display banner header (ASCII art + tagline) without any CLI dependencies.

    This can be called immediately on app mount, before CLI is ready.
    No external service dependencies - just needs IO.

    Args:
        io: UnifiedIO instance with console property
    """
    # Display ASCII art banner
    banner = BANNER_ART.format(version=__version__)
    _print_rich(io, banner)
    io.echo()

    # Tagline and help hint
    io.echo("Scrappy can write, test, and debug code right from your terminal.")
    _print_rich(io, "Describe a task to get started or enter [cyan]/help[/] for commands.")
    io.echo()


def display_banner_header_tui(output_sink: "OutputSinkProtocol") -> None:
    """Display banner header in TUI mode using output sink directly.

    This can be called immediately on app mount, before CLI is ready.
    Uses the output_adapter's post_output/post_renderable methods directly,
    bypassing the need for a full UnifiedIO.

    Args:
        output_sink: TUI output adapter with post_output/post_renderable methods
    """
    # Display ASCII art banner
    banner = BANNER_ART.format(version=__version__)
    banner_text = Text.from_markup(banner)
    output_sink.post_renderable(banner_text)
    output_sink.post_output("")

    # Tagline and help hint
    output_sink.post_output("Scrappy can write, test, and debug code right from your terminal.")
    help_text = Text.from_markup("Describe a task to get started or enter [cyan]/help[/] for commands.")
    output_sink.post_renderable(help_text)
    output_sink.post_output("")


def display_banner_status(
    io: "UnifiedIOProtocol",
    api_key_service: Optional[ApiKeyConfigServiceProtocol] = None,
    path_provider: Optional[ScrappyPathProvider] = None,
) -> None:
    """Display banner status lines (providers + workspace).

    This should be called after CLI is ready, as it needs api_key_service
    to check configured providers.

    Args:
        io: UnifiedIO instance with console property
        api_key_service: Optional service for checking API keys (for testing)
        path_provider: Optional path provider (for testing)
    """
    # Use provided dependencies or create defaults
    if api_key_service is None:
        api_key_service = create_api_key_service()
    if path_provider is None:
        path_provider = ScrappyPathProvider(Path.cwd())

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


def display_banner(
    io: "UnifiedIOProtocol",
    api_key_service: Optional[ApiKeyConfigServiceProtocol] = None,
    path_provider: Optional[ScrappyPathProvider] = None,
) -> None:
    """Display welcome banner with ASCII art, providers, and workspace.

    This is the original combined function for backwards compatibility.
    For deferred startup, use display_banner_header() on mount and
    display_banner_status() when CLI is ready.

    Args:
        io: UnifiedIO instance with console property and theme
        api_key_service: Optional service for checking API keys (for testing)
        path_provider: Optional path provider (for testing)
    """
    display_banner_header(io)
    display_banner_status(io, api_key_service, path_provider)
