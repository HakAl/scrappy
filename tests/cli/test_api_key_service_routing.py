"""Behavioural routing of the API key configuration service (scrappy-i2jo).

Mirrors tests/cli/test_path_provider_routing.py for the second seam: the
service is resolved ONCE at the composition root and threaded to every
consumer, so no class body, screen, handler or module function builds its own
from the default user config path.

Each test injects a double, drives the REAL operation, and asserts the
operation read THAT service. The tripwire is armed wherever a missed seam
would fall back to the default path; it rejects reads AND writes at the
persistence boundary, so a regression fails loudly instead of quietly reading
the developer's profile.

The refresh-boundary cases (the last class) use the REAL service over
disposable persistence, because they are about cache semantics that a double
cannot model: /models and status re-read the file, everything else serves the
startup snapshot.
"""

import contextlib
import json
import threading
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from textual.app import App

from scrappy.cli.command_router import CommandRouter
from scrappy.cli.core import CLI
from scrappy.cli.display import CLIDisplay
from scrappy.cli.interactive_banner import display_banner, display_banner_status
from scrappy.cli.screens.wizard_screen import SetupWizardScreen
from scrappy.cli.setup_wizard import SetupWizard
from scrappy.cli.textual.app import ScrappyApp
from scrappy.cli.utils.cli_factory import create_cli, create_cli_from_context
from scrappy.infrastructure.config.api_keys import ApiKeyConfigService
from scrappy.infrastructure.paths import TempPathProvider
from scrappy.infrastructure.persistence.json_persistence import JSONPersistence
from scrappy.infrastructure.threading import managed_thread
from scrappy.orchestrator.api_key_composition import create_api_key_service
from tests.cli.helpers import MockApiKeyConfigService, MockKeyValidationService
from tests.default_path_tripwire import TRIPWIRE_MESSAGE, armed_default_path_tripwire

GROQ_KEY = "GROQ_API_KEY"
CEREBRAS_KEY = "CEREBRAS_API_KEY"
GROQ_CHAT_MODEL = "groq/llama-3.3-70b-versatile"


class _UnstartedThread:
    """Stand-in for threading.Thread that never runs its target.

    Used only where the managed-thread module creates its stdlib thread, so the
    semantic-search model loader (unrelated to key routing, and a network
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


class _FalsyApiKeyService(MockApiKeyConfigService):
    """A real double that is falsy, to pin the explicit is-None rule."""

    def __bool__(self) -> bool:
        return False


@contextlib.contextmanager
def _isolated_cli_env(*, real_orchestrator: bool = True):
    """Patch the CLI's unrelated I/O, leaving the key-service seam REAL.

    With real_orchestrator=True the default orchestrator is built for real
    (CLI -> AgentOrchestrator -> OrchestratorFactory), so the service can be
    followed all the way down; the only stubs on that route are the stdlib
    thread the semantic-search loader would start and the LiteLLM router, both
    unrelated to key routing and both slow or network-bound.
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
        patch(
            "scrappy.orchestrator.factory.create_litellm_router",
            return_value=MagicMock(),
        ),
        patch.object(CLI, "_create_default_io", return_value=MagicMock()),
        patch("scrappy.cli.core.initialize_cli_handlers", return_value=handlers),
        patch("scrappy.cli.core.create_conversation_store", return_value=store),
    ):
        yield


@pytest.fixture
def tripwire(tmp_path, monkeypatch):
    """Reject any read or write of the default user config path."""
    with armed_default_path_tripwire(tmp_path, monkeypatch) as sentinel:
        yield sentinel


def _groq_double() -> MockApiKeyConfigService:
    """A double that is the ONLY holder of a groq key."""
    return MockApiKeyConfigService(keys={GROQ_KEY: "gsk-injected"})


