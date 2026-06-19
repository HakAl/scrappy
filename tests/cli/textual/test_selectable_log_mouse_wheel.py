"""Headless mouse-wheel contract tests for SelectableLog."""

from __future__ import annotations

import pytest
from textual import events
from textual.app import App, ComposeResult

from scrappy.cli.widgets.selectable_log import SelectableLog


class _LogApp(App):
    CSS = "SelectableLog { height: 100%; width: 100%; }"

    def compose(self) -> ComposeResult:
        yield SelectableLog(id="log")


@pytest.mark.asyncio
async def test_mouse_wheel_up_enters_review_and_wheel_down_returns_to_follow() -> None:
    """Mouse wheel up enters review; wheel down re-follows at the live bottom."""
    app = _LogApp()
    async with app.run_test(size=(60, 10)) as pilot:
        await pilot.pause()
        log = app.query_one("#log", SelectableLog)
        for i in range(60):
            log.write(f"line {i:02d}")
        await pilot.pause()

        assert log.max_scroll_y > 0
        bottom_y = float(log.scroll_offset.y)
        assert log.is_following is True

        # Directly drive the wheel handlers: they are the contract under test and
        # still exercise Textual's real ScrollView wheel delegation via super().
        log._on_mouse_scroll_up(
            events.MouseScrollUp(log, 10, 5, 0, -1, 0, False, False, False)
        )
        await pilot.pause()

        review_y = float(log.scroll_offset.y)
        assert review_y < bottom_y
        assert log.is_following is False

        log._on_mouse_scroll_down(
            events.MouseScrollDown(log, 10, 5, 0, 1, 0, False, False, False)
        )
        await pilot.pause()

        returned_y = float(log.scroll_offset.y)
        assert returned_y > review_y
        assert returned_y == bottom_y
        assert log.is_following is True
