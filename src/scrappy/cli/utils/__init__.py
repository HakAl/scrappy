"""
CLI utility modules.

Shared utilities for the CLI package to eliminate duplication across
command handlers and core CLI functionality.

This module re-exports session display utilities for convenient access:

Session Display Functions:
    display_session_restored: Show session restoration success with stats.
    display_session_load_error: Show session load failure or no-session message.
    display_session_saved: Show session save confirmation with message count.
    display_session_save_error: Show session save failure warning.
    display_previous_session_detected: Show info about detected previous session.
    display_last_conversation_messages: Show recent conversation messages.
    display_session_not_saved_warning: Warn that session was not saved.

Other utilities are available in submodules:
    - error_handler: Consistent error handling with severity levels
    - error_utils: Command error handling with retry/recovery
    - cli_factory: Factory functions for CLI instance creation

Example:
    from scrappy.cli.utils import display_session_saved

    display_session_saved(io, "/path/to/session.json", 10)
"""

from scrappy.cli.utils.session_utils import (
    display_session_restored,
    display_session_load_error,
    display_session_saved,
    display_session_save_error,
    display_previous_session_detected,
    display_last_conversation_messages,
    display_session_not_saved_warning
)

__all__ = [
    'display_session_restored',
    'display_session_load_error',
    'display_session_saved',
    'display_session_save_error',
    'display_previous_session_detected',
    'display_last_conversation_messages',
    'display_session_not_saved_warning'
]
