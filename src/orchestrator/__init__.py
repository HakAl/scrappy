"""
LLM Agent Orchestrator Package

Provides coordination layer for multi-provider LLM agent teams.

Architecture:
    Claude Code (complex reasoning) <-- Human/Orchestrator
           |
           v
    Orchestrator (this package)
           |
    +------+------+------+
    |      |      |      |
    v      v      v      v
   Groq  Cohere  [Future providers...]
  (fast) (embed) (OpenRouter, HuggingFace, etc.)

The orchestrator:
1. Maintains a registry of available providers
2. Routes tasks to appropriate providers based on task type
3. Tracks usage and rate limits across providers
4. Provides fallback strategies when limits are hit
"""

from .core import AgentOrchestrator, create_orchestrator
from .cache import ResponseCache
from .rate_limiter import RateLimitTracker
from .memory import WorkingMemory
from .session import SessionManager
from .task_executor import TaskExecutor
from .provider_selector import ProviderSelector
from .protocols import Orchestrator

__all__ = [
    'AgentOrchestrator',
    'create_orchestrator',
    'ResponseCache',
    'RateLimitTracker',
    'WorkingMemory',
    'SessionManager',
    'TaskExecutor',
    'ProviderSelector',
    'Orchestrator',
]
