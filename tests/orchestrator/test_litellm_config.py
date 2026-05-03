"""
Tests for LiteLLM router configuration.

Tests model group configuration and API key handling.
"""

import pytest
from unittest.mock import patch, MagicMock

from scrappy.orchestrator.litellm_config import (
    create_litellm_router,
    build_model_list,
    get_models_for_group,
    get_configured_models,
    get_available_groups,
    MODEL_METADATA,
)

from tests.helpers import MockApiKeyService


class TestBuildModelList:
    """Tests for build_model_list function."""

    def test_adds_fast_models_when_groq_key_present(self):
        """Verify groq key adds fast tier model."""
        api_key_service = MockApiKeyService(keys={
            "GROQ_API_KEY": "test-groq-key",
        })

        model_list = build_model_list(api_key_service)

        fast_models = [m for m in model_list if m["model_name"] == "fast"]
        assert len(fast_models) >= 1
        assert any(
            m["litellm_params"]["model"] == "groq/llama-3.1-8b-instant"
            for m in fast_models
        )

    def test_adds_fast_models_when_cerebras_key_present(self):
        """Verify cerebras key adds fast tier model."""
        api_key_service = MockApiKeyService(keys={
            "CEREBRAS_API_KEY": "test-cerebras-key",
        })

        model_list = build_model_list(api_key_service)

        fast_models = [m for m in model_list if m["model_name"] == "fast"]
        assert len(fast_models) >= 1
        assert any(
            m["litellm_params"]["model"] == "cerebras/llama3.1-8b"
            for m in fast_models
        )

    def test_adds_instruct_models_when_gemini_key_present(self):
        """Verify gemini key adds instruct tier model."""
        api_key_service = MockApiKeyService(keys={
            "GEMINI_API_KEY": "test-gemini-key",
        })

        model_list = build_model_list(api_key_service)

        instruct_models = [m for m in model_list if m["model_name"] == "instruct"]
        assert len(instruct_models) >= 1
        assert any(
            m["litellm_params"]["model"] == "gemini/gemini-2.5-flash"
            for m in instruct_models
        )

    def test_adds_instruct_models_when_groq_key_present(self):
        """Verify groq key adds instruct tier models (kimi-k2)."""
        api_key_service = MockApiKeyService(keys={
            "GROQ_API_KEY": "test-groq-key",
        })

        model_list = build_model_list(api_key_service)

        instruct_models = [m for m in model_list if m["model_name"] == "instruct"]
        # Groq adds kimi-k2 to instruct tier
        assert len(instruct_models) >= 1
        assert any(
            m["litellm_params"]["model"] == "groq/moonshotai/kimi-k2-instruct"
            for m in instruct_models
        )

    def test_skips_models_when_api_key_missing(self):
        """Verify missing keys don't add models."""
        # Only groq key, no cerebras or gemini
        api_key_service = MockApiKeyService(keys={
            "GROQ_API_KEY": "test-groq-key",
            "CEREBRAS_API_KEY": None,
            "GEMINI_API_KEY": None,
        })

        model_list = build_model_list(api_key_service)

        # Should not have cerebras or gemini models
        assert not any(
            "cerebras" in m["litellm_params"]["model"]
            for m in model_list
        )
        assert not any(
            "gemini" in m["litellm_params"]["model"]
            for m in model_list
        )

    def test_empty_model_list_returns_empty(self):
        """Verify no keys returns empty list."""
        api_key_service = MockApiKeyService(keys={})

        model_list = build_model_list(api_key_service)

        assert model_list == []

    def test_fast_tier_priority_groq_before_cerebras(self):
        """Verify groq is added before cerebras in fast tier (priority order)."""
        api_key_service = MockApiKeyService(keys={
            "GROQ_API_KEY": "test-groq-key",
            "CEREBRAS_API_KEY": "test-cerebras-key",
        })

        model_list = build_model_list(api_key_service)

        fast_models = [m for m in model_list if m["model_name"] == "fast"]
        # Groq should come before Cerebras
        groq_idx = next(
            i for i, m in enumerate(fast_models)
            if "groq" in m["litellm_params"]["model"]
        )
        cerebras_idx = next(
            i for i, m in enumerate(fast_models)
            if "cerebras" in m["litellm_params"]["model"]
        )
        assert groq_idx < cerebras_idx

    def test_instruct_tier_prioritizes_stable_and_free_tier_models(self):
        """Verify instruct tier starts with stable/default agent models."""
        api_key_service = MockApiKeyService(keys={
            "CEREBRAS_API_KEY": "test-cerebras-key",
            "GROQ_API_KEY": "test-groq-key",
            "GEMINI_API_KEY": "test-gemini-key",
        })

        model_list = build_model_list(api_key_service)

        instruct_models = [m for m in model_list if m["model_name"] == "instruct"]
        instruct_ids = [m["litellm_params"]["model"] for m in instruct_models]

        assert instruct_ids[:4] == [
            "cerebras/gpt-oss-120b",
            "groq/moonshotai/kimi-k2-instruct",
            "cerebras/zai-glm-4.7",
            "gemini/gemini-2.5-flash",
        ]
        assert "cerebras/qwen-3-235b-a22b-instruct-2507" in instruct_ids


