"""
Tests for ProviderStatusTracker and key validation.

Tests real-time status tracking, rolling window metrics, and health check
functionality. The tracker is session-scoped (in-memory only, D6a): stats
must not survive into a fresh tracker and events must not touch the disk.
"""

import pytest
from datetime import datetime, timedelta

from scrappy.orchestrator.provider_status import (
    ProviderStatusTracker,
    ProviderStatus,
    HealthCheckResult,
    RequestRecord,
    DEFAULT_WINDOW_SIZE,
)
from scrappy.orchestrator.litellm_callbacks import RateTrackingCallback

from tests.helpers import (
    MockRateLimitTracker,
    MockProviderStatusTracker,
    make_mock_litellm_response,
)


class TestProviderStatusTracker:
    """Tests for ProviderStatusTracker status tracking."""

    def test_on_success_marks_provider_healthy(self):
        """Verify on_success marks provider as healthy."""
        tracker = ProviderStatusTracker()

        tracker.on_success("groq", "groq/llama-3.1-8b-instant", 150.0)

        status = tracker.get_status("groq")
        assert status is not None
        assert status.healthy is True
        assert status.last_latency_ms == 150.0
        assert status.request_count == 1

    def test_on_failure_marks_provider_unhealthy(self):
        """Verify on_failure marks provider as unhealthy."""
        tracker = ProviderStatusTracker()

        tracker.on_failure("groq", "Rate limit exceeded")

        status = tracker.get_status("groq")
        assert status is not None
        assert status.healthy is False
        assert status.last_error == "Rate limit exceeded"
        assert status.error_count == 1

    def test_success_clears_last_error(self):
        """Verify success clears last error."""
        tracker = ProviderStatusTracker()

        # Fail first
        tracker.on_failure("groq", "Some error")
        assert tracker.get_status("groq").last_error == "Some error"

        # Then succeed
        tracker.on_success("groq", "groq/llama-3.1-8b-instant", 100.0)

        status = tracker.get_status("groq")
        assert status.healthy is True
        assert status.last_error is None

    def test_multiple_providers_tracked_separately(self):
        """Verify each provider has independent status."""
        tracker = ProviderStatusTracker()

        tracker.on_success("groq", "groq/llama-3.1-8b-instant", 100.0)
        tracker.on_failure("cerebras", "Auth error")

        groq_status = tracker.get_status("groq")
        cerebras_status = tracker.get_status("cerebras")

        assert groq_status.healthy is True
        assert cerebras_status.healthy is False

    def test_get_all_status_returns_all_providers(self):
        """Verify get_all_status returns all tracked providers."""
        tracker = ProviderStatusTracker()

        tracker.on_success("groq", "groq/llama-3.1-8b-instant", 100.0)
        tracker.on_success("cerebras", "cerebras/llama3.1-8b", 50.0)

        all_status = tracker.get_all_status()

        assert "groq" in all_status
        assert "cerebras" in all_status
        assert len(all_status) == 2

    def test_is_healthy_returns_true_for_unknown_provider(self):
        """Verify unknown providers are assumed healthy."""
        tracker = ProviderStatusTracker()

        # No data for provider
        assert tracker.is_healthy("unknown_provider") is True

    def test_is_healthy_reflects_last_status(self):
        """Verify is_healthy reflects current status."""
        tracker = ProviderStatusTracker()

        tracker.on_success("groq", "groq/llama", 100.0)
        assert tracker.is_healthy("groq") is True

        tracker.on_failure("groq", "Error")
        assert tracker.is_healthy("groq") is False

    def test_request_and_error_counts_accumulate(self):
        """Verify counts accumulate across calls."""
        tracker = ProviderStatusTracker()

        tracker.on_success("groq", "groq/llama", 100.0)
        tracker.on_success("groq", "groq/llama", 100.0)
        tracker.on_failure("groq", "Error 1")
        tracker.on_success("groq", "groq/llama", 100.0)
        tracker.on_failure("groq", "Error 2")

        status = tracker.get_status("groq")
        assert status.request_count == 3
        assert status.error_count == 2


