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
from .response_parser import JSONResponseParser, ParseResult
from .protocols import (
    AuditLoggerProtocol,
    ResponseParserProtocol,
    PromptBuilderProtocol,
    ToolRegistryProtocol,
    ToolContextProtocol,
    CheckpointManagerProtocol,
    FileSystemProtocol,
    PlatformUtilsProtocol,
)
from ..infrastructure.file_system import RealFileSystem, InMemoryFileSystem
from .platform_adapter import RealPlatformUtils, MockPlatformUtils

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
    # Checkpoint
    'create_git_checkpoint',
    'rollback_to_checkpoint',
    # Protocols
    'AuditLoggerProtocol',
    'ResponseParserProtocol',
    'PromptBuilderProtocol',
    'ToolRegistryProtocol',
    'ToolContextProtocol',
    'CheckpointManagerProtocol',
    'FileSystemProtocol',
    'PlatformUtilsProtocol',
    # File system implementations
    'RealFileSystem',
    'InMemoryFileSystem',
    # Platform implementations
    'RealPlatformUtils',
    'MockPlatformUtils',
]
