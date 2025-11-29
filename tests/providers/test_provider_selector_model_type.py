"""
Tests for ProviderSelector instruction-tuned model selection.

Tests the orchestrator's ability to automatically select instruction-tuned
models for tasks that require JSON compliance (like agent planning).
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.orchestrator.provider_selector import ProviderSelector
from src.providers.base import ProviderRegistry, ModelType, ModelInfo


class TestProviderSelectorInstructModels:
    """Test instruction-tuned model selection in ProviderSelector."""

    def _create_mock_registry(self, providers_config: dict) -> ProviderRegistry:
        """
        Create a mock registry with specified providers.

        Args:
            providers_config: Dict of provider_name -> list of (model_id, ModelInfo)
        """
        registry = ProviderRegistry()

        for provider_name, models in providers_config.items():
            provider = MagicMock()
            provider.name = provider_name
            provider.is_available.return_value = True

            # Set up available_models
            model_ids = [m[0] for m in models]
            type(provider).available_models = PropertyMock(return_value=model_ids)
            type(provider).default_model = PropertyMock(return_value=model_ids[0] if model_ids else "")

            # Set up get_model_info
            model_info_map = {m[0]: m[1] for m in models}

            def make_get_model_info(info_map):
                def get_model_info(model_id):
                    return info_map.get(model_id, ModelInfo(model_id, ModelType.UNKNOWN, 4096))
                return get_model_info

            provider.get_model_info = make_get_model_info(model_info_map)

            # Set up get_instruction_tuned_models
            def make_get_instruct(info_map):
                def get_instruction_tuned_models():
                    return [mid for mid, info in info_map.items() if info.is_instruction_tuned]
                return get_instruction_tuned_models

            provider.get_instruction_tuned_models = make_get_instruct(model_info_map)

            # Mock get_model_for_task
            provider.get_model_for_task.return_value = model_ids[0] if model_ids else ""

            registry.register(provider)

        return registry

    def test_select_for_planning_prefers_instruct_models(self):
        """Planning tasks should prefer instruction-tuned models."""
        registry = self._create_mock_registry({
            "groq": [
                ("llama-3.3-70b-versatile", ModelInfo("llama-3.3-70b-versatile", ModelType.CHAT, 32768, rpd=1000)),
                ("gemma2-9b-it", ModelInfo("gemma2-9b-it", ModelType.INSTRUCT, 8192, rpd=14400)),
            ]
        })

        selector = ProviderSelector(registry)
        provider_name, model = selector.select_for_planning()

        assert provider_name == "groq"
        assert model == "gemma2-9b-it"  # Should pick instruction-tuned model

    def test_select_for_planning_prioritizes_high_rpd_instruct(self):
        """Should prefer instruction-tuned models with highest RPD."""
        registry = self._create_mock_registry({
            "groq": [
                ("gemma2-9b-it", ModelInfo("gemma2-9b-it", ModelType.INSTRUCT, 8192, rpd=14400)),
                ("llama-3.3-70b-versatile", ModelInfo("llama-3.3-70b-versatile", ModelType.CHAT, 32768, rpd=1000)),
            ],
            "cerebras": [
                ("llama3.1-8b", ModelInfo("llama3.1-8b", ModelType.UNKNOWN, 8192, rpd=14400)),
            ]
        })

        selector = ProviderSelector(registry)
        provider_name, model = selector.select_for_planning()

        # Should pick groq's gemma2-9b-it because it's instruction-tuned with high RPD
        assert provider_name == "groq"
        assert model == "gemma2-9b-it"

    def test_select_for_planning_falls_back_to_chat_if_no_instruct(self):
        """Should fall back to chat models if no instruction-tuned available."""
        registry = self._create_mock_registry({
            "groq": [
                ("llama-3.3-70b-versatile", ModelInfo("llama-3.3-70b-versatile", ModelType.CHAT, 32768, rpd=1000)),
            ]
        })

        selector = ProviderSelector(registry)
        provider_name, model = selector.select_for_planning()

        # Should fall back to chat model
        assert provider_name == "groq"
        assert model == "llama-3.3-70b-versatile"

    def test_select_for_planning_uses_default_if_no_instruct_or_chat(self):
        """Should use default model if no instruction or chat models."""
        registry = self._create_mock_registry({
            "cerebras": [
                ("llama3.1-8b", ModelInfo("llama3.1-8b", ModelType.UNKNOWN, 8192, rpd=14400)),
            ]
        })

        selector = ProviderSelector(registry)
        provider_name, model = selector.select_for_planning()

        # Should use what's available
        assert provider_name == "cerebras"
        assert model == "llama3.1-8b"

    def test_select_for_planning_with_multiple_providers(self):
        """Should compare across providers and pick best instruction-tuned."""
        registry = self._create_mock_registry({
            "cerebras": [
                ("llama3.1-8b", ModelInfo("llama3.1-8b", ModelType.UNKNOWN, 8192, rpd=14400)),
            ],
            "groq": [
                ("gemma2-9b-it", ModelInfo("gemma2-9b-it", ModelType.INSTRUCT, 8192, rpd=14400)),
            ],
            "gemini": [
                ("gemini-2.5-flash", ModelInfo("gemini-2.5-flash", ModelType.CHAT, 1048576, rpd=250)),
            ]
        })

        selector = ProviderSelector(registry)
        provider_name, model = selector.select_for_planning()

        # Should pick groq's instruction-tuned model over cerebras's unknown
        assert provider_name == "groq"
        assert model == "gemma2-9b-it"

    def test_get_best_instruct_model_from_provider(self):
        """Should get best instruction-tuned model from a specific provider."""
        registry = self._create_mock_registry({
            "groq": [
                ("llama-3.1-8b-instant", ModelInfo("llama-3.1-8b-instant", ModelType.UNKNOWN, 131072, rpd=7000)),
                ("gemma2-9b-it", ModelInfo("gemma2-9b-it", ModelType.INSTRUCT, 8192, rpd=14400)),
                ("llama-3.3-70b-versatile", ModelInfo("llama-3.3-70b-versatile", ModelType.CHAT, 32768, rpd=1000)),
            ]
        })

        selector = ProviderSelector(registry)
        model = selector.get_best_instruct_model("groq")

        assert model == "gemma2-9b-it"

    def test_get_best_instruct_model_returns_none_if_no_instruct(self):
        """Should return None if provider has no instruction-tuned models."""
        registry = self._create_mock_registry({
            "cerebras": [
                ("llama3.1-8b", ModelInfo("llama3.1-8b", ModelType.UNKNOWN, 8192, rpd=14400)),
            ]
        })

        selector = ProviderSelector(registry)
        model = selector.get_best_instruct_model("cerebras")

        assert model is None

    def test_get_best_instruct_model_prefers_higher_rpd(self):
        """Should prefer instruction-tuned model with higher RPD."""
        registry = self._create_mock_registry({
            "groq": [
                ("low-quota-instruct", ModelInfo("low-quota-instruct", ModelType.INSTRUCT, 8192, rpd=1000)),
                ("high-quota-instruct", ModelInfo("high-quota-instruct", ModelType.INSTRUCT, 8192, rpd=14400)),
            ]
        })

        selector = ProviderSelector(registry)
        model = selector.get_best_instruct_model("groq")

        assert model == "high-quota-instruct"

    def test_has_instruction_tuned_models(self):
        """Should detect if any provider has instruction-tuned models."""
        registry = self._create_mock_registry({
            "groq": [
                ("gemma2-9b-it", ModelInfo("gemma2-9b-it", ModelType.INSTRUCT, 8192, rpd=14400)),
            ]
        })

        selector = ProviderSelector(registry)
        assert selector.has_instruction_tuned_models() is True

    def test_has_instruction_tuned_models_false(self):
        """Should return False if no instruction-tuned models available."""
        registry = self._create_mock_registry({
            "cerebras": [
                ("llama3.1-8b", ModelInfo("llama3.1-8b", ModelType.UNKNOWN, 8192, rpd=14400)),
            ]
        })

        selector = ProviderSelector(registry)
        assert selector.has_instruction_tuned_models() is False

    def test_list_instruction_tuned_models(self):
        """Should list all instruction-tuned models across providers."""
        registry = self._create_mock_registry({
            "groq": [
                ("gemma2-9b-it", ModelInfo("gemma2-9b-it", ModelType.INSTRUCT, 8192, rpd=14400)),
                ("llama-3.3-70b-versatile", ModelInfo("llama-3.3-70b-versatile", ModelType.CHAT, 32768, rpd=1000)),
            ],
            "cerebras": [
                ("qwen-instruct", ModelInfo("qwen-instruct", ModelType.INSTRUCT, 8192, rpd=14400)),
            ]
        })

        selector = ProviderSelector(registry)
        instruct_models = selector.list_instruction_tuned_models()

        assert len(instruct_models) == 2
        assert ("groq", "gemma2-9b-it") in instruct_models
        assert ("cerebras", "qwen-instruct") in instruct_models

    def test_select_for_planning_logs_decision(self):
        """Should log the model selection decision."""
        registry = self._create_mock_registry({
            "groq": [
                ("gemma2-9b-it", ModelInfo("gemma2-9b-it", ModelType.INSTRUCT, 8192, rpd=14400)),
            ]
        })

        selector = ProviderSelector(registry, verbose=False)
        selector.select_for_planning()

        log = selector.get_selection_log()
        assert any("instruction-tuned" in entry.lower() or "instruct" in entry.lower() for entry in log)


class TestProviderSelectorPlanningIntegration:
    """Integration tests for planning model selection."""

    def test_get_model_fast_still_works(self):
        """get_model with FAST should work correctly."""
        registry = ProviderRegistry()

        provider = MagicMock()
        provider.name = "cerebras"
        provider.is_available.return_value = True
        type(provider).available_models = PropertyMock(return_value=["llama3.1-8b"])

        registry.register(provider)

        selector = ProviderSelector(registry)
        from src.orchestrator.model_selection import ModelSelectionType
        provider_name, model = selector.get_model(ModelSelectionType.FAST)

        assert provider_name == "cerebras"
        assert model == "llama3.1-8b"

    def test_get_model_instruct_uses_instruction_tuned(self):
        """get_model with INSTRUCT should use instruction-tuned selection."""
        registry = ProviderRegistry()

        provider = MagicMock()
        provider.name = "groq"
        provider.is_available.return_value = True
        type(provider).available_models = PropertyMock(return_value=["gemma2-9b-it", "llama-3.3-70b-versatile"])

        # Set up model info
        def get_model_info(model_id):
            if model_id == "gemma2-9b-it":
                return ModelInfo("gemma2-9b-it", ModelType.INSTRUCT, 8192, rpd=14400)
            else:
                return ModelInfo(model_id, ModelType.CHAT, 32768, rpd=1000)

        provider.get_model_info = get_model_info

        def get_instruction_tuned():
            return ["gemma2-9b-it"]

        provider.get_instruction_tuned_models = get_instruction_tuned

        registry.register(provider)

        selector = ProviderSelector(registry)

        # INSTRUCT type should prefer instruction-tuned
        from src.orchestrator.model_selection import ModelSelectionType
        provider_name, model = selector.get_model(ModelSelectionType.INSTRUCT)

        assert provider_name == "groq"
        assert model == "gemma2-9b-it"  # Should pick instruction-tuned