class _RecordingIO:
    """Minimal IO that captures what the banner rendered."""

    def __init__(self) -> None:
        self.printed: list[str] = []
        self.output_sink = None
        self._console = SimpleNamespace(
            print=lambda text: self.printed.append(str(text))
        )

    @property
    def console(self):
        return self._console

    def echo(self, text: str = "") -> None:
        self.printed.append(text)

    def secho(self, text: str = "", **kwargs) -> None:
        self.printed.append(text)

    @property
    def theme(self):
        return SimpleNamespace(
            warning="yellow",
            error="red",
            success="green",
            primary="cyan",
            secondary="blue",
            muted="grey",
        )

    def rendered(self) -> str:
        return " ".join(self.printed)

    def providers_line(self) -> str:
        """The one banner line listing configured providers.

        Scoped deliberately: the guidance line names providers too, so a
        whole-output search could never tell an unconfigured provider from a
        mentioned one.
        """
        return next(line for line in self.printed if "Providers:" in line)


class TestTripwireDetectsDefaultPathAccess:
    """The instrument itself, before anything relies on it."""

    def test_default_path_read_trips_the_wire(self, tripwire):
        """A default-path service that READS raises, even though the file is absent.

        This is the case the absent-file sentinel could not catch: load()
        returns None for a missing file, so only observing the boundary works.
        """
        assert not tripwire.exists()

        with pytest.raises(AssertionError, match=TRIPWIRE_MESSAGE):
            create_api_key_service().get_key(GROQ_KEY)

    def test_default_path_write_trips_the_wire(self, tripwire):
        """The save arm is armed too, independently of the read arm."""
        with pytest.raises(AssertionError, match=TRIPWIRE_MESSAGE):
            JSONPersistence(str(tripwire)).save({"api_keys": {}})


class TestAppMountUsesInjectedService:
    """ScrappyApp.on_mount's two reads follow the injected service on both routes."""

    @pytest.mark.asyncio
    async def test_non_mock_mount_reads_injected_service_and_shows_wizard(
        self, tripwire, tmp_path, monkeypatch
    ):
        """T3a: no keys and disclaimer not acknowledged -> wizard, both reads
        served by the double."""
        monkeypatch.delenv("SCRAPPY_MOCK_LLM", raising=False)
        monkeypatch.setattr(
            "scrappy.orchestrator.mock_llm_service.is_mock_mode_enabled",
            lambda: False,
        )
        double = MockApiKeyConfigService()
        double._disclaimer_acknowledged = False

        app = ScrappyApp(
            cli_factory=lambda: MagicMock(),
            path_provider=TempPathProvider(tmp_path),
            api_key_service=double,
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, SetupWizardScreen)

        assert "has_any_key" in double.calls
        assert "is_disclaimer_acknowledged" in double.calls

    @pytest.mark.asyncio
    async def test_mock_mode_mount_still_reads_only_the_injected_service(
        self, tripwire, tmp_path, monkeypatch
    ):
        """T3b: mock mode shows the main screen, but both reads still happened
        (they precede the flag) and both went to the injected service."""
        from scrappy.cli.screens import MainAppScreen

        monkeypatch.setenv("SCRAPPY_MOCK_LLM", "1")
        monkeypatch.setattr(
            "scrappy.orchestrator.mock_llm_service.is_mock_mode_enabled",
            lambda: True,
        )
        double = _groq_double()

        app = ScrappyApp(
            cli_factory=lambda: MagicMock(),
            path_provider=TempPathProvider(tmp_path),
            api_key_service=double,
        )

        async with app.run_test() as pilot:
            for _ in range(50):
                if isinstance(app.screen, MainAppScreen):
                    break
                await pilot.pause(delay=0.05)
            assert isinstance(app.screen, MainAppScreen)

        assert "has_any_key" in double.calls
        assert "is_disclaimer_acknowledged" in double.calls


