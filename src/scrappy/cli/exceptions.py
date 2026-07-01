"""
Custom CLI exceptions for consistent error handling.

This module provides a hierarchy of exceptions with rich metadata
for categorization, severity levels, suggestions, and recovery strategies.
"""

import json
import logging
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
    """Base exception for all CLI errors.

    Provides rich metadata for error handling including category,
    severity, context, suggestions, and recovery strategies. This is the
    base class for all custom CLI exceptions.

    Attributes:
        message: Human-readable error message.
        category: ErrorCategory enum value for error classification.
        severity: ErrorSeverity enum value for logging level.
        context: Dict of additional context data for debugging.
        original: The original exception if this wraps another error.
    """

    def __init__(
        self,
        message: Optional[str],
        category: ErrorCategory = ErrorCategory.SYSTEM,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        context: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None,
        original: Optional[Exception] = None
    ) -> None:
        """Initialize CLI error with metadata.

        Args:
            message: Human-readable error message. None is converted to "".
            category: Error category for classification and routing.
            severity: Error severity for logging level determination.
            context: Additional context data as key-value pairs.
            suggestion: Optional actionable suggestion for the user.
            original: Original exception if wrapping another error.

        State Changes:
            Sets all instance attributes and establishes exception chain
            via __cause__ if original is provided.
        """
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
        """Return string representation of the error.

        Returns:
            The error message, or empty string if message is None/empty.
        """
        return self.message if self.message else ""

    def __repr__(self) -> str:
        """Return debug representation of the error.

        Returns:
            Class name with message, e.g., "CLIError('message')".
        """
        return f"{self.__class__.__name__}({self.message!r})"

    @property
    def suggestion(self) -> str:
        """Get actionable suggestion for resolving this error.

        Returns:
            Custom suggestion if provided during initialization, otherwise
            a default suggestion for the error type.
        """
        if self._suggestion:
            return self._suggestion
        return "Try again or check the operation parameters."

    @property
    def log_level(self) -> int:
        """Map error severity to Python logging level.

        Returns:
            Logging level constant (logging.INFO, WARNING, ERROR, or CRITICAL).
            Defaults to logging.ERROR if severity is not recognized.
        """
        mapping = {
            ErrorSeverity.INFO: logging.INFO,
            ErrorSeverity.WARNING: logging.WARNING,
            ErrorSeverity.ERROR: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL,
        }
        return mapping.get(self.severity, logging.ERROR)

    @property
    def recovery_action(self) -> RecoveryAction:
        """Get suggested recovery action for this error.

        Returns:
            RecoveryAction enum value. Base CLIError returns ASK_USER;
            subclasses may override with more specific actions.
        """
        return RecoveryAction.ASK_USER

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for structured logging.

        Serializes the error to a JSON-compatible dictionary, converting
        non-serializable context values to strings.

        Returns:
            Dict with keys: message, category, severity, context.
            Category and severity are converted to their enum names.
        """
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
        """Get extra data for structured logging.

        Returns:
            Dict with error_type (class name) and category for use
            as extra fields in logging calls.
        """
        return {
            "error_type": self.__class__.__name__,
            "category": self.category.name if hasattr(self.category, 'name') else str(self.category),
        }


class ValidationError(CLIError):
    """Exception for input validation failures.

    Raised when user input or configuration values fail validation checks.

    Attributes:
        field: Name of the field that failed validation, if applicable.
        value: The invalid value that was provided.
    """

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Any = None,
        **kwargs
    ) -> None:
        """Initialize validation error.

        Args:
            message: Human-readable description of the validation failure.
            field: Name of the field that failed validation.
            value: The invalid value that was provided.
            **kwargs: Additional arguments passed to CLIError.__init__.

        State Changes:
            Sets field and value attributes. Category defaults to VALIDATION.
        """
        kwargs.setdefault('category', ErrorCategory.VALIDATION)
        super().__init__(message, **kwargs)
        self.field = field
        self.value = value

    @property
    def suggestion(self) -> str:
        """Get validation-specific suggestion.

        Returns:
            Suggestion mentioning the specific field if available,
            otherwise a generic format suggestion.
        """
        if self._suggestion:
            return self._suggestion
        if self.field:
            return f"Check the value for '{self.field}' and ensure it's in the correct format."
        return "Verify the input value is in the expected format."

    def __repr__(self) -> str:
        """Return debug representation with field info.

        Returns:
            String like "ValidationError('message', field='fieldname')".
        """
        return f"ValidationError({self.message!r}, field={self.field!r})"


class ProviderError(CLIError):
    """Exception for API/provider failures.

    Raised when an API provider (OpenAI, Anthropic, etc.) returns an error
    or fails to respond. Includes metadata about the failure type for
    determining retry and fallback strategies.

    Attributes:
        provider: Name of the provider that failed.
        rate_limited: True if failure was due to rate limiting.
        is_timeout: True if failure was due to timeout.
        is_auth_error: True if failure was due to authentication.
    """

    def __init__(
        self,
        message: str,
        provider: str = "unknown",
        rate_limited: bool = False,
        is_timeout: bool = False,
        is_auth_error: bool = False,
        original: Optional[Exception] = None,
        **kwargs
    ) -> None:
        """Initialize provider error.

        Args:
            message: Human-readable description of the provider failure.
            provider: Name of the provider that failed (e.g., "openai").
            rate_limited: True if error was due to rate limiting.
            is_timeout: True if error was due to request timeout.
            is_auth_error: True if error was due to authentication failure.
            original: Original exception from the provider SDK.
            **kwargs: Additional arguments passed to CLIError.__init__.

        State Changes:
            Sets provider-specific attributes. Category defaults to API.
        """
        kwargs.setdefault('category', ErrorCategory.API)
        super().__init__(message, original=original, **kwargs)
        self.provider = provider
        self.rate_limited = rate_limited
        self.is_timeout = is_timeout
        self.is_auth_error = is_auth_error

    @property
    def is_retryable(self) -> bool:
        """Check if this error can be retried.

        Returns:
            True if the error is transient (rate limit, timeout) and can
            be retried. False for auth errors and other permanent failures.
        """
        if self.is_auth_error:
            return False
        return self.rate_limited or self.is_timeout or not self.is_auth_error

    @property
    def suggestion(self) -> str:
        """Get provider-specific recovery suggestion.

        Returns:
            Actionable suggestion based on error type (rate limit, timeout,
            auth, or generic provider failure).
        """
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
        """Get suggested recovery action based on error type.

        Returns:
            ABORT for auth errors (non-recoverable),
            RETRY for rate limits/timeouts,
            FALLBACK for other provider errors.
        """
        if self.is_auth_error:
            return RecoveryAction.ABORT
        if self.rate_limited or self.is_timeout:
            return RecoveryAction.RETRY
        return RecoveryAction.FALLBACK

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary including provider metadata.

        Returns:
            Dict with base fields plus provider, rate_limited,
            is_timeout, and is_auth_error.
        """
        result = super().to_dict()
        result["provider"] = self.provider
        result["rate_limited"] = self.rate_limited
        result["is_timeout"] = self.is_timeout
        result["is_auth_error"] = self.is_auth_error
        return result

    def logging_extra(self) -> Dict[str, Any]:
        """Get extra logging data including provider info.

        Returns:
            Dict with base fields plus provider, rate_limited, and is_timeout.
        """
        extra = super().logging_extra()
        extra["provider"] = self.provider
        extra["rate_limited"] = self.rate_limited
        extra["is_timeout"] = self.is_timeout
        return extra


