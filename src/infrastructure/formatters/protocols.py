"""
Protocols for display formatting infrastructure.

This module defines the contracts for formatting statistics, tables,
and other display output. Following SOLID principles, each protocol
has a single, focused responsibility.
"""

from typing import Protocol, Dict, Any, List, Optional, Tuple


class StatsFormatterProtocol(Protocol):
    """Protocol for formatting statistics displays.

    Implementations format statistics data into human-readable output
    with appropriate colors, alignment, and formatting.
    """

    def format_header(self, title: str, width: int = 60) -> str:
        """Format a header with title and separator.

        Args:
            title: The header title text
            width: Total width of the header (default: 60)

        Returns:
            Formatted header string with ANSI color codes
        """
        ...

    def format_key_value(self, key: str, value: Any, indent: int = 0) -> str:
        """Format a key-value pair for display.

        Args:
            key: The key/label text
            value: The value to display
            indent: Number of spaces to indent (default: 0)

        Returns:
            Formatted string like "  Key: value"
        """
        ...

    def format_percentage(
        self,
        value: float,
        total: float,
        label: str = "",
        show_numbers: bool = True
    ) -> str:
        """Format a percentage with color coding.

        Args:
            value: Current value
            total: Total/maximum value
            label: Optional label prefix
            show_numbers: Whether to show numbers (e.g., "10/100 (10%)")

        Returns:
            Formatted string with color based on percentage
            Colors: green < 75%, yellow < 90%, red >= 90%
        """
        ...

    def format_number(self, value: int, with_commas: bool = True) -> str:
        """Format a number for display.

        Args:
            value: The numeric value
            with_commas: Whether to add thousand separators

        Returns:
            Formatted number string (e.g., "1,234,567")
        """
        ...


class RateLimitFormatterProtocol(Protocol):
    """Protocol for formatting rate limit displays.

    Implementations format rate limit status data including quotas,
    usage percentages, and per-model breakdowns.
    """

    def format_status(self, status: Dict[str, Any]) -> str:
        """Format complete rate limit status for display.

        Args:
            status: Rate limit status dict from RateLimitTracker
                Expected keys:
                - last_reset: Dict with 'daily' and 'monthly' timestamps
                - providers: Dict mapping provider names to usage data

        Returns:
            Complete formatted status string with headers, quotas, warnings
        """
        ...

    def format_quota_line(
        self,
        label: str,
        used: int,
        limit: int,
        show_remaining: bool = False
    ) -> str:
        """Format a single quota line with color coding.

        Args:
            label: The quota label (e.g., "Daily Requests")
            used: Amount used
            limit: Maximum limit
            show_remaining: Whether to show remaining amount

        Returns:
            Formatted line like "Daily Requests: 10/100 (10%)" with colors
        """
        ...

    def format_provider_section(
        self,
        provider: str,
        data: Dict[str, Any]
    ) -> str:
        """Format a provider's usage section.

        Args:
            provider: Provider name (e.g., "openai")
            data: Provider usage data with keys:
                - total_requests_today
                - total_tokens_today
                - total_requests_month
                - limits (optional)
                - remaining (optional)
                - by_model (optional)

        Returns:
            Formatted provider section with totals, quotas, model breakdown
        """
        ...

    def format_warnings(self, warnings: List[str]) -> str:
        """Format rate limit warnings.

        Args:
            warnings: List of warning messages

        Returns:
            Formatted warnings section in red
        """
        ...


class CacheFormatterProtocol(Protocol):
    """Protocol for formatting cache statistics displays.

    Implementations format cache statistics including hit rates,
    entry counts, and cache status.
    """

    def get_stats_data(
        self,
        stats: Dict[str, Any],
        enabled: bool
    ) -> Tuple[List[str], List[List[str]], str]:
        """Return structured data for table display.

        Args:
            stats: Cache statistics dict with keys like exact_cache_entries,
                intent_cache_entries, exact_hits, etc.
            enabled: Whether caching is currently enabled

        Returns:
            Tuple of (headers, rows, title) suitable for io.table()
        """
        ...

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
        ...

    def format_hit_rate(self, rate_str: str, label: str = "Hit Rate") -> str:
        """Format a cache hit rate with color coding.

        Args:
            rate_str: Hit rate string (e.g., "50.0%")
            label: Label for the rate (default: "Hit Rate")

        Returns:
            Formatted line with color (green > 50%, yellow <= 50%)
        """
        ...


class TableFormatterProtocol(Protocol):
    """Protocol for formatting table-style displays.

    Implementations format data in table format with columns,
    alignment, and optional colors.
    """

    def format_table(
        self,
        headers: List[str],
        rows: List[List[Any]],
        alignments: Optional[List[str]] = None
    ) -> str:
        """Format data as a table.

        Args:
            headers: Column headers
            rows: List of row data
            alignments: Optional column alignments ('left', 'right', 'center')

        Returns:
            Formatted table string
        """
        ...

    def format_row(
        self,
        values: List[Any],
        widths: List[int],
        alignments: List[str]
    ) -> str:
        """Format a single table row.

        Args:
            values: Cell values
            widths: Column widths
            alignments: Column alignments

        Returns:
            Formatted row string
        """
        ...
