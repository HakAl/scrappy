"""
Behavior tests for PR-3b retry-after consolidation at real boundaries.

CRITICAL: NO REAL API CALLS. Exception-like fakes only.

Covers, through the real RateLimitTracker (no _persist/update mocks):
- Gemini parity: a recorded gemini exception driven through
  log_failure_event yields the same retry_at window as the deleted
  parse_gemini_rate_limit_error path did.
- Non-gemini providers now populate retry_at (declared PR-3b delta),
  visible via is_rate_limited and the legacy recommender ONLY; the
  enforcement gate does not read retry_at and is not tested here.
- D6a double-write retirement, observed at the filesystem boundary:
  one failure event changes exactly one store's file.
"""

import time
from datetime import datetime, timedelta

import pytest

from scrappy.orchestrator.litellm_callbacks import RateTrackingCallback
from scrappy.orchestrator.provider_status import ProviderStatusTracker
from scrappy.orchestrator.rate_limiting.factory import create_rate_limit_tracker
from scrappy.orchestrator.rate_limiting.recommender import RateLimitRecommender

GEMINI_MESSAGE = "Resource exhausted. Please retry in 7.215400659s"
GEMINI_RETRY_SECONDS = 7.215400659


class FakeRegistry:
    """Registry double: providers are available but expose no limits."""

    def __init__(self, available=None):
        self._available = available or []

    def list_available(self):
        return list(self._available)

    def get(self, name):
        return None


def _fire_failure(callback, exception, model):
    """Drive one failure event through the callback."""
    start_time = datetime.now()
    end_time = start_time + timedelta(milliseconds=100)
    callback.log_failure_event(
        kwargs={"exception": exception, "model": model},
        response_obj=None,
        start_time=start_time,
        end_time=end_time,
    )


class TestGeminiParity:
    """The provider-agnostic path must reproduce the deleted parser's result."""

    def test_gemini_exception_yields_same_retry_at_window(self, tmp_path):
        """A recorded gemini 429 message produces retry_at = now + parsed value."""
        tracker = create_rate_limit_tracker(
            tracker_file=tmp_path / "rate_limits.json"
        )
        callback = RateTrackingCallback(rate_tracker=tracker)

        class GeminiException(Exception):
            llm_provider = "gemini"

        before = datetime.now()
        _fire_failure(callback, GeminiException(GEMINI_MESSAGE), "gemini-2.0-flash")
        after = datetime.now()

        header_data = tracker.get_provider_headers("gemini")
        assert header_data is not None
        assert header_data["retry_after_seconds"] == pytest.approx(
            GEMINI_RETRY_SECONDS
        )
        retry_at = datetime.fromisoformat(header_data["retry_at"])
        assert before + timedelta(seconds=GEMINI_RETRY_SECONDS) <= retry_at
        assert retry_at <= after + timedelta(seconds=GEMINI_RETRY_SECONDS)

        # The window suppresses the provider exactly as before
        assert tracker.is_rate_limited("gemini", FakeRegistry()) is True


class TestNonGeminiRetryAt:
    """Declared PR-3b delta: retry_at now populates for all providers."""

    def test_header_retry_after_flips_is_rate_limited_until_it_passes(
        self, tmp_path
    ):
        """A groq Retry-After header suppresses groq until the window expires."""
        tracker = create_rate_limit_tracker(
            tracker_file=tmp_path / "rate_limits.json"
        )
        callback = RateTrackingCallback(rate_tracker=tracker)

        class FakeResponse:
            headers = {"Retry-After": "0.2"}

        class GroqException(Exception):
            llm_provider = "groq"
            response = FakeResponse()

        _fire_failure(callback, GroqException("Too many requests"), "groq/llama")

        registry = FakeRegistry()
        assert tracker.is_rate_limited("groq", registry) is True

        time.sleep(0.25)
        assert tracker.is_rate_limited("groq", registry) is False

    def test_legacy_recommender_skips_provider_in_retry_window(self, tmp_path):
        """The legacy availability path routes around a retry_at-suppressed provider."""
        tracker = create_rate_limit_tracker(
            tracker_file=tmp_path / "rate_limits.json"
        )
        callback = RateTrackingCallback(rate_tracker=tracker)

        class FakeResponse:
            headers = {"Retry-After": "60"}

        class GroqException(Exception):
            llm_provider = "groq"
            response = FakeResponse()

        _fire_failure(callback, GroqException("Too many requests"), "groq/llama")

        recommender = RateLimitRecommender(usage_query=tracker, scorer=None)
        registry = FakeRegistry(available=["groq", "cerebras"])

        recommended = recommender.recommended(
            "general", registry, {"general": ["groq", "cerebras"]}
        )

        assert recommended == "cerebras"


class TestDoubleWriteRetired:
    """D6a: one failure event writes exactly one store's file."""

    def test_one_failure_event_changes_exactly_one_file(
        self, tmp_path, monkeypatch
    ):
        """Only the rate tracker file appears; no provider stats file anywhere."""
        # Point HOME into the observed tmp tree so a regression to the old
        # ~/.scrappy/provider_stats.json write would show up in the scan.
        monkeypatch.setenv("HOME", str(tmp_path))

        rate_file = tmp_path / "rate" / "rate_limits.json"
        rate_file.parent.mkdir(parents=True)
        rate_tracker = create_rate_limit_tracker(tracker_file=rate_file)
        status_tracker = ProviderStatusTracker()
        callback = RateTrackingCallback(
            rate_tracker=rate_tracker,
            status_tracker=status_tracker,
        )

        before = {p for p in tmp_path.rglob("*") if p.is_file()}

        class GeminiException(Exception):
            llm_provider = "gemini"

        _fire_failure(callback, GeminiException(GEMINI_MESSAGE), "gemini-2.0-flash")

        after = {p for p in tmp_path.rglob("*") if p.is_file()}
        assert after - before == {rate_file}

        # Both stores still saw the event in memory
        assert status_tracker.get_status("gemini") is not None
        assert rate_tracker.get_provider_headers("gemini") is not None
