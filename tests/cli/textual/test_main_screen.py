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
    screen._layout = Mock()
    return screen, app, clipboard


def test_process_command_waits_for_interactive_mode():
    """Calling process_command early should not crash the worker thread."""
    screen, app, _ = create_screen(interactive_mode=None)

    token = active_app.set(app)
    try:
        MainAppScreen.process_command.__wrapped__(screen, "hello")
    finally:
        active_app.reset(token)

    screen._layout.write.assert_called_once_with("Still initializing...\n")
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
    screen._layout.write.assert_not_called()
    app.call_from_thread.assert_called_once_with(app.restore_mouse_support)


def test_on_click_right_click_pastes_clipboard_into_input():
    """Right-click should paste clipboard text into the input widget."""
    screen, _, clipboard = create_screen()
    selection = Mock()
    selection.start = (0, 0)
    selection.end = (0, 0)
    screen._layout.input.selection = selection
    clipboard.paste_text.return_value = "clipboard text"
    event = Mock()
    event.button = 3

    screen.on_click(event)

    clipboard.paste_text.assert_called_once_with()
    screen._layout.input.replace.assert_called_once_with(
        "clipboard text",
        selection.start,
        selection.end,
        maintain_selection_offset=True,
    )
