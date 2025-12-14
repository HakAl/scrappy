"""
Display and UI-related CLI functionality.
Handles help, status, listings, and usage statistics.
"""

from datetime import datetime

from .io_interface import CLIIOProtocol
from .unified_io import UnifiedIO
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
            self.io.echo(f"  {self.io.style('/history', fg=self.io.theme.warning)} [n]     - Show last n messages (default: 10)")
            self.io.echo()
            self.io.secho("Task Operations:", bold=True)
            self.io.echo(f"  {self.io.style('/plan', fg=self.io.theme.warning)} <task>     - Break down task into steps")
            self.io.echo(f"  {self.io.style('/tasks', fg=self.io.theme.warning)}           - View current plan progress")
            self.io.echo(f"  {self.io.style('/agent', fg=self.io.theme.warning)} <task>    - Run code agent")
            self.io.echo(f"  {self.io.style('/smart', fg=self.io.theme.warning)} <query>   - Research-first query")
            self.io.echo()
            self.io.secho("Provider Management:", bold=True)
            self.io.echo(f"  {self.io.style('/models', fg=self.io.theme.warning)} [filter] - List models")
            self.io.echo(f"  {self.io.style('/model', fg=self.io.theme.warning)} [mode]    - Toggle quality/fast mode")
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
        """List available models by group (fast/quality).

        With LiteLLM integration, models are organized into groups rather than
        by individual providers.

        Args:
            provider_name: Optional filter - 'fast', 'quality', or provider name.

        Side Effects:
            - Writes formatted model list to stdout via self.io

        Returns:
            None
        """
        from scrappy.orchestrator.litellm_config import get_configured_models
        from scrappy.infrastructure.config.api_keys import create_api_key_service

        api_key_service = create_api_key_service()
        configured_models = get_configured_models(api_key_service)

        if not configured_models:
            self.io.secho("No models configured. Run /setup to configure API keys.", fg=self.io.theme.warning)
            return

        # Filter by group or provider if specified
        filter_arg = provider_name.strip().lower() if provider_name else ""

        if filter_arg in ("fast", "quality"):
            filtered = [m for m in configured_models if m.group == filter_arg]
            self.io.secho(f"\n{filter_arg.upper()} Models:", bold=True)
            self.io.echo("-" * 50)
            for m in filtered:
                self.io.echo(f"  {m.model_id} ({m.context_length:,} ctx, {m.rpd:,} RPD)")
        elif filter_arg:
            # Filter by provider name
            filtered = [m for m in configured_models if m.provider == filter_arg]
            if not filtered:
                self.io.secho(f"No models found for provider: {filter_arg}", fg=self.io.theme.warning)
                return
            self.io.secho(f"\n{filter_arg.upper()} Models:", bold=True)
            self.io.echo("-" * 50)
            for m in filtered:
                self.io.echo(f"  {m.model_id} [{m.group}] ({m.context_length:,} ctx)")
        else:
            # Show all models grouped by tier
            self.io.secho("\nConfigured Models:", bold=True)
            self.io.echo("-" * 50)

            fast_models = [m for m in configured_models if m.group == "fast"]
            quality_models = [m for m in configured_models if m.group == "quality"]

            if fast_models:
                self.io.secho("\nFAST (speed priority):", fg=self.io.theme.primary)
                for m in fast_models:
                    self.io.echo(f"  {m.model_id} ({m.context_length:,} ctx, {m.rpd:,} RPD)")

            if quality_models:
                self.io.secho("\nQUALITY (reasoning priority):", fg=self.io.theme.primary)
                for m in quality_models:
                    self.io.echo(f"  {m.model_id} ({m.context_length:,} ctx, {m.rpd:,} RPD)")
