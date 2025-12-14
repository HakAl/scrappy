"""
Tests for ProviderSelector after LiteLLM integration.

After LiteLLM integration, ProviderSelector returns model groups ("fast", "quality")
instead of provider names. Agent role filtering is now handled by the LiteLLM
Router configuration - providers without agent role support are simply not
included in the quality tier.

Tests:
- setup_brain() returns "quality" group by default
- setup_brain() maps legacy provider names to groups
- select_for_planning() returns "quality" group
"""

import pytest

from scrappy.orchestrator.provider_selector import ProviderSelector


class TestSetupBrainModelGroup:
    """Tests for setup_brain() returning model groups."""

    def test_setup_brain_returns_quality_group_by_default(self):
        """setup_brain() returns 'quality' group for brain/reasoning tasks."""
        selector = ProviderSelector()

        group, model = selector.setup_brain()

        assert group == "quality"
        assert model is None  # Router picks actual model

    def test_setup_brain_with_quality_group(self):
        """setup_brain() accepts 'quality' as preferred provider."""
        selector = ProviderSelector()

        group, model = selector.setup_brain(preferred_provider="quality")

        assert group == "quality"
        assert model is None

    def test_setup_brain_with_fast_group(self):
        """setup_brain() accepts 'fast' as preferred provider."""
        selector = ProviderSelector()

        group, model = selector.setup_brain(preferred_provider="fast")

        assert group == "fast"
        assert model is None

    def test_setup_brain_maps_legacy_provider_to_quality(self):
        """setup_brain() maps legacy provider names to 'quality' group."""
        selector = ProviderSelector()

        # Legacy provider names should map to quality for brain tasks
        group, model = selector.setup_brain(preferred_provider="gemini")

        assert group == "quality"
        assert model is None

    def test_setup_brain_maps_cerebras_to_quality(self):
        """setup_brain() maps 'cerebras' to 'quality' group."""
        selector = ProviderSelector()

        group, model = selector.setup_brain(preferred_provider="cerebras")

        assert group == "quality"
        assert model is None

    def test_setup_brain_logs_selection(self):
        """setup_brain() logs the selection decision."""
        selector = ProviderSelector(verbose=True)

        selector.setup_brain()

        log = selector.get_selection_log()
        assert len(log) > 0
        assert any("brain" in entry.lower() for entry in log)


class TestSelectForPlanningModelGroup:
    """Tests for select_for_planning() returning model groups."""

    def test_select_for_planning_returns_quality_group(self):
        """select_for_planning() returns 'quality' group."""
        selector = ProviderSelector()

        group, model = selector.select_for_planning()

        assert group == "quality"
        assert model is None  # Router picks actual model

    def test_select_for_planning_logs_selection(self):
        """select_for_planning() logs the selection decision."""
        selector = ProviderSelector(verbose=True)

        selector.select_for_planning()

        log = selector.get_selection_log()
        assert len(log) > 0
        assert any("planning" in entry.lower() or "quality" in entry.lower() for entry in log)


class TestGetProviderForFallbackModelGroup:
    """Tests for get_provider_for_fallback() returning model groups."""

    def test_fallback_returns_fast_by_default(self):
        """get_provider_for_fallback() returns 'fast' by default."""
        selector = ProviderSelector()

        result = selector.get_provider_for_fallback()

        assert result == "fast"

    def test_fallback_returns_quality_for_quality_selection(self):
        """get_provider_for_fallback() returns 'quality' for quality selection type."""
        from scrappy.orchestrator.model_selection import ModelSelectionType

        selector = ProviderSelector()

        result = selector.get_provider_for_fallback(
            selection_type=ModelSelectionType.QUALITY
        )

        assert result == "quality"

    def test_fallback_ignores_exclude_list(self):
        """get_provider_for_fallback() ignores exclude list (LiteLLM handles fallback)."""
        selector = ProviderSelector()

        # Exclude list should be ignored - LiteLLM Router handles fallback
        result = selector.get_provider_for_fallback(
            exclude=["cerebras", "groq", "gemini"]
        )

        # Should still return a valid group
        assert result in ("fast", "quality")


class TestRecommendModelGroup:
    """Tests for recommend() returning model groups."""

    def test_recommend_returns_fast_for_speed_priority(self):
        """recommend() returns 'fast' for speed priority."""
        selector = ProviderSelector()

        result = selector.recommend({"speed": "fast"})

        assert result == "fast"

    def test_recommend_returns_quality_for_excellent_quality(self):
        """recommend() returns 'quality' for excellent quality requirement."""
        selector = ProviderSelector()

        result = selector.recommend({"quality": "excellent"})

        assert result == "quality"

    def test_recommend_returns_fast_for_budget_sensitive(self):
        """recommend() returns 'fast' for budget-sensitive tasks."""
        selector = ProviderSelector()

        result = selector.recommend({"budget_sensitive": True})

        assert result == "fast"

    def test_recommend_returns_fast_by_default(self):
        """recommend() returns 'fast' by default."""
        selector = ProviderSelector()

        result = selector.recommend({})

        assert result == "fast"
