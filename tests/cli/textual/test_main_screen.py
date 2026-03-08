"""Tests for MainAppScreen command processing safeguards."""

from unittest.mock import Mock

from textual.message_pump import active_app

from scrappy.cli.screens.main_screen import MainAppScreen
from scrappy.cli.textual.output_adapter import TextualOutputAdapter


class MockTheme:
    """Minimal theme for screen error rendering."""

    error = "red"


def create_screen(interactive_mode=None):
    """Create a MainAppScreen with lightweight mocked dependencies."""
    output_adapter = TextualOutputAdapter()
    bridge = Mock()
    screen = MainAppScreen(
        interactive_mode=interactive_mode,
        output_adapter=output_adapter,
        bridge=bridge,
        theme=MockTheme(),
    )
    app = Mock()
    app.interactive_mode = interactive_mode
    screen._app = app
    screen._layout = Mock()
    return screen, app


def test_process_command_waits_for_interactive_mode():
    """Calling process_command early should not crash the worker thread."""
    screen, app = create_screen(interactive_mode=None)

    token = active_app.set(app)
    try:
        MainAppScreen.process_command.__wrapped__(screen, "hello")
    finally:
        active_app.reset(token)

    screen._layout.write.assert_called_once_with("Still initializing...\n")
    app.post_message.assert_called()
    app.exit.assert_not_called()


def test_process_command_recovers_interactive_mode_from_app():
    """Screen should rehydrate its interactive mode from the app when available."""
    interactive_mode = Mock()
    interactive_mode._process_input.return_value = True
    screen, app = create_screen(interactive_mode=None)
    app.interactive_mode = interactive_mode

    token = active_app.set(app)
    try:
        MainAppScreen.process_command.__wrapped__(screen, "hello")
    finally:
        active_app.reset(token)

    interactive_mode._process_input.assert_called_once_with("hello")
    assert screen.interactive_mode is interactive_mode
    screen._layout.write.assert_not_called()
