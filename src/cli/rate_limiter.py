"""
Rate limit tracking functionality for the CLI.
Handles display and reset of API rate limit usage.
"""

from typing import Optional
import logging

from .io_interface import CLIIOProtocol
from .validators import validate_subcommand
from src.infrastructure.formatters import RateLimitFormatter, RateLimitFormatterProtocol

logger = logging.getLogger(__name__)


class RateLimiter:
    """Manages rate limit tracking display and operations.

    This class provides a CLI interface for viewing and managing API rate limit
    usage data that is persisted across sessions. It displays usage statistics
    per provider and model, along with quota information and warnings.

    Attributes:
        orchestrator: The AgentOrchestrator instance that provides rate limit
            tracking functionality.
        formatter: Formatter for displaying rate limit statistics.
    """

    def __init__(
        self,
        orchestrator,
        io: CLIIOProtocol,
        formatter: Optional[RateLimitFormatterProtocol] = None
    ) -> None:
        """Initialize rate limiter.

        Args:
            orchestrator: The AgentOrchestrator instance that provides rate limit
                operations (get_rate_limit_status, reset_rate_tracking,
                check_rate_limit_warnings) and context for project path.
            io: I/O interface for output.
            formatter: Optional formatter for display. Defaults to RateLimitFormatter.

        State Changes:
            Sets self.orchestrator to the provided orchestrator instance.
            Sets self.io to the provided I/O interface.
            Sets self.formatter to the provided formatter or creates default.
        """
        self.orchestrator = orchestrator
        self.io = io
        self.formatter = formatter or RateLimitFormatter(io=io)

    def show_rate_limits(self, args: str = "") -> None:
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

        Returns:
            None. Results are displayed via self.io interface.

        Side Effects:
            - When args is "": Reads rate limit status from orchestrator and
              displays formatted output via self.io (no state changes)
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
        # Validate subcommand
        validation = validate_subcommand("limits", args)
        if not validation.is_valid:
            self.io.secho(validation.error, fg=self.io.theme.error)
            self.io.echo("Usage: /limits [reset [provider]|<provider>]")
            self.io.echo("  (no args)     - Show all providers' usage")
            self.io.echo("  reset         - Reset all tracking data")
            self.io.echo("  reset <name>  - Reset specific provider")
            self.io.echo("  <provider>    - Show specific provider only")
            return

        # Handle reset subcommand
        if validation.subcommand == "reset":
            if validation.args:
                # Reset specific provider
                provider_name = validation.args
                if self.io.confirm(f"Reset rate limit tracking for {provider_name}?", default=False):
                    self.orchestrator.reset_rate_tracking(provider_name)
                    self.io.secho(f"Rate limit tracking for {provider_name} reset.", fg=self.io.theme.success)
            else:
                # Reset all
                if self.io.confirm("Reset all rate limit tracking data?", default=False):
                    self.orchestrator.reset_rate_tracking()
                    self.io.secho("Rate limit tracking data reset.", fg=self.io.theme.success)
            return

        # Get rate limit status
        status = self.orchestrator.get_rate_limit_status()

        # Get provider filter if specified
        provider_filter = validation.args.lower().strip() if validation.args else ""

        # Format and display status using formatter
        formatted_output = self.formatter.format_status(status, provider_filter)
        self.io.echo(formatted_output)

        # Check for warnings and display if present
        warnings = self.orchestrator.check_rate_limit_warnings()
        if warnings:
            warnings_output = self.formatter.format_warnings(warnings)
            self.io.echo(warnings_output)

        # Show tracker file location (get from rate tracker storage)
        tracker_file = self.orchestrator.rate_tracker._storage.path
        if tracker_file:
            tracker_location = self.formatter.format_tracker_file_location(str(tracker_file))
            self.io.echo(tracker_location)
