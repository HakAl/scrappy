"""
E2E tests for clipboard operations through the full ScrappyApp key handler chain.

These tests exercise the real on_key -> _handle_ctrl_c -> SelectableLog -> clipboard
pipeline. They catch regressions where app-level wiring breaks copy/paste even
though the widget itself works fine.

Pass/fail contract:
- PASS on main: basic Ctrl+C copy, double-tap exit, no-selection hint
- Should catch regressions when key handler ordering or clipboard wiring changes
"""

import os
import time
import pytest
from unittest.mock import MagicMock, patch

os.environ["SCRAPPY_MOCK_LLM"] = "1"

from scrappy.cli.textual.app import ScrappyApp
from scrappy.cli.widgets.selectable_log import SelectableLog


def create_mock_cli():
    mock_cli = MagicMock()
    mock_cli.interactive_mode = MagicMock()
    mock_cli.interactive_mode.command_router = MagicMock()
    mock_cli.interactive_mode.command_router.set_setup_wizard_callback = MagicMock()
    mock_cli.interactive_mode._process_input = MagicMock(return_value=True)
    return mock_cli


def create_test_app():
    return ScrappyApp(cli_factory=create_mock_cli)


def get_output_log(app) -> SelectableLog:
    return app.screen.query_one(SelectableLog)


class TestCopyViaCtrlC:
    """Ctrl+C with an active selection should copy text, not cancel or exit."""

    @pytest.mark.asyncio
    async def test_ctrl_c_copies_selected_text(self):
        """Select text in output log, Ctrl+C should copy it."""
        app = create_test_app()
        copied = {}

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            log = get_output_log(app)
            log.write("Hello clipboard world")
            await pilot.pause()

            # Simulate mouse selection (row 0, col 0 to col 15)
            log._selection_start = (0, 0)
            log._selection_end = (0, 15)

            with patch.object(app, "copy_to_clipboard", side_effect=lambda t: copied.update(text=t)):
                await pilot.press("ctrl+c")
                await pilot.pause()

            assert "text" in copied, "Ctrl+C with selection should copy text"
            assert len(copied["text"]) > 0, "Copied text should not be empty"

    @pytest.mark.asyncio
    async def test_ctrl_c_without_selection_does_not_copy(self):
        """Ctrl+C with no selection should not call copy_to_clipboard."""
        app = create_test_app()
        copy_called = []

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            log = get_output_log(app)
            log.write("Some text but nothing selected")
            await pilot.pause()

            # No selection set
            assert log.selection_text == ""

            with patch.object(app, "copy_to_clipboard", side_effect=lambda t: copy_called.append(t)):
                await pilot.press("ctrl+c")
                await pilot.pause()

            assert len(copy_called) == 0, "Should not copy when nothing is selected"

    @pytest.mark.asyncio
    async def test_ctrl_c_copy_does_not_arm_exit(self):
        """Copying text should not count as a Ctrl+C tap for double-tap exit."""
        app = create_test_app()

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            log = get_output_log(app)
            log.write("Copy me")
            await pilot.pause()

            # Set selection
            log._selection_start = (0, 0)
            log._selection_end = (0, 7)

            with patch.object(app, "copy_to_clipboard"):
                await pilot.press("ctrl+c")
                await pilot.pause()

            # The copy should have consumed the event.
            # A second Ctrl+C shortly after should NOT exit (it wasn't a double-tap
            # of the cancel gesture — the first one was a copy).
            # Reset selection so second press goes through cancel path
            log._selection_start = None
            log._selection_end = None

            exited = []
            original_exit = app.exit

            def capture_exit(*a, **kw):
                exited.append(True)
                original_exit(*a, **kw)

            with patch.object(app, "exit", side_effect=capture_exit):
                await pilot.press("ctrl+c")
                await pilot.pause()

            assert len(exited) == 0, "Copy + Ctrl+C should not trigger double-tap exit"



