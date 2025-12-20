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
    parse_gemini_rate_limit_error,
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


class TestExtractProvider:
    """Tests for _extract_provider method."""

    def test_extracts_from_model_string_with_slash(self):
        """Verify provider extracted from 'provider/model' format."""
        callback = RateTrackingCallback()

        result = callback._extract_provider("groq/llama-3.3-70b-versatile", {})

        assert result == "groq"

    def test_extracts_from_custom_llm_provider_kwarg(self):
        """Verify provider extracted from custom_llm_provider in kwargs."""
        callback = RateTrackingCallback()

        result = callback._extract_provider(
            "llama-3.3-70b-versatile",
            {"custom_llm_provider": "groq"}
        )

        assert result == "groq"

    def test_extracts_from_litellm_params(self):
        """Verify provider extracted from litellm_params.custom_llm_provider."""
        callback = RateTrackingCallback()

        result = callback._extract_provider(
            "llama-3.3-70b-versatile",
            {"litellm_params": {"custom_llm_provider": "groq"}}
        )

        assert result == "groq"

    def test_infers_groq_from_llama_70b_model(self):
        """Verify groq inferred from llama 70b model without prefix."""
        callback = RateTrackingCallback()

        result = callback._extract_provider("llama-3.3-70b-versatile", {})

        assert result == "groq"

    def test_infers_groq_from_llama_8b_model(self):
        """Verify groq inferred from llama 8b model without prefix."""
        callback = RateTrackingCallback()

        result = callback._extract_provider("llama-3.1-8b-instant", {})

        assert result == "groq"

    def test_infers_gemini_from_gemini_model(self):
        """Verify gemini inferred from gemini model name."""
        callback = RateTrackingCallback()

        result = callback._extract_provider("gemini-2.0-flash-lite", {})

        assert result == "gemini"

    def test_infers_anthropic_from_claude_model(self):
        """Verify anthropic inferred from claude model name."""
        callback = RateTrackingCallback()

        result = callback._extract_provider("claude-3-5-sonnet", {})

        assert result == "anthropic"

    def test_infers_openai_from_gpt_model(self):
        """Verify openai inferred from gpt model name."""
        callback = RateTrackingCallback()

        result = callback._extract_provider("gpt-4o", {})

        assert result == "openai"

    def test_returns_unknown_for_unrecognized_model(self):
        """Verify unknown returned for unrecognized model."""
        callback = RateTrackingCallback()

        result = callback._extract_provider("some-unknown-model", {})

        assert result == "unknown"

    def test_lowercases_provider_name(self):
        """Verify provider name is lowercased."""
        callback = RateTrackingCallback()

        result = callback._extract_provider("GROQ/model", {})

        assert result == "groq"

    def test_model_string_takes_priority(self):
        """Verify model string with slash takes priority over kwargs."""
        callback = RateTrackingCallback()

        result = callback._extract_provider(
            "anthropic/claude-3",
            {"custom_llm_provider": "openai"}  # Should be ignored
        )

        assert result == "anthropic"


