import sys
import pytest
from unittest.mock import MagicMock, patch, ANY

from src.infrastructure.textual_progress import TextualProgressReporter
from src.infrastructure.theme import DEFAULT_THEME, LightTheme, NoColorTheme


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

    def test_update_increment(self, reporter_setup):
        """Test updating the progress count."""
        reporter, mock_app, mock_widget = reporter_setup

        reporter.start("Processing", total=50)
        reporter.update(current=10)

        expected = f"[{DEFAULT_THEME.primary}]Processing (10/50)[/{DEFAULT_THEME.primary}]"
        mock_widget.update.assert_called_with(expected)

    def test_update_description(self, reporter_setup):
        """Test updating only the description."""
        reporter, mock_app, mock_widget = reporter_setup

        reporter.start("Phase 1", total=50)
        reporter.update(description="Phase 2")

        # Should keep the previous current count (0)
        expected = f"[{DEFAULT_THEME.primary}]Phase 2 (0/50)[/{DEFAULT_THEME.primary}]"
        mock_widget.update.assert_called_with(expected)

    def test_update_indeterminate_logic(self, reporter_setup):
        """Test update logic when total is None."""
        reporter, mock_app, mock_widget = reporter_setup

        reporter.start("Thinking")
        reporter.update(current=5)  # Current implies nothing without total in this logic

        # If total is None, it defaults to formatted description regardless of 'current'
        expected = f"[{DEFAULT_THEME.primary}]Thinking...[/{DEFAULT_THEME.primary}]"
        mock_widget.update.assert_called_with(expected)

    def test_update_fallback_message(self, reporter_setup):
        """Test the fallback message when no description exists."""
        reporter, mock_app, mock_widget = reporter_setup

        # Manually set state to simulate a weird edge case or re-init
        reporter._total = None
        reporter._current_description = None

        reporter.update(current=1)

        expected = f"[{DEFAULT_THEME.primary}]Processing...[/{DEFAULT_THEME.primary}]"
        mock_widget.update.assert_called_with(expected)

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

    def test_resilience_to_missing_widget(self, reporter_setup):
        """
        Test that the reporter silently fails if the app isn't ready
        or the widget is missing (The try/except block).
        """
        reporter, mock_app, _ = reporter_setup

        # Simulate app raising an error (e.g. widget not found)
        mock_app.query_one.side_effect = Exception("No matching widget")

        # Should not raise exception
        try:
            reporter.start("Test")
        except Exception as e:
            pytest.fail(f"Reporter raised exception despite try/except block: {e}")

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

    def test_uses_custom_theme_for_start(self, themed_reporter_setup):
        """Test that custom theme colors are used for start."""
        reporter, _, mock_widget, light_theme = themed_reporter_setup
        reporter.start("Loading")

        expected = f"[{light_theme.primary}]Loading...[/{light_theme.primary}]"
        mock_widget.update.assert_called_with(expected)

    def test_uses_custom_theme_for_update(self, themed_reporter_setup):
        """Test that custom theme colors are used for update."""
        reporter, _, mock_widget, light_theme = themed_reporter_setup
        reporter.start("Phase 1", total=10)
        reporter.update(current=5)

        expected = f"[{light_theme.primary}]Phase 1 (5/10)[/{light_theme.primary}]"
        mock_widget.update.assert_called_with(expected)

    def test_uses_custom_theme_for_complete(self, themed_reporter_setup):
        """Test that custom theme colors are used for complete."""
        reporter, _, mock_widget, light_theme = themed_reporter_setup
        reporter.complete("Done!")

        expected = f"[{light_theme.success}]Done![/{light_theme.success}]"
        mock_widget.update.assert_called_with(expected)

    def test_uses_custom_theme_for_error(self, themed_reporter_setup):
        """Test that custom theme colors are used for error."""
        reporter, _, mock_widget, light_theme = themed_reporter_setup
        reporter.error("Failed!")

        expected = f"[{light_theme.error}]Error: Failed![/{light_theme.error}]"
        mock_widget.update.assert_called_with(expected)

    def test_no_color_theme(self, mock_textual_env):
        """Test NoColorTheme produces empty strings for colors."""
        mock_app = MagicMock()
        mock_widget = MagicMock()
        mock_app.query_one.return_value = mock_widget

        no_color = NoColorTheme()
        reporter = TextualProgressReporter(mock_app, theme=no_color)
        reporter.start("Test")

        # Empty strings for color tags
        expected = f"[{no_color.primary}]Test...[/{no_color.primary}]"
        mock_widget.update.assert_called_with(expected)