"""
Tests for orchestrator provider configuration after LiteLLM integration.

After LiteLLM integration:
- ProviderSelector returns model groups ("fast", "chat", "instruct") not provider names
- setup_brain() returns "instruct" for brain/reasoning tasks
- get_model() maps ModelSelectionType to groups
- Fallback is handled by LiteLLM Router, not ProviderSelector

Legacy provider priority tests are REMOVED - LiteLLM Router handles priority
based on the order of models in litellm_config.py.
"""

import pytest
from unittest.mock import MagicMock, PropertyMock

from scrappy.orchestrator.provider_selector import ProviderSelector
from scrappy.orchestrator.model_selection import ModelSelectionType


class TestProviderSelectorModelGroups:
    """Tests for ProviderSelector returning model groups."""

    def test_setup_brain_returns_instruct_group(self):
        """setup_brain() returns 'instruct' model group."""
        selector = ProviderSelector()

        group, model = selector.setup_brain()

        assert group == "instruct"
        assert model is None

    def test_setup_brain_maps_legacy_provider_to_instruct(self):
        """setup_brain() maps legacy provider names to 'instruct' group."""
        selector = ProviderSelector()

        group, model = selector.setup_brain(preferred_provider="gemini")

        assert group == "instruct"
        assert model is None

    def test_setup_brain_accepts_fast_group(self):
        """setup_brain() accepts 'fast' as preferred group."""
        selector = ProviderSelector()

        group, model = selector.setup_brain(preferred_provider="fast")

        assert group == "fast"
        assert model is None

    def test_setup_brain_accepts_quality_maps_to_instruct(self):
        """setup_brain() maps legacy 'quality' to 'instruct' group."""
        selector = ProviderSelector()

        group, model = selector.setup_brain(preferred_provider="quality")

        assert group == "instruct"  # quality maps to instruct for brain
        assert model is None


class TestFallbackModelGroups:
    """Tests for fallback returning model groups."""

    def test_fallback_returns_fast_by_default(self):
        """get_provider_for_fallback() returns 'fast' by default."""
        selector = ProviderSelector()

        result = selector.get_provider_for_fallback()

        assert result == "fast"

    def test_fallback_with_chat_selection_type(self):
        """get_provider_for_fallback() returns 'chat' for chat selection."""
        selector = ProviderSelector()

        result = selector.get_provider_for_fallback(
            selection_type=ModelSelectionType.CHAT
        )

        assert result == "chat"

    def test_fallback_ignores_exclude_list(self):
        """get_provider_for_fallback() ignores exclude - LiteLLM handles fallback."""
        selector = ProviderSelector()

        # Exclude list is ignored - LiteLLM Router handles fallback internally
        result = selector.get_provider_for_fallback(
            exclude=["cerebras", "groq", "gemini"]
        )

        assert result in ("fast", "chat", "instruct")


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


class TestSelectForTaskModelGroups:
    """Tests for get_model() returning model groups."""

    def test_fast_task_returns_fast_group(self):
        """FAST selection returns 'fast' model group."""
        selector = ProviderSelector()

        group, model = selector.get_model(ModelSelectionType.FAST)

        assert group == "fast"
        assert model is None

    def test_chat_task_returns_chat_group(self):
        """CHAT selection returns 'chat' model group."""
        selector = ProviderSelector()

        group, model = selector.get_model(ModelSelectionType.CHAT)

        assert group == "chat"
        assert model is None

    def test_embed_task_returns_fast_group(self):
        """EMBED selection returns 'fast' model group."""
        selector = ProviderSelector()

        group, model = selector.get_model(ModelSelectionType.EMBED)

        assert group == "fast"
        assert model is None

    def test_instruct_task_returns_instruct_group(self):
        """INSTRUCT selection returns 'instruct' model group."""
        selector = ProviderSelector()

        group, model = selector.get_model(ModelSelectionType.INSTRUCT)

        assert group == "instruct"
        assert model is None