class TestProviderStatusTrackerTimestamps:
    """Tests for timestamp tracking."""

    def test_last_success_timestamp_recorded(self):
        """Verify last_success timestamp is set."""
        tracker = ProviderStatusTracker()
        before = datetime.now()

        tracker.on_success("groq", "groq/llama", 100.0)

        status = tracker.get_status("groq")
        assert status.last_success is not None
        assert status.last_success >= before

    def test_last_failure_timestamp_recorded(self):
        """Verify last_failure timestamp is set."""
        tracker = ProviderStatusTracker()
        before = datetime.now()

        tracker.on_failure("groq", "Error")

        status = tracker.get_status("groq")
        assert status.last_failure is not None
        assert status.last_failure >= before


class TestProviderStatusTrackerSessionScope:
    """Tests for session-scoped (in-memory only) behavior (D6a).

    /status continuity across restart was retired deliberately: the tracker
    has zero routing consumers and its persistence was a per-event disk write.
    """

    def test_fresh_tracker_starts_empty(self):
        """Verify stats recorded in one tracker do not appear in a new one."""
        tracker1 = ProviderStatusTracker()
        tracker1.on_success("groq", "groq/llama", 100.0, tokens=50)
        tracker1.on_failure("gemini", "Rate limit")
        assert tracker1.get_all_status() != {}

        tracker2 = ProviderStatusTracker()

        assert tracker2.get_all_status() == {}
        assert tracker2.get_status("groq") is None

    def test_events_write_nothing_to_disk(self, tmp_path, monkeypatch):
        """Verify success/failure/reset events never touch the filesystem."""
        # Point HOME at an empty tmp dir so a regression to the old
        # ~/.scrappy/provider_stats.json write would land here and be visible.
        monkeypatch.setenv("HOME", str(tmp_path))

        tracker = ProviderStatusTracker()
        tracker.on_success("groq", "groq/llama", 100.0, tokens=50)
        tracker.on_failure("gemini", "Rate limit exceeded")
        tracker.reset_stats("groq")
        tracker.reset_stats()

        assert list(tmp_path.rglob("*")) == []

    def test_in_session_status_still_available(self):
        """Verify the session-scoped tracker still serves /status in-session."""
        tracker = ProviderStatusTracker()

        tracker.on_success("groq", "groq/llama", 100.0, tokens=50)

        status = tracker.get_status("groq")
        assert status is not None
        assert status.request_count == 1
        assert status.total_tokens == 50


class TestRateTrackingCallbackWithStatusTracker:
    """Tests for RateTrackingCallback integration with ProviderStatusTracker."""

    def test_callback_records_success_to_status_tracker(self):
        """Verify callback calls status_tracker.on_success."""
        status_tracker = MockProviderStatusTracker()
        callback = RateTrackingCallback(status_tracker=status_tracker)

        mock_response = make_mock_litellm_response(model="groq/llama-3.1-8b-instant")
        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=150)

        callback.log_success_event(
            kwargs={},
            response_obj=mock_response,
            start_time=start_time,
            end_time=end_time,
        )

        assert status_tracker.last_success is not None
        assert status_tracker.last_success["provider"] == "groq"
        assert status_tracker.last_success["model"] == "groq/llama-3.1-8b-instant"
        assert status_tracker.last_success["latency_ms"] == pytest.approx(150.0, abs=10)

    def test_callback_records_failure_to_status_tracker(self):
        """Verify callback calls status_tracker.on_failure."""
        status_tracker = MockProviderStatusTracker()
        callback = RateTrackingCallback(status_tracker=status_tracker)

        class MockException(Exception):
            llm_provider = "groq"

        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=100)

        callback.log_failure_event(
            kwargs={"exception": MockException("Rate limit exceeded")},
            response_obj=None,
            start_time=start_time,
            end_time=end_time,
        )

        assert status_tracker.last_failure is not None
        assert status_tracker.last_failure["provider"] == "groq"
        assert "Rate limit exceeded" in status_tracker.last_failure["error"]

    def test_callback_works_with_both_trackers(self):
        """Verify callback works with both rate_tracker and status_tracker."""
        rate_tracker = MockRateLimitTracker()
        status_tracker = MockProviderStatusTracker()
        callback = RateTrackingCallback(
            rate_tracker=rate_tracker,
            status_tracker=status_tracker,
        )

        mock_response = make_mock_litellm_response(model="groq/llama-3.1-8b-instant")
        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=100)

        callback.log_success_event(
            kwargs={},
            response_obj=mock_response,
            start_time=start_time,
            end_time=end_time,
        )

        # Both trackers should have received the event
        assert rate_tracker.last_recorded is not None
        assert status_tracker.last_success is not None



