import sys
import pytest
from unittest.mock import MagicMock, patch, ANY

from scrappy.infrastructure.textual_progress import TextualProgressReporter
from scrappy.infrastructure.theme import DEFAULT_THEME, LightTheme, NoColorTheme


@pytest.fixture
def reporter_setup():
    """
    Creates a reporter instance with a mocked StatusBarUpdater.
    Returns a tuple of (reporter, mock_status_updater).
    """
    mock_status_updater = MagicMock()
    reporter = TextualProgressReporter(mock_status_updater)

    return reporter, mock_status_updater


class TestTextualProgressReporter:

    def test_start_indeterminate(self, reporter_setup):
        """Test starting a process with no total (indeterminate)."""
        reporter, mock_status_updater = reporter_setup

        reporter.start("Loading")

        # Verify the update_status was called with correct format using theme.primary
        expected = f"[{DEFAULT_THEME.primary}]Loading...[/{DEFAULT_THEME.primary}]"
        mock_status_updater.update_status.assert_called_with(expected)

        # Verify internal state
        assert reporter._total is None
        assert reporter._current == 0

    def test_start_determinate(self, reporter_setup):
        """Test starting a process with a specific total."""
        reporter, mock_status_updater = reporter_setup

        reporter.start("Downloading", total=100)

        expected = f"[{DEFAULT_THEME.primary}]Downloading (0/100)[/{DEFAULT_THEME.primary}]"
        mock_status_updater.update_status.assert_called_with(expected)
        assert reporter._total == 100





    def test_complete(self, reporter_setup):
        """Test completion message and state reset."""
        reporter, mock_status_updater = reporter_setup

        reporter.start("Working", total=10)
        reporter.complete("Done!")

        # Verify theme.success styling
        expected = f"[{DEFAULT_THEME.success}]Done![/{DEFAULT_THEME.success}]"
        mock_status_updater.update_status.assert_called_with(expected)

        # Verify state reset
        assert reporter._total is None
        assert reporter._current_description is None
        assert reporter._current is None

    def test_error(self, reporter_setup):
        """Test error message and state reset."""
        reporter, mock_status_updater = reporter_setup

        reporter.start("Working", total=10)
        reporter.error("Connection Failed")

        # Verify theme.error styling
        expected = f"[{DEFAULT_THEME.error}]Error: Connection Failed[/{DEFAULT_THEME.error}]"
        mock_status_updater.update_status.assert_called_with(expected)

        # Verify state reset
        assert reporter._total is None


class TestTextualProgressReporterTheme:
    """Tests for theme injection in TextualProgressReporter."""

    @pytest.fixture
    def themed_reporter_setup(self):
        """Creates a reporter with custom theme."""
        mock_status_updater = MagicMock()
        light_theme = LightTheme()
        reporter = TextualProgressReporter(mock_status_updater, theme=light_theme)

        return reporter, mock_status_updater, light_theme




