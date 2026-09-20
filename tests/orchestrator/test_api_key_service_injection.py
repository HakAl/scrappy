"""Behavioural routing of the API key service through the orchestrator (scrappy-i2jo).

The factory and the orchestrator each used to build their own service from the
default user config path. These tests inject one service and assert the real
operations read THAT service: the model selector's configured set, the LLM
service the factory hands the router, and the orchestrator's refresh/status
paths.

The tripwire is armed throughout, so a missed seam that falls back to the
default path fails loudly at the persistence boundary instead of quietly
reading the developer's profile. A disposable path provider keeps the
unrelated user-level files (cooldowns, logs) out of the profile too.
"""

from unittest.mock import MagicMock, patch

import pytest

from scrappy.infrastructure.paths import TempPathProvider
from scrappy.orchestrator.core import AgentOrchestrator
from scrappy.orchestrator.factory import OrchestratorFactory
from scrappy.orchestrator.litellm_service import LiteLLMService
from scrappy.orchestrator.output import NullOutput
from tests.cli.helpers import MockApiKeyConfigService
from tests.default_path_tripwire import armed_default_path_tripwire

GROQ_CHAT_MODEL = "groq/llama-3.3-70b-versatile"
CEREBRAS_CHAT_MODEL = "cerebras/llama-3.3-70b"


@pytest.fixture
def tripwire(tmp_path, monkeypatch):
    """Reject any read or write of the default user config path."""
    with armed_default_path_tripwire(tmp_path, monkeypatch) as sentinel:
        yield sentinel


def _groq_double() -> MockApiKeyConfigService:
    """A double that is the ONLY holder of a groq key."""
    return MockApiKeyConfigService(keys={"GROQ_API_KEY": "gsk-injected"})


class TestFactoryUsesInjectedService:
    """OrchestratorFactory's two default-path sites follow the injected service."""

    def test_model_selector_and_llm_service_use_injected_service(
        self, tripwire, tmp_path, monkeypatch
    ):
        """T1: non-mock, BOTH factory sites.

        Site 1: create_model_selector marks the double's groq model configured
        and nothing else. Site 2: create_llm_service hands the SAME instance to
        LiteLLMService.
        """
        monkeypatch.delenv("SCRAPPY_MOCK_LLM", raising=False)
        double = _groq_double()
        factory = OrchestratorFactory(
            api_key_service=double, path_provider=TempPathProvider(tmp_path)
        )

        selector = factory.create_model_selector()
        assert selector.is_configured(GROQ_CHAT_MODEL)
        assert not selector.is_configured(CEREBRAS_CHAT_MODEL)

        with patch(
            "scrappy.orchestrator.factory.create_litellm_router",
            return_value=MagicMock(),
        ):
            service = factory.create_llm_service(
                NullOutput(), MagicMock(), MagicMock()
            )

        assert isinstance(service, LiteLLMService)
        assert service._api_key_service is double

    def test_mock_mode_returns_mocks_without_touching_the_service(
        self, tripwire, tmp_path, monkeypatch
    ):
        """T2: the early mock returns are a real bypass -- zero calls on the double."""
        monkeypatch.setenv("SCRAPPY_MOCK_LLM", "1")
        double = _groq_double()
        factory = OrchestratorFactory(
            api_key_service=double, path_provider=TempPathProvider(tmp_path)
        )

        selector = factory.create_model_selector()
        service = factory.create_llm_service(NullOutput(), MagicMock(), MagicMock())

        assert not isinstance(service, LiteLLMService)
        assert selector.__class__.__name__ == "MockModelSelectionService"
        assert double.calls == []


class TestOrchestratorUsesInjectedService:
    """AgentOrchestrator's refresh and status paths read the injected service."""

    def test_refresh_and_status_read_the_injected_service(
        self, tripwire, tmp_path, monkeypatch
    ):
        """T7: a key added to the injected double AFTER construction reaches both
        the refresh path and status, proving each reads that service rather than
        a default one. Identity is asserted on attributes that exist: the
        orchestrator stores the service, and the LLM service it built holds the
        same instance (the factory is a local, never retained).
        """
        monkeypatch.delenv("SCRAPPY_MOCK_LLM", raising=False)
        double = MockApiKeyConfigService()

        with patch(
            "scrappy.orchestrator.factory.create_litellm_router",
            return_value=MagicMock(),
        ):
            orchestrator = AgentOrchestrator(
                project_path=".",
                enable_semantic_search=False,
                path_provider=TempPathProvider(tmp_path),
                api_key_service=double,
            )

        assert orchestrator._api_key_service is double
        assert orchestrator.llm_service._api_key_service is double
        assert not orchestrator.model_selector.is_configured(GROQ_CHAT_MODEL)

        # The key exists ONLY in the injected double.
        double.keys["GROQ_API_KEY"] = "gsk-injected"

        orchestrator.refresh_provider_configuration()
        assert orchestrator.model_selector.is_configured(GROQ_CHAT_MODEL)

        status = orchestrator.status()
        assert GROQ_CHAT_MODEL in {m["model_id"] for m in status["configured_models"]}
        assert "chat" in status["model_groups"]
