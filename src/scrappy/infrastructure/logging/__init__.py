"""
Infrastructure-level structured logging.

Provides structured logging that can be used across all application layers
(CLI, orchestrator, agent) with support for:
- Multiple output targets (IO, files, structured JSON)
- Context binding and request tracing
- Filtering and sampling
- File rotation
- Test isolation

Usage:
    from infrastructure.logging import get_logger, configure_logging

    # Configure global settings (optional)
    configure_logging(level=logging.DEBUG, io=my_io)

    # Get a logger
    logger = get_logger("my_module")

    # Log messages
    logger.info("Operation started")
    logger.error("Operation failed", extra={"operation_id": "123"})

    # Use context binding
    with logger.context(request_id="456"):
        logger.info("Processing request")

    # Bind context to logger instance
    request_logger = logger.bind(request_id="789")
    request_logger.info("Processing")
"""

# Main exports
from .logger import StructuredLogger
from .registry import LoggerRegistry, configure_logging, get_logger, reset_logging

# Formatters
from .formatters import SafeJSONEncoder, safe_json_dumps

# Protocols
from .protocols import (
    LoggerProtocol,
    LoggerRegistryProtocol,
    OutputInterfaceProtocol,
)

__all__ = [
    # Main logger and registry
    "StructuredLogger",
    "LoggerRegistry",
    "get_logger",
    "configure_logging",
    "reset_logging",
    # Formatters
    "SafeJSONEncoder",
    "safe_json_dumps",
    # Protocols
    "LoggerProtocol",
    "LoggerRegistryProtocol",
    "OutputInterfaceProtocol",
]
