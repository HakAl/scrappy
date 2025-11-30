import sys
import logging
from unittest.mock import MagicMock, patch, call
import pytest

from src.infrastructure.progress import (
    RichProgressReporter,
    LiveProgressReporter,
    LoggingProgressReporter,
    CallbackProgressReporter,
    NullProgressReporter,
    UnifiedIOProgressReporter,
)
from src.infrastructure.theme import DEFAULT_THEME, LightTheme, NoColorTheme


# --- Fixtures ---

@pytest.fixture
def mock_rich_modules():
    """
    Simulates that 'rich' is installed and mocks its components.
    Since imports happen inside methods, we must patch sys.modules.
    """
    mock_console = MagicMock()
    mock_status = MagicMock()
    mock_live = MagicMock()
    mock_spinner = MagicMock()

    # Setup chain: Console().status() -> status_obj
    mock_console.return_value.status.return_value = mock_status

    # Setup chain: Live() -> live_obj
    mock_live.return_value = MagicMock()

    # Create the mock module structure
    modules = {
        'rich': MagicMock(),
        'rich.console': MagicMock(Console=mock_console),
        'rich.status': MagicMock(),
        'rich.live': MagicMock(Live=mock_live),
        'rich.spinner': MagicMock(Spinner=mock_spinner),
        'rich.text': MagicMock(Text=MagicMock()),
    }

    with patch.dict(sys.modules, modules):
        yield {
            'console_cls': mock_console,
            'status_inst': mock_status,
            'live_cls': mock_live,
            'spinner_cls': mock_spinner
        }


@pytest.fixture
def mock_io():
    """Mocks the CLIIOProtocol."""
    io = MagicMock()
    io.secho = MagicMock()
    return io


# --- Tests for RichProgressReporter ---

def test_rich_reporter_start_success(mock_rich_modules):
    reporter = RichProgressReporter()
    reporter.start("Loading", total=100)

    # Verify Console was initialized with stderr=True
    mock_rich_modules['console_cls'].assert_called_with(stderr=True)
    # Verify status started with theme.primary color
    mock_rich_modules['console_cls'].return_value.status.assert_called_with(
        f"[{DEFAULT_THEME.primary}]Loading[/{DEFAULT_THEME.primary}]"
    )
    mock_rich_modules['status_inst'].start.assert_called_once()


def test_rich_reporter_update(mock_rich_modules):
    reporter = RichProgressReporter()
    reporter.start("Start")
    reporter.update(current=50, description="Processing")

    mock_rich_modules['status_inst'].update.assert_called_with(
        f"[{DEFAULT_THEME.primary}]Processing[/{DEFAULT_THEME.primary}]"
    )


def test_rich_reporter_complete(mock_rich_modules):
    reporter = RichProgressReporter()
    reporter.start("Start")
    reporter.complete("Done")

    # Status should stop
    mock_rich_modules['status_inst'].stop.assert_called_once()
    # Completion message printed with theme.success color
    mock_rich_modules['console_cls'].return_value.print.assert_called_with(
        f"[{DEFAULT_THEME.success}]Done[/{DEFAULT_THEME.success}]"
    )


def test_rich_reporter_error(mock_rich_modules):
    reporter = RichProgressReporter()
    reporter.start("Start")
    reporter.error("Failed")

    mock_rich_modules['status_inst'].stop.assert_called_once()
    mock_rich_modules['console_cls'].return_value.print.assert_called_with(
        f"[{DEFAULT_THEME.error}]Error: Failed[/{DEFAULT_THEME.error}]"
    )


def test_rich_reporter_import_error(caplog):
    """Test behavior when rich is not installed."""
    # We create a context where importing rich raises ImportError
    with patch.dict(sys.modules, {'rich.console': None}):
        # We need to ensure the import actually fails.
        # A side_effect on __import__ is tricky, so we rely on the implementation
        # trying to import from rich.console.
        with patch('builtins.__import__', side_effect=ImportError):
            reporter = RichProgressReporter()
            reporter.start("Test")

            assert "Rich library not available" in caplog.text
            # Ensure no crash on subsequent calls
            reporter.update(1, "update")
            reporter.complete()


# --- Tests for LiveProgressReporter ---

def test_live_reporter_flow(mock_rich_modules):
    # Mock time.sleep to speed up tests
    with patch('time.sleep'):
        reporter = LiveProgressReporter()
        reporter.start("Live Action")

        # Check Live initialization
        mock_rich_modules['live_cls'].assert_called_once()
        mock_live_inst = mock_rich_modules['live_cls'].return_value
        mock_live_inst.start.assert_called_once()

        # Update
        reporter.update(description="Updated Action")
        mock_live_inst.update.assert_called()

        # Complete
        reporter.complete("Finished")
        # Should show success message then stop
        assert mock_live_inst.update.call_count >= 2  # Once for update, once for complete
        mock_live_inst.stop.assert_called_once()


def test_live_reporter_exception_handling(caplog):
    """Test general exception during start (e.g., inside Rich logic)."""
    # Set log level to capture ERROR logs from the progress module
    caplog.set_level(logging.ERROR, logger='src.infrastructure.progress')

    with patch.dict(sys.modules, {'rich.console': MagicMock()}):
        # Force an error inside the try block
        with patch('rich.console.Console', side_effect=Exception("Boom")):
            reporter = LiveProgressReporter()
            reporter.start("Test")

            assert "Error starting Live progress: Boom" in caplog.text


# --- Tests for LoggingProgressReporter ---

