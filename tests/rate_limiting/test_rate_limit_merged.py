"""
Tests for merged rate limit logic in RateLimitTracker.

These tests verify that rate limit methods from core.py work correctly
when moved to RateLimitTracker.
"""

import pytest
from unittest.mock import Mock, MagicMock
from typing import Optional

from src.orchestrator.rate_limiter import RateLimitTracker
from src.orchestrator.rate_limiting import RateLimitCalculator, RateLimitPolicy, RateLimitRecommender
from src.providers.base import ProviderLimits
from tests.helpers import create_test_rate_limit_tracker, FakeStorage


def make_mock_provider(
    name: str,
    default_model: str = "default-model",
    limits: Optional[ProviderLimits] = None
) -> Mock:
    """Create a mock provider with configurable limits."""
    provider = Mock()
    provider.name = name
    provider.default_model = default_model
    provider.get_limits.return_value = limits or ProviderLimits()
    return provider


def make_mock_registry(providers: dict) -> Mock:
    """
    Create a mock registry with providers.

    Args:
        providers: Dict of provider_name -> Mock provider
    """
    registry = Mock()
    registry.list_available.return_value = list(providers.keys())
    registry.get.side_effect = lambda name: providers.get(name)
    return registry


def create_real_tracker():
    """
    Create a tracker with REAL calculator and policy for testing actual rate limiting logic.

    Uses FakeStorage (in-memory) since that's just for persistence, but uses
    real Calculator and Policy to test the actual rate limiting behavior.
    """
    storage = FakeStorage()
    policy = RateLimitPolicy()
    calculator = RateLimitCalculator()

    # Create tracker with placeholder recommender
    tracker = RateLimitTracker(
        storage=storage,
        policy=policy,
        calculator=calculator,
        recommender=MagicMock()
    )

    # Create real recommender with the tracker as usage query
    # and replace the mock recommender
    recommender = RateLimitRecommender(tracker)
    tracker._recommender = recommender

    return tracker


class TestIsRateLimited:
    """Tests for is_rate_limited method on RateLimitTracker."""

    @pytest.mark.unit
    def test_not_rate_limited_when_under_quota(self):
        """Provider should not be rate limited when under quota."""
        tracker = create_test_rate_limit_tracker()

        # Use 5 of 100 daily requests
        for _ in range(5):
            tracker.record_request('groq', 'model', 100, 50)

        provider = make_mock_provider(
            'groq',
            default_model='model',
            limits=ProviderLimits(requests_per_day=100)
        )
        registry = make_mock_registry({'groq': provider})

        result = tracker.is_rate_limited('groq', registry)

        assert result is False

    @pytest.mark.unit
    def test_rate_limited_when_daily_quota_exhausted(self):
        """Provider should be rate limited when daily requests exhausted."""
        tracker = create_real_tracker()

        # Use all 10 daily requests
        for _ in range(10):
            tracker.record_request('groq', 'model', 100, 50)

        provider = make_mock_provider(
            'groq',
            default_model='model',
            limits=ProviderLimits(requests_per_day=10)
        )
        registry = make_mock_registry({'groq': provider})

        result = tracker.is_rate_limited('groq', registry)

        assert result is True

    @pytest.mark.unit
    def test_rate_limited_when_monthly_quota_exhausted(self):
        """Provider should be rate limited when monthly requests exhausted."""
        tracker = create_real_tracker()

        # Directly set monthly usage
        tracker._ensure_provider_model('groq', 'model')
        tracker._usage['providers']['groq']['model']['requests_this_month'] = 1000

        provider = make_mock_provider(
            'groq',
            default_model='model',
            limits=ProviderLimits(requests_per_month=1000)
        )
        registry = make_mock_registry({'groq': provider})

        result = tracker.is_rate_limited('groq', registry)

        assert result is True

    @pytest.mark.unit
    def test_not_rate_limited_when_no_limits_set(self):
        """Provider should not be rate limited when no limits are configured."""
        tracker = create_test_rate_limit_tracker()

        # Record many requests
        for _ in range(100):
            tracker.record_request('groq', 'model', 100, 50)

        provider = make_mock_provider(
            'groq',
            default_model='model',
            limits=ProviderLimits()  # No limits
        )
        registry = make_mock_registry({'groq': provider})

        result = tracker.is_rate_limited('groq', registry)

        assert result is False

    @pytest.mark.unit
    def test_not_rate_limited_for_unknown_provider(self):
        """Unknown provider should not be considered rate limited."""
        tracker = create_test_rate_limit_tracker()
        registry = make_mock_registry({})  # Empty registry

        result = tracker.is_rate_limited('unknown', registry)

        assert result is False

    @pytest.mark.unit
    def test_not_rate_limited_when_provider_has_no_limits(self):
        """Provider with None limits should not be rate limited."""
        tracker = create_test_rate_limit_tracker()

        provider = make_mock_provider('groq', default_model='model')
        provider.get_limits.return_value = None
        registry = make_mock_registry({'groq': provider})

        result = tracker.is_rate_limited('groq', registry)

        assert result is False

    @pytest.mark.unit
    def test_uses_provider_default_model(self):
        """Should check quota using provider's default model."""
        tracker = create_real_tracker()

        # Record requests for custom-model
        for _ in range(10):
            tracker.record_request('groq', 'custom-model', 100, 50)

        # Provider's default model is different
        provider = make_mock_provider(
            'groq',
            default_model='custom-model',  # This model is at limit
            limits=ProviderLimits(requests_per_day=10)
        )
        registry = make_mock_registry({'groq': provider})

        result = tracker.is_rate_limited('groq', registry)

        assert result is True


