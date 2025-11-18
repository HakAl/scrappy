"""
Session persistence functionality for the CLI.
Handles saving, loading, and managing session state.
"""

import json
from typing import Any, Dict, List, Optional

try:
    from .io_interface import CLIIOProtocol, ClickIO
    from .utils.session_utils import display_session_load_error
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cli.io_interface import CLIIOProtocol, ClickIO  # type: ignore[no-redef]
    from cli.utils.session_utils import display_session_load_error  # type: ignore[no-redef]


class SessionPersistence:
    """Manages session persistence operations."""

    def __init__(self, orchestrator: Any) -> None:
        """Initialize session persistence manager.

        Args:
            orchestrator: The AgentOrchestrator instance
        """
        self.orchestrator = orchestrator

    def manage_session(
        self,
        args: str = "",
        conversation_history: Optional[List[Dict[str, str]]] = None,
        auto_save: bool = True,
        io: Optional[CLIIOProtocol] = None
    ) -> Dict[str, Any]:
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
            else:
                display_session_load_error(io, load_result)

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
