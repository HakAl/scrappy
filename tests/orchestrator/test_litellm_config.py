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

    def test_adds_quality_models_when_gemini_key_present(self):
        """Verify gemini key adds quality tier model."""
        api_key_service = MockApiKeyService(keys={
            "GEMINI_API_KEY": "test-gemini-key",
        })

        model_list = build_model_list(api_key_service)

        quality_models = [m for m in model_list if m["model_name"] == "quality"]
        assert len(quality_models) >= 1
        assert any(
            m["litellm_params"]["model"] == "gemini/gemini-2.5-flash"
            for m in quality_models
        )

    def test_adds_quality_models_when_groq_key_present(self):
        """Verify groq key adds quality tier models (70B variants)."""
        api_key_service = MockApiKeyService(keys={
            "GROQ_API_KEY": "test-groq-key",
        })

        model_list = build_model_list(api_key_service)

        quality_models = [m for m in model_list if m["model_name"] == "quality"]
        # Groq adds llama-3.3-70b-versatile and kimi-k2-instruct to quality
        assert len(quality_models) >= 2
        assert any(
            m["litellm_params"]["model"] == "groq/llama-3.3-70b-versatile"
            for m in quality_models
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

    def test_quality_tier_excludes_cerebras_70b(self):
        """Verify cerebras 70B is NOT in quality tier (only 8k context)."""
        api_key_service = MockApiKeyService(keys={
            "CEREBRAS_API_KEY": "test-cerebras-key",
            "GROQ_API_KEY": "test-groq-key",
        })

        model_list = build_model_list(api_key_service)

        quality_models = [m for m in model_list if m["model_name"] == "quality"]
        # No cerebras models in quality tier
        assert not any(
            "cerebras" in m["litellm_params"]["model"]
            for m in quality_models
        )


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
            assert call_kwargs["num_retries"] == 3
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

    def test_returns_quality_models(self):
        """Verify returns only quality tier models."""
        quality_models = get_models_for_group("quality")

        assert len(quality_models) >= 1
        assert all(m.group == "quality" for m in quality_models)

    def test_returns_empty_for_unknown_group(self):
        """Verify returns empty list for unknown group."""
        models = get_models_for_group("unknown")

        assert models == []


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

    def test_returns_quality_when_gemini_configured(self):
        """Verify quality group available when gemini key present."""
        api_key_service = MockApiKeyService(keys={
            "GEMINI_API_KEY": "test-key",
        })

        groups = get_available_groups(api_key_service)

        assert "quality" in groups

    def test_returns_both_when_groq_configured(self):
        """Verify both groups available when groq key present (has models in both)."""
        api_key_service = MockApiKeyService(keys={
            "GROQ_API_KEY": "test-key",
        })

        groups = get_available_groups(api_key_service)

        # Groq has models in both fast and quality tiers
        assert "fast" in groups
        assert "quality" in groups

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

    def test_all_quality_models_have_quality_group(self):
        """Verify quality models are correctly tagged."""
        quality_models = [m for m in MODEL_METADATA.values() if m.group == "quality"]

        assert len(quality_models) >= 2  # At least gemini and groq 70B

    def test_quality_models_have_32k_plus_context(self):
        """Verify quality models meet 32k context requirement."""
        quality_models = [m for m in MODEL_METADATA.values() if m.group == "quality"]

        for model in quality_models:
            assert model.context_length >= 32768, (
                f"{model.model_id} has only {model.context_length} context"
            )

    def test_metadata_has_required_fields(self):
        """Verify all metadata has required fields."""
        for model_id, metadata in MODEL_METADATA.items():
            assert metadata.model_id == model_id
            assert metadata.provider in ["groq", "cerebras", "gemini", "sambanova"]
            assert metadata.group in ["fast", "quality"]
            assert metadata.context_length > 0
            assert metadata.rpd > 0
            assert metadata.tpm > 0
