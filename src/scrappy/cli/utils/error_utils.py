"""
Error handling utilities for CLI commands.

Provides consolidated error handling patterns to eliminate duplication
across command handlers.
"""

import sys
from typing import Any, Callable, Optional, TypeVar

from ..exceptions import (
    CLIError,
    ProviderError,
    ValidationError,
    FileOperationError,
    UserInputError,
)
from ..error_recovery import (
    retry_operation,
    graceful_degrade,
    error_recovery_context,
)
from ..logging import get_logger

T = TypeVar('T')


def handle_command_error(io: Any, error: Exception, exit_code: int = 1) -> int:
    """
    Handle and display a command error.

    Consolidates the error display pattern used across multiple commands:
        click.secho(f"Error: {e}", fg="red")
        sys.exit(1)

    Args:
        io: IO interface for output (CLIIOProtocol or click)
        error: The exception that occurred
        exit_code: Exit code to return (default 1)

    Returns:
        The exit code (for use with sys.exit or testing)
    """
    error_message = str(error) if str(error) else "Unknown error"

    # Handle CLI-specific exceptions with enhanced messaging
    if isinstance(error, CLIError):
        # Use severity-appropriate styling
        if error.severity.value >= 4:  # CRITICAL
            io.secho(f"Error: {error_message}", fg=io.theme.error, bold=True)
        else:
            io.secho(f"Error: {error_message}", fg=io.theme.error)

        # Show suggestion if available
        if error.suggestion:
            io.echo(f"Suggestion: {error.suggestion}")

        # Log structured data
        logger = get_logger("cli.error", io=io)
        logger.error(error_message, extra=error.logging_extra())
    else:
        io.secho(f"Error: {error_message}", fg=io.theme.error)

    return exit_code


def run_with_error_handling(
    io: Any,
    func: Callable[[], T],
    exit_code: int = 1,
    retry: bool = False,
    max_retries: int = 3
) -> T:
    """
    Run a function with standardized error handling.

    Wraps a function call with try/except that:
    - Catches exceptions and displays them
    - Handles KeyboardInterrupt gracefully
    - Optionally retries on transient failures
    - Calls sys.exit with appropriate code

    Args:
        io: IO interface for output
        func: Function to execute (no arguments)
        exit_code: Exit code on error (default 1)
        retry: Whether to retry on transient failures
        max_retries: Maximum retry attempts

    Returns:
        The function's return value on success

    Raises:
        SystemExit: On any error or keyboard interrupt
    """
    try:
        if retry:
            return retry_operation(func, max_retries=max_retries)
        return func()
    except KeyboardInterrupt:
        io.secho("\nOperation interrupted by user.", fg=io.theme.warning)
        sys.exit(exit_code)
    except UserInputError as e:
        if e.interrupted:
            io.secho("\nOperation interrupted by user.", fg=io.theme.warning)
        else:
            handle_command_error(io, e, exit_code)
        sys.exit(exit_code)
    except CLIError as e:
        handle_command_error(io, e, exit_code)
        sys.exit(exit_code)
    except Exception as e:
        handle_command_error(io, e, exit_code)
        sys.exit(exit_code)


def run_with_recovery(
    io: Any,
    func: Callable[[], T],
    fallback: Optional[Callable[[], T]] = None,
    retry: bool = False,
    max_retries: int = 3
) -> T:
    """
    Run a function with error recovery support.

    Provides graceful degradation and retry capabilities without exiting.

    Args:
        io: IO interface for output
        func: Function to execute
        fallback: Optional fallback function
        retry: Whether to retry on transient failures
        max_retries: Maximum retry attempts

    Returns:
        The function's return value or fallback result
    """
    if fallback:
        return graceful_degrade(
            func,
            on_error=lambda e: fallback(),
            io=io,
            degraded_message="Using fallback due to error."
        )

    if retry:
        try:
            return retry_operation(func, max_retries=max_retries)
        except ProviderError as e:
            handle_command_error(io, e)
            raise

    return func()


def with_error_context(
    io: Any,
    retry: bool = False,
    max_retries: int = 3,
    fallback: Optional[Callable] = None
):
    """
    Get an error recovery context manager.

    Usage:
        with with_error_context(io, retry=True) as ctx:
            result = risky_operation()
            ctx.result = result

        if ctx.had_error:
            handle_failure()

    Args:
        io: IO interface for output
        retry: Whether to enable retry logic
        max_retries: Maximum retry attempts
        fallback: Optional fallback function

    Returns:
        Error recovery context manager
    """
    return error_recovery_context(
        io=io,
        retry=retry,
        max_retries=max_retries,
        fallback=fallback
    )
