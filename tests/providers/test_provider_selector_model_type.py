"""
Tests for ProviderSelector after LiteLLM integration.

After LiteLLM integration:
- ProviderSelector returns model groups ("fast", "quality") not provider names
- select_for_planning() returns "quality" group (instruction-tuned models are in quality tier)
- get_model() maps ModelSelectionType to groups
- Methods like get_best_instruct_model() are REMOVED - LiteLLM handles model selection
"""

import pytest

from scrappy.orchestrator.provider_selector import ProviderSelector
from scrappy.orchestrator.model_selection import ModelSelectionType, SELECTION_TYPE_TO_GROUP


class TestProviderSelectorInstructModels:
    """Test instruction-tuned model selection via model groups."""

    def test_select_for_planning_returns_quality_group(self):
        """Planning tasks return 'quality' model group (contains instruction-tuned models)."""
        selector = ProviderSelector()
        group, model = selector.select_for_planning()

        assert group == "quality"
        assert model is None  # Router picks actual model

    def test_instruct_selection_type_returns_quality_group(self):
        """INSTRUCT selection type maps to 'quality' group."""
        selector = ProviderSelector()
        group, model = selector.get_model(ModelSelectionType.INSTRUCT)

        assert group == "quality"
        assert model is None

    def test_select_for_planning_logs_decision(self):
        """Should log the model selection decision."""
        selector = ProviderSelector(verbose=True)
        selector.select_for_planning()

        log = selector.get_selection_log()
        assert len(log) > 0
        assert any("planning" in entry.lower() or "quality" in entry.lower() for entry in log)


class TestProviderSelectorModelGroups:
    """Tests for get_model() returning model groups."""

    def test_get_model_fast_returns_fast_group(self):
        """get_model with FAST returns 'fast' model group."""
        selector = ProviderSelector()
        group, model = selector.get_model(ModelSelectionType.FAST)

        assert group == "fast"
        assert model is None

    def test_get_model_quality_returns_quality_group(self):
        """get_model with QUALITY returns 'quality' model group."""
        selector = ProviderSelector()
        group, model = selector.get_model(ModelSelectionType.QUALITY)

        assert group == "quality"
        assert model is None

    def test_get_model_embed_returns_fast_group(self):
        """get_model with EMBED returns 'fast' model group."""
        selector = ProviderSelector()
        group, model = selector.get_model(ModelSelectionType.EMBED)

        assert group == "fast"
        assert model is None


class TestProviderSelectorPlanningIntegration:
    """Integration tests for planning model selection."""

    @pytest.mark.parametrize("selection_type,expected_group", [
        (ModelSelectionType.FAST, "fast"),
        (ModelSelectionType.QUALITY, "quality"),
        (ModelSelectionType.INSTRUCT, "quality"),
        (ModelSelectionType.EMBED, "fast"),
    ])
    def test_all_selection_types_return_valid_groups(self, selection_type, expected_group):
        """All selection types return valid model groups."""
        selector = ProviderSelector()
        group, model = selector.get_model(selection_type)

        assert group == expected_group
        assert model is None

    def test_selection_mapping_matches_module_constant(self):
        """Verify get_model() uses SELECTION_TYPE_TO_GROUP mapping."""
        selector = ProviderSelector()

        for selection_type, expected_group in SELECTION_TYPE_TO_GROUP.items():
            group, _ = selector.get_model(selection_type)
            assert group == expected_group
