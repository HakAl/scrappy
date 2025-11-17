"""
Session management functionality for the CLI.
Handles context, cache, rate limits, and session persistence.
"""

import click
import json


class CLISessionManager:
    """Manages session state, caching, and persistence."""

    def __init__(self, orchestrator):
        """Initialize session manager.

        Args:
            orchestrator: The AgentOrchestrator instance
        """
        self.orchestrator = orchestrator

    def manage_context(self, args: str = ""):
        """Manage codebase context."""
        if not args:
            # Show context status
            status = self.orchestrator.get_context_status()
            click.secho("\nContext Status:", fg="cyan", bold=True)
            click.secho("-" * 50, fg="cyan")
            click.echo(f"Project: {click.style(str(status['project_path']), fg='bright_white')}")
            click.echo(f"Explored: {click.style('Yes' if status['is_explored'] else 'No', fg='green' if status['is_explored'] else 'yellow')}")
            click.echo(f"Has Summary: {'Yes' if status['has_summary'] else 'No'}")
            if status['explored_at']:
                click.echo(f"Explored At: {status['explored_at']}")
            click.echo(f"Total Files: {status['total_files']}")
            if status.get('has_git_history'):
                click.echo(f"Git Branch: {click.style(status.get('git_branch', 'unknown'), fg='cyan')}")
                click.echo(f"Git Commits: {status.get('git_commits', 0)}")
            click.echo(f"Context Aware: {click.style('Enabled' if self.orchestrator.context_aware else 'Disabled', fg='green' if self.orchestrator.context_aware else 'red')}")
            click.echo(f"Cache File: {status['cache_file']}")
            click.echo(f"Cache Exists: {'Yes' if status['cache_exists'] else 'No'}")

            # Show working memory status
            mem_status = self.orchestrator.get_working_memory_summary()
            click.secho("\nSession Working Memory:", fg="magenta", bold=True)
            click.secho("-" * 50, fg="magenta")
            click.echo(f"Files Cached: {click.style(str(mem_status['files_cached']), fg='cyan')}")
            if mem_status['cached_files']:
                for f in mem_status['cached_files'][-5:]:  # Show last 5
                    click.echo(f"  - {f}")
                if len(mem_status['cached_files']) > 5:
                    click.echo(f"  ... and {len(mem_status['cached_files']) - 5} more")
            click.echo(f"Recent Searches: {mem_status['recent_searches']}")
            click.echo(f"Git Operations: {mem_status['git_operations']}")
            click.echo(f"Discoveries: {mem_status['discoveries']}")

            if status['has_summary']:
                click.secho("\nProject Summary:", bold=True)
                click.echo(self.orchestrator.context.summary)

        elif args.lower() == "explore":
            click.echo("Exploring current project...")
            result = self.orchestrator.explore_project(force=False)
            if result['status'] == 'cached':
                click.secho("Using cached exploration.", fg="cyan")
            else:
                click.secho(f"Found {result['total_files']} files.", fg="green")

            if self.orchestrator.context.summary:
                click.secho("\nGenerated Summary:", bold=True)
                click.echo(self.orchestrator.context.summary)

        elif args.lower() == "refresh":
            click.echo("Force re-exploring project...")
            result = self.orchestrator.explore_project(force=True)
            click.secho(f"Found {result['total_files']} files.", fg="green")

            if self.orchestrator.context.summary:
                click.secho("\nGenerated Summary:", bold=True)
                click.echo(self.orchestrator.context.summary)

        elif args.lower() == "clear":
            self.orchestrator.context.clear_cache()
            click.secho("Context cache cleared.", fg="green")

        elif args.lower() == "clearmem":
            self.orchestrator.clear_working_memory()
            click.secho("Session working memory cleared.", fg="green")

        elif args.lower() == "toggle":
            self.orchestrator.context_aware = not self.orchestrator.context_aware
            status = "enabled" if self.orchestrator.context_aware else "disabled"
            click.secho(f"Context awareness {status}.", fg="green" if self.orchestrator.context_aware else "yellow")

        else:
            click.echo("Usage: /context [explore|refresh|clear|clearmem|toggle]")
            click.echo("  (no args)  - Show context status and working memory")
            click.echo("  explore    - Explore project (uses cache if available)")
            click.echo("  refresh    - Force re-exploration")
            click.echo("  clear      - Clear cached context")
            click.echo("  clearmem   - Clear session working memory")
            click.echo("  toggle     - Toggle context-aware prompts")

    def manage_cache(self, args: str = ""):
        """Manage response cache."""
        if not args:
            # Show cache status
            stats = self.orchestrator.get_cache_stats()
            click.secho("\nCache Statistics:", bold=True)
            click.echo("-" * 50)
            total_entries = stats.get('exact_cache_entries', 0) + stats.get('intent_cache_entries', 0)
            click.echo(f"Total Entries: {total_entries}")
            click.echo(f"Exact Cache Hits: {stats.get('exact_hits', 0)}")
            click.echo(f"Intent Cache Hits: {stats.get('intent_hits', 0)}")
            click.echo(f"Cache Misses: {stats.get('exact_misses', 0)}")
            click.echo(f"Cache Saves: {stats.get('saves', 0)}")
            exact_hit_rate = stats.get('exact_hit_rate', '0.0%')
            intent_hit_rate = stats.get('intent_hit_rate', '0.0%')
            exact_rate_value = float(exact_hit_rate.rstrip('%'))
            click.secho(f"Exact Hit Rate: {exact_hit_rate}", fg="green" if exact_rate_value > 50 else "yellow")
            click.secho(f"Intent Hit Rate: {intent_hit_rate}", fg="green" if float(intent_hit_rate.rstrip('%')) > 50 else "yellow")
            click.echo(f"Cache File: {stats.get('cache_file', 'N/A')}")
            click.echo(f"Caching: {click.style('Enabled' if self.orchestrator.caching_enabled else 'Disabled', fg='green' if self.orchestrator.caching_enabled else 'red')}")

        elif args.lower() == "clear":
            self.orchestrator.clear_cache()
            click.secho("Response cache cleared.", fg="green")

        elif args.lower() == "toggle":
            new_state = self.orchestrator.toggle_cache()
            status = "enabled" if new_state else "disabled"
            click.secho(f"Response caching {status}.", fg="green" if new_state else "yellow")

        else:
            click.echo("Usage: /cache [clear|toggle]")
            click.echo("  (no args)  - Show cache statistics")
            click.echo("  clear      - Clear all cached responses")
            click.echo("  toggle     - Toggle caching on/off")

    def show_rate_limits(self, args: str = ""):
        """Show rate limit usage (persistent tracking)."""
        if args.lower() == "reset":
            if click.confirm("Reset all rate limit tracking data?", default=False):
                self.orchestrator.reset_rate_tracking()
                click.secho("Rate limit tracking data reset.", fg="green")
            return

        if args.lower().startswith("reset "):
            provider_name = args[6:].strip()
            if click.confirm(f"Reset rate limit tracking for {provider_name}?", default=False):
                self.orchestrator.reset_rate_tracking(provider_name)
                click.secho(f"Rate limit tracking for {provider_name} reset.", fg="green")
            return

        # Get rate limit status
        status = self.orchestrator.get_rate_limit_status()

        click.secho("\nRate Limit Usage (Persistent):", fg="cyan", bold=True)
        click.secho("-" * 60, fg="cyan")

        # Show last reset times
        last_reset = status.get('last_reset', {})
        click.echo(f"Last Daily Reset: {last_reset.get('daily', 'N/A')}")
        click.echo(f"Last Monthly Reset: {last_reset.get('monthly', 'N/A')}")
        click.echo()

        # Filter by provider if specified
        providers_to_show = status.get('providers', {})
        if args and args.lower() not in ['reset']:
            provider_filter = args.lower().strip()
            if provider_filter in providers_to_show:
                providers_to_show = {provider_filter: providers_to_show[provider_filter]}
            else:
                click.secho(f"Provider '{args}' not found in tracking data.", fg="yellow")
                return

        if not providers_to_show:
            click.echo("No usage data recorded yet.")
            click.echo("Rate limits will be tracked as you make API calls.")
            return

        # Check for warnings
        warnings = self.orchestrator.check_rate_limit_warnings()
        if warnings:
            click.secho("WARNINGS:", fg="red", bold=True)
            for warning in warnings:
                click.secho(f"  • {warning}", fg="red")
            click.echo()

        # Show usage by provider
        for provider, data in providers_to_show.items():
            click.secho(f"{provider.upper()}:", fg="green", bold=True)

            # Show totals
            click.echo(f"  Today: {data['total_requests_today']} requests, {data['total_tokens_today']:,} tokens")
            click.echo(f"  This Month: {data['total_requests_month']} requests")

            # Show limits and remaining
            if 'limits' in data:
                limits = data['limits']
                remaining = data.get('remaining', {})

                click.secho("  Quotas:", bold=True)
                if limits.get('requests_per_day'):
                    used = remaining.get('usage_today', 0)
                    left = remaining.get('requests_remaining_today', 0)
                    pct = (used / limits['requests_per_day'] * 100) if limits['requests_per_day'] else 0
                    color = 'green' if pct < 75 else ('yellow' if pct < 90 else 'red')
                    click.echo(f"    Daily Requests: ", nl=False)
                    click.secho(f"{used:,}/{limits['requests_per_day']:,} ({pct:.1f}%)", fg=color)

                if limits.get('requests_per_month'):
                    used = remaining.get('usage_this_month', 0)
                    left = remaining.get('requests_remaining_month', 0)
                    pct = (used / limits['requests_per_month'] * 100) if limits['requests_per_month'] else 0
                    color = 'green' if pct < 75 else ('yellow' if pct < 90 else 'red')
                    click.echo(f"    Monthly Requests: ", nl=False)
                    click.secho(f"{used:,}/{limits['requests_per_month']:,} ({pct:.1f}%)", fg=color)

                if limits.get('tokens_per_day'):
                    used = remaining.get('tokens_today', 0)
                    pct = (used / limits['tokens_per_day'] * 100) if limits['tokens_per_day'] else 0
                    color = 'green' if pct < 75 else ('yellow' if pct < 90 else 'red')
                    click.echo(f"    Daily Tokens: ", nl=False)
                    click.secho(f"{used:,}/{limits['tokens_per_day']:,} ({pct:.1f}%)", fg=color)

                if limits.get('tokens_per_minute'):
                    click.echo(f"    TPM Limit: {limits['tokens_per_minute']:,}")

            # Show per-model breakdown
            if data.get('by_model'):
                click.secho("  By Model:", bold=True)
                for model, model_data in data['by_model'].items():
                    last_req = model_data.get('last_request', 'never')
                    if last_req and last_req != 'never':
                        # Format the timestamp nicely
                        last_req = last_req.split('T')[1].split('.')[0] if 'T' in last_req else last_req
                    click.echo(f"    {model}:")
                    click.echo(f"      Today: {model_data['requests_today']} req, {model_data['tokens_today']:,} tok")
                    click.echo(f"      Last: {last_req}")
            click.echo()

        # Show tracker file location
        tracker_file = self.orchestrator.context.project_path / ".llm_rate_limits.json"
        click.secho(f"Tracking File: {tracker_file}", fg="cyan")

    def manage_session(self, args: str = "", conversation_history: list = None, auto_save: bool = True):
        """Manage session persistence.

        Args:
            args: Command arguments
            conversation_history: Current conversation history
            auto_save: Current auto-save setting

        Returns:
            dict with keys:
                - conversation_history: Updated conversation history (if loaded)
                - auto_save: Updated auto-save setting (if toggled)
        """
        result = {
            'conversation_history': conversation_history,
            'auto_save': auto_save
        }

        if not args:
            # Show session info
            session_file = self.orchestrator.context.project_path / ".llm_team_session.json"
            click.secho("\nSession Management:", fg="magenta", bold=True)
            click.secho("-" * 50, fg="magenta")
            click.echo(f"Session File: {session_file}")
            click.echo(f"Session Exists: {'Yes' if session_file.exists() else 'No'}")

            if session_file.exists():
                try:
                    with open(session_file, 'r') as f:
                        data = json.load(f)
                    click.echo(f"Last Saved: {data.get('saved_at', 'unknown')}")
                    click.echo(f"Files Cached: {len(data.get('file_reads', {}))}")
                    click.echo(f"Searches: {len(data.get('search_results', []))}")
                    click.echo(f"Git Ops: {len(data.get('git_operations', []))}")
                    click.echo(f"Discoveries: {len(data.get('discoveries', []))}")
                    click.echo(f"Conversation: {len(data.get('conversation_history', []))} messages")
                except Exception as e:
                    click.echo(f"Error reading session: {e}")

            # Show current memory stats
            mem = self.orchestrator.get_working_memory_summary()
            click.secho("\nCurrent Session Memory:", bold=True)
            click.echo(f"  Files in memory: {mem['files_cached']}")
            click.echo(f"  Searches: {mem['recent_searches']}")
            click.echo(f"  Git ops: {mem['git_operations']}")
            click.echo(f"  Discoveries: {mem['discoveries']}")
            click.echo(f"  Conversation: {len(conversation_history or [])} messages")
            click.echo(f"  Auto-save: {click.style('ON' if auto_save else 'OFF', fg='green' if auto_save else 'yellow')}")

        elif args.lower() == "save":
            try:
                session_file = self.orchestrator.save_session(conversation_history or [])
                click.secho(f"Session saved to: {session_file}", fg="green")
                click.echo(f"  Conversation: {len(conversation_history or [])} messages")
            except Exception as e:
                click.secho(f"Error saving session: {e}", fg="red")

        elif args.lower() == "load":
            load_result = self.orchestrator.load_session()
            if load_result['status'] == 'loaded':
                click.secho(f"Session loaded from {load_result['saved_at']}", fg="green")
                click.echo(f"  Files: {load_result['files_restored']}")
                click.echo(f"  Searches: {load_result['searches_restored']}")
                click.echo(f"  Git ops: {load_result['git_ops_restored']}")
                click.echo(f"  Discoveries: {load_result['discoveries_restored']}")

                # Restore conversation
                conversation = load_result.get('conversation_history', [])
                if conversation:
                    result['conversation_history'] = conversation
                    click.echo(f"  Conversation: {len(conversation)} messages")
            elif load_result['status'] == 'no_session':
                click.secho("No saved session found.", fg="yellow")
            else:
                click.secho(f"Error: {load_result.get('message', 'unknown')}", fg="red")

        elif args.lower() == "clear":
            self.orchestrator.clear_session()
            click.secho("Saved session cleared.", fg="green")

        elif args.lower() == "toggle":
            result['auto_save'] = not auto_save
            status = click.style("ON", fg="green") if result['auto_save'] else click.style("OFF", fg="yellow")
            click.echo(f"Auto-save on exit: {status}")
            if result['auto_save']:
                click.echo("Session will be saved automatically on /quit")
            else:
                click.echo("Session will NOT be saved on /quit (use '/session save' manually)")

        else:
            click.echo("Usage: /session [save|load|clear|toggle]")
            click.echo("  (no args)  - Show session info")
            click.echo("  save       - Save current session to disk")
            click.echo("  load       - Load saved session")
            click.echo("  clear      - Delete saved session file")
            click.echo("  toggle     - Toggle auto-save on/off")
            click.echo(f"\nAuto-save: {click.style('ON' if auto_save else 'OFF', fg='green' if auto_save else 'yellow')}")

        return result
