"""Tests for RateLimitTracker header update functionality.

CRITICAL: NO REAL API CALLS. All tests use mocks/fakes.
"""
from datetime import datetime
from typing import Any, Dict
from unittest.mock import Mock

import pytest

from scrappy.orchestrator.rate_limiting.tracker import RateLimitTracker


class FakeStorage:
    """Fake storage that captures save calls."""

    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.save_calls: list[Dict[str, Any]] = []

    def load(self) -> Dict[str, Any]:
        return self.data

    async def load_async(self) -> Dict[str, Any]:
        return self.data

    def save(self, data: Dict[str, Any]) -> None:
        self.data = data
        self.save_calls.append(data.copy())

    async def save_async(self, data: Dict[str, Any]) -> None:
        self.save(data)


class FakePolicy:
    """Fake policy that never needs reset."""

    def reset_needed(self, last_reset: Dict[str, Any]) -> Dict[str, bool]:
        return {"daily": False, "monthly": False}

    def apply_reset(self, usage: Dict[str, Any], flags: Dict[str, bool]) -> None:
        pass


class FakeCalculator:
    """Fake calculator that properly calculates remaining quota."""

    def remaining(self, usage: Dict[str, Any], limits: Any) -> Dict[str, Any]:
        requests_limit = getattr(limits, "requests_per_day", 1000)
        tokens_limit = getattr(limits, "tokens_per_day", 100000)
        requests_used = usage.get("requests_today", 0)
        tokens_used = usage.get("tokens_today", 0)

        return {
            "requests_remaining_today": requests_limit - requests_used,
            "requests_remaining_month": getattr(limits, "requests_per_month", 10000) - usage.get("requests_this_month", 0),
            "tokens_remaining_today": tokens_limit - tokens_used,
            "tokens_remaining_minute": getattr(limits, "tokens_per_minute", 10000),
            "usage_today": requests_used,
            "tokens_today": tokens_used,
            "usage_this_month": usage.get("requests_this_month", 0),
        }

    def warnings(self, remaining: Dict[str, Any], limits: Any, threshold: float) -> Dict[str, Any]:
        return {"warning": False}

    def summarise(self, usage: Dict[str, Any]) -> Dict[str, Any]:
        return usage


class FakeRecommender:
    """Fake recommender."""

    def recommended(self, task_type: str, registry: Any, prefs: Any) -> str:
        return "default"


@pytest.fixture
def tracker():
    """Create a tracker with fake dependencies."""
    return RateLimitTracker(
        storage=FakeStorage(),
        policy=FakePolicy(),
        calculator=FakeCalculator(),
        recommender=FakeRecommender(),
    )


