"""
Tests for ProviderStatusTracker and key validation.

Tests real-time status tracking and health check functionality.
"""

import pytest
from datetime import datetime, timedelta

from scrappy.orchestrator.provider_status import (
    ProviderStatusTracker,
    ProviderStatus,
    HealthCheckResult,
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