class TestWizardRoutingReadsAndWrites:
    """Both wizard entry points hand their service to the wizard, and the
    wizard's save path writes through it."""

    @pytest.mark.asyncio
    async def test_screen_builds_wizard_on_injected_service_and_saves_through_it(
        self, tripwire
    ):
        """T4 (screen route): the mounted screen's wizard holds the injected
        service, and driving the existing key-save entry writes to it."""
        double = MockApiKeyConfigService()
        io = MagicMock()
        io.output_sink = MagicMock()
        io.prompt.return_value = "valid_test_key_123456"

        screen = SetupWizardScreen(
            io=io,
            key_validator=MockKeyValidationService((True, None)),
            clipboard=MagicMock(),
            config_service=double,
        )

        class _Host(App):
            def compose(self):
                yield screen

        async with _Host().run_test() as pilot:
            await pilot.pause()
            wizard = screen._wizard
            assert wizard is not None
            assert wizard._config_service is double

            # The same save entry the wizard suite exercises.
            assert wizard._configure_provider("groq") is True

        assert double.keys[GROQ_KEY] == "valid_test_key_123456"
        assert double.save_called
        assert "set_key" in double.calls

    def test_router_builds_wizard_on_injected_service(self, tripwire):
        """T4 (router route): /setup in CLI mode passes the router's service."""
        double = MockApiKeyConfigService()
        router = CommandRouter(
            io=MagicMock(),
            orchestrator=MagicMock(),
            session_context=MagicMock(),
            display=MagicMock(),
            session_mgr=MagicMock(),
            codebase=MagicMock(),
            tasks=MagicMock(),
            agent_mgr=MagicMock(),
            session_saver=MagicMock(),
            model_selection=MagicMock(),
            api_key_service=double,
        )

        with patch.object(SetupWizard, "run", autospec=True) as run_mock:
            assert router._handle_setup("") is True

        wizard = run_mock.call_args[0][0]
        assert wizard._config_service is double


class TestWizardSessionReadsCurrentDiskState:
    """A wizard session starts from what is on disk, not from the snapshot the
    long-lived service cached at startup.

    The service writes the WHOLE config back on every set_key, so a session
    that opened on a stale snapshot would silently revert a key another process
    added in the meantime. Real persistence over a disposable file, because this
    is cache semantics a double cannot model; the tripwire is armed so a session
    that reaches the default path instead fails loudly rather than writing there.
    """

    OTHER_KEY = CEREBRAS_KEY
    THIRD_KEY = "OPENROUTER_API_KEY"

    def _stale_service(self, tmp_path: Path) -> ApiKeyConfigService:
        """A service warmed on a one-key file that then grows a second key."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"api_keys": {GROQ_KEY: "gsk-x"}}))
        service = ApiKeyConfigService(
            JSONPersistence(str(config_file)),
            (GROQ_KEY, self.OTHER_KEY, self.THIRD_KEY),
        )
        assert service.get_key(GROQ_KEY) == "gsk-x"  # warms the cache

        # Another process adds a key after this service was built.
        config_file.write_text(json.dumps({
            "api_keys": {GROQ_KEY: "gsk-x", self.OTHER_KEY: "csk-y"}
        }))
        assert service.get_key(self.OTHER_KEY) is None  # the snapshot is stale
        return service

    def _stored_keys(self, tmp_path: Path) -> dict:
        return json.loads((tmp_path / "config.json").read_text())["api_keys"]

    @pytest.mark.asyncio
    async def test_screen_session_does_not_revert_an_external_key(
        self, tripwire, tmp_path
    ):
        """Saving through the screen-mounted wizard keeps the external key."""
        service = self._stale_service(tmp_path)

        io = MagicMock()
        io.output_sink = MagicMock()
        screen = SetupWizardScreen(
            io=io,
            key_validator=MockKeyValidationService((True, None)),
            clipboard=MagicMock(),
            config_service=service,
        )

        class _Host(App):
            def compose(self):
                yield screen

        async with _Host().run_test() as pilot:
            await pilot.pause()
            screen._wizard._save_key(self.THIRD_KEY, "sk-or-z-0123456789")

        stored = self._stored_keys(tmp_path)
        assert stored.get(self.THIRD_KEY) == "sk-or-z-0123456789"
        assert stored.get(self.OTHER_KEY) == "csk-y"

    def test_router_session_does_not_revert_an_external_key(self, tripwire, tmp_path):
        """Saving through the /setup CLI-mode wizard keeps the external key."""
        service = self._stale_service(tmp_path)
        router = CommandRouter(
            io=MagicMock(),
            orchestrator=MagicMock(),
            session_context=MagicMock(),
            display=MagicMock(),
            session_mgr=MagicMock(),
            codebase=MagicMock(),
            tasks=MagicMock(),
            agent_mgr=MagicMock(),
            session_saver=MagicMock(),
            model_selection=MagicMock(),
            api_key_service=service,
        )

        with patch.object(SetupWizard, "run", autospec=True) as run_mock:
            assert router._handle_setup("") is True
        run_mock.call_args[0][0]._save_key(self.THIRD_KEY, "sk-or-z-0123456789")

        stored = self._stored_keys(tmp_path)
        assert stored.get(self.THIRD_KEY) == "sk-or-z-0123456789"
        assert stored.get(self.OTHER_KEY) == "csk-y"


class TestBannerUsesInjectedService:
    """The banner names the injected double's providers, through both entries."""

    def test_status_lists_injected_providers(self, tripwire, tmp_path):
        """T5: display_banner_status reads the service it is given."""
        io = _RecordingIO()

        display_banner_status(
            io,
            api_key_service=_groq_double(),
            path_provider=TempPathProvider(tmp_path),
        )

        providers = io.providers_line()
        assert "Groq" in providers
        assert "Cerebras" not in providers

    def test_wrapper_forwards_the_service(self, tripwire, tmp_path):
        """T5: display_banner has no hidden default either; it forwards."""
        io = _RecordingIO()

        display_banner(
            io,
            api_key_service=_groq_double(),
            path_provider=TempPathProvider(tmp_path),
        )

        assert "Groq" in io.providers_line()


