"""
Rate limit tracking functionality for the CLI.
Handles display and reset of API rate limit usage.
"""

from typing import Optional
import logging

from .io_interface import CLIIOProtocol, ClickIO
from .validators import validate_subcommand

logger = logging.getLogger(__name__)


def extract_time_from_timestamp(timestamp: str) -> str:
    """Safely extract time portion from ISO timestamp.

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
    if not timestamp or timestamp == 'never':
        return timestamp or 'never'

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

    except (IndexError, AttributeError) as e:
        logger.debug(f"Failed to parse timestamp '{timestamp}': {e}")
        return timestamp


class RateLimiter:
    """Manages rate limit tracking display and operations.

    This class provides a CLI interface for viewing and managing API rate limit
    usage data that is persisted across sessions. It displays usage statistics
    per provider and model, along with quota information and warnings.

    Attributes:
        orchestrator: The AgentOrchestrator instance that provides rate limit
            tracking functionality.
    """

    def __init__(self, orchestrator) -> None:
        """Initialize rate limiter.

        Args:
            orchestrator: The AgentOrchestrator instance that provides rate limit
                operations (get_rate_limit_status, reset_rate_tracking,
                check_rate_limit_warnings) and context for project path.

        State Changes:
            Sets self.orchestrator to the provided orchestrator instance.
        """
        self.orchestrator = orchestrator

    def show_rate_limits(self, args: str = "", io: Optional[CLIIOProtocol] = None) -> None:
        """Display and manage rate limit usage data.

        Shows persistent rate limit tracking data including requests and tokens
        used per provider and model, quota usage percentages, and warnings when
        approaching limits.

        Args:
            args: Command argument string. Valid values are:
                - "": Show all providers' rate limit usage
                - "reset": Reset all tracking data (with confirmation)
                - "reset <provider>": Reset specific provider's data (with confirmation)
                - "<provider>": Filter display to specific provider only

            io: I/O interface for output. Defaults to ClickIO if not provided.

        Returns:
            None. Results are displayed via the io interface.

        Side Effects:
            - When args is "": Reads rate limit status from orchestrator and
              displays formatted output (no state changes)
            - When args is "reset": Prompts for confirmation, then calls
              orchestrator.reset_rate_tracking() which clears persisted tracking
              data in .llm_rate_limits.json
            - When args is "reset <provider>": Prompts for confirmation, then
              calls orchestrator.reset_rate_tracking(provider) which clears
              tracking data for that specific provider

        Output Sections:
            - Last reset times (daily and monthly)
            - Warnings for providers approaching limits (if any)
            - Per-provider usage showing daily/monthly requests and tokens
            - Quota percentages with color-coded status (green/yellow/red)
            - Per-model breakdown with last request timestamps
            - Tracker file location

        Example:
            >>> rate_limiter.show_rate_limits()  # Show all
            >>> rate_limiter.show_rate_limits("anthropic")  # Filter to anthropic
            >>> rate_limiter.show_rate_limits("reset")  # Reset all
            >>> rate_limiter.show_rate_limits("reset openai")  # Reset openai only
        """
        if io is None:
            io = ClickIO()

        # Validate subcommand
        validation = validate_subcommand("limits", args)
        if not validation.is_valid:
            io.secho(validation.error, fg="red")
            io.echo("Usage: /limits [reset [provider]|<provider>]")
            io.echo("  (no args)     - Show all providers' usage")
            io.echo("  reset         - Reset all tracking data")
            io.echo("  reset <name>  - Reset specific provider")
            io.echo("  <provider>    - Show specific provider only")
            return

        # Handle reset subcommand
        if validation.subcommand == "reset":
            if validation.args:
                # Reset specific provider
                provider_name = validation.args
                if io.confirm(f"Reset rate limit tracking for {provider_name}?", default=False):
                    self.orchestrator.reset_rate_tracking(provider_name)
                    io.secho(f"Rate limit tracking for {provider_name} reset.", fg="green")
            else:
                # Reset all
                if io.confirm("Reset all rate limit tracking data?", default=False):
                    self.orchestrator.reset_rate_tracking()
                    io.secho("Rate limit tracking data reset.", fg="green")
            return

        # Get rate limit status
        status = self.orchestrator.get_rate_limit_status()

        io.secho("\nRate Limit Usage (Persistent):", fg="cyan", bold=True)
        io.secho("-" * 60, fg="cyan")

        # Show last reset times
        last_reset = status.get('last_reset', {})
        io.echo(f"Last Daily Reset: {last_reset.get('daily', 'N/A')}")
        io.echo(f"Last Monthly Reset: {last_reset.get('monthly', 'N/A')}")
        io.echo()

        # Filter by provider if specified
        providers_to_show = status.get('providers', {})
        if validation.args:
            provider_filter = validation.args.lower().strip()
            if provider_filter in providers_to_show:
                providers_to_show = {provider_filter: providers_to_show[provider_filter]}
            else:
                io.secho(f"Provider '{validation.args}' not found in tracking data.", fg="yellow")
                return

        if not providers_to_show:
            io.echo("No usage data recorded yet.")
            io.echo("Rate limits will be tracked as you make API calls.")
            # Show tracker file location even when no data
            tracker_file = self.orchestrator.context.project_path / ".llm_rate_limits.json"
            io.secho(f"Tracking File: {tracker_file}", fg="cyan")
            return

        # Check for warnings
        warnings = self.orchestrator.check_rate_limit_warnings()
        if warnings:
            io.secho("WARNINGS:", fg="red", bold=True)
            for warning in warnings:
                io.secho(f"  {warning}", fg="red")
            io.echo()

        # Show usage by provider
        for provider, data in providers_to_show.items():
            io.secho(f"{provider.upper()}:", fg="green", bold=True)

            # Show totals
            io.echo(f"  Today: {data['total_requests_today']} requests, {data['total_tokens_today']:,} tokens")
            io.echo(f"  This Month: {data['total_requests_month']} requests")

            # Show limits and remaining
            if 'limits' in data:
                limits = data['limits']
                remaining = data.get('remaining', {})

                io.secho("  Quotas:", bold=True)
                if limits.get('requests_per_day'):
                    used = remaining.get('usage_today', 0)
                    left = remaining.get('requests_remaining_today', 0)
                    pct = (used / limits['requests_per_day'] * 100) if limits['requests_per_day'] else 0
                    color = 'green' if pct < 75 else ('yellow' if pct < 90 else 'red')
                    io.echo(f"    Daily Requests: ", nl=False)
                    io.secho(f"{used:,}/{limits['requests_per_day']:,} ({pct:.1f}%)", fg=color)

                if limits.get('requests_per_month'):
                    used = remaining.get('usage_this_month', 0)
                    left = remaining.get('requests_remaining_month', 0)
                    pct = (used / limits['requests_per_month'] * 100) if limits['requests_per_month'] else 0
                    color = 'green' if pct < 75 else ('yellow' if pct < 90 else 'red')
                    io.echo(f"    Monthly Requests: ", nl=False)
                    io.secho(f"{used:,}/{limits['requests_per_month']:,} ({pct:.1f}%)", fg=color)

                if limits.get('tokens_per_day'):
                    used = remaining.get('tokens_today', 0)
                    pct = (used / limits['tokens_per_day'] * 100) if limits['tokens_per_day'] else 0
                    color = 'green' if pct < 75 else ('yellow' if pct < 90 else 'red')
                    io.echo(f"    Daily Tokens: ", nl=False)
                    io.secho(f"{used:,}/{limits['tokens_per_day']:,} ({pct:.1f}%)", fg=color)

                if limits.get('tokens_per_minute'):
                    io.echo(f"    TPM Limit: {limits['tokens_per_minute']:,}")

            # Show per-model breakdown
            if data.get('by_model'):
                io.secho("  By Model:", bold=True)
                for model, model_data in data['by_model'].items():
                    last_req = model_data.get('last_request', 'never')
                    if last_req and last_req != 'never':
                        # Format the timestamp nicely
                        last_req = extract_time_from_timestamp(last_req)
                    io.echo(f"    {model}:")
                    io.echo(f"      Today: {model_data['requests_today']} req, {model_data['tokens_today']:,} tok")
                    io.echo(f"      Last: {last_req}")
            io.echo()

        # Show tracker file location
        tracker_file = self.orchestrator.context.project_path / ".llm_rate_limits.json"
        io.secho(f"Tracking File: {tracker_file}", fg="cyan")
