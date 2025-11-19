"""
Tests for AgentOrchestrator dependency injection.

Verifies that all major dependencies can be injected for testability.
"""

import pytest
from unittest.mock import Mock, MagicMock
from pathlib import Path

from src.orchestrator.core import AgentOrchestrator
from src.orchestrator.cache import ResponseCache
from src.orchestrator.rate_limiter import RateLimitTracker
from src.orchestrator.memory import WorkingMemory
from src.orchestrator.session import SessionManager
from src.orchestrator.provider_selector import ProviderSelector
from src.orchestrator.output import OutputInterface, NullOutput


class TestDependencyInjection:
    """Tests for dependency injection in AgentOrchestrator."""

    def test_uses_injected_cache(self, tmp_path):
        """Injected cache should be used instead of creating default."""
        mock_cache = Mock(spec=ResponseCache)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            output=NullOutput()
        )

        assert orch.cache is mock_cache

    def test_uses_injected_rate_tracker(self, tmp_path):
        """Injected rate tracker should be used instead of creating default."""
        mock_tracker = Mock(spec=RateLimitTracker)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            rate_tracker=mock_tracker,
            output=NullOutput()
        )

        assert orch.rate_tracker is mock_tracker

    def test_uses_injected_working_memory(self, tmp_path):
        """Injected working memory should be used instead of creating default."""
        mock_memory = Mock(spec=WorkingMemory)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            working_memory=mock_memory,
            output=NullOutput()
        )

        assert orch.working_memory is mock_memory

    def test_uses_injected_session_manager(self, tmp_path):
        """Injected session manager should be used instead of creating default."""
        mock_session = Mock(spec=SessionManager)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            session_manager=mock_session,
            output=NullOutput()
        )

        assert orch.session_manager is mock_session

    def test_uses_injected_provider_selector(self, tmp_path):
        """Injected provider selector should be used instead of creating default."""
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            provider_selector=mock_selector,
            output=NullOutput()
        )

        assert orch.provider_selector is mock_selector

    def test_creates_defaults_when_not_injected(self, tmp_path):
        """Should create default instances when dependencies not injected."""
        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            output=NullOutput()
        )

        assert isinstance(orch.cache, ResponseCache)
        assert isinstance(orch.rate_tracker, RateLimitTracker)
        assert isinstance(orch.working_memory, WorkingMemory)
        assert isinstance(orch.session_manager, SessionManager)
        assert isinstance(orch.provider_selector, ProviderSelector)

    def test_partial_injection(self, tmp_path):
        """Can inject some dependencies while using defaults for others."""
        mock_cache = Mock(spec=ResponseCache)
        mock_memory = Mock(spec=WorkingMemory)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            working_memory=mock_memory,
            output=NullOutput()
        )

        # Injected
        assert orch.cache is mock_cache
        assert orch.working_memory is mock_memory

        # Defaults
        assert isinstance(orch.rate_tracker, RateLimitTracker)
        assert isinstance(orch.session_manager, SessionManager)
        assert isinstance(orch.provider_selector, ProviderSelector)

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

        mock_selector = Mock(spec=ProviderSelector)

        # Create orchestrator with all mocks
        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            session_manager=mock_session,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        # Verify all mocks were used
        assert orch.cache is mock_cache
        assert orch.rate_tracker is mock_tracker
        assert orch.working_memory is mock_memory
        assert orch.session_manager is mock_session
        assert orch.provider_selector is mock_selector

        # Can now test orchestrator methods in isolation
        # by configuring mock return values

    def test_cache_stats_uses_injected_cache(self, tmp_path):
        """get_cache_stats should use injected cache."""
        mock_cache = Mock(spec=ResponseCache)
        expected_stats = {'exact_hits': 10, 'intent_hits': 5}
        mock_cache.get_stats.return_value = expected_stats

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            output=NullOutput()
        )

        stats = orch.get_cache_stats()

        assert stats == expected_stats
        mock_cache.get_stats.assert_called_once()

    def test_working_memory_methods_use_injected_memory(self, tmp_path):
        """Working memory delegation should use injected instance."""
        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_summary.return_value = {'files_cached': 5}

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            working_memory=mock_memory,
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

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            session_manager=mock_session,
            output=NullOutput()
        )

        result = orch.load_session()

        assert result['status'] == 'loaded'
        mock_session.load_session.assert_called_once()


class TestDependencyInjectionEdgeCases:
    """Edge case tests for dependency injection."""

    def test_none_values_create_defaults(self, tmp_path):
        """Explicitly passing None should create defaults."""
        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=None,
            rate_tracker=None,
            working_memory=None,
            session_manager=None,
            provider_selector=None,
            output=NullOutput()
        )

        assert isinstance(orch.cache, ResponseCache)
        assert isinstance(orch.rate_tracker, RateLimitTracker)
        assert isinstance(orch.working_memory, WorkingMemory)
        assert isinstance(orch.session_manager, SessionManager)
        assert isinstance(orch.provider_selector, ProviderSelector)

    def test_output_already_injectable(self, tmp_path):
        """Output interface was already injectable - verify still works."""
        mock_output = Mock(spec=OutputInterface)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            output=mock_output
        )

        assert orch.output is mock_output
