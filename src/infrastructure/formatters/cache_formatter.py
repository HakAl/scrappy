"""
Cache statistics display formatter.

Extracts display formatting logic from CLI cache manager handler.
"""

from typing import Dict, Any
import click

from .stats_formatter import StatsFormatter


class CacheFormatter(StatsFormatter):
    """Formatter for cache statistics displays.

    Provides formatting for cache statistics including hit rates,
    entry counts, and cache status.
    """

    def format_stats(self, stats: Dict[str, Any], enabled: bool) -> str:
        """Format cache statistics for display.

        Args:
            stats: Cache statistics dict with keys:
                - exact_cache_entries: Number of exact match entries
                - intent_cache_entries: Number of intent match entries
                - exact_hits: Number of exact cache hits
                - intent_hits: Number of intent cache hits
                - exact_misses: Number of cache misses
                - saves: Number of cache saves
                - exact_hit_rate: Hit rate string (e.g., "50.0%")
                - intent_hit_rate: Intent hit rate string
                - cache_file: Path to cache file
            enabled: Whether caching is currently enabled

        Returns:
            Formatted stats string with header, metrics, hit rates
        """
        parts = []

        # Header
        parts.append(self.format_header("Cache Statistics:", width=50))

        # Total entries
        total_entries = stats.get('exact_cache_entries', 0) + stats.get('intent_cache_entries', 0)
        parts.append(f"Total Entries: {total_entries}")

        # Hit counts
        parts.append(f"Exact Cache Hits: {stats.get('exact_hits', 0)}")
        parts.append(f"Intent Cache Hits: {stats.get('intent_hits', 0)}")
        parts.append(f"Cache Misses: {stats.get('exact_misses', 0)}")
        parts.append(f"Cache Saves: {stats.get('saves', 0)}")

        # Hit rates with color coding
        exact_hit_rate = stats.get('exact_hit_rate', '0.0%')
        intent_hit_rate = stats.get('intent_hit_rate', '0.0%')

        parts.append(self.format_hit_rate(exact_hit_rate, "Exact Hit Rate"))
        parts.append(self.format_hit_rate(intent_hit_rate, "Intent Hit Rate"))

        # Cache file location
        parts.append(f"Cache File: {stats.get('cache_file', 'N/A')}")

        # Caching status
        status_label = self.format_boolean_status(enabled, "Enabled", "Disabled")
        parts.append(f"Caching: {status_label}")

        return "\n".join(parts)

    def format_hit_rate(self, rate_str: str, label: str = "Hit Rate") -> str:
        """Format a cache hit rate with color coding.

        Args:
            rate_str: Hit rate string (e.g., "50.0%")
            label: Label for the rate (default: "Hit Rate")

        Returns:
            Formatted line with color (green > 50%, yellow <= 50%)
        """
        # Extract numeric value from string
        try:
            rate_value = float(rate_str.rstrip('%'))
        except (ValueError, AttributeError):
            rate_value = 0.0

        # Determine color (green if > 50%, yellow otherwise)
        color = "green" if rate_value > 50 else "yellow"

        return f"{label}: {click.style(rate_str, fg=color)}"

    def format_toggle_message(self, new_state: bool) -> str:
        """Format the cache toggle success message.

        Args:
            new_state: New caching state (True = enabled, False = disabled)

        Returns:
            Formatted success message with color
        """
        status = "enabled" if new_state else "disabled"
        color = "green" if new_state else "yellow"
        return click.style(f"Response caching {status}.", fg=color)

    def format_clear_message(self) -> str:
        """Format the cache clear success message.

        Returns:
            Formatted success message
        """
        return click.style("Response cache cleared.", fg="green")
