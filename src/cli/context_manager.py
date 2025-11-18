"""
Context management functionality for the CLI.
Handles project context, exploration, and working memory.
"""

from typing import Optional

try:
    from .io_interface import CLIIOProtocol, ClickIO
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cli.io_interface import CLIIOProtocol, ClickIO


class ContextManager:
    """Manages project context and working memory."""

    def __init__(self, orchestrator):
        """Initialize context manager.

        Args:
            orchestrator: The AgentOrchestrator instance
        """
        self.orchestrator = orchestrator

    def manage_context(self, args: str = "", io: Optional[CLIIOProtocol] = None):
        """Manage codebase context, working memory, and context awareness settings.

        Handles multiple subcommands:
        - (no args): Display context status, working memory, and project summary
        - explore: Explore project using cache if available
        - refresh: Force re-exploration of the project
        - clear: Clear cached context data
        - clearmem: Clear session working memory
        - toggle: Toggle context-aware prompts on/off

        Args:
            args: Subcommand string (explore|refresh|clear|clearmem|toggle).
                Empty string displays status.
            io: I/O interface for output. Defaults to ClickIO if None.

        State Changes:
            - explore/refresh: Populates orchestrator.context with project data
            - clear: Removes cached context from disk
            - clearmem: Clears orchestrator working memory
            - toggle: Flips orchestrator.context_aware boolean

        Side Effects:
            - Writes formatted output to stdout via io
            - explore/refresh: May read many files from disk
            - clear: Deletes context cache file

        Returns:
            None
        """
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
                summary = self.orchestrator.context.summary
                if summary and isinstance(summary, str):
                    io.secho("\nProject Summary:", bold=True)
                    io.echo(summary)

        elif args.lower() == "explore":
            io.echo("Exploring current project...")
            result = self.orchestrator.explore_project(force=False)
            if result['status'] == 'cached':
                io.secho("Using cached exploration.", fg="cyan")
            else:
                io.secho(f"Found {result['total_files']} files.", fg="green")

            summary = self.orchestrator.context.summary
            if summary and isinstance(summary, str):
                io.secho("\nGenerated Summary:", bold=True)
                io.echo(summary)

        elif args.lower() == "refresh":
            io.echo("Force re-exploring project...")
            result = self.orchestrator.explore_project(force=True)
            io.secho(f"Found {result['total_files']} files.", fg="green")

            summary = self.orchestrator.context.summary
            if summary and isinstance(summary, str):
                io.secho("\nGenerated Summary:", bold=True)
                io.echo(summary)

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
