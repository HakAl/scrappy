"""
Error node for LangGraph agent.

Handles tool failures and routes back to think with error context.
This node is reached when last_error is set (via routing in edges.py).

Features:
- Formats error context for the LLM to understand and retry
- Uses recovery_action and error_category from state for smarter decisions
- Clears last_error after processing to avoid looping on same error
- Preserves last_error when terminating (MAX_RETRIES reached) for diagnostics
- Optionally escalates to quality tier on repeated errors
- Langfuse tracing integration
"""

from typing import Literal, Optional

from scrappy.graph.edges import MAX_RETRIES
from scrappy.graph.state import AgentState
from scrappy.infrastructure.exceptions import RecoveryAction
from scrappy.infrastructure.error_recovery import (
    RetryConfig,
    DEFAULT_RETRY_CONFIG,
    AGGRESSIVE_RETRY_CONFIG,
    CONSERVATIVE_RETRY_CONFIG,
)
from scrappy.infrastructure.logging import get_logger

logger = get_logger(__name__)

# Threshold for escalating to quality tier on repeated errors
ERROR_ESCALATION_THRESHOLD = 2

# Map error categories to appropriate retry configs
# Rate limits need longer backoff, network errors can retry quickly
CATEGORY_RETRY_CONFIGS: dict[str, RetryConfig] = {
    "rate_limit": CONSERVATIVE_RETRY_CONFIG,  # Longer delays for rate limits
    "network": AGGRESSIVE_RETRY_CONFIG,  # Quick retries for transient network issues
    "api": DEFAULT_RETRY_CONFIG,  # Standard retry for API errors
    "parse": AGGRESSIVE_RETRY_CONFIG,  # Quick retry for parsing (may be transient)
    "system": CONSERVATIVE_RETRY_CONFIG,  # Careful with system errors
}


def get_retry_config_for_category(category: Optional[str]) -> RetryConfig:
    """Get appropriate retry config based on error category."""
    if category and category in CATEGORY_RETRY_CONFIGS:
        return CATEGORY_RETRY_CONFIGS[category]
    return DEFAULT_RETRY_CONFIG


