"""Tests for model availability tracking and rate limit handling."""

import pytest

from scrappy.orchestrator.model_selection import (
    ModelAvailabilityTracker,
    ModelHealthState,
    ModelSelectionService,
    ModelSelectionType,
    SelectionExhaustedError,
    AllModelsRateLimitedError,
)
from scrappy.infrastructure.exceptions.failure_kinds import FailureKind
from scrappy.orchestrator.failure_policy import (
    FAILURE_POLICIES,
    SHOULD_RETRY_KINDS,
    FailureRecord,
    HealthScope,
)


class FakeClock:
    """Controllable clock for availability tests."""

    def __init__(self, now: float = 100.0):
        self.value = now

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def mark_tracker_rate_limit(
    tracker: ModelAvailabilityTracker,
    model: str,
    retry_after: float = 60.0,
) -> None:
    """Mark a tracker entry with the canonical health-state API."""
    tracker.mark(
        model,
        ModelHealthState(
            expires_at=tracker.now() + retry_after,
            failure_kind=FailureKind.RATE_LIMIT,
            retry_after=retry_after,
        ),
    )


class TestFailurePolicy:
    """Test failure policy table invariants."""

    def test_policy_table_covers_every_failure_kind(self):
        """Every failure kind has an explicit policy."""
        assert set(FAILURE_POLICIES) == set(FailureKind)

    def test_should_retry_kinds_match_policy_table(self):
        """Retryable kinds are derived from the policy table."""
        expected = {
            kind for kind, policy in FAILURE_POLICIES.items() if policy.should_retry
        }

        assert SHOULD_RETRY_KINDS == expected

    def test_retryable_policies_have_health_scope(self):
        """Retryable failures must mark a model or provider unhealthy."""
        for policy in FAILURE_POLICIES.values():
            if policy.should_retry:
                assert policy.scope != HealthScope.NONE


