"""
Rate limit tracking functionality for the CLI.
Handles display and reset of API rate limit usage.
"""

from typing import Optional

try:
    from .io_interface import CLIIOProtocol, ClickIO
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cli.io_interface import CLIIOProtocol, ClickIO


class RateLimiter:
    """Manages rate limit tracking display and operations."""

    def __init__(self, orchestrator):
        """Initialize rate limiter.

        Args:
            orchestrator: The AgentOrchestrator instance
        """
        self.orchestrator = orchestrator

    def show_rate_limits(self, args: str = "", io: Optional[CLIIOProtocol] = None):
        """Show rate limit usage (persistent tracking)."""
        if io is None:
            io = ClickIO()

        if args.lower() == "reset":
            if io.confirm("Reset all rate limit tracking data?", default=False):
                self.orchestrator.reset_rate_tracking()
                io.secho("Rate limit tracking data reset.", fg="green")
            return

        if args.lower().startswith("reset "):
            provider_name = args[6:].strip()
            if io.confirm(f"Reset rate limit tracking for {provider_name}?", default=False):
                self.orchestrator.reset_rate_tracking(provider_name)
                io.secho(f"Rate limit tracking for {provider_name} reset.", fg="green")
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
        if args and args.lower() not in ['reset']:
            provider_filter = args.lower().strip()
            if provider_filter in providers_to_show:
                providers_to_show = {provider_filter: providers_to_show[provider_filter]}
            else:
                io.secho(f"Provider '{args}' not found in tracking data.", fg="yellow")
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
                        last_req = last_req.split('T')[1].split('.')[0] if 'T' in last_req else last_req
                    io.echo(f"    {model}:")
                    io.echo(f"      Today: {model_data['requests_today']} req, {model_data['tokens_today']:,} tok")
                    io.echo(f"      Last: {last_req}")
            io.echo()

        # Show tracker file location
        tracker_file = self.orchestrator.context.project_path / ".llm_rate_limits.json"
        io.secho(f"Tracking File: {tracker_file}", fg="cyan")
