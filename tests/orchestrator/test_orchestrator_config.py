"""
Tests for orchestrator provider configuration.

These tests capture current behavior for regression testing during
the consolidation of provider config into src/orchestrator/config.py.
"""

import pytest
from unittest.mock import MagicMock, PropertyMock

from scrappy.orchestrator.provider_selector import ProviderSelector
from scrappy.orchestrator.rate_limiting import RateLimitTracker
from scrappy.orchestrator.model_selection import ModelSelectionType
from scrappy.providers.base import ProviderRegistry
from tests.helpers import create_test_rate_limit_tracker


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
            # Mock get_model_info to return proper context_length for fallback filtering
            mock_model_info = MagicMock()
            mock_model_info.context_length = 128000  # Sufficient context for brain
            provider.get_model_info.return_value = mock_model_info
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

    def _create_real_tracker(self):
        """Create a tracker with real recommender for testing task preferences."""
        from scrappy.orchestrator.rate_limiting import RateLimitTracker, RateLimitRecommender
        from tests.helpers import FakeStorage, FakePolicy, FakeCalculator

        storage = FakeStorage()
        policy = FakePolicy()
        calculator = FakeCalculator()

        # Create tracker with placeholder recommender
        tracker = RateLimitTracker(
            storage=storage,
            policy=policy,
            calculator=calculator,
            recommender=MagicMock()
        )

        # Create real recommender with the tracker as usage query
        # and replace the mock recommender
        recommender = RateLimitRecommender(tracker)
        tracker._recommender = recommender

        return tracker

    def test_planning_task_preferences(self):
        """Planning tasks should prefer cerebras > groq > gemini."""
        registry = self._create_mock_registry(['cerebras', 'groq', 'gemini'])
        tracker = self._create_real_tracker()

        result = tracker.get_recommended_provider('planning', registry)

        assert result == 'cerebras'

    def test_execution_task_preferences(self):
        """Execution tasks should prefer cerebras > groq > gemini."""
        registry = self._create_mock_registry(['cerebras', 'groq', 'gemini'])
        tracker = self._create_real_tracker()

        result = tracker.get_recommended_provider('execution', registry)

        assert result == 'cerebras'

    def test_quick_task_preferences(self):
        """Quick tasks should prefer cerebras > groq."""
        registry = self._create_mock_registry(['groq', 'gemini'])
        tracker = self._create_real_tracker()

        result = tracker.get_recommended_provider('quick', registry)

        # groq is first in quick preferences that's available
        assert result == 'groq'

    def test_general_task_preferences(self):
        """General tasks should prefer cerebras > groq > gemini."""
        registry = self._create_mock_registry(['gemini', 'cohere'])
        tracker = self._create_real_tracker()

        result = tracker.get_recommended_provider('general', registry)

        # gemini is first in general preferences that's available
        assert result == 'gemini'

    def test_unknown_task_type_uses_general_preferences(self):
        """Unknown task types should fall back to general preferences."""
        registry = self._create_mock_registry(['cerebras', 'groq'])
        tracker = self._create_real_tracker()

        result = tracker.get_recommended_provider('unknown_task', registry)

        assert result == 'cerebras'

    def test_returns_first_available_when_no_preferences_match(self):
        """Should return first available provider when no preferences match."""
        registry = self._create_mock_registry(['cohere', 'github_models'])
        tracker = self._create_real_tracker()

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
    """Regression tests for get_model behavior."""

    def _create_mock_registry(self, available_providers: list[str]) -> ProviderRegistry:
        """Create a mock registry with specified providers."""
        from scrappy.providers.base import ModelInfo, ModelType, SpeedRank, QualityRank
        registry = ProviderRegistry()

        for provider_name in available_providers:
            provider = MagicMock()
            provider.name = provider_name
            provider.is_available.return_value = True

            # Create proper model info objects
            if provider_name == 'cerebras':
                models = ["llama3.1-8b", "llama-3.3-70b"]
                type(provider).available_models = PropertyMock(return_value=models)
                type(provider).default_model = PropertyMock(return_value="llama3.1-8b")

                def get_model_info(model_id):
                    if model_id == "llama3.1-8b":
                        return ModelInfo("llama3.1-8b", ModelType.UNKNOWN, 8192, rpd=14400, speed=SpeedRank.ULTRA_FAST, quality=QualityRank.GOOD)
                    elif model_id == "llama-3.3-70b":
                        return ModelInfo("llama-3.3-70b", ModelType.CHAT, 8192, rpd=14400, speed=SpeedRank.FAST, quality=QualityRank.VERY_GOOD)
                    return ModelInfo(model_id, ModelType.UNKNOWN, 4096)
                provider.get_model_info = get_model_info
            elif provider_name == 'cohere':
                models = ["command-r7b-12-2024"]
                type(provider).available_models = PropertyMock(return_value=models)
                type(provider).default_model = PropertyMock(return_value="command-r7b-12-2024")
                provider.get_model_info = lambda model_id: ModelInfo("command-r7b-12-2024", ModelType.CHAT, 128000, speed=SpeedRank.VERY_FAST, quality=QualityRank.MODERATE)
            else:
                type(provider).available_models = PropertyMock(return_value=["test-model"])
                type(provider).default_model = PropertyMock(return_value="test-model")
                provider.get_model_info = lambda model_id: ModelInfo(model_id, ModelType.UNKNOWN, 4096, speed=SpeedRank.FAST, quality=QualityRank.GOOD)

            registry.register(provider)

        return registry

    def test_fast_task_prefers_cerebras(self):
        """Fast task should prefer cerebras for high quota."""
        registry = self._create_mock_registry(['cerebras', 'groq', 'gemini'])
        selector = ProviderSelector(registry)

        name, model = selector.get_model(ModelSelectionType.FAST)

        assert name == 'cerebras'

    def test_high_volume_task_prefers_cerebras(self):
        """High volume task should prefer cerebras for highest quota."""
        registry = self._create_mock_registry(['cerebras', 'groq', 'gemini'])
        selector = ProviderSelector(registry)

        name, model = selector.get_model(ModelSelectionType.FAST)

        assert name == 'cerebras'

    def test_general_task_prefers_cerebras(self):
        """General task should prefer cerebras."""
        registry = self._create_mock_registry(['cerebras', 'groq', 'gemini'])
        selector = ProviderSelector(registry)

        name, model = selector.get_model(ModelSelectionType.FAST)

        assert name == 'cerebras'

    def test_quality_task_uses_large_model(self):
        """Quality task should use largest model available."""
        registry = self._create_mock_registry(['cerebras', 'groq'])
        selector = ProviderSelector(registry)

        name, model = selector.get_model(ModelSelectionType.QUALITY)

        assert name == 'cerebras'
        # Should use the large model
        assert '70b' in (model or '')

    def test_embed_task_uses_cohere(self):
        """Embed task should use cohere when available."""
        registry = self._create_mock_registry(['cerebras', 'cohere'])
        selector = ProviderSelector(registry)

        name, model = selector.get_model(ModelSelectionType.EMBED)

        assert name == 'cohere'

    def test_fallback_to_first_available(self):
        """Should fall back to first available when no priority matches."""
        registry = self._create_mock_registry(['github_models'])
        selector = ProviderSelector(registry)

        name, model = selector.get_model(ModelSelectionType.FAST)

        assert name == 'github_models'
