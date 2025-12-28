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
from .models import (
    Step,
    StepStatus,
    Plan,
    PlanExecutionState,
    VerificationResult,
    UnitTestResult,
    LintResult,
    TypecheckResult,
    VerificationPolicy,
    ApprovalPolicy,
)
from .exceptions import (
    AgentLoopError,
    PlanCreationError,
    PlanRejectedError,
    PlanRevisionLimitError,
    VerificationError,
    MaxRetriesExceededError,
    StepExecutionError,
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
    PlannerProtocol,
    VerifierProtocol,
)
from .verifier import Verifier
from .planner import Planner
from .agent_loop import AgentLoop
from ..infrastructure.protocols import FileSystemProtocol
from ..infrastructure.file_system import RealFileSystem, InMemoryFileSystem

__all__ = [
    # Core agent
    'CodeAgent',
    'AgentLoop',
    # Types
    'AgentThought',
    'AgentAction',
    'ActionResult',
    'EvaluationResult',
    'ConversationState',
    # Models (Phase 0.5)
    'Step',
    'StepStatus',
    'Plan',
    'PlanExecutionState',
    'VerificationResult',
    'UnitTestResult',
    'LintResult',
    'TypecheckResult',
    'VerificationPolicy',
    'ApprovalPolicy',
    # Exceptions (Phase 0.5)
    'AgentLoopError',
    'PlanCreationError',
    'PlanRejectedError',
    'PlanRevisionLimitError',
    'VerificationError',
    'MaxRetriesExceededError',
    'StepExecutionError',
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
    'PlannerProtocol',
    'VerifierProtocol',
    'FileSystemProtocol',
    # File system implementations
    'RealFileSystem',
    'InMemoryFileSystem',
    # Verifier implementation
    'Verifier',
    # Planner implementation
    'Planner',
]