class TestGetRecommendedProvider:
    """Tests for get_recommended_provider method on RateLimitTracker."""

    @pytest.mark.unit
    def test_returns_first_available_provider_for_general_task(self):
        """Should return first non-rate-limited provider for general tasks."""
        tracker = create_real_tracker()

        providers = {
            'cerebras': make_mock_provider(
                'cerebras',
                limits=ProviderLimits(requests_per_day=100)
            ),
            'groq': make_mock_provider(
                'groq',
                limits=ProviderLimits(requests_per_day=100)
            ),
        }
        registry = make_mock_registry(providers)

        result = tracker.get_recommended_provider('general', registry)

        assert result == 'cerebras'  # First in preference list

    @pytest.mark.unit
    def test_skips_rate_limited_provider(self):
        """Should skip providers that are rate limited."""
        tracker = create_real_tracker()

        # Rate limit cerebras
        for _ in range(10):
            tracker.record_request('cerebras', 'default-model', 100, 50)

        providers = {
            'cerebras': make_mock_provider(
                'cerebras',
                limits=ProviderLimits(requests_per_day=10)  # At limit
            ),
            'groq': make_mock_provider(
                'groq',
                limits=ProviderLimits(requests_per_day=100)
            ),
        }
        registry = make_mock_registry(providers)

        result = tracker.get_recommended_provider('general', registry)

        assert result == 'groq'

    @pytest.mark.unit
    def test_returns_none_when_no_providers_available(self):
        """Should return None when no providers are available."""
        tracker = create_real_tracker()
        registry = make_mock_registry({})

        result = tracker.get_recommended_provider('general', registry)

        assert result is None

    @pytest.mark.unit
    def test_respects_task_type_preferences(self):
        """Should prefer different providers based on task type."""
        tracker = create_real_tracker()

        providers = {
            'cerebras': make_mock_provider(
                'cerebras',
                limits=ProviderLimits(requests_per_day=100)
            ),
            'groq': make_mock_provider(
                'groq',
                limits=ProviderLimits(requests_per_day=100)
            ),
            'gemini': make_mock_provider(
                'gemini',
                limits=ProviderLimits(requests_per_day=100)
            ),
        }
        registry = make_mock_registry(providers)

        # Planning should prefer cerebras
        result = tracker.get_recommended_provider('planning', registry)
        assert result == 'cerebras'

        # Quick should prefer cerebras (fast)
        result = tracker.get_recommended_provider('quick', registry)
        assert result == 'cerebras'

    @pytest.mark.unit
    def test_fallback_when_preferred_not_available(self):
        """Should fallback to next provider when preferred is not available."""
        tracker = create_real_tracker()

        # Only groq available, not cerebras
        providers = {
            'groq': make_mock_provider(
                'groq',
                limits=ProviderLimits(requests_per_day=100)
            ),
        }
        registry = make_mock_registry(providers)

        result = tracker.get_recommended_provider('planning', registry)

        assert result == 'groq'


