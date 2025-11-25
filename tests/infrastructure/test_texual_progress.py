import sys
import pytest
from unittest.mock import MagicMock, patch, ANY

# Adjust import based on your actual file structure
from src.infrastructure.textual_progress import TextualProgressReporter


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
        # Verify the update string format
        mock_widget.update.assert_called_with("[cyan]Loading...[/cyan]")

        # Verify internal state
        assert reporter._total is None
        assert reporter._current == 0

    def test_start_determinate(self, reporter_setup):
        """Test starting a process with a specific total."""
        reporter, mock_app, mock_widget = reporter_setup

        reporter.start("Downloading", total=100)

        mock_widget.update.assert_called_with("[cyan]Downloading (0/100)[/cyan]")
        assert reporter._total == 100

    def test_update_increment(self, reporter_setup):
        """Test updating the progress count."""
        reporter, mock_app, mock_widget = reporter_setup

        reporter.start("Processing", total=50)
        reporter.update(current=10)

        mock_widget.update.assert_called_with("[cyan]Processing (10/50)[/cyan]")

    def test_update_description(self, reporter_setup):
        """Test updating only the description."""
        reporter, mock_app, mock_widget = reporter_setup

        reporter.start("Phase 1", total=50)
        reporter.update(description="Phase 2")

        # Should keep the previous current count (0)
        mock_widget.update.assert_called_with("[cyan]Phase 2 (0/50)[/cyan]")

    def test_update_indeterminate_logic(self, reporter_setup):
        """Test update logic when total is None."""
        reporter, mock_app, mock_widget = reporter_setup

        reporter.start("Thinking")
        reporter.update(current=5)  # Current implies nothing without total in this logic

        # If total is None, it defaults to formatted description regardless of 'current'
        mock_widget.update.assert_called_with("[cyan]Thinking...[/cyan]")

    def test_update_fallback_message(self, reporter_setup):
        """Test the fallback message when no description exists."""
        reporter, mock_app, mock_widget = reporter_setup

        # Manually set state to simulate a weird edge case or re-init
        reporter._total = None
        reporter._current_description = None

        reporter.update(current=1)

        mock_widget.update.assert_called_with("[cyan]Processing...[/cyan]")

    def test_complete(self, reporter_setup):
        """Test completion message and state reset."""
        reporter, mock_app, mock_widget = reporter_setup

        reporter.start("Working", total=10)
        reporter.complete("Done!")

        # Verify green styling
        mock_widget.update.assert_called_with("[green]Done![/green]")

        # Verify state reset
        assert reporter._total is None
        assert reporter._current_description is None
        assert reporter._current is None

    def test_error(self, reporter_setup):
        """Test error message and state reset."""
        reporter, mock_app, mock_widget = reporter_setup

        reporter.start("Working", total=10)
        reporter.error("Connection Failed")

        # Verify red styling
        mock_widget.update.assert_called_with("[red]Error: Connection Failed[/red]")

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

# todo
    # def test_import_handling(self):
    #     """
    #     Test specifically what happens if textual cannot be imported at all.
    #     The _update_status method calls 'from textual...'.
    #     """
    #     # We assume the app is passed, but the import inside _update_status fails
    #     mock_app = MagicMock()
    #     reporter = TextualProgressReporter(mock_app)
    #
    #     # Simulate ImportError when importing textual.widgets
    #     with patch.dict(sys.modules, {'textual.widgets': None}):
    #         # We rely on the implementation detail that it tries to import inside the method
    #         with patch('builtins.__import__', side_effect=ImportError):
    #             # Should catch the ImportError via the broad Exception clause in _update_status
    #             reporter.start("Test")
    #
    #     # Verification: execution continued without crashing
    #     assert reporter._current_description == "Test"