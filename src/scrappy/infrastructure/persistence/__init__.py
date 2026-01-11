"""
Infrastructure persistence layer.

Provides abstractions for persisting structured data with error handling,
including conversation history storage.

Components:
- PersistenceProtocol: Generic persistence abstraction
- JSONPersistence: JSON file persistence implementation
- ConversationStore: SQLite-backed conversation history storage
"""

from .protocols import PersistenceProtocol, AsyncPersistenceProtocol
from .json_persistence import JSONPersistence
from .conversation_store import (
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
    # Generic persistence
    'PersistenceProtocol',
    'AsyncPersistenceProtocol',
    'JSONPersistence',
    # Conversation persistence
    'ConversationStore',
    'ConversationStoreProtocol',
    'check_session_staleness',
    'format_stale_separator',
    'get_or_create_project_id',
    'get_stale_context_message',
    'strip_ansi',
    'STALE_THRESHOLD',
]