class TestGetRateLimitStatusExtended:
    """Tests for extended get_rate_limit_status with provider info."""

    @pytest.mark.unit
    def test_includes_limits_for_each_provider(self):
        """Should include limit information for each provider."""
        tracker = create_real_tracker()
        tracker.record_request('groq', 'model', 100, 50)

        providers = {
            'groq': make_mock_provider(
                'groq',
                default_model='model',
                limits=ProviderLimits(
                    requests_per_day=100,
                    requests_per_month=1000,
                    tokens_per_day=50000
                )
            ),
        }
        registry = make_mock_registry(providers)

        status = tracker.get_rate_limit_status_extended(registry)

        assert 'groq' in status['providers']
        groq_status = status['providers']['groq']
        assert groq_status['limits']['requests_per_day'] == 100
        assert groq_status['limits']['requests_per_month'] == 1000
        assert groq_status['limits']['tokens_per_day'] == 50000

    @pytest.mark.unit
    def test_includes_remaining_quota(self):
        """Should include remaining quota for each provider."""
        tracker = create_real_tracker()

        # Use 5 requests
        for _ in range(5):
            tracker.record_request('groq', 'model', 100, 50)

        providers = {
            'groq': make_mock_provider(
                'groq',
                default_model='model',
                limits=ProviderLimits(requests_per_day=100)
            ),
        }
        registry = make_mock_registry(providers)

        status = tracker.get_rate_limit_status_extended(registry)

        groq_status = status['providers']['groq']
        assert groq_status['remaining']['requests_remaining_today'] == 95

    @pytest.mark.unit
    def test_handles_provider_lookup_errors_gracefully(self):
        """Should handle errors when looking up provider info."""
        tracker = create_real_tracker()
        tracker.record_request('groq', 'model', 100, 50)

        # Provider that raises an error
        provider = make_mock_provider('groq')
        provider.get_limits.side_effect = Exception("API error")

        registry = make_mock_registry({'groq': provider})

        # Should not raise, but status might be incomplete
        status = tracker.get_rate_limit_status_extended(registry)

        # Should still return status dict
        assert 'providers' in status
        assert 'groq' in status['providers']

    @pytest.mark.unit
    def test_includes_all_available_providers(self):
        """Should include status for all providers with usage."""
        tracker = create_real_tracker()
        tracker.record_request('groq', 'model', 100, 50)
        tracker.record_request('cerebras', 'llama', 200, 100)

        providers = {
            'groq': make_mock_provider(
                'groq',
                default_model='model',
                limits=ProviderLimits(requests_per_day=100)
            ),
            'cerebras': make_mock_provider(
                'cerebras',
                default_model='llama',
                limits=ProviderLimits(requests_per_day=200)
            ),
        }
        registry = make_mock_registry(providers)

        status = tracker.get_rate_limit_status_extended(registry)

        assert 'groq' in status['providers']
        assert 'cerebras' in status['providers']


class TestCheckAllWarnings:
    """Tests for check_all_warnings method on RateLimitTracker."""

    @pytest.mark.unit
    def test_returns_empty_list_when_no_warnings(self):
        """Should return empty list when no providers approaching limits."""
        tracker = create_real_tracker()
        tracker.record_request('groq', 'model', 100, 50)

        providers = {
            'groq': make_mock_provider(
                'groq',
                default_model='model',
                limits=ProviderLimits(requests_per_day=100)
            ),
        }
        registry = make_mock_registry(providers)

        warnings = tracker.check_all_warnings(registry)

        assert warnings == []

    @pytest.mark.unit
    def test_returns_warnings_for_approaching_limits(self):
        """Should return warnings when providers approach limits."""
        tracker = create_real_tracker()

        # Use 95 of 100 requests
        for _ in range(95):
            tracker.record_request('groq', 'model', 10, 5)

        providers = {
            'groq': make_mock_provider(
                'groq',
                default_model='model',
                limits=ProviderLimits(requests_per_day=100)
            ),
        }
        registry = make_mock_registry(providers)

        warnings = tracker.check_all_warnings(registry)

        assert len(warnings) >= 1
        assert any('groq' in w for w in warnings)

    @pytest.mark.unit
    def test_checks_all_models_for_provider(self):
        """Should check warnings for all models of each provider."""
        tracker = create_real_tracker()

        # Use different models
        for _ in range(95):
            tracker.record_request('groq', 'model-a', 10, 5)
        for _ in range(5):
            tracker.record_request('groq', 'model-b', 10, 5)

        providers = {
            'groq': make_mock_provider(
                'groq',
                default_model='model-a',
                limits=ProviderLimits(requests_per_day=100)
            ),
        }
        registry = make_mock_registry(providers)

        warnings = tracker.check_all_warnings(registry)

        # Should have warning for model-a
        assert any('model-a' in w or 'groq' in w for w in warnings)

    @pytest.mark.unit
    def test_checks_multiple_providers(self):
        """Should check warnings across all providers."""
        tracker = create_real_tracker()

        # Approach limits on multiple providers
        for _ in range(95):
            tracker.record_request('groq', 'model', 10, 5)
        for _ in range(90):
            tracker.record_request('cerebras', 'llama', 10, 5)

        providers = {
            'groq': make_mock_provider(
                'groq',
                default_model='model',
                limits=ProviderLimits(requests_per_day=100)
            ),
            'cerebras': make_mock_provider(
                'cerebras',
                default_model='llama',
                limits=ProviderLimits(requests_per_day=100)
            ),
        }
        registry = make_mock_registry(providers)

        warnings = tracker.check_all_warnings(registry)

        # Should have warnings for both
        assert len(warnings) >= 2


