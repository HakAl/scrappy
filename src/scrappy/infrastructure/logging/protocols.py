"""
Protocols for structured logging infrastructure.

This module defines the contracts for logging components that can be used
across all layers of the application (CLI, orchestrator, agent).
"""

from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Protocol


class LoggerProtocol(Protocol):
    """
    Protocol for structured logger implementations.

    Provides both human-readable output and machine-parseable structured data
    with support for context binding and filtering.
    """

    name: str
    level: int

    def debug(self, message: str, *args, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log debug message with optional extra context."""
        ...

    def info(self, message: str, *args, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log info message with optional formatting args and extra context."""
        ...

    def warning(self, message: str, *args, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log warning message with optional formatting args and extra context."""
        ...

    def error(self, message: str, *args, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log error message with optional formatting args and extra context."""
        ...

    def critical(self, message: str, *args, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log critical message with optional formatting args and extra context."""
        ...

    def exception(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log exception with traceback."""
        ...

    def get_records(self) -> List[Dict[str, Any]]:
        """Get all stored log records."""
        ...

    def export_json(self) -> str:
        """Export all records as JSON string."""
        ...

    @contextmanager
    def context(self, **kwargs):
        """Context manager for adding context to all messages in scope."""
        ...

    def bind(self, **kwargs) -> 'LoggerProtocol':
        """Return logger with bound context."""
        ...

    def flush(self) -> None:
        """Flush any buffered output."""
        ...

    def close(self) -> None:
        """Close the logger and release any resources."""
        ...


class LoggerRegistryProtocol(Protocol):
    """
    Protocol for logger registry implementations.

    Manages logger instances and provides global configuration.
    """

    def get_logger(self, name: str, io: Optional[Any] = None) -> LoggerProtocol:
        """
        Get or create a logger by name.

        Args:
            name: Logger name
            io: IO interface (used only on first creation)

        Returns:
            Logger instance
        """
        ...

    def configure(self, level: int, io: Optional[Any] = None) -> None:
        """
        Configure default logging settings.

        Args:
            level: Default logging level
            io: Default IO interface
        """
        ...

    def reset(self) -> None:
        """Reset registry to initial state, clearing all loggers."""
        ...


class OutputInterfaceProtocol(Protocol):
    """
    Protocol for output interfaces that loggers can write to.

    This allows loggers to work with CLI output, console output,
    or any other output mechanism.
    """

    def echo(self, message: str) -> None:
        """Write plain message to output."""
        ...

    def secho(self, message: str, fg: Optional[str] = None, bold: bool = False) -> None:
        """Write styled message to output with color and formatting."""
        ...
