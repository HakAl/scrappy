"""
Persistence layer for scrappy.

This package provides storage abstractions for conversation history,
agent state, and other persistent data.

Components:
- ConversationStore: SQLite-backed conversation persistence
- ConversationStoreProtocol: Protocol for conversation storage implementations
"""

from scrappy.persistence.conversation_store import (
    ConversationStore,
    ConversationStoreProtocol,
    check_session_staleness,
    format_stale_separator,
    get_or_create_project_id,
    get_stale_context_message,
    strip_ansi,
    STALE_THRESHOLD,
)

__all__ = [
    "ConversationStore",
    "ConversationStoreProtocol",
    "check_session_staleness",
    "format_stale_separator",
    "get_or_create_project_id",
    "get_stale_context_message",
    "strip_ansi",
    "STALE_THRESHOLD",
]
