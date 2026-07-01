"""
Base exception classes for unified error handling.

Unifies the previously separate CLI and delegation exception hierarchies
into a single, coherent taxonomy with rich metadata and recovery actions.
"""

from typing import Optional, Any, Dict
import json
import logging
import traceback

from .enums import (
    RecoveryAction,
    ErrorSeverity,
    ErrorCategory
)


class BaseError(Exception):
    """Base exception for all application errors.

    Provides rich metadata, recovery hints, and structured logging support.
    Unifies the previous CLIError and DelegationError hierarchies.

    Attributes:
        message: Human-readable error message
        category: Classification of error type
        severity: Severity level (maps to log level)
        context: Additional context data
        suggestion: User-facing suggestion for resolution
        original_error: Wrapped exception (if any)
        recovery_action: Recommended recovery action
    """

    # Default values (can be overridden by subclasses)
    default_category = ErrorCategory.SYSTEM
    default_severity = ErrorSeverity.ERROR
    default_recovery_action = RecoveryAction.ABORT

    def __init__(
        self,
        message: str,
        *,
        category: Optional[ErrorCategory] = None,
        severity: Optional[ErrorSeverity] = None,
        context: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None,
        original_error: Optional[Exception] = None,
        recovery_action: Optional[RecoveryAction] = None
    ):
        """Initialize error with metadata.

        Args:
            message: Error message
            category: Error category (uses default if None)
            severity: Severity level (uses default if None)
            context: Additional context data
            suggestion: User-facing recovery suggestion
            original_error: Original wrapped exception
            recovery_action: Recommended recovery action
        """
        super().__init__(message)
        self.message = message
        self.category = category or self.default_category
        self.severity = severity or self.default_severity
        self.context = context or {}
        self.suggestion = suggestion
        self.original_error = original_error
        self._recovery_action = recovery_action

    @property
    def recovery_action(self) -> RecoveryAction:
        """Get recommended recovery action.

        Returns appropriate action based on error characteristics.
        """
        if self._recovery_action:
            return self._recovery_action

        # Auto-determine recovery action from error characteristics
        if self.is_retryable:
            return RecoveryAction.RETRY
        elif self.severity == ErrorSeverity.CRITICAL:
            return RecoveryAction.ABORT
        elif self.category == ErrorCategory.USER_INPUT:
            return RecoveryAction.ASK_USER
        else:
            return self.default_recovery_action

    @property
    def is_retryable(self) -> bool:
        """Check if error is retryable.

        Override in subclasses for specific retry logic.
        """
        return False

    @property
    def log_level(self) -> int:
        """Get logging level from severity."""
        severity_to_level = {
            ErrorSeverity.INFO: logging.INFO,
            ErrorSeverity.WARNING: logging.WARNING,
            ErrorSeverity.ERROR: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL,
        }
        return severity_to_level.get(self.severity, logging.ERROR)

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to structured dictionary.

        Returns:
            Dictionary with all error metadata
        """
        data = {
            'type': self.__class__.__name__,
            'message': self.message,
            'category': self.category.value,
            'severity': self.severity.value,
            'recovery_action': self.recovery_action.value,
            'context': self.context,
        }

        if self.suggestion:
            data['suggestion'] = self.suggestion

        if self.original_error:
            data['original_error'] = {
                'type': type(self.original_error).__name__,
                'message': str(self.original_error),
            }

        return data

    def to_json(self) -> str:
        """Convert error to JSON string.

        Returns:
            JSON representation of error
        """
        return json.dumps(self.to_dict(), indent=2)

    def logging_extra(self) -> Dict[str, Any]:
        """Get extra fields for structured logging.

        Returns:
            Dictionary of fields for log context
        """
        extra = {
            'error_type': self.__class__.__name__,
            'error_category': self.category.value,
            'error_severity': self.severity.value,
            'recovery_action': self.recovery_action.value,
        }

        # Add context fields with error_ prefix
        for key, value in self.context.items():
            extra[f'error_context_{key}'] = value

        return extra

    def get_traceback(self) -> str:
        """Get formatted traceback.

        Returns:
            Formatted traceback string
        """
        if self.original_error:
            return ''.join(traceback.format_exception(
                type(self.original_error),
                self.original_error,
                self.original_error.__traceback__
            ))
        return ''.join(traceback.format_exception(
            type(self),
            self,
            self.__traceback__
        ))

    def __str__(self) -> str:
        """String representation."""
        parts = [self.message]
        if self.suggestion:
            parts.append(f"\nSuggestion: {self.suggestion}")
        if self.original_error:
            parts.append(f"\nCaused by: {type(self.original_error).__name__}: {self.original_error}")
        return ''.join(parts)

    def __repr__(self) -> str:
        """Developer representation."""
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"category={self.category}, "
            f"severity={self.severity}, "
            f"recovery_action={self.recovery_action})"
        )


class RetryableError(BaseError):
    """Base for errors that can be retried.

    Subclasses automatically have is_retryable=True.
    """

    default_recovery_action = RecoveryAction.RETRY

    @property
    def is_retryable(self) -> bool:
        """This error is retryable."""
        return True


class NonRetryableError(BaseError):
    """Base for errors that should not be retried.

    Makes explicit that retry is not appropriate.
    """

    default_recovery_action = RecoveryAction.ABORT

    @property
    def is_retryable(self) -> bool:
        """This error is not retryable."""
        return False
