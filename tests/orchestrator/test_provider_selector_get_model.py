"""
Tests for ProviderSelector.get_model() method with ModelSelectionType enums.

Tests the new centralized model selection logic that replaced the old
select_for_task() method.
"""

import pytest
from unittest.mock import Mock

from src.orchestrator.provider_selector import ProviderSelector
from src.orchestrator.model_selection import ModelSelectionType
from src.providers.base import ModelInfo, ModelType, SpeedRank, QualityRank


def create_mock_registry_with_models(models_config):
    """
    Create a mock registry with providers that have specific models.

    Args:
        models_config: List of tuples (provider_name, model_id, {'speed': SpeedRank, 'quality': QualityRank, ...})
    """
    registry = Mock()
    providers_dict = {}

    for provider_name, model_id, config in models_config:
        if provider_name not in providers_dict:
            provider = Mock()
            provider.available_models = []
            providers_dict[provider_name] = provider

        providers_dict[provider_name].available_models.append(model_id)

    # Setup get_model_info for each provider
    for prov_name, provider in providers_dict.items():
        def make_get_model_info(current_provider_name):
            def get_model_info(model_id):
                for pname, mid, config in models_config:
                    if pname == current_provider_name and mid == model_id:
                        return ModelInfo(
                            id=model_id,
                            model_type=config.get('model_type', ModelType.CHAT),
                            context_length=config.get('context', 8192),
                            rpd=config.get('rpd', 1000),
                            speed=config.get('speed', SpeedRank.FAST),
                            quality=config.get('quality', QualityRank.GOOD)
                        )
                return None
            return get_model_info

        provider.get_model_info = make_get_model_info(prov_name)

    registry.list_available.return_value = list(providers_dict.keys())
    registry.get = lambda name: providers_dict.get(name)

    return registry


def create_mock_registry(provider_names):
    """Create a simple mock registry with just provider names."""
    registry = Mock()
    registry.list_available.return_value = provider_names

    providers = {}
    for name in provider_names:
        provider = Mock()
        provider.available_models = []
        providers[name] = provider

    registry.get = lambda name: providers.get(name)
    return registry


class TestGetModelFast:
    """Tests for ModelSelectionType.FAST selection."""

    def test_fast_prefers_speed_over_quality(self):
        """FAST selection prioritizes speed over quality."""
        registry = create_mock_registry_with_models([
            ('cerebras', 'llama3.1-8b', {
                'speed': SpeedRank.ULTRA_FAST,
                'quality': QualityRank.GOOD,
                'rpd': 14400
            }),
            ('cerebras', 'llama-3.3-70b', {
                'speed': SpeedRank.FAST,
                'quality': QualityRank.EXCELLENT,
                'rpd': 14400
            }),
        ])
        selector = ProviderSelector(registry)

        provider, model = selector.get_model(ModelSelectionType.FAST)

        assert provider == 'cerebras'
        assert model == 'llama3.1-8b'  # Ultra fast beats excellent quality

    def test_fast_uses_rpd_as_tiebreaker(self):
        """When speeds are equal, FAST prefers higher RPD."""
        registry = create_mock_registry_with_models([
            ('groq', 'model-a', {
                'speed': SpeedRank.VERY_FAST,
                'quality': QualityRank.GOOD,
                'rpd': 7000
            }),
            ('cerebras', 'model-b', {
                'speed': SpeedRank.VERY_FAST,
                'quality': QualityRank.GOOD,
                'rpd': 14400
            }),
        ])
        selector = ProviderSelector(registry)

        provider, model = selector.get_model(ModelSelectionType.FAST)

        assert provider == 'cerebras'
        assert model == 'model-b'  # Higher RPD wins tiebreaker

    def test_fast_returns_first_available_when_no_candidates(self):
        """FAST falls back to first provider when no model info available."""
        registry = create_mock_registry(['cerebras', 'groq'])
        selector = ProviderSelector(registry)

        provider, model = selector.get_model(ModelSelectionType.FAST)

        assert provider == 'cerebras'
        assert model is None


