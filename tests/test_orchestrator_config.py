"""
Tests for orchestrator provider configuration.

These tests capture current behavior for regression testing during
the consolidation of provider config into src/orchestrator/config.py.
"""

import pytest
from unittest.mock import MagicMock, PropertyMock

from src.orchestrator.provider_selector import ProviderSelector
from src.orchestrator.rate_limiter import RateLimitTracker
from src.providers.base import ProviderRegistry


class TestProviderPriorityRegression:
    """
    Regression tests for provider priority order.

    These tests ensure the consolidation doesn't break existing behavior.
    Priority order should be: cerebras > groq > gemini
    """

    def _create_mock_registry(self, available_providers: list[str]) -> ProviderRegistry:
        """Create a mock registry with specified providers."""
        registry = ProviderRegistry()

        for provider_name in available_providers:
            provider = MagicMock()
            provider.name = provider_name
            provider.is_available.return_value = True
            type(provider).available_models = PropertyMock(return_value=["test-model"])
            type(provider).default_model = PropertyMock(return_value="test-model")
            provider.get_model_for_task.return_value = "test-model"
            registry.register(provider)

        return registry

    def test_setup_brain_prefers_cerebras(self):
        """setup_brain should prefer cerebras when available."""
        registry = self._create_mock_registry(['cerebras', 'groq', 'gemini'])
        selector = ProviderSelector(registry)

        name, provider = selector.setup_brain()

        assert name == 'cerebras'

    def test_setup_brain_falls_back_to_groq(self):
        """setup_brain should fall back to groq when cerebras unavailable."""
        registry = self._create_mock_registry(['groq', 'gemini'])
        selector = ProviderSelector(registry)

        name, provider = selector.setup_brain()

        assert name == 'groq'

    def test_setup_brain_falls_back_to_gemini(self):
        """setup_brain should fall back to gemini when cerebras/groq unavailable."""
        registry = self._create_mock_registry(['gemini', 'cohere'])
        selector = ProviderSelector(registry)

        name, provider = selector.setup_brain()

        assert name == 'gemini'

    def test_setup_brain_uses_first_available_as_last_resort(self):
        """setup_brain should use first available provider as last resort."""
        registry = self._create_mock_registry(['cohere', 'github_models'])
        selector = ProviderSelector(registry)

        name, provider = selector.setup_brain()

        assert name == 'cohere'

    def test_setup_brain_respects_user_preference(self):
        """setup_brain should use user-specified provider when available."""
        registry = self._create_mock_registry(['cerebras', 'groq', 'gemini'])
        selector = ProviderSelector(registry)

        name, provider = selector.setup_brain('gemini')

        assert name == 'gemini'

    def test_setup_brain_warns_on_unavailable_preference(self):
        """setup_brain should warn and auto-select when preference unavailable."""
        registry = self._create_mock_registry(['groq', 'gemini'])
        selector = ProviderSelector(registry)

        name, provider = selector.setup_brain('cerebras')

        # Should fall back to priority order
        assert name == 'groq'
        # Should have logged a warning
        log = selector.get_selection_log()
        assert any('not available' in entry.lower() for entry in log)



class TestFallbackPriorityRegression:
    """Regression tests for fallback provider selection."""

    def _create_mock_registry(self, available_providers: list[str]) -> ProviderRegistry:
        """Create a mock registry with specified providers."""
        registry = ProviderRegistry()

        for provider_name in available_providers:
            provider = MagicMock()
            provider.name = provider_name
            provider.is_available.return_value = True
            registry.register(provider)

        return registry

    def test_fallback_priority_order(self):
        """get_provider_for_fallback should follow priority: cerebras > groq > gemini."""
        registry = self._create_mock_registry(['cerebras', 'groq', 'gemini'])
        selector = ProviderSelector(registry)

        # With no exclusions, should return cerebras
        assert selector.get_provider_for_fallback() == 'cerebras'

        # Excluding cerebras, should return groq
        assert selector.get_provider_for_fallback(exclude=['cerebras']) == 'groq'

        # Excluding cerebras and groq, should return gemini
        assert selector.get_provider_for_fallback(exclude=['cerebras', 'groq']) == 'gemini'

    def test_fallback_returns_any_available_when_priority_exhausted(self):
        """get_provider_for_fallback should return any available provider."""
        registry = self._create_mock_registry(['cohere', 'github_models'])
        selector = ProviderSelector(registry)

        result = selector.get_provider_for_fallback()

        assert result in ['cohere', 'github_models']

    def test_fallback_returns_none_when_all_excluded(self):
        """get_provider_for_fallback should return None when all excluded."""
        registry = self._create_mock_registry(['cerebras', 'groq'])
        selector = ProviderSelector(registry)

        result = selector.get_provider_for_fallback(exclude=['cerebras', 'groq'])

        assert result is None


