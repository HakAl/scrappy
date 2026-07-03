"""
Structured logger implementation for multi-layer application logging.

Provides structured logging with context binding, filtering, and multiple
output targets (IO, files, structured JSON).
"""

import logging
import random
import sys
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional

from .formatters import safe_json_dumps


class StructuredLogger:
    """
    Structured logger with context binding and multiple output targets.

    Provides both human-readable colored output and structured JSON logging
    for machine parsing. Supports:
    - Context binding for request tracing
    - File rotation
    - Filtering by category
    - Sampling for high-volume logs
    - In-memory record storage
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
        categories: Optional[List[Any]] = None,
        sample_rate: float = 1.0
    ):
        """
        Initialize structured logger.

        Args:
            name: Logger name (typically module path)
            io: IO interface for output (must have echo/secho methods)
            level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            structured_only: Output only structured JSON
            format: Custom format string with {level} and {message} placeholders
            max_records: Maximum records to keep in memory
            log_file: Optional file path for file logging
            max_bytes: Max file size before rotation
            backup_count: Number of backup files to keep
            categories: Filter to only these categories (if provided in extra)
            sample_rate: Sampling rate (0.0 to 1.0) for high-volume logs
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
        """Set up rotating file handler for persistent logging."""
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
        """Check if message should be logged based on sampling rate."""
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
        """Create a structured log record."""
        # Get caller info (skip _create_record, _log, and calling method)
        frame = sys._getframe(3)
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

            # Extract extra from exceptions that provide logging_extra method
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
            msg = safe_json_dumps(record) + "\n"
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
                self._io.echo(safe_json_dumps(record))
            else:
                self._output_formatted(self._io, level_name, message)

    def _output_formatted(self, io: Any, level: str, message: str):
        """Output formatted message to the given (non-None) IO."""
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
            io.secho(output, fg=fg, bold=bold)
        else:
            io.echo(output)

    def debug(self, message: str, *args, extra: Optional[Dict[str, Any]] = None):
        """
        Log debug message.

        Supports lazy formatting for expensive operations - pass callables
        as args and they will only be invoked if debug logging is enabled.
        """
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

    def info(self, message: str, *args, extra: Optional[Dict[str, Any]] = None):
        """Log info message with optional formatting args."""
        if args:
            message = message % args
        self._log(logging.INFO, "INFO", message, extra)

    def warning(self, message: str, *args, extra: Optional[Dict[str, Any]] = None):
        """Log warning message with optional formatting args."""
        if args:
            message = message % args
        self._log(logging.WARNING, "WARNING", message, extra)

    def error(self, message: str, *args, extra: Optional[Dict[str, Any]] = None):
        """Log error message with optional formatting args."""
        if args:
            message = message % args
        self._log(logging.ERROR, "ERROR", message, extra)

    def critical(self, message: str, *args, extra: Optional[Dict[str, Any]] = None):
        """Log critical message with optional formatting args."""
        if args:
            message = message % args
        self._log(logging.CRITICAL, "CRITICAL", message, extra)

    def exception(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log exception with traceback."""
        exc_info = sys.exc_info()
        self._log(logging.ERROR, "ERROR", message, extra, exc_info)

    def log_with_severity(
        self,
        message: str,
        severity: Any,
        extra: Optional[Dict[str, Any]] = None
    ):
        """
        Log message with severity level.

        Compatible with ErrorSeverity enum from CLI error_handler.
        Accepts any enum-like object with INFO, WARNING, ERROR, CRITICAL values.

        Args:
            message: Log message
            severity: Severity level (enum with values 1-4)
            extra: Extra context
        """
        # Map severity values to logging levels
        # Works with any enum that has values 1=INFO, 2=WARNING, 3=ERROR, 4=CRITICAL
        level_map = {
            1: (logging.INFO, "INFO"),
            2: (logging.WARNING, "WARNING"),
            3: (logging.ERROR, "ERROR"),
            4: (logging.CRITICAL, "CRITICAL"),
        }
        # Handle enum-like objects by getting their value
        severity_value = severity.value if hasattr(severity, 'value') else severity
        level, level_name = level_map.get(severity_value, (logging.INFO, "INFO"))
        self._log(level, level_name, message, extra)

    def get_records(self) -> List[Dict[str, Any]]:
        """Get all stored log records."""
        return self._records

    def export_json(self) -> str:
        """Export all records as JSON string."""
        return safe_json_dumps(self._records)

    @contextmanager
    def context(self, **kwargs):
        """
        Context manager for adding context to all messages.

        Example:
            with logger.context(request_id="123", user="alice"):
                logger.info("Processing request")
                # Both messages will have request_id and user in extra
                logger.info("Request complete")
        """
        self._context_stack.append(kwargs)
        try:
            yield
        finally:
            self._context_stack.pop()

    def bind(self, **kwargs) -> 'StructuredLogger':
        """
        Return logger with bound context.

        Creates a new logger instance that shares records but has additional
        context bound to all messages.

        Example:
            request_logger = logger.bind(request_id="123")
            request_logger.info("Processing")  # Includes request_id in extra
        """
        # Create a new logger that shares records but has bound context
        bound = StructuredLogger(
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