class TestDoubleTapExit:
    """Double-tap Ctrl+C should exit regardless of state."""

    @pytest.mark.asyncio
    async def test_double_tap_exits(self):
        """Two rapid Ctrl+C presses with no selection should exit."""
        app = create_test_app()
        exited = []

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            original_exit = app.exit

            def capture_exit(*a, **kw):
                exited.append(True)
                original_exit(*a, **kw)

            with patch.object(app, "exit", side_effect=capture_exit):
                await pilot.press("ctrl+c")
                await pilot.pause()
                await pilot.press("ctrl+c")
                await pilot.pause()

            assert len(exited) > 0, "Double-tap Ctrl+C should exit"

    @pytest.mark.asyncio
    async def test_slow_double_tap_does_not_exit(self):
        """Two Ctrl+C presses separated by > threshold should not exit."""
        app = create_test_app()
        exited = []

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            original_exit = app.exit

            def capture_exit(*a, **kw):
                exited.append(True)
                original_exit(*a, **kw)

            with patch.object(app, "exit", side_effect=capture_exit):
                await pilot.press("ctrl+c")
                await pilot.pause()
                # Push timestamp back so next press is outside threshold
                app._last_ctrl_c_time = time.time() - 1.0
                await pilot.press("ctrl+c")
                await pilot.pause()

            assert len(exited) == 0, "Slow double-tap should not exit"


class TestSelectionViaMouseDrag:
    """Mouse drag on SelectableLog should create a selection that Ctrl+C can copy."""

    @pytest.mark.asyncio
    async def test_mouse_drag_creates_selection(self):
        """Click and drag on output log should set selection start/end."""
        from textual.app import App, ComposeResult

        class MinimalApp(App):
            CSS = "SelectableLog { height: 100%; width: 100%; }"

            def compose(self) -> ComposeResult:
                yield SelectableLog(id="log")

        app = MinimalApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            log = app.query_one("#log", SelectableLog)
            log.write("Drag to select this text")
            await pilot.pause()

            # Programmatic selection (pilot.click doesn't support drag)
            log._selection_start = (0, 0)
            log._selection_end = (0, 10)

            assert log.selection_text != "", "Mouse drag should create selection"

    @pytest.mark.asyncio
    async def test_select_then_ctrl_c_copies(self):
        """Full flow: write content, select, Ctrl+C should copy."""
        app = create_test_app()
        copied = {}

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            log = get_output_log(app)
            log.write("End to end copy test")
            await pilot.pause()

            # Select the last line (banner content comes before our text)
            last_row = len(log._strips) - 1
            log._selection_start = (last_row, 0)
            log._selection_end = (last_row, 20)

            with patch.object(app, "copy_to_clipboard", side_effect=lambda t: copied.update(text=t)):
                await pilot.press("ctrl+c")
                await pilot.pause()

            assert "text" in copied
            assert "End to end" in copied["text"]


class TestMultilineSelection:
    """Selection spanning multiple lines should copy all lines."""

    @pytest.mark.asyncio
    async def test_multiline_copy(self):
        """Selecting across two lines should produce newline-separated text."""
        app = create_test_app()
        copied = {}

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            log = get_output_log(app)
            log.write("Line one")
            log.write("Line two")
            await pilot.pause()

            log._selection_start = (0, 0)
            log._selection_end = (1, 8)

            with patch.object(app, "copy_to_clipboard", side_effect=lambda t: copied.update(text=t)):
                await pilot.press("ctrl+c")
                await pilot.pause()

            assert "text" in copied
            assert "\n" in copied["text"], "Multiline selection should contain newlines"


class TestEscapeCancellation:
    """ESC should cancel operations without affecting clipboard state."""

    @pytest.mark.asyncio
    async def test_escape_does_not_clear_selection(self):
        """ESC cancels operations but shouldn't wipe an existing selection."""
        app = create_test_app()

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            log = get_output_log(app)
            log.write("Keep my selection")
            await pilot.pause()

            log._selection_start = (0, 0)
            log._selection_end = (0, 10)

            await pilot.press("escape")
            await pilot.pause()

            # Selection in the log widget should still be intact
            assert log.selection_text != "", "ESC should not clear text selection"
