"""
Tests for infrastructure-level structured logging.

These tests prove that the logging infrastructure works correctly
across all application layers (CLI, orchestrator, agent).
"""

import pytest
import json
import logging
from pathlib import Path
from datetime import datetime

from src.infrastructure.logging import (
    StructuredLogger,
    LoggerRegistry,
    get_logger,
    configure_logging,
    reset_logging,
    SafeJSONEncoder,
    safe_json_dumps
)
from tests.helpers import MockIO


class TestStructuredLogger:
    """Test the main StructuredLogger class."""

    @pytest.mark.unit
    def test_logger_creation(self):
        """StructuredLogger should be created with name and io interface."""
        io = MockIO()
        logger = StructuredLogger("test_logger", io=io)

        assert logger.name == "test_logger"
        assert logger.level == logging.INFO

    @pytest.mark.unit
    def test_logger_outputs_to_io(self):
        """Logger should output to IO interface."""
        io = MockIO()
        logger = StructuredLogger("test", io=io)

        logger.info("Test message")

        output = io.get_output()
        assert "Test message" in output

    @pytest.mark.unit
    def test_logger_error_uses_red_color(self):
        """Error messages should use red color."""
        io = MockIO()
        logger = StructuredLogger("test", io=io)

        logger.error("Error message")

        styled = io.get_styled_outputs()
        assert any(s.get('fg') == 'red' for s in styled)

    @pytest.mark.unit
    def test_logger_warning_uses_yellow_color(self):
        """Warning messages should use yellow color."""
        io = MockIO()
        logger = StructuredLogger("test", io=io)

        logger.warning("Warning message")

        styled = io.get_styled_outputs()
        assert any(s.get('fg') == 'yellow' for s in styled)

    @pytest.mark.unit
    def test_logger_critical_uses_bold_red(self):
        """Critical messages should use bold red."""
        io = MockIO()
        logger = StructuredLogger("test", io=io)

        logger.critical("Critical message")

        styled = io.get_styled_outputs()
        assert any(s.get('fg') == 'red' and s.get('bold') for s in styled)

    @pytest.mark.unit
    def test_logger_debug_respects_level(self):
        """Debug messages should respect log level."""
        io = MockIO()
        logger = StructuredLogger("test", io=io, level=logging.INFO)

        logger.debug("Debug message")

        output = io.get_output()
        assert "Debug message" not in output


class TestStructuredOutput:
    """Test structured data output capabilities."""

    @pytest.mark.unit
    def test_logger_stores_structured_data(self):
        """Logger should store structured data in records."""
        io = MockIO()
        logger = StructuredLogger("test", io=io)

        logger.info("Operation completed", extra={
            "operation": "save",
            "duration_ms": 150,
            "items": 5
        })

        records = logger.get_records()
        assert len(records) > 0
        assert records[-1]["extra"]["operation"] == "save"
        assert records[-1]["extra"]["duration_ms"] == 150

    @pytest.mark.unit
    def test_logger_records_timestamp(self):
        """Logger should record timestamp for each message."""
        io = MockIO()
        logger = StructuredLogger("test", io=io)

        logger.info("Test")

        records = logger.get_records()
        assert "timestamp" in records[-1]

    @pytest.mark.unit
    def test_logger_records_level(self):
        """Logger should record log level for each message."""
        io = MockIO()
        logger = StructuredLogger("test", io=io)

        logger.warning("Test")

        records = logger.get_records()
        assert records[-1]["level"] == "WARNING"

    @pytest.mark.unit
    def test_logger_records_location(self):
        """Logger should record source location."""
        io = MockIO()
        logger = StructuredLogger("test", io=io)

        logger.info("Test")

        records = logger.get_records()
        assert "location" in records[-1]
        assert "file" in records[-1]

    @pytest.mark.unit
    def test_logger_export_to_json(self):
        """Logger should export records as JSON."""
        io = MockIO()
        logger = StructuredLogger("test", io=io)

        logger.info("Message 1", extra={"key": "value1"})
        logger.error("Message 2", extra={"key": "value2"})

        json_output = logger.export_json()
        data = json.loads(json_output)

        assert len(data) == 2
        assert data[0]["message"] == "Message 1"
        assert data[1]["level"] == "ERROR"


