"""
Provider-specific exceptions.

Errors related to LLM providers, API calls, rate limits, and authentication.
"""

from typing import Optional, Dict, Any
from .base import (
    BaseError,
    RetryableError,
    NonRetryableError
)
from .enums import (
    ErrorCategory,
    ErrorSeverity,
    RecoveryAction
)
from .failure_kinds import FailureKind
from .suggestions import (
    AUTH_SUGGESTION_TEMPLATE,
    NETWORK_SUGGESTION,
    PROVIDER_NOT_FOUND_TEMPLATE,
    RATE_LIMIT_WAIT_TEMPLATE,
    TIMEOUT_SUGGESTION,
    format_wait_time,
    router_group_suggestion,
)


class ProviderError(BaseError):
    """Base for all provider-related errors."""

    default_category = ErrorCategory.API

    def __init__(
        self,
        message: str,
        provider_name: Optional[str] = None,
        failure_kind: FailureKind = FailureKind.UNKNOWN,
        retry_after: Optional[float] = None,
        **kwargs: Any
    ):
        """Initialize provider error.

        Args:
            message: Error message
            provider_name: Name of the provider that failed
            failure_kind: Semantic classification for fallback policy
            retry_after: Suggested retry delay in seconds, if available
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        if provider_name:
            context['provider_name'] = provider_name
        context['failure_kind'] = failure_kind.value
        if retry_after is not None:
            context['retry_after'] = retry_after

        super().__init__(message, context=context, **kwargs)
        self.provider_name = provider_name
        self.failure_kind = failure_kind
        self.retry_after = retry_after


class RateLimitError(ProviderError, RetryableError):
    """Rate limit exceeded error.

    This is retryable after a wait period.
    """

    default_category = ErrorCategory.RATE_LIMIT
    default_severity = ErrorSeverity.WARNING

    def __init__(
        self,
        message: str,
        provider_name: Optional[str] = None,
        wait_seconds: Optional[float] = None,
        max_wait_seconds: Optional[float] = None,
        failure_kind: FailureKind = FailureKind.RATE_LIMIT,
        retry_after: Optional[float] = None,
        **kwargs: Any
    ):
        """Initialize rate limit error.

        Args:
            message: Error message
            provider_name: Provider that hit rate limit
            wait_seconds: Suggested wait time
            max_wait_seconds: Maximum wait time allowed
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        context.update({
            'provider_name': provider_name,
            'wait_seconds': wait_seconds,
            'max_wait_seconds': max_wait_seconds,
        })
        resolved_retry_after = retry_after if retry_after is not None else wait_seconds

        # Add helpful suggestion
        suggestion = kwargs.pop('suggestion', None)
        if not suggestion and resolved_retry_after:
            suggestion = RATE_LIMIT_WAIT_TEMPLATE.format(seconds=resolved_retry_after)

        super().__init__(
            message,
            provider_name=provider_name,
            failure_kind=failure_kind,
            retry_after=resolved_retry_after,
            context=context,
            suggestion=suggestion,
            **kwargs
        )
        self.wait_seconds = resolved_retry_after
        self.max_wait_seconds = max_wait_seconds


class RouterGroupExhaustedError(ProviderError, NonRetryableError):
    """All providers in a router group are exhausted.

    No point retrying since all providers are unavailable.
    """

    default_category = ErrorCategory.RATE_LIMIT
    default_severity = ErrorSeverity.ERROR
    default_recovery_action = RecoveryAction.ABORT

    def __init__(
        self,
        message: str,
        attempted_providers: Optional[list[str]] = None,
        provider_details: Optional[Dict[str, Dict[str, Any]]] = None,
        failure_summary: Optional[dict[str, FailureKind]] = None,
        **kwargs: Any
    ):
        """Initialize all-providers-rate-limited error.

        Args:
            message: Error message
            attempted_providers: List of providers attempted
            provider_details: Per-provider info with retry_after times.
                Format: {"provider": {"retry_after": seconds, "error": msg}}
            **kwargs: Additional BaseError arguments
        """
        self.provider_details = provider_details or {}
        self.attempted_providers = attempted_providers or list(self.provider_details.keys())
        self.failure_summary = failure_summary or {}

        context = kwargs.pop('context', {})
        if self.attempted_providers:
            context['attempted_providers'] = self.attempted_providers
        if self.provider_details:
            context['provider_details'] = self.provider_details
        if self.failure_summary:
            context['failure_summary'] = {
                key: value.value for key, value in self.failure_summary.items()
            }

        # Generate user-friendly suggestion based on retry times
        suggestion = kwargs.pop('suggestion', None)
        if not suggestion:
            suggestion = self._generate_suggestion()

        # Generate user-friendly message if not provided
        if not message or message == "Rate limit exceeded":
            message = self._generate_message()

        super().__init__(
            message,
            failure_kind=FailureKind.EXHAUSTED,
            context=context,
            suggestion=suggestion,
            **kwargs
        )

    def _generate_message(self) -> str:
        """Generate user-friendly error message listing providers."""
        if not self.attempted_providers:
            return "All providers are rate limited."

        parts = ["Rate limited by all providers:"]
        for provider in self.attempted_providers:
            details = self.provider_details.get(provider, {})
            retry_after = details.get("retry_after")
            if retry_after:
                parts.append(f"  - {provider}: retry after {self._format_time(retry_after)}")
            else:
                parts.append(f"  - {provider}")

        return "\n".join(parts)


    def _generate_suggestion(self) -> str:
        """Generate actionable suggestion based on retry times."""
        # Find minimum retry time
        min_retry = None
        for details in self.provider_details.values():
            retry_after = details.get("retry_after")
            if retry_after is not None:
                if min_retry is None or retry_after < min_retry:
                    min_retry = retry_after

        return router_group_suggestion(min_retry)

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds into human-readable time."""
        return format_wait_time(seconds)


# Backward-compatible public aliases. New code should use
# RouterGroupExhaustedError for LiteLLM router-group exhaustion.
AllProvidersRateLimitedError = RouterGroupExhaustedError
AllProvidersExhaustedError = RouterGroupExhaustedError


class ProviderNotFoundError(NonRetryableError):
    """Provider not found or not configured."""

    default_category = ErrorCategory.API
    default_severity = ErrorSeverity.ERROR

    def __init__(
        self,
        message: str,
        provider_name: Optional[str] = None,
        available_providers: Optional[list[str]] = None,
        **kwargs: Any
    ):
        """Initialize provider-not-found error.

        Args:
            message: Error message
            provider_name: Name of missing provider
            available_providers: List of available providers
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        context.update({
            'provider_name': provider_name,
            'available_providers': available_providers,
        })

        suggestion = kwargs.pop('suggestion', None)
        if not suggestion and available_providers:
            providers_str = ", ".join(available_providers)
            suggestion = PROVIDER_NOT_FOUND_TEMPLATE.format(providers=providers_str)

        super().__init__(
            message,
            context=context,
            suggestion=suggestion,
            **kwargs
        )
        self.provider_name = provider_name
        self.available_providers = available_providers or []


