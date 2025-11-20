"""
Rate limit display formatter.

Extracts display formatting logic from CLI rate limiter handler.
"""

from typing import Dict, Any, List
import click

from .stats_formatter import StatsFormatter


def extract_time_from_timestamp(timestamp: str) -> str:
    """Extract time portion from ISO timestamp.

    Handles various ISO 8601 formats:
    - 2024-11-18T10:30:45.123456
    - 2024-11-18T10:30:45
    - 2024-11-18T10:30:45Z
    - 2024-11-18T10:30:45+05:00
    - 2024-11-18T10:30:45-08:00

    Args:
        timestamp: ISO format timestamp string

    Returns:
        Time portion (HH:MM:SS) or fallback value
    """
    if timestamp == 'never':
        return 'never'
    if not timestamp:
        return timestamp

    try:
        # Check for ISO format with 'T' separator
        if 'T' not in timestamp:
            return timestamp

        # Extract time portion after 'T'
        time_part = timestamp.split('T')[1]

        # Remove fractional seconds if present (before timezone)
        if '.' in time_part:
            time_part = time_part.split('.')[0]

        # Remove timezone info: Z, +HH:MM, -HH:MM
        # Check for 'Z' suffix
        if time_part.endswith('Z'):
            time_part = time_part[:-1]
        # Check for timezone offset (+ or - followed by time)
        # Be careful not to split on the first character if it's a minus
        for i, char in enumerate(time_part):
            if i > 0 and char in ['+', '-']:
                time_part = time_part[:i]
                break

        return time_part

    except (IndexError, AttributeError):
        return timestamp


class RateLimitFormatter(StatsFormatter):
    """Formatter for rate limit statistics displays.

    Provides formatting for rate limit status including quotas,
    usage percentages, warnings, and per-model breakdowns.
    """

    def format_status(
        self,
        status: Dict[str, Any],
        provider_filter: str = ""
    ) -> str:
        """Format complete rate limit status for display.

        Args:
            status: Rate limit status dict from RateLimitTracker
                Expected keys:
                - last_reset: Dict with 'daily' and 'monthly' timestamps
                - providers: Dict mapping provider names to usage data
            provider_filter: Optional provider name to filter display

        Returns:
            Complete formatted status string with headers, quotas, warnings
        """
        parts = []

        # Header
        parts.append(self.format_header("Rate Limit Usage (Persistent)"))

        # Last reset times
        last_reset = status.get('last_reset', {})
        parts.append(f"Last Daily Reset: {last_reset.get('daily', 'N/A')}")
        parts.append(f"Last Monthly Reset: {last_reset.get('monthly', 'N/A')}")
        parts.append("")  # Empty line

        # Filter providers if requested
        providers_to_show = status.get('providers', {})
        if provider_filter:
            if provider_filter in providers_to_show:
                providers_to_show = {provider_filter: providers_to_show[provider_filter]}
            else:
                header = self.format_header('Rate Limit Usage (Persistent)')
                error_msg = click.style(f"Provider '{provider_filter}' not found in tracking data.", fg='yellow')
                return f"{header}\n{error_msg}"

        # Check if any data
        if not providers_to_show:
            parts.append("No usage data recorded yet.")
            parts.append("Rate limits will be tracked as you make API calls.")
            return "\n".join(parts)

        # Format provider sections
        for provider, data in providers_to_show.items():
            parts.append(self.format_provider_section(provider, data))
            parts.append("")  # Empty line between providers

        return "\n".join(parts)

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
        if limit == 0:
            percentage = 0.0
        else:
            percentage = (used / limit) * 100

        color = self._get_percentage_color(percentage)
        quota_text = f"{used:,}/{limit:,} ({percentage:.1f}%)"

        if show_remaining:
            remaining = limit - used
            quota_text += f" ({remaining:,} remaining)"

        return f"    {label}: {click.style(quota_text, fg=color)}"

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
        parts = []

        # Provider header
        parts.append(click.style(f"{provider.upper()}:", fg="green", bold=True))

        # Show totals
        parts.append(f"  Today: {data['total_requests_today']} requests, {data['total_tokens_today']:,} tokens")
        parts.append(f"  This Month: {data['total_requests_month']} requests")

        # Show limits and remaining
        if 'limits' in data:
            limits = data['limits']
            remaining = data.get('remaining', {})

            parts.append(click.style("  Quotas:", bold=True))

            # Daily requests
            if limits.get('requests_per_day'):
                used = remaining.get('usage_today', 0)
                parts.append(
                    self.format_quota_line(
                        "Daily Requests",
                        used,
                        limits['requests_per_day']
                    )
                )

            # Monthly requests
            if limits.get('requests_per_month'):
                used = remaining.get('usage_this_month', 0)
                parts.append(
                    self.format_quota_line(
                        "Monthly Requests",
                        used,
                        limits['requests_per_month']
                    )
                )

            # Daily tokens
            if limits.get('tokens_per_day'):
                used = remaining.get('tokens_today', 0)
                parts.append(
                    self.format_quota_line(
                        "Daily Tokens",
                        used,
                        limits['tokens_per_day']
                    )
                )

            # TPM limit (no usage tracking, just display limit)
            if limits.get('tokens_per_minute'):
                parts.append(f"    TPM Limit: {limits['tokens_per_minute']:,}")

        # Show per-model breakdown
        if data.get('by_model'):
            parts.append(click.style("  By Model:", bold=True))
            for model, model_data in data['by_model'].items():
                last_req = model_data.get('last_request', 'never')
                if last_req and last_req != 'never':
                    last_req = extract_time_from_timestamp(last_req)
                parts.append(f"    {model}:")
                parts.append(f"      Today: {model_data['requests_today']} req, {model_data['tokens_today']:,} tok")
                parts.append(f"      Last: {last_req}")

        return "\n".join(parts)

    def format_warnings(self, warnings: List[str]) -> str:
        """Format rate limit warnings.

        Args:
            warnings: List of warning messages

        Returns:
            Formatted warnings section in red
        """
        if not warnings:
            return ""

        parts = [click.style("WARNINGS:", fg="red", bold=True)]
        for warning in warnings:
            parts.append(click.style(f"  {warning}", fg="red"))
        parts.append("")  # Empty line after warnings

        return "\n".join(parts)

    def format_tracker_file_location(self, file_path: str) -> str:
        """Format the tracker file location display.

        Args:
            file_path: Path to the tracker file

        Returns:
            Formatted file location string
        """
        return click.style(f"Tracking File: {file_path}", fg="cyan")
