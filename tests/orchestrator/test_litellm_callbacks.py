"""
Tests for LiteLLM callbacks.

Tests RateTrackingCallback and EscalationMetrics for usage tracking
and provider status monitoring (D9, D10 verification).
"""

import pytest
from datetime import datetime, timedelta

from scrappy.orchestrator.litellm_callbacks import (
    RateTrackingCallback,
    EscalationMetrics,
)

from tests.helpers import (
    MockRateLimitTracker,
    MockLiteLLMResponse,
    make_mock_litellm_response,
)


class TestEscalationMetrics:
    """Tests for EscalationMetrics tracking."""

    def test_records_escalation_event(self):
        """Verify escalation events are recorded."""
        metrics = EscalationMetrics()

        metrics.record_escalation("fast", "quality")

        assert metrics.total_escalations == 1
        assert metrics.escalations_by_path["fast->quality"] == 1

    def test_tracks_multiple_escalations(self):
        """Verify multiple escalations are counted correctly."""
        metrics = EscalationMetrics()

        metrics.record_escalation("fast", "quality")
        metrics.record_escalation("fast", "quality")
        metrics.record_escalation("fast", "quality")

        assert metrics.total_escalations == 3
        assert metrics.escalations_by_path["fast->quality"] == 3

    def test_tracks_different_escalation_paths(self):
        """Verify different escalation paths are tracked separately."""
        metrics = EscalationMetrics()

        metrics.record_escalation("fast", "quality")
        metrics.record_escalation("fast", "quality")
        metrics.record_escalation("ultra_fast", "fast")  # Hypothetical path

        assert metrics.total_escalations == 3
        assert metrics.escalations_by_path["fast->quality"] == 2
        assert metrics.escalations_by_path["ultra_fast->fast"] == 1

    def test_get_summary_returns_correct_format(self):
        """Verify get_summary returns proper dictionary format."""
        metrics = EscalationMetrics()
        metrics.record_escalation("fast", "quality")
        metrics.record_escalation("fast", "quality")

        summary = metrics.get_summary()

        assert summary["total_escalations"] == 2
        assert summary["by_path"]["fast->quality"] == 2

    def test_empty_metrics_summary(self):
        """Verify empty metrics return zero counts."""
        metrics = EscalationMetrics()

        summary = metrics.get_summary()

        assert summary["total_escalations"] == 0
        assert summary["by_path"] == {}


class TestRateTrackingCallback:
    """Tests for RateTrackingCallback (D9 verification)."""

    def test_callback_extracts_real_provider_not_group_name(self):
        """Verify callback records 'groq' not 'fast' (D9)."""
        tracker = MockRateLimitTracker()
        callback = RateTrackingCallback(rate_tracker=tracker)

        # Create mock response with real model
        mock_response = make_mock_litellm_response(
            model="groq/llama-3.1-8b-instant",
            prompt_tokens=10,
            completion_tokens=20,
        )

        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=100)

        callback.log_success_event(
            kwargs={"model": "fast"},  # Group name in request
            response_obj=mock_response,
            start_time=start_time,
            end_time=end_time,
        )

        # Provider should be extracted from response, not request
        assert tracker.last_recorded["provider"] == "groq"

    def test_callback_extracts_real_model_not_group_name(self):
        """Verify callback records 'groq/llama-3.1-8b-instant' not 'fast' (D9)."""
        tracker = MockRateLimitTracker()
        callback = RateTrackingCallback(rate_tracker=tracker)

        mock_response = make_mock_litellm_response(
            model="groq/llama-3.1-8b-instant"
        )

        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=100)

        callback.log_success_event(
            kwargs={"model": "fast"},
            response_obj=mock_response,
            start_time=start_time,
            end_time=end_time,
        )

        # Model info is extracted from response
        assert tracker.last_recorded["provider"] == "groq"

    def test_callback_records_token_counts_correctly(self):
        """Verify token counts are recorded correctly."""
        tracker = MockRateLimitTracker()
        callback = RateTrackingCallback(rate_tracker=tracker)

        mock_response = make_mock_litellm_response(
            prompt_tokens=50,
            completion_tokens=100,
        )

        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=100)

        callback.log_success_event(
            kwargs={},
            response_obj=mock_response,
            start_time=start_time,
            end_time=end_time,
        )

        assert tracker.last_recorded["input_tokens"] == 50
        assert tracker.last_recorded["output_tokens"] == 100

    def test_callback_records_latency_correctly(self):
        """Verify latency is calculated from start/end time and passed to status_tracker."""
        from tests.helpers import MockProviderStatusTracker

        status_tracker = MockProviderStatusTracker()
        callback = RateTrackingCallback(status_tracker=status_tracker)

        mock_response = make_mock_litellm_response(model="groq/llama-3.1-8b-instant")

        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=250)  # 250ms latency

        callback.log_success_event(
            kwargs={},
            response_obj=mock_response,
            start_time=start_time,
            end_time=end_time,
        )

        # Latency should be calculated as (end - start) in milliseconds
        assert status_tracker.last_success is not None
        assert status_tracker.last_success["latency_ms"] == pytest.approx(250.0, abs=10)

    def test_callbacks_noop_when_no_rate_tracker(self):
        """Verify callbacks don't crash when no rate_tracker is provided."""
        callback = RateTrackingCallback(rate_tracker=None)

        mock_response = make_mock_litellm_response()

        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=100)

        # Should not raise any errors
        callback.log_success_event(
            kwargs={},
            response_obj=mock_response,
            start_time=start_time,
            end_time=end_time,
        )

        callback.log_failure_event(
            kwargs={"exception": Exception("test")},
            response_obj=None,
            start_time=start_time,
            end_time=end_time,
        )


