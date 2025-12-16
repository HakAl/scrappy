"""
Consistent error handling utilities for CLI operations.

This module provides a unified approach to error handling across the CLI,
ensuring consistent user messaging, appropriate styling, and actionable
suggestions for common error types.
"""

from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Optional, Tuple, Union, Dict, Type
import json
import traceback

from ..io_interface import CLIIOProtocol
from ..validators import is_empty_or_whitespace


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


# Descriptive messages for common exception types when the message is empty
_EXCEPTION_DESCRIPTIONS: Dict[Type[Exception], str] = {
    ConnectionError: "Could not connect to the server",
    TimeoutError: "The request timed out",
    PermissionError: "Permission denied",
    FileNotFoundError: "File not found",
    FileExistsError: "File already exists",
    IsADirectoryError: "Expected a file but found a directory",
    NotADirectoryError: "Expected a directory but found a file",
    json.JSONDecodeError: "Failed to parse JSON response",
    KeyError: "Required data field is missing",
    ValueError: "Invalid value provided",
    TypeError: "Unexpected data type",
    AttributeError: "Missing required attribute",
    ImportError: "Required module not available",
    ModuleNotFoundError: "Required module not installed",
    RuntimeError: "Operation failed unexpectedly",
    OSError: "System operation failed",
    IOError: "Input/output operation failed",
    MemoryError: "Out of memory",
    RecursionError: "Operation nested too deeply",
    StopIteration: "No more items available",
    UnicodeDecodeError: "Failed to decode text (encoding issue)",
    UnicodeEncodeError: "Failed to encode text (encoding issue)",
}