class TestDisplayUsesInjectedService:
    """CLIDisplay.list_models reads its injected service."""

    def test_list_models_lists_the_doubles_models(self, tripwire):
        """T6: only the double knows the groq key, so only groq models list."""
        io = _RecordingIO()
        display = CLIDisplay(
            MagicMock(), datetime.now(), io, api_key_service=_groq_double()
        )

        display.list_models()

        rendered = io.rendered()
        assert GROQ_CHAT_MODEL in rendered
        assert "cerebras/" not in rendered


class TestCompositionSitesThreadService:
    """The service passed at each composition root reaches the consumers."""

    def test_create_cli_from_context_threads_service(self, tripwire):
        """T8: create_cli_from_context -> CLI -> orchestrator."""
        double = _groq_double()
        ctx = SimpleNamespace(obj={})

        with _isolated_cli_env():
            cli = create_cli_from_context(
                ctx, io=MagicMock(), api_key_service=double
            )

        assert cli._api_key_service is double
        assert cli.orchestrator._api_key_service is double

    def test_create_cli_threads_service(self, tripwire):
        """T8: create_cli -> CLI -> orchestrator."""
        double = _groq_double()

        with _isolated_cli_env():
            cli = create_cli({}, io=MagicMock(), api_key_service=double)

        assert cli._api_key_service is double
        assert cli.orchestrator._api_key_service is double

    def test_app_holds_the_injected_service(self, tripwire, tmp_path):
        """T8: the app the root builds holds the same instance."""
        double = _groq_double()

        app = ScrappyApp(
            cli_factory=MagicMock,
            path_provider=TempPathProvider(tmp_path),
            api_key_service=double,
        )

        assert app._api_key_service is double

    def test_interactive_mode_threads_service_to_its_app(self, tripwire):
        """T8: the immediate-mode route carries the service too, so the app it
        builds does not fall back to a second, default-path service."""
        double = _groq_double()

        with _isolated_cli_env(real_orchestrator=False):
            cli = CLI(api_key_service=double)
            cli.io.output_sink = MagicMock()
            mode = cli._create_interactive_mode()

        assert mode._api_key_service is double

        with (
            patch("scrappy.cli.textual_interactive.ScrappyApp") as app_cls,
            patch("scrappy.cli.textual_interactive.create_textual_runtime_session"),
            patch("scrappy.cli.textual_interactive.wire_textual_runtime"),
        ):
            mode.run()

        assert app_cls.call_args.kwargs["api_key_service"] is double