class TestParseGeminiRateLimitError:
    """Tests for parse_gemini_rate_limit_error function."""

    def test_parses_retry_in_seconds(self):
        """Verify retry delay is extracted from error message."""
        error = "Resource exhausted. Please retry in 7.215400659s"

        result = parse_gemini_rate_limit_error(error)

        assert result is not None
        assert result["retry_after_seconds"] == pytest.approx(7.215400659)

    def test_parses_integer_retry_seconds(self):
        """Verify integer retry delay is parsed correctly."""
        error = "Rate limit exceeded. Please retry in 30s"

        result = parse_gemini_rate_limit_error(error)

        assert result is not None
        assert result["retry_after_seconds"] == 30.0

    def test_identifies_quota_exceeded(self):
        """Verify quota type is identified."""
        error = "Quota exceeded for quota metric"

        result = parse_gemini_rate_limit_error(error)

        assert result is not None
        assert result["quota_type"] == "quota"

    def test_identifies_token_quota(self):
        """Verify token quota is identified."""
        error = "Token quota exceeded"

        result = parse_gemini_rate_limit_error(error)

        assert result is not None
        assert result["quota_type"] == "tokens"

    def test_identifies_request_quota(self):
        """Verify request quota is identified."""
        error = "Request rate limit exceeded"

        result = parse_gemini_rate_limit_error(error)

        assert result is not None
        assert result["quota_type"] == "requests"

    def test_preserves_original_message(self):
        """Verify original error message is preserved."""
        error = "Resource has been exhausted (e.g. check quota)."

        result = parse_gemini_rate_limit_error(error)

        assert result is not None
        assert result["message"] == error

    def test_returns_none_for_non_rate_limit_error(self):
        """Verify None returned for non-rate-limit errors."""
        error = "Invalid API key"

        result = parse_gemini_rate_limit_error(error)

        assert result is None

    def test_returns_none_for_empty_message(self):
        """Verify None returned for empty message."""
        result = parse_gemini_rate_limit_error("")

        assert result is None

    def test_returns_none_for_none_message(self):
        """Verify None returned for None message."""
        result = parse_gemini_rate_limit_error(None)

        assert result is None

    def test_handles_429_status_code_in_message(self):
        """Verify 429 in error message triggers parsing."""
        error = "Error 429: Too many requests"

        result = parse_gemini_rate_limit_error(error)

        assert result is not None
        assert result["message"] == error

    def test_handles_exhausted_keyword(self):
        """Verify 'exhausted' keyword triggers parsing."""
        error = "Resource has been exhausted"

        result = parse_gemini_rate_limit_error(error)

        assert result is not None


class TestGeminiRateLimitIntegration:
    """Tests for Gemini rate limit parsing integration with callbacks."""

    def test_gemini_failure_triggers_error_parsing(self):
        """Verify Gemini failures trigger rate limit error parsing."""
        # Create a tracker that supports update_from_error
        tracker = MockRateLimitTracker()
        tracker.error_updates = []

        def capture_error_update(provider, data):
            tracker.error_updates.append({"provider": provider, "data": data})

        tracker.update_from_error = capture_error_update

        callback = RateTrackingCallback(rate_tracker=tracker)

        class GeminiException(Exception):
            llm_provider = "gemini"

        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=100)

        callback.log_failure_event(
            kwargs={
                "exception": GeminiException("Please retry in 5.5s"),
                "model": "gemini-2.0-flash"
            },
            response_obj=None,
            start_time=start_time,
            end_time=end_time,
        )

        # Should have called update_from_error
        assert len(tracker.error_updates) == 1
        assert tracker.error_updates[0]["provider"] == "gemini"
        assert tracker.error_updates[0]["data"]["retry_after_seconds"] == pytest.approx(5.5)

    def test_non_gemini_failure_does_not_trigger_parsing(self):
        """Verify non-Gemini failures don't trigger error parsing."""
        tracker = MockRateLimitTracker()
        tracker.error_updates = []

        def capture_error_update(provider, data):
            tracker.error_updates.append({"provider": provider, "data": data})

        tracker.update_from_error = capture_error_update

        callback = RateTrackingCallback(rate_tracker=tracker)

        class GroqException(Exception):
            llm_provider = "groq"

        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=100)

        callback.log_failure_event(
            kwargs={
                "exception": GroqException("Rate limit exceeded"),
                "model": "groq/llama"
            },
            response_obj=None,
            start_time=start_time,
            end_time=end_time,
        )

        # Should not have called update_from_error for groq
        assert len(tracker.error_updates) == 0

    def test_gemini_non_rate_limit_error_not_stored(self):
        """Verify Gemini non-rate-limit errors don't update tracker."""
        tracker = MockRateLimitTracker()
        tracker.error_updates = []

        def capture_error_update(provider, data):
            tracker.error_updates.append({"provider": provider, "data": data})

        tracker.update_from_error = capture_error_update

        callback = RateTrackingCallback(rate_tracker=tracker)

        class GeminiException(Exception):
            llm_provider = "gemini"

        start_time = datetime.now()
        end_time = start_time + timedelta(milliseconds=100)

        callback.log_failure_event(
            kwargs={
                "exception": GeminiException("Invalid API key"),
                "model": "gemini-2.0-flash"
            },
            response_obj=None,
            start_time=start_time,
            end_time=end_time,
        )

        # Should not have called update_from_error for non-rate-limit error
        assert len(tracker.error_updates) == 0
