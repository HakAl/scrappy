"""
CLI-specific exceptions.

Errors related to user interaction, file operations, sessions, and tasks.
"""

from typing import Optional, Any
from pathlib import Path
from infrastructure.exceptions.base import BaseError, NonRetryableError
from infrastructure.exceptions.enums import (
    ErrorCategory,
    ErrorSeverity,
    RecoveryAction
)


class CLIError(BaseError):
    """Base for CLI-related errors."""

    default_category = ErrorCategory.SYSTEM


class ValidationError(NonRetryableError):
    """User input validation error."""

    default_category = ErrorCategory.VALIDATION
    default_severity = ErrorSeverity.WARNING
    default_recovery_action = RecoveryAction.ASK_USER

    def __init__(
        self,
        message: str,
        field_name: Optional[str] = None,
        field_value: Optional[Any] = None,
        **kwargs: Any
    ):
        """Initialize validation error.

        Args:
            message: Error message
            field_name: Name of field that failed validation
            field_value: Invalid value
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        context.update({
            'field_name': field_name,
            'field_value': field_value,
        })

        super().__init__(
            message,
            context=context,
            **kwargs
        )
        self.field_name = field_name
        self.field_value = field_value


class FileOperationError(BaseError):
    """File system operation error."""

    default_category = ErrorCategory.FILE
    default_severity = ErrorSeverity.ERROR

    def __init__(
        self,
        message: str,
        file_path: Optional[Path] = None,
        operation: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize file operation error.

        Args:
            message: Error message
            file_path: Path to file that caused error
            operation: Operation that failed (read, write, delete, etc.)
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        context.update({
            'file_path': str(file_path) if file_path else None,
            'operation': operation,
        })

        suggestion = kwargs.pop('suggestion', None)
        if not suggestion and file_path:
            if operation == 'read':
                suggestion = f"Check that {file_path} exists and is readable."
            elif operation == 'write':
                suggestion = f"Check that {file_path} is writable and disk has space."
            elif operation == 'delete':
                suggestion = f"Check that {file_path} exists and you have permissions."

        super().__init__(
            message,
            context=context,
            suggestion=suggestion,
            **kwargs
        )
        self.file_path = file_path
        self.operation = operation


class SessionError(BaseError):
    """Session management error."""

    default_category = ErrorCategory.SYSTEM
    default_severity = ErrorSeverity.WARNING

    def __init__(
        self,
        message: str,
        session_id: Optional[str] = None,
        operation: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize session error.

        Args:
            message: Error message
            session_id: Session that had the error
            operation: Operation that failed (load, save, restore, etc.)
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        context.update({
            'session_id': session_id,
            'operation': operation,
        })

        super().__init__(
            message,
            context=context,
            **kwargs
        )
        self.session_id = session_id
        self.operation = operation


class TaskExecutionError(BaseError):
    """Task execution error."""

    default_category = ErrorCategory.TASK
    default_severity = ErrorSeverity.ERROR

    def __init__(
        self,
        message: str,
        task_name: Optional[str] = None,
        task_id: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize task execution error.

        Args:
            message: Error message
            task_name: Name of task that failed
            task_id: ID of task that failed
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        context.update({
            'task_name': task_name,
            'task_id': task_id,
        })

        super().__init__(
            message,
            context=context,
            **kwargs
        )
        self.task_name = task_name
        self.task_id = task_id


class ParseError(NonRetryableError):
    """Parsing error (JSON, YAML, etc.)."""

    default_category = ErrorCategory.PARSE
    default_severity = ErrorSeverity.ERROR

    def __init__(
        self,
        message: str,
        filename: Optional[str] = None,
        content_preview: Optional[str] = None,
        line_number: Optional[int] = None,
        **kwargs: Any
    ):
        """Initialize parse error.

        Args:
            message: Error message
            filename: File that failed to parse
            content_preview: Preview of content that failed
            line_number: Line number where parsing failed
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        context.update({
            'filename': filename,
            'content_preview': content_preview,
            'line_number': line_number,
        })

        super().__init__(
            message,
            context=context,
            **kwargs
        )
        self.filename = filename
        self.content_preview = content_preview
        self.line_number = line_number


class UserInputError(NonRetryableError):
    """Invalid user input error."""

    default_category = ErrorCategory.USER_INPUT
    default_severity = ErrorSeverity.WARNING
    default_recovery_action = RecoveryAction.ASK_USER

    def __init__(
        self,
        message: str,
        input_value: Optional[str] = None,
        expected_format: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize user input error.

        Args:
            message: Error message
            input_value: Invalid input provided
            expected_format: Description of expected format
            **kwargs: Additional BaseError arguments
        """
        context = kwargs.pop('context', {})
        context.update({
            'input_value': input_value,
            'expected_format': expected_format,
        })

        suggestion = kwargs.pop('suggestion', None)
        if not suggestion and expected_format:
            suggestion = f"Expected format: {expected_format}"

        super().__init__(
            message,
            context=context,
            suggestion=suggestion,
            **kwargs
        )
        self.input_value = input_value
        self.expected_format = expected_format
