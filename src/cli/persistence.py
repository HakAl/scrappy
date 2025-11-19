"""
Session persistence functionality for the CLI.
Handles saving, loading, and managing session state.
"""

import json
from typing import Any, Dict, List, Optional

from .io_interface import CLIIOProtocol
from .rich_output import RichIO
from .utils.session_utils import display_session_load_error
from .validators import validate_subcommand


class SessionPersistence:
    """Manages session persistence operations.

    This class provides functionality for saving and loading CLI session state
    to disk, allowing users to resume work across sessions. Session data includes
    file caches, search results, git operations, discoveries, and conversation
    history.

    The session file is stored at .llm_team_session.json in the project directory.

    Attributes:
        orchestrator: The AgentOrchestrator instance that provides session
            storage operations.
    """

    def __init__(self, orchestrator: Any) -> None:
        """Initialize session persistence manager.

        Args:
            orchestrator: The AgentOrchestrator instance that provides session
                operations (save_session, load_session, clear_session,
                get_working_memory_summary) and context for project path.

        State Changes:
            Sets self.orchestrator to the provided orchestrator instance.
        """
        self.orchestrator = orchestrator

    def manage_session(
        self,
        args: str = "",
        conversation_history: Optional[List[Dict[str, str]]] = None,
        auto_save: bool = True,
        io: Optional[CLIIOProtocol] = None
    ) -> Dict[str, Any]:
        """Manage session persistence with subcommands.

        Provides a CLI interface for session management including saving,
        loading, clearing session state, and toggling auto-save behavior.

        Args:
            args: Command argument string. Valid values are:
                - "": Show current session info and memory statistics
                - "save": Save current session to disk
                - "load": Load saved session from disk
                - "clear": Delete saved session file
                - "toggle": Toggle auto-save on/off

            conversation_history: Current conversation history list to save/restore.
                Each entry is a dict with 'role' and 'content' keys.

            auto_save: Current auto-save setting. When True, session is saved
                automatically on /quit.

            io: I/O interface for output. Defaults to ClickIO if not provided.

        Returns:
            Dict with the following keys:
                - conversation_history: Updated conversation history (same as input,
                  or restored list if "load" was called)
                - auto_save: Updated auto-save setting (same as input, or toggled
                  value if "toggle" was called)

        Side Effects:
            - When args is "": Reads session file and memory stats, displays
              formatted output (no state changes)
            - When args is "save": Calls orchestrator.save_session() which writes
              session data to .llm_team_session.json including file caches,
              search results, git operations, discoveries, and conversation history
            - When args is "load": Calls orchestrator.load_session() which reads
              .llm_team_session.json and restores working memory state in the
              orchestrator. Updates returned conversation_history.
            - When args is "clear": Calls orchestrator.clear_session() which
              deletes .llm_team_session.json from disk
            - When args is "toggle": Returns opposite auto_save value (no disk I/O)

        Example:
            >>> result = persistence.manage_session()  # Show info
            >>> result = persistence.manage_session("save", conversation_history)
            >>> result = persistence.manage_session("load")
            >>> history = result['conversation_history']  # Restored history
        """
        if io is None:
            io = RichIO()

        result = {
            'conversation_history': conversation_history,
            'auto_save': auto_save
        }

        # Validate subcommand
        validation = validate_subcommand("session", args)
        if not validation.is_valid:
            io.secho(validation.error, fg="red")
            io.echo("Usage: /session [save|load|clear|toggle]")
            io.echo("  (no args)  - Show session info")
            io.echo("  save       - Save current session to disk")
            io.echo("  load       - Load saved session")
            io.echo("  clear      - Delete saved session file")
            io.echo("  toggle     - Toggle auto-save on/off")
            io.echo(f"\nAuto-save: {io.style('ON' if auto_save else 'OFF', fg='green' if auto_save else 'yellow')}")
            return result

        if validation.subcommand == "":
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
            mem = self.orchestrator.working_memory.get_summary()
            io.secho("\nCurrent Session Memory:", bold=True)
            io.echo(f"  Files in memory: {mem['files_cached']}")
            io.echo(f"  Searches: {mem['recent_searches']}")
            io.echo(f"  Git ops: {mem['git_operations']}")
            io.echo(f"  Discoveries: {mem['discoveries']}")
            io.echo(f"  Conversation: {len(conversation_history or [])} messages")
            io.echo(f"  Auto-save: {io.style('ON' if auto_save else 'OFF', fg='green' if auto_save else 'yellow')}")

        elif validation.subcommand == "save":
            try:
                session_file = self.orchestrator.save_session(conversation_history or [])
                io.secho(f"Session saved to: {session_file}", fg="green")
                io.echo(f"  Conversation: {len(conversation_history or [])} messages")
            except Exception as e:
                io.secho(f"Error saving session: {e}", fg="red")

        elif validation.subcommand == "load":
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
            else:
                display_session_load_error(io, load_result)

        elif validation.subcommand == "clear":
            self.orchestrator.clear_session()
            io.secho("Saved session cleared.", fg="green")

        elif validation.subcommand == "toggle":
            result['auto_save'] = not auto_save
            status = io.style("ON", fg="green") if result['auto_save'] else io.style("OFF", fg="yellow")
            io.echo(f"Auto-save on exit: {status}")
            if result['auto_save']:
                io.echo("Session will be saved automatically on /quit")
            else:
                io.echo("Session will NOT be saved on /quit (use '/session save' manually)")

        return result
