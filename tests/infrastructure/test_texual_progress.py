import sys
import pytest
from unittest.mock import MagicMock, patch, ANY

from scrappy.infrastructure.textual_progress import TextualProgressReporter
from scrappy.infrastructure.theme import DEFAULT_THEME, LightTheme, NoColorTheme


@pytest.fixture
def mock_textual_env():
    """
    Mocks the 'textual' library.
    Since the class imports 'Static' inside the method, we must patch sys.modules
    to prevent ImportError if textual isn't installed, and to inspect the mock.
    """
    mock_static_cls = MagicMock()
    mock_widgets_module = MagicMock()
    mock_widgets_module.Static = mock_static_cls

    with patch.dict(sys.modules, {'textual.widgets': mock_widgets_module}):
        yield mock_static_cls


@pytest.fixture
def reporter_setup(mock_textual_env):
    """
    Creates a reporter instance with a mocked App and Widget.
    Returns a tuple of (reporter, mock_app, mock_widget).
    """
    mock_app = MagicMock()
    mock_widget = MagicMock()

    # Setup app.query_one to return our mock widget
    mock_app.query_one.return_value = mock_widget

    reporter = TextualProgressReporter(mock_app)

    return reporter, mock_app, mock_widget


class TestTextualProgressReporter:

    def test_start_indeterminate(self, reporter_setup):
        """Test starting a process with no total (indeterminate)."""
        reporter, mock_app, mock_widget = reporter_setup

        reporter.start("Loading")

        # Verify it queried for the #status widget
        mock_app.query_one.assert_called_with("#status", ANY)
        # Verify the update string format uses theme.primary
        expected = f"[{DEFAULT_THEME.primary}]Loading...[/{DEFAULT_THEME.primary}]"
        mock_widget.update.assert_called_with(expected)

        # Verify internal state
        assert reporter._total is None
        assert reporter._current == 0

    def test_start_determinate(self, reporter_setup):
        """Test starting a process with a specific total."""
        reporter, mock_app, mock_widget = reporter_setup

        reporter.start("Downloading", total=100)

        expected = f"[{DEFAULT_THEME.primary}]Downloading (0/100)[/{DEFAULT_THEME.primary}]"
        mock_widget.update.assert_called_with(expected)
        assert reporter._total == 100





    def test_complete(self, reporter_setup):
        """Test completion message and state reset."""
        reporter, mock_app, mock_widget = reporter_setup

        reporter.start("Working", total=10)
        reporter.complete("Done!")

        # Verify theme.success styling
        expected = f"[{DEFAULT_THEME.success}]Done![/{DEFAULT_THEME.success}]"
        mock_widget.update.assert_called_with(expected)

        # Verify state reset
        assert reporter._total is None
        assert reporter._current_description is None
        assert reporter._current is None

    def test_error(self, reporter_setup):
        """Test error message and state reset."""
        reporter, mock_app, mock_widget = reporter_setup

        reporter.start("Working", total=10)
        reporter.error("Connection Failed")

        # Verify theme.error styling
        expected = f"[{DEFAULT_THEME.error}]Error: Connection Failed[/{DEFAULT_THEME.error}]"
        mock_widget.update.assert_called_with(expected)

        # Verify state reset
        assert reporter._total is None


class TestTextualProgressReporterTheme:
    """Tests for theme injection in TextualProgressReporter."""

    @pytest.fixture
    def themed_reporter_setup(self, mock_textual_env):
        """Creates a reporter with custom theme."""
        mock_app = MagicMock()
        mock_widget = MagicMock()
        mock_app.query_one.return_value = mock_widget

        light_theme = LightTheme()
        reporter = TextualProgressReporter(mock_app, theme=light_theme)

        return reporter, mock_app, mock_widget, light_theme