class TestUpdateFromHeaders:
    """Tests for update_from_headers method."""

    @pytest.mark.unit
    def test_stores_raw_headers(self, tracker):
        """Should store raw headers for debugging."""
        headers = {
            "x-ratelimit-remaining-requests": "14399",
            "x-ratelimit-limit-requests": "14400",
        }

        tracker.update_from_headers("groq", headers)

        stored = tracker.get_provider_headers("groq")
        assert stored is not None
        assert stored["raw_headers"] == headers

    @pytest.mark.unit
    def test_parses_remaining_requests(self, tracker):
        """Should parse remaining request counts."""
        headers = {
            "x-ratelimit-remaining-requests": "14399",
        }

        tracker.update_from_headers("groq", headers)

        stored = tracker.get_provider_headers("groq")
        assert stored["remaining_requests"] == 14399

    @pytest.mark.unit
    def test_parses_cerebras_day_format(self, tracker):
        """Should parse Cerebras day/hour/minute format."""
        headers = {
            "x-ratelimit-remaining-requests-day": "14375",
            "x-ratelimit-remaining-requests-hour": "875",
            "x-ratelimit-remaining-requests-minute": "21",
            "x-ratelimit-remaining-tokens-day": "988171",
        }

        tracker.update_from_headers("cerebras", headers)

        stored = tracker.get_provider_headers("cerebras")
        assert stored["remaining_requests_day"] == 14375
        assert stored["remaining_requests_hour"] == 875
        assert stored["remaining_requests_minute"] == 21
        assert stored["remaining_tokens_day"] == 988171

    @pytest.mark.unit
    def test_parses_limit_values(self, tracker):
        """Should parse limit values."""
        headers = {
            "x-ratelimit-limit-requests": "14400",
            "x-ratelimit-limit-tokens": "6000",
        }

        tracker.update_from_headers("groq", headers)

        stored = tracker.get_provider_headers("groq")
        assert stored["limit_requests"] == 14400
        assert stored["limit_tokens"] == 6000

    @pytest.mark.unit
    def test_parses_sambanova_format(self, tracker):
        """Should parse SambaNova day format with limits."""
        headers = {
            "x-ratelimit-limit-requests-day": "40",
            "x-ratelimit-remaining-requests-day": "39",
            "x-ratelimit-reset-requests-day": "1766229945",
        }

        tracker.update_from_headers("sambanova", headers)

        stored = tracker.get_provider_headers("sambanova")
        assert stored["limit_requests_day"] == 40
        assert stored["remaining_requests_day"] == 39
        assert stored["reset_requests"] == "1766229945"

    @pytest.mark.unit
    def test_stores_timestamp(self, tracker):
        """Should store when headers were last updated."""
        headers = {"x-ratelimit-remaining-requests": "100"}

        tracker.update_from_headers("groq", headers)

        stored = tracker.get_provider_headers("groq")
        assert "last_updated" in stored

    @pytest.mark.unit
    def test_persists_to_storage(self, tracker):
        """Should save to storage after update."""
        headers = {"x-ratelimit-remaining-requests": "100"}

        tracker.update_from_headers("groq", headers)

        # Verify storage.save was called
        assert len(tracker._storage.save_calls) > 0
        saved = tracker._storage.save_calls[-1]
        assert "provider_headers" in saved
        assert "groq" in saved["provider_headers"]

    @pytest.mark.unit
    def test_ignores_empty_headers(self, tracker):
        """Should not update when headers dict is empty."""
        tracker.update_from_headers("groq", {})

        stored = tracker.get_provider_headers("groq")
        assert stored is None

    @pytest.mark.unit
    def test_updates_existing_provider(self, tracker):
        """Should update existing provider data."""
        # First update
        tracker.update_from_headers("groq", {"x-ratelimit-remaining-requests": "100"})

        # Second update with different value
        tracker.update_from_headers("groq", {"x-ratelimit-remaining-requests": "50"})

        stored = tracker.get_provider_headers("groq")
        assert stored["remaining_requests"] == 50

    @pytest.mark.unit
    def test_handles_non_numeric_values(self, tracker):
        """Should handle non-numeric reset times as strings."""
        headers = {
            "x-ratelimit-reset-requests": "6s",
            "x-ratelimit-reset-tokens": "440ms",
        }

        tracker.update_from_headers("groq", headers)

        stored = tracker.get_provider_headers("groq")
        assert stored["reset_requests"] == "6s"
        assert stored["reset_tokens"] == "440ms"

    @pytest.mark.unit
    def test_multiple_providers(self, tracker):
        """Should store headers for multiple providers separately."""
        tracker.update_from_headers("groq", {"x-ratelimit-remaining-requests": "100"})
        tracker.update_from_headers("cerebras", {"x-ratelimit-remaining-requests-day": "200"})

        groq = tracker.get_provider_headers("groq")
        cerebras = tracker.get_provider_headers("cerebras")

        assert groq["remaining_requests"] == 100
        assert cerebras["remaining_requests_day"] == 200


class TestGetProviderHeaders:
    """Tests for get_provider_headers method."""

    @pytest.mark.unit
    def test_returns_none_for_unknown_provider(self, tracker):
        """Should return None for provider with no header data."""
        result = tracker.get_provider_headers("unknown")
        assert result is None

    @pytest.mark.unit
    def test_returns_stored_data(self, tracker):
        """Should return stored header data."""
        tracker.update_from_headers("groq", {"x-ratelimit-remaining-requests": "100"})

        result = tracker.get_provider_headers("groq")

        assert result is not None
        assert "remaining_requests" in result


