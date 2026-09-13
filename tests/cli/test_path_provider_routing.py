"""Behavioural routing of command history and model cooldowns (scrappy-i2jo).

These are the regression tests for the injected path provider: each uses two
DISTINCT disposable roots (a disposable HOME kept separate from the injected
provider root), drives the REAL construction path, drives a REAL operation, and
asserts the persisted payload lands under the PROVIDER root.

The negative assertion is SCOPED: a real composition still creates platform
directories and migrates files, so this suite does NOT assert whole-HOME
emptiness. It seeds ONLY the history and cooldown paths under HOME with
sentinels and asserts both that no write landed on them and that their bytes
are unchanged, plus that the provider-root target actually received the write.

Consumers and their construction sites:
- CLI command history        -> CLI._load_command_history via CLI(path_provider=...)
- MainAppScreen history      -> MainAppScreen.__init__ (leaf, required param)
- orchestrator cooldown      -> OrchestratorFactory.create_model_availability_tracker
                                via OrchestratorFactory(path_provider=...)

The composition tests additionally drive create_cli_from_context, create_cli
and ScrappyApp._show_main_screen.
"""

import contextlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from scrappy.cli.core import CLI
from scrappy.cli.screens.main_screen import MainAppScreen
from scrappy.cli.textual.app import ScrappyApp
from scrappy.cli.utils.cli_factory import create_cli_from_context, create_cli
from scrappy.infrastructure.exceptions.failure_kinds import FailureKind
from scrappy.infrastructure.paths import TempPathProvider
from scrappy.orchestrator.factory import OrchestratorFactory
from scrappy.orchestrator.model_selection import (
    ModelAvailabilityTracker,
    ModelHealthState,
)

HISTORY_SENTINEL = b"SENTINEL-HISTORY-do-not-touch"
COOLDOWN_SENTINEL = b"SENTINEL-COOLDOWN-do-not-touch"


def _seed_home_sentinels(home: Path) -> tuple[Path, Path]:
    """Seed HOME's history and cooldown paths so a stray write is detectable.

    Returns the two seeded paths for the scoped negative assertion.
    """
    scrappy_dir = home / ".scrappy"
    scrappy_dir.mkdir(parents=True, exist_ok=True)
    history = scrappy_dir / "command_history"
    cooldown = scrappy_dir / "model_cooldowns.json"
    history.write_bytes(HISTORY_SENTINEL)
    cooldown.write_bytes(COOLDOWN_SENTINEL)
    return history, cooldown


def _assert_home_sentinels_untouched(history: Path, cooldown: Path) -> None:
    """The operation under test must not have written the HOME history/cooldown."""
    assert history.read_bytes() == HISTORY_SENTINEL
    assert cooldown.read_bytes() == COOLDOWN_SENTINEL


@contextlib.contextmanager
def _isolated_cli_env():
    """Patch the CLI's unrelated I/O (orchestrator, io, handlers, store).

    Leaves the command-history seam REAL so the routing under test is exercised
    end to end; only orchestrator/provider/persistence I/O is stubbed.
    """
    store = MagicMock()
    store.get_recent.return_value = []
    handlers = {
        "display": MagicMock(),
        "session_mgr": MagicMock(),
        "codebase": MagicMock(),
        "tasks": MagicMock(),
        "agent_mgr": MagicMock(),
    }
    with (
        patch.object(CLI, "_create_default_orchestrator", return_value=MagicMock()),
        patch.object(CLI, "_create_default_io", return_value=MagicMock()),
        patch("scrappy.cli.core.initialize_cli_handlers", return_value=handlers),
        patch("scrappy.cli.core.create_conversation_store", return_value=store),
    ):
        yield


def mark_unavailable(tracker: ModelAvailabilityTracker, model: str) -> None:
    """Mark a model unhealthy through the canonical health-state API (persists)."""
    tracker.mark(
        model,
        ModelHealthState(
            expires_at=tracker.now() + 3600.0,
            failure_kind=FailureKind.RATE_LIMIT,
            retry_after=3600.0,
        ),
    )


