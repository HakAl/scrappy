"""Contract tests for the TUI interaction refactor.

These tests pin user-visible behavior described in docs/behavior/TUI.md.
Future PRs remove strict xfail markers as each behavior lands.
"""

from unittest.mock import MagicMock, patch

import pytest
from textual.app import App, ComposeResult
from textual.events import MouseDown, MouseMove, MouseUp
from textual.widgets import TextArea

from scrappy.cli.screens.chat_surface import ChatSurface
from scrappy.cli.screens.main_screen import MainAppScreen
from scrappy.cli.screens.wizard_screen import SetupWizardScreen
from scrappy.cli.textual.app import ScrappyApp
from scrappy.cli.widgets.selectable_log import SelectableLog


def create_test_app() -> ScrappyApp:
    """Create a ScrappyApp instance for contract tests."""
    interactive_mode = MagicMock()
    interactive_mode.command_router.set_setup_wizard_callback = MagicMock()
    return ScrappyApp(interactive_mode=interactive_mode)


def force_main_screen(monkeypatch) -> None:
    """Force ScrappyApp pilot tests onto the main chat screen."""
    monkeypatch.setattr(
        "scrappy.orchestrator.mock_llm_service.is_mock_mode_enabled",
        lambda: True,
    )


class LogHarnessApp(App):
    """Minimal app for widget-level transcript contracts."""

    CSS = "SelectableLog { height: 100%; width: 100%; }"

    def compose(self) -> ComposeResult:
        yield SelectableLog(id="log")


class SingleScreenApp(App):
    """Mount one real screen without going through ScrappyApp routing."""

    def __init__(self, screen) -> None:
        super().__init__()
        self._screen = screen

    def compose(self) -> ComposeResult:
        yield self._screen


def write_transcript_lines(log: SelectableLog, prefix: str, count: int = 80) -> None:
    """Append enough transcript rows to overflow a small pilot viewport."""
    for i in range(count):
        log.write(f"{prefix} line {i}")


def select_first_word(log: SelectableLog) -> None:
    """Create a small real selection in the transcript widget."""
    log.on_mouse_down(MouseDown(log, 0, 0, 0, 0, 1, False, False, False))
    log.on_mouse_move(MouseMove(log, 8, 0, 8, 0, 0, False, False, False))
    log.on_mouse_up(MouseUp(log, 8, 0, 0, 0, 1, False, False, False))


def create_main_screen(clipboard) -> MainAppScreen:
    """Create a real main screen with external dependencies stubbed."""
    return MainAppScreen(
        interactive_mode=None,
        output_adapter=MagicMock(),
        bridge=MagicMock(),
        theme=MagicMock(),
        clipboard=clipboard,
    )


def create_wizard_screen(clipboard) -> SetupWizardScreen:
    """Create a real wizard screen with external dependencies stubbed."""
    mock_io = MagicMock()
    mock_io.theme = MagicMock()
    mock_io.output_sink = MagicMock()
    return SetupWizardScreen(
        io=mock_io,
        key_validator=MagicMock(),
        clipboard=clipboard,
    )


class TestTranscriptScrollContracts:
    """Contracts for transcript scrolling and scrollbars."""

    @pytest.mark.asyncio
    async def test_transcript_uses_normal_scrollbar_on_overflow(self, monkeypatch):
        """Overflowing transcript content should expose a normal vertical scrollbar."""
        force_main_screen(monkeypatch)
        app = create_test_app()

        async with app.run_test(size=(80, 12)) as pilot:
            await pilot.pause()

            log = app.screen.query_one(SelectableLog)
            write_transcript_lines(log, "scrollbar contract")
            await pilot.pause()

            scrollbar_size = getattr(log.styles, "scrollbar_size_vertical", 0)
            assert scrollbar_size != 0
            assert getattr(log, "show_vertical_scrollbar") is True

    @pytest.mark.asyncio
    async def test_transcript_has_single_scroll_owner(self, monkeypatch):
        """The transcript widget should be the only scroll owner for output."""
        force_main_screen(monkeypatch)
        app = create_test_app()

        async with app.run_test(size=(80, 12)) as pilot:
            await pilot.pause()

            surface = app.screen.query_one(ChatSurface)
            log = app.screen.query_one(SelectableLog)

            assert list(app.screen.query("#output_container")) == []
            assert log.parent is surface

    @pytest.mark.asyncio
    async def test_page_up_scrolls_transcript_after_enough_output(self, monkeypatch):
        """PageUp should move an overflowing transcript away from the live bottom."""
        force_main_screen(monkeypatch)
        app = create_test_app()

        async with app.run_test(size=(80, 12)) as pilot:
            await pilot.pause()

            log = app.screen.query_one(SelectableLog)
            write_transcript_lines(log, "scroll-up contract")
            await pilot.pause()

            log.focus()
            bottom = int(log.scroll_offset.y)
            assert bottom > 0

            await pilot.press("pageup")
            await pilot.pause()

            assert int(log.scroll_offset.y) < bottom

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="PR 6 adds reviewing mode so new output does not yank the viewport.",
    )
    async def test_new_output_preserves_reviewing_viewport(self):
        """New transcript output should not move the viewport while reviewing old output."""
        # PR 6: move this to SingleScreenApp/create_test_app when scroll state
        # lives in the surface/controller instead of the widget.
        app = LogHarnessApp()

        async with app.run_test(size=(80, 12)) as pilot:
            await pilot.pause()

            log = app.query_one("#log", SelectableLog)
            write_transcript_lines(log, "review contract")
            await pilot.pause()

            log.scroll_to(y=0, animate=False)
            await pilot.pause()
            before = int(log.scroll_offset.y)

            log.write("new output while reviewing")
            await pilot.pause()

            assert int(log.scroll_offset.y) == before

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="PR 6 routes End/Ctrl+End to transcript follow-latest behavior.",
    )
    async def test_end_key_returns_to_live_bottom(self, monkeypatch):
        """End should return a reviewing transcript to the live bottom."""
        force_main_screen(monkeypatch)
        app = create_test_app()

        async with app.run_test(size=(80, 12)) as pilot:
            await pilot.pause()

            log = app.screen.query_one(SelectableLog)
            write_transcript_lines(log, "end contract")
            await pilot.pause()

            log.scroll_to(y=0, animate=False)
            await pilot.pause()
            await pilot.press("end")
            await pilot.pause()

            max_scroll_y = int(getattr(log, "max_scroll_y"))
            assert int(log.scroll_offset.y) >= max_scroll_y - 2

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="PR 7 separates command history from transcript scroll ownership.",
    )
    async def test_history_navigation_does_not_block_transcript_up_scroll(
        self, monkeypatch
    ):
        """Up should scroll the transcript when transcript focus owns the key."""
        force_main_screen(monkeypatch)
        app = create_test_app()

        async with app.run_test(size=(80, 12)) as pilot:
            await pilot.pause()

            log = app.screen.query_one(SelectableLog)
            write_transcript_lines(log, "history contract")
            await pilot.pause()

            log.focus()
            bottom = int(log.scroll_offset.y)
            assert bottom > 0

            await pilot.press("up")
            await pilot.pause()

            assert int(log.scroll_offset.y) < bottom


