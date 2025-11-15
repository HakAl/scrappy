"""
Display and UI-related CLI functionality.
Handles help, status, listings, and usage statistics.
"""

import click
from datetime import datetime


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

    def show_help(self):
        """Display help information."""
        click.secho("\nAvailable Commands:", fg="cyan", bold=True)
        click.secho("-" * 50, fg="cyan")
        click.secho("Chat & Conversation:", bold=True)
        click.echo(f"  {click.style('(text)', fg='yellow')}           - Send message to current brain")
        click.echo(f"  {click.style('/ml', fg='yellow')}              - Toggle multiline input mode (ON by default)")
        click.echo(f"  {click.style('/clear', fg='yellow')}           - Clear conversation history")
        click.echo()
        click.secho("Task Operations:", bold=True)
        click.echo(f"  {click.style('/plan', fg='yellow')} <task>     - Break down task into steps (with tracking)")
        click.echo(f"  {click.style('/tasks', fg='yellow')}           - View current plan progress")
        click.echo(f"  {click.style('/reason', fg='yellow')} <q>      - Analyze question with reasoning")
        click.echo(f"  {click.style('/agent', fg='yellow')} <task>    - Run code agent to complete task")
        click.echo(f"  {click.style('/smart', fg='yellow')} <query>   - Research-first query (uses tools)")
        click.echo(f"  {click.style('/smart toggle', fg='yellow')}    - Toggle smart mode always-on")
        click.echo(f"  {click.style('/synthesize', fg='yellow')}      - Combine multiple provider responses")
        click.echo(f"  {click.style('/delegate', fg='yellow')} <p>    - Send prompt to specific provider")
        click.echo(f"  {click.style('/explore', fg='yellow')} [path]  - Explore and learn about a codebase")
        click.echo()
        click.secho("Provider Management:", bold=True)
        click.echo(f"  {click.style('/providers', fg='yellow')}       - List all available providers")
        click.echo(f"  {click.style('/brain', fg='yellow')} <name>    - Switch orchestrator brain")
        click.echo(f"  {click.style('/models', fg='yellow')} [prov]   - List models (optionally for provider)")
        click.echo(f"  {click.style('/status', fg='yellow')}          - Show current system status")
        click.echo(f"  {click.style('/usage', fg='yellow')}           - Show usage statistics")
        click.echo()
        click.secho("Context Management:", bold=True)
        click.echo(f"  {click.style('/context', fg='yellow')}         - Show context status")
        click.echo(f"  {click.style('/context explore', fg='yellow')} - Explore current project")
        click.echo(f"  {click.style('/context clear', fg='yellow')}   - Clear cached context")
        click.echo(f"  {click.style('/context toggle', fg='yellow')}  - Toggle context awareness")
        click.echo()
        click.secho("Cache Management:", bold=True)
        click.echo(f"  {click.style('/cache', fg='yellow')}           - Show cache statistics")
        click.echo("  /cache clear     - Clear response cache")
        click.echo("  /cache toggle    - Toggle caching on/off")
        click.echo()
        click.secho("Rate Limit Tracking:", bold=True)
        click.echo(f"  {click.style('/limits', fg='yellow')}          - Show rate limit usage (persistent)")
        click.echo("  /limits <provider> - Show specific provider usage")
        click.echo("  /limits reset    - Reset rate limit tracking")
        click.echo()
        click.secho("Session Management:", bold=True)
        click.echo(f"  {click.style('/session', fg='yellow')}         - Show session info")
        click.echo("  /session save    - Save current session")
        click.echo("  /session load    - Load previous session")
        click.echo("  /session clear   - Delete saved session")
        click.echo("  /session toggle  - Toggle auto-save on/off")
        click.echo("  (auto-saves on /quit by default)")
        click.echo()
        click.secho("System:", bold=True)
        click.echo("  /help            - Show this help message")
        click.echo("  /quit or /exit   - Exit the CLI")

    def show_status(self):
        """Display current system status."""
        status = self.orchestrator.status()

        click.secho("\nSystem Status:", fg="cyan", bold=True)
        click.secho("-" * 50, fg="cyan")
        brain = status.get('orchestrator_brain', status.get('brain', 'unknown'))
        click.echo(f"Current Brain: {click.style(brain, fg='green', bold=True)}")
        click.echo(f"Total Providers: {len(status.get('available_providers', []))}")
        click.echo(f"Available: {click.style(', '.join(status['available_providers']), fg='cyan')}")
        click.echo(f"Tasks Completed: {status.get('tasks_executed', 0)}")
        click.echo(f"Session Duration: {datetime.now() - self.session_start}")

    def list_providers(self):
        """List all providers with their details."""
        click.secho("\nAvailable Providers:", fg="cyan", bold=True)
        click.secho("-" * 50, fg="cyan")

        info = self.orchestrator.providers.get_provider_info()

        for name, details in info.items():
            if details['available']:
                limits = details['limits']
                click.secho(f"\n{name.upper()} ", fg="green", bold=True, nl=False)
                click.secho("(Active)", fg="green")
                click.echo(f"  Default Model: {details['default_model']}")
                click.echo(f"  Daily Quota: {limits.requests_per_day:,} requests")
                if limits.tokens_per_minute > 0:
                    click.echo(f"  Token Limit: {limits.tokens_per_minute:,} TPM")
                click.echo(f"  Models: {', '.join(details['models'][:3])}")
                if len(details['models']) > 3:
                    click.echo(f"           ... and {len(details['models']) - 3} more")
            else:
                click.secho(f"\n{name.upper()} ", fg="red", bold=True, nl=False)
                click.secho("(Not Configured)", fg="red")

    def switch_brain(self, provider_name: str):
        """Switch the orchestrator brain to a different provider."""
        if not provider_name:
            click.echo(f"Current brain: {click.style(self.orchestrator.brain, fg='green', bold=True)}")
            click.echo(f"Available: {', '.join(self.orchestrator.providers.list_available())}")
            click.echo("Usage: /brain <provider_name>")
            return

        provider_name = provider_name.lower().strip()
        available = self.orchestrator.providers.list_available()

        if provider_name not in available:
            click.secho(f"Provider '{provider_name}' not available.", fg="red")
            click.echo(f"Available: {', '.join(available)}")
            return

        old_brain = self.orchestrator.brain
        self.orchestrator.brain = provider_name
        click.secho(f"Brain switched: {old_brain} -> {provider_name}", fg="green")

    def show_usage(self):
        """Display usage statistics."""
        report = self.orchestrator.get_usage_report()

        click.secho("\nUsage Statistics:", fg="cyan", bold=True)
        click.secho("-" * 50, fg="cyan")
        click.echo(f"Total Tasks: {click.style(str(report.get('total_tasks', 0)), fg='green', bold=True)}")
        if 'cached_hits' in report:
            click.echo(f"Cache Hits: {click.style(str(report['cached_hits']), fg='green')}")
            click.echo(f"API Calls: {report['api_calls']}")
        click.echo(f"Session Duration: {report.get('session_duration', 'N/A')}")

        if report.get('by_provider'):
            click.secho("\nBy Provider:", bold=True)
            for provider, stats in report['by_provider'].items():
                click.secho(f"  {provider}:", fg="cyan", bold=True)
                click.echo(f"    Requests: {stats['count']}")
                if stats.get('cached_hits', 0) > 0:
                    click.echo(f"    Cached Hits: {click.style(str(stats['cached_hits']), fg='green')}")
                click.echo(f"    Total Tokens: {stats['total_tokens']:,}")
                click.echo(f"    Avg Tokens/Request: {stats['avg_tokens']:.1f}")
                click.echo(f"    Total Latency: {stats['total_latency_ms']:.0f}ms")

        if 'cache_stats' in report:
            cache_stats = report['cache_stats']
            click.secho("\nCache:", bold=True)
            click.echo(f"  Exact Hit Rate: {cache_stats.get('exact_hit_rate', 'N/A')}")
            click.echo(f"  Intent Hit Rate: {cache_stats.get('intent_hit_rate', 'N/A')}")
            total_entries = cache_stats.get('exact_cache_entries', 0) + cache_stats.get('intent_cache_entries', 0)
            click.echo(f"  Entries: {total_entries}")

    def list_models(self, provider_name: str = ""):
        """List available models."""
        if provider_name:
            provider_name = provider_name.lower().strip()
            available = self.orchestrator.providers.list_available()

            if provider_name not in available:
                click.secho(f"Provider '{provider_name}' not available.", fg="red")
                return

            provider = self.orchestrator.providers.get(provider_name)
            click.secho(f"\n{provider_name.upper()} Models:", bold=True)
            click.echo("-" * 50)
            for model in provider.available_models:
                if model == provider.default_model:
                    click.echo(f"  - {model} ", nl=False)
                    click.secho("(default)", fg="green")
                else:
                    click.echo(f"  - {model}")
        else:
            click.secho("\nAll Available Models:", bold=True)
            click.echo("-" * 50)

            for name in self.orchestrator.providers.list_available():
                provider = self.orchestrator.providers.get(name)
                click.secho(f"\n{name.upper()}:", bold=True)
                for model in provider.available_models:
                    if model == provider.default_model:
                        click.echo(f"  - {model} ", nl=False)
                        click.secho("(default)", fg="green")
                    else:
                        click.echo(f"  - {model}")
