"""
Code Agent package.

Provides a modular, AI-powered code agent with tool use and safety features.
"""

from .types import (
    AgentThought,
    AgentAction,
    ActionResult,
    EvaluationResult,
    ConversationState
)
from .audit import AuditLogger
from .checkpoint import create_git_checkpoint, rollback_to_checkpoint
from .core import CodeAgent

__all__ = [
    # Core agent
    'CodeAgent',
    # Types
    'AgentThought',
    'AgentAction',
    'ActionResult',
    'EvaluationResult',
    'ConversationState',
    # Audit
    'AuditLogger',
    # Checkpoint
    'create_git_checkpoint',
    'rollback_to_checkpoint',
]
