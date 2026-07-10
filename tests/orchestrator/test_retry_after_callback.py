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
from scrappy.orchestrator.retry_after import (
    RETRY_AFTER_CAP_SECONDS,
    RETRY_AFTER_FLOOR_SECONDS,
)

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

    def test_header_retry_after_suppresses_provider(self, tmp_path):
        """A groq Retry-After header flips is_rate_limited through the callback."""
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

        assert tracker.is_rate_limited("groq", FakeRegistry()) is True

    def test_retry_at_expires_and_unsuppresses(self, tmp_path):
        """retry_at suppression self-expires once the window passes.

        Written at the tracker seam (update_from_error trusts its caller;
        the callback consumer clamps to >= 1s) so the window can be
        sub-second and the test can watch the real clock cross it.
        """
        tracker = create_rate_limit_tracker(
            tracker_file=tmp_path / "rate_limits.json"
        )
        tracker.update_from_error("cerebras", {"retry_after_seconds": 0.2})

        registry = FakeRegistry()
        assert tracker.is_rate_limited("cerebras", registry) is True

        time.sleep(0.25)
        assert tracker.is_rate_limited("cerebras", registry) is False

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


class TestCallbackRetryAfterBounds:
    """The callback consumer enforces the ratified [floor, cap] bounds.

    extract_retry_after stays raw by design; clamp_retry_after guards the
    tracker write so failure logging never throws on hostile or garbage
    values and never persists an out-of-bounds suppression window.
    """

    def _tracker_and_callback(self, tmp_path):
        tracker = create_rate_limit_tracker(
            tracker_file=tmp_path / "rate_limits.json"
        )
        return tracker, RateTrackingCallback(rate_tracker=tracker)

    @staticmethod
    def _exception_with_header(value):
        class FakeResponse:
            headers = {"Retry-After": value}

        class ProviderException(Exception):
            llm_provider = "groq"
            response = FakeResponse()

        return ProviderException("Too many requests")

    @pytest.mark.parametrize("raw", ["nan", "inf", "-5", "0"])
    def test_unusable_values_neither_write_nor_raise(self, tmp_path, raw):
        """Non-finite and non-positive values are dropped, not stored or thrown."""
        tracker, callback = self._tracker_and_callback(tmp_path)

        _fire_failure(
            callback, self._exception_with_header(raw), "groq/llama"
        )

        assert tracker.get_provider_headers("groq") is None
        assert tracker.is_rate_limited("groq", FakeRegistry()) is False

    def test_below_floor_value_clamps_to_floor(self, tmp_path):
        """A sub-second server value stores the 1s floor, not the raw value."""
        tracker, callback = self._tracker_and_callback(tmp_path)

        _fire_failure(
            callback, self._exception_with_header("0.2"), "groq/llama"
        )

        stored = tracker.get_provider_headers("groq")
        assert stored["retry_after_seconds"] == RETRY_AFTER_FLOOR_SECONDS

    def test_above_cap_value_clamps_to_cap(self, tmp_path):
        """A 25-hour server value stores the 86400s cap, not the raw value."""
        tracker, callback = self._tracker_and_callback(tmp_path)

        before = datetime.now()
        _fire_failure(
            callback, self._exception_with_header("90000"), "groq/llama"
        )

        stored = tracker.get_provider_headers("groq")
        assert stored["retry_after_seconds"] == RETRY_AFTER_CAP_SECONDS
        retry_at = datetime.fromisoformat(stored["retry_at"])
        assert retry_at >= before + timedelta(seconds=RETRY_AFTER_CAP_SECONDS - 1)
        assert retry_at <= datetime.now() + timedelta(
            seconds=RETRY_AFTER_CAP_SECONDS
        )


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
