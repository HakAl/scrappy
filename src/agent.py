"""
Code Agent with human-in-the-loop safety.

This module re-exports from the agent package for backward compatibility.
The actual implementation has been modularized into:
- agent/core.py - main CodeAgent class
- agent/types.py - dataclasses
- agent/audit.py - audit logging
- agent/checkpoint.py - git operations
"""

# Re-export all components from the new package structure
from .agent import (
    # Core agent
    CodeAgent,
    # Types
    AgentThought,
    AgentAction,
    ActionResult,
    EvaluationResult,
    ConversationState,
    # Audit
    AuditLogger,
    # Checkpoint
    create_git_checkpoint,
    rollback_to_checkpoint,
)

__all__ = [
    'CodeAgent',
    'AgentThought',
    'AgentAction',
    'ActionResult',
    'EvaluationResult',
    'ConversationState',
    'AuditLogger',
    'create_git_checkpoint',
    'rollback_to_checkpoint',
]