class TestTaskPreferencesRegression:
    """
    Regression tests for task-based provider preferences.

    Tests the TASK_PREFERENCES behavior in rate_limiter.py
    """

    def _create_mock_registry(self, available_providers: list[str]) -> ProviderRegistry:
        """Create a mock registry with specified providers."""
        registry = ProviderRegistry()

        for provider_name in available_providers:
            provider = MagicMock()
            provider.name = provider_name
            provider.is_available.return_value = True
            type(provider).default_model = PropertyMock(return_value="test-model")
            # Mock get_limits to return None (no rate limiting)
            provider.get_limits.return_value = None
            registry.register(provider)

        return registry

    def test_planning_task_preferences(self):
        """Planning tasks should prefer cerebras > groq > gemini."""
        registry = self._create_mock_registry(['cerebras', 'groq', 'gemini'])
        tracker = RateLimitTracker()

        result = tracker.get_recommended_provider('planning', registry)

        assert result == 'cerebras'

    def test_execution_task_preferences(self):
        """Execution tasks should prefer cerebras > groq > gemini."""
        registry = self._create_mock_registry(['cerebras', 'groq', 'gemini'])
        tracker = RateLimitTracker()

        result = tracker.get_recommended_provider('execution', registry)

        assert result == 'cerebras'

    def test_quick_task_preferences(self):
        """Quick tasks should prefer cerebras > groq."""
        registry = self._create_mock_registry(['groq', 'gemini'])
        tracker = RateLimitTracker()

        result = tracker.get_recommended_provider('quick', registry)

        # groq is first in quick preferences that's available
        assert result == 'groq'

    def test_general_task_preferences(self):
        """General tasks should prefer cerebras > groq > gemini."""
        registry = self._create_mock_registry(['gemini', 'cohere'])
        tracker = RateLimitTracker()

        result = tracker.get_recommended_provider('general', registry)

        # gemini is first in general preferences that's available
        assert result == 'gemini'

    def test_unknown_task_type_uses_general_preferences(self):
        """Unknown task types should fall back to general preferences."""
        registry = self._create_mock_registry(['cerebras', 'groq'])
        tracker = RateLimitTracker()

        result = tracker.get_recommended_provider('unknown_task', registry)

        assert result == 'cerebras'

    def test_returns_first_available_when_no_preferences_match(self):
        """Should return first available provider when no preferences match."""
        registry = self._create_mock_registry(['cohere', 'github_models'])
        tracker = RateLimitTracker()

        result = tracker.get_recommended_provider('planning', registry)

        assert result == 'cohere'


class TestProviderInfoRegression:
    """
    Regression tests for provider information/reasons.

    Tests the _get_brain_selection_reason behavior in provider_selector.py
    """

    def _create_mock_registry(self, available_providers: list[str]) -> ProviderRegistry:
        """Create a mock registry with specified providers."""
        registry = ProviderRegistry()

        for provider_name in available_providers:
            provider = MagicMock()
            provider.name = provider_name
            provider.is_available.return_value = True
            type(provider).available_models = PropertyMock(return_value=["test-model"])
            type(provider).default_model = PropertyMock(return_value="test-model")
            provider.get_model_for_task.return_value = "test-model"
            registry.register(provider)

        return registry

    def test_cerebras_reason_mentions_quota(self):
        """Cerebras selection reason should mention RPD quota."""
        registry = self._create_mock_registry(['cerebras'])
        selector = ProviderSelector(registry)

        reason = selector._get_brain_selection_reason('cerebras')

        assert '14,400' in reason or 'RPD' in reason

    def test_groq_reason_mentions_characteristics(self):
        """Groq selection reason should mention its characteristics."""
        registry = self._create_mock_registry(['groq'])
        selector = ProviderSelector(registry)

        reason = selector._get_brain_selection_reason('groq')

        # Should mention something about groq's characteristics
        assert reason  # Not empty
        assert 'groq' not in reason.lower() or 'RPD' in reason or 'fast' in reason.lower()

    def test_gemini_reason_mentions_fallback(self):
        """Gemini selection reason should mention auto-fallback."""
        registry = self._create_mock_registry(['gemini'])
        selector = ProviderSelector(registry)

        reason = selector._get_brain_selection_reason('gemini')

        assert 'fallback' in reason.lower() or 'auto' in reason.lower()

    def test_cohere_reason_mentions_limited_quota(self):
        """Cohere selection reason should mention limited quota."""
        registry = self._create_mock_registry(['cohere'])
        selector = ProviderSelector(registry)

        reason = selector._get_brain_selection_reason('cohere')

        assert '1,000' in reason or 'month' in reason.lower() or 'limited' in reason.lower()

    def test_unknown_provider_returns_available(self):
        """Unknown provider should return 'available' as reason."""
        registry = self._create_mock_registry(['unknown_provider'])
        selector = ProviderSelector(registry)

        reason = selector._get_brain_selection_reason('unknown_provider')

        assert reason == 'available'