class TestClipboardPriorityContracts:
    """Contracts for Ctrl+C copy, cancel, and double-tap priority."""

    def test_ctrl_c_priority_prefers_copy_then_cancel_then_double_tap(self):
        """Ctrl+C should copy first, then cancel, then use double-tap exit."""
        copy_app = create_test_app()

        with (
            patch.object(
                copy_app, "_handle_copy_shortcut", return_value=True
            ) as copy_shortcut,
            patch.object(copy_app, "_cancel_operation", return_value=True) as cancel_operation,
            patch.object(copy_app, "exit") as exit_app,
        ):
            assert copy_app._handle_ctrl_c() is True

        copy_shortcut.assert_called_once_with()
        cancel_operation.assert_not_called()
        exit_app.assert_not_called()

        cancel_app = create_test_app()
        with (
            patch("scrappy.cli.textual.app.time.time", return_value=100.0),
            patch.object(cancel_app, "_handle_copy_shortcut", return_value=False),
            patch.object(
                cancel_app, "_cancel_operation", return_value=True
            ) as cancel_operation,
            patch.object(cancel_app, "exit") as exit_app,
        ):
            assert cancel_app._handle_ctrl_c() is True

        cancel_operation.assert_called_once_with()
        exit_app.assert_not_called()

        exit_app_instance = create_test_app()
        with (
            patch("scrappy.cli.textual.app.time.time", side_effect=[200.0, 200.25]),
            patch.object(exit_app_instance, "_handle_copy_shortcut", return_value=False),
            patch.object(exit_app_instance, "_cancel_operation", return_value=False),
            patch.object(exit_app_instance, "notify") as notify,
            patch.object(exit_app_instance, "exit") as exit_app,
        ):
            assert exit_app_instance._handle_ctrl_c() is True
            assert exit_app_instance._handle_ctrl_c() is True

        notify.assert_called_once_with("Press Ctrl+C again to exit", timeout=2)
        assert exit_app.called


class TestMouseSelectionContracts:
    """Contracts for transcript mouse selection and copy."""

    @pytest.mark.asyncio
    async def test_mouse_selection_copies_selected_transcript_text(self):
        """Mouse-selected transcript text should copy through the app clipboard path."""
        app = LogHarnessApp()

        async with app.run_test(size=(80, 12)) as pilot:
            await pilot.pause()

            log = app.query_one("#log", SelectableLog)
            log.write("copyable transcript text")
            await pilot.pause()

            select_first_word(log)

            with patch.object(app, "copy_to_clipboard") as copy_to_clipboard:
                log.action_copy_selection()

        copy_to_clipboard.assert_called_once_with("copyable")


class TestSharedSurfaceContracts:
    """Contracts for behavior that must be shared by main chat and setup wizard."""

    @pytest.mark.asyncio
    async def test_transcript_click_keeps_transcript_focus_on_main_and_wizard(self):
        """Clicking transcript output should preserve transcript interaction ownership."""
        for create_screen in (create_main_screen, create_wizard_screen):
            clipboard = MagicMock()
            screen = create_screen(clipboard)
            app = SingleScreenApp(screen)

            async with app.run_test(size=(80, 12)) as pilot:
                await pilot.pause()

                log = app.query_one(SelectableLog)
                log.write("selected transcript text")
                select_first_word(log)
                log.focus()
                await pilot.pause()

                event = MagicMock()
                event.button = 1
                event.widget = log

                screen.on_click(event)

                assert app.focused is log
                assert log.selection_text != ""

    @pytest.mark.asyncio
    async def test_transcript_right_click_does_not_paste_into_composer(self):
        """Transcript mouse actions should not paste into the composer."""
        for create_screen in (create_main_screen, create_wizard_screen):
            clipboard = MagicMock()
            clipboard.paste_text.return_value = "pasted"
            screen = create_screen(clipboard)
            app = SingleScreenApp(screen)

            async with app.run_test(size=(80, 12)) as pilot:
                await pilot.pause()

                log = app.query_one(SelectableLog)
                composer = app.query_one(TextArea)
                composer.clear()
                log.write("selected transcript text")
                select_first_word(log)
                log.focus()
                await pilot.pause()

                event = MagicMock()
                event.button = 3
                event.widget = log

                screen.on_click(event)

                assert composer.text == ""
                assert log.selection_text != ""
