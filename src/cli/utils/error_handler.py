"""
Consistent error handling utilities for CLI operations.

This module provides a unified approach to error handling across the CLI,
ensuring consistent user messaging, appropriate styling, and actionable
suggestions for common error types.
"""

from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Optional, Tuple, Union
import json
import traceback

from ..io_interface import CLIIOProtocol


class ErrorSeverity(IntEnum):
    """Error severity levels for appropriate styling and handling."""
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4


class ErrorCategory(IntEnum):
    """Error categories for classification and suggestion generation."""
    VALIDATION = 1
    API = 2
    FILE = 3
    SYSTEM = 4
    PARSE = 5
    TASK = 6
    USER_INPUT = 7


def format_error(
    exception: Optional[Exception],
    include_traceback: bool = False
) -> str:
    """
    Convert an exception to a user-friendly error message.

    Args:
        exception: The exception to format
        include_traceback: Whether to include the full traceback

    Returns:
        A user-friendly error message string
    """
    if exception is None:
        return "Unknown error occurred"

    # Get the error message
    message = str(exception)

    # Handle empty or very short messages - add context
    if not message or message.strip() == "":
        message = f"Unknown error ({type(exception).__name__})"
    elif len(message) <= 5:
        # Very short messages need more context
        message = f"{type(exception).__name__}: {message}"

    # Include traceback if requested
    if include_traceback:
        tb = traceback.format_exception(type(exception), exception, exception.__traceback__)
        message = "".join(tb)

    # Truncate very long messages
    max_length = 500
    if len(message) > max_length:
        message = message[:max_length - 3] + "..."

    return message


def get_error_suggestion(
    exception: Exception,
    context: Optional[str] = None
) -> str:
    """
    Generate actionable suggestions for common error types.

    Args:
        exception: The exception to generate suggestions for
        context: Optional context about the operation

    Returns:
        An actionable suggestion string
    """
    exception_type = type(exception)

    # FileNotFoundError suggestions
    if isinstance(exception, FileNotFoundError):
        return "Check that the file path exists and is spelled correctly."

    # PermissionError suggestions
    if isinstance(exception, PermissionError):
        return "Verify you have the necessary permissions to access this resource."

    # ConnectionError suggestions
    if isinstance(exception, (ConnectionError, TimeoutError)):
        return "Check your network connection and try again."

    # JSON parsing errors
    if isinstance(exception, json.JSONDecodeError):
        return "Verify the JSON syntax is correct and properly formatted."

    # KeyError suggestions
    if isinstance(exception, KeyError):
        return "Check that the required key exists in the data."

    # ValueError suggestions
    if isinstance(exception, ValueError):
        return "Verify the input value is in the expected format."

    # Generic suggestion
    return "Try again or check the operation parameters."


def handle_error(
    exception: Optional[Exception],
    io: CLIIOProtocol,
    severity: ErrorSeverity = ErrorSeverity.ERROR,
    context: Optional[str] = None
) -> None:
    """
    Display an error message with appropriate styling.

    Args:
        exception: The exception to handle
        io: IO interface for output
        severity: Error severity level
        context: Optional context about the operation
    """
    if exception is None:
        message = "Unknown error occurred"
    else:
        message = format_error(exception)

    # Determine styling based on severity
    if severity == ErrorSeverity.CRITICAL:
        fg = "red"
        bold = True
    elif severity == ErrorSeverity.ERROR:
        fg = "red"
        bold = False
    elif severity == ErrorSeverity.WARNING:
        fg = "yellow"
        bold = False
    else:  # INFO
        fg = "cyan"
        bold = False

    # Build the output message
    if context:
        output = f"Error ({context}): {message}"
    else:
        output = f"Error: {message}"

    io.secho(output, fg=fg, bold=bold)


def safe_operation(
    func: Callable,
    *args,
    default_return: Any = None,
    io: Optional[CLIIOProtocol] = None,
    silent: bool = False,
    **kwargs
) -> Tuple[bool, Any]:
    """
    Safely execute an operation with error handling.

    Args:
        func: The function to execute
        *args: Positional arguments to pass to the function
        default_return: Value to return on failure
        io: Optional IO interface for error output
        silent: Whether to suppress error output
        **kwargs: Keyword arguments to pass to the function

    Returns:
        Tuple of (success: bool, result: Any)
    """
    try:
        result = func(*args, **kwargs)
        return True, result
    except Exception as e:
        # Output error if IO provided and not silent
        if io and not silent:
            handle_error(e, io)

        # Return default or the exception
        if default_return is not None:
            return False, default_return
        return False, e


def file_operation_error(
    io: CLIIOProtocol,
    error: Exception,
    path: Path
) -> None:
    """
    Handle file operation errors with appropriate messaging.

    Args:
        io: IO interface for output
        error: The exception that occurred
        path: The file path involved
    """
    path_str = str(path)

    if isinstance(error, FileNotFoundError):
        message = f"File not found: {path_str}"
        suggestion = get_error_suggestion(error)
    elif isinstance(error, PermissionError):
        message = f"Permission denied: {path_str}"
        suggestion = get_error_suggestion(error)
    else:
        message = f"File operation failed on {path_str}: {error}"
        suggestion = None

    io.secho(message, fg="red")
    if suggestion:
        io.echo(f"Suggestion: {suggestion}")


def api_delegation_error(
    io: CLIIOProtocol,
    error: Exception,
    provider: str
) -> None:
    """
    Handle API delegation errors with provider context.

    Args:
        io: IO interface for output
        error: The exception that occurred
        provider: The provider name
    """
    error_msg = str(error).lower()

    if isinstance(error, TimeoutError) or "timeout" in error_msg or "timed out" in error_msg:
        message = f"Request to {provider} timed out"
    elif "rate limit" in error_msg:
        message = f"Rate limit exceeded for {provider}"
    else:
        message = f"Error from {provider}: {error}"

    io.secho(message, fg="red")


def task_execution_error(
    io: CLIIOProtocol,
    error: Exception,
    task_name: str
) -> None:
    """
    Handle task execution errors.

    Args:
        io: IO interface for output
        error: The exception that occurred
        task_name: Name of the task that failed
    """
    message = f"Error during {task_name}: {error}"
    io.secho(message, fg="red")


def session_error(
    io: CLIIOProtocol,
    error: Exception,
    operation: str
) -> None:
    """
    Handle session operation errors.

    Args:
        io: IO interface for output
        error: The exception that occurred
        operation: The session operation (save/load)
    """
    message = f"Session {operation} failed: {error}"
    io.secho(message, fg="red")


def parse_error(
    io: CLIIOProtocol,
    error: Exception,
    filename: str,
    content_preview: Optional[str] = None
) -> None:
    """
    Handle parsing errors with context.

    Args:
        io: IO interface for output
        error: The exception that occurred
        filename: Name of the file being parsed
        content_preview: Optional preview of the content
    """
    message = f"Failed to parse {filename}: {error}"
    io.secho(message, fg="red")

    if content_preview:
        io.echo(f"Content preview: {content_preview}")


def validation_error(
    io: CLIIOProtocol,
    message: str,
    field: Optional[str] = None,
    value: Any = None
) -> None:
    """
    Handle validation errors with field context.

    Args:
        io: IO interface for output
        message: The validation error message
        field: Optional field name that failed validation
        value: Optional invalid value
    """
    if field:
        output = f"Validation error for '{field}': {message}"
    else:
        output = f"Validation error: {message}"

    io.secho(output, fg="red")

    if value is not None:
        io.echo(f"Invalid value: {value}")
