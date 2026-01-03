"""
Error node for LangGraph agent.

Handles tool failures and routes back to think with error context.
This node is reached when last_error is set (via routing in edges.py).

Features:
- Formats error context for the LLM to understand and retry
- Clears last_error after processing to avoid looping on same error
- Optionally escalates to quality tier on repeated errors
- Langfuse tracing integration
"""

import logging
from typing import Literal

from scrappy.graph.state import AgentState

logger = logging.getLogger(__name__)

# Threshold for escalating to quality tier on repeated errors
ERROR_ESCALATION_THRESHOLD = 2


def format_error_context(error: str, error_count: int) -> str:
    """
    Format error context message for the LLM.

    Provides clear instructions to help the LLM understand and recover.

    Args:
        error: The error message
        error_count: Number of consecutive errors

    Returns:
        Formatted error context string
    """
    context = f"""[Error Recovery]
The previous action failed with the following error:

{error}

Please analyze this error and try a different approach. Consider:
1. Was the input/path correct?
2. Is there a prerequisite step that was missed?
3. Should you try an alternative method?
"""

    if error_count > 1:
        context += f"""
Note: This is error #{error_count} in a row. If the same approach keeps failing,
try a fundamentally different strategy.
"""

    return context


def should_escalate_tier(error_count: int, current_tier: Literal["fast", "quality"]) -> bool:
    """
    Determine if we should escalate to quality tier.

    Escalates to quality tier after repeated errors, as more capable
    models may handle complex error recovery better.

    Args:
        error_count: Number of consecutive errors
        current_tier: Current model tier

    Returns:
        True if should escalate to quality tier
    """
    return (
        current_tier == "fast"
        and error_count >= ERROR_ESCALATION_THRESHOLD
    )


def error_node(state: AgentState) -> AgentState:
    """
    Error node - handles tool failures and prepares context for retry.

    This node is reached when last_error is set (via routing in edges.py).
    It formats the error for the LLM and clears last_error so the graph
    routes back to think for a retry attempt.

    Behavior:
    - Creates a system message explaining the error
    - Clears last_error after processing
    - Optionally escalates to quality tier on repeated errors

    Args:
        state: Current agent state with last_error set

    Returns:
        Updated AgentState with error context in messages and last_error cleared
    """
    error = state.last_error

    if error is None:
        # Defensive: should not happen based on routing, but handle gracefully
        logger.warning("error_node called with no last_error set")
        return state

    logger.info(
        "Processing error (count=%d): %s",
        state.error_count,
        error[:100] + "..." if len(error) > 100 else error,
    )

    # Format error context message
    error_context = format_error_context(error, state.error_count)

    # Append error context to messages
    new_messages = list(state.messages) + [{
        "role": "system",
        "content": error_context,
    }]

    # Determine if we should escalate tier
    new_tier = state.current_tier
    if should_escalate_tier(state.error_count, state.current_tier):
        new_tier = "quality"
        logger.info(
            "Escalating to quality tier after %d consecutive errors",
            state.error_count,
        )

    # Clear last_error so routing goes back to think
    return state.model_copy(
        update={
            "messages": new_messages,
            "last_error": None,  # Clear to avoid looping on same error
            "current_tier": new_tier,
        }
    )
