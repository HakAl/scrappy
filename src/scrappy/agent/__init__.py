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
from .cancellation import CancellationToken
from .checkpoint import create_git_checkpoint, rollback_to_checkpoint
from .core import CodeAgent
from .response_parser import JSONResponseParser, ParseResult
from .protocols import (
    AuditLoggerProtocol,
    ResponseParserProtocol,
    ToolRegistryProtocol,
    ToolContextProtocol,
    CheckpointManagerProtocol,
)
from ..infrastructure.protocols import FileSystemProtocol
from ..infrastructure.file_system import RealFileSystem, InMemoryFileSystem

__all__ = [
    # Core agent
    'CodeAgent',
    # Types
    'AgentThought',
    'AgentAction',
    'ActionResult',
    'EvaluationResult',
    'ConversationState',
    # Response parsing
    'JSONResponseParser',
    'ParseResult',
    # Audit
    'AuditLogger',
    # Cancellation
    'CancellationToken',
    # Checkpoint
    'create_git_checkpoint',
    'rollback_to_checkpoint',
    # Protocols
    'AuditLoggerProtocol',
    'ResponseParserProtocol',
    'ToolRegistryProtocol',
    'ToolContextProtocol',
    'CheckpointManagerProtocol',
    'FileSystemProtocol',
    # File system implementations
    'RealFileSystem',
    'InMemoryFileSystem',
]