# ---------------------------------------------------------------------------
# Routing, one test per consumer, two distinct disposable roots
# ---------------------------------------------------------------------------

class TestCliCommandHistoryRouting:
    """The CLI's file-backed history follows its injected provider."""

    def test_cli_history_lands_under_provider_root(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        provider_root = tmp_path / "provider"
        home.mkdir()
        provider_root.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        history_sentinel, cooldown_sentinel = _seed_home_sentinels(home)

        provider = TempPathProvider(provider_root)
        with _isolated_cli_env():
            cli = CLI(path_provider=provider)
            cli._load_command_history()
            cli.command_history.add_to_history("real command one")

        target = provider.command_history_file()
        assert target.is_relative_to(provider_root)
        assert target.exists()
        assert "real command one" in target.read_text(encoding="utf-8")
        # Scoped negative: the disposable HOME history/cooldown were not written.
        _assert_home_sentinels_untouched(history_sentinel, cooldown_sentinel)


class TestScreenHistoryRouting:
    """The main screen's history follows its (required) injected provider."""

    def test_screen_history_lands_under_provider_root(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        provider_root = tmp_path / "provider"
        home.mkdir()
        provider_root.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        history_sentinel, cooldown_sentinel = _seed_home_sentinels(home)

        provider = TempPathProvider(provider_root)
        screen = MainAppScreen(
            interactive_mode=None,
            output_adapter=MagicMock(),
            bridge=MagicMock(),
            theme=MagicMock(),
            clipboard=MagicMock(),
            path_provider=provider,
        )
        # Drive a real history write through the screen's own history object.
        screen._history.add_to_history("screen command one")

        target = provider.command_history_file()
        assert target.is_relative_to(provider_root)
        assert target.exists()
        assert "screen command one" in target.read_text(encoding="utf-8")
        _assert_home_sentinels_untouched(history_sentinel, cooldown_sentinel)


class TestCooldownRouting:
    """The orchestrator factory's cooldown store follows its provider."""

    def test_cooldown_lands_under_provider_root(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        provider_root = tmp_path / "provider"
        home.mkdir()
        provider_root.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        history_sentinel, cooldown_sentinel = _seed_home_sentinels(home)

        provider = TempPathProvider(provider_root)
        factory = OrchestratorFactory(path_provider=provider)
        tracker = factory.create_model_availability_tracker()
        # Drive a real cooldown mutation, which persists through the store.
        mark_unavailable(tracker, "groq/model-a")

        target = provider.model_cooldowns_file()
        assert target.is_relative_to(provider_root)
        assert target.exists()
        # The persisted payload records the model we just suppressed.
        assert "groq/model-a" in target.read_text(encoding="utf-8")
        _assert_home_sentinels_untouched(history_sentinel, cooldown_sentinel)

    def test_orchestrator_forwards_provider_to_factory(self):
        """AgentOrchestrator threads path_provider to OrchestratorFactory.

        Without this passthrough the provider the CLI holds could never reach
        the cooldown file. Asserted at the seam so it does not depend on
        selector internals or mock mode.
        """
        provider = MagicMock(name="path_provider")
        from scrappy.orchestrator import core as orchestrator_core

        with patch.object(orchestrator_core, "OrchestratorFactory") as mock_factory:
            orchestrator_core.AgentOrchestrator(
                project_path=".", path_provider=provider
            )

        mock_factory.assert_called_once()
        assert mock_factory.call_args.kwargs["path_provider"] is provider

    def test_cli_forwards_provider_to_orchestrator(self):
        """CLI._create_default_orchestrator passes its provider onward."""
        provider = MagicMock(name="path_provider")
        with (
            patch.object(CLI, "_create_default_io", return_value=MagicMock()),
            patch("scrappy.cli.core.initialize_cli_handlers", return_value={
                "display": MagicMock(), "session_mgr": MagicMock(),
                "codebase": MagicMock(), "tasks": MagicMock(), "agent_mgr": MagicMock(),
            }),
            patch("scrappy.cli.core.AgentOrchestrator") as mock_orch,
        ):
            CLI(path_provider=provider)

        mock_orch.assert_called_once()
        assert mock_orch.call_args.kwargs["path_provider"] is provider


# ---------------------------------------------------------------------------
# Composition coverage for the three production construction sites
# ---------------------------------------------------------------------------

class TestCompositionSitesThreadProvider:
    """The provider passed at each composition root reaches the consumer."""

    def test_create_cli_from_context_threads_provider(self, tmp_path, monkeypatch):
        """create_cli_from_context -> CLI(...) -> history under provider root."""
        home = tmp_path / "home"
        provider_root = tmp_path / "provider"
        home.mkdir()
        provider_root.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        history_sentinel, cooldown_sentinel = _seed_home_sentinels(home)

        provider = TempPathProvider(provider_root)
        ctx = SimpleNamespace(obj={})
        with _isolated_cli_env():
            cli = create_cli_from_context(ctx, io=MagicMock(), path_provider=provider)
            cli.command_history.add_to_history("from context")

        assert cli._path_provider is provider
        target = provider.command_history_file()
        assert target.is_relative_to(provider_root)
        assert target.exists()
        assert "from context" in target.read_text(encoding="utf-8")
        _assert_home_sentinels_untouched(history_sentinel, cooldown_sentinel)

    def test_create_cli_threads_provider(self, tmp_path, monkeypatch):
        """create_cli -> CLI(...) -> history under provider root."""
        home = tmp_path / "home"
        provider_root = tmp_path / "provider"
        home.mkdir()
        provider_root.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        history_sentinel, cooldown_sentinel = _seed_home_sentinels(home)

        provider = TempPathProvider(provider_root)
        with _isolated_cli_env():
            cli = create_cli({}, io=MagicMock(), path_provider=provider)
            cli.command_history.add_to_history("from dict config")

        assert cli._path_provider is provider
        target = provider.command_history_file()
        assert target.is_relative_to(provider_root)
        assert target.exists()
        assert "from dict config" in target.read_text(encoding="utf-8")
        _assert_home_sentinels_untouched(history_sentinel, cooldown_sentinel)

    @pytest.mark.asyncio
    async def test_app_show_main_screen_threads_provider(self, tmp_path, monkeypatch):
        """ScrappyApp._show_main_screen -> MainAppScreen(path_provider=...).

        Mounts a real app (deferred mode) and drives it onto the main chat
        screen, then asserts the mounted screen's history is the provider's.
        """
        from scrappy.cli.screens import MainAppScreen as ScreenType, SetupWizardScreen

        monkeypatch.setenv("SCRAPPY_MOCK_LLM", "1")
        monkeypatch.setattr(
            "scrappy.orchestrator.mock_llm_service.is_mock_mode_enabled",
            lambda: True,
        )
        home = tmp_path / "home"
        provider_root = tmp_path / "provider"
        home.mkdir()
        provider_root.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))

        provider = TempPathProvider(provider_root)

        def create_mock_cli():
            mock_cli = MagicMock()
            mock_cli.interactive_mode = MagicMock()
            mock_cli.interactive_mode.command_router.set_setup_wizard_callback = MagicMock()
            return mock_cli

        app = ScrappyApp(cli_factory=create_mock_cli, path_provider=provider)

        async with app.run_test() as pilot:
            for _ in range(50):
                if isinstance(app.screen, ScreenType):
                    break
                if isinstance(app.screen, SetupWizardScreen):
                    app._show_main_screen()
                await pilot.pause(delay=0.05)

            assert isinstance(app.screen, ScreenType)
            history_file = app.screen._history._history_file
            assert history_file == provider.command_history_file()
            assert history_file.is_relative_to(provider_root)
