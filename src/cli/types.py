"""
Type definitions for CLI module.

Centralizes type aliases to avoid explicit Any usage while maintaining
flexibility for different orchestrator implementations. These types provide
consistent typing across all CLI components.

Usage:
    from src.cli.types import OrchestratorType, SessionResult, ConversationHistory

    def process_session(orchestrator: OrchestratorType) -> SessionResult:
        ...
"""

from typing import Dict, List
from ..orchestrator.protocols import Orchestrator

#: Type alias for the Orchestrator Protocol.
#:
#: Provides a convenient alias for the Orchestrator protocol type.
#: This allows handlers to be typed correctly with a shorter name.
#:
#: Example:
#:     from ..types import OrchestratorType
#:
#:     def __init__(self, orchestrator: OrchestratorType) -> None:
#:         self.orchestrator = orchestrator
OrchestratorType = Orchestrator

#: Type alias for session operation result dictionaries.
#:
#: Returned by session load/save operations. Common keys include:
#: - 'status': Operation result ('loaded', 'saved', 'error', 'no_session')
#: - 'saved_at': Timestamp string when session was saved
#: - 'files_restored': Count of cached files restored
#: - 'searches_restored': Count of search results restored
#: - 'message': Error message if status is 'error'
#:
#: Example:
#:     result: SessionResult = orchestrator.load_session()
#:     if result['status'] == 'loaded':
#:         print(f"Restored {result.get('files_restored', 0)} files")
SessionResult = Dict[str, object]

#: Type alias for conversation history.
#:
#: A list of message dictionaries representing the conversation between
#: the user and assistant. Each message has:
#: - 'role': Either 'user' or 'assistant'
#: - 'content': The message text
#:
#: Example:
#:     history: ConversationHistory = [
#:         {'role': 'user', 'content': 'Hello'},
#:         {'role': 'assistant', 'content': 'Hi! How can I help?'}
#:     ]
ConversationHistory = List[Dict[str, str]]
