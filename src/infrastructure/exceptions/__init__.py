"""
Unified exception hierarchy for the application.

This package consolidates the previously separate CLI and delegation
exception hierarchies into a single, coherent taxonomy.

All exceptions inherit from BaseError and include:
- Rich metadata (category, severity, context)
- Recovery action hints
- Structured logging support
- Retry classification

Example usage:

    from infrastructure.exceptions import RateLimitError, RecoveryAction

    try:
        make_api_call()
    except RateLimitError as e:
        if e.recovery_action == RecoveryAction.RETRY:
            # Retry logic
            pass
        logger.error("Rate limit hit", extra=e.logging_extra())
"""

# Import enums first (no dependencies)
from .enums import (
    RecoveryAction,
    ErrorSeverity,
    ErrorCategory,
)

# Base classes
from .base import (
    BaseError,
    RetryableError,
    NonRetryableError,
)

# Provider errors
from .provider_errors import (
    ProviderError,
    RateLimitError,
    AllProvidersRateLimitedError,
    ProviderNotFoundError,
    AuthenticationError,
    TimeoutError,
    NetworkError,
    ProviderExecutionError,
)

# Delegation errors
from .delegation_errors import (
    DelegationError,
    RetryExhaustedError,
    CacheError,
    InvalidRequestError,
    PromptAugmentationError,
    BatchSchedulingError,
    CircuitBreakerOpenError,
)

# CLI errors
from .cli_errors import (
    CLIError,
    ValidationError,
    FileOperationError,
    SessionError,
    TaskExecutionError,
    ParseError,
    UserInputError,
)

__all__ = [
    # Enums
    'RecoveryAction',
    'ErrorSeverity',
    'ErrorCategory',

    # Base classes
    'BaseError',
    'RetryableError',
    'NonRetryableError',

    # Provider errors
    'ProviderError',
    'RateLimitError',
    'AllProvidersRateLimitedError',
    'ProviderNotFoundError',
    'AuthenticationError',
    'TimeoutError',
    'NetworkError',
    'ProviderExecutionError',

    # Delegation errors
    'DelegationError',
    'RetryExhaustedError',
    'CacheError',
    'InvalidRequestError',
    'PromptAugmentationError',
    'BatchSchedulingError',
    'CircuitBreakerOpenError',

    # CLI errors
    'CLIError',
    'ValidationError',
    'FileOperationError',
    'SessionError',
    'TaskExecutionError',
    'ParseError',
    'UserInputError',
]
