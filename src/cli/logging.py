"""
Structured logging for CLI operations.

This module provides a logging system that outputs both human-readable
messages and structured data for machine parsing.
"""

import json
import logging
import random
import sys
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional

from .utils.error_handler import ErrorCategory, ErrorSeverity


class SafeJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles non-serializable types gracefully."""

    def default(self, obj):
        """Convert non-serializable objects to string representations."""
        # Handle datetime objects
        if isinstance(obj, datetime):
            return obj.isoformat()

        # Handle bytes
        if isinstance(obj, bytes):
            try:
                return obj.decode('utf-8')
            except UnicodeDecodeError:
                return f"<bytes: {len(obj)} bytes>"

        # Handle sets
        if isinstance(obj, set):
            return list(obj)

        # Handle Path objects
        if isinstance(obj, Path):
            return str(obj)

        # Handle functions/callables
        if callable(obj):
            return f"<{type(obj).__name__}: {getattr(obj, '__name__', 'anonymous')}>"

        # Handle objects with __dict__
        if hasattr(obj, '__dict__'):
            return f"<{type(obj).__name__}>"

        # Fallback: convert to string
        try:
            return str(obj)
        except Exception:
            return f"<non-serializable: {type(obj).__name__}>"


def _safe_json_dumps(obj: Any) -> str:
    """Safely serialize object to JSON string, handling non-serializable types."""
    try:
        return json.dumps(obj, cls=SafeJSONEncoder)
    except Exception as e:
        # Last resort fallback if even the custom encoder fails
        return json.dumps({
            "error": "serialization_failed",
            "error_message": str(e),
            "type": str(type(obj))
        })


class LoggerRegistry:
    """
    Registry for managing CLI loggers.

    Encapsulates logger storage and default configuration to avoid
    module-level global state. This enables:
    - Test isolation with separate registries
    - Easy reset of all loggers
    - Explicit dependency injection
    """

    def __init__(self):
        """Initialize registry with default values."""
        self._loggers: Dict[str, 'CLILogger'] = {}
        self._default_io = None
        self._default_level = logging.INFO

    def get_logger(self, name: str, io: Optional[Any] = None) -> 'CLILogger':
        """
        Get or create a logger by name.

        Returns the same instance for the same name.

        Args:
            name: Logger name
            io: IO interface (used only on first creation)

        Returns:
            CLILogger instance
        """
        if name not in self._loggers:
            effective_io = io or self._default_io
            self._loggers[name] = CLILogger(
                name=name,
                io=effective_io,
                level=self._default_level
            )

        return self._loggers[name]

    def configure(self, level: int = logging.INFO, io: Optional[Any] = None):
        """
        Configure default logging settings.

        Args:
            level: Default logging level
            io: Default IO interface
        """
        self._default_io = io
        self._default_level = level

        # Update existing loggers
        for logger in self._loggers.values():
            logger.level = level
            if io:
                logger._io = io

    def reset(self):
        """Reset registry to initial state, clearing all loggers."""
        self._loggers = {}
        self._default_io = None
        self._default_level = logging.INFO


# Default global registry for backward compatibility
_default_registry = LoggerRegistry()


class CLILogger:
    """
    CLI logger with structured output and IO integration.

    Provides both human-readable colored output and structured
    data logging for machine parsing.
    """

    def __init__(
        self,
        name: str,
        io: Optional[Any] = None,
        level: int = logging.INFO,
        structured_only: bool = False,
        format: Optional[str] = None,
        max_records: int = 1000,
        log_file: Optional[Path] = None,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
        categories: Optional[List[ErrorCategory]] = None,
        sample_rate: float = 1.0
    ):
        """
        Initialize CLI logger.

        Args:
            name: Logger name
            io: IO interface for output
            level: Logging level
            structured_only: Output only structured JSON
            format: Custom format string
            max_records: Maximum records to keep in memory
            log_file: Optional file path for file logging
            max_bytes: Max file size before rotation
            backup_count: Number of backup files to keep
            categories: Filter to only these categories
            sample_rate: Sampling rate (0.0 to 1.0)
        """
        self.name = name
        self._io = io
        # When sampling is enabled, default to DEBUG level to allow sampling all messages
        if sample_rate < 1.0 and level == logging.INFO:
            self.level = logging.DEBUG
        else:
            self.level = level
        self._structured_only = structured_only
        self._format = format
        self._max_records = max_records
        self._categories = categories
        self._sample_rate = sample_rate

        self._records: List[Dict[str, Any]] = []
        self._context_stack: List[Dict[str, Any]] = []
        self._bound_context: Dict[str, Any] = {}

        # File handler setup
        self._file_handler = None
        self._log_file = None
        if log_file:
            self._setup_file_handler(log_file, max_bytes, backup_count)

    def _setup_file_handler(self, log_file: Path, max_bytes: int, backup_count: int):
        """Set up rotating file handler."""
        log_file.parent.mkdir(parents=True, exist_ok=True)
        self._log_file = log_file
        self._file_handler = RotatingFileHandler(
            str(log_file),
            maxBytes=max_bytes,
            backupCount=backup_count,
            mode='a'
        )
        self._file_handler.setLevel(logging.DEBUG)

    def _should_log(self, level: int) -> bool:
        """Check if message should be logged based on level."""
        return level >= self.level

    def _should_sample(self) -> bool:
        """Check if message should be logged based on sampling."""
        if self._sample_rate >= 1.0:
            return True
        return random.random() < self._sample_rate

    def _get_current_context(self) -> Dict[str, Any]:
        """Get merged context from stack and bound context."""
        context = dict(self._bound_context)
        for ctx in self._context_stack:
            context.update(ctx)
        return context

    def _create_record(
        self,
        level: str,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        exc_info: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Create a log record."""
        # Get caller info
        frame = sys._getframe(3)  # Skip _create_record, _log, and method
        location = f"{frame.f_code.co_filename}:{frame.f_lineno}"

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
            "logger": self.name,
            "location": location,
            "file": frame.f_code.co_filename,
            "extra": {**self._get_current_context(), **(extra or {})}
        }

        if exc_info:
            record["exc_info"] = True
            record["traceback"] = "".join(traceback.format_exc())
            record["exception_type"] = type(exc_info[1]).__name__ if exc_info[1] else None

            # Extract extra from CLI exceptions
            if exc_info[1] and hasattr(exc_info[1], 'logging_extra'):
                for k, v in exc_info[1].logging_extra().items():
                    record["extra"][k] = v

        return record

    def _log(
        self,
        level: int,
        level_name: str,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        exc_info: Optional[Any] = None
    ):
        """Internal log method."""
        if not self._should_log(level):
            return

        # Check category filter
        if self._categories and extra:
            category = extra.get("category")
            if category and category not in self._categories:
                return

        # Check sampling
        if not self._should_sample():
            return

        # Create record
        record = self._create_record(level_name, message, extra, exc_info)

        # Store record (with limit)
        self._records.append(record)
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]

        # Output to file
        if self._file_handler:
            msg = _safe_json_dumps(record) + "\n"
            # Use emit-like behavior for proper rotation
            if self._file_handler.shouldRollover(logging.LogRecord(
                name=self.name, level=level, pathname="", lineno=0,
                msg=msg, args=(), exc_info=None
            )):
                self._file_handler.doRollover()
            self._file_handler.stream.write(msg)
            self._file_handler.stream.flush()

        # Output to IO
        if self._io:
            if self._structured_only:
                self._io.echo(_safe_json_dumps(record))
            else:
                self._output_formatted(level_name, message)

    def _output_formatted(self, level: str, message: str):
        """Output formatted message to IO."""
        # Determine color and style
        if level == "CRITICAL":
            fg = "red"
            bold = True
        elif level == "ERROR":
            fg = "red"
            bold = False
        elif level == "WARNING":
            fg = "yellow"
            bold = False
        else:
            fg = None
            bold = False

        # Format message
        if self._format:
            output = self._format.format(level=level, message=message)
        else:
            output = message

        if fg:
            self._io.secho(output, fg=fg, bold=bold)
        else:
            self._io.echo(output)

    def debug(self, message: str, *args, extra: Optional[Dict[str, Any]] = None):
        """Log debug message."""
        # Lazy formatting - only format if we'll actually log
        if not self._should_log(logging.DEBUG):
            return

        # Handle lazy args
        if args and callable(args[0]):
            # Don't call the function if not logging
            if self._should_log(logging.DEBUG):
                formatted_args = [arg() if callable(arg) else arg for arg in args]
                message = message % tuple(formatted_args)
        elif args:
            message = message % args

        self._log(logging.DEBUG, "DEBUG", message, extra)

    def info(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log info message."""
        self._log(logging.INFO, "INFO", message, extra)

    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log warning message."""
        self._log(logging.WARNING, "WARNING", message, extra)

    def error(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log error message."""
        self._log(logging.ERROR, "ERROR", message, extra)

    def critical(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log critical message."""
        self._log(logging.CRITICAL, "CRITICAL", message, extra)

    def exception(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log exception with traceback."""
        exc_info = sys.exc_info()
        self._log(logging.ERROR, "ERROR", message, extra, exc_info)

    def log_with_severity(
        self,
        message: str,
        severity: ErrorSeverity,
        extra: Optional[Dict[str, Any]] = None
    ):
        """Log message with ErrorSeverity level."""
        level_map = {
            ErrorSeverity.INFO: (logging.INFO, "INFO"),
            ErrorSeverity.WARNING: (logging.WARNING, "WARNING"),
            ErrorSeverity.ERROR: (logging.ERROR, "ERROR"),
            ErrorSeverity.CRITICAL: (logging.CRITICAL, "CRITICAL"),
        }
        level, level_name = level_map.get(severity, (logging.INFO, "INFO"))
        self._log(level, level_name, message, extra)

    def get_records(self) -> List[Dict[str, Any]]:
        """Get all stored log records."""
        return self._records

    def export_json(self) -> str:
        """Export all records as JSON string."""
        return _safe_json_dumps(self._records)

    @contextmanager
    def context(self, **kwargs):
        """Context manager for adding context to all messages."""
        self._context_stack.append(kwargs)
        try:
            yield
        finally:
            self._context_stack.pop()

    def bind(self, **kwargs) -> 'CLILogger':
        """Return logger with bound context."""
        # Create a new logger that shares records but has bound context
        bound = CLILogger(
            name=self.name,
            io=self._io,
            level=self.level,
            structured_only=self._structured_only,
            format=self._format,
            max_records=self._max_records
        )
        bound._records = self._records  # Share records
        bound._bound_context = {**self._bound_context, **kwargs}
        return bound

    def flush(self):
        """Flush any buffered output."""
        if self._file_handler:
            self._file_handler.flush()

    def close(self):
        """Close the logger and release any file handles."""
        if self._file_handler:
            self._file_handler.close()
            self._file_handler = None


def get_logger(name: str, io: Optional[Any] = None) -> CLILogger:
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
    """
    _default_registry.configure(level, io)


def reset_logging():
    """
    Reset logging to initial state.

    Clears all loggers and resets defaults. Useful for test isolation.
    """
    _default_registry.reset()