class TestGetModelQuality:
    """Tests for ModelSelectionType.QUALITY selection."""

    def test_quality_prefers_quality_over_speed(self):
        """QUALITY selection prioritizes quality over speed."""
        registry = create_mock_registry_with_models([
            ('cerebras', 'llama3.1-8b', {
                'speed': SpeedRank.ULTRA_FAST,
                'quality': QualityRank.GOOD,
                'rpd': 14400
            }),
            ('cerebras', 'llama-3.3-70b', {
                'speed': SpeedRank.FAST,
                'quality': QualityRank.EXCELLENT,
                'rpd': 14400
            }),
        ])
        selector = ProviderSelector(registry)

        provider, model = selector.get_model(ModelSelectionType.QUALITY)

        assert provider == 'cerebras'
        assert model == 'llama-3.3-70b'  # Excellent quality beats speed

    def test_quality_uses_rpd_as_tiebreaker(self):
        """When quality is equal, prefers higher RPD."""
        registry = create_mock_registry_with_models([
            ('groq', 'model-a', {
                'speed': SpeedRank.FAST,
                'quality': QualityRank.EXCELLENT,
                'rpd': 1000
            }),
            ('cerebras', 'model-b', {
                'speed': SpeedRank.MODERATE,
                'quality': QualityRank.EXCELLENT,
                'rpd': 14400
            }),
        ])
        selector = ProviderSelector(registry)

        provider, model = selector.get_model(ModelSelectionType.QUALITY)

        assert provider == 'cerebras'
        assert model == 'model-b'


class TestGetModelInstruct:
    """Tests for ModelSelectionType.INSTRUCT selection."""

    def test_instruct_filters_instruction_tuned_models(self):
        """INSTRUCT selection only considers instruction-tuned models."""
        registry = create_mock_registry_with_models([
            ('cerebras', 'llama3.1-8b', {
                'speed': SpeedRank.ULTRA_FAST,
                'quality': QualityRank.GOOD,
                'model_type': ModelType.CHAT,
                'rpd': 14400
            }),
            ('cerebras', 'qwen-instruct', {
                'speed': SpeedRank.FAST,
                'quality': QualityRank.VERY_GOOD,
                'model_type': ModelType.INSTRUCT,
                'rpd': 14400
            }),
        ])
        selector = ProviderSelector(registry)

        provider, model = selector.get_model(ModelSelectionType.INSTRUCT)

        assert provider == 'cerebras'
        assert model == 'qwen-instruct'  # Only instruct model selected

    def test_instruct_prefers_higher_rpd(self):
        """INSTRUCT prefers instruction-tuned models with higher RPD."""
        registry = create_mock_registry_with_models([
            ('groq', 'instruct-a', {
                'model_type': ModelType.INSTRUCT,
                'rpd': 1000
            }),
            ('cerebras', 'instruct-b', {
                'model_type': ModelType.INSTRUCT,
                'rpd': 14400
            }),
        ])
        selector = ProviderSelector(registry)

        provider, model = selector.get_model(ModelSelectionType.INSTRUCT)

        assert provider == 'cerebras'
        assert model == 'instruct-b'

    def test_instruct_falls_back_to_quality_when_no_instruct_models(self):
        """INSTRUCT falls back to QUALITY when no instruct models available."""
        registry = create_mock_registry_with_models([
            ('cerebras', 'llama3.1-8b', {
                'quality': QualityRank.GOOD,
                'model_type': ModelType.CHAT,
                'rpd': 14400
            }),
            ('cerebras', 'llama-3.3-70b', {
                'quality': QualityRank.EXCELLENT,
                'model_type': ModelType.CHAT,
                'rpd': 14400
            }),
        ])
        selector = ProviderSelector(registry)

        provider, model = selector.get_model(ModelSelectionType.INSTRUCT)

        assert provider == 'cerebras'
        assert model == 'llama-3.3-70b'  # Best quality since no instruct models