def _get_descriptive_message(exception: Exception) -> str:
    """
    Get a descriptive message for an exception type.

    Args:
        exception: The exception to describe

    Returns:
        A human-readable description of the error
    """
    exception_type = type(exception)

    # Check exact type match first
    if exception_type in _EXCEPTION_DESCRIPTIONS:
        return _EXCEPTION_DESCRIPTIONS[exception_type]

    # Check parent classes
    for exc_class, description in _EXCEPTION_DESCRIPTIONS.items():
        if isinstance(exception, exc_class):
            return description

    # Check exception type name for common patterns
    type_name = exception_type.__name__

    if "Auth" in type_name:
        return "Authentication failed"
    if "Rate" in type_name or "Limit" in type_name:
        return "Rate limit exceeded"
    if "Timeout" in type_name:
        return "Request timed out"
    if "Connection" in type_name or "Network" in type_name:
        return "Network connection failed"
    if "Permission" in type_name or "Access" in type_name:
        return "Access denied"
    if "NotFound" in type_name:
        return "Resource not found"
    if "Invalid" in type_name:
        return "Invalid input provided"
    if "Context" in type_name and "Window" in type_name:
        return "Input too long for model context window"

    # Fallback: use type name converted to readable form
    # e.g., "APIConnectionError" -> "API connection error"
    import re
    readable = re.sub(r'([A-Z])', r' \1', type_name).strip()
    readable = readable.replace('Error', '').strip()
    if readable:
        return f"{readable} error occurred"

    return "An unexpected error occurred"


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
        return "An unexpected error occurred. Please try again."

    # Get the error message
    message = str(exception)

    # Handle empty or very short messages - extract more context
    if is_empty_or_whitespace(message):
        # Try to get context from chained exceptions
        if exception.__cause__:
            cause_msg = str(exception.__cause__)
            if not is_empty_or_whitespace(cause_msg):
                message = f"{_get_descriptive_message(exception)}: {cause_msg}"
            else:
                message = f"{_get_descriptive_message(exception)} (caused by {type(exception.__cause__).__name__})"
        elif exception.__context__:
            ctx_msg = str(exception.__context__)
            if not is_empty_or_whitespace(ctx_msg):
                message = f"{_get_descriptive_message(exception)}: {ctx_msg}"
            else:
                message = _get_descriptive_message(exception)
        else:
            # Use descriptive message based on exception type
            message = _get_descriptive_message(exception)
    elif len(message) <= 5:
        # Very short messages need more context
        message = f"{_get_descriptive_message(exception)}: {message}"

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
    # Check for rich exceptions with built-in suggestions first
    if hasattr(exception, 'suggestion') and exception.suggestion:
        return exception.suggestion

    # Get error message for pattern matching
    error_msg = str(exception).lower()
    exception_type = type(exception).__name__

    # API key / Authentication issues
    if any(pattern in error_msg for pattern in ['api key', 'api_key', 'apikey', 'invalid key', 'unauthorized', '401', 'authentication']):
        return "Check your API key is set correctly in .env file."
    if any(pattern in error_msg for pattern in ['forbidden', '403', 'access denied']):
        return "Your API key may not have permission for this operation."
    if 'Auth' in exception_type:
        return "Check your API key is set correctly in .env file."

    # Rate limiting
    if any(pattern in error_msg for pattern in ['rate limit', 'rate_limit', 'ratelimit', '429', 'quota', 'too many requests']):
        return "Wait a few seconds before retrying, or try a different provider."
    if 'Rate' in exception_type or 'Limit' in exception_type:
        return "Wait a few seconds before retrying, or try a different provider."

    # Network / Connection issues
    if any(pattern in error_msg for pattern in ['connect', 'connection', 'network', 'unreachable', 'refused']):
        return "Check your internet connection and try again."
    if any(pattern in error_msg for pattern in ['timeout', 'timed out', 'deadline']):
        return "The request timed out. The server may be slow - try again."
    if 'Timeout' in exception_type or 'Connection' in exception_type or 'Network' in exception_type:
        return "Check your internet connection and try again."

    # Context window / Token limits
    if any(pattern in error_msg for pattern in ['context length', 'context window', 'token limit', 'max tokens', 'too long']):
        return "Your input is too long. Try a shorter prompt or split into parts."
    if 'Context' in exception_type and 'Window' in exception_type:
        return "Your input is too long. Try a shorter prompt or split into parts."

    # Model not found
    if any(pattern in error_msg for pattern in ['model not found', 'unknown model', 'invalid model']):
        return "Check the model name is correct. Run '/providers' to see available models."

    # Provider not available
    if any(pattern in error_msg for pattern in ['provider', 'no providers', 'all providers']):
        return "No providers available. Run '/providers' to check API key configuration."

    # File-related errors
    if isinstance(exception, FileNotFoundError):
        return "Check that the file path exists and is spelled correctly."
    if isinstance(exception, PermissionError):
        return "Check you have the necessary permissions for this operation."
    if isinstance(exception, IsADirectoryError):
        return "Expected a file but found a directory. Check the path."
    if isinstance(exception, NotADirectoryError):
        return "Expected a directory but found a file. Check the path."

    # JSON parsing errors
    if isinstance(exception, json.JSONDecodeError):
        return "The response format was unexpected. This may be a temporary issue - try again."

    # KeyError suggestions
    if isinstance(exception, KeyError):
        return "Required data is missing. The API response may have changed."

    # ValueError suggestions
    if isinstance(exception, ValueError):
        return "Check that the input value is in the expected format."

    # Import errors
    if isinstance(exception, (ImportError, ModuleNotFoundError)):
        return "A required package may be missing. Try: pip install -e ."

    # Memory errors
    if isinstance(exception, MemoryError):
        return "Not enough memory. Try closing other applications or using a smaller input."

    # Context-specific suggestions
    if context:
        if 'index' in context.lower():
            return "Try re-indexing with '/reindex' command."
        if 'session' in context.lower():
            return "Try clearing the session with '/clear' command."

    # Generic but still helpful suggestion
    return "If the issue persists, try '/clear' to reset or check the logs for details."


def handle_error(
    exception: Optional[Exception],
    io: CLIIOProtocol,
    severity: ErrorSeverity = ErrorSeverity.ERROR,
    context: Optional[str] = None,
    show_suggestion: bool = True
) -> None:
    """
    Display an error message with appropriate styling and suggestions.

    Args:
        exception: The exception to handle
        io: IO interface for output
        severity: Error severity level
        context: Optional context about the operation
        show_suggestion: Whether to show actionable suggestions
    """
    if exception is None:
        message = "An unexpected error occurred. Please try again."
        suggestion = None
    else:
        message = format_error(exception)
        suggestion = get_error_suggestion(exception, context) if show_suggestion else None

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

    # Show suggestion if available and not redundant with message
    if suggestion and suggestion.lower() not in message.lower():
        io.echo(f"Suggestion: {suggestion}")


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

    io.secho(message, fg=io.theme.error)
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

    io.secho(message, fg=io.theme.error)


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
    io.secho(message, fg=io.theme.error)


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
    io.secho(message, fg=io.theme.error)


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
    io.secho(message, fg=io.theme.error)

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

    io.secho(output, fg=io.theme.error)

    if value is not None:
        io.echo(f"Invalid value: {value}")
