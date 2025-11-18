"""
Custom CLI exceptions for consistent error handling.

This module provides a hierarchy of exceptions with rich metadata
for categorization, severity levels, suggestions, and recovery strategies.
"""

import json
import logging
import traceback
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from .utils.error_handler import ErrorCategory, ErrorSeverity


class RecoveryAction(Enum):
    """Recovery actions that can be taken for errors."""
    RETRY = "retry"
    FALLBACK = "fallback"
    ABORT = "abort"
    SKIP = "skip"
    ASK_USER = "ask_user"


class CLIError(Exception):
    """
    Base exception for all CLI errors.

    Provides rich metadata for error handling including category,
    severity, context, suggestions, and recovery strategies.
    """

    def __init__(
        self,
        message: Optional[str],
        category: ErrorCategory = ErrorCategory.SYSTEM,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        context: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None,
        original: Optional[Exception] = None
    ):
        self.message = message if message is not None else ""
        self.category = category
        self.severity = severity
        self.context = context or {}
        self._suggestion = suggestion
        self.original = original

        super().__init__(self.message)

        if original:
            self.__cause__ = original

    def __str__(self) -> str:
        return self.message if self.message else ""

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.message!r})"

    @property
    def suggestion(self) -> str:
        """Get actionable suggestion for this error."""
        if self._suggestion:
            return self._suggestion
        return "Try again or check the operation parameters."

    @property
    def log_level(self) -> int:
        """Map severity to Python logging level."""
        mapping = {
            ErrorSeverity.INFO: logging.INFO,
            ErrorSeverity.WARNING: logging.WARNING,
            ErrorSeverity.ERROR: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL,
        }
        return mapping.get(self.severity, logging.ERROR)

    @property
    def recovery_action(self) -> RecoveryAction:
        """Get suggested recovery action for this error."""
        return RecoveryAction.ASK_USER

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for structured logging."""
        result = {
            "message": self.message,
            "category": self.category.name if hasattr(self.category, 'name') else str(self.category),
            "severity": self.severity.name if hasattr(self.severity, 'name') else str(self.severity),
        }

        # Handle non-serializable context values
        if self.context:
            try:
                json.dumps(self.context)
                result["context"] = self.context
            except (TypeError, ValueError):
                # Convert non-serializable values to strings
                result["context"] = {
                    k: str(v) if not isinstance(v, (str, int, float, bool, type(None), list, dict)) else v
                    for k, v in self.context.items()
                }
        else:
            result["context"] = {}

        return result

    def logging_extra(self) -> Dict[str, Any]:
        """Get extra data for structured logging."""
        return {
            "error_type": self.__class__.__name__,
            "category": self.category.name if hasattr(self.category, 'name') else str(self.category),
        }


class ValidationError(CLIError):
    """Exception for input validation failures."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Any = None,
        **kwargs
    ):
        kwargs.setdefault('category', ErrorCategory.VALIDATION)
        super().__init__(message, **kwargs)
        self.field = field
        self.value = value

    @property
    def suggestion(self) -> str:
        if self._suggestion:
            return self._suggestion
        if self.field:
            return f"Check the value for '{self.field}' and ensure it's in the correct format."
        return "Verify the input value is in the expected format."

    def __repr__(self) -> str:
        return f"ValidationError({self.message!r}, field={self.field!r})"


