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
    clipboard = Mock()
    screen = MainAppScreen(
        interactive_mode=interactive_mode,
        output_adapter=output_adapter,
        bridge=bridge,
        theme=MockTheme(),
        clipboard=clipboard,
    )
    app = Mock()
    app.interactive_mode = interactive_mode
    app.tui_event_sink = Mock()
    screen._app = app
    screen._surface = Mock()
    return screen, app, clipboard


def test_process_command_waits_for_interactive_mode():
    """Calling process_command early should not crash the worker thread."""
    screen, app, _ = create_screen(interactive_mode=None)

    token = active_app.set(app)
    try:
        MainAppScreen.process_command.__wrapped__(screen, "hello")
    finally:
        active_app.reset(token)

    screen._surface.write.assert_called_once_with("Still initializing...\n")
    app.tui_event_sink.post_event.assert_called()
    app.exit.assert_not_called()


def test_process_command_recovers_interactive_mode_from_app():
    """Screen should rehydrate its interactive mode from the app when available."""
    interactive_mode = Mock()
    interactive_mode._process_input.return_value = True
    screen, app, _ = create_screen(interactive_mode=None)
    app.interactive_mode = interactive_mode

    token = active_app.set(app)
    try:
        MainAppScreen.process_command.__wrapped__(screen, "hello")
    finally:
        active_app.reset(token)

    interactive_mode._process_input.assert_called_once_with("hello")
    assert screen.interactive_mode is interactive_mode
    screen._surface.write.assert_not_called()
    app.call_from_thread.assert_called_once_with(app.restore_mouse_support)


def test_on_click_right_click_pastes_clipboard_into_input():
    """Right-click should route through the shared chat surface policy."""
    screen, _, clipboard = create_screen()
    clipboard.paste_text.return_value = "clipboard text"
    event = Mock()
    event.button = 3

    screen.on_click(event)

    screen._surface.handle_click.assert_called_once_with(event, clipboard)