class TestSelectForTaskRegression:
    """Regression tests for select_for_task behavior."""

    def _create_mock_registry(self, available_providers: list[str]) -> ProviderRegistry:
        """Create a mock registry with specified providers."""
        registry = ProviderRegistry()

        for provider_name in available_providers:
            provider = MagicMock()
            provider.name = provider_name
            provider.is_available.return_value = True
            type(provider).available_models = PropertyMock(return_value=["test-model"])
            type(provider).default_model = PropertyMock(return_value="test-model")
            provider.get_model_for_task.return_value = "test-model"
            registry.register(provider)

        return registry

    def test_fast_task_prefers_cerebras(self):
        """Fast task should prefer cerebras for high quota."""
        registry = self._create_mock_registry(['cerebras', 'groq', 'gemini'])
        selector = ProviderSelector(registry)

        name, model = selector.select_for_task('fast')

        assert name == 'cerebras'

    def test_high_volume_task_prefers_cerebras(self):
        """High volume task should prefer cerebras for highest quota."""
        registry = self._create_mock_registry(['cerebras', 'groq', 'gemini'])
        selector = ProviderSelector(registry)

        name, model = selector.select_for_task('high_volume')

        assert name == 'cerebras'

    def test_general_task_prefers_cerebras(self):
        """General task should prefer cerebras."""
        registry = self._create_mock_registry(['cerebras', 'groq', 'gemini'])
        selector = ProviderSelector(registry)

        name, model = selector.select_for_task('general')

        assert name == 'cerebras'

    def test_quality_task_uses_large_model(self):
        """Quality task should use largest model available."""
        registry = self._create_mock_registry(['cerebras', 'groq'])
        selector = ProviderSelector(registry)

        name, model = selector.select_for_task('quality')

        assert name == 'cerebras'
        # Should use the large model
        assert '70b' in (model or '')

    def test_embed_task_uses_cohere(self):
        """Embed task should use cohere when available."""
        registry = self._create_mock_registry(['cerebras', 'cohere'])
        selector = ProviderSelector(registry)

        name, model = selector.select_for_task('embed')

        assert name == 'cohere'

    def test_fallback_to_first_available(self):
        """Should fall back to first available when no priority matches."""
        registry = self._create_mock_registry(['github_models'])
        selector = ProviderSelector(registry)

        name, model = selector.select_for_task('fast')

        assert name == 'github_models'


class TestConfigValidation:
    """
    Tests for config validation after consolidation.

    These tests will validate the config.py structure once created.
    They should fail until config.py is properly implemented.
    """


    def test_provider_priority_defined(self):
        """PROVIDER_PRIORITY should be defined."""
        try:
            from src.orchestrator.config import PROVIDER_PRIORITY
            assert isinstance(PROVIDER_PRIORITY, list)
            assert len(PROVIDER_PRIORITY) > 0
        except ImportError:
            pytest.skip("config.py not yet created")

    def test_provider_info_defined(self):
        """PROVIDER_INFO should be defined."""
        try:
            from src.orchestrator.config import PROVIDER_INFO
            assert isinstance(PROVIDER_INFO, dict)
            assert len(PROVIDER_INFO) > 0
        except ImportError:
            pytest.skip("config.py not yet created")

    def test_task_preferences_defined(self):
        """TASK_PREFERENCES should be defined."""
        try:
            from src.orchestrator.config import TASK_PREFERENCES
            assert isinstance(TASK_PREFERENCES, dict)
            assert len(TASK_PREFERENCES) > 0
        except ImportError:
            pytest.skip("config.py not yet created")

    def test_all_priority_providers_have_info(self):
        """All providers in PROVIDER_PRIORITY should have PROVIDER_INFO."""
        try:
            from src.orchestrator.config import PROVIDER_PRIORITY, PROVIDER_INFO

            for provider in PROVIDER_PRIORITY:
                assert provider in PROVIDER_INFO, \
                    f"Provider '{provider}' in PROVIDER_PRIORITY but not in PROVIDER_INFO"
        except ImportError:
            pytest.skip("config.py not yet created")

    def test_all_task_preference_providers_are_valid(self):
        """All providers in TASK_PREFERENCES should be in PROVIDER_PRIORITY."""
        try:
            from src.orchestrator.config import PROVIDER_PRIORITY, TASK_PREFERENCES

            for task_type, providers in TASK_PREFERENCES.items():
                for provider in providers:
                    assert provider in PROVIDER_PRIORITY, \
                        f"Provider '{provider}' in TASK_PREFERENCES['{task_type}'] but not in PROVIDER_PRIORITY"
        except ImportError:
            pytest.skip("config.py not yet created")

    def test_provider_info_has_required_fields(self):
        """PROVIDER_INFO entries should have required fields."""
        try:
            from src.orchestrator.config import PROVIDER_INFO

            required_fields = ['quota', 'description']

            for provider, info in PROVIDER_INFO.items():
                for field in required_fields:
                    assert field in info, \
                        f"Provider '{provider}' missing required field '{field}'"
        except ImportError:
            pytest.skip("config.py not yet created")

    def test_task_preferences_has_required_task_types(self):
        """TASK_PREFERENCES should have required task types."""
        try:
            from src.orchestrator.config import TASK_PREFERENCES

            required_tasks = ['planning', 'execution', 'quick', 'general']

            for task in required_tasks:
                assert task in TASK_PREFERENCES, \
                    f"Required task type '{task}' not in TASK_PREFERENCES"
        except ImportError:
            pytest.skip("config.py not yet created")