class FileOperationError(CLIError):
    """Exception for file system operation failures.

    Raised when file operations (read, write, delete, etc.) fail due to
    missing files, permission issues, or other OS-level errors.

    Attributes:
        path: Path to the file that caused the error.
        operation: Name of the operation that failed (e.g., "read", "write").
    """

    def __init__(
        self,
        message: str,
        path: Optional[Path] = None,
        operation: Optional[str] = None,
        original: Optional[Exception] = None,
        **kwargs
    ) -> None:
        """Initialize file operation error.

        Args:
            message: Human-readable description of the file operation failure.
            path: Path to the file that caused the error.
            operation: Name of the operation that failed.
            original: Original OS-level exception.
            **kwargs: Additional arguments passed to CLIError.__init__.

        State Changes:
            Sets path, operation, and _is_permission_error attributes.
            Category defaults to FILE.
        """
        kwargs.setdefault('category', ErrorCategory.FILE)
        super().__init__(message, original=original, **kwargs)
        self.path = path
        self.operation = operation
        self._is_permission_error = isinstance(original, PermissionError)

    @classmethod
    def from_os_error(cls, error: Exception, path: Path) -> 'FileOperationError':
        """Create FileOperationError from OS-level error.

        Factory method that creates an appropriate error message based on
        the type of OS error encountered.

        Args:
            error: The original OS exception (FileNotFoundError, PermissionError, etc.).
            path: Path to the file that caused the error.

        Returns:
            FileOperationError with appropriate message and metadata.
        """
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
        """Get file-operation-specific suggestion.

        Returns:
            Permission-specific suggestion if applicable, otherwise
            generic path accessibility suggestion.
        """
        if self._suggestion:
            return self._suggestion
        if self._is_permission_error:
            return "Check that you have permission to access this file."
        return "Check that the path exists and is accessible."


