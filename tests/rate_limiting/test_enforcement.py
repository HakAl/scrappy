"""
Tests for rate limit enforcement components.

Tests QuotaScorer, RateLimitEnforcementPolicy, and RateLimitNotifier.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from scrappy.orchestrator.rate_limiting.protocols import (
    EnforcementAction,
)
from scrappy.orchestrator.rate_limiting.scorer import QuotaScorer
from scrappy.orchestrator.rate_limiting.enforcement import RateLimitEnforcementPolicy
from scrappy.orchestrator.rate_limiting.notifier import RateLimitNotifier


# --- Test Doubles ---

@dataclass
class FakeLimits:
    """Fake provider limits for testing."""
    requests_per_day: int = 1000
    requests_per_month: int = 10000
    tokens_per_day: int = 100000
    tokens_per_minute: int = 10000


class FakeUsageQuery:
    """Controllable usage query for testing."""

    def __init__(
        self,
        remaining_percent: float = 1.0,
        provider_quotas: Optional[Dict[str, float]] = None,
    ):
        self._remaining = remaining_percent
        self._quotas = provider_quotas or {}

    def get_remaining_quota(
        self,
        provider: str,
        model: str,
        limits: Any,
    ) -> Dict[str, Any]:
        quota = self._quotas.get(provider, self._remaining)
        requests_limit = getattr(limits, "requests_per_day", 1000)
        tokens_limit = getattr(limits, "tokens_per_day", 100000)

        return {
            "requests_remaining_today": int(requests_limit * quota),
            "tokens_remaining_today": int(tokens_limit * quota),
            "requests_remaining_month": int(requests_limit * 10 * quota),
        }

    def is_rate_limited(self, provider_name: str, registry: Any) -> bool:
        quota = self._quotas.get(provider_name, self._remaining)
        return quota <= 0


class FakeRegistry:
    """Fake provider registry for testing."""

    def __init__(self, providers: Dict[str, Any]):
        self._providers = providers

    def get(self, name: str) -> Optional[Any]:
        return self._providers.get(name)

    def list_available(self) -> List[str]:
        return list(self._providers.keys())


class FakeProvider:
    """Fake provider for testing."""

    def __init__(self, limits: Optional[FakeLimits] = None, default_model: str = "default"):
        self._limits = limits
        self.default_model = default_model

    def get_limits(self) -> Optional[FakeLimits]:
        return self._limits


class FakeOutput:
    """Captures output for test assertions."""

    def __init__(self):
        self.messages: List[tuple] = []

    def print(self, message: str) -> None:
        self.messages.append(("info", message))

    def print_warning(self, message: str) -> None:
        self.messages.append(("warning", message))

    def print_error(self, message: str) -> None:
        self.messages.append(("error", message))


# --- QuotaScorer Tests ---

class TestQuotaScorer:
    """Tests for QuotaScorer."""

    @pytest.mark.unit
    def test_score_fully_available_provider(self):
        """Provider with full quota should score 1.0."""
        usage = FakeUsageQuery(remaining_percent=1.0)
        scorer = QuotaScorer(usage)
        limits = FakeLimits()

        score = scorer.score_provider("test_provider", "default", limits)

        assert score.score == 1.0
        assert score.is_rate_limited is False
        assert score.warning_threshold_hit is False

    @pytest.mark.unit
    def test_score_partially_used_provider(self):
        """Provider with partial quota should score proportionally."""
        usage = FakeUsageQuery(remaining_percent=0.5)
        scorer = QuotaScorer(usage)
        limits = FakeLimits()

        score = scorer.score_provider("test_provider", "default", limits)

        assert score.score == 0.5
        assert score.is_rate_limited is False
        assert score.warning_threshold_hit is False

    @pytest.mark.unit
    def test_score_approaching_limit_triggers_warning(self):
        """Provider below warn threshold should have warning flag."""
        usage = FakeUsageQuery(remaining_percent=0.08)
        scorer = QuotaScorer(usage, warn_threshold=0.1)
        limits = FakeLimits()

        score = scorer.score_provider("test_provider", "default", limits)

        assert score.score == 0.08
        assert score.is_rate_limited is False
        assert score.warning_threshold_hit is True

    @pytest.mark.unit
    def test_score_exhausted_provider(self):
        """Provider with no quota should score 0 and be rate limited."""
        usage = FakeUsageQuery(remaining_percent=0.0)
        scorer = QuotaScorer(usage)
        limits = FakeLimits()

        score = scorer.score_provider("test_provider", "default", limits)

        assert score.score == 0.0
        assert score.is_rate_limited is True
        assert score.warning_threshold_hit is False

    @pytest.mark.unit
    def test_speed_bonus_applied(self):
        """Fast providers should get speed bonus."""
        usage = FakeUsageQuery(remaining_percent=0.9)
        scorer = QuotaScorer(usage, speed_bonus={"cerebras": 0.1})
        limits = FakeLimits()

        score = scorer.score_provider("cerebras", "default", limits)

        assert score.score == 1.0  # 0.9 + 0.1 = 1.0 (capped)

    @pytest.mark.unit
    def test_speed_bonus_capped_at_one(self):
        """Score should not exceed 1.0 even with bonus."""
        usage = FakeUsageQuery(remaining_percent=1.0)
        scorer = QuotaScorer(usage, speed_bonus={"cerebras": 0.5})
        limits = FakeLimits()

        score = scorer.score_provider("cerebras", "default", limits)

        assert score.score == 1.0  # Capped

    @pytest.mark.unit
    def test_rank_providers_sorts_by_score(self):
        """Providers should be ranked by score descending."""
        usage = FakeUsageQuery(provider_quotas={
            "provider_a": 0.3,
            "provider_b": 0.8,
            "provider_c": 0.5,
        })
        scorer = QuotaScorer(usage)

        providers = {
            "provider_a": FakeProvider(FakeLimits()),
            "provider_b": FakeProvider(FakeLimits()),
            "provider_c": FakeProvider(FakeLimits()),
        }
        registry = FakeRegistry(providers)

        ranked = scorer.rank_providers(["provider_a", "provider_b", "provider_c"], registry)

        assert len(ranked) == 3
        assert ranked[0].provider == "provider_b"
        assert ranked[1].provider == "provider_c"
        assert ranked[2].provider == "provider_a"

    @pytest.mark.unit
    def test_rank_providers_handles_no_limits(self):
        """Providers without limits should be fully available."""
        usage = FakeUsageQuery(remaining_percent=0.5)
        scorer = QuotaScorer(usage)

        providers = {
            "limited": FakeProvider(FakeLimits()),
            "unlimited": FakeProvider(None),  # No limits
        }
        registry = FakeRegistry(providers)

        ranked = scorer.rank_providers(["limited", "unlimited"], registry)

        assert len(ranked) == 2
        # Unlimited should rank higher
        assert ranked[0].provider == "unlimited"
        assert ranked[0].score >= 1.0


# --- EnforcementPolicy Tests ---

class TestEnforcementPolicy:
    """Tests for RateLimitEnforcementPolicy."""

    @pytest.mark.unit
    def test_allows_request_when_quota_available(self):
        """ALLOW when provider has sufficient quota."""
        usage = FakeUsageQuery(remaining_percent=0.8)
        scorer = QuotaScorer(usage)
        policy = RateLimitEnforcementPolicy(usage, scorer)

        providers = {"cerebras": FakeProvider(FakeLimits())}
        registry = FakeRegistry(providers)

        decision = policy.evaluate("cerebras", "default", 1000, registry)

        assert decision.action == EnforcementAction.ALLOW
        assert decision.provider == "cerebras"

    @pytest.mark.unit
    def test_warns_when_approaching_limit(self):
        """WARN when below threshold but not exhausted."""
        usage = FakeUsageQuery(remaining_percent=0.08)
        # No speed bonuses to avoid interference
        scorer = QuotaScorer(usage, speed_bonus={})
        policy = RateLimitEnforcementPolicy(usage, scorer, warn_threshold=0.1)

        providers = {"test_provider": FakeProvider(FakeLimits())}
        registry = FakeRegistry(providers)

        decision = policy.evaluate("test_provider", "default", 1000, registry)

        assert decision.action == EnforcementAction.WARN
        assert "approaching" in decision.reason.lower() or "8%" in decision.reason

    @pytest.mark.unit
    def test_blocks_and_suggests_alternative(self):
        """BLOCK with alternative when quota exhausted."""
        usage = FakeUsageQuery(provider_quotas={
            "provider_a": 0.0,  # Exhausted
            "provider_b": 0.5,  # Available
        })
        # No speed bonuses
        scorer = QuotaScorer(usage, speed_bonus={})
        policy = RateLimitEnforcementPolicy(usage, scorer)

        providers = {
            "provider_a": FakeProvider(FakeLimits()),
            "provider_b": FakeProvider(FakeLimits()),
        }
        registry = FakeRegistry(providers)

        decision = policy.evaluate("provider_a", "default", 1000, registry)

        assert decision.action == EnforcementAction.BLOCK
        assert decision.alternative_provider == "provider_b"

    @pytest.mark.unit
    def test_fails_when_all_exhausted(self):
        """FAIL when no providers have quota."""
        usage = FakeUsageQuery(provider_quotas={
            "provider_a": 0.0,
            "provider_b": 0.0,
        })
        # No speed bonuses
        scorer = QuotaScorer(usage, speed_bonus={})
        policy = RateLimitEnforcementPolicy(usage, scorer)

        providers = {
            "provider_a": FakeProvider(FakeLimits()),
            "provider_b": FakeProvider(FakeLimits()),
        }
        registry = FakeRegistry(providers)

        decision = policy.evaluate("provider_a", "default", 1000, registry)

        assert decision.action == EnforcementAction.FAIL
        assert decision.alternative_provider is None

    @pytest.mark.unit
    def test_allows_when_no_limits_configured(self):
        """ALLOW when provider has no rate limits."""
        usage = FakeUsageQuery(remaining_percent=0.0)  # Would be blocked normally
        scorer = QuotaScorer(usage)
        policy = RateLimitEnforcementPolicy(usage, scorer)

        providers = {"cerebras": FakeProvider(None)}  # No limits
        registry = FakeRegistry(providers)

        decision = policy.evaluate("cerebras", "default", 1000, registry)

        assert decision.action == EnforcementAction.ALLOW
        assert "no rate limits" in decision.reason.lower()

    @pytest.mark.unit
    def test_fails_for_unknown_provider(self):
        """FAIL when provider doesn't exist."""
        usage = FakeUsageQuery()
        scorer = QuotaScorer(usage)
        policy = RateLimitEnforcementPolicy(usage, scorer)

        registry = FakeRegistry({})  # Empty registry

        decision = policy.evaluate("nonexistent", "default", 1000, registry)

        assert decision.action == EnforcementAction.FAIL
        assert "not available" in decision.reason.lower()