class TestRateTrackingCallbackEscalation:
    """Tests for escalation tracking in RateTrackingCallback."""

    def test_record_escalation_updates_metrics(self):
        """Verify record_escalation updates escalation metrics."""
        callback = RateTrackingCallback()

        callback.record_escalation("fast", "quality")

        assert callback.escalation_metrics.total_escalations == 1

    def test_callback_maintains_escalation_metrics(self):
        """Verify escalation metrics are accessible."""
        callback = RateTrackingCallback()

        callback.record_escalation("fast", "quality")
        callback.record_escalation("fast", "quality")

        summary = callback.escalation_metrics.get_summary()
        assert summary["total_escalations"] == 2
        assert summary["by_path"]["fast->quality"] == 2

    def test_custom_escalation_metrics_used(self):
        """Verify custom EscalationMetrics can be injected."""
        custom_metrics = EscalationMetrics()
        custom_metrics.record_escalation("preset", "path")

        callback = RateTrackingCallback(escalation_metrics=custom_metrics)

        # Should use the provided metrics
        assert callback.escalation_metrics.total_escalations == 1
        assert callback.escalation_metrics.escalations_by_path["preset->path"] == 1


class TestRateTrackingCallbackFailure:
    """Tests for failure tracking in RateTrackingCallback."""

    def test_log_failure_records_to_tracker(self):
        """Verify failures are recorded to rate tracker."""
        tracker = MockRateLimitTracker()
        callback = RateTrackingCallback(rate_tracker=tracker)

        class MockException(Exception):
            llm_provider = "groq"

        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=100)

        callback.log_failure_event(
            kwargs={"exception": MockException("test"), "model": "fast"},
            response_obj=None,
            start_time=start_time,
            end_time=end_time,
        )

        assert tracker.last_recorded["provider"] == "groq"
        assert tracker.last_recorded["input_tokens"] == 0
        assert tracker.last_recorded["output_tokens"] == 0
        assert tracker.last_recorded["success"] is False

    def test_log_failure_handles_missing_provider(self):
        """Verify failure logging handles missing llm_provider."""
        tracker = MockRateLimitTracker()
        callback = RateTrackingCallback(rate_tracker=tracker)

        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=100)

        callback.log_failure_event(
            kwargs={"exception": Exception("test"), "model": "fast"},
            response_obj=None,
            start_time=start_time,
            end_time=end_time,
        )

        assert tracker.last_recorded["provider"] == "unknown"


class TestCallbackLiteLLMInterface:
    """Tests for LiteLLM CustomLogger interface methods."""

    def test_log_pre_api_call_is_noop(self):
        """Verify log_pre_api_call does nothing (no errors)."""
        callback = RateTrackingCallback()

        # Should not raise
        callback.log_pre_api_call(
            model="fast",
            messages=[],
            kwargs={}
        )

    def test_log_post_api_call_calls_success_for_valid_response(self):
        """Verify log_post_api_call calls log_success_event for valid responses."""
        tracker = MockRateLimitTracker()
        callback = RateTrackingCallback(rate_tracker=tracker)

        mock_response = make_mock_litellm_response(model="groq/llama-3.1-8b-instant")

        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=100)

        callback.log_post_api_call(
            kwargs={},
            response_obj=mock_response,
            start_time=start_time,
            end_time=end_time,
        )

        # Should have recorded a request
        assert len(tracker.recorded_requests) == 1

    def test_log_post_api_call_ignores_none_response(self):
        """Verify log_post_api_call ignores None responses."""
        tracker = MockRateLimitTracker()
        callback = RateTrackingCallback(rate_tracker=tracker)

        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=100)

        callback.log_post_api_call(
            kwargs={},
            response_obj=None,
            start_time=start_time,
            end_time=end_time,
        )

        # Should not have recorded anything
        assert len(tracker.recorded_requests) == 0

    def test_log_stream_event_is_noop(self):
        """Verify log_stream_event does nothing (no errors)."""
        callback = RateTrackingCallback()

        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=100)

        # Should not raise
        callback.log_stream_event(
            kwargs={},
            response_obj=None,
            start_time=start_time,
            end_time=end_time,
        )


class TestAsyncCallbackMethods:
    """Tests for async callback methods."""

    @pytest.mark.asyncio
    async def test_async_log_success_event(self):
        """Verify async_log_success_event works correctly."""
        tracker = MockRateLimitTracker()
        callback = RateTrackingCallback(rate_tracker=tracker)

        mock_response = make_mock_litellm_response(model="groq/llama-3.1-8b-instant")

        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=100)

        await callback.async_log_success_event(
            kwargs={},
            response_obj=mock_response,
            start_time=start_time,
            end_time=end_time,
        )

        assert tracker.last_recorded["provider"] == "groq"

    @pytest.mark.asyncio
    async def test_async_log_failure_event(self):
        """Verify async_log_failure_event works correctly."""
        tracker = MockRateLimitTracker()
        callback = RateTrackingCallback(rate_tracker=tracker)

        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=100)

        await callback.async_log_failure_event(
            kwargs={"exception": Exception("test")},
            response_obj=None,
            start_time=start_time,
            end_time=end_time,
        )

        assert len(tracker.recorded_requests) == 1
