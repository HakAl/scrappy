"""
Tests for orchestrator provider configuration after LiteLLM integration.

Legacy provider priority tests are REMOVED - LiteLLM Router handles priority
based on the order of models in litellm_config.py.
"""

from unittest.mock import MagicMock, PropertyMock


class TestTaskPreferencesRegression:
    """
    Regression tests for task-based provider preferences.

    After LiteLLM integration, task preferences are handled differently:
    - RateLimitTracker.get_recommended_provider still works
    - But actual provider selection is done by LiteLLM Router
    """

    def _create_mock_registry(self, available_providers: list[str]):
        """Create a mock registry with specified providers."""
        from scrappy.orchestrator.provider_types import ProviderRegistry

        registry = ProviderRegistry()

        for provider_name in available_providers:
            provider = MagicMock()
            provider.name = provider_name
            provider.is_available.return_value = True
            type(provider).default_model = PropertyMock(return_value="test-model")
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

        tracker = RateLimitTracker(
            storage=storage,
            policy=policy,
            calculator=calculator,
            recommender=MagicMock()
        )

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
