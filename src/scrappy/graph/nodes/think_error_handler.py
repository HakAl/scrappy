"""
Error handler for think node LLM calls.

Centralizes error handling logic that was previously inline in think.py.
Maps exceptions to ThinkResult with appropriate recovery guidance.

Single Responsibility: Convert exceptions to recovery-actionable results.
"""

import json
from typing import Optional, Protocol, runtime_checkable

from scrappy.graph.protocols import ThinkResult
from scrappy.graph.run_context import AgentRunContextProtocol
from scrappy.infrastructure.exceptions import (
    AllProvidersRateLimitedError,
    AuthenticationError,
    NetworkError,
    ProviderError,
    ProviderExecutionError,
    RateLimitError,
    RecoveryAction,
    TimeoutError as InfraTimeoutError,
)
from scrappy.infrastructure.logging import get_logger
from scrappy.orchestrator.litellm_service import NotConfiguredError, StreamCancelledError
from scrappy.orchestrator.model_selection import SelectionExhaustedError

logger = get_logger(__name__)


@runtime_checkable
class ThinkErrorHandlerProtocol(Protocol):
    """
    Protocol for handling LLM errors in think node.

    Implementations convert exceptions to ThinkResult with recovery guidance.
    """

    def handle(
        self,
        error: Exception,
        run_context: Optional[AgentRunContextProtocol] = None,
    ) -> ThinkResult:
        """
        Convert exception to ThinkResult with recovery action.

        Args:
            error: The exception that occurred
            run_context: Optional context for error tracking (affinity handoff)

        Returns:
            ThinkResult with error info and recovery guidance
        """
        ...


class DefaultThinkErrorHandler:
    """
    Default implementation of ThinkErrorHandlerProtocol.

    Maps known exception types to appropriate ThinkResult with:
    - Error message for display
    - Recovery action (retry, fallback, abort)
    - Error category for classification
    - Fatal flag for immediate stop

    Also records errors in run_context for affinity tracking.
    """

    def handle(
        self,
        error: Exception,
        run_context: Optional[AgentRunContextProtocol] = None,
    ) -> ThinkResult:
        """Convert exception to ThinkResult with recovery guidance."""
        # Record error for affinity tracking (may trigger provider handoff)
        self._record_error_for_affinity(error, run_context)

        # Handle cancellation first (user-initiated)
        if isinstance(error, StreamCancelledError):
            logger.info("LLM streaming cancelled by user")
            return ThinkResult(
                error="Cancelled by user",
                recovery_action=RecoveryAction.ABORT.value,
                is_fatal=True,
            )

        # LLM not configured - fatal, needs user action
        if isinstance(error, NotConfiguredError):
            logger.error("LLM not configured. User needs to run setup.")
            return ThinkResult(
                error="LLM not configured. Run /setup",
                recovery_action=RecoveryAction.ABORT.value,
                is_fatal=True,
            )

        # Authentication error - non-retryable, user needs to fix API keys
        if isinstance(error, AuthenticationError):
            logger.error("Authentication error: %s", error)
            return ThinkResult(
                error=str(error),
                recovery_action=error.recovery_action.value,
                error_category=error.category.value,
                is_fatal=True,
            )

        # Concrete model selection exhausted after orchestrator-level fallback.
        if isinstance(error, SelectionExhaustedError):
            logger.warning("Selection exhausted: %s", error)
            return ThinkResult(
                error=str(error),
                suggestion=error.suggestion,
                recovery_action=RecoveryAction.FALLBACK.value,
                error_category="rate_limit",
                is_fatal=False,
            )

        # Router group exhausted - trigger fallback to different model
        if isinstance(error, AllProvidersRateLimitedError):
            logger.warning("Router group exhausted")
            return ThinkResult(
                error="All providers rate limited. Please try again later.",
                recovery_action=RecoveryAction.FALLBACK.value,
                error_category=error.category.value,
                is_fatal=False,  # Delegator should try fallback
            )

        # Single provider rate limit - retryable with fallback
        if isinstance(error, RateLimitError):
            logger.warning(
                "Rate limit on provider %s: %s",
                error.provider_name or "unknown",
                error,
                extra=error.logging_extra(),
            )
            return ThinkResult(
                error=str(error),
                recovery_action=error.recovery_action.value,
                error_category=error.category.value,
                is_fatal=False,
            )

        # Network/timeout errors - retryable
        if isinstance(error, (NetworkError, InfraTimeoutError)):
            logger.warning(
                "Network error in think node: %s",
                error,
                extra=error.logging_extra(),
            )
            return ThinkResult(
                error=str(error),
                recovery_action=error.recovery_action.value,
                error_category=error.category.value,
                is_fatal=False,
            )

        # Stdlib network errors (fallback for non-wrapped errors)
        if isinstance(error, (ConnectionError, TimeoutError, OSError)):
            logger.warning("Network error in think node: %s", error)
            return ThinkResult(
                error=f"Connection error: {error}",
                recovery_action=RecoveryAction.RETRY.value,
                error_category="network",
                is_fatal=False,
            )

        # Provider execution error - may be retryable
        if isinstance(error, ProviderExecutionError):
            logger.warning(
                "Provider execution error: %s",
                error,
                extra=error.logging_extra(),
            )
            return ThinkResult(
                error=str(error),
                recovery_action=error.recovery_action.value,
                error_category=error.category.value,
                is_fatal=False,
            )

        # Generic provider error - check if retryable
        if isinstance(error, ProviderError):
            log_method = logger.warning if error.is_retryable else logger.error
            log_method(
                "Provider error: %s",
                error,
                extra=error.logging_extra(),
            )
            return ThinkResult(
                error=str(error),
                recovery_action=error.recovery_action.value,
                error_category=error.category.value,
                is_fatal=not error.is_retryable,
            )

        # Response parsing/handling errors - may be retryable (API returned bad format)
        if isinstance(error, (json.JSONDecodeError, ValueError, TypeError, AttributeError)):
            logger.warning("Response parsing error in think node: %s", error)
            return ThinkResult(
                error=f"Response error: {error}",
                recovery_action=RecoveryAction.RETRY.value,
                error_category="parse",
                is_fatal=False,
            )

        # Unexpected error - log with full traceback for debugging
        logger.exception(f"Unexpected error in think node: {type(error).__name__}: {error}")
        return ThinkResult(
            error=str(error),
            recovery_action=RecoveryAction.ABORT.value,
            error_category="system",
            is_fatal=True,
        )

    def _record_error_for_affinity(
        self,
        error: Exception,
        run_context: Optional[AgentRunContextProtocol],
    ) -> None:
        """Record error in run_context for affinity tracking."""
        if run_context is None:
            return

        # Extract provider and category from error if available
        provider = getattr(error, "provider_name", None) or "unknown"
        category = getattr(error, "category", None)

        if category:
            run_context.record_provider_error(provider, category.value)
        elif isinstance(error, (ConnectionError, TimeoutError, OSError)):
            run_context.record_provider_error(provider, "network")
