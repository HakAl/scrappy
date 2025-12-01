"""Domain-specific exceptions for LLM delegation.

This module defines a hierarchy of exceptions specific to the delegation
domain. Using domain exceptions instead of generic Exception provides:
- Clear error semantics
- Type-safe exception handling
- Better error messages
- Easier debugging and logging
"""

from typing import Any


class DelegationError(Exception):
    """Base exception for all delegation-related errors.

    All delegation exceptions inherit from this base class, allowing
    callers to catch all delegation errors with a single except clause
    if desired.
    """
    pass


class RetryExhaustedError(DelegationError):
    """Raised when all retry attempts are exhausted.

    This exception is raised when the retry orchestrator has attempted
    all configured retries across all available providers and still
    could not successfully complete the request.

    Attributes:
        attempted_providers: List of provider names that were attempted
        last_error: The final error that caused the failure
        total_attempts: Total number of retry attempts made
    """

    def __init__(
        self,
        attempted_providers: list[str],
        last_error: Exception,
        total_attempts: int = 0
    ):
        self.attempted_providers = attempted_providers
        self.last_error = last_error
        self.total_attempts = total_attempts

        message = (
            f"All providers failed after {total_attempts} attempts. "
            f"Attempted providers: {attempted_providers}. "
            f"Last error: {last_error}"
        )
        super().__init__(message)


class CacheError(DelegationError):
    """Raised when cache operations fail.

    This exception is raised when the cache protocol implementation
    encounters an error during get, put, or clear operations.
    """
    pass


class ProviderNotFoundError(DelegationError):
    """Raised when requested provider doesn't exist.

    This exception is raised when a caller requests a specific provider
    by name but that provider is not registered in the provider registry.

    Attributes:
        provider_name: The name of the provider that was requested
        available_providers: List of provider names that are available
    """

    def __init__(self, provider_name: str, available_providers: list[str]):
        self.provider_name = provider_name
        self.available_providers = available_providers

        message = (
            f"Provider '{provider_name}' not found. "
            f"Available providers: {available_providers}"
        )
        super().__init__(message)


class RateLimitExceededError(DelegationError):
    """Raised when rate limit is exceeded and cannot wait.

    This exception is raised when a provider's rate limit is exceeded
    and the rate limit tracker determines that waiting is not feasible
    (e.g., wait time exceeds timeout threshold).

    Attributes:
        provider_name: The name of the provider that hit rate limit
        wait_seconds: How long the caller would need to wait
        max_wait_seconds: Maximum wait time configured
    """

    def __init__(
        self,
        provider_name: str,
        wait_seconds: float,
        max_wait_seconds: float | None = None
    ):
        self.provider_name = provider_name
        self.wait_seconds = wait_seconds
        self.max_wait_seconds = max_wait_seconds

        message = f"Rate limit exceeded for provider '{provider_name}'. "
        if max_wait_seconds is not None:
            message += (
                f"Would need to wait {wait_seconds:.1f}s, "
                f"but max wait is {max_wait_seconds:.1f}s."
            )
        else:
            message += f"Would need to wait {wait_seconds:.1f}s."

        super().__init__(message)


class InvalidRequestError(DelegationError):
    """Raised when request parameters are invalid.

    This exception is raised when the request object contains invalid
    parameters (e.g., negative max_tokens, empty prompt, invalid temperature).

    Attributes:
        parameter_name: The name of the invalid parameter
        parameter_value: The invalid value provided
        validation_message: Description of why the value is invalid
    """

    def __init__(
        self,
        parameter_name: str,
        parameter_value: Any,
        validation_message: str
    ):
        self.parameter_name = parameter_name
        self.parameter_value = parameter_value
        self.validation_message = validation_message

        message = (
            f"Invalid request parameter '{parameter_name}': "
            f"{validation_message} (got: {parameter_value})"
        )
        super().__init__(message)


class PromptAugmentationError(DelegationError):
    """Raised when prompt augmentation fails.

    This exception is raised when the prompt augmenter encounters an
    error while trying to augment a prompt with context or working memory.
    """
    pass


class BatchSchedulingError(DelegationError):
    """Raised when batch scheduling fails.

    This exception is raised when the batch scheduler encounters an
    error during parallel execution setup or coordination.
    """
    pass


class ProviderExecutionError(DelegationError):
    """Raised when a provider execution fails.

    This exception wraps provider-specific errors and provides context
    about which provider failed and what the original error was.

    Attributes:
        provider_name: The name of the provider that failed
        original_error: The original exception from the provider
    """

    def __init__(self, provider_name: str, original_error: Exception):
        self.provider_name = provider_name
        self.original_error = original_error

        message = (
            f"Provider '{provider_name}' execution failed: {original_error}"
        )
        super().__init__(message)