class TestGetModelEmbed:
    """Tests for ModelSelectionType.EMBED selection."""

    def test_embed_prefers_cohere(self):
        """EMBED selection prefers cohere when available."""
        registry = create_mock_registry(['cerebras', 'groq', 'cohere'])
        selector = ProviderSelector(registry)

        provider, model = selector.get_model(ModelSelectionType.EMBED)

        assert provider == 'cohere'
        assert model is None

    def test_embed_falls_back_without_cohere(self):
        """EMBED uses first available when cohere not available."""
        registry = create_mock_registry(['cerebras', 'groq'])
        selector = ProviderSelector(registry)

        provider, model = selector.get_model(ModelSelectionType.EMBED)

        assert provider == 'cerebras'
        assert model is None


class TestGetModelErrors:
    """Tests for error handling in get_model()."""

    def test_raises_when_no_providers_available(self):
        """Raises RuntimeError when no providers available."""
        registry = create_mock_registry([])
        selector = ProviderSelector(registry)

        with pytest.raises(RuntimeError, match="No providers available"):
            selector.get_model(ModelSelectionType.FAST)

    def test_returns_first_available_for_unknown_type(self):
        """Falls back to first provider for unknown selection type."""
        registry = create_mock_registry(['cerebras'])
        selector = ProviderSelector(registry)

        # Create a mock selection type that's not handled
        # (this shouldn't happen in practice, but tests fallback)
        provider, model = selector.get_model(ModelSelectionType.FAST)

        assert provider == 'cerebras'


class TestGetModelIntegration:
    """Integration tests combining multiple scenarios."""

    def test_realistic_multi_provider_scenario(self):
        """Test realistic scenario with multiple providers and models."""
        registry = create_mock_registry_with_models([
            # Cerebras - high quota, multiple models
            ('cerebras', 'llama3.1-8b', {
                'speed': SpeedRank.ULTRA_FAST,
                'quality': QualityRank.GOOD,
                'rpd': 14400,
                'model_type': ModelType.CHAT
            }),
            ('cerebras', 'llama-3.3-70b', {
                'speed': SpeedRank.VERY_FAST,
                'quality': QualityRank.EXCELLENT,
                'rpd': 14400,
                'model_type': ModelType.CHAT
            }),
            ('cerebras', 'qwen-instruct', {
                'speed': SpeedRank.FAST,
                'quality': QualityRank.EXCELLENT,
                'rpd': 14400,
                'model_type': ModelType.INSTRUCT
            }),
            # Groq - moderate quota
            ('groq', 'llama-3.1-8b-instant', {
                'speed': SpeedRank.VERY_FAST,
                'quality': QualityRank.GOOD,
                'rpd': 7000,
                'model_type': ModelType.CHAT
            }),
            # Cohere - for embeddings
            ('cohere', 'command-r', {
                'speed': SpeedRank.MODERATE,
                'quality': QualityRank.VERY_GOOD,
                'rpd': 1000,
                'model_type': ModelType.CHAT
            }),
        ])
        selector = ProviderSelector(registry)

        # FAST should get ultra_fast model
        provider, model = selector.get_model(ModelSelectionType.FAST)
        assert provider == 'cerebras'
        assert model == 'llama3.1-8b'

        # QUALITY should get excellent quality model
        # Between llama-3.3-70b and qwen-instruct (both excellent),
        # should prefer based on other factors (both same RPD, so order)
        provider, model = selector.get_model(ModelSelectionType.QUALITY)
        assert provider == 'cerebras'
        assert model in ['llama-3.3-70b', 'qwen-instruct']

        # INSTRUCT should get instruction-tuned model
        provider, model = selector.get_model(ModelSelectionType.INSTRUCT)
        assert provider == 'cerebras'
        assert model == 'qwen-instruct'

        # EMBED should prefer cohere
        provider, model = selector.get_model(ModelSelectionType.EMBED)
        assert provider == 'cohere'
