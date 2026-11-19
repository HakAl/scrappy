"""First-run startup outcomes through the real Textual lifecycle.

Harness: test_app_mouse_routing.py (ScrappyApp.run_test and injected service),
plus test_wizard.py (wizard screen and fake CLI IO). The synthetic key matches
error_handler's sk-[a-zA-Z0-9_-]{20,} pattern; /Users/someone matches its home
path pattern. Only external composition boundaries are replaced.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

from click.testing import CliRunner
import pytest

from scrappy.cli import commands
from scrappy.cli.screens import SetupWizardScreen
from scrappy.cli.textual.app import ScrappyApp
from scrappy.cli.textual.output_adapter import TextualOutputAdapter
from scrappy.cli.unified_io import UnifiedIO
from scrappy.cli.widgets import SelectableLog
from scrappy.infrastructure.paths import TempPathProvider
from tests.cli.helpers import MockApiKeyConfigService


SECRET = "sk-ant-api03-FAKEFAKEFAKEFAKE"


@pytest.fixture(autouse=True)
def real_startup_mode(monkeypatch):
    monkeypatch.delenv("SCRAPPY_MOCK_LLM", raising=False)


def failing_factory():
    raise RuntimeError(f"boom {SECRET} in /Users/someone/x")


def make_app(tmp_path, factory, *, configured=False):
    service = MockApiKeyConfigService({"GROQ_API_KEY": "fake-key"} if configured else {})
    service._disclaimer_acknowledged = configured
    return ScrappyApp(
        cli_factory=factory,
        path_provider=TempPathProvider(tmp_path),
        api_key_service=service,
    )


@pytest.mark.asyncio
async def test_first_run_failure_exits_with_sanitized_output(tmp_path, capsys):
    app = make_app(tmp_path, failing_factory)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Bounded red signal: baseline is still live here; no key input or timer.
        assert app.return_code == 1
        assert not app.is_running
        assert app.ready is False
        assert not any(isinstance(screen, SetupWizardScreen) for screen in app.screen_stack)
    emitted = capsys.readouterr().err
    print(f"T1 real shutdown stderr: {emitted!r}")
    assert "Scrappy could not start first-run setup." in emitted
    assert "RuntimeError: boom" in emitted
    assert "First-run setup did not complete. Fix the problem above and run scrappy again." in emitted
    assert SECRET not in emitted
    assert "/Users/someone" not in emitted


@pytest.mark.asyncio
async def test_first_run_success_shows_wizard(tmp_path):
    # Minimal factory product; real InteractiveMode and runtime wiring run.
    router = Mock()
    orchestrator = SimpleNamespace(
        cancel_all_background_tasks=lambda: 0,
        llm_service=SimpleNamespace(close=lambda: None),
    )
    adapter = TextualOutputAdapter()
    cli = SimpleNamespace(
        io=UnifiedIO(output_sink=adapter), orchestrator=orchestrator, session_context=Mock(),
        state_manager=Mock(), input_handler=Mock(), display=Mock(), tasks=Mock(),
        logger=Mock(), _code_root=str(tmp_path), agent_mgr=None,
        _create_command_router=lambda: router,
        reinitialize_handlers_with_bridge=lambda *args: None,
    )
    app = make_app(tmp_path, lambda: cli)
    adapter.bind_event_sink(app.tui_event_sink)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, SetupWizardScreen)
        assert app.is_running
        assert app.return_code is None
        assert app.ready is True


@pytest.mark.asyncio
async def test_configured_failure_keeps_existing_transcript(tmp_path):
    app = make_app(tmp_path, failing_factory, configured=True)
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        output = app.screen.query_one(SelectableLog)
        assert any("Startup error:" in str(entry.renderable)
                   for entry in output.transcript_model.entries())
        assert app.is_running
        assert app.return_code is None


@pytest.mark.parametrize("return_code", [1, 0])
def test_click_propagates_app_return_code(tmp_path, monkeypatch, return_code):
    class FinishedApp:
        def __init__(self, **kwargs):
            self.return_code = None

        def run(self):
            self.return_code = return_code

    monkeypatch.setattr("scrappy.cli.textual.app.ScrappyApp", FinishedApp)
    monkeypatch.setattr(
        "scrappy.infrastructure.paths.create_default_path_provider",
        lambda *args: TempPathProvider(tmp_path),
    )
    monkeypatch.setattr(
        "scrappy.orchestrator.api_key_composition.create_api_key_service",
        MockApiKeyConfigService,
    )
    result = CliRunner().invoke(commands.cli, [], obj={commands.CONFIG_CAPTURE_KEY: None})
    assert result.exit_code == return_code, result.output


@pytest.mark.asyncio
async def test_real_run_failure_emits_sanitized_stderr(tmp_path, capsys):
    app = make_app(tmp_path, failing_factory)
    async with asyncio.timeout(10):
        await app.run_async(headless=True)
    emitted = capsys.readouterr().err
    print(f"T5 real run_async stderr: {emitted!r}")
    assert "Scrappy could not start first-run setup." in emitted
    assert "RuntimeError: boom" in emitted
    assert SECRET not in emitted
    assert "/Users/someone" not in emitted
    assert app.return_code == 1


@pytest.mark.asyncio
async def test_real_run_shutdown_cancels_extra_task(tmp_path):
    # Public on_mount lifecycle hook starts the unrelated task before exiting.
    class ShutdownApp(ScrappyApp):
        async def on_mount(self):
            self.extra_task = asyncio.create_task(asyncio.sleep(3600))
            self.exit()

    app = ShutdownApp(
        cli_factory=failing_factory,
        path_provider=TempPathProvider(tmp_path),
        api_key_service=MockApiKeyConfigService({}),
    )
    async with asyncio.timeout(10):
        await app.run_async(headless=True)
    assert app.extra_task.cancelled()
