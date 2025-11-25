"""
Cache management functionality for the CLI.
Handles response caching statistics and operations.
"""

from typing import Optional

from .io_interface import CLIIOProtocol
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
        io: CLIIOProtocol,
        formatter: Optional[CacheFormatterProtocol] = None
    ) -> None:
        """Initialize cache manager.

        Args:
            orchestrator: The AgentOrchestrator instance that provides cache
                operations (get_cache_stats, clear_cache, toggle_cache).
            io: I/O interface for output.
            formatter: Optional formatter for display. Defaults to CacheFormatter
                with color support based on io.supports_color().

        State Changes:
            Sets self.orchestrator to the provided orchestrator instance.
            Sets self.io to the provided I/O interface.
            Sets self.formatter to the provided formatter or creates default.
        """
        self.orchestrator = orchestrator
        self.io = io
        # Create formatter with color support based on IO capabilities
        if formatter is not None:
            self.formatter = formatter
        else:
            use_color = getattr(io, 'supports_color', lambda: True)()
            self.formatter = CacheFormatter(use_color=use_color)

    def manage_cache(self, args: str = "") -> None:
        """Manage response cache with subcommands.

        Provides a CLI interface for cache management with the following subcommands:
        - (no args): Display cache statistics including hit rates and entry counts
        - "clear": Clear all cached responses
        - "toggle": Toggle caching on/off

        Args:
            args: Command argument string. Valid values are "", "clear", or "toggle".

        Returns:
            None. Results are displayed via self.io interface.

        Side Effects:
            - When args is "": Outputs cache statistics to self.io (no state changes)
            - When args is "clear": Calls orchestrator.clear_cache() which removes
              all cached responses from memory and disk
            - When args is "toggle": Calls orchestrator.toggle_cache() which changes
              orchestrator.caching_enabled state

        Example:
            >>> cache_mgr.manage_cache()  # Show stats
            >>> cache_mgr.manage_cache("clear")  # Clear cache
            >>> cache_mgr.manage_cache("toggle")  # Toggle on/off
        """
        # Validate subcommand
        validation = validate_subcommand("cache", args)
        if not validation.is_valid:
            self.io.secho(validation.error, fg="red")
            self.io.echo("Usage: /cache [clear|toggle]")
            self.io.echo("  (no args)  - Show cache statistics")
            self.io.echo("  clear      - Clear all cached responses")
            self.io.echo("  toggle     - Toggle caching on/off")
            return

        if validation.subcommand == "":
            # Show cache status using formatter
            stats = self.orchestrator.get_cache_stats()
            enabled = self.orchestrator.caching_enabled
            formatted_stats = self.formatter.format_stats(stats, enabled)
            self.io.echo(formatted_stats)

        elif validation.subcommand == "clear":
            self.orchestrator.clear_cache()
            clear_message = self.formatter.format_clear_message()
            self.io.echo(clear_message)

        elif validation.subcommand == "toggle":
            new_state = self.orchestrator.toggle_cache()
            toggle_message = self.formatter.format_toggle_message(new_state)
            self.io.echo(toggle_message)
