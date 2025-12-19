"""Tests for model availability tracking and rate limit handling."""

import time
import pytest
from unittest.mock import patch

from scrappy.orchestrator.model_selection import (
    ModelAvailabilityTracker,
    ModelSelectionService,
    ModelSelectionType,
    AllModelsRateLimitedError,
)


class TestModelAvailabilityTracker:
    """Test rate limit tracking with cooldown."""

    def test_model_available_by_default(self):
        """Models are available when not rate limited."""
        tracker = ModelAvailabilityTracker()

        assert tracker.is_available("groq/llama-3.1-8b") is True

    def test_model_unavailable_after_rate_limit(self):
        """Model becomes unavailable after rate limit."""
        tracker = ModelAvailabilityTracker()

        tracker.mark_rate_limited("groq/llama-3.1-8b")

        assert tracker.is_available("groq/llama-3.1-8b") is False


    def test_get_available_filters_rate_limited(self):
        """get_available removes rate-limited models from list."""
        tracker = ModelAvailabilityTracker()

        models = [
            "groq/llama-3.1-8b",
            "cerebras/llama3.1-8b",
            "gemini/gemini-2.5-flash",
        ]

        tracker.mark_rate_limited("cerebras/llama3.1-8b")

        available = tracker.get_available(models)

        assert available == ["groq/llama-3.1-8b", "gemini/gemini-2.5-flash"]

    def test_get_available_preserves_order(self):
        """get_available preserves priority order of input list."""
        tracker = ModelAvailabilityTracker()

        models = ["model-a", "model-b", "model-c"]

        tracker.mark_rate_limited("model-b")

        available = tracker.get_available(models)

        assert available == ["model-a", "model-c"]

    def test_get_cooldown_remaining_zero_when_available(self):
        """Cooldown remaining is 0 for available models."""
        tracker = ModelAvailabilityTracker()

        remaining = tracker.get_cooldown_remaining("groq/llama-3.1-8b")

        assert remaining == 0.0

    def test_get_cooldown_remaining_positive_when_rate_limited(self):
        """Cooldown remaining is positive for rate-limited models."""
        tracker = ModelAvailabilityTracker(cooldown_seconds=60)

        tracker.mark_rate_limited("groq/llama-3.1-8b")

        remaining = tracker.get_cooldown_remaining("groq/llama-3.1-8b")

        assert 59 < remaining <= 60

    def test_clear_removes_all_rate_limits(self):
        """clear() removes all rate limit tracking."""
        tracker = ModelAvailabilityTracker()

        tracker.mark_rate_limited("model-a")
        tracker.mark_rate_limited("model-b")
        tracker.clear()

        assert tracker.is_available("model-a") is True
        assert tracker.is_available("model-b") is True



class TestModelSelectionServiceRateLimits:
    """Test ModelSelectionService rate limit integration."""

    def test_select_skips_rate_limited_model(self):
        """Selection skips rate-limited models."""
        service = ModelSelectionService(
            configured_models={"model-a", "model-b", "model-c"},
            model_priorities={
                ModelSelectionType.FAST: ["model-a", "model-b", "model-c"]
            }
        )

        # Rate limit the first priority model
        service.mark_rate_limited("model-a")

        selected = service.select(ModelSelectionType.FAST)

        assert selected == "model-b"

    def test_select_raises_when_all_rate_limited(self):
        """Selection raises when all models are rate limited."""
        service = ModelSelectionService(
            configured_models={"model-a", "model-b"},
            model_priorities={
                ModelSelectionType.FAST: ["model-a", "model-b"]
            }
        )

        service.mark_rate_limited("model-a")
        service.mark_rate_limited("model-b")

        with pytest.raises(AllModelsRateLimitedError) as exc_info:
            service.select(ModelSelectionType.FAST)

        assert "rate limited" in str(exc_info.value).lower()

    def test_session_preferred_skipped_if_rate_limited(self):
        """Session-preferred model is skipped if rate limited."""
        service = ModelSelectionService(
            configured_models={"model-a", "model-b"},
            model_priorities={
                ModelSelectionType.FAST: ["model-a", "model-b"]
            }
        )

        service.mark_rate_limited("model-a")

        # Even with session preference, rate-limited model is skipped
        selected = service.select(
            ModelSelectionType.FAST,
            session_preferred="model-a"
        )

        assert selected == "model-b"

    def test_is_available_checks_both_configured_and_rate_limit(self):
        """is_available checks configuration and rate limit status."""
        service = ModelSelectionService(
            configured_models={"model-a", "model-b"},
            model_priorities={
                ModelSelectionType.FAST: ["model-a", "model-b"]
            }
        )

        # Configured and not rate limited
        assert service.is_available("model-a") is True

        # Configured but rate limited
        service.mark_rate_limited("model-a")
        assert service.is_available("model-a") is False

        # Not configured
        assert service.is_available("model-c") is False



class TestModelSelectionServiceFallbackChain:
    """Test the fallback chain when models are rate limited."""

    def test_fallback_through_priority_list(self):
        """Selection falls back through priority list."""
        service = ModelSelectionService(
            configured_models={"model-1", "model-2", "model-3"},
            model_priorities={
                ModelSelectionType.QUALITY: ["model-1", "model-2", "model-3"]
            }
        )

        # All available - select first
        assert service.select(ModelSelectionType.QUALITY) == "model-1"

        # Rate limit first
        service.mark_rate_limited("model-1")
        assert service.select(ModelSelectionType.QUALITY) == "model-2"

        # Rate limit second
        service.mark_rate_limited("model-2")
        assert service.select(ModelSelectionType.QUALITY) == "model-3"

        # Rate limit third - should raise
        service.mark_rate_limited("model-3")
        with pytest.raises(AllModelsRateLimitedError):
            service.select(ModelSelectionType.QUALITY)

    def test_error_message_includes_cooldown_time(self):
        """AllModelsRateLimitedError includes time to retry."""
        tracker = ModelAvailabilityTracker(cooldown_seconds=60)
        service = ModelSelectionService(
            configured_models={"model-a"},
            model_priorities={
                ModelSelectionType.FAST: ["model-a"]
            },
            availability_tracker=tracker,
        )

        service.mark_rate_limited("model-a")

        with pytest.raises(AllModelsRateLimitedError) as exc_info:
            service.select(ModelSelectionType.FAST)

        # Error message should mention seconds
        assert "seconds" in str(exc_info.value).lower()


class TestModelSelectionServiceEdgeCases:
    """Test edge cases in model selection."""

    def test_no_configured_models_raises_value_error(self):
        """Raises ValueError when no models configured for type."""
        service = ModelSelectionService(
            configured_models=set(),
            model_priorities={
                ModelSelectionType.FAST: ["model-a"]
            }
        )

        with pytest.raises(ValueError) as exc_info:
            service.select(ModelSelectionType.FAST)

        assert "no models configured" in str(exc_info.value).lower()


    def test_mark_rate_limited_on_unconfigured_model(self):
        """Can mark unconfigured model as rate limited without error."""
        service = ModelSelectionService(
            configured_models={"model-a"},
            model_priorities={
                ModelSelectionType.FAST: ["model-a"]
            }
        )

        # Should not raise
        service.mark_rate_limited("nonexistent-model")

        # Should still work normally
        assert service.select(ModelSelectionType.FAST) == "model-a"
