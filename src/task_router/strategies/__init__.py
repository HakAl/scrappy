"""
Execution strategies for different task types.

Each strategy is now in its own module for better organization and maintainability.
"""

# Base classes and types
from .base import (
    ExecutionResult,
    ExecutionStrategy,
    ContextLike,
    ProviderRegistryLike,
    LLMResponseLike,
    OrchestratorLike,
)

# Strategy implementations
from .direct_executor import DirectExecutor
from .conversation_executor import ConversationExecutor
from .research_executor import ResearchExecutor
from .agent_executor import AgentExecutor

__all__ = [
    # Base classes
    'ExecutionResult',
    'ExecutionStrategy',
    'ContextLike',
    'ProviderRegistryLike',
    'LLMResponseLike',
    'OrchestratorLike',
    # Executors
    'DirectExecutor',
    'ConversationExecutor',
    'ResearchExecutor',
    'AgentExecutor',
]
