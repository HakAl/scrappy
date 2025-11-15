"""
LLM Agent Orchestrator

DEPRECATED: This module has been refactored into the orchestrator package.
This file is kept for backward compatibility.

New imports should use:
    from orchestrator import AgentOrchestrator, ResponseCache, RateLimitTracker
    # or
    from orchestrator.core import AgentOrchestrator

Architecture:
    Claude Code (complex reasoning) <-- Human/Orchestrator
           |
           v
    Orchestrator (orchestrator package)
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

# Re-export from the new package structure for backward compatibility
try:
    from .orchestrator import (
        AgentOrchestrator,
        create_orchestrator,
        ResponseCache,
        RateLimitTracker,
        WorkingMemory,
        SessionManager,
        TaskExecutor,
        ProviderSelector,
    )
except ImportError:
    # Allow running as script or if package not fully set up
    from orchestrator import (
        AgentOrchestrator,
        create_orchestrator,
        ResponseCache,
        RateLimitTracker,
        WorkingMemory,
        SessionManager,
        TaskExecutor,
        ProviderSelector,
    )

__all__ = [
    'AgentOrchestrator',
    'create_orchestrator',
    'ResponseCache',
    'RateLimitTracker',
    'WorkingMemory',
    'SessionManager',
    'TaskExecutor',
    'ProviderSelector',
]
