"""
Graph node implementations.

Each node is a function that takes AgentState and returns updated AgentState.

Nodes:
- think.py: LLM reasoning step (decide what to do next)
- execute.py: Tool execution (run tools from LLM response)
- verify.py: Linting/testing verification (ruff, mypy)
- confirm.py: Human-in-the-loop confirmation (dangerous operations)
- error.py: Error handling and recovery (format errors for LLM retry)
"""

from .think import (
    think_node,
    think_node_streaming,
    build_system_prompt,
    sanitize_context,
    LLMServiceProtocol,
    StreamingLLMServiceProtocol,
)

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
    "think_node",
    "think_node_streaming",
    "build_system_prompt",
    "sanitize_context",
    "LLMServiceProtocol",
    "StreamingLLMServiceProtocol",
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
