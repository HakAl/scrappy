"""
Type definitions for CLI module.

Centralizes type aliases to avoid explicit Any usage while maintaining
flexibility for different orchestrator implementations.
"""

from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from ..orchestrator import AgentOrchestrator

# Type alias for orchestrator - used in TYPE_CHECKING blocks
OrchestratorType = "AgentOrchestrator"

# Type alias for session result dictionaries
SessionResult = Dict[str, object]

# Type alias for conversation history
ConversationHistory = List[Dict[str, str]]
