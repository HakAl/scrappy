"""
Logger registry for managing logger instances.

Provides centralized logger management with configuration support
and test isolation.
"""

import logging
from typing import Any, Dict, Optional

from .logger import StructuredLogger


class LoggerRegistry:
    """
    Registry for managing structured logger instances.

    Encapsulates logger storage and default configuration to avoid
    module-level global state. This enables:
    - Test isolation with separate registries
    - Easy reset of all loggers
    - Explicit dependency injection
    - Centralized configuration
    """

    def __init__(self):
        """Initialize registry with default values."""
        self._loggers: Dict[str, StructuredLogger] = {}
        self._default_io = None
        self._default_level = logging.INFO

    def get_logger(self, name: str, io: Optional[Any] = None) -> StructuredLogger:
        """
        Get or create a logger by name.

        Returns the same instance for the same name (singleton per name).

        Args:
            name: Logger name (typically module path like "orchestrator.core")
            io: IO interface (used only on first creation)

        Returns:
            StructuredLogger instance
        """
        if name not in self._loggers:
            effective_io = io or self._default_io
            self._loggers[name] = StructuredLogger(
                name=name,
                io=effective_io,
                level=self._default_level
            )

        return self._loggers[name]

    def configure(self, level: int = logging.INFO, io: Optional[Any] = None):
        """
        Configure default logging settings.

        Updates the registry defaults and all existing loggers.

        Args:
            level: Default logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            io: Default IO interface for output
        """
        self._default_io = io
        self._default_level = level

        # Update existing loggers
        for logger in self._loggers.values():
            logger.level = level
            if io:
                logger._io = io

    def reset(self):
        """
        Reset registry to initial state, clearing all loggers.

        Useful for test isolation - each test can start with a clean registry.
        """
        self._loggers = {}
        self._default_io = None
        self._default_level = logging.INFO


# Default global registry for convenience
_default_registry = LoggerRegistry()


def get_logger(name: str, io: Optional[Any] = None) -> StructuredLogger:
    """
    Get or create a logger by name using the default global registry.

    Returns the same instance for the same name.

    Args:
        name: Logger name (typically module path)
        io: IO interface (used only on first creation)

    Returns:
        StructuredLogger instance

    Example:
        logger = get_logger("orchestrator.core")
        logger.info("Operation started")
    """
    return _default_registry.get_logger(name, io)


def configure_logging(
    level: int = logging.INFO,
    io: Optional[Any] = None
):
    """
    Configure global logging settings.

    Updates the default global registry and all existing loggers.

    Args:
        level: Default logging level
        io: Default IO interface

    Example:
        configure_logging(level=logging.DEBUG, io=my_io)
    """
    _default_registry.configure(level, io)


def reset_logging():
    """
    Reset logging to initial state.

    Clears all loggers and resets defaults. Useful for test isolation.

    Example:
        def test_something():
            reset_logging()  # Start with clean state
            logger = get_logger("test")
            # ... test code ...
    """
    _default_registry.reset()
