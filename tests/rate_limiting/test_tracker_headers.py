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


class TestUpdateFromError:
    """Tests for update_from_error method (Gemini rate limit parsing)."""

    @pytest.mark.unit
    def test_stores_retry_after_seconds(self, tracker):
        """Should store retry_after_seconds from error data."""
        error_data = {
            "retry_after_seconds": 7.215,
            "message": "Resource exhausted. Please retry in 7.215s",
        }

        tracker.update_from_error("gemini", error_data)

        stored = tracker.get_provider_headers("gemini")
        assert stored is not None
        assert stored["retry_after_seconds"] == 7.215

    @pytest.mark.unit
    def test_calculates_retry_at_timestamp(self, tracker):
        """Should calculate when we can retry."""
        error_data = {
            "retry_after_seconds": 30.0,
            "message": "Please retry in 30s",
        }

        tracker.update_from_error("gemini", error_data)

        stored = tracker.get_provider_headers("gemini")
        assert "retry_at" in stored
        # Should be a valid ISO timestamp
        from datetime import datetime
        retry_at = datetime.fromisoformat(stored["retry_at"])
        assert retry_at > datetime.now()

    @pytest.mark.unit
    def test_stores_quota_type(self, tracker):
        """Should store quota_type when provided."""
        error_data = {
            "quota_type": "tokens",
            "message": "Token quota exceeded",
        }

        tracker.update_from_error("gemini", error_data)

        stored = tracker.get_provider_headers("gemini")
        assert stored["quota_exceeded"] == "tokens"

    @pytest.mark.unit
    def test_stores_error_message_truncated(self, tracker):
        """Should store error message, truncated to 200 chars."""
        long_message = "x" * 300
        error_data = {
            "message": long_message,
        }

        tracker.update_from_error("gemini", error_data)

        stored = tracker.get_provider_headers("gemini")
        assert len(stored["error_message"]) == 200

    @pytest.mark.unit
    def test_marks_from_error_flag(self, tracker):
        """Should mark data as coming from error response."""
        error_data = {"message": "Rate limit exceeded"}

        tracker.update_from_error("gemini", error_data)

        stored = tracker.get_provider_headers("gemini")
        assert stored["from_error"] is True

    @pytest.mark.unit
    def test_stores_timestamp(self, tracker):
        """Should store when error was received."""
        error_data = {"message": "Quota exceeded"}

        tracker.update_from_error("gemini", error_data)

        stored = tracker.get_provider_headers("gemini")
        assert "last_updated" in stored

    @pytest.mark.unit
    def test_persists_to_storage(self, tracker):
        """Should save to storage after update."""
        error_data = {"message": "Rate limit exceeded"}

        tracker.update_from_error("gemini", error_data)

        # Verify storage.save was called
        assert len(tracker._storage.save_calls) > 0
        saved = tracker._storage.save_calls[-1]
        assert "provider_headers" in saved
        assert "gemini" in saved["provider_headers"]

    @pytest.mark.unit
    def test_ignores_empty_error_data(self, tracker):
        """Should not update when error_data is empty."""
        tracker.update_from_error("gemini", {})

        stored = tracker.get_provider_headers("gemini")
        assert stored is None

    @pytest.mark.unit
    def test_ignores_none_error_data(self, tracker):
        """Should not update when error_data is None."""
        tracker.update_from_error("gemini", None)

        stored = tracker.get_provider_headers("gemini")
        assert stored is None

    @pytest.mark.unit
    def test_updates_existing_provider(self, tracker):
        """Should update existing provider data."""
        # First update
        tracker.update_from_error("gemini", {"retry_after_seconds": 10.0, "message": "First"})

        # Second update
        tracker.update_from_error("gemini", {"retry_after_seconds": 5.0, "message": "Second"})

        stored = tracker.get_provider_headers("gemini")
        assert stored["retry_after_seconds"] == 5.0
        assert stored["error_message"] == "Second"


class TestIsRateLimitedWithRetryAt:
    """Tests for is_rate_limited checking retry_at timestamp."""

    @pytest.mark.unit
    def test_returns_true_when_retry_at_in_future(self, tracker):
        """Should return True when retry_at is in the future."""
        from datetime import datetime, timedelta

        # Set retry_at to 30 seconds from now
        future_time = datetime.now() + timedelta(seconds=30)
        tracker._usage["provider_headers"] = {
            "gemini": {
                "retry_at": future_time.isoformat(),
            }
        }

        # Mock registry with empty provider
        class MockRegistry:
            def get(self, name):
                return None

        result = tracker.is_rate_limited("gemini", MockRegistry())
        assert result is True

    @pytest.mark.unit
    def test_returns_false_when_retry_at_in_past(self, tracker):
        """Should return False when retry_at has passed."""
        from datetime import datetime, timedelta

        # Set retry_at to 30 seconds ago
        past_time = datetime.now() - timedelta(seconds=30)
        tracker._usage["provider_headers"] = {
            "gemini": {
                "retry_at": past_time.isoformat(),
            }
        }

        # Mock registry with empty provider
        class MockRegistry:
            def get(self, name):
                return None

        result = tracker.is_rate_limited("gemini", MockRegistry())
        assert result is False  # retry_at passed, provider not in registry

    @pytest.mark.unit
    def test_handles_invalid_retry_at(self, tracker):
        """Should ignore invalid retry_at timestamps."""
        tracker._usage["provider_headers"] = {
            "gemini": {
                "retry_at": "not-a-timestamp",
            }
        }

        class MockRegistry:
            def get(self, name):
                return None

        # Should not raise, just ignore
        result = tracker.is_rate_limited("gemini", MockRegistry())
        assert result is False

    @pytest.mark.unit
    def test_integrates_with_error_update(self, tracker):
        """Should detect rate limit from error update flow."""
        # Simulate Gemini rate limit error
        tracker.update_from_error("gemini", {
            "retry_after_seconds": 60.0,
            "message": "Please retry in 60s",
        })

        class MockRegistry:
            def get(self, name):
                return None

        # Should be rate limited since retry_at is in future
        result = tracker.is_rate_limited("gemini", MockRegistry())
        assert result is True
