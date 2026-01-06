"""Tests for ModelSelectionService."""

import pytest

from scrappy.orchestrator.model_selection import (
    ModelSelectionService,
    ModelSelectionType,
    MODEL_PRIORITIES,
)


class TestModelSelectionService:
    """Tests for deterministic model selection."""

    def test_returns_highest_priority_model_when_no_preference(self):
        """First model in priority list is returned when no session preference."""
        configured = {
            "groq/llama-3.1-8b-instant",
            "cerebras/llama3.1-8b",
        }
        service = ModelSelectionService(configured_models=configured)

        result = service.select(ModelSelectionType.FAST)

        # groq is first in MODEL_PRIORITIES[FAST]
        assert result == "groq/llama-3.1-8b-instant"

    def test_returns_session_preferred_when_available(self):
        """Session-preferred model is returned when it's still configured."""
        configured = {
            "groq/llama-3.1-8b-instant",
            "cerebras/llama3.1-8b",
        }
        service = ModelSelectionService(configured_models=configured)

        result = service.select(
            ModelSelectionType.FAST,
            session_preferred="cerebras/llama3.1-8b"
        )

        # Session preference takes precedence
        assert result == "cerebras/llama3.1-8b"

    def test_ignores_session_preferred_when_not_configured(self):
        """Falls back to priority list when session-preferred model is no longer configured."""
        configured = {
            "groq/llama-3.1-8b-instant",
            # cerebras NOT configured
        }
        service = ModelSelectionService(configured_models=configured)

        result = service.select(
            ModelSelectionType.FAST,
            session_preferred="cerebras/llama3.1-8b"  # Not in configured set
        )

        # Falls back to first available
        assert result == "groq/llama-3.1-8b-instant"

    def test_raises_when_no_models_configured_for_type(self):
        """Raises ValueError when no models are configured for selection type."""
        configured = set()  # Nothing configured
        service = ModelSelectionService(configured_models=configured)

        with pytest.raises(ValueError) as exc_info:
            service.select(ModelSelectionType.FAST)

        assert "No models configured for fast" in str(exc_info.value)

    def test_get_models_for_type_filters_by_configured(self):
        """get_models_for_type only returns configured models, in priority order."""
        configured = {
            "cerebras/llama3.1-8b",  # Second in priority
            # groq NOT configured (first in priority)
        }
        service = ModelSelectionService(configured_models=configured)

        result = service.get_models_for_type(ModelSelectionType.FAST)

        # Only cerebras is returned (groq not configured)
        assert result == ["cerebras/llama3.1-8b"]

    def test_preserves_priority_order(self):
        """Models are returned in priority order, not arbitrary order."""
        configured = {
            "sambanova/Meta-Llama-3.1-8B-Instruct",  # Third priority
            "groq/llama-3.1-8b-instant",             # First priority
            "cerebras/llama3.1-8b",                  # Second priority
        }
        service = ModelSelectionService(configured_models=configured)

        result = service.get_models_for_type(ModelSelectionType.FAST)

        # Priority order preserved
        assert result == [
            "groq/llama-3.1-8b-instant",
            "cerebras/llama3.1-8b",
            "sambanova/Meta-Llama-3.1-8B-Instruct",
        ]

    def test_is_configured(self):
        """is_configured correctly checks if model has API key."""
        configured = {"groq/llama-3.1-8b-instant"}
        service = ModelSelectionService(configured_models=configured)

        assert service.is_configured("groq/llama-3.1-8b-instant") is True
        assert service.is_configured("cerebras/llama3.1-8b") is False

    def test_chat_models_selection(self):
        """CHAT selection type uses correct priority list."""
        configured = {
            "cerebras/llama-3.3-70b",
            "groq/llama-3.3-70b-versatile",
        }
        service = ModelSelectionService(configured_models=configured)

        result = service.select(ModelSelectionType.CHAT)

        # Cerebras 70B is first in CHAT priorities
        assert result == "cerebras/llama-3.3-70b"

    def test_instruct_models_selection(self):
        """Instruct selection type uses correct priority list."""
        configured = {
            "cerebras/qwen-3-235b-a22b-instruct-2507",
            "groq/meta-llama/llama-4-scout-17b-16e-instruct",
        }
        service = ModelSelectionService(configured_models=configured)

        result = service.select(ModelSelectionType.INSTRUCT)

        # Cerebras qwen is first in INSTRUCT priorities
        assert result == "cerebras/qwen-3-235b-a22b-instruct-2507"

    def test_session_preference_ignored_for_wrong_type(self):
        """Session preference for INSTRUCT doesn't affect FAST selection."""
        configured = {
            "groq/llama-3.1-8b-instant",
            "cerebras/qwen-3-235b-a22b-instruct-2507",
        }
        service = ModelSelectionService(configured_models=configured)

        # Session preferred an INSTRUCT model, but selecting FAST
        result = service.select(
            ModelSelectionType.FAST,
            session_preferred="cerebras/qwen-3-235b-a22b-instruct-2507"
        )

        # INSTRUCT model isn't in FAST list, so falls back to priority
        assert result == "groq/llama-3.1-8b-instant"


class TestModelSelectionServiceCustomPriorities:
    """Tests for custom priority configurations."""

    def test_custom_priorities_override_defaults(self):
        """Custom priorities can override default MODEL_PRIORITIES."""
        custom_priorities = {
            ModelSelectionType.FAST: [
                "custom/model-a",
                "custom/model-b",
            ],
        }
        configured = {"custom/model-a", "custom/model-b"}
        service = ModelSelectionService(
            configured_models=configured,
            model_priorities=custom_priorities
        )

        result = service.select(ModelSelectionType.FAST)

        assert result == "custom/model-a"



class TestModelPrioritiesConfig:
    """Tests for MODEL_PRIORITIES configuration."""

    def test_fast_priorities_exist(self):
        """FAST selection type has priority list defined."""
        assert ModelSelectionType.FAST in MODEL_PRIORITIES
        assert len(MODEL_PRIORITIES[ModelSelectionType.FAST]) > 0

    def test_chat_priorities_exist(self):
        """CHAT selection type has priority list defined."""
        assert ModelSelectionType.CHAT in MODEL_PRIORITIES
        assert len(MODEL_PRIORITIES[ModelSelectionType.CHAT]) > 0

    def test_instruct_priorities_exist(self):
        """INSTRUCT selection type has priority list defined."""
        assert ModelSelectionType.INSTRUCT in MODEL_PRIORITIES
        assert len(MODEL_PRIORITIES[ModelSelectionType.INSTRUCT]) > 0

    def test_all_models_have_provider_prefix(self):
        """All models in priorities have provider/model format."""
        for selection_type, models in MODEL_PRIORITIES.items():
            for model_id in models:
                assert "/" in model_id, f"{model_id} missing provider prefix"
