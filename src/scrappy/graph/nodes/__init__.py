"""
Graph node implementations.

Each node is a function that takes AgentState and returns updated AgentState.

Nodes:
- think.py: LLM reasoning step (decide what to do next)
- execute.py: Tool execution (run tools from LLM response)
- verify.py: Linting/testing verification (ruff, mypy)
- confirm.py: Human-in-the-loop confirmation (dangerous operations)
- error.py: Error handling and recovery (format errors for LLM retry)

Supporting classes:
- token_estimator.py: Token counting for context management
- context_manager.py: Context window management and trimming
- tool_call_processor.py: Tool call format conversion
"""

from .context_manager import ContextManager, ContextManagerProtocol
from .think import (
    think_node,
    think_node_streaming,
    build_system_prompt,
    sanitize_context,
)
from .think_delegator import (
    LiteLLMThinkDelegator,
    create_think_delegator,
)
from .think_error_handler import (
    DefaultThinkErrorHandler,
    ThinkErrorHandlerProtocol,
)
from .mock_think_delegator import (
    MockThinkDelegator,
    FailingThinkDelegator,
    SequenceThinkDelegator,
)
from .token_estimator import TokenEstimator, TokenEstimatorProtocol
from .tool_call_processor import ToolCallProcessor, ToolCallProcessorProtocol

# Node imports will be added as they're implemented
from .execute import execute_node
from .verify import verify_node
from .confirm import (
    confirm_node,
    create_pending_confirmation,
    should_abort_on_denial,
    format_confirmation_message,
    ABORT_ON_DENIAL_TYPES,
)
from .error import (
    error_node,
    format_error_context,
    should_escalate_tier,
    ERROR_ESCALATION_THRESHOLD,
)

__all__ = [
    # Think node
    "think_node",
    "think_node_streaming",
    "build_system_prompt",
    "sanitize_context",
    # Think delegator
    "LiteLLMThinkDelegator",
    "create_think_delegator",
    "DefaultThinkErrorHandler",
    "ThinkErrorHandlerProtocol",
    # Mock delegators for testing
    "MockThinkDelegator",
    "FailingThinkDelegator",
    "SequenceThinkDelegator",
    # Supporting classes
    "TokenEstimator",
    "TokenEstimatorProtocol",
    "ContextManager",
    "ContextManagerProtocol",
    "ToolCallProcessor",
    "ToolCallProcessorProtocol",
    # Other nodes
    "execute_node",
    "verify_node",
    "confirm_node",
    "create_pending_confirmation",
    "should_abort_on_denial",
    "format_confirmation_message",
    "ABORT_ON_DENIAL_TYPES",
    "error_node",
    "format_error_context",
    "should_escalate_tier",
    "ERROR_ESCALATION_THRESHOLD",
]
