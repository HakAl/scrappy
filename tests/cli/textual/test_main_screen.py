"""Tests for MainAppScreen command processing safeguards."""

from unittest.mock import Mock

from textual.message_pump import active_app

from scrappy.cli.screens.main_screen import MainAppScreen
from scrappy.cli.textual.output_adapter import TextualOutputAdapter
from scrappy.cli.textual.tui_events import TranscriptAppendRenderable, TranscriptAppendText


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

    transcript_events = [
        call.args[0]
        for call in app.tui_event_sink.post_event.call_args_list
        if isinstance(call.args[0], TranscriptAppendText)
    ]
    assert transcript_events == [TranscriptAppendText(content="Still initializing...\n")]
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


def test_process_command_errors_route_through_typed_sink():
    """Worker command errors should stay in the typed TUI event sequence."""
    interactive_mode = Mock()
    interactive_mode._process_input.side_effect = RuntimeError("boom")
    screen, app, _ = create_screen(interactive_mode=interactive_mode)

    token = active_app.set(app)
    try:
        MainAppScreen.process_command.__wrapped__(screen, "hello")
    finally:
        active_app.reset(token)

    renderable_events = [
        call.args[0]
        for call in app.tui_event_sink.post_event.call_args_list
        if isinstance(call.args[0], TranscriptAppendRenderable)
    ]
    assert len(renderable_events) == 1
    assert "Error:" in renderable_events[0].renderable.plain
    app.tui_event_sink.flush.assert_called_once_with(timeout=5.0)


def test_on_click_right_click_pastes_clipboard_into_input():
    """Right-click should route through the shared chat surface policy."""
    screen, _, clipboard = create_screen()
    clipboard.paste_text.return_value = "clipboard text"
    event = Mock()
    event.button = 3

    screen.on_click(event)

    screen._surface.handle_click.assert_called_once_with(event, clipboard)
