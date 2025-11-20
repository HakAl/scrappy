"""
Cache management functionality for the CLI.
Handles response caching statistics and operations.
"""

from typing import Optional

from .io_interface import CLIIOProtocol
from .rich_output import RichIO
from .validators import validate_subcommand
from src.infrastructure.formatters import CacheFormatter, CacheFormatterProtocol


class CacheManager:
    """Manages response cache operations.

    This class provides cache management functionality including viewing statistics,
    clearing cached responses, and toggling cache on/off. It wraps the orchestrator's
    cache functionality with a CLI-friendly interface.

    Attributes:
        orchestrator: The AgentOrchestrator instance that owns the actual cache.
        formatter: Formatter for displaying cache statistics.
    """

    def __init__(
        self,
        orchestrator,
        formatter: Optional[CacheFormatterProtocol] = None
    ) -> None:
        """Initialize cache manager.

        Args:
            orchestrator: The AgentOrchestrator instance that provides cache
                operations (get_cache_stats, clear_cache, toggle_cache).
            formatter: Optional formatter for display. Defaults to CacheFormatter.

        State Changes:
            Sets self.orchestrator to the provided orchestrator instance.
            Sets self.formatter to the provided formatter or creates default.
        """
        self.orchestrator = orchestrator
        self.formatter = formatter or CacheFormatter()

    def manage_cache(self, args: str = "", io: Optional[CLIIOProtocol] = None) -> None:
        """Manage response cache with subcommands.

        Provides a CLI interface for cache management with the following subcommands:
        - (no args): Display cache statistics including hit rates and entry counts
        - "clear": Clear all cached responses
        - "toggle": Toggle caching on/off

        Args:
            args: Command argument string. Valid values are "", "clear", or "toggle".
            io: I/O interface for output. Defaults to ClickIO if not provided.

        Returns:
            None. Results are displayed via the io interface.

        Side Effects:
            - When args is "": Outputs cache statistics to io (no state changes)
            - When args is "clear": Calls orchestrator.clear_cache() which removes
              all cached responses from memory and disk
            - When args is "toggle": Calls orchestrator.toggle_cache() which changes
              orchestrator.caching_enabled state

        Example:
            >>> cache_mgr.manage_cache()  # Show stats
            >>> cache_mgr.manage_cache("clear")  # Clear cache
            >>> cache_mgr.manage_cache("toggle")  # Toggle on/off
        """
        if io is None:
            io = RichIO()

        # Validate subcommand
        validation = validate_subcommand("cache", args)
        if not validation.is_valid:
            io.secho(validation.error, fg="red")
            io.echo("Usage: /cache [clear|toggle]")
            io.echo("  (no args)  - Show cache statistics")
            io.echo("  clear      - Clear all cached responses")
            io.echo("  toggle     - Toggle caching on/off")
            return

        if validation.subcommand == "":
            # Show cache status using formatter
            stats = self.orchestrator.get_cache_stats()
            enabled = self.orchestrator.caching_enabled
            formatted_stats = self.formatter.format_stats(stats, enabled)
            io.echo(formatted_stats)

        elif validation.subcommand == "clear":
            self.orchestrator.clear_cache()
            clear_message = self.formatter.format_clear_message()
            io.echo(clear_message)

        elif validation.subcommand == "toggle":
            new_state = self.orchestrator.toggle_cache()
            toggle_message = self.formatter.format_toggle_message(new_state)
            io.echo(toggle_message)
