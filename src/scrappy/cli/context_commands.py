"""
Context management functionality for the CLI.
Handles project context, exploration, and working memory commands.
"""

from typing import Optional

from .io_interface import CLIIOProtocol
from .validators import validate_subcommand
from scrappy.infrastructure.theme import ThemeProtocol, DEFAULT_THEME


class CLIContextCommands:
    """Handles CLI context-related commands."""

    def __init__(
        self,
        orchestrator,
        io: CLIIOProtocol,
        theme: Optional[ThemeProtocol] = None,
    ):
        """Initialize context command handler.

        Args:
            orchestrator: The AgentOrchestrator instance
            io: I/O interface for output
            theme: Optional theme for consistent styling
        """
        self.orchestrator = orchestrator
        self.io = io
        self._theme = theme or DEFAULT_THEME

    def manage_context(self, args: str = ""):
        """Manage codebase context, working memory, and context awareness settings.

        Handles multiple subcommands:
        - (no args): Display context status, working memory, and project summary
        - refresh: Force re-exploration of the project
        - clear: Clear cached context data
        - clearmem: Clear session working memory
        - toggle: Toggle context-aware prompts on/off

        Note: Use /explore command for codebase exploration instead of /context explore.

        Args:
            args: Subcommand string (refresh|clear|clearmem|toggle).
                Empty string displays status.

        State Changes:
            - refresh: Populates orchestrator.context with project data
            - clear: Removes cached context from disk
            - clearmem: Clears orchestrator working memory
            - toggle: Flips orchestrator.context_aware boolean

        Side Effects:
            - Writes formatted output to stdout via self.io
            - refresh: May read many files from disk
            - clear: Deletes context cache file

        Returns:
            None
        """
        # Validate subcommand
        validation = validate_subcommand("context", args)
        if not validation.is_valid:
            self.io.secho(validation.error, fg=self._theme.error)
            self.io.echo("Usage: /context [refresh|clear|clearmem|toggle|add]")
            self.io.echo("  (no args)  - Show context status and working memory")
            self.io.echo("  refresh    - Force re-exploration")
            self.io.echo("  clear      - Clear cached context")
            self.io.echo("  clearmem   - Clear session working memory")
            self.io.echo("  toggle     - Toggle context-aware prompts")
            self.io.echo("  add <path> - Add file to context")
            self.io.echo("")
            self.io.echo("Tip: Use /explore to explore the codebase")
            return

        if validation.subcommand == "":
            # Show context status
            status = self.orchestrator.get_context_status()
            self.io.secho("\nContext Status:", fg=self._theme.primary, bold=True)
            self.io.secho("-" * 50, fg=self._theme.primary)
            self.io.echo(f"Project: {self.io.style(str(status['project_path']), fg=self._theme.text)}")
            self.io.echo(f"Explored: {self.io.style('Yes' if status['is_explored'] else 'No', fg=self._theme.success if status['is_explored'] else self._theme.warning)}")
            self.io.echo(f"Has Summary: {'Yes' if status['has_summary'] else 'No'}")
            if status['explored_at']:
                self.io.echo(f"Explored At: {status['explored_at']}")
            self.io.echo(f"Total Files: {status['total_files']}")
            if status.get('has_git_history'):
                self.io.echo(f"Git Branch: {self.io.style(status.get('git_branch', 'unknown'), fg=self._theme.primary)}")
                self.io.echo(f"Git Commits: {status.get('git_commits', 0)}")
            self.io.echo(f"Context Aware: {self.io.style('Enabled' if self.orchestrator.context_aware else 'Disabled', fg=self._theme.success if self.orchestrator.context_aware else self._theme.error)}")
            self.io.echo(f"Cache File: {status['cache_file']}")
            self.io.echo(f"Cache Exists: {'Yes' if status['cache_exists'] else 'No'}")

            # Show working memory status
            mem_status = self.orchestrator.working_memory.get_summary()
            self.io.secho("\nSession Working Memory:", fg=self._theme.accent, bold=True)
            self.io.secho("-" * 50, fg=self._theme.accent)
            self.io.echo(f"Files Cached: {self.io.style(str(mem_status['files_cached']), fg=self._theme.primary)}")
            if mem_status['cached_files']:
                for f in mem_status['cached_files'][-5:]:  # Show last 5
                    self.io.echo(f"  - {f}")
                if len(mem_status['cached_files']) > 5:
                    self.io.echo(f"  ... and {len(mem_status['cached_files']) - 5} more")
            self.io.echo(f"Recent Searches: {mem_status['recent_searches']}")
            self.io.echo(f"Git Operations: {mem_status['git_operations']}")
            self.io.echo(f"Discoveries: {mem_status['discoveries']}")

            if status['has_summary']:
                summary = self.orchestrator.context.summary
                if summary and isinstance(summary, str):
                    self.io.secho("\nProject Summary:", bold=True)
                    self.io.echo(summary)

        elif validation.subcommand == "refresh":
            self.io.echo("Force re-exploring project...")
            result = self.orchestrator.explore_project(force=True)
            self.io.secho(f"Found {result['total_files']} files.", fg=self._theme.success)

            summary = self.orchestrator.context.summary
            if summary and isinstance(summary, str):
                self.io.secho("\nGenerated Summary:", bold=True)
                self.io.echo(summary)

        elif validation.subcommand == "clear":
            self.orchestrator.context.clear_cache()
            self.io.secho("Context cache cleared.", fg=self._theme.success)

        elif validation.subcommand == "clearmem":
            self.orchestrator.working_memory.clear()
            self.io.secho("Session working memory cleared.", fg=self._theme.success)

        elif validation.subcommand == "toggle":
            self.orchestrator.context_aware = not self.orchestrator.context_aware
            status = "enabled" if self.orchestrator.context_aware else "disabled"
            self.io.secho(f"Context awareness {status}.", fg=self._theme.success if self.orchestrator.context_aware else self._theme.warning)

        elif validation.subcommand == "add":
            # Handle add with path argument
            if not validation.args:
                self.io.secho("Error: 'add' requires a file path argument", fg=self._theme.error)
                self.io.echo("Usage: /context add <path>")
            else:
                self.io.echo(f"Adding to context: {validation.args}")
                # The actual add logic would go here
