"""Tests for model-backed SelectableLog behavior."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.events import MouseDown, MouseMove

from scrappy.cli.widgets.selectable_log import SelectableLog
from scrappy.cli.widgets.transcript_model import TranscriptModel


class LogHarnessApp(App):
    """Minimal app that mounts a transcript widget."""

    CSS = "SelectableLog { height: 100%; width: 100%; }"

    def __init__(self, log: SelectableLog | None = None) -> None:
        super().__init__()
        self._log = log or SelectableLog(id="log")

    def compose(self) -> ComposeResult:
        yield self._log


def select_first_word(log: SelectableLog, end_x: int = 8) -> None:
    """Create a mouse selection on the first rendered row."""
    log.on_mouse_down(MouseDown(log, 0, 0, 0, 0, 1, False, False, False))
    log.on_mouse_move(MouseMove(log, end_x, 0, end_x, 0, 0, False, False, False))


def test_transcript_model_entry_ids_are_monotonic_after_trim_and_clear() -> None:
    """Entry IDs are stable identities, not list indices."""
    model = TranscriptModel()
    first = model.append("first")
    second = model.append("second")

    assert model.entry_ids() == (first, second)

    model.trim_through(first)
    third = model.append("third")

    assert model.entry_ids() == (second, third)
    assert int(third) > int(second)

    model.clear()
    fourth = model.append("fourth")

    assert int(fourth) > int(third)


@pytest.mark.asyncio
async def test_resize_reflows_existing_transcript_content() -> None:
    """Existing transcript content should reflow after terminal resize."""
    app = LogHarnessApp()

    async with app.run_test(size=(80, 12)) as pilot:
        await pilot.pause()

        log = app.query_one("#log", SelectableLog)
        log.write("word " * 40)
        await pilot.pause()
        wide_height = log.virtual_size.height

        await pilot.resize_terminal(24, 12)
        await pilot.pause()

        assert log.virtual_size.height > wide_height


@pytest.mark.asyncio
async def test_resize_clears_selection_to_avoid_stale_rendered_rows() -> None:
    """Selection should not survive a width-changing reflow."""
    app = LogHarnessApp()

    async with app.run_test(size=(80, 12)) as pilot:
        await pilot.pause()

        log = app.query_one("#log", SelectableLog)
        log.write("copyable transcript text")
        await pilot.pause()
        select_first_word(log)

        assert log.selection_text == "copyable"

        await pilot.resize_terminal(40, 12)
        await pilot.pause()

        assert log.selection_text == ""


@pytest.mark.asyncio
async def test_active_drag_resize_releases_mouse_capture(monkeypatch) -> None:
    """Resize invalidation should release an in-progress transcript drag."""
    app = LogHarnessApp()

    async with app.run_test(size=(80, 12)) as pilot:
        await pilot.pause()

        log = app.query_one("#log", SelectableLog)
        log.write("drag selection text")
        await pilot.pause()
        released: list[bool] = []
        monkeypatch.setattr(log, "release_mouse", lambda: released.append(True))

        log.on_mouse_down(MouseDown(log, 0, 0, 0, 0, 1, False, False, False))
        assert log._is_selecting is True

        await pilot.resize_terminal(40, 12)
        await pilot.pause()

        assert log._is_selecting is False
        assert released == [True]


@pytest.mark.asyncio
async def test_trim_removes_entries_by_id_and_clears_selection() -> None:
    """Trimming old entries should not leave selection pointing at stale rows."""
    log = SelectableLog(id="log", max_lines=2)
    app = LogHarnessApp(log)

    async with app.run_test(size=(80, 12)) as pilot:
        await pilot.pause()

        log.write("first entry")
        first_id = log.transcript_model.entry_ids()[0]
        log.write("second entry")
        await pilot.pause()
        select_first_word(log, end_x=5)

        assert log.selection_text == "first"

        log.write("third entry")
        await pilot.pause()

        assert first_id not in log.transcript_model.entry_ids()
        assert log.selection_text == ""


@pytest.mark.asyncio
async def test_trim_continues_when_placeholder_rows_exist() -> None:
    """Sustained writes should trim even after lazy placeholder rows exist."""
    max_lines = 20
    log = SelectableLog(id="log", max_lines=max_lines)
    app = LogHarnessApp(log)

    async with app.run_test(size=(80, 12)) as pilot:
        await pilot.pause()

        for index in range(max_lines):
            log.write(f"seed {index}")
        await pilot.pause()

        await pilot.resize_terminal(40, 12)
        await pilot.pause()
        log.render_line(max_lines - 1)

        assert any(line.is_placeholder for line in log._rendered_lines)

        for index in range(max_lines * 2):
            log.write(f"stream {index}")
        await pilot.pause()

        entries = log.transcript_model.entries()
        assert len(entries) == max_lines
        assert all(str(entry.renderable).startswith("stream ") for entry in entries)


@pytest.mark.asyncio
async def test_resize_does_not_render_every_entry_synchronously(monkeypatch) -> None:
    """Width invalidation should rebuild only the visible transcript rows."""
    log = SelectableLog(id="log")
    app = LogHarnessApp(log)

    async with app.run_test(size=(80, 12)) as pilot:
        await pilot.pause()

        for index in range(200):
            log.write(f"entry {index}")
        await pilot.pause()

        calls = 0
        original_render_entry = log._render_entry

        def count_render(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original_render_entry(*args, **kwargs)

        monkeypatch.setattr(log, "_render_entry", count_render)

        await pilot.resize_terminal(40, 12)
        await pilot.pause()

        assert 0 < calls < 200
