"""Enter must observe exactly the text preceding it in the composer's queue."""

from datetime import datetime
from unittest.mock import Mock

import pytest
from rich.console import Console
from textual import events

from scrappy.cli.agent_manager import CLIAgentManager
from scrappy.cli.codebase import CLICodebaseAnalysis
from scrappy.cli.command_router import CommandRouter
from scrappy.cli.display import CLIDisplay
from scrappy.cli.input_handler import InputHandler
from scrappy.cli.interactive import InteractiveMode
from scrappy.cli.screens.chat_surface import ChatSurface
from scrappy.cli.screens.wizard_screen import SetupWizardScreen
from scrappy.cli.session_context import SessionContext
from scrappy.cli.state_manager import PlanStateManager
from scrappy.cli.tasks import CLITaskExecution
from scrappy.cli.textual.app import ScrappyApp
from scrappy.cli.textual.output_adapter import TextualOutputAdapter
from scrappy.cli.unified_io import UnifiedIO
from scrappy.infrastructure.paths import TempPathProvider
from tests.cli.helpers import MockApiKeyConfigService, MockKeyValidationService


def make_app(tmp_path, monkeypatch):
    """Use real command routing/display; isolate provider and config boundaries."""
    monkeypatch.setenv("SCRAPPY_MOCK_LLM", "1")
    paths = TempPathProvider(tmp_path)
    assert not paths.command_history_file().exists()
    config = MockApiKeyConfigService()
    adapter = TextualOutputAdapter()
    io = UnifiedIO(output_sink=adapter)
    provider = Mock()
    context = SessionContext(auto_save=False)
    state = PlanStateManager()
    display = CLIDisplay(provider, datetime(2026, 1, 1), io, config)
    tasks = CLITaskExecution(provider, io)
    router = CommandRouter(
        io=io,
        orchestrator=provider,
        session_context=context,
        display=display,
        # These paths are unused by /help and /verbose; do not replace routing.
        session_mgr=None,
        codebase=CLICodebaseAnalysis(provider, io),
        tasks=tasks,
        agent_mgr=CLIAgentManager(provider, io),
        session_saver=None,
        model_selection=None,
        state_manager=state,
        api_key_service=config,
        path_provider=paths,
    )
    mode = InteractiveMode(
        io=io,
        orchestrator=provider,
        session_context=context,
        state_manager=state,
        input_handler=InputHandler(io),
        command_router=router,
        display=display,
        tasks=tasks,
        logger=None,
        session_saver=None,
    )
    app = ScrappyApp(
        interactive_mode=mode,
        output_adapter=adapter,
        path_provider=paths,
        api_key_service=config,
        clipboard=Mock(),
        mouse_policy=Mock(),
    )
    return app, io


def packed(app, *keys):
    """Queue the entire batch without yielding to either App or widget tasks."""
    for key in keys:
        app.post_message(events.Key(key, key if len(key) == 1 else None))


def transcript(surface):
    """Render the actual transcript entries, including Rich command tables."""
    console = Console(width=100, color_system=None)
    with console.capture() as capture:
        for entry in surface.output.transcript_model.entries():
            console.print(entry.renderable)
    return capture.get()


async def wizard_quit(tmp_path, monkeypatch, typed):
    app, io = make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        config = MockApiKeyConfigService()
        config._disclaimer_acknowledged = False
        screen = SetupWizardScreen(
            io=io,
            key_validator=MockKeyValidationService(),
            clipboard=Mock(),
            config_service=config,
        )
        await app.push_screen(screen)
        await pilot.pause()
        surface = screen.query_one(ChatSurface)
        assert screen._wizard.current_prompt == "Type 'ok' to continue, or 'q' to quit"
        if typed:
            await pilot.press("q", "enter")
        else:
            packed(app, "q", "enter")
        await pilot.pause()
        assert app.screen is not screen
        assert not screen._wizard.is_active
        assert surface.input.text == ""
        assert "Please type 'ok'" not in transcript(surface)


@pytest.mark.asyncio
async def test_t1_wizard_packed_quit(tmp_path, monkeypatch):
    await wizard_quit(tmp_path, monkeypatch, typed=False)


async def main_help(tmp_path, monkeypatch, typed=False, trailing=False):
    app, _ = make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        surface = app.screen.query_one(ChatSurface)
        surface.clear_output()
        if typed:
            await pilot.press(*"/help", "enter")
        else:
            packed(app, *"/help", "enter", *(["X"] if trailing else []))
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert transcript(surface).count("Available Commands") == 1
        assert surface.input.text == ("X" if trailing else "")


@pytest.mark.asyncio
async def test_t2_main_packed_help(tmp_path, monkeypatch):
    await main_help(tmp_path, monkeypatch)


@pytest.mark.asyncio
@pytest.mark.parametrize("screen", ["wizard", "main"])
async def test_t3_typed_controls(tmp_path, monkeypatch, screen):
    if screen == "wizard":
        await wizard_quit(tmp_path, monkeypatch, typed=True)
    else:
        await main_help(tmp_path, monkeypatch, typed=True)


@pytest.mark.asyncio
async def test_t4_packed_trailing_text(tmp_path, monkeypatch):
    await main_help(tmp_path, monkeypatch, trailing=True)


@pytest.mark.asyncio
async def test_t5_two_packed_submissions_in_history(tmp_path, monkeypatch):
    # /verbose toggles only session-local state and emits text, with no provider I/O.
    second = "/verbose"
    app, _ = make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        surface = app.screen.query_one(ChatSurface)
        await pilot.press("up")
        assert surface.input.text == ""
        packed(app, *"/help", "enter", *second, "enter")
        await pilot.pause()
        assert surface.input.text == ""
        await pilot.press("up")
        assert surface.input.text == second
        await pilot.press("up")
        assert surface.input.text == "/help"
        await pilot.press("up")
        assert surface.input.text == "/help"
        await app.workers.wait_for_complete()


@pytest.mark.asyncio
async def test_t6_not_ready_preserves_text(tmp_path, monkeypatch):
    app, _ = make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        surface = app.screen.query_one(ChatSurface)
        surface.clear_output()
        app.ready = False
        packed(app, *"abc", "enter", "d")
        await pilot.pause()
        assert surface.input.text == "abcd"
        assert transcript(surface) == ""
        assert not list(app.workers)


@pytest.mark.asyncio
async def test_t7_shift_enter_unchanged(tmp_path, monkeypatch):
    app, _ = make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        surface = app.screen.query_one(ChatSurface)
        await pilot.press("a", "shift+enter", "b")
        await pilot.pause()
        assert surface.input.text == "ab"
        assert not list(app.workers)


@pytest.mark.asyncio
async def test_t8_transcript_focus_enter_unchanged(tmp_path, monkeypatch):
    app, _ = make_app(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        surface = app.screen.query_one(ChatSurface)
        surface.clear_output()
        surface.input.text = "/help"
        surface.output.focus()
        await pilot.pause()
        assert surface.output.has_focus
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert transcript(surface).count("Available Commands") == 1
        assert surface.input.text == ""
