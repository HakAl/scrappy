"""
Delegation and orchestration exceptions.

Errors related to request delegation, caching, and batch processing.
"""

from typing import Optional, Any
from .base import BaseError, NonRetryableError
from .enums import (
    ErrorCategory,
    ErrorSeverity,
    RecoveryAction
)


class DelegationError(BaseError):
    """Base for delegation/orchestration errors."""

    default_category = ErrorCategory.SYSTEM


class RetryExhaustedError(NonRetryableError):
    """All retry attempts exhausted."""

    default_category = ErrorCategory.SYSTEM
    default_severity = ErrorSeverity.ERROR
    default_recovery_action = RecoveryAction.FALLBACK

    def __init__(
        self,
        message: str,
        attempted_providers: Optional[list[str]] = None,
        last_error: Optional[Exception] = None,
        total_attempts: int = 0,
        **kwargs: Any
    ):
        """Initialize retry exhausted error.

        Args:
            message: Error message
            attempted_providers: Providers that were attempted
            last_error: Last error that occurred
            total_attempts: Total number of attempts made
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        context.update({
            'attempted_providers': attempted_providers or [],
            'total_attempts': total_attempts,
        })

        super().__init__(
            message,
            context=context,
            original_error=last_error,
            **kwargs
        )
        self.attempted_providers = attempted_providers or []
        self.last_error = last_error
        self.total_attempts = total_attempts


class CacheError(BaseError):
    """Cache operation error."""

    default_category = ErrorCategory.SYSTEM
    default_severity = ErrorSeverity.WARNING

    def __init__(
        self,
        message: str,
        cache_key: Optional[str] = None,
        operation: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize cache error.

        Args:
            message: Error message
            cache_key: Key that caused the error
            operation: Operation that failed (get, put, clear, etc.)
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        context.update({
            'cache_key': cache_key,
            'operation': operation,
        })

        super().__init__(
            message,
            context=context,
            **kwargs
        )
        self.cache_key = cache_key
        self.operation = operation


class InvalidRequestError(NonRetryableError):
    """Invalid request parameters."""

    default_category = ErrorCategory.VALIDATION
    default_severity = ErrorSeverity.ERROR

    def __init__(
        self,
        message: str,
        parameter_name: Optional[str] = None,
        parameter_value: Optional[Any] = None,
        validation_message: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize invalid request error.

        Args:
            message: Error message
            parameter_name: Name of invalid parameter
            parameter_value: Value that was invalid
            validation_message: Specific validation failure
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        context.update({
            'parameter_name': parameter_name,
            'parameter_value': parameter_value,
            'validation_message': validation_message,
        })

        suggestion = kwargs.pop('suggestion', None)
        if not suggestion and validation_message:
            suggestion = validation_message

        super().__init__(
            message,
            context=context,
            suggestion=suggestion,
            **kwargs
        )
        self.parameter_name = parameter_name
        self.parameter_value = parameter_value
        self.validation_message = validation_message


class PromptAugmentationError(BaseError):
    """Error during prompt augmentation."""

    default_category = ErrorCategory.SYSTEM
    default_severity = ErrorSeverity.WARNING

    def __init__(
        self,
        message: str,
        augmentation_type: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize prompt augmentation error.

        Args:
            message: Error message
            augmentation_type: Type of augmentation that failed
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        if augmentation_type:
            context['augmentation_type'] = augmentation_type

        super().__init__(
            message,
            context=context,
            **kwargs
        )
        self.augmentation_type = augmentation_type


class BatchSchedulingError(BaseError):
    """Error during batch request scheduling."""

    default_category = ErrorCategory.SYSTEM
    default_severity = ErrorSeverity.ERROR

    def __init__(
        self,
        message: str,
        batch_size: Optional[int] = None,
        failed_count: Optional[int] = None,
        **kwargs: Any
    ):
        """Initialize batch scheduling error.

        Args:
            message: Error message
            batch_size: Size of batch that failed
            failed_count: Number of failed requests
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        context.update({
            'batch_size': batch_size,
            'failed_count': failed_count,
        })

        super().__init__(
            message,
            context=context,
            **kwargs
        )
        self.batch_size = batch_size
        self.failed_count = failed_count


class CircuitBreakerOpenError(NonRetryableError):
    """Circuit breaker is open, blocking calls."""

    default_category = ErrorCategory.SYSTEM
    default_severity = ErrorSeverity.WARNING
    default_recovery_action = RecoveryAction.FALLBACK

    def __init__(
        self,
        message: str,
        circuit_name: Optional[str] = None,
        failure_count: Optional[int] = None,
        reset_timeout: Optional[float] = None,
        **kwargs: Any
    ):
        """Initialize circuit breaker open error.

        Args:
            message: Error message
            circuit_name: Name of the circuit
            failure_count: Number of failures that opened circuit
            reset_timeout: Seconds until circuit tries half-open
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        context.update({
            'circuit_name': circuit_name,
            'failure_count': failure_count,
            'reset_timeout': reset_timeout,
        })

        suggestion = kwargs.pop('suggestion', None)
        if not suggestion and reset_timeout:
            suggestion = f"Circuit will reset in {reset_timeout:.1f} seconds. Try a different provider."

        super().__init__(
            message,
            context=context,
            suggestion=suggestion,
            **kwargs
        )
        self.circuit_name = circuit_name
        self.failure_count = failure_count
        self.reset_timeout = reset_timeout
