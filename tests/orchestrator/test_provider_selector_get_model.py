"""
Tests for ProviderSelector.get_model() after LiteLLM integration.

After LiteLLM integration, get_model() returns model groups ("fast", "chat", "instruct")
instead of provider names. The LiteLLM Router handles actual model selection.

Tests:
- FAST -> "fast" group
- CHAT -> "chat" group
- INSTRUCT -> "instruct" group
- EMBED -> "fast" group
- Model is always None (Router picks actual model)
"""

import pytest

from scrappy.orchestrator.provider_selector import ProviderSelector
from scrappy.orchestrator.model_selection import ModelSelectionType, SELECTION_TYPE_TO_GROUP


class TestGetModelFast:
    """Tests for ModelSelectionType.FAST selection."""

    def test_fast_returns_fast_group(self):
        """FAST selection returns 'fast' model group."""
        selector = ProviderSelector()
        group, model = selector.get_model(ModelSelectionType.FAST)

        assert group == "fast"
        assert model is None

    def test_fast_logs_selection(self):
        """FAST selection should log the decision."""
        selector = ProviderSelector(verbose=True)
        selector.get_model(ModelSelectionType.FAST)

        log = selector.get_selection_log()
        assert any("fast" in entry.lower() for entry in log)


class TestGetModelChat:
    """Tests for ModelSelectionType.CHAT selection."""

    def test_chat_returns_chat_group(self):
        """CHAT selection returns 'chat' model group."""
        selector = ProviderSelector()
        group, model = selector.get_model(ModelSelectionType.CHAT)

        assert group == "chat"
        assert model is None

    def test_chat_logs_selection(self):
        """CHAT selection should log the decision."""
        selector = ProviderSelector(verbose=True)
        selector.get_model(ModelSelectionType.CHAT)

        log = selector.get_selection_log()
        assert any("chat" in entry.lower() for entry in log)


class TestGetModelInstruct:
    """Tests for ModelSelectionType.INSTRUCT selection."""

    def test_instruct_returns_instruct_group(self):
        """INSTRUCT selection maps to 'instruct' group."""
        selector = ProviderSelector()
        group, model = selector.get_model(ModelSelectionType.INSTRUCT)

        assert group == "instruct"
        assert model is None


class TestGetModelEmbed:
    """Tests for ModelSelectionType.EMBED selection."""

    def test_embed_returns_fast_group(self):
        """EMBED selection maps to 'fast' group."""
        selector = ProviderSelector()
        group, model = selector.get_model(ModelSelectionType.EMBED)

        assert group == "fast"
        assert model is None


class TestGetModelErrors:
    """Test error handling in get_model()."""

    def test_all_valid_types_return_valid_groups(self):
        """All valid ModelSelectionType values return valid groups."""
        selector = ProviderSelector(verbose=True)
        selector.clear_selection_log()

        for selection_type in ModelSelectionType:
            group, model = selector.get_model(selection_type)
            assert group in ("fast", "chat", "instruct")
            assert model is None


class TestGetModelIntegration:
    """Integration tests for get_model()."""

    @pytest.mark.parametrize("selection_type,expected_group", [
        (ModelSelectionType.FAST, "fast"),
        (ModelSelectionType.CHAT, "chat"),
        (ModelSelectionType.INSTRUCT, "instruct"),
        (ModelSelectionType.EMBED, "fast"),
    ])
    def test_all_selection_types_return_valid_groups(self, selection_type, expected_group):
        """All selection types should return valid model groups."""
        selector = ProviderSelector()
        group, model = selector.get_model(selection_type)

        assert group == expected_group
        assert model is None  # Router picks actual model

    def test_selection_mapping_matches_module_constant(self):
        """Verify get_model() uses SELECTION_TYPE_TO_GROUP mapping."""
        selector = ProviderSelector()

        for selection_type, expected_group in SELECTION_TYPE_TO_GROUP.items():
            group, _ = selector.get_model(selection_type)
            assert group == expected_group