class TestExceptionLogging:
    """Test logging of exceptions with structured data."""

    @pytest.mark.unit
    def test_logger_exception_includes_traceback(self):
        """Logger should include traceback for exceptions."""
        io = MockIO()
        logger = StructuredLogger("test", io=io)

        try:
            raise ValueError("Test error")
        except ValueError:
            logger.exception("Operation failed")

        records = logger.get_records()
        assert "traceback" in records[-1] or "exc_info" in records[-1]

    @pytest.mark.unit
    def test_logger_exception_includes_type(self):
        """Logger should include exception type."""
        io = MockIO()
        logger = StructuredLogger("test", io=io)

        try:
            raise ValueError("Test")
        except ValueError:
            logger.exception("Failed")

        records = logger.get_records()
        assert "ValueError" in str(records[-1])


class TestLoggerConfiguration:
    """Test logger configuration options."""

    @pytest.mark.unit
    def test_logger_set_level(self):
        """Logger level should be configurable."""
        io = MockIO()
        logger = StructuredLogger("test", io=io, level=logging.WARNING)

        logger.info("Should not appear")
        logger.warning("Should appear")

        output = io.get_output()
        assert "Should not appear" not in output
        assert "Should appear" in output

    @pytest.mark.unit
    def test_logger_enable_structured_mode(self):
        """Logger should support structured-only mode for machine parsing."""
        io = MockIO()
        logger = StructuredLogger("test", io=io, structured_only=True)

        logger.info("Test message")

        output = io.get_output()
        data = json.loads(output.strip())
        assert data["message"] == "Test message"

    @pytest.mark.unit
    def test_logger_format_string(self):
        """Logger should support custom format strings."""
        io = MockIO()
        logger = StructuredLogger(
            "test",
            io=io,
            format="[{level}] {message}"
        )

        logger.info("Test message")

        output = io.get_output()
        assert "[INFO]" in output

    @pytest.mark.unit
    def test_logger_max_records(self):
        """Logger should limit stored records to prevent memory issues."""
        io = MockIO()
        logger = StructuredLogger("test", io=io, max_records=10)

        for i in range(20):
            logger.info(f"Message {i}")

        records = logger.get_records()
        assert len(records) <= 10


class TestContextManagement:
    """Test context management for structured logging."""

    @pytest.mark.unit
    def test_logger_with_context(self):
        """Logger should support context that applies to all messages."""
        io = MockIO()
        logger = StructuredLogger("test", io=io)

        with logger.context(operation="bulk_import", user="test_user"):
            logger.info("Step 1")
            logger.info("Step 2")

        records = logger.get_records()
        for record in records:
            assert record["extra"]["operation"] == "bulk_import"
            assert record["extra"]["user"] == "test_user"

    @pytest.mark.unit
    def test_logger_nested_context(self):
        """Logger should support nested contexts."""
        io = MockIO()
        logger = StructuredLogger("test", io=io)

        with logger.context(operation="import"):
            logger.info("Outer")
            with logger.context(step="validation"):
                logger.info("Inner")

        records = logger.get_records()
        assert records[1]["extra"]["operation"] == "import"
        assert records[1]["extra"]["step"] == "validation"

    @pytest.mark.unit
    def test_logger_bind_returns_new_logger(self):
        """bind() should return logger with bound context."""
        io = MockIO()
        logger = StructuredLogger("test", io=io)

        bound_logger = logger.bind(request_id="123")
        bound_logger.info("Test")

        records = logger.get_records()
        assert records[-1]["extra"]["request_id"] == "123"


