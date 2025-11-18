"""
Session management functionality for the CLI.
Handles context, cache, rate limits, and session persistence.
"""

import json
from typing import Optional

try:
    from .io_interface import CLIIOProtocol, ClickIO
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cli.io_interface import CLIIOProtocol, ClickIO


class CLISessionManager:
    """Manages session state, caching, and persistence."""

    def __init__(self, orchestrator):
        """Initialize session manager.

        Args:
            orchestrator: The AgentOrchestrator instance
        """
        self.orchestrator = orchestrator

    def manage_context(self, args: str = "", io: Optional[CLIIOProtocol] = None):
        """Manage codebase context."""
        if io is None:
            io = ClickIO()

        if not args:
            # Show context status
            status = self.orchestrator.get_context_status()
            io.secho("\nContext Status:", fg="cyan", bold=True)
            io.secho("-" * 50, fg="cyan")
            io.echo(f"Project: {io.style(str(status['project_path']), fg='bright_white')}")
            io.echo(f"Explored: {io.style('Yes' if status['is_explored'] else 'No', fg='green' if status['is_explored'] else 'yellow')}")
            io.echo(f"Has Summary: {'Yes' if status['has_summary'] else 'No'}")
            if status['explored_at']:
                io.echo(f"Explored At: {status['explored_at']}")
            io.echo(f"Total Files: {status['total_files']}")
            if status.get('has_git_history'):
                io.echo(f"Git Branch: {io.style(status.get('git_branch', 'unknown'), fg='cyan')}")
                io.echo(f"Git Commits: {status.get('git_commits', 0)}")
            io.echo(f"Context Aware: {io.style('Enabled' if self.orchestrator.context_aware else 'Disabled', fg='green' if self.orchestrator.context_aware else 'red')}")
            io.echo(f"Cache File: {status['cache_file']}")
            io.echo(f"Cache Exists: {'Yes' if status['cache_exists'] else 'No'}")

            # Show working memory status
            mem_status = self.orchestrator.get_working_memory_summary()
            io.secho("\nSession Working Memory:", fg="magenta", bold=True)
            io.secho("-" * 50, fg="magenta")
            io.echo(f"Files Cached: {io.style(str(mem_status['files_cached']), fg='cyan')}")
            if mem_status['cached_files']:
                for f in mem_status['cached_files'][-5:]:  # Show last 5
                    io.echo(f"  - {f}")
                if len(mem_status['cached_files']) > 5:
                    io.echo(f"  ... and {len(mem_status['cached_files']) - 5} more")
            io.echo(f"Recent Searches: {mem_status['recent_searches']}")
            io.echo(f"Git Operations: {mem_status['git_operations']}")
            io.echo(f"Discoveries: {mem_status['discoveries']}")

            if status['has_summary']:
                io.secho("\nProject Summary:", bold=True)
                io.echo(self.orchestrator.context.summary)

        elif args.lower() == "explore":
            io.echo("Exploring current project...")
            result = self.orchestrator.explore_project(force=False)
            if result['status'] == 'cached':
                io.secho("Using cached exploration.", fg="cyan")
            else:
                io.secho(f"Found {result['total_files']} files.", fg="green")

            if self.orchestrator.context.summary:
                io.secho("\nGenerated Summary:", bold=True)
                io.echo(self.orchestrator.context.summary)

        elif args.lower() == "refresh":
            io.echo("Force re-exploring project...")
            result = self.orchestrator.explore_project(force=True)
            io.secho(f"Found {result['total_files']} files.", fg="green")

            if self.orchestrator.context.summary:
                io.secho("\nGenerated Summary:", bold=True)
                io.echo(self.orchestrator.context.summary)

        elif args.lower() == "clear":
            self.orchestrator.context.clear_cache()
            io.secho("Context cache cleared.", fg="green")

        elif args.lower() == "clearmem":
            self.orchestrator.clear_working_memory()
            io.secho("Session working memory cleared.", fg="green")

        elif args.lower() == "toggle":
            self.orchestrator.context_aware = not self.orchestrator.context_aware
            status = "enabled" if self.orchestrator.context_aware else "disabled"
            io.secho(f"Context awareness {status}.", fg="green" if self.orchestrator.context_aware else "yellow")

        else:
            io.echo("Usage: /context [explore|refresh|clear|clearmem|toggle]")
            io.echo("  (no args)  - Show context status and working memory")
            io.echo("  explore    - Explore project (uses cache if available)")
            io.echo("  refresh    - Force re-exploration")
            io.echo("  clear      - Clear cached context")
            io.echo("  clearmem   - Clear session working memory")
            io.echo("  toggle     - Toggle context-aware prompts")

    def manage_cache(self, args: str = "", io: Optional[CLIIOProtocol] = None):
        """Manage response cache."""
        if io is None:
            io = ClickIO()

        if not args:
            # Show cache status
            stats = self.orchestrator.get_cache_stats()
            io.secho("\nCache Statistics:", bold=True)
            io.echo("-" * 50)
            total_entries = stats.get('exact_cache_entries', 0) + stats.get('intent_cache_entries', 0)
            io.echo(f"Total Entries: {total_entries}")
            io.echo(f"Exact Cache Hits: {stats.get('exact_hits', 0)}")
            io.echo(f"Intent Cache Hits: {stats.get('intent_hits', 0)}")
            io.echo(f"Cache Misses: {stats.get('exact_misses', 0)}")
            io.echo(f"Cache Saves: {stats.get('saves', 0)}")
            exact_hit_rate = stats.get('exact_hit_rate', '0.0%')
            intent_hit_rate = stats.get('intent_hit_rate', '0.0%')
            exact_rate_value = float(exact_hit_rate.rstrip('%'))
            io.secho(f"Exact Hit Rate: {exact_hit_rate}", fg="green" if exact_rate_value > 50 else "yellow")
            io.secho(f"Intent Hit Rate: {intent_hit_rate}", fg="green" if float(intent_hit_rate.rstrip('%')) > 50 else "yellow")
            io.echo(f"Cache File: {stats.get('cache_file', 'N/A')}")
            io.echo(f"Caching: {io.style('Enabled' if self.orchestrator.caching_enabled else 'Disabled', fg='green' if self.orchestrator.caching_enabled else 'red')}")

        elif args.lower() == "clear":
            self.orchestrator.clear_cache()
            io.secho("Response cache cleared.", fg="green")

        elif args.lower() == "toggle":
            new_state = self.orchestrator.toggle_cache()
            status = "enabled" if new_state else "disabled"
            io.secho(f"Response caching {status}.", fg="green" if new_state else "yellow")

        else:
            io.echo("Usage: /cache [clear|toggle]")
            io.echo("  (no args)  - Show cache statistics")
            io.echo("  clear      - Clear all cached responses")
            io.echo("  toggle     - Toggle caching on/off")

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

    def manage_session(self, args: str = "", conversation_history: list = None, auto_save: bool = True, io: Optional[CLIIOProtocol] = None):
        """Manage session persistence.

        Args:
            args: Command arguments
            conversation_history: Current conversation history
            auto_save: Current auto-save setting
            io: I/O interface for output

        Returns:
            dict with keys:
                - conversation_history: Updated conversation history (if loaded)
                - auto_save: Updated auto-save setting (if toggled)
        """
        if io is None:
            io = ClickIO()

        result = {
            'conversation_history': conversation_history,
            'auto_save': auto_save
        }

        if not args:
            # Show session info
            session_file = self.orchestrator.context.project_path / ".llm_team_session.json"
            io.secho("\nSession Management:", fg="magenta", bold=True)
            io.secho("-" * 50, fg="magenta")
            io.echo(f"Session File: {session_file}")
            io.echo(f"Session Exists: {'Yes' if session_file.exists() else 'No'}")

            if session_file.exists():
                try:
                    with open(session_file, 'r') as f:
                        data = json.load(f)
                    io.echo(f"Last Saved: {data.get('saved_at', 'unknown')}")
                    io.echo(f"Files Cached: {len(data.get('file_reads', {}))}")
                    io.echo(f"Searches: {len(data.get('search_results', []))}")
                    io.echo(f"Git Ops: {len(data.get('git_operations', []))}")
                    io.echo(f"Discoveries: {len(data.get('discoveries', []))}")
                    io.echo(f"Conversation: {len(data.get('conversation_history', []))} messages")
                except Exception as e:
                    io.echo(f"Error reading session: {e}")

            # Show current memory stats
            mem = self.orchestrator.get_working_memory_summary()
            io.secho("\nCurrent Session Memory:", bold=True)
            io.echo(f"  Files in memory: {mem['files_cached']}")
            io.echo(f"  Searches: {mem['recent_searches']}")
            io.echo(f"  Git ops: {mem['git_operations']}")
            io.echo(f"  Discoveries: {mem['discoveries']}")
            io.echo(f"  Conversation: {len(conversation_history or [])} messages")
            io.echo(f"  Auto-save: {io.style('ON' if auto_save else 'OFF', fg='green' if auto_save else 'yellow')}")

        elif args.lower() == "save":
            try:
                session_file = self.orchestrator.save_session(conversation_history or [])
                io.secho(f"Session saved to: {session_file}", fg="green")
                io.echo(f"  Conversation: {len(conversation_history or [])} messages")
            except Exception as e:
                io.secho(f"Error saving session: {e}", fg="red")

        elif args.lower() == "load":
            load_result = self.orchestrator.load_session()
            if load_result['status'] == 'loaded':
                io.secho(f"Session loaded from {load_result['saved_at']}", fg="green")
                io.echo(f"  Files: {load_result['files_restored']}")
                io.echo(f"  Searches: {load_result['searches_restored']}")
                io.echo(f"  Git ops: {load_result['git_ops_restored']}")
                io.echo(f"  Discoveries: {load_result['discoveries_restored']}")

                # Restore conversation
                conversation = load_result.get('conversation_history', [])
                if conversation:
                    result['conversation_history'] = conversation
                    io.echo(f"  Conversation: {len(conversation)} messages")
            elif load_result['status'] == 'no_session':
                io.secho("No saved session found.", fg="yellow")
            else:
                io.secho(f"Error: {load_result.get('message', 'unknown')}", fg="red")

        elif args.lower() == "clear":
            self.orchestrator.clear_session()
            io.secho("Saved session cleared.", fg="green")

        elif args.lower() == "toggle":
            result['auto_save'] = not auto_save
            status = io.style("ON", fg="green") if result['auto_save'] else io.style("OFF", fg="yellow")
            io.echo(f"Auto-save on exit: {status}")
            if result['auto_save']:
                io.echo("Session will be saved automatically on /quit")
            else:
                io.echo("Session will NOT be saved on /quit (use '/session save' manually)")

        else:
            io.echo("Usage: /session [save|load|clear|toggle]")
            io.echo("  (no args)  - Show session info")
            io.echo("  save       - Save current session to disk")
            io.echo("  load       - Load saved session")
            io.echo("  clear      - Delete saved session file")
            io.echo("  toggle     - Toggle auto-save on/off")
            io.echo(f"\nAuto-save: {io.style('ON' if auto_save else 'OFF', fg='green' if auto_save else 'yellow')}")

        return result
