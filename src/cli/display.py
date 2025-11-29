"""
Display and UI-related CLI functionality.
Handles help, status, listings, and usage statistics.
"""

from datetime import datetime

from .io_interface import CLIIOProtocol
from .unified_io import UnifiedIO
from .validators import validate_provider
from .display_rich import show_help_table, show_status_rich, show_usage_rich


class CLIDisplay:
    """Handles all display and UI operations for the CLI."""

    def __init__(self, orchestrator, session_start: datetime, io: CLIIOProtocol):
        """Initialize display handler.

        Args:
            orchestrator: The AgentOrchestrator instance
            session_start: When the CLI session started
            io: I/O interface for output
        """
        self.orchestrator = orchestrator
        self.session_start = session_start
        self.io = io

    def show_help(self):
        """Display help information showing all available CLI commands.

        Outputs a formatted list of all available commands grouped by category
        (Chat, Task Operations, Provider Management, Context, Cache, Rate Limits,
        Session, System).

        Side Effects:
            - Writes formatted help text to stdout via self.io

        Returns:
            None
        """
        # Use Rich table if UnifiedIO is available
        if isinstance(self.io, UnifiedIO):
            show_help_table(self.io)
        else:
            # Fallback to basic text display
            self.io.secho("\nAvailable Commands:", fg=self.io.theme.primary, bold=True)
            self.io.secho("-" * 50, fg=self.io.theme.primary)
            self.io.secho("Chat & Conversation:", bold=True)
            self.io.echo(f"  {self.io.style('(text)', fg=self.io.theme.warning)}           - Send message to current brain")
            self.io.echo(f"  {self.io.style('/ml', fg=self.io.theme.warning)}              - Toggle multiline input mode")
            self.io.echo(f"  {self.io.style('/clear', fg=self.io.theme.warning)}           - Clear conversation history")
            self.io.echo()
            self.io.secho("Task Operations:", bold=True)
            self.io.echo(f"  {self.io.style('/plan', fg=self.io.theme.warning)} <task>     - Break down task into steps")
            self.io.echo(f"  {self.io.style('/tasks', fg=self.io.theme.warning)}           - View current plan progress")
            self.io.echo(f"  {self.io.style('/agent', fg=self.io.theme.warning)} <task>    - Run code agent")
            self.io.echo(f"  {self.io.style('/smart', fg=self.io.theme.warning)} <query>   - Research-first query")
            self.io.echo()
            self.io.secho("Provider Management:", bold=True)
            self.io.echo(f"  {self.io.style('/providers', fg=self.io.theme.warning)}       - List all providers")
            self.io.echo(f"  {self.io.style('/brain', fg=self.io.theme.warning)} <name>    - Switch brain")
            self.io.echo(f"  {self.io.style('/status', fg=self.io.theme.warning)}          - Show status")
            self.io.echo(f"  {self.io.style('/usage', fg=self.io.theme.warning)}           - Show usage")
            self.io.echo()
            self.io.secho("System:", bold=True)
            self.io.echo("  /help            - Show this help")
            self.io.echo("  /quit or /exit   - Exit the CLI")

    def show_status(self):
        """Display current system status including brain, providers, and session info.

        Retrieves status from the orchestrator and displays:
        - Current brain provider
        - Total and available providers
        - Tasks completed count
        - Session duration

        Side Effects:
            - Writes formatted status to stdout via self.io

        Returns:
            None
        """
        # Use Rich panel if UnifiedIO is available
        if isinstance(self.io, UnifiedIO):
            show_status_rich(self.io, self.orchestrator, self.session_start)
        else:
            # Fallback to basic text display
            status = self.orchestrator.status()

            self.io.secho("\nSystem Status:", fg=self.io.theme.primary, bold=True)
            self.io.secho("-" * 50, fg=self.io.theme.primary)
            brain = status.get('orchestrator_brain', status.get('brain', 'unknown'))
            self.io.echo(f"Current Brain: {self.io.style(brain, fg=self.io.theme.success, bold=True)}")
            self.io.echo(f"Total Providers: {len(status.get('available_providers', []))}")
            self.io.echo(f"Available: {self.io.style(', '.join(status['available_providers']), fg=self.io.theme.primary)}")
            self.io.echo(f"Tasks Completed: {status.get('tasks_executed', 0)}")
            self.io.echo(f"Session Duration: {datetime.now() - self.session_start}")

    def list_providers(self):
        """List all providers with their configuration and rate limit details.

        Displays each provider's availability status, default model, rate limits
        (requests/day, tokens/minute, tokens/day), and available models.

        Side Effects:
            - Writes formatted provider list to stdout via self.io

        Returns:
            None
        """
        self.io.secho("\nAvailable Providers:", fg=self.io.theme.primary, bold=True)
        self.io.secho("-" * 50, fg=self.io.theme.primary)

        info = self.orchestrator.providers.get_provider_info()

        for name, details in info.items():
            if details['available']:
                limits = details['limits']
                self.io.secho(f"\n{name.upper()} ", fg=self.io.theme.success, bold=True, nl=False)
                self.io.secho("(Active)", fg=self.io.theme.success)
                self.io.echo(f"  Default Model: {details['default_model']}")
                if limits.requests_per_day:
                    self.io.echo(f"  Daily Quota: {limits.requests_per_day:,} requests")
                if limits.tokens_per_minute and limits.tokens_per_minute > 0:
                    self.io.echo(f"  Token Limit: {limits.tokens_per_minute:,} TPM")
                if limits.tokens_per_day:
                    self.io.echo(f"  Daily Tokens: {limits.tokens_per_day:,} TPD")
                self.io.echo(f"  Models: {', '.join(details['models'][:3])}")
                if len(details['models']) > 3:
                    self.io.echo(f"           ... and {len(details['models']) - 3} more")
            else:
                self.io.secho(f"\n{name.upper()} ", fg=self.io.theme.error, bold=True, nl=False)
                self.io.secho("(Not Configured)", fg=self.io.theme.error)

    def switch_brain(self, provider_name: str):
        """Switch the orchestrator's primary brain to a different provider.

        Args:
            provider_name: Name of the provider to switch to. If empty, displays
                current brain and available providers.

        State Changes:
            - Sets orchestrator.brain to the new provider name

        Side Effects:
            - Writes confirmation or error message to stdout via self.io

        Returns:
            None
        """
        if not provider_name:
            self.io.echo(f"Current brain: {self.io.style(self.orchestrator.brain, fg=self.io.theme.success, bold=True)}")
            self.io.echo(f"Available: {', '.join(self.orchestrator.providers.list_available())}")
            self.io.echo("Usage: /brain <provider_name>")
            return

        # Validate provider with availability check
        available = self.orchestrator.providers.list_available()
        validation = validate_provider(provider_name, available_providers=available)

        if not validation.is_valid:
            self.io.secho(f"{validation.error}", fg=self.io.theme.error)
            return

        old_brain = self.orchestrator.brain
        self.orchestrator.brain = validation.provider
        self.io.secho(f"Brain switched: {old_brain} -> {validation.provider}", fg=self.io.theme.success)

    def show_usage(self):
        """Display usage statistics for the current session.

        Shows aggregate and per-provider statistics including:
        - Total tasks executed
        - Cache hits and API calls
        - Session duration
        - Per-provider request counts, token usage, and latency
        - Cache hit rates and entry counts

        Side Effects:
            - Writes formatted usage report to stdout via self.io

        Returns:
            None
        """
        report = self.orchestrator.get_usage_report()

        # Use Rich tables if UnifiedIO is available
        if isinstance(self.io, UnifiedIO):
            show_usage_rich(self.io, report)
        else:
            # Fallback to basic text display
            self.io.secho("\nUsage Statistics:", fg=self.io.theme.primary, bold=True)
            self.io.secho("-" * 50, fg=self.io.theme.primary)
            self.io.echo(f"Total Tasks: {self.io.style(str(report.get('total_tasks', 0)), fg=self.io.theme.success, bold=True)}")
            if 'cached_hits' in report:
                self.io.echo(f"Cache Hits: {self.io.style(str(report['cached_hits']), fg=self.io.theme.success)}")
                self.io.echo(f"API Calls: {report['api_calls']}")
            self.io.echo(f"Session Duration: {report.get('session_duration', 'N/A')}")

            if report.get('by_provider'):
                self.io.secho("\nBy Provider:", bold=True)
                for provider, stats in report['by_provider'].items():
                    self.io.secho(f"  {provider}:", fg=self.io.theme.primary, bold=True)
                    self.io.echo(f"    Requests: {stats['count']}")
                    if stats.get('cached_hits', 0) > 0:
                        self.io.echo(f"    Cached Hits: {self.io.style(str(stats['cached_hits']), fg=self.io.theme.success)}")
                    self.io.echo(f"    Total Tokens: {stats['total_tokens']:,}")
                    self.io.echo(f"    Avg Tokens/Request: {stats['avg_tokens']:.1f}")
                    self.io.echo(f"    Total Latency: {stats['total_latency_ms']:.0f}ms")

            if 'cache_stats' in report:
                cache_stats = report['cache_stats']
                self.io.secho("\nCache:", bold=True)
                self.io.echo(f"  Exact Hit Rate: {cache_stats.get('exact_hit_rate', 'N/A')}")
                self.io.echo(f"  Intent Hit Rate: {cache_stats.get('intent_hit_rate', 'N/A')}")
                total_entries = cache_stats.get('exact_cache_entries', 0) + cache_stats.get('intent_cache_entries', 0)
                self.io.echo(f"  Entries: {total_entries}")

    def list_models(self, provider_name: str = ""):
        """List available models for one or all providers.

        Args:
            provider_name: Specific provider to list models for. If empty,
                lists models for all available providers.

        Side Effects:
            - Writes formatted model list to stdout via self.io

        Returns:
            None
        """
        if provider_name:
            # Validate provider with availability check
            available = self.orchestrator.providers.list_available()
            validation = validate_provider(provider_name, available_providers=available)

            if not validation.is_valid:
                self.io.secho(f"{validation.error}", fg=self.io.theme.error)
                return

            provider = self.orchestrator.providers.get(validation.provider)
            self.io.secho(f"\n{validation.provider.upper()} Models:", bold=True)
            self.io.echo("-" * 50)
            for model in provider.available_models:
                if model == provider.default_model:
                    self.io.echo(f"  - {model} ", nl=False)
                    self.io.secho("(default)", fg=self.io.theme.success)
                else:
                    self.io.echo(f"  - {model}")
        else:
            self.io.secho("\nAll Available Models:", bold=True)
            self.io.echo("-" * 50)

            for name in self.orchestrator.providers.list_available():
                provider = self.orchestrator.providers.get(name)
                self.io.secho(f"\n{name.upper()}:", bold=True)
                for model in provider.available_models:
                    if model == provider.default_model:
                        self.io.echo(f"  - {model} ", nl=False)
                        self.io.secho("(default)", fg=self.io.theme.success)
                    else:
                        self.io.echo(f"  - {model}")
