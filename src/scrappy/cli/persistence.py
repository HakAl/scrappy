"""
Session persistence functionality for the CLI.
Handles saving, loading, and managing session state.
"""

import json
from typing import Any

from .io_interface import CLIIOProtocol
from .validators import validate_subcommand


class SessionPersistence:
    """Manages session persistence operations.

    This class provides functionality for displaying session statistics and
    clearing session state. Session data includes file caches, search results,
    git operations, and discoveries stored in .session.json.

    Note: Conversation history is now managed separately by ConversationStore.

    Attributes:
        orchestrator: The AgentOrchestrator instance that provides session
            storage operations.
        io: I/O interface for output.
    """

    def __init__(self, orchestrator: Any, io: CLIIOProtocol) -> None:
        """Initialize session persistence manager.

        Args:
            orchestrator: The AgentOrchestrator instance that provides session
                operations (clear_session, session_manager.session_file) and
                working_memory.get_summary() for displaying statistics.
            io: I/O interface for output.

        State Changes:
            Sets self.orchestrator to the provided orchestrator instance.
            Sets self.io to the provided I/O interface.
        """
        self.orchestrator = orchestrator
        self.io = io

    def manage_session(self, args: str = "") -> None:
        """Manage session persistence with subcommands.

        Provides a CLI interface for session management including displaying
        session statistics and clearing session state.

        Args:
            args: Command argument string. Valid values are:
                - "": Show current session info and memory statistics
                - "clear": Delete saved session file

        Side Effects:
            - When args is "": Reads session file and memory stats, displays
              formatted output via self.io (no state changes)
            - When args is "clear": Calls orchestrator.clear_session() which
              deletes .session.json from disk

        Example:
            >>> persistence.manage_session()  # Show info
            >>> persistence.manage_session("clear")  # Clear session
        """
        # Validate subcommand
        validation = validate_subcommand("session", args)
        if not validation.is_valid:
            self.io.secho(validation.error, fg=self.io.theme.error)
            self.io.echo("Usage: /session [clear]")
            self.io.echo("  (no args)  - Show session info")
            self.io.echo("  clear      - Delete saved session file")
            return

        if validation.subcommand == "":
            # Show session info
            session_file = self.orchestrator.session_manager.session_file
            self.io.secho("\nSession Management:", fg=self.io.theme.accent, bold=True)
            self.io.secho("-" * 50, fg=self.io.theme.accent)
            self.io.echo(f"Session File: {session_file}")
            self.io.echo(f"Session Exists: {'Yes' if session_file.exists() else 'No'}")

            if session_file.exists():
                try:
                    with open(session_file, 'r') as f:
                        data = json.load(f)
                    self.io.echo(f"Last Saved: {data.get('saved_at', 'unknown')}")
                    self.io.echo(f"Files Cached: {len(data.get('file_reads', {}))}")
                    self.io.echo(f"Searches: {len(data.get('search_results', []))}")
                    self.io.echo(f"Git Ops: {len(data.get('git_operations', []))}")
                    self.io.echo(f"Discoveries: {len(data.get('discoveries', []))}")
                except Exception as e:
                    self.io.echo(f"Error reading session: {e}")

            # Show current memory stats
            mem = self.orchestrator.working_memory.get_summary()
            self.io.secho("\nCurrent Session Memory:", bold=True)
            self.io.echo(f"  Files in memory: {mem['files_cached']}")
            self.io.echo(f"  Searches: {mem['recent_searches']}")
            self.io.echo(f"  Git ops: {mem['git_operations']}")
            self.io.echo(f"  Discoveries: {mem['discoveries']}")

        elif validation.subcommand == "clear":
            self.orchestrator.clear_session()
            self.io.secho("Saved session cleared.", fg=self.io.theme.success)
