"""
Cache management functionality for the CLI.
Handles response caching statistics and operations.
"""

from typing import Optional

try:
    from .io_interface import CLIIOProtocol, ClickIO
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cli.io_interface import CLIIOProtocol, ClickIO


class CacheManager:
    """Manages response cache operations."""

    def __init__(self, orchestrator):
        """Initialize cache manager.

        Args:
            orchestrator: The AgentOrchestrator instance
        """
        self.orchestrator = orchestrator

    def manage_cache(self, args: str = "", io: Optional[CLIIOProtocol] = None):
        """Manage response cache."""
        if io is None:
            io = ClickIO()

        if not args:
            # Show cache status
            stats = self.orchestrator.get_cache_stats()
            io.secho("\nCache Statistics:", bold=True)
            io.echo("-" * 50)
            total_entries = stats.get('exact_cache_entries', 0) + stats.get('intent_cache_entries', 0)
            io.echo(f"Total Entries: {total_entries}")
            io.echo(f"Exact Cache Hits: {stats.get('exact_hits', 0)}")
            io.echo(f"Intent Cache Hits: {stats.get('intent_hits', 0)}")
            io.echo(f"Cache Misses: {stats.get('exact_misses', 0)}")
            io.echo(f"Cache Saves: {stats.get('saves', 0)}")
            exact_hit_rate = stats.get('exact_hit_rate', '0.0%')
            intent_hit_rate = stats.get('intent_hit_rate', '0.0%')
            exact_rate_value = float(exact_hit_rate.rstrip('%'))
            io.secho(f"Exact Hit Rate: {exact_hit_rate}", fg="green" if exact_rate_value > 50 else "yellow")
            io.secho(f"Intent Hit Rate: {intent_hit_rate}", fg="green" if float(intent_hit_rate.rstrip('%')) > 50 else "yellow")
            io.echo(f"Cache File: {stats.get('cache_file', 'N/A')}")
            io.echo(f"Caching: {io.style('Enabled' if self.orchestrator.caching_enabled else 'Disabled', fg='green' if self.orchestrator.caching_enabled else 'red')}")

        elif args.lower() == "clear":
            self.orchestrator.clear_cache()
            io.secho("Response cache cleared.", fg="green")

        elif args.lower() == "toggle":
            new_state = self.orchestrator.toggle_cache()
            status = "enabled" if new_state else "disabled"
            io.secho(f"Response caching {status}.", fg="green" if new_state else "yellow")

        else:
            io.echo("Usage: /cache [clear|toggle]")
            io.echo("  (no args)  - Show cache statistics")
            io.echo("  clear      - Clear all cached responses")
            io.echo("  toggle     - Toggle caching on/off")