class TestModelAvailabilityTracker:
    """Test rate limit tracking with cooldown."""

    def test_all_models_rate_limited_aliases_selection_exhausted(self):
        """Old exhaustion name remains compatible with new selection name."""
        assert AllModelsRateLimitedError is SelectionExhaustedError

    def test_model_available_by_default(self):
        """Models are available when not rate limited."""
        tracker = ModelAvailabilityTracker()

        assert tracker.is_available("groq/llama-3.1-8b") is True

    def test_model_unavailable_after_rate_limit(self):
        """Model becomes unavailable after rate limit."""
        tracker = ModelAvailabilityTracker()

        mark_tracker_rate_limit(tracker, "groq/llama-3.1-8b")

        assert tracker.is_available("groq/llama-3.1-8b") is False

    def test_get_available_filters_rate_limited(self):
        """get_available removes rate-limited models from list."""
        tracker = ModelAvailabilityTracker()

        models = [
            "groq/llama-3.1-8b",
            "cerebras/llama3.1-8b",
            "gemini/gemini-2.5-flash",
        ]

        mark_tracker_rate_limit(tracker, "cerebras/llama3.1-8b")

        available = tracker.get_available(models)

        assert available == ["groq/llama-3.1-8b", "gemini/gemini-2.5-flash"]

    def test_get_available_preserves_order(self):
        """get_available preserves priority order of input list."""
        tracker = ModelAvailabilityTracker()

        models = ["model-a", "model-b", "model-c"]

        mark_tracker_rate_limit(tracker, "model-b")

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

        mark_tracker_rate_limit(tracker, "groq/llama-3.1-8b")

        remaining = tracker.get_cooldown_remaining("groq/llama-3.1-8b")

        assert 59 < remaining <= 60

    def test_clear_removes_all_rate_limits(self):
        """clear() removes all rate limit tracking."""
        tracker = ModelAvailabilityTracker()

        mark_tracker_rate_limit(tracker, "model-a")
        mark_tracker_rate_limit(tracker, "model-b")
        tracker.clear()

        assert tracker.is_available("model-a") is True
        assert tracker.is_available("model-b") is True

    def test_later_expiration_wins_under_duplicate_marks(self):
        """A shorter new state does not replace a longer active state."""
        clock = FakeClock()
        tracker = ModelAvailabilityTracker(now=clock)

        tracker.mark(
            "model-a",
            ModelHealthState(
                expires_at=200.0,
                failure_kind=FailureKind.RATE_LIMIT,
            ),
        )
        tracker.mark(
            "model-a",
            ModelHealthState(
                expires_at=150.0,
                failure_kind=FailureKind.AUTH,
            ),
        )

        state = tracker.get_unavailable_state("model-a")
        assert state is not None
        assert state.failure_kind == FailureKind.RATE_LIMIT

    def test_equal_expiration_uses_newest_state(self):
        """Equal expirations prefer the most recent failure kind."""
        clock = FakeClock()
        tracker = ModelAvailabilityTracker(now=clock)

        tracker.mark(
            "model-a",
            ModelHealthState(
                expires_at=200.0,
                failure_kind=FailureKind.RATE_LIMIT,
            ),
        )
        tracker.mark(
            "model-a",
            ModelHealthState(
                expires_at=200.0,
                failure_kind=FailureKind.AUTH,
            ),
        )

        state = tracker.get_unavailable_state("model-a")
        assert state is not None
        assert state.failure_kind == FailureKind.AUTH

    def test_injected_clock_controls_expiration(self):
        """Injected clock determines when health state expires."""
        clock = FakeClock()
        tracker = ModelAvailabilityTracker(cooldown_seconds=60, now=clock)

        mark_tracker_rate_limit(tracker, "model-a")

        assert tracker.is_available("model-a") is False

        clock.advance(60.0)

        assert tracker.is_available("model-a") is True

    def test_clear_kinds_removes_only_matching_failures(self):
        """Targeted clearing leaves unrelated health states intact."""
        clock = FakeClock()
        tracker = ModelAvailabilityTracker(now=clock)
        tracker.mark(
            "auth-model",
            ModelHealthState(
                expires_at=200.0,
                failure_kind=FailureKind.AUTH,
            ),
        )
        tracker.mark(
            "rate-model",
            ModelHealthState(
                expires_at=200.0,
                failure_kind=FailureKind.RATE_LIMIT,
            ),
        )

        tracker.clear_kinds({FailureKind.AUTH})

        assert tracker.is_available("auth-model") is True
        assert tracker.is_available("rate-model") is False

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
        service.mark_unhealthy("model-a", FailureKind.RATE_LIMIT)

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

        service.mark_unhealthy("model-a", FailureKind.RATE_LIMIT)
        service.mark_unhealthy("model-b", FailureKind.RATE_LIMIT)

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

        service.mark_unhealthy("model-a", FailureKind.RATE_LIMIT)

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
        service.mark_unhealthy("model-a", FailureKind.RATE_LIMIT)
        assert service.is_available("model-a") is False

        # Not configured
        assert service.is_available("model-c") is False

    def test_auth_marks_provider_scope_across_selection_types(self):
        """AUTH failures exclude all configured models for that provider."""
        service = ModelSelectionService(
            configured_models={
                "cerebras/fast-model",
                "cerebras/chat-model",
                "groq/fast-model",
                "groq/chat-model",
            },
            model_priorities={
                ModelSelectionType.FAST: ["cerebras/fast-model", "groq/fast-model"],
                ModelSelectionType.CHAT: ["cerebras/chat-model", "groq/chat-model"],
            },
        )

        service.mark_unhealthy("cerebras/fast-model", FailureKind.AUTH)

        assert service.select(ModelSelectionType.FAST) == "groq/fast-model"
        assert service.select(ModelSelectionType.CHAT) == "groq/chat-model"

    def test_ambiguous_provider_scope_degrades_to_per_model(self, caplog):
        """Provider-scope failures without a known prefix mark only the failed model."""
        service = ModelSelectionService(
            configured_models={"cerebras/model-a", "cerebras/model-b"},
            model_priorities={
                ModelSelectionType.FAST: ["cerebras/model-a", "cerebras/model-b"]
            },
        )

        with caplog.at_level("WARNING"):
            service.mark_unhealthy("ambiguous-model", FailureKind.AUTH)

        assert service.select(ModelSelectionType.FAST) == "cerebras/model-a"
        assert "ambiguous-model" in caplog.text

    def test_retry_after_overrides_static_cooldown(self):
        """Retry-After controls cooldown duration when present."""
        clock = FakeClock()
        tracker = ModelAvailabilityTracker(now=clock)
        service = ModelSelectionService(
            configured_models={"model-a"},
            model_priorities={ModelSelectionType.FAST: ["model-a"]},
            availability_tracker=tracker,
        )

        service.mark_unhealthy(
            "model-a",
            FailureKind.RATE_LIMIT,
            retry_after=10.0,
        )

        assert tracker.get_cooldown_remaining("model-a") == 10.0

    def test_select_exclude_prevents_reselection(self):
        """Request-local exclude skips otherwise available models."""
        service = ModelSelectionService(
            configured_models={"model-a", "model-b"},
            model_priorities={
                ModelSelectionType.FAST: ["model-a", "model-b"]
            },
        )

        selected = service.select(ModelSelectionType.FAST, exclude={"model-a"})

        assert selected == "model-b"

    def test_select_applies_min_context_and_exclude_together(self):
        """Context and request-local exclude filters apply in one selection."""
        service = ModelSelectionService(
            configured_models={
                "cerebras/llama-3.3-70b",
                "groq/llama-3.3-70b-versatile",
                "groq/llama-3.1-8b-instant",
            },
            model_priorities={
                ModelSelectionType.CHAT: [
                    "cerebras/llama-3.3-70b",
                    "groq/llama-3.3-70b-versatile",
                    "groq/llama-3.1-8b-instant",
                ]
            },
        )

        selected = service.select(
            ModelSelectionType.CHAT,
            min_context=32768,
            exclude={"groq/llama-3.3-70b-versatile"},
        )

        assert selected == "groq/llama-3.1-8b-instant"

    def test_selection_exhausted_has_failure_summary(self):
        """Selection exhaustion exposes tracker-derived failure records."""
        service = ModelSelectionService(
            configured_models={"model-a"},
            model_priorities={ModelSelectionType.FAST: ["model-a"]},
        )
        service.mark_unhealthy("model-a", FailureKind.RATE_LIMIT)

        with pytest.raises(SelectionExhaustedError) as exc_info:
            service.select(ModelSelectionType.FAST)

        assert exc_info.value.failure_summary["model-a"].kind == FailureKind.RATE_LIMIT
        assert "model-a" in exc_info.value.suggestion
        assert "rate_limit" in exc_info.value.suggestion
        assert "Wait" in exc_info.value.suggestion

    def test_selection_exhausted_suggestion_mentions_auth_setup(self):
        """AUTH and payment failures point users toward setup/config fixes."""
        error = SelectionExhaustedError(
            "No models available",
            failure_summary={
                "cerebras/model-a": FailureRecord(
                    kind=FailureKind.AUTH,
                    provider="cerebras",
                    retry_after=None,
                    message="bad key",
                ),
                "groq/model-b": FailureRecord(
                    kind=FailureKind.PAYMENT_REQUIRED,
                    provider="groq",
                    retry_after=None,
                    message="billing",
                ),
            },
        )

        assert "cerebras/model-a" in error.suggestion
        assert "groq/model-b" in error.suggestion
        assert "api keys" in error.suggestion.lower()
        assert "billing" in error.suggestion.lower()
        assert "Wait" not in error.suggestion

    def test_update_configured_preserves_health_state(self):
        """Configuration refresh does not reset active cooldowns."""
        service = ModelSelectionService(
            configured_models={"model-a", "model-b"},
            model_priorities={
                ModelSelectionType.FAST: ["model-a", "model-b", "model-c"]
            },
        )
        service.mark_unhealthy("model-a", FailureKind.RATE_LIMIT)

        service.update_configured({"model-a", "model-c"})

        assert service.is_available("model-a") is False
        assert service.select(ModelSelectionType.FAST) == "model-c"