class TestFalsyServiceIsKeptAndRouted:
    """The explicit is-None rule at all three composition roots."""

    @pytest.mark.parametrize("root", ["cli", "app", "orchestrator"])
    def test_falsy_service_is_kept(self, root, tripwire, tmp_path):
        """T9: a Protocol-typed service that is FALSY must not trigger a silent
        default at the CLI, the app, or the orchestrator."""
        from scrappy.orchestrator.core import AgentOrchestrator

        service = _FalsyApiKeyService()
        assert not service

        if root == "cli":
            with _isolated_cli_env(real_orchestrator=False):
                held = CLI(api_key_service=service)._api_key_service
        elif root == "app":
            held = ScrappyApp(
                cli_factory=MagicMock,
                path_provider=TempPathProvider(tmp_path),
                api_key_service=service,
            )._api_key_service
        else:
            with patch(
                "scrappy.orchestrator.factory.create_litellm_router",
                return_value=MagicMock(),
            ):
                held = AgentOrchestrator(
                    project_path=".",
                    enable_semantic_search=False,
                    path_provider=TempPathProvider(tmp_path),
                    api_key_service=service,
                )._api_key_service

        assert held is service


class TestRefreshBoundaryPreservesFreshReads:
    """The two consumers that used to build a fresh service per call still see
    external edits; everything else serves the startup snapshot.

    Each case owns its service: reload() refreshes the shared instance for every
    consumer, so sharing one service between the cases would let one command's
    reload hide a missing reload in the other.
    """

    def _service(self, tmp_path: Path, key: str) -> ApiKeyConfigService:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"api_keys": {GROQ_KEY: key}}))
        return ApiKeyConfigService(
            JSONPersistence(str(config_file)), (GROQ_KEY, CEREBRAS_KEY)
        )

    def _rewrite(self, tmp_path: Path, key: str) -> None:
        """Rewrite the groq key AND add a provider that was not there before.

        The added provider is what makes the assertion consumer-visible: the
        key value alone could be checked on the service, which a reload placed
        AFTER the read would still satisfy.
        """
        (tmp_path / "config.json").write_text(
            json.dumps({"api_keys": {GROQ_KEY: key, CEREBRAS_KEY: "csk-added"}})
        )

    def test_list_models_sees_an_external_edit(self, tmp_path):
        """T10a: /models re-reads, so a provider added after startup is RENDERED."""
        service = self._service(tmp_path, "gsk-old")
        io = _RecordingIO()
        display = CLIDisplay(MagicMock(), datetime.now(), io, api_key_service=service)

        assert service.get_key(GROQ_KEY) == "gsk-old"  # warms the cache

        display.list_models()
        assert "cerebras/" not in io.rendered()  # the provider is not configured yet

        self._rewrite(tmp_path, "gsk-new")
        assert service.get_key(GROQ_KEY) == "gsk-old"  # the edit alone is invisible

        io.printed.clear()
        display.list_models()

        assert "cerebras/" in io.rendered()
        assert GROQ_CHAT_MODEL in io.rendered()
        assert service.get_key(GROQ_KEY) == "gsk-new"

    def test_status_sees_an_external_edit(self, tmp_path):
        """T10b: status re-reads, so a provider added after startup is REPORTED,
        independently of the /models path."""
        from scrappy.orchestrator.core import AgentOrchestrator

        service = self._service(tmp_path, "gsk-old")

        with patch(
            "scrappy.orchestrator.factory.create_litellm_router",
            return_value=MagicMock(),
        ):
            orchestrator = AgentOrchestrator(
                project_path=".",
                enable_semantic_search=False,
                path_provider=TempPathProvider(tmp_path / "provider"),
                api_key_service=service,
            )

        assert service.get_key(GROQ_KEY) == "gsk-old"  # warms the cache

        assert not self._reported_cerebras_models(orchestrator.status())

        self._rewrite(tmp_path, "gsk-new")
        assert service.get_key(GROQ_KEY) == "gsk-old"  # the edit alone is invisible

        assert self._reported_cerebras_models(orchestrator.status())
        assert service.get_key(GROQ_KEY) == "gsk-new"

    @staticmethod
    def _reported_cerebras_models(status: dict) -> list:
        return [
            model for model in status["configured_models"]
            if str(model.get("model_id", "")).startswith("cerebras/")
        ]