class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""

    def test_healthy_result(self):
        """Verify healthy result structure."""
        result = HealthCheckResult(
            model="groq/llama-3.1-8b-instant",
            healthy=True,
            latency_ms=150.0,
        )

        assert result.model == "groq/llama-3.1-8b-instant"
        assert result.healthy is True
        assert result.latency_ms == 150.0
        assert result.error is None

    def test_unhealthy_result(self):
        """Verify unhealthy result structure."""
        result = HealthCheckResult(
            model="groq/llama-3.1-8b-instant",
            healthy=False,
            error="Invalid API key",
        )

        assert result.healthy is False
        assert result.error == "Invalid API key"
        assert result.latency_ms is None


# =============================================================================
# Rolling Window Tests
# =============================================================================


class TestRequestRecord:
    """Tests for RequestRecord dataclass."""

    def test_creates_success_record(self):
        """Verify successful request record creation."""
        record = RequestRecord(
            timestamp=datetime.now(),
            success=True,
            latency_ms=100.0,
            tokens=150,
        )

        assert record.success is True
        assert record.latency_ms == 100.0
        assert record.tokens == 150
        assert record.error is None

    def test_creates_failure_record(self):
        """Verify failed request record creation."""
        record = RequestRecord(
            timestamp=datetime.now(),
            success=False,
            latency_ms=50.0,
            error="Rate limit exceeded",
        )

        assert record.success is False
        assert record.error == "Rate limit exceeded"
        assert record.tokens == 0


class TestProviderStatusRollingWindow:
    """Tests for ProviderStatus rolling window metrics."""

    def test_success_rate_with_no_requests(self):
        """Verify success rate returns 1.0 when healthy with no requests."""
        status = ProviderStatus(healthy=True)
        assert status.success_rate == 1.0

    def test_success_rate_when_unhealthy_no_requests(self):
        """Verify success rate returns 0.0 when unhealthy with no requests."""
        status = ProviderStatus(healthy=False)
        assert status.success_rate == 0.0

    def test_success_rate_from_rolling_window(self):
        """Verify success rate calculated from rolling window."""
        status = ProviderStatus()

        # Add 3 successes and 1 failure = 75%
        for _ in range(3):
            status.add_request(RequestRecord(
                timestamp=datetime.now(),
                success=True,
                latency_ms=100.0,
            ))
        status.add_request(RequestRecord(
            timestamp=datetime.now(),
            success=False,
            latency_ms=50.0,
            error="error",
        ))

        assert status.success_rate == 0.75

    def test_avg_latency_from_rolling_window(self):
        """Verify average latency calculated from successful requests."""
        status = ProviderStatus()

        # Add 3 requests with latencies 100, 200, 300 (avg = 200)
        for latency in [100.0, 200.0, 300.0]:
            status.add_request(RequestRecord(
                timestamp=datetime.now(),
                success=True,
                latency_ms=latency,
            ))

        assert status.avg_latency_ms == 200.0

    def test_avg_latency_excludes_failures(self):
        """Verify average latency only includes successful requests."""
        status = ProviderStatus()

        status.add_request(RequestRecord(
            timestamp=datetime.now(), success=True, latency_ms=100.0,
        ))
        status.add_request(RequestRecord(
            timestamp=datetime.now(), success=False, latency_ms=5000.0, error="timeout",
        ))
        status.add_request(RequestRecord(
            timestamp=datetime.now(), success=True, latency_ms=200.0,
        ))

        # (100 + 200) / 2 = 150
        assert status.avg_latency_ms == 150.0

    def test_avg_latency_falls_back_to_last_latency(self):
        """Verify avg_latency falls back to last_latency_ms when no successes."""
        status = ProviderStatus(last_latency_ms=500.0)

        status.add_request(RequestRecord(
            timestamp=datetime.now(), success=False, latency_ms=100.0, error="err",
        ))

        assert status.avg_latency_ms == 500.0

    def test_window_tokens_sums_all_requests(self):
        """Verify window_tokens sums tokens from all requests."""
        status = ProviderStatus()

        status.add_request(RequestRecord(
            timestamp=datetime.now(), success=True, latency_ms=100.0, tokens=50,
        ))
        status.add_request(RequestRecord(
            timestamp=datetime.now(), success=True, latency_ms=100.0, tokens=100,
        ))

        assert status.window_tokens == 150

    def test_rolling_window_max_size(self):
        """Verify rolling window respects max size."""
        status = ProviderStatus()

        # Add more than window size
        for _ in range(DEFAULT_WINDOW_SIZE + 10):
            status.add_request(RequestRecord(
                timestamp=datetime.now(), success=True, latency_ms=100.0,
            ))

        assert status.window_size == DEFAULT_WINDOW_SIZE


