"""
Integration tests for rate limit enforcement in DelegationManager.

CRITICAL: These tests use mocks/fakes ONLY. No real API calls.

Tests verify that enforcement components are properly wired and that
DelegationManager respects enforcement decisions (ALLOW, WARN, BLOCK, FAIL).
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import Mock

import pytest

from scrappy.orchestrator.delegation import DelegationManager
from scrappy.orchestrator.rate_limiting.scorer import QuotaScorer
from scrappy.orchestrator.rate_limiting.enforcement import RateLimitEnforcementPolicy
from scrappy.orchestrator.rate_limiting.notifier import RateLimitNotifier, NullNotifier
from scrappy.orchestrator.rate_limiting.protocols import EnforcementAction
from scrappy.orchestrator.provider_types import LLMResponse
from scrappy.infrastructure.exceptions.provider_errors import AllProvidersRateLimitedError


# =============================================================================
# Test Doubles (NO REAL API CALLS)
# =============================================================================

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
        self._limits = limits or FakeLimits()
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


class FakeNotifier:
    """Captures notifications for test assertions."""

    def __init__(self):
        self.notifications: List[tuple] = []

    def notify_approaching_limit(
        self, provider: str, remaining_percent: float, remaining_requests: int
    ) -> None:
        self.notifications.append(("approaching", provider, remaining_percent, remaining_requests))

    def notify_fallback(self, from_provider: str, to_provider: str, reason: str) -> None:
        self.notifications.append(("fallback", from_provider, to_provider, reason))

    def notify_all_exhausted(self, attempted_providers: List[str]) -> None:
        self.notifications.append(("exhausted", attempted_providers))


class FakeLLMService:
    """Fake LLM service that returns canned responses. NO API CALLS."""

    def __init__(self, response: Optional[LLMResponse] = None):
        self.response = response or LLMResponse(
            content="test response",
            model="fake-model",
            provider="fake",
            tokens_used=100,
            latency_ms=50.0,
        )
        self.calls: List[tuple] = []

    def completion_sync(self, model: str, messages: list, **kwargs) -> tuple:
        self.calls.append(("sync", model, messages, kwargs))
        return self.response, {"provider": "fake", "model": model, "tokens_used": 100}

    async def completion(self, model: str, messages: list, **kwargs) -> tuple:
        self.calls.append(("async", model, messages, kwargs))
        return self.response, {"provider": "fake", "model": model, "tokens_used": 100}


class FakeCache:
    """Fake cache that always misses."""

    def get(self, *args, **kwargs) -> None:
        return None

    def get_by_intent(self, *args, **kwargs) -> None:
        return None

    def put(self, *args, **kwargs) -> None:
        pass

    def put_by_intent(self, *args, **kwargs) -> None:
        pass


class FakePromptAugmenter:
    """Fake augmenter that returns prompt unchanged."""

    def augment(self, prompt: str, use_context: bool = False) -> str:
        return prompt


class FakeBatchScheduler:
    """Fake batch scheduler."""
    pass


# =============================================================================
# Integration Tests
# =============================================================================

class TestEnforcementIntegration:
    """Tests for enforcement wiring in DelegationManager."""

    def _create_manager(
        self,
        provider_quotas: Dict[str, float],
        provider_names: Optional[List[str]] = None,
    ) -> tuple[DelegationManager, FakeLLMService, FakeNotifier, FakeRegistry]:
        """Helper to create DelegationManager with enforcement wired."""
        if provider_names is None:
            provider_names = list(provider_quotas.keys())

        # Create usage query with controlled quotas
        usage = FakeUsageQuery(provider_quotas=provider_quotas)

        # Create scorer and enforcement (no speed bonuses to avoid interference)
        scorer = QuotaScorer(usage, speed_bonus={})
        enforcement = RateLimitEnforcementPolicy(usage, scorer)

        # Create notifier that captures calls
        notifier = FakeNotifier()

        # Create registry with fake providers
        providers = {name: FakeProvider() for name in provider_names}
        registry = FakeRegistry(providers)

        # Create fake LLM service (NO API CALLS)
        llm_service = FakeLLMService()

        # Create manager with enforcement wired
        manager = DelegationManager(
            llm_service=llm_service,
            cache=FakeCache(),
            output=FakeOutput(),
            prompt_augmenter=FakePromptAugmenter(),
            batch_scheduler=FakeBatchScheduler(),
            context_aware=False,
            enforcement=enforcement,
            notifier=notifier,
            registry=registry,
        )

        return manager, llm_service, notifier, registry

    @pytest.mark.unit
    def test_allows_request_when_quota_available(self):
        """Request should proceed when provider has quota."""
        manager, llm_service, notifier, _ = self._create_manager(
            provider_quotas={"test_provider": 0.8}  # 80% remaining
        )

        response, record = manager.delegate(
            provider_name="test_provider",
            prompt="test prompt",
        )

        # Should have made the call
        assert len(llm_service.calls) == 1
        assert response.content == "test response"
        # No notifications
        assert len(notifier.notifications) == 0

    @pytest.mark.unit
    def test_warns_when_approaching_limit(self):
        """Should warn but proceed when below warn threshold."""
        manager, llm_service, notifier, _ = self._create_manager(
            provider_quotas={"test_provider": 0.08}  # 8% remaining (below 10% threshold)
        )

        response, record = manager.delegate(
            provider_name="test_provider",
            prompt="test prompt",
        )

        # Should have made the call
        assert len(llm_service.calls) == 1
        assert response.content == "test response"
        # Should have warned
        assert len(notifier.notifications) == 1
        assert notifier.notifications[0][0] == "approaching"
        assert notifier.notifications[0][1] == "test_provider"

    @pytest.mark.unit
    def test_blocks_exhausted_provider_uses_alternative(self):
        """Exhausted provider should be blocked, alternative used."""
        manager, llm_service, notifier, _ = self._create_manager(
            provider_quotas={
                "exhausted_provider": 0.0,  # Exhausted
                "available_provider": 0.5,  # Available
            }
        )

        response, record = manager.delegate(
            provider_name="exhausted_provider",
            prompt="test prompt",
        )

        # Should have made the call (to alternative)
        assert len(llm_service.calls) == 1
        assert response.content == "test response"
        # Should have notified about fallback
        assert len(notifier.notifications) == 1
        assert notifier.notifications[0][0] == "fallback"
        assert notifier.notifications[0][1] == "exhausted_provider"
        assert notifier.notifications[0][2] == "available_provider"

    @pytest.mark.unit
    def test_fails_when_all_providers_exhausted(self):
        """Should raise error when all providers exhausted."""
        manager, llm_service, notifier, _ = self._create_manager(
            provider_quotas={
                "provider_a": 0.0,
                "provider_b": 0.0,
            }
        )

        with pytest.raises(AllProvidersRateLimitedError):
            manager.delegate(
                provider_name="provider_a",
                prompt="test prompt",
            )

        # Should NOT have made any API calls
        assert len(llm_service.calls) == 0
        # Should have notified about exhaustion
        assert len(notifier.notifications) == 1
        assert notifier.notifications[0][0] == "exhausted"

    @pytest.mark.unit
    def test_skips_enforcement_when_not_configured(self):
        """Should proceed without enforcement when enforcement=None."""
        llm_service = FakeLLMService()

        # Create manager WITHOUT enforcement (backwards compat)
        manager = DelegationManager(
            llm_service=llm_service,
            cache=FakeCache(),
            output=FakeOutput(),
            prompt_augmenter=FakePromptAugmenter(),
            batch_scheduler=FakeBatchScheduler(),
            context_aware=False,
            enforcement=None,  # Not configured
            notifier=None,
            registry=None,
        )

        response, record = manager.delegate(
            provider_name="any_provider",
            prompt="test prompt",
        )

        # Should have made the call regardless
        assert len(llm_service.calls) == 1
        assert response.content == "test response"

    @pytest.mark.unit
    def test_skips_enforcement_for_model_groups(self):
        """Should skip enforcement for 'fast' and 'quality' model groups."""
        # Create with exhausted provider
        manager, llm_service, notifier, _ = self._create_manager(
            provider_quotas={"some_provider": 0.0}
        )

        # Request with model group (not specific provider)
        response, record = manager.delegate(
            provider_name="fast",  # Model group, not provider
            prompt="test prompt",
        )

        # Should have made the call (enforcement skipped for groups)
        assert len(llm_service.calls) == 1
        assert response.content == "test response"
        # No notifications (enforcement was skipped)
        assert len(notifier.notifications) == 0

    @pytest.mark.unit
    def test_skips_enforcement_for_chat_group(self):
        """Should skip enforcement for 'chat' model group."""
        manager, llm_service, notifier, _ = self._create_manager(
            provider_quotas={"some_provider": 0.0}
        )

        response, record = manager.delegate(
            provider_name="chat",  # Model group (not a provider with rate limits)
            prompt="test prompt",
        )

        # Should have made the call
        assert len(llm_service.calls) == 1
        # No notifications
        assert len(notifier.notifications) == 0
