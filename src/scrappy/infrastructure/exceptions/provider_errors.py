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


class ProviderError(BaseError):
    """Base for all provider-related errors."""

    default_category = ErrorCategory.API

    def __init__(
        self,
        message: str,
        provider_name: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize provider error.

        Args:
            message: Error message
            provider_name: Name of the provider that failed
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        if provider_name:
            context['provider_name'] = provider_name

        super().__init__(message, context=context, **kwargs)
        self.provider_name = provider_name


class RateLimitError(RetryableError):
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

        # Add helpful suggestion
        suggestion = kwargs.pop('suggestion', None)
        if not suggestion and wait_seconds:
            suggestion = f"Wait {wait_seconds:.1f} seconds before retrying."

        super().__init__(
            message,
            context=context,
            suggestion=suggestion,
            **kwargs
        )
        self.provider_name = provider_name
        self.wait_seconds = wait_seconds
        self.max_wait_seconds = max_wait_seconds


class AllProvidersRateLimitedError(NonRetryableError):
    """All providers are rate limited.

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

        context = kwargs.pop('context', {})
        if self.attempted_providers:
            context['attempted_providers'] = self.attempted_providers
        if self.provider_details:
            context['provider_details'] = self.provider_details

        # Generate user-friendly suggestion based on retry times
        suggestion = kwargs.pop('suggestion', None)
        if not suggestion:
            suggestion = self._generate_suggestion()

        # Generate user-friendly message if not provided
        if not message or message == "Rate limit exceeded":
            message = self._generate_message()

        super().__init__(
            message,
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

        if min_retry is not None:
            return f"Wait {self._format_time(min_retry)} or add another provider API key."
        return "Wait for rate limits to reset or add more provider API keys."

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds into human-readable time."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"

    def user_friendly_message(self) -> str:
        """Get complete user-friendly message with suggestion.

        Returns formatted message suitable for display to users.
        """
        parts = [str(self)]
        if self.suggestion:
            parts.append(f"Suggestion: {self.suggestion}")
        return "\n".join(parts)


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
            suggestion = f"Available providers: {providers_str}"

        super().__init__(
            message,
            context=context,
            suggestion=suggestion,
            **kwargs
        )
        self.provider_name = provider_name
        self.available_providers = available_providers or []


class AuthenticationError(NonRetryableError):
    """Authentication or API key error."""

    default_category = ErrorCategory.AUTHENTICATION
    default_severity = ErrorSeverity.CRITICAL

    def __init__(
        self,
        message: str,
        provider_name: Optional[str] = None,
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
            suggestion = (
                f"Check your API key for {provider_name or 'the provider'}. "
                "Ensure it is valid and has proper permissions."
            )

        super().__init__(
            message,
            context=context,
            suggestion=suggestion,
            **kwargs
        )
        self.provider_name = provider_name


class TimeoutError(RetryableError):
    """Request timeout error."""

    default_category = ErrorCategory.NETWORK
    default_severity = ErrorSeverity.WARNING

    def __init__(
        self,
        message: str,
        timeout_seconds: Optional[float] = None,
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
            suggestion = "The request took too long. Try again or check network connection."

        super().__init__(
            message,
            context=context,
            suggestion=suggestion,
            **kwargs
        )
        self.timeout_seconds = timeout_seconds


class NetworkError(RetryableError):
    """Network connectivity error."""

    default_category = ErrorCategory.NETWORK
    default_severity = ErrorSeverity.WARNING

    def __init__(
        self,
        message: str,
        **kwargs: Any
    ):
        """Initialize network error.

        Args:
            message: Error message
            **kwargs: Additional BaseError arguments
        """
        suggestion = kwargs.pop('suggestion', None)
        if not suggestion:
            suggestion = "Check your network connection and try again."

        super().__init__(
            message,
            suggestion=suggestion,
            **kwargs
        )


class ProviderExecutionError(RetryableError):
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
            context=context,
            original_error=original_error,
            **kwargs
        )
        self.provider_name = provider_name
