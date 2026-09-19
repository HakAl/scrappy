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
and ScrappyApp._show_main_screen, and the cooldown tests drive the REAL
CLI -> AgentOrchestrator -> OrchestratorFactory -> tracker composition (mock
mode off, so the persisted tracker is actually built), stubbing only the
CLI's unrelated I/O and, at the stdlib thread boundary, the semantic-search
model-loading thread.
"""

import contextlib
import json
import threading
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
from scrappy.infrastructure.threading import managed_thread
from scrappy.orchestrator.core import AgentOrchestrator
from scrappy.orchestrator.factory import OrchestratorFactory
from scrappy.orchestrator.model_selection import (
    ModelAvailabilityTracker,
    ModelHealthState,
)
from scrappy.orchestrator.output import NullOutput

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


def _two_roots(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Create a disposable HOME and a DISTINCT provider root; point Path.home at HOME."""
    home = tmp_path / "home"
    provider_root = tmp_path / "provider"
    home.mkdir()
    provider_root.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return home, provider_root


def _expired_cooldown_store(model: str) -> bytes:
    """A persisted cooldown store holding ONE entry that expired long ago.

    Loading such a store prunes the entry and REWRITES the file, so it turns
    tracker construction into an observable write.
    """
    return json.dumps(
        {model: {"expires_at": 1.0, "failure_kind": "rate_limit", "retry_after": None}}
    ).encode("utf-8")


class _UnstartedThread:
    """Stand-in for threading.Thread that never runs its target.

    Used only where the managed-thread module creates its stdlib thread, so
    the semantic-search model loader (unrelated to path routing, and a network
    boundary when the model is not cached) is composed for real but never
    executes. Everything above the stdlib call stays real.
    """

    def __init__(self, *args, **kwargs) -> None:
        self.name = kwargs.get("name", "")

    def start(self) -> None:
        return None

    def join(self, timeout=None) -> None:
        return None

    def is_alive(self) -> bool:
        return False


_threading_without_start = SimpleNamespace(
    Thread=_UnstartedThread, Event=threading.Event, Lock=threading.Lock
)


class _FalsyProvider(TempPathProvider):
    """A real provider that is falsy, to pin the explicit is-None rule."""

    def __bool__(self) -> bool:
        return False


