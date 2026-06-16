"""Regression tests for scrappy-2vig: keyboard scrollback to older messages.

The SelectableLog widget scrolls correctly when driven; the bug was that the
chat screen never routed a working key to it during normal use (up/down are
consumed by command history while the input is focused, and PageUp/PageDown
were unbound). These tests cover both layers, headless and cross-platform.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from textual.app import App, ComposeResult

from scrappy.cli.screens.main_screen import MainAppScreen
from scrappy.cli.widgets.selectable_log import SelectableLog


class _LogApp(App):
    CSS = "SelectableLog { height: 100%; width: 100%; }"

    def compose(self) -> ComposeResult:
        yield SelectableLog(id="log")


@pytest.mark.asyncio
async def test_page_up_enters_review_and_page_down_returns_to_follow() -> None:
    """Paging up moves the viewport off the bottom; paging down returns to live."""
    app = _LogApp()
    async with app.run_test(size=(60, 10)) as pilot:
        await pilot.pause()
        log = app.query_one("#log", SelectableLog)
        for i in range(60):
            log.write(f"line {i:02d}")
        await pilot.pause()

        assert log.max_scroll_y > 0  # content overflows: scrolling is possible
        bottom = float(log.scroll_offset.y)
        assert log.is_following

        log.action_page_up()
        await pilot.pause()
        assert float(log.scroll_offset.y) < bottom  # moved to older messages
        assert not log.is_following  # review mode

        log.action_scroll_end()
        await pilot.pause()
        assert log.is_following
        assert float(log.scroll_offset.y) == bottom


def _screen_with_real_output() -> tuple[MainAppScreen, Mock]:
    """MainAppScreen whose surface.output is a stand-in we can assert on."""
    screen = MainAppScreen(
        interactive_mode=None,
        output_adapter=Mock(),
        bridge=Mock(),
        theme=Mock(),
        clipboard=Mock(),
    )
    surface = Mock()
    screen._surface = surface
    return screen, surface


def test_ctrl_pageup_pagedown_are_bound_to_transcript_scroll() -> None:
    """The chat screen binds Ctrl+PageUp/PageDown to transcript scrolling.

    Plain PageUp/PageDown stay with the focused composer (TextArea paging); the
    Ctrl chord is the focus-independent keyboard path to older messages, so it
    does not collide with composer navigation.
    """
    actions_by_key = {b.key: b.action for b in MainAppScreen.BINDINGS}
    assert "ctrl+pageup" in actions_by_key, (
        "Ctrl+PageUp is not bound -- cannot scroll to older messages while typing"
    )
    assert actions_by_key["ctrl+pageup"] == "transcript_page_up"
    assert actions_by_key["ctrl+pagedown"] == "transcript_page_down"
    assert "pageup" not in actions_by_key, (
        "plain PageUp must stay with the focused composer, not the transcript"
    )


def test_transcript_page_actions_drive_the_output_regardless_of_focus() -> None:
    """Paging the transcript scrolls the log even while the input holds focus."""
    screen, surface = _screen_with_real_output()

    screen.action_transcript_page_up()
    surface.output.action_page_up.assert_called_once_with()

    screen.action_transcript_page_down()
    surface.output.action_page_down.assert_called_once_with()