def format_error_context(
    error: str,
    error_count: int,
    error_category: Optional[str] = None,
    recovery_action: Optional[str] = None,
    retry_config: Optional[RetryConfig] = None,
) -> str:
    """
    Format error context message for the LLM.

    Provides clear instructions to help the LLM understand and recover.
    Uses error_category and recovery_action metadata for more specific guidance.
    Includes backoff timing information based on retry_config.

    Args:
        error: The error message
        error_count: Number of consecutive errors
        error_category: Category of error (network, rate_limit, api, etc.)
        recovery_action: Recommended recovery action
        retry_config: Retry configuration for backoff calculation

    Returns:
        Formatted error context string
    """
    context = f"""[Error Recovery]
The previous action failed with the following error:

{error}
"""

    # Add category-specific guidance
    if error_category:
        category_guidance = {
            "network": "This appears to be a network issue. The operation may succeed if retried.",
            "rate_limit": "Rate limit was hit. Consider waiting or using a different approach.",
            "api": "The API returned an error. Check the request parameters.",
            "authentication": "Authentication failed. API credentials may be invalid.",
            "parse": "Response parsing failed. The API may have returned unexpected data.",
            "validation": "Input validation failed. Check the provided parameters.",
            "file": "File operation failed. Check paths and permissions.",
            "system": "A system error occurred. This may require investigation.",
        }
        if error_category in category_guidance:
            context += f"\nCategory: {error_category}\n{category_guidance[error_category]}\n"

    # Add backoff timing information if retry is recommended
    if retry_config and recovery_action in (RecoveryAction.RETRY.value, RecoveryAction.FALLBACK.value):
        # Calculate suggested backoff based on error count (0-indexed attempt)
        attempt = max(0, error_count - 1)
        suggested_delay = retry_config.calculate_delay(attempt)
        remaining_retries = max(0, retry_config.max_retries - error_count)

        context += f"""
Retry Status:
- Attempt: {error_count} of {retry_config.max_retries + 1}
- Suggested backoff: {suggested_delay:.1f}s
- Remaining retries: {remaining_retries}
"""

    # Add recovery-specific guidance
    if recovery_action:
        action_guidance = {
            RecoveryAction.RETRY.value: "Suggestion: Retry the same operation - it may succeed.",
            RecoveryAction.FALLBACK.value: "Suggestion: Try an alternative approach or provider.",
            RecoveryAction.SKIP.value: "Suggestion: Skip this step and continue with the next task.",
            RecoveryAction.ASK_USER.value: "Suggestion: Ask the user for clarification or input.",
            RecoveryAction.ABORT.value: "This error cannot be recovered automatically.",
        }
        if recovery_action in action_guidance:
            context += f"\n{action_guidance[recovery_action]}\n"

    context += """
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


# Tier escalation path: fast -> chat -> instruct
TIER_ESCALATION = {
    "fast": "chat",
    "chat": "instruct",
}


def should_escalate_tier(error_count: int, current_tier: Literal["fast", "chat", "instruct"]) -> bool:
    """
    Determine if we should escalate to next tier.

    Escalates to next tier after repeated errors, as more capable
    models may handle complex error recovery better.

    Escalation path: fast -> chat -> instruct

    Args:
        error_count: Number of consecutive errors
        current_tier: Current model tier

    Returns:
        True if should escalate to next tier
    """
    return (
        current_tier in TIER_ESCALATION
        and error_count >= ERROR_ESCALATION_THRESHOLD
    )


def get_next_tier(current_tier: Literal["fast", "chat", "instruct"]) -> Literal["fast", "chat", "instruct"]:
    """Get the next tier in escalation path, or same tier if already at top."""
    return TIER_ESCALATION.get(current_tier, current_tier)  # type: ignore[return-value]


def error_node(state: AgentState) -> AgentState:
    """
    Error node - handles tool failures and prepares context for retry.

    This node is reached when last_error is set (via routing in edges.py).
    It formats the error for the LLM and clears last_error so the graph
    routes back to think for a retry attempt.

    Behavior:
    - Creates a system message explaining the error with category/recovery guidance
    - Uses recovery_action to determine if retry is appropriate
    - Clears last_error, recovery_action, error_category after processing
    - Optionally escalates tier on repeated errors (fast -> chat -> instruct)

    Args:
        state: Current agent state with last_error set

    Returns:
        Updated AgentState with error context in messages and error fields cleared
    """
    error = state.last_error

    if error is None:
        # Defensive: should not happen based on routing, but handle gracefully
        logger.warning("error_node called with no last_error set")
        return state

    logger.info(
        "Processing error (count=%d, category=%s, action=%s): %s",
        state.error_count,
        state.error_category or "unknown",
        state.recovery_action or "unknown",
        error[:100] + "..." if len(error) > 100 else error,
    )

    # Check if recovery_action indicates we should not retry
    # ABORT means the error is non-recoverable - mark as done
    if state.recovery_action == RecoveryAction.ABORT.value:
        logger.warning(
            "Error marked as non-recoverable (ABORT). Stopping graph."
        )
        return state.model_copy(
            update={
                "done": True,
                # Preserve error info for diagnostics
            }
        )

    # Get appropriate retry config based on error category
    retry_config = get_retry_config_for_category(state.error_category)

    # Format error context message with category, recovery guidance, and backoff info
    error_context = format_error_context(
        error,
        state.error_count,
        error_category=state.error_category,
        recovery_action=state.recovery_action,
        retry_config=retry_config,
    )

    # Append error context to messages
    new_messages = list(state.messages) + [{
        "role": "system",
        "content": error_context,
    }]

    # Determine if we should escalate tier
    # Don't escalate if recovery_action suggests fallback is already happening
    new_tier = state.current_tier
    if state.recovery_action != RecoveryAction.FALLBACK.value:
        if should_escalate_tier(state.error_count, state.current_tier):
            new_tier = get_next_tier(state.current_tier)
            logger.info(
                "Escalating from %s to %s tier after %d consecutive errors",
                state.current_tier,
                new_tier,
                state.error_count,
            )

    # Clear error fields so routing goes back to think
    # BUT preserve them if we've hit max retries (about to terminate) for diagnostics
    # Use both global MAX_RETRIES and category-specific config
    max_retries_for_category = retry_config.max_retries
    should_preserve_error = state.error_count >= min(MAX_RETRIES, max_retries_for_category)

    # Log retry exhaustion if we're about to terminate
    if should_preserve_error:
        logger.warning(
            "Retry exhausted for %s error (count=%d, max=%d)",
            state.error_category or "unknown",
            state.error_count,
            max_retries_for_category,
        )

    return state.model_copy(
        update={
            "messages": new_messages,
            "last_error": error if should_preserve_error else None,
            "recovery_action": state.recovery_action if should_preserve_error else None,
            "error_category": state.error_category if should_preserve_error else None,
            "current_tier": new_tier,
        }
    )