def test_logging_reporter(caplog):
    caplog.set_level(logging.INFO)
    reporter = LoggingProgressReporter("test_logger")

    # Test indeterminate
    reporter.start("Doing work")
    assert "Doing work" in caplog.text

    # Test determinate update
    reporter._total = 10  # Manually setting state for test sequence
    reporter.update(5, "Halfway")
    assert "Halfway (5/10)" in caplog.text

    # Test error
    reporter.error("Something broke")
    assert "Something broke" in caplog.text

    # Verify log levels
    assert caplog.records[-1].levelname == "ERROR"


# --- Tests for CallbackProgressReporter ---

def test_callback_reporter():
    mock_cb = MagicMock()
    reporter = CallbackProgressReporter(mock_cb)

    # Start
    reporter.start("Init", total=100)
    mock_cb.assert_called_with("Init (0/100)")

    # Update
    reporter.update(10, "Moving")
    mock_cb.assert_called_with("Moving (10/100)")

    # Complete
    reporter.complete("Done")
    mock_cb.assert_called_with("Done")

    # Error
    reporter.error("Fail")
    mock_cb.assert_called_with("Error: Fail")


# --- Tests for NullProgressReporter ---

def test_null_reporter():
    # Smoke test to ensure it doesn't crash
    reporter = NullProgressReporter()
    reporter.start("Hi")
    reporter.update(1)
    reporter.complete()
    reporter.error("Err")


# --- Tests for UnifiedIOProgressReporter ---

def test_unified_io_reporter_start(mock_io):
    reporter = UnifiedIOProgressReporter(mock_io)

    # Indeterminate
    reporter.start("Loading")
    mock_io.secho.assert_called_with("Loading...", fg=DEFAULT_THEME.primary)

    # Determinate
    reporter.start("Loading", total=50)
    mock_io.secho.assert_called_with("Loading (0/50)", fg=DEFAULT_THEME.primary)


def test_unified_io_reporter_update(mock_io):
    reporter = UnifiedIOProgressReporter(mock_io)
    reporter.update(description="Step 2")

    mock_io.secho.assert_called_with("  Step 2", fg=DEFAULT_THEME.primary)


def test_unified_io_reporter_complete(mock_io):
    reporter = UnifiedIOProgressReporter(mock_io)
    reporter.complete("All Done")

    mock_io.secho.assert_called_with("All Done", fg=DEFAULT_THEME.success)


def test_unified_io_reporter_error(mock_io):
    reporter = UnifiedIOProgressReporter(mock_io)
    reporter.error("Fatal Error")

    mock_io.secho.assert_called_with("Error: Fatal Error", fg=DEFAULT_THEME.error)


# --- Tests for Theme Integration ---

class TestRichProgressReporterTheme:
    """Tests for theme injection in RichProgressReporter."""

    def test_uses_custom_theme(self, mock_rich_modules):
        """Test that custom theme colors are used."""
        light_theme = LightTheme()
        reporter = RichProgressReporter(theme=light_theme)
        reporter.start("Loading")

        mock_rich_modules['console_cls'].return_value.status.assert_called_with(
            f"[{light_theme.primary}]Loading[/{light_theme.primary}]"
        )

    def test_complete_uses_theme_success(self, mock_rich_modules):
        """Test that complete uses theme.success."""
        light_theme = LightTheme()
        reporter = RichProgressReporter(theme=light_theme)
        reporter.start("Start")
        reporter.complete("Done")

        mock_rich_modules['console_cls'].return_value.print.assert_called_with(
            f"[{light_theme.success}]Done[/{light_theme.success}]"
        )

    def test_error_uses_theme_error(self, mock_rich_modules):
        """Test that error uses theme.error."""
        light_theme = LightTheme()
        reporter = RichProgressReporter(theme=light_theme)
        reporter.start("Start")
        reporter.error("Failed")

        mock_rich_modules['console_cls'].return_value.print.assert_called_with(
            f"[{light_theme.error}]Error: Failed[/{light_theme.error}]"
        )


class TestUnifiedIOProgressReporterTheme:
    """Tests for theme injection in UnifiedIOProgressReporter."""

    def test_uses_custom_theme_for_start(self, mock_io):
        """Test that custom theme colors are used for start."""
        light_theme = LightTheme()
        reporter = UnifiedIOProgressReporter(mock_io, theme=light_theme)
        reporter.start("Loading")

        mock_io.secho.assert_called_with("Loading...", fg=light_theme.primary)

    def test_uses_custom_theme_for_update(self, mock_io):
        """Test that custom theme colors are used for update."""
        light_theme = LightTheme()
        reporter = UnifiedIOProgressReporter(mock_io, theme=light_theme)
        reporter.update(description="Step 2")

        mock_io.secho.assert_called_with("  Step 2", fg=light_theme.primary)

    def test_uses_custom_theme_for_complete(self, mock_io):
        """Test that custom theme colors are used for complete."""
        light_theme = LightTheme()
        reporter = UnifiedIOProgressReporter(mock_io, theme=light_theme)
        reporter.complete("Done")

        mock_io.secho.assert_called_with("Done", fg=light_theme.success)

    def test_uses_custom_theme_for_error(self, mock_io):
        """Test that custom theme colors are used for error."""
        light_theme = LightTheme()
        reporter = UnifiedIOProgressReporter(mock_io, theme=light_theme)
        reporter.error("Failed")

        mock_io.secho.assert_called_with("Error: Failed", fg=light_theme.error)

    def test_no_color_theme(self, mock_io):
        """Test NoColorTheme produces empty strings for colors."""
        no_color = NoColorTheme()
        reporter = UnifiedIOProgressReporter(mock_io, theme=no_color)
        reporter.start("Test")

        mock_io.secho.assert_called_with("Test...", fg="")