class TestCreateLiteLLMRouter:
    """Tests for create_litellm_router factory."""

    def test_router_configured_with_callbacks(self):
        """Verify callbacks are set globally on litellm module."""
        import litellm

        mock_callback = MagicMock()

        with patch("litellm.Router") as mock_router_class:
            mock_router = MagicMock()
            mock_router_class.return_value = mock_router

            create_litellm_router(callbacks=[mock_callback])

            # Callbacks are set globally, not passed to Router
            assert mock_callback in litellm.callbacks

    def test_router_configured_with_retry_settings(self):
        """Verify router has correct retry configuration."""
        with patch("litellm.Router") as mock_router_class:
            mock_router = MagicMock()
            mock_router_class.return_value = mock_router

            create_litellm_router()

            call_kwargs = mock_router_class.call_args[1]
            # num_retries=1: reduced to let graph fallback chain handle retries deterministically
            assert call_kwargs["num_retries"] == 1
            assert call_kwargs["timeout"] == 60
            assert call_kwargs["retry_after"] == 5
            assert call_kwargs["routing_strategy"] == "simple-shuffle"

    def test_router_starts_with_empty_model_list(self):
        """Verify router is created with empty model list."""
        with patch("litellm.Router") as mock_router_class:
            mock_router = MagicMock()
            mock_router_class.return_value = mock_router

            create_litellm_router()

            call_kwargs = mock_router_class.call_args[1]
            assert call_kwargs["model_list"] == []


class TestGetModelsForGroup:
    """Tests for get_models_for_group helper."""

    def test_returns_fast_models(self):
        """Verify returns only fast tier models."""
        fast_models = get_models_for_group("fast")

        assert len(fast_models) >= 1
        assert all(m.group == "fast" for m in fast_models)

    def test_returns_instruct_models(self):
        """Verify returns only instruct tier models."""
        instruct_models = get_models_for_group("instruct")

        assert len(instruct_models) >= 1
        assert all(m.group == "instruct" for m in instruct_models)



class TestGetConfiguredModels:
    """Tests for get_configured_models helper."""

    def test_returns_models_with_keys(self):
        """Verify returns only models with configured keys."""
        api_key_service = MockApiKeyService(keys={
            "GROQ_API_KEY": "test-key",
        })

        models = get_configured_models(api_key_service)

        assert len(models) >= 1
        assert all(m.provider == "groq" for m in models)

    def test_excludes_models_without_keys(self):
        """Verify excludes models without configured keys."""
        api_key_service = MockApiKeyService(keys={
            "GROQ_API_KEY": "test-key",
            "CEREBRAS_API_KEY": None,
        })

        models = get_configured_models(api_key_service)

        assert not any(m.provider == "cerebras" for m in models)

    def test_returns_empty_when_no_keys(self):
        """Verify returns empty when no keys configured."""
        api_key_service = MockApiKeyService(keys={})

        models = get_configured_models(api_key_service)

        assert models == []


class TestGetAvailableGroups:
    """Tests for get_available_groups helper."""

    def test_returns_fast_when_groq_configured(self):
        """Verify fast group available when groq key present."""
        api_key_service = MockApiKeyService(keys={
            "GROQ_API_KEY": "test-key",
        })

        groups = get_available_groups(api_key_service)

        assert "fast" in groups

    def test_returns_instruct_when_gemini_configured(self):
        """Verify instruct group available when gemini key present."""
        api_key_service = MockApiKeyService(keys={
            "GEMINI_API_KEY": "test-key",
        })

        groups = get_available_groups(api_key_service)

        assert "instruct" in groups

    def test_returns_multiple_when_groq_configured(self):
        """Verify multiple groups available when groq key present (has models in fast, chat, instruct)."""
        api_key_service = MockApiKeyService(keys={
            "GROQ_API_KEY": "test-key",
        })

        groups = get_available_groups(api_key_service)

        # Groq has models in fast, chat, and instruct tiers
        assert "fast" in groups
        assert "instruct" in groups

    def test_returns_empty_when_no_keys(self):
        """Verify empty when no keys configured."""
        api_key_service = MockApiKeyService(keys={})

        groups = get_available_groups(api_key_service)

        assert groups == set()


class TestModelMetadata:
    """Tests for MODEL_METADATA constants."""

    def test_all_fast_models_have_fast_group(self):
        """Verify fast models are correctly tagged."""
        fast_models = [m for m in MODEL_METADATA.values() if m.group == "fast"]

        assert len(fast_models) >= 2  # At least groq and cerebras 8B

    def test_all_instruct_models_have_instruct_group(self):
        """Verify instruct models are correctly tagged."""
        instruct_models = [m for m in MODEL_METADATA.values() if m.group == "instruct"]

        assert len(instruct_models) >= 2  # At least gemini and qwen-235b

    def test_instruct_models_used_for_agent_have_reasonable_context(self):
        """Verify instruct models used for agent routing have reasonable context.

        Note: MODEL_METADATA includes all models for status display, but
        build_model_list() controls actual agent routing. Models in metadata
        may have varying context lengths.
        """
        # Models actually used for agent instruct tier (from build_model_list)
        agent_instruct_models = [
            "cerebras/gpt-oss-120b",
            "groq/moonshotai/kimi-k2-instruct",
            "cerebras/zai-glm-4.7",
            "gemini/gemini-2.5-flash",
        ]

        for model_id in agent_instruct_models:
            if model_id in MODEL_METADATA:
                model = MODEL_METADATA[model_id]
                # Agent instruct models should have reasonable context (8k+)
                assert model.context_length >= 8192, (
                    f"{model.model_id} has only {model.context_length} context"
                )

    def test_metadata_has_required_fields(self):
        """Verify all metadata has required fields."""
        for model_id, metadata in MODEL_METADATA.items():
            assert metadata.model_id == model_id
            assert metadata.provider in ["groq", "cerebras", "gemini", "sambanova"]
            assert metadata.group in ["fast", "chat", "instruct"]
            assert metadata.context_length > 0
            assert metadata.rpd > 0
            assert metadata.tpm > 0