@contextlib.contextmanager
def _isolated_cli_env(*, real_orchestrator: bool = False):
    """Patch the CLI's unrelated I/O (io, handlers, store, and by default the
    orchestrator).

    Leaves the command-history seam REAL so the routing under test is exercised
    end to end. With real_orchestrator=True the default orchestrator is built for
    real too (CLI -> AgentOrchestrator -> OrchestratorFactory -> tracker); the
    only stub on that route is the stdlib thread the managed-thread module would
    start for the semantic-search model loader, which is unrelated to path
    routing. The loader's own composition (callbacks, initializer) stays real.
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
    orchestrator_patch = (
        patch.object(managed_thread, "threading", _threading_without_start)
        if real_orchestrator
        else patch.object(CLI, "_create_default_orchestrator", return_value=MagicMock())
    )
    with (
        orchestrator_patch,
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

    def test_orchestrator_construction_binds_cooldowns_to_provider_not_home(
        self, tmp_path, monkeypatch
    ):
        """AgentOrchestrator(path_provider=...) -> factory -> tracker, mock mode OFF.

        Construction alone is a cooldown WRITE path: the persisted tracker loads
        its store when built and rewrites it after pruning expired entries. So
        an expired entry is seeded at BOTH roots, and a partial-injection
        construction (the shape most orchestrator tests use; it enters the
        factory branch) must prune the PROVIDER store and leave the HOME store
        byte-identical. A tracker bound to the default provider inverts both.
        """
        monkeypatch.delenv("SCRAPPY_MOCK_LLM", raising=False)
        home, provider_root = _two_roots(tmp_path, monkeypatch)
        project = tmp_path / "project"
        project.mkdir()
        provider = TempPathProvider(provider_root)
        expired = _expired_cooldown_store("groq/model-a")
        home_store = home / ".scrappy" / "model_cooldowns.json"
        home_store.parent.mkdir(parents=True)
        home_store.write_bytes(expired)
        provider_store = provider.model_cooldowns_file()
        provider_store.parent.mkdir(parents=True, exist_ok=True)
        provider_store.write_bytes(expired)

        AgentOrchestrator(
            project_path=str(project),
            delegation_manager=MagicMock(),
            output=NullOutput(),
            path_provider=provider,
        )

        # Provider store: loaded, pruned, rewritten as an empty object.
        assert json.loads(provider_store.read_text(encoding="utf-8")) == {}
        # HOME store: never read for pruning, never rewritten.
        assert home_store.read_bytes() == expired

    def test_orchestrator_cooldown_persists_and_reloads_through_provider(
        self, tmp_path, monkeypatch
    ):
        """A cooldown marked through one orchestrator's REAL selector is persisted
        under the provider root and is live again in a second orchestrator built
        with the same provider (mock mode OFF so the real selector and tracker
        are composed)."""
        monkeypatch.delenv("SCRAPPY_MOCK_LLM", raising=False)
        home, provider_root = _two_roots(tmp_path, monkeypatch)
        history_sentinel, cooldown_sentinel = _seed_home_sentinels(home)
        project = tmp_path / "project"
        project.mkdir()
        provider = TempPathProvider(provider_root)

        def build() -> AgentOrchestrator:
            return AgentOrchestrator(
                project_path=str(project),
                delegation_manager=MagicMock(),
                output=NullOutput(),
                path_provider=provider,
            )

        first = build()
        first.model_selector.mark_unhealthy(
            "groq/model-a", FailureKind.RATE_LIMIT, retry_after=3600.0
        )

        target = provider.model_cooldowns_file()
        assert target.is_relative_to(provider_root)
        assert target.exists()
        assert "groq/model-a" in target.read_text(encoding="utf-8")
        _assert_home_sentinels_untouched(history_sentinel, cooldown_sentinel)

        # Reload: a fresh orchestrator on the same provider sees the cooldown.
        # Both models are configured so the difference is the persisted state.
        second = build()
        second.model_selector.update_configured({"groq/model-a", "groq/model-b"})
        assert second.model_selector.is_available("groq/model-b") is True
        assert second.model_selector.is_available("groq/model-a") is False

    def test_cli_default_orchestrator_persists_cooldowns_under_provider_root(
        self, tmp_path, monkeypatch
    ):
        """CLI(path_provider=...) -> _create_default_orchestrator -> AgentOrchestrator
        -> OrchestratorFactory -> tracker: the CLI's provider reaches the cooldown
        file with the orchestrator built for real (mock mode OFF)."""
        monkeypatch.delenv("SCRAPPY_MOCK_LLM", raising=False)
        home, provider_root = _two_roots(tmp_path, monkeypatch)
        history_sentinel, cooldown_sentinel = _seed_home_sentinels(home)
        project = tmp_path / "project"
        project.mkdir()
        # The default orchestrator uses project_path="."; point it at a disposable dir.
        monkeypatch.chdir(project)
        provider = TempPathProvider(provider_root)

        with _isolated_cli_env(real_orchestrator=True):
            cli = CLI(path_provider=provider)
        assert isinstance(cli.orchestrator, AgentOrchestrator)
        # The stand-in held: the semantic-search loader thread never ran.
        assert "SemanticSearchInit" not in {t.name for t in threading.enumerate()}
        cli.orchestrator.model_selector.mark_unhealthy(
            "groq/model-a", FailureKind.RATE_LIMIT, retry_after=3600.0
        )

        target = provider.model_cooldowns_file()
        assert target.is_relative_to(provider_root)
        assert target.exists()
        assert "groq/model-a" in target.read_text(encoding="utf-8")
        _assert_home_sentinels_untouched(history_sentinel, cooldown_sentinel)

    def test_falsy_provider_is_kept_and_routed(self, tmp_path, monkeypatch):
        """The explicit is-None rule: a Protocol-typed provider that is FALSY must
        not trigger a silent default at the CLI, the app, or the orchestrator
        factory. The falsy provider is retained by identity and its cooldown
        member is still the one written."""
        monkeypatch.delenv("SCRAPPY_MOCK_LLM", raising=False)
        home, provider_root = _two_roots(tmp_path, monkeypatch)
        history_sentinel, cooldown_sentinel = _seed_home_sentinels(home)
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.chdir(project)
        provider = _FalsyProvider(provider_root)
        assert not provider

        with _isolated_cli_env(real_orchestrator=True):
            cli = CLI(path_provider=provider)
        assert cli._path_provider is provider
        assert ScrappyApp(cli_factory=MagicMock, path_provider=provider)._path_provider is provider

        cli.orchestrator.model_selector.mark_unhealthy(
            "groq/model-a", FailureKind.RATE_LIMIT, retry_after=3600.0
        )
        target = provider.model_cooldowns_file()
        assert target.is_relative_to(provider_root)
        assert "groq/model-a" in target.read_text(encoding="utf-8")
        _assert_home_sentinels_untouched(history_sentinel, cooldown_sentinel)


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
