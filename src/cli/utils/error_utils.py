"""
Error handling utilities for CLI commands.

Provides consolidated error handling patterns to eliminate duplication
across command handlers.
"""

import sys
from typing import Any, Callable, TypeVar

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
    io.secho(f"Error: {error_message}", fg="red")
    return exit_code


def run_with_error_handling(
    io: Any,
    func: Callable[[], T],
    exit_code: int = 1
) -> T:
    """
    Run a function with standardized error handling.

    Wraps a function call with try/except that:
    - Catches exceptions and displays them
    - Handles KeyboardInterrupt gracefully
    - Calls sys.exit with appropriate code

    Args:
        io: IO interface for output
        func: Function to execute (no arguments)
        exit_code: Exit code on error (default 1)

    Returns:
        The function's return value on success

    Raises:
        SystemExit: On any error or keyboard interrupt
    """
    try:
        return func()
    except KeyboardInterrupt:
        io.secho("\nOperation interrupted by user.", fg="yellow")
        sys.exit(exit_code)
    except Exception as e:
        handle_command_error(io, e, exit_code)
        sys.exit(exit_code)