class FakeLimits:
    """Fake provider limits for testing."""
    requests_per_day = 1000
    requests_per_month = 10000
    tokens_per_day = 100000
    tokens_per_minute = 10000


class TestGetRemainingQuotaWithHeaders:
    """Tests for get_remaining_quota integration with header data."""

    @pytest.mark.unit
    def test_uses_header_data_when_fresh(self, tracker):
        """Should prefer header-reported values when available and fresh."""
        # Store fresh header data
        tracker.update_from_headers("groq", {
            "x-ratelimit-remaining-requests": "500",
            "x-ratelimit-remaining-tokens": "50000",
        })

        # Record some usage (would normally reduce calculated remaining)
        tracker.record_request("groq", "test-model", input_tokens=1000, output_tokens=500)

        # Get remaining - should use header data, not calculated
        result = tracker.get_remaining_quota("groq", "test-model", FakeLimits())

        # Should be 500 from headers, not 999 from calculated (1000 - 1)
        assert result["requests_remaining_today"] == 500
        assert result["_source"] == "headers"

    @pytest.mark.unit
    def test_falls_back_to_calculated_when_no_headers(self, tracker):
        """Should use calculated values when no header data available."""
        # Record usage without any header data
        tracker.record_request("groq", "test-model", input_tokens=1000, output_tokens=500)

        result = tracker.get_remaining_quota("groq", "test-model", FakeLimits())

        # Should be calculated: 1000 - 1 = 999
        assert result["requests_remaining_today"] == 999
        assert "_source" not in result  # No source marker for calculated

    @pytest.mark.unit
    def test_falls_back_when_headers_stale(self, tracker):
        """Should use calculated values when header data is stale."""
        from datetime import datetime, timedelta

        # Manually set stale header data
        tracker._usage["provider_headers"] = {
            "groq": {
                "last_updated": (datetime.now() - timedelta(minutes=10)).isoformat(),
                "remaining_requests": 500,
            }
        }

        # Record usage
        tracker.record_request("groq", "test-model", input_tokens=100, output_tokens=50)

        result = tracker.get_remaining_quota("groq", "test-model", FakeLimits())

        # Should be calculated since headers are stale (>5 min old)
        assert result["requests_remaining_today"] == 999
        assert "_source" not in result

    @pytest.mark.unit
    def test_uses_day_format_headers(self, tracker):
        """Should handle Cerebras day/hour/minute format."""
        tracker.update_from_headers("cerebras", {
            "x-ratelimit-remaining-requests-day": "14375",
            "x-ratelimit-remaining-tokens-day": "988171",
        })

        result = tracker.get_remaining_quota("cerebras", "test-model", FakeLimits())

        assert result["requests_remaining_today"] == 14375
        assert result["tokens_remaining_today"] == 988171
        assert result["_source"] == "headers"

    @pytest.mark.unit
    def test_includes_tracked_usage_with_header_data(self, tracker):
        """Should include our tracked usage even when using header data."""
        # Store header data
        tracker.update_from_headers("groq", {
            "x-ratelimit-remaining-requests": "500",
        })

        # Record some usage
        tracker.record_request("groq", "test-model", input_tokens=1000, output_tokens=500)

        result = tracker.get_remaining_quota("groq", "test-model", FakeLimits())

        # Should have header-reported remaining
        assert result["requests_remaining_today"] == 500
        # But also include our tracked usage
        assert result["usage_today"] == 1
        assert result["tokens_today"] == 1500

    @pytest.mark.unit
    def test_falls_back_when_no_remaining_requests(self, tracker):
        """Should fall back if headers don't have remaining requests."""
        # Headers without remaining requests
        tracker._usage["provider_headers"] = {
            "groq": {
                "last_updated": datetime.now().isoformat(),
                "limit_requests": 1000,  # Only limit, no remaining
            }
        }

        tracker.record_request("groq", "test-model", input_tokens=100, output_tokens=50)

        result = tracker.get_remaining_quota("groq", "test-model", FakeLimits())

        # Should fall back to calculated
        assert result["requests_remaining_today"] == 999
        assert "_source" not in result