class TestFileLogging:
    """Test file-based logging output."""

    @pytest.mark.unit
    def test_logger_writes_to_file(self, tmp_path):
        """Logger should write to file when configured."""
        log_file = tmp_path / "test.log"
        io = MockIO()
        logger = StructuredLogger("test", io=io, log_file=log_file)

        logger.info("Test message")
        logger.flush()

        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message" in content

        logger.close()

    @pytest.mark.unit
    def test_file_output_is_structured(self, tmp_path):
        """File output should be structured JSON lines."""
        log_file = tmp_path / "test.log"
        io = MockIO()
        logger = StructuredLogger("test", io=io, log_file=log_file)

        logger.info("Message 1", extra={"key": "value1"})
        logger.info("Message 2", extra={"key": "value2"})
        logger.flush()

        lines = log_file.read_text().strip().split('\n')
        for line in lines:
            data = json.loads(line)
            assert "message" in data

        logger.close()

    @pytest.mark.unit
    def test_logger_rotates_large_files(self, tmp_path):
        """Logger should rotate log files when they get too large."""
        log_file = tmp_path / "test.log"
        io = MockIO()

        logger = StructuredLogger(
            "test",
            io=io,
            log_file=log_file,
            max_bytes=1024,  # 1KB max size
            backup_count=3
        )

        # Write enough to trigger rotation
        for i in range(100):
            logger.info("X" * 50, extra={"i": i})

        logger.flush()

        # Should have created backup files
        log_files = list(tmp_path.glob("test.log*"))
        assert len(log_files) > 1

        logger.close()


class TestLoggerRegistry:
    """Test LoggerRegistry for managing logger instances."""

    @pytest.mark.unit
    def test_registry_get_logger_returns_same_instance(self):
        """Registry get_logger should return same instance for same name."""
        registry = LoggerRegistry()
        io = MockIO()

        logger1 = registry.get_logger("shared", io=io)
        logger2 = registry.get_logger("shared")

        assert logger1 is logger2

    @pytest.mark.unit
    def test_registry_configure_updates_existing_loggers(self):
        """Registry configure should update existing loggers."""
        registry = LoggerRegistry()
        io1 = MockIO()
        io2 = MockIO()

        logger = registry.get_logger("test", io=io1)
        assert logger.level == logging.INFO

        registry.configure(level=logging.DEBUG, io=io2)

        assert logger.level == logging.DEBUG

    @pytest.mark.unit
    def test_registry_reset_clears_all_state(self):
        """Registry reset should clear all loggers and defaults."""
        registry = LoggerRegistry()
        io = MockIO()

        registry.configure(level=logging.DEBUG, io=io)
        registry.get_logger("test1", io=io)
        registry.get_logger("test2", io=io)

        registry.reset()

        assert registry._loggers == {}
        assert registry._default_io is None
        assert registry._default_level == logging.INFO

    @pytest.mark.unit
    def test_separate_registries_are_isolated(self):
        """Separate registries should not affect each other."""
        registry1 = LoggerRegistry()
        registry2 = LoggerRegistry()
        io = MockIO()

        registry1.configure(level=logging.DEBUG, io=io)
        registry1.get_logger("test", io=io)

        # Registry2 should be unaffected
        assert registry2._loggers == {}
        assert registry2._default_level == logging.INFO


class TestModuleFunctions:
    """Test module-level convenience functions."""

    @pytest.mark.unit
    def test_get_logger_returns_configured_instance(self):
        """get_logger should return configured logger instance."""
        reset_logging()  # Start clean
        io = MockIO()

        logger = get_logger("my_module", io=io)

        assert logger.name == "my_module"

        reset_logging()  # Clean up

    @pytest.mark.unit
    def test_get_logger_returns_same_instance(self):
        """get_logger should return same instance for same name."""
        reset_logging()  # Start clean
        io = MockIO()

        logger1 = get_logger("shared", io=io)
        logger2 = get_logger("shared", io=io)

        assert logger1 is logger2

        reset_logging()  # Clean up

    @pytest.mark.unit
    def test_configure_all_loggers(self):
        """Should be able to configure all loggers at once."""
        reset_logging()  # Start clean
        io = MockIO()

        configure_logging(level=logging.DEBUG, io=io)

        logger = get_logger("test_module", io=io)
        assert logger.level <= logging.DEBUG

        reset_logging()  # Clean up