class TestProviderStatusTrackerTokens:
    """Tests for token tracking in ProviderStatusTracker."""

    def test_on_success_tracks_tokens(self):
        """Verify on_success accumulates tokens."""
        tracker = ProviderStatusTracker()

        tracker.on_success("groq", "groq/llama", 100.0, tokens=50)
        tracker.on_success("groq", "groq/llama", 100.0, tokens=100)

        status = tracker.get_status("groq")
        assert status.total_tokens == 150

    def test_tokens_in_rolling_window(self):
        """Verify tokens tracked in rolling window."""
        tracker = ProviderStatusTracker()

        tracker.on_success("groq", "groq/llama", 100.0, tokens=50)
        tracker.on_success("groq", "groq/llama", 100.0, tokens=100)

        status = tracker.get_status("groq")
        assert status.window_tokens == 150


class TestProviderStatusTrackerFiltering:
    """Tests for filtering providers by health."""

    def test_get_healthy_providers_filters_by_success_rate(self):
        """Verify get_healthy_providers filters by minimum success rate."""
        tracker = ProviderStatusTracker()

        # Provider with 100% success rate
        for _ in range(5):
            tracker.on_success("groq", "groq/llama", 100.0)

        # Provider with 50% success rate
        tracker.on_success("gemini", "gemini/flash", 100.0)
        tracker.on_failure("gemini", "error")

        # With 0.5 threshold, both should be included
        healthy = tracker.get_healthy_providers(min_success_rate=0.5)
        assert "groq" in healthy
        assert "gemini" in healthy

        # With 0.8 threshold, only groq should be included
        healthy = tracker.get_healthy_providers(min_success_rate=0.8)
        assert "groq" in healthy
        assert "gemini" not in healthy

    def test_reset_stats_clears_specific_provider(self):
        """Verify reset_stats clears only specified provider."""
        tracker = ProviderStatusTracker()

        tracker.on_success("groq", "groq/llama", 100.0)
        tracker.on_success("gemini", "gemini/flash", 150.0)

        tracker.reset_stats("groq")

        assert tracker.get_status("groq") is None
        assert tracker.get_status("gemini") is not None

    def test_reset_stats_clears_all_when_no_provider(self):
        """Verify reset_stats clears all providers when no provider specified."""
        tracker = ProviderStatusTracker()

        tracker.on_success("groq", "groq/llama", 100.0)
        tracker.on_success("gemini", "gemini/flash", 150.0)

        tracker.reset_stats()

        assert tracker.get_status("groq") is None
        assert tracker.get_status("gemini") is None


class TestCallbackTokenTracking:
    """Tests for token tracking through callback integration."""

    def test_callback_passes_tokens_to_status_tracker(self):
        """Verify callback passes token count to status_tracker."""
        status_tracker = MockProviderStatusTracker()
        callback = RateTrackingCallback(status_tracker=status_tracker)

        mock_response = make_mock_litellm_response(
            model="groq/llama-3.1-8b-instant",
            prompt_tokens=50,
            completion_tokens=100,
        )
        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=150)

        callback.log_success_event(
            kwargs={},
            response_obj=mock_response,
            start_time=start_time,
            end_time=end_time,
        )

        assert status_tracker.last_success is not None
        assert status_tracker.last_success["tokens"] == 150  # 50 + 100
