"""
Tests for ProviderResolver utility.

After LiteLLM integration, ProviderResolver directly maps ModelSelectionType
to model groups ("fast", "chat", "instruct"). No orchestrator/ProviderSelector needed.

Tests:
- Direct mapping: FAST -> "fast", CHAT -> "chat", INSTRUCT -> "instruct", EMBED -> "fast"
- None selection type returns (None, None)
- Model is always None (Router picks actual model)
"""

import pytest

from scrappy.task_router.provider_resolver import ProviderResolver
from scrappy.orchestrator.model_selection import ModelSelectionType, SELECTION_TYPE_TO_GROUP


class TestProviderResolverBasics:
    """Test basic provider resolution functionality."""

    def test_resolve_with_no_hint_returns_none(self):
        """Return (None, None) when no hint provided."""
        resolver = ProviderResolver()
        provider, model = resolver.resolve(None)

        assert provider is None
        assert model is None

    def test_resolver_does_not_need_orchestrator(self):
        """Orchestrator parameter is ignored (kept for backward compat)."""
        resolver = ProviderResolver(orchestrator="anything")
        provider, model = resolver.resolve(ModelSelectionType.FAST)

        # Should work without using orchestrator
        assert provider == "fast"
        assert model is None


class TestFastHintResolution:
    """Test resolution of FAST hint to 'fast' model group."""

    def test_fast_hint_returns_fast_group(self):
        """FAST hint should return 'fast' model group."""
        resolver = ProviderResolver()
        provider, model = resolver.resolve(ModelSelectionType.FAST)

        assert provider == "fast"
        assert model is None  # Router picks actual model

    def test_fast_group_is_in_mapping(self):
        """Verify FAST is in the selection mapping."""
        assert ModelSelectionType.FAST in SELECTION_TYPE_TO_GROUP
        assert SELECTION_TYPE_TO_GROUP[ModelSelectionType.FAST] == "fast"


class TestChatHintResolution:
    """Test resolution of CHAT hint."""

    def test_chat_hint_returns_chat_group(self):
        """CHAT hint should return 'chat' model group."""
        resolver = ProviderResolver()
        provider, model = resolver.resolve(ModelSelectionType.CHAT)

        assert provider == "chat"
        assert model is None  # Router picks actual model

    def test_chat_group_is_in_mapping(self):
        """Verify CHAT is in the selection mapping."""
        assert ModelSelectionType.CHAT in SELECTION_TYPE_TO_GROUP
        assert SELECTION_TYPE_TO_GROUP[ModelSelectionType.CHAT] == "chat"


class TestInstructHintResolution:
    """Test resolution of INSTRUCT hint."""

    def test_instruct_hint_returns_instruct_group(self):
        """INSTRUCT hint maps to 'instruct' group (best instruction-following models)."""
        resolver = ProviderResolver()
        provider, model = resolver.resolve(ModelSelectionType.INSTRUCT)

        assert provider == "instruct"
        assert model is None

    def test_instruct_group_is_in_mapping(self):
        """Verify INSTRUCT is in the selection mapping."""
        assert ModelSelectionType.INSTRUCT in SELECTION_TYPE_TO_GROUP
        assert SELECTION_TYPE_TO_GROUP[ModelSelectionType.INSTRUCT] == "instruct"


class TestEmbedHintResolution:
    """Test resolution of EMBED hint."""

    def test_embed_hint_returns_fast_group(self):
        """EMBED hint maps to 'fast' group."""
        resolver = ProviderResolver()
        provider, model = resolver.resolve(ModelSelectionType.EMBED)

        assert provider == "fast"
        assert model is None

    def test_embed_group_is_in_mapping(self):
        """Verify EMBED is in the selection mapping."""
        assert ModelSelectionType.EMBED in SELECTION_TYPE_TO_GROUP
        assert SELECTION_TYPE_TO_GROUP[ModelSelectionType.EMBED] == "fast"


class TestModelIsAlwaysNone:
    """Test that model is always None (Router picks actual model)."""

    @pytest.mark.parametrize("selection_type", list(ModelSelectionType))
    def test_model_is_none_for_all_types(self, selection_type):
        """Model should be None for all selection types."""
        resolver = ProviderResolver()
        _, model = resolver.resolve(selection_type)

        assert model is None


class TestResolverReusability:
    """Test that resolver can be reused for multiple resolutions."""

    def test_resolver_can_be_reused(self):
        """Same resolver instance can resolve multiple hints."""
        resolver = ProviderResolver()

        # Resolve multiple hints
        fast_group, _ = resolver.resolve(ModelSelectionType.FAST)
        chat_group, _ = resolver.resolve(ModelSelectionType.CHAT)

        assert fast_group == "fast"
        assert chat_group == "chat"

    def test_consistent_results(self):
        """Same input always produces same output."""
        resolver = ProviderResolver()

        # Call multiple times
        result1 = resolver.resolve(ModelSelectionType.FAST)
        result2 = resolver.resolve(ModelSelectionType.FAST)
        result3 = resolver.resolve(ModelSelectionType.FAST)

        assert result1 == result2 == result3 == ("fast", None)


class TestSelectionMappingComplete:
    """Test that all ModelSelectionType values are mapped."""

    def test_all_selection_types_mapped(self):
        """Every ModelSelectionType should have a mapping."""
        for selection_type in ModelSelectionType:
            assert selection_type in SELECTION_TYPE_TO_GROUP, (
                f"Missing mapping for {selection_type}"
            )

    def test_all_mappings_are_valid_groups(self):
        """All mapped values should be valid model groups."""
        valid_groups = {"fast", "chat", "instruct"}
        for selection_type, group in SELECTION_TYPE_TO_GROUP.items():
            assert group in valid_groups, (
                f"Invalid group '{group}' for {selection_type}"
            )