class TestModelSelectionServiceFallbackChain:
    """Test the fallback chain when models are rate limited."""

    def test_fallback_through_priority_list(self):
        """Selection falls back through priority list."""
        service = ModelSelectionService(
            configured_models={"model-1", "model-2", "model-3"},
            model_priorities={
                ModelSelectionType.CHAT: ["model-1", "model-2", "model-3"]
            }
        )

        # All available - select first
        assert service.select(ModelSelectionType.CHAT) == "model-1"

        # Rate limit first
        service.mark_unhealthy("model-1", FailureKind.RATE_LIMIT)
        assert service.select(ModelSelectionType.CHAT) == "model-2"

        # Rate limit second
        service.mark_unhealthy("model-2", FailureKind.RATE_LIMIT)
        assert service.select(ModelSelectionType.CHAT) == "model-3"

        # Rate limit third - should raise
        service.mark_unhealthy("model-3", FailureKind.RATE_LIMIT)
        with pytest.raises(AllModelsRateLimitedError):
            service.select(ModelSelectionType.CHAT)

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

        service.mark_unhealthy("model-a", FailureKind.RATE_LIMIT)

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

    def test_mark_unhealthy_on_unconfigured_model(self):
        """Can mark an unconfigured model unhealthy without error."""
        service = ModelSelectionService(
            configured_models={"model-a"},
            model_priorities={
                ModelSelectionType.FAST: ["model-a"]
            }
        )

        # Should not raise
        service.mark_unhealthy("nonexistent-model", FailureKind.RATE_LIMIT)

        # Should still work normally
        assert service.select(ModelSelectionType.FAST) == "model-a"