# --- Notifier Tests ---

class TestRateLimitNotifier:
    """Tests for RateLimitNotifier."""

    @pytest.mark.unit
    def test_notify_approaching_limit(self):
        """Should display warning when limit approaching."""
        output = FakeOutput()
        notifier = RateLimitNotifier(output)

        notifier.notify_approaching_limit("cerebras", 0.08, 80)

        assert len(output.messages) == 1
        assert output.messages[0][0] == "warning"
        assert "cerebras" in output.messages[0][1]
        assert "8%" in output.messages[0][1]

    @pytest.mark.unit
    def test_notify_fallback(self):
        """Should display info when falling back."""
        output = FakeOutput()
        notifier = RateLimitNotifier(output)

        notifier.notify_fallback("cerebras", "groq", "rate limit")

        assert len(output.messages) == 1
        assert output.messages[0][0] == "info"
        assert "cerebras" in output.messages[0][1]
        assert "groq" in output.messages[0][1]

    @pytest.mark.unit
    def test_notify_all_exhausted(self):
        """Should display error when all exhausted."""
        output = FakeOutput()
        notifier = RateLimitNotifier(output)

        notifier.notify_all_exhausted(["cerebras", "groq"])

        assert len(output.messages) == 1
        assert output.messages[0][0] == "error"
        assert "exhausted" in output.messages[0][1].lower()

    @pytest.mark.unit
    def test_quiet_mode_suppresses_warnings(self):
        """Quiet mode should suppress non-critical notifications."""
        output = FakeOutput()
        notifier = RateLimitNotifier(output, quiet_mode=True)

        notifier.notify_approaching_limit("cerebras", 0.08, 80)
        notifier.notify_fallback("cerebras", "groq", "rate limit")

        assert len(output.messages) == 0

    @pytest.mark.unit
    def test_quiet_mode_shows_critical(self):
        """Quiet mode should still show critical errors."""
        output = FakeOutput()
        notifier = RateLimitNotifier(output, quiet_mode=True)

        notifier.notify_all_exhausted(["cerebras", "groq"])

        assert len(output.messages) == 1
        assert output.messages[0][0] == "error"

    @pytest.mark.unit
    def test_cooldown_prevents_spam(self):
        """Same notification should be rate limited."""
        output = FakeOutput()
        notifier = RateLimitNotifier(output, notification_cooldown=60)

        # First notification should show
        notifier.notify_approaching_limit("cerebras", 0.08, 80)
        # Second should be suppressed (within cooldown)
        notifier.notify_approaching_limit("cerebras", 0.07, 70)

        assert len(output.messages) == 1

    @pytest.mark.unit
    def test_different_providers_not_affected_by_cooldown(self):
        """Different providers should have separate cooldowns."""
        output = FakeOutput()
        notifier = RateLimitNotifier(output, notification_cooldown=60)

        notifier.notify_approaching_limit("cerebras", 0.08, 80)
        notifier.notify_approaching_limit("groq", 0.08, 80)

        assert len(output.messages) == 2

    @pytest.mark.unit
    def test_reset_cooldowns(self):
        """Reset should clear all cooldowns."""
        output = FakeOutput()
        notifier = RateLimitNotifier(output, notification_cooldown=60)

        notifier.notify_approaching_limit("cerebras", 0.08, 80)
        notifier.reset_cooldowns()
        notifier.notify_approaching_limit("cerebras", 0.08, 80)

        assert len(output.messages) == 2


class TestNullNotifier:
    """Tests for NullNotifier."""