class AuthenticationError(ProviderError, NonRetryableError):
    """Authentication or API key error."""

    default_category = ErrorCategory.AUTHENTICATION
    default_severity = ErrorSeverity.CRITICAL

    def __init__(
        self,
        message: str,
        provider_name: Optional[str] = None,
        failure_kind: FailureKind = FailureKind.AUTH,
        retry_after: Optional[float] = None,
        **kwargs: Any
    ):
        """Initialize authentication error.

        Args:
            message: Error message
            provider_name: Provider with auth issue
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        if provider_name:
            context['provider_name'] = provider_name

        suggestion = kwargs.pop('suggestion', None)
        if not suggestion:
            suggestion = AUTH_SUGGESTION_TEMPLATE.format(
                provider=provider_name or 'the provider'
            )

        super().__init__(
            message,
            provider_name=provider_name,
            failure_kind=failure_kind,
            retry_after=retry_after,
            context=context,
            suggestion=suggestion,
            **kwargs
        )


class TimeoutError(ProviderError, RetryableError):
    """Request timeout error."""

    default_category = ErrorCategory.NETWORK
    default_severity = ErrorSeverity.WARNING

    def __init__(
        self,
        message: str,
        timeout_seconds: Optional[float] = None,
        provider_name: Optional[str] = None,
        failure_kind: FailureKind = FailureKind.TIMEOUT,
        retry_after: Optional[float] = None,
        **kwargs: Any
    ):
        """Initialize timeout error.

        Args:
            message: Error message
            timeout_seconds: Timeout value that was exceeded
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        if timeout_seconds:
            context['timeout_seconds'] = timeout_seconds

        suggestion = kwargs.pop('suggestion', None)
        if not suggestion:
            suggestion = TIMEOUT_SUGGESTION

        super().__init__(
            message,
            provider_name=provider_name,
            failure_kind=failure_kind,
            retry_after=retry_after,
            context=context,
            suggestion=suggestion,
            **kwargs
        )
        self.timeout_seconds = timeout_seconds


class NetworkError(ProviderError, RetryableError):
    """Network connectivity error."""

    default_category = ErrorCategory.NETWORK
    default_severity = ErrorSeverity.WARNING

    def __init__(
        self,
        message: str,
        provider_name: Optional[str] = None,
        failure_kind: FailureKind = FailureKind.NETWORK,
        retry_after: Optional[float] = None,
        **kwargs: Any
    ):
        """Initialize network error.

        Args:
            message: Error message
            **kwargs: Additional BaseError arguments
        """
        suggestion = kwargs.pop('suggestion', None)
        if not suggestion:
            suggestion = NETWORK_SUGGESTION

        super().__init__(
            message,
            provider_name=provider_name,
            failure_kind=failure_kind,
            retry_after=retry_after,
            suggestion=suggestion,
            **kwargs
        )


class ProviderExecutionError(ProviderError, RetryableError):
    """Error during provider execution.

    Wraps provider-specific errors with context.
    """

    default_category = ErrorCategory.API
    default_severity = ErrorSeverity.ERROR

    def __init__(
        self,
        message: str,
        provider_name: Optional[str] = None,
        original_error: Optional[Exception] = None,
        failure_kind: FailureKind = FailureKind.UNKNOWN,
        retry_after: Optional[float] = None,
        **kwargs: Any
    ):
        """Initialize provider execution error.

        Args:
            message: Error message
            provider_name: Provider that failed
            original_error: Original provider exception
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        if provider_name:
            context['provider_name'] = provider_name

        super().__init__(
            message,
            provider_name=provider_name,
            failure_kind=failure_kind,
            retry_after=retry_after,
            context=context,
            original_error=original_error,
            **kwargs
        )
