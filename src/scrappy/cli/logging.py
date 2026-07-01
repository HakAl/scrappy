"""
Structured logging for CLI operations.

This module provides a logging system that outputs both human-readable
messages and structured data for machine parsing.

NOTE: This module now delegates to infrastructure.logging for the core
implementation. Imports are maintained for backward compatibility.
"""

# Import from infrastructure.logging
from scrappy.infrastructure.logging import (
    StructuredLogger,
    LoggerRegistry as InfraLoggerRegistry,
    SafeJSONEncoder,
)

# Backward compatibility aliases
CLILogger = StructuredLogger
LoggerRegistry = InfraLoggerRegistry


def _safe_json_dumps(obj):
    """Backward compatibility wrapper for safe_json_dumps."""
    from scrappy.infrastructure.logging import safe_json_dumps
    return safe_json_dumps(obj)


# Default global registry for backward compatibility
_default_registry = LoggerRegistry()


def get_logger(name: str, io=None):
    """
    Get or create a logger by name.

    Returns the same instance for the same name.
    Uses the default global registry.

    Args:
        name: Logger name
        io: IO interface (used only on first creation)

    Returns:
        CLILogger instance
    """
    return _default_registry.get_logger(name, io)


def configure_logging(level=None, io=None):
    """
    Configure global logging settings.

    Updates the default global registry and all existing loggers.

    Args:
        level: Default logging level
        io: Default IO interface
    """
    import logging
    if level is None:
        level = logging.INFO
    _default_registry.configure(level, io)


def reset_logging():
    """
    Reset logging to initial state.

    Clears all loggers and resets defaults. Useful for test isolation.
    """
    _default_registry.reset()


# Export everything for backward compatibility
__all__ = [
    "CLILogger",
    "LoggerRegistry",
    "SafeJSONEncoder",
    "get_logger",
    "configure_logging",
    "reset_logging",
]
