"""
Tests for AgentOrchestrator dependency injection.

Verifies that all major dependencies can be injected for testability.

After LiteLLM integration (Phase 3):
- Factory now creates LiteLLMService which requires API keys
- Tests must inject delegation_manager or mock API keys
- Tests use mock delegation_manager to avoid API key requirements

Every construction here is PARTIAL injection, so each one enters the factory
branch of AgentOrchestrator.__init__. Outside mock mode that branch builds the
persisted model-cooldown tracker, whose store is read and can be rewritten on
construction alone, so every construction injects a TempPathProvider(tmp_path):
the tracker, the user-directory creation and the cache all resolve under the
test's own root instead of the developer's profile (scrappy-i2jo).
"""

import json

import pytest
from unittest.mock import Mock

from scrappy.infrastructure import paths as paths_module
from scrappy.infrastructure.paths import TempPathProvider
from scrappy.orchestrator.core import AgentOrchestrator, create_orchestrator
from scrappy.orchestrator.cache import ResponseCache
from scrappy.orchestrator.rate_limiting import RateLimitTracker
from scrappy.orchestrator.memory import WorkingMemory
from scrappy.orchestrator.session import SessionManager
from scrappy.cli.protocols import BaseOutputProtocol
from scrappy.orchestrator.output import NullOutput


class MockDelegationManager:
    """Mock delegation manager for tests that don't need API keys."""

    async def delegate_async(self, provider, prompt, **kwargs):
        from scrappy.orchestrator.provider_types import LLMResponse
        response = LLMResponse(
            content="mock response",
            model="mock-model",
            provider="mock",
            tokens_used=10
        )
        return response, {"provider": "mock", "model": "mock-model"}

    def delegate(self, provider, prompt, **kwargs):
        import asyncio
        return asyncio.run(self.delegate_async(provider, prompt, **kwargs))


@pytest.fixture
def mock_api_key_service():
    """Fixture that mocks API key service to return fake keys."""
    mock_service = Mock()
    mock_service.get_key = Mock(side_effect=lambda k: f"fake-{k}")
    mock_service.has_any_key = Mock(return_value=True)
    return mock_service