class TestJSONFormatters:
    """Test JSON formatting utilities."""

    @pytest.mark.unit
    def test_safe_json_handles_datetime(self):
        """safe_json_dumps should handle datetime objects."""
        data = {"timestamp": datetime.now()}

        result = safe_json_dumps(data)

        assert result is not None
        parsed = json.loads(result)
        assert "timestamp" in parsed

    @pytest.mark.unit
    def test_safe_json_handles_sets(self):
        """safe_json_dumps should handle set objects."""
        data = {"items": {1, 2, 3}}

        result = safe_json_dumps(data)

        parsed = json.loads(result)
        assert "items" in parsed

    @pytest.mark.unit
    def test_safe_json_handles_custom_objects(self):
        """safe_json_dumps should handle custom objects."""
        class CustomObject:
            def __init__(self):
                self.value = 42

        data = {"obj": CustomObject()}

        result = safe_json_dumps(data)

        assert result is not None
        parsed = json.loads(result)
        assert "obj" in parsed

    @pytest.mark.unit
    def test_safe_json_encoder_handles_bytes(self):
        """SafeJSONEncoder should handle bytes."""
        encoder = SafeJSONEncoder()

        result = encoder.default(b"test data")

        assert result == "test data"

    @pytest.mark.unit
    def test_safe_json_encoder_handles_path(self):
        """SafeJSONEncoder should handle Path objects."""
        encoder = SafeJSONEncoder()

        result = encoder.default(Path("/tmp/test.txt"))

        assert "/tmp/test.txt" in result or "\\tmp\\test.txt" in result


class TestLazyFormatting:
    """Test lazy formatting for performance."""

    @pytest.mark.unit
    def test_logger_lazy_formatting(self):
        """Logger should use lazy formatting for expensive operations."""
        io = MockIO()
        logger = StructuredLogger("test", io=io, level=logging.ERROR)

        expensive_called = []

        def expensive_operation():
            expensive_called.append(1)
            return "expensive result"

        # Debug is disabled, so expensive_operation should not be called
        logger.debug("Result: %s", expensive_operation)

        assert len(expensive_called) == 0


class TestSampling:
    """Test log sampling for high-volume scenarios."""

    @pytest.mark.unit
    def test_logger_sampling(self):
        """Logger should support sampling for high-volume logs."""
        io = MockIO()
        logger = StructuredLogger("test", io=io, sample_rate=0.5)

        # Log many messages
        for i in range(100):
            logger.debug(f"Message {i}")

        records = logger.get_records()
        # Should have approximately 50% (with some variance)
        assert 20 < len(records) < 80


class TestSeverityMapping:
    """Test severity mapping for error handler integration."""

    @pytest.mark.unit
    def test_log_with_severity_accepts_enum_like_values(self):
        """log_with_severity should accept enum-like severity values."""
        io = MockIO()
        logger = StructuredLogger("test", io=io)

        # Mock an enum-like object
        class MockSeverity:
            def __init__(self, value):
                self.value = value

        severity = MockSeverity(2)  # WARNING
        logger.log_with_severity("Test message", severity=severity)

        records = logger.get_records()
        assert records[-1]["level"] == "WARNING"

    @pytest.mark.unit
    def test_log_with_severity_handles_int_values(self):
        """log_with_severity should handle plain integer values."""
        io = MockIO()
        logger = StructuredLogger("test", io=io)

        logger.log_with_severity("Test message", severity=3)  # ERROR

        records = logger.get_records()
        assert records[-1]["level"] == "ERROR"
