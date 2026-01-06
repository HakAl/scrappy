"""
Tests for LiteLLM context window escalation behavior.

Tests that ContextWindowExceededError triggers proper escalation from
fast -> quality tier with depth guards and metrics tracking.
"""

import pytest
from unittest.mock import Mock

from scrappy.orchestrator.litellm_service import LiteLLMService, MAX_ESCALATION_DEPTH
from scrappy.orchestrator.litellm_callbacks import RateTrackingCallback, EscalationMetrics

from tests.helpers import (
    MockLiteLLMRouter,
    MockOutputForLiteLLM,
    MockApiKeyService,
    make_mock_litellm_response,
)


def make_context_window_error(message: str = "too long", model: str = "fast"):
    """Create a mock ContextWindowExceededError."""
    from litellm import ContextWindowExceededError

    return ContextWindowExceededError(
        message=message,
        model=model,
        llm_provider="groq"
    )


def make_configured_service(router, output, callback=None):
    """Create a LiteLLMService that is pre-configured for testing."""
    api_key_service = MockApiKeyService(keys={"GROQ_API_KEY": "test-key"})
    service = LiteLLMService(
        router=router,
        api_key_service=api_key_service,
        output=output,
        callback=callback,
    )
    # Mark as configured to bypass NotConfiguredError
    service._configured = True
    return service


class TestEscalationDepthGuard:
    """Tests for recursion safety in context window escalation."""

    def test_max_escalation_depth_raises_runtime_error_sync(self):
        """Verify sync method raises RuntimeError when max depth exceeded."""
        mock_router = MockLiteLLMRouter(
            response=make_mock_litellm_response()
        )
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        # Directly call with depth at limit
        with pytest.raises(RuntimeError) as exc_info:
            service.completion_sync(
                model="quality",
                messages=[{"role": "user", "content": "test"}],
                _escalation_depth=MAX_ESCALATION_DEPTH,
            )

        assert "Max escalation depth" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_max_escalation_depth_raises_runtime_error_async(self):
        """Verify async method raises RuntimeError when max depth exceeded."""
        mock_router = MockLiteLLMRouter(
            response=make_mock_litellm_response()
        )
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        with pytest.raises(RuntimeError) as exc_info:
            await service.completion(
                model="quality",
                messages=[{"role": "user", "content": "test"}],
                _escalation_depth=MAX_ESCALATION_DEPTH,
            )

        assert "Max escalation depth" in str(exc_info.value)




class TestEscalationMetrics:
    """Tests for escalation metrics tracking."""

    def test_escalation_metrics_records_event(self):
        """Verify EscalationMetrics correctly records escalation."""
        metrics = EscalationMetrics()

        metrics.record_escalation("fast", "chat")
        metrics.record_escalation("fast", "chat")

        summary = metrics.get_summary()
        assert summary["total_escalations"] == 2
        assert summary["by_path"]["fast->chat"] == 2

    def test_callback_record_escalation_updates_metrics(self):
        """Verify callback properly updates escalation metrics."""
        callback = RateTrackingCallback()

        callback.record_escalation("fast", "chat")

        assert callback.escalation_metrics.total_escalations == 1


class TestEscalationMetadataInResponse:
    """Tests for escalation info in response/task_record."""

    def test_escalated_from_in_response_metadata(self):
        """Verify escalated_from appears in LLMResponse.metadata."""
        context_error = make_context_window_error()

        mock_router = MockLiteLLMRouter(
            responses=[
                context_error,
                make_mock_litellm_response(model="groq/llama-3.3-70b-versatile"),
            ]
        )
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        response, _ = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        )

        assert response.metadata.get("escalated_from") == "fast"

    def test_escalated_from_in_task_record(self):
        """Verify escalated_from appears in task_record."""
        context_error = make_context_window_error()

        mock_router = MockLiteLLMRouter(
            responses=[
                context_error,
                make_mock_litellm_response(model="groq/llama-3.3-70b-versatile"),
            ]
        )
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        _, task_record = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        )

        assert task_record["escalated_from"] == "fast"

    def test_no_escalation_no_metadata(self):
        """Verify escalated_from not in metadata when no escalation."""
        mock_router = MockLiteLLMRouter(
            response=make_mock_litellm_response(model="groq/llama-3.1-8b-instant")
        )
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        response, task_record = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        )

        assert "escalated_from" not in response.metadata
        assert task_record.get("escalated_from") is None


class TestEscalationWarningOutput:
    """Tests for warning output during escalation."""

    def test_escalation_outputs_warning(self):
        """Verify escalation outputs warning message."""
        context_error = make_context_window_error()

        mock_router = MockLiteLLMRouter(
            responses=[
                context_error,
                make_mock_litellm_response(model="groq/llama-3.3-70b-versatile"),
            ]
        )
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        )

        warnings = mock_output.get_warnings()
        assert len(warnings) == 1
        assert "Context window exceeded" in warnings[0]
        assert "fast" in warnings[0]
        assert "chat" in warnings[0]  # fast escalates to chat


class TestAsyncEscalation:
    """Tests for async escalation behavior."""

    @pytest.mark.asyncio
    async def test_async_escalation_works(self):
        """Verify async escalation handles context window errors."""
        context_error = make_context_window_error()

        mock_router = MockLiteLLMRouter(
            responses=[
                context_error,
                make_mock_litellm_response(model="groq/llama-3.3-70b-versatile"),
            ]
        )
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        response, task_record = await service.completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        )

        assert response.metadata.get("escalated_from") == "fast"
        assert task_record["escalated_from"] == "fast"

    @pytest.mark.asyncio
    async def test_async_escalation_records_callback(self):
        """Verify async escalation records to callback."""
        context_error = make_context_window_error()

        mock_router = MockLiteLLMRouter(
            responses=[
                context_error,
                make_mock_litellm_response(model="groq/llama-3.3-70b-versatile"),
            ]
        )
        mock_output = MockOutputForLiteLLM()
        mock_callback = Mock(spec=RateTrackingCallback)

        service = make_configured_service(
            router=mock_router, output=mock_output, callback=mock_callback
        )

        await service.completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        )

        mock_callback.record_escalation.assert_called_once_with("fast", "chat")


class TestMultipleEscalationAttempts:
    """Tests for multiple escalation scenarios."""

    def test_escalation_uses_quality_tier_response(self):
        """Verify escalation returns quality tier response."""
        context_error = make_context_window_error()

        mock_router = MockLiteLLMRouter(
            responses=[
                context_error,
                make_mock_litellm_response(
                    content="Quality response",
                    model="gemini/gemini-2.5-flash"
                ),
            ]
        )
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        response, _ = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        )

        assert response.content == "Quality response"
        assert response.model == "gemini/gemini-2.5-flash"
        assert response.provider == "gemini"