class ProviderError(CLIError):
    """Exception for API/provider failures."""

    def __init__(
        self,
        message: str,
        provider: str = "unknown",
        rate_limited: bool = False,
        is_timeout: bool = False,
        is_auth_error: bool = False,
        original: Optional[Exception] = None,
        **kwargs
    ):
        kwargs.setdefault('category', ErrorCategory.API)
        super().__init__(message, original=original, **kwargs)
        self.provider = provider
        self.rate_limited = rate_limited
        self.is_timeout = is_timeout
        self.is_auth_error = is_auth_error

    @property
    def is_retryable(self) -> bool:
        """Check if this error can be retried."""
        if self.is_auth_error:
            return False
        return self.rate_limited or self.is_timeout or not self.is_auth_error

    @property
    def suggestion(self) -> str:
        if self._suggestion:
            return self._suggestion
        if self.rate_limited:
            return "Wait a moment and retry the request."
        if self.is_timeout:
            return "The request timed out. Try again or use a different provider."
        if self.is_auth_error:
            return "Check your API key configuration."
        return "Try using an alternative provider."

    @property
    def recovery_action(self) -> RecoveryAction:
        if self.is_auth_error:
            return RecoveryAction.ABORT
        if self.rate_limited or self.is_timeout:
            return RecoveryAction.RETRY
        return RecoveryAction.FALLBACK

    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result["provider"] = self.provider
        result["rate_limited"] = self.rate_limited
        result["is_timeout"] = self.is_timeout
        result["is_auth_error"] = self.is_auth_error
        return result

    def logging_extra(self) -> Dict[str, Any]:
        extra = super().logging_extra()
        extra["provider"] = self.provider
        extra["rate_limited"] = self.rate_limited
        extra["is_timeout"] = self.is_timeout
        return extra


class FileOperationError(CLIError):
    """Exception for file system operation failures."""

    def __init__(
        self,
        message: str,
        path: Optional[Path] = None,
        operation: Optional[str] = None,
        original: Optional[Exception] = None,
        **kwargs
    ):
        kwargs.setdefault('category', ErrorCategory.FILE)
        super().__init__(message, original=original, **kwargs)
        self.path = path
        self.operation = operation
        self._is_permission_error = isinstance(original, PermissionError)

    @classmethod
    def from_os_error(cls, error: Exception, path: Path) -> 'FileOperationError':
        """Create FileOperationError from OS-level error."""
        if isinstance(error, FileNotFoundError):
            message = f"File not found: {path}"
        elif isinstance(error, PermissionError):
            message = f"Permission denied: {path}"
        else:
            message = f"File operation failed: {error}"

        instance = cls(message, path=path, original=error)
        instance._is_permission_error = isinstance(error, PermissionError)
        return instance

    @property
    def suggestion(self) -> str:
        if self._suggestion:
            return self._suggestion
        if self._is_permission_error:
            return "Check that you have permission to access this file."
        return "Check that the path exists and is accessible."


class SessionError(CLIError):
    """Exception for session management failures."""

    def __init__(
        self,
        message: str,
        operation: str = "unknown",
        session_path: Optional[Path] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.operation = operation
        self.session_path = session_path


class TaskExecutionError(CLIError):
    """Exception for task execution failures."""

    def __init__(
        self,
        message: str,
        task_name: str = "unknown",
        partial_result: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        kwargs.setdefault('category', ErrorCategory.TASK)
        super().__init__(message, **kwargs)
        self.task_name = task_name
        self.partial_result = partial_result


class ParseError(CLIError):
    """Exception for parsing failures."""

    def __init__(
        self,
        message: str,
        source: str = "unknown",
        content_preview: Optional[str] = None,
        original: Optional[Exception] = None,
        **kwargs
    ):
        kwargs.setdefault('category', ErrorCategory.PARSE)
        super().__init__(message, original=original, **kwargs)
        self.source = source
        self.content_preview = content_preview

    @classmethod
    def from_json_error(cls, error: Exception, source: str) -> 'ParseError':
        """Create ParseError from JSON decode error."""
        return cls(
            message=str(error),
            source=source,
            original=error
        )


class UserInputError(CLIError):
    """Exception for user input failures."""

    def __init__(
        self,
        message: str,
        interrupted: bool = False,
        eof: bool = False,
        **kwargs
    ):
        kwargs.setdefault('category', ErrorCategory.USER_INPUT)
        super().__init__(message, **kwargs)
        self.interrupted = interrupted
        self.eof = eof