class SessionError(CLIError):
    """Exception for session management failures.

    Raised when session operations (save, load, clear) fail due to
    file system issues, corruption, or other session-related problems.

    Attributes:
        operation: Name of the session operation that failed.
        session_path: Path to the session file, if applicable.
    """

    def __init__(
        self,
        message: str,
        operation: str = "unknown",
        session_path: Optional[Path] = None,
        **kwargs
    ) -> None:
        """Initialize session error.

        Args:
            message: Human-readable description of the session failure.
            operation: Name of the operation that failed (e.g., "save", "load").
            session_path: Path to the session file that caused the error.
            **kwargs: Additional arguments passed to CLIError.__init__.

        State Changes:
            Sets operation and session_path attributes.
        """
        super().__init__(message, **kwargs)
        self.operation = operation
        self.session_path = session_path


class TaskExecutionError(CLIError):
    """Exception for task execution failures.

    Raised when a task fails during execution, potentially with partial
    results that can be used for recovery or reporting.

    Attributes:
        task_name: Name or identifier of the task that failed.
        partial_result: Any partial results obtained before failure.
    """

    def __init__(
        self,
        message: str,
        task_name: str = "unknown",
        partial_result: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        """Initialize task execution error.

        Args:
            message: Human-readable description of the task failure.
            task_name: Name or identifier of the task that failed.
            partial_result: Any partial results obtained before the failure.
            **kwargs: Additional arguments passed to CLIError.__init__.

        State Changes:
            Sets task_name and partial_result attributes.
            Category defaults to TASK.
        """
        kwargs.setdefault('category', ErrorCategory.TASK)
        super().__init__(message, **kwargs)
        self.task_name = task_name
        self.partial_result = partial_result


class ParseError(CLIError):
    """Exception for parsing failures.

    Raised when content parsing fails (JSON, YAML, markdown, etc.) due to
    malformed input or unexpected format.

    Attributes:
        source: Identifier for the source being parsed (file path, URL, etc.).
        content_preview: Preview of the content that failed to parse.
    """

    def __init__(
        self,
        message: str,
        source: str = "unknown",
        content_preview: Optional[str] = None,
        original: Optional[Exception] = None,
        **kwargs
    ) -> None:
        """Initialize parse error.

        Args:
            message: Human-readable description of the parsing failure.
            source: Identifier for the source being parsed.
            content_preview: Preview of the malformed content for debugging.
            original: Original parsing exception (e.g., json.JSONDecodeError).
            **kwargs: Additional arguments passed to CLIError.__init__.

        State Changes:
            Sets source and content_preview attributes.
            Category defaults to PARSE.
        """
        kwargs.setdefault('category', ErrorCategory.PARSE)
        super().__init__(message, original=original, **kwargs)
        self.source = source
        self.content_preview = content_preview

    @classmethod
    def from_json_error(cls, error: Exception, source: str) -> 'ParseError':
        """Create ParseError from JSON decode error.

        Factory method for creating parse errors from JSON parsing failures.

        Args:
            error: The JSON decode exception.
            source: Identifier for the source being parsed.

        Returns:
            ParseError with message from the original error.
        """
        return cls(
            message=str(error),
            source=source,
            original=error
        )


class UserInputError(CLIError):
    """Exception for user input failures.

    Raised when user input operations fail due to interruption (Ctrl+C),
    end of input (Ctrl+D), or other input-related issues.

    Attributes:
        interrupted: True if input was interrupted by user (KeyboardInterrupt).
        eof: True if end-of-file was reached (EOFError).
    """

    def __init__(
        self,
        message: str,
        interrupted: bool = False,
        eof: bool = False,
        **kwargs
    ) -> None:
        """Initialize user input error.

        Args:
            message: Human-readable description of the input failure.
            interrupted: True if user pressed Ctrl+C.
            eof: True if user pressed Ctrl+D or input stream ended.
            **kwargs: Additional arguments passed to CLIError.__init__.

        State Changes:
            Sets interrupted and eof attributes.
            Category defaults to USER_INPUT.
        """
        kwargs.setdefault('category', ErrorCategory.USER_INPUT)
        super().__init__(message, **kwargs)
        self.interrupted = interrupted
        self.eof = eof
