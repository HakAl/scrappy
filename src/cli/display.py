"""
Display and UI-related CLI functionality.
Handles help, status, listings, and usage statistics.
"""

import click
from datetime import datetime
from typing import Optional

from .io_interface import CLIIOProtocol, ClickIO


class CLIDisplay:
    """Handles all display and UI operations for the CLI."""

    def __init__(self, orchestrator, session_start: datetime):
        """Initialize display handler.

        Args:
            orchestrator: The AgentOrchestrator instance
            session_start: When the CLI session started
        """
        self.orchestrator = orchestrator
        self.session_start = session_start

    def show_help(self, io: Optional[CLIIOProtocol] = None):
        """Display help information showing all available CLI commands.

        Outputs a formatted list of all available commands grouped by category
        (Chat, Task Operations, Provider Management, Context, Cache, Rate Limits,
        Session, System).

        Args:
            io: I/O interface for output. If None, uses ClickIO.

        Side Effects:
            - Writes formatted help text to stdout via io

        Returns:
            None
        """
        if io is None:
            io = ClickIO()

        io.secho("\nAvailable Commands:", fg="cyan", bold=True)
        io.secho("-" * 50, fg="cyan")
        io.secho("Chat & Conversation:", bold=True)
        io.echo(f"  {io.style('(text)', fg='yellow')}           - Send message to current brain")
        io.echo(f"  {io.style('/ml', fg='yellow')}              - Toggle multiline input mode (ON by default)")
        io.echo(f"  {io.style('/clear', fg='yellow')}           - Clear conversation history")
        io.echo()
        io.secho("Task Operations:", bold=True)
        io.echo(f"  {io.style('/plan', fg='yellow')} <task>     - Break down task into steps (with tracking)")
        io.echo(f"  {io.style('/tasks', fg='yellow')}           - View current plan progress")
        io.echo(f"  {io.style('/reason', fg='yellow')} <q>      - Analyze question with reasoning")
        io.echo(f"  {io.style('/agent', fg='yellow')} <task>    - Run code agent to complete task")
        io.echo(f"  {io.style('/smart', fg='yellow')} <query>   - Research-first query (uses tools)")
        io.echo(f"  {io.style('/smart toggle', fg='yellow')}    - Toggle smart mode always-on")
        io.echo(f"  {io.style('/synthesize', fg='yellow')}      - Combine multiple provider responses")
        io.echo(f"  {io.style('/delegate', fg='yellow')} <p>    - Send prompt to specific provider")
        io.echo(f"  {io.style('/explore', fg='yellow')} [path]  - Explore and learn about a codebase")
        io.echo()
        io.secho("Provider Management:", bold=True)
        io.echo(f"  {io.style('/providers', fg='yellow')}       - List all available providers")
        io.echo(f"  {io.style('/brain', fg='yellow')} <name>    - Switch orchestrator brain")
        io.echo(f"  {io.style('/models', fg='yellow')} [prov]   - List models (optionally for provider)")
        io.echo(f"  {io.style('/status', fg='yellow')}          - Show current system status")
        io.echo(f"  {io.style('/usage', fg='yellow')}           - Show usage statistics")
        io.echo()
        io.secho("Context Management:", bold=True)
        io.echo(f"  {io.style('/context', fg='yellow')}         - Show context status")
        io.echo(f"  {io.style('/context explore', fg='yellow')} - Explore current project")
        io.echo(f"  {io.style('/context clear', fg='yellow')}   - Clear cached context")
        io.echo(f"  {io.style('/context toggle', fg='yellow')}  - Toggle context awareness")
        io.echo()
        io.secho("Cache Management:", bold=True)
        io.echo(f"  {io.style('/cache', fg='yellow')}           - Show cache statistics")
        io.echo("  /cache clear     - Clear response cache")
        io.echo("  /cache toggle    - Toggle caching on/off")
        io.echo()
        io.secho("Rate Limit Tracking:", bold=True)
        io.echo(f"  {io.style('/limits', fg='yellow')}          - Show rate limit usage (persistent)")
        io.echo("  /limits <provider> - Show specific provider usage")
        io.echo("  /limits reset    - Reset rate limit tracking")
        io.echo()
        io.secho("Session Management:", bold=True)
        io.echo(f"  {io.style('/session', fg='yellow')}         - Show session info")
        io.echo("  /session save    - Save current session")
        io.echo("  /session load    - Load previous session")
        io.echo("  /session clear   - Delete saved session")
        io.echo("  /session toggle  - Toggle auto-save on/off")
        io.echo("  (auto-saves on /quit by default)")
        io.echo()
        io.secho("System:", bold=True)
        io.echo("  /help            - Show this help message")
        io.echo("  /quit or /exit   - Exit the CLI")

    def show_status(self, io: Optional[CLIIOProtocol] = None):
        """Display current system status including brain, providers, and session info.

        Retrieves status from the orchestrator and displays:
        - Current brain provider
        - Total and available providers
        - Tasks completed count
        - Session duration

        Args:
            io: I/O interface for output. If None, uses ClickIO.

        Side Effects:
            - Writes formatted status to stdout via io

        Returns:
            None
        """
        if io is None:
            io = ClickIO()

        status = self.orchestrator.status()

        io.secho("\nSystem Status:", fg="cyan", bold=True)
        io.secho("-" * 50, fg="cyan")
        brain = status.get('orchestrator_brain', status.get('brain', 'unknown'))
        io.echo(f"Current Brain: {io.style(brain, fg='green', bold=True)}")
        io.echo(f"Total Providers: {len(status.get('available_providers', []))}")
        io.echo(f"Available: {io.style(', '.join(status['available_providers']), fg='cyan')}")
        io.echo(f"Tasks Completed: {status.get('tasks_executed', 0)}")
        io.echo(f"Session Duration: {datetime.now() - self.session_start}")

    def list_providers(self, io: Optional[CLIIOProtocol] = None):
        """List all providers with their configuration and rate limit details.

        Displays each provider's availability status, default model, rate limits
        (requests/day, tokens/minute, tokens/day), and available models.

        Args:
            io: I/O interface for output. If None, uses ClickIO.

        Side Effects:
            - Writes formatted provider list to stdout via io

        Returns:
            None
        """
        if io is None:
            io = ClickIO()

        io.secho("\nAvailable Providers:", fg="cyan", bold=True)
        io.secho("-" * 50, fg="cyan")

        info = self.orchestrator.providers.get_provider_info()

        for name, details in info.items():
            if details['available']:
                limits = details['limits']
                io.secho(f"\n{name.upper()} ", fg="green", bold=True, nl=False)
                io.secho("(Active)", fg="green")
                io.echo(f"  Default Model: {details['default_model']}")
                if limits.requests_per_day:
                    io.echo(f"  Daily Quota: {limits.requests_per_day:,} requests")
                if limits.tokens_per_minute and limits.tokens_per_minute > 0:
                    io.echo(f"  Token Limit: {limits.tokens_per_minute:,} TPM")
                if limits.tokens_per_day:
                    io.echo(f"  Daily Tokens: {limits.tokens_per_day:,} TPD")
                io.echo(f"  Models: {', '.join(details['models'][:3])}")
                if len(details['models']) > 3:
                    io.echo(f"           ... and {len(details['models']) - 3} more")
            else:
                io.secho(f"\n{name.upper()} ", fg="red", bold=True, nl=False)
                io.secho("(Not Configured)", fg="red")

    def switch_brain(self, provider_name: str, io: Optional[CLIIOProtocol] = None):
        """Switch the orchestrator's primary brain to a different provider.

        Args:
            provider_name: Name of the provider to switch to. If empty, displays
                current brain and available providers.
            io: I/O interface for output. If None, uses ClickIO.

        State Changes:
            - Sets orchestrator.brain to the new provider name

        Side Effects:
            - Writes confirmation or error message to stdout via io

        Returns:
            None
        """
        if io is None:
            io = ClickIO()

        if not provider_name:
            io.echo(f"Current brain: {io.style(self.orchestrator.brain, fg='green', bold=True)}")
            io.echo(f"Available: {', '.join(self.orchestrator.providers.list_available())}")
            io.echo("Usage: /brain <provider_name>")
            return

        provider_name = provider_name.lower().strip()
        available = self.orchestrator.providers.list_available()

        if provider_name not in available:
            io.secho(f"Provider '{provider_name}' not available.", fg="red")
            io.echo(f"Available: {', '.join(available)}")
            return

        old_brain = self.orchestrator.brain
        self.orchestrator.brain = provider_name
        io.secho(f"Brain switched: {old_brain} -> {provider_name}", fg="green")

    def show_usage(self, io: Optional[CLIIOProtocol] = None):
        """Display usage statistics for the current session.

        Shows aggregate and per-provider statistics including:
        - Total tasks executed
        - Cache hits and API calls
        - Session duration
        - Per-provider request counts, token usage, and latency
        - Cache hit rates and entry counts

        Args:
            io: I/O interface for output. If None, uses ClickIO.

        Side Effects:
            - Writes formatted usage report to stdout via io

        Returns:
            None
        """
        if io is None:
            io = ClickIO()

        report = self.orchestrator.get_usage_report()

        io.secho("\nUsage Statistics:", fg="cyan", bold=True)
        io.secho("-" * 50, fg="cyan")
        io.echo(f"Total Tasks: {io.style(str(report.get('total_tasks', 0)), fg='green', bold=True)}")
        if 'cached_hits' in report:
            io.echo(f"Cache Hits: {io.style(str(report['cached_hits']), fg='green')}")
            io.echo(f"API Calls: {report['api_calls']}")
        io.echo(f"Session Duration: {report.get('session_duration', 'N/A')}")

        if report.get('by_provider'):
            io.secho("\nBy Provider:", bold=True)
            for provider, stats in report['by_provider'].items():
                io.secho(f"  {provider}:", fg="cyan", bold=True)
                io.echo(f"    Requests: {stats['count']}")
                if stats.get('cached_hits', 0) > 0:
                    io.echo(f"    Cached Hits: {io.style(str(stats['cached_hits']), fg='green')}")
                io.echo(f"    Total Tokens: {stats['total_tokens']:,}")
                io.echo(f"    Avg Tokens/Request: {stats['avg_tokens']:.1f}")
                io.echo(f"    Total Latency: {stats['total_latency_ms']:.0f}ms")

        if 'cache_stats' in report:
            cache_stats = report['cache_stats']
            io.secho("\nCache:", bold=True)
            io.echo(f"  Exact Hit Rate: {cache_stats.get('exact_hit_rate', 'N/A')}")
            io.echo(f"  Intent Hit Rate: {cache_stats.get('intent_hit_rate', 'N/A')}")
            total_entries = cache_stats.get('exact_cache_entries', 0) + cache_stats.get('intent_cache_entries', 0)
            io.echo(f"  Entries: {total_entries}")

    def list_models(self, provider_name: str = "", io: Optional[CLIIOProtocol] = None):
        """List available models for one or all providers.

        Args:
            provider_name: Specific provider to list models for. If empty,
                lists models for all available providers.
            io: I/O interface for output. If None, uses ClickIO.

        Side Effects:
            - Writes formatted model list to stdout via io

        Returns:
            None
        """
        if io is None:
            io = ClickIO()

        if provider_name:
            provider_name = provider_name.lower().strip()
            available = self.orchestrator.providers.list_available()

            if provider_name not in available:
                io.secho(f"Provider '{provider_name}' not available.", fg="red")
                return

            provider = self.orchestrator.providers.get(provider_name)
            io.secho(f"\n{provider_name.upper()} Models:", bold=True)
            io.echo("-" * 50)
            for model in provider.available_models:
                if model == provider.default_model:
                    io.echo(f"  - {model} ", nl=False)
                    io.secho("(default)", fg="green")
                else:
                    io.echo(f"  - {model}")
        else:
            io.secho("\nAll Available Models:", bold=True)
            io.echo("-" * 50)

            for name in self.orchestrator.providers.list_available():
                provider = self.orchestrator.providers.get(name)
                io.secho(f"\n{name.upper()}:", bold=True)
                for model in provider.available_models:
                    if model == provider.default_model:
                        io.echo(f"  - {model} ", nl=False)
                        io.secho("(default)", fg="green")
                    else:
                        io.echo(f"  - {model}")
