"""
Session display utilities.

Shared utilities for displaying session-related information across CLI modules.
Eliminates duplication in session restoration, save, and detection display code.
"""

from typing import Any, Dict, List, Optional


def display_session_restored(io: Any, result: Dict[str, Any]) -> Optional[List[Dict[str, str]]]:
    """
    Display session restoration success information.

    Args:
        io: IO interface for output (CLIIOProtocol or click)
        result: Session load result with status, counts, and conversation

    Returns:
        The conversation history list if present, else None
    """
    saved_at = result.get('saved_at', 'unknown')
    io.secho(f"\nResumed session from {saved_at}", fg="green", bold=True)
    io.echo(f"  Files restored: {result.get('files_restored', 0)}")
    io.echo(f"  Searches restored: {result.get('searches_restored', 0)}")
    io.echo(f"  Git ops restored: {result.get('git_ops_restored', 0)}")
    io.echo(f"  Discoveries restored: {result.get('discoveries_restored', 0)}")
    io.echo(f"  Task history: {result.get('tasks_restored', 0)} entries")

    conversation = result.get('conversation_history', [])
    if conversation:
        io.echo(f"  Conversation: {len(conversation)} messages restored")
        display_last_conversation_messages(io, conversation)

    return conversation if conversation else None


def display_session_load_error(io: Any, result: Dict[str, Any]) -> None:
    """
    Display session load error or no-session message.

    Args:
        io: IO interface for output
        result: Session load result with status and optional message
    """
    status = result.get('status', 'error')

    if status == 'no_session':
        io.secho("No previous session found. Starting fresh.", fg="yellow")
    else:
        message = result.get('message', 'unknown')
        io.secho(f"Error loading session: {message}", fg="red")


def display_session_saved(
    io: Any,
    session_file: str,
    conversation_count: int,
    with_help: bool = False
) -> None:
    """
    Display session save success information.

    Args:
        io: IO interface for output
        session_file: Path where session was saved
        conversation_count: Number of conversation messages saved
        with_help: Whether to show resume help text
    """
    io.secho(f"\nSession saved to: {session_file}", fg="green")
    io.echo(f"  Conversation: {conversation_count} messages")

    if with_help:
        io.echo("Use 'llm-team --resume' to continue later.")


def display_session_save_error(io: Any, error: Exception) -> None:
    """
    Display session save error warning.

    Args:
        io: IO interface for output
        error: The exception that occurred
    """
    io.secho(f"Warning: Could not save session: {error}", fg="yellow")


def display_previous_session_detected(io: Any, session_info: Dict[str, Any]) -> None:
    """
    Display information about a detected previous session.

    Args:
        io: IO interface for output
        session_info: Session metadata including counts and timestamps
    """
    io.secho("\nPrevious session detected:", fg="yellow", bold=True)
    io.echo(f"  Saved: {session_info.get('saved_at', 'unknown')}")
    io.echo(f"  Files cached: {session_info.get('file_count', 0)}")
    io.echo(f"  Searches: {session_info.get('search_count', 0)}")
    io.echo(f"  Discoveries: {session_info.get('discovery_count', 0)}")
    io.echo(f"  Tasks: {session_info.get('task_count', 0)}")

    if session_info.get('has_conversation', False):
        io.echo("  Has conversation history: Yes")


def display_last_conversation_messages(
    io: Any,
    conversation: List[Dict[str, str]],
    max_messages: int = 4,
    truncate_at: int = 100
) -> None:
    """
    Display the last few messages from a conversation.

    Args:
        io: IO interface for output
        conversation: List of message dicts with 'role' and 'content'
        max_messages: Maximum number of messages to display
        truncate_at: Maximum characters per message before truncation
    """
    if not conversation:
        return

    io.secho("\nLast conversation:", fg="cyan")

    # Get last N messages
    messages_to_show = conversation[-max_messages:] if len(conversation) > max_messages else conversation

    for msg in messages_to_show:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')[:truncate_at]

        if len(msg.get('content', '')) > truncate_at:
            content += "..."

        if role == 'user':
            io.echo(f"  You: {content}")
        else:
            io.echo(f"  Assistant: {content}")


def display_session_not_saved_warning(io: Any) -> None:
    """
    Display warning that session was not saved due to auto-save being disabled.

    Args:
        io: IO interface for output
    """
    io.secho("\nSession not saved (auto-save disabled).", fg="yellow")
    io.echo("Use '/session save' to manually save before quitting.")