class TestDependencyInjection:
    """Tests for dependency injection in AgentOrchestrator."""

    def test_uses_injected_cache(self, tmp_path):
        """Injected cache should be used instead of creating default."""
        mock_cache = Mock(spec=ResponseCache)
        mock_delegation = MockDelegationManager()

        orch = AgentOrchestrator(
            project_path=str(tmp_path),
            path_provider=TempPathProvider(tmp_path),
            cache=mock_cache,
            delegation_manager=mock_delegation,
            output=NullOutput()
        )

        assert orch.cache is mock_cache

    def test_uses_injected_rate_tracker(self, tmp_path):
        """Injected rate tracker should be used instead of creating default."""
        mock_tracker = Mock(spec=RateLimitTracker)
        mock_delegation = MockDelegationManager()

        orch = AgentOrchestrator(
            project_path=str(tmp_path),
            path_provider=TempPathProvider(tmp_path),
            rate_tracker=mock_tracker,
            delegation_manager=mock_delegation,
            output=NullOutput()
        )

        assert orch.rate_tracker is mock_tracker

    def test_uses_injected_working_memory(self, tmp_path):
        """Injected working memory should be used instead of creating default."""
        mock_memory = Mock(spec=WorkingMemory)
        mock_delegation = MockDelegationManager()

        orch = AgentOrchestrator(
            project_path=str(tmp_path),
            path_provider=TempPathProvider(tmp_path),
            working_memory=mock_memory,
            delegation_manager=mock_delegation,
            output=NullOutput()
        )

        assert orch.working_memory is mock_memory

    def test_uses_injected_session_manager(self, tmp_path):
        """Injected session manager should be used instead of creating default."""
        mock_session = Mock(spec=SessionManager)
        mock_delegation = MockDelegationManager()

        orch = AgentOrchestrator(
            project_path=str(tmp_path),
            path_provider=TempPathProvider(tmp_path),
            session_manager=mock_session,
            delegation_manager=mock_delegation,
            output=NullOutput()
        )

        assert orch.session_manager is mock_session

    def test_uses_injected_background_manager(self, tmp_path):
        """Injected background manager should be used instead of creating default."""
        from scrappy.orchestrator.manager_protocols import BackgroundTaskManagerProtocol

        mock_manager = Mock(spec=BackgroundTaskManagerProtocol)
        mock_delegation = MockDelegationManager()

        orch = AgentOrchestrator(
            project_path=str(tmp_path),
            path_provider=TempPathProvider(tmp_path),
            background_manager=mock_manager,
            delegation_manager=mock_delegation,
            output=NullOutput()
        )

        assert orch.background_manager is mock_manager

    def test_injection_enables_mock_testing(self, tmp_path):
        """Demonstrates using injection for unit testing with mocks."""
        # Set up mocks
        mock_cache = Mock(spec=ResponseCache)
        mock_cache.get.return_value = None
        mock_cache.get_stats.return_value = {'hits': 0, 'misses': 0}

        mock_tracker = Mock(spec=RateLimitTracker)
        mock_tracker.get_remaining_quota.return_value = {
            'requests_remaining_today': 100,
            'requests_remaining_month': 1000
        }

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""
        mock_memory.get_summary.return_value = {'files_cached': 0}

        mock_session = Mock(spec=SessionManager)

        mock_delegation = MockDelegationManager()

        # Create orchestrator with all mocks
        orch = AgentOrchestrator(
            project_path=str(tmp_path),
            path_provider=TempPathProvider(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            session_manager=mock_session,
            delegation_manager=mock_delegation,
            output=NullOutput()
        )

        # Verify all mocks were used
        assert orch.cache is mock_cache
        assert orch.rate_tracker is mock_tracker
        assert orch.working_memory is mock_memory
        assert orch.session_manager is mock_session

        # Can now test orchestrator methods in isolation
        # by configuring mock return values

    def test_cache_stats_uses_injected_cache(self, tmp_path):
        """get_cache_stats should use injected cache."""
        from scrappy.orchestrator.usage_reporter import UsageReporter

        mock_cache = Mock(spec=ResponseCache)
        expected_stats = {'exact_hits': 10, 'intent_hits': 5}
        mock_cache.get_stats.return_value = expected_stats

        # Create usage_reporter with the mock cache
        usage_reporter = UsageReporter(
            cache=mock_cache,
            created_at=None
        )

        mock_delegation = MockDelegationManager()

        orch = AgentOrchestrator(
            project_path=str(tmp_path),
            path_provider=TempPathProvider(tmp_path),
            cache=mock_cache,
            usage_reporter=usage_reporter,
            delegation_manager=mock_delegation,
            output=NullOutput()
        )

        stats = orch.get_cache_stats()

        assert stats == expected_stats
        mock_cache.get_stats.assert_called_once()

    def test_working_memory_methods_use_injected_memory(self, tmp_path):
        """Working memory delegation should use injected instance."""
        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_summary.return_value = {'files_cached': 5}

        mock_delegation = MockDelegationManager()

        orch = AgentOrchestrator(
            project_path=str(tmp_path),
            path_provider=TempPathProvider(tmp_path),
            working_memory=mock_memory,
            delegation_manager=mock_delegation,
            output=NullOutput()
        )

        # Access working memory directly
        summary = orch.working_memory.get_summary()

        assert summary == {'files_cached': 5}
        mock_memory.get_summary.assert_called_once()

    def test_session_methods_use_injected_session_manager(self, tmp_path):
        """Session operations should use injected session manager."""
        mock_session = Mock(spec=SessionManager)
        mock_session.load_session.return_value = {
            'status': 'loaded',
            'working_memory': WorkingMemory(),
            'task_history': [],
            'saved_at': '2024-01-01',
            'files_restored': 0,
            'searches_restored': 0,
            'git_ops_restored': 0,
            'discoveries_restored': 0,
            'tasks_restored': 0,
            'conversation_history': []
        }

        mock_delegation = MockDelegationManager()

        orch = AgentOrchestrator(
            project_path=str(tmp_path),
            path_provider=TempPathProvider(tmp_path),
            session_manager=mock_session,
            delegation_manager=mock_delegation,
            output=NullOutput()
        )

        result = orch.load_session()

        assert result['status'] == 'loaded'
        mock_session.load_session.assert_called_once()


@pytest.fixture
def mock_mode(monkeypatch):
    """Deterministic, latency-free mock mode so the helper needs no API keys."""
    monkeypatch.setenv("SCRAPPY_MOCK_LLM", "1")
    monkeypatch.setenv("SCRAPPY_MOCK_LATENCY_MS", "0")
    monkeypatch.setenv("SCRAPPY_MOCK_RESPONSE", "Mock response")


class TestCreateOrchestratorPathProvider:
    """create_orchestrator() forwards a provider, and still works without one.

    Both tests drive the REAL rate tracker the factory builds and then read the
    file it wrote. Persistence at a provider-derived path is the evidence; the
    call graph is not asserted, because an inlined equivalent would be
    observationally identical in production and a test that could tell them
    apart would be asserting composition rather than behaviour.
    """

    def test_injected_provider_receives_the_real_trackers_writes(self, mock_mode, tmp_path):
        """T11: the provider passed in is the one the consumers persist through."""
        provider = TempPathProvider(tmp_path)

        orch = create_orchestrator(path_provider=provider)
        orch.rate_tracker.record_request("groq", "llama-3.3-70b-versatile", input_tokens=7)

        recorded = json.loads(provider.rate_limits_file().read_text())
        assert recorded["providers"]["groq"]["llama-3.3-70b-versatile"]["requests_today"] == 1
        assert provider.rate_limits_file().is_relative_to(tmp_path)

    def test_no_argument_call_resolves_through_discovery(self, mock_mode, tmp_path, monkeypatch):
        """T12: the no-argument path still works, against controlled discovery.

        The discovery inputs are patched on the paths module, not on Path.home():
        create_default_path_provider reads the three platformdirs lookups when it
        builds the provider and CAPTURES the import-bound LEGACY_USER_DIR, so a
        home() change would not reach the legacy source (D5).
        """
        discovered = tmp_path / "discovered"
        legacy = tmp_path / "legacy" / ".scrappy"
        legacy.mkdir(parents=True)
        (legacy / "command_history").write_text("legacy history\n")

        monkeypatch.setattr(paths_module, "user_data_dir", lambda app: str(discovered / app / "data"))
        monkeypatch.setattr(paths_module, "user_config_dir", lambda app: str(discovered / app / "config"))
        monkeypatch.setattr(paths_module, "user_cache_dir", lambda app: str(discovered / app / "cache"))
        monkeypatch.setattr(paths_module, "LEGACY_USER_DIR", legacy)
        monkeypatch.chdir(tmp_path)

        orch = create_orchestrator()
        orch.rate_tracker.record_request("groq", "llama-3.3-70b-versatile", input_tokens=7)

        data_dir = discovered / paths_module.APP_NAME / "data"
        persisted = json.loads((data_dir / "rate_limits.json").read_text())
        assert persisted["providers"]["groq"]["llama-3.3-70b-versatile"]["requests_today"] == 1
        # The real ensure_user_dir ran, including the legacy migration, and read
        # the captured module constant rather than a home()-derived path.
        assert (data_dir / "command_history").read_text() == "legacy history\n"


class TestDependencyInjectionEdgeCases:
    """Edge case tests for dependency injection."""

    def test_output_already_injectable(self, tmp_path):
        """Output interface was already injectable - verify still works."""
        mock_output = Mock(spec=BaseOutputProtocol)
        mock_delegation = MockDelegationManager()

        orch = AgentOrchestrator(
            project_path=str(tmp_path),
            path_provider=TempPathProvider(tmp_path),
            delegation_manager=mock_delegation,
            output=mock_output
        )

        assert orch.output is mock_output
