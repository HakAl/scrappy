"""
Tests for LiteLLMService.

Tests response conversion, exception mapping, and completion flow.
Uses test doubles from tests/helpers.py to avoid real API calls.
"""

import pytest
from unittest.mock import Mock, AsyncMock

from scrappy.orchestrator.litellm_service import LiteLLMService, MAX_ESCALATION_DEPTH
from scrappy.infrastructure.exceptions.provider_errors import AllProvidersRateLimitedError

from tests.helpers import (
    MockLiteLLMRouter,
    MockLiteLLMResponse,
    MockOutputForLiteLLM,
    MockApiKeyService,
    make_mock_litellm_response,
    make_mock_tool_call,
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


class TestResponseConversion:
    """Tests for _convert_response method."""

    def test_converts_standard_response(self):
        """Verify content, tokens, and latency are correctly extracted."""
        mock_router = MockLiteLLMRouter(
            response=make_mock_litellm_response(
                content="Hello, world!",
                model="groq/llama-3.1-8b-instant",
                prompt_tokens=15,
                completion_tokens=25,
            )
        )
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        response, task_record = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "Hi"}]
        )

        assert response.content == "Hello, world!"
        assert response.model == "groq/llama-3.1-8b-instant"
        assert response.input_tokens == 15
        assert response.output_tokens == 25
        assert response.tokens_used == 40
        assert response.latency_ms > 0

    def test_extracts_provider_from_model_string(self):
        """Verify 'cerebras/llama-3.3-70b' -> provider='cerebras'."""
        mock_router = MockLiteLLMRouter(
            response=make_mock_litellm_response(model="cerebras/llama-3.3-70b")
        )
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        response, task_record = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}]
        )

        assert response.provider == "cerebras"
        assert task_record["provider"] == "cerebras"

    def test_handles_missing_usage_gracefully(self):
        """Verify usage=None doesn't crash."""
        # Create response with no usage
        mock_response = MockLiteLLMResponse(content="test")
        mock_response.usage = None

        mock_router = MockLiteLLMRouter(response=mock_response)
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        response, task_record = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}]
        )

        assert response.tokens_used == 0
        assert response.input_tokens == 0
        assert response.output_tokens == 0

    def test_extracts_tool_calls_when_present(self):
        """Verify tool calls are extracted from response."""
        tool_call = make_mock_tool_call(
            id="call_abc123",
            name="get_weather",
            arguments={"location": "NYC"}
        )
        mock_router = MockLiteLLMRouter(
            response=make_mock_litellm_response(
                content="",
                tool_calls=[tool_call]
            )
        )
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        response, task_record = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "What's the weather?"}]
        )

        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].id == "call_abc123"
        assert response.tool_calls[0].name == "get_weather"
        assert response.tool_calls[0].arguments == {"location": "NYC"}

    def test_returns_task_record_with_metadata(self):
        """Verify task_record contains provider, model, tokens, latency."""
        mock_router = MockLiteLLMRouter(
            response=make_mock_litellm_response(
                model="groq/llama-3.1-8b-instant",
                prompt_tokens=10,
                completion_tokens=20,
            )
        )
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        response, task_record = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}]
        )

        assert task_record["provider"] == "groq"
        assert task_record["model"] == "groq/llama-3.1-8b-instant"
        assert task_record["tokens_used"] == 30
        assert task_record["latency_ms"] > 0

    def test_returns_actual_model_used_not_group_name(self):
        """Ensure we record 'groq/llama-3...' not 'fast' in our logs."""
        mock_router = MockLiteLLMRouter(
            response=make_mock_litellm_response(model="groq/llama-3.1-8b-instant")
        )
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        # Request with model="fast" (group name)
        response, task_record = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}]
        )

        # Critical: Use the model from the RESPONSE, not the REQUEST
        assert response.model == "groq/llama-3.1-8b-instant"
        assert task_record["model"] == "groq/llama-3.1-8b-instant"


def make_rate_limit_error(provider: str = "groq", message: str = "Rate limit exceeded"):
    """Create a mock RateLimitError for testing."""
    from litellm import RateLimitError
    import httpx

    # Create a proper httpx.Response
    response = httpx.Response(
        status_code=429,
        headers={"x-ratelimit-remaining": "0"},
    )

    error = RateLimitError(
        message=message,
        llm_provider=provider,
        model=f"{provider}/llama",
        response=response
    )
    return error


class TestExceptionMapping:
    """Tests for exception handling and mapping."""

    def test_rate_limit_error_becomes_all_providers_exhausted(self):
        """Verify LiteLLM RateLimitError maps to AllProvidersRateLimitedError."""
        mock_error = make_rate_limit_error(provider="groq")

        mock_router = MockLiteLLMRouter(exception=mock_error)
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        with pytest.raises(AllProvidersRateLimitedError) as exc_info:
            service.completion_sync(
                model="fast",
                messages=[{"role": "user", "content": "test"}]
            )

        assert "groq" in exc_info.value.attempted_providers

    def test_preserves_llm_provider_in_exception(self):
        """Verify provider name is extracted from exception."""
        mock_error = make_rate_limit_error(provider="cerebras")

        mock_router = MockLiteLLMRouter(exception=mock_error)
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        with pytest.raises(AllProvidersRateLimitedError) as exc_info:
            service.completion_sync(
                model="fast",
                messages=[{"role": "user", "content": "test"}]
            )

        assert "cerebras" in exc_info.value.attempted_providers

    def test_handles_missing_llm_provider_attribute(self):
        """Verify graceful handling when exception lacks llm_provider."""
        # Create a custom exception without llm_provider
        class MockRateLimitError(Exception):
            pass

        # LiteLLM RateLimitError always has llm_provider, so we test
        # with a None provider instead
        from litellm import RateLimitError
        import httpx

        response = httpx.Response(
            status_code=429,
            headers={},
        )

        mock_error = RateLimitError(
            message="Rate limit exceeded",
            llm_provider=None,
            model="unknown",
            response=response
        )

        mock_router = MockLiteLLMRouter(exception=mock_error)
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        with pytest.raises(AllProvidersRateLimitedError) as exc_info:
            service.completion_sync(
                model="fast",
                messages=[{"role": "user", "content": "test"}]
            )

        # Should still raise without crashing
        assert exc_info.value.attempted_providers == []


class TestCompletionFlow:
    """Tests for completion execution flow."""

    def test_completion_calls_router_with_correct_params(self):
        """Verify completion passes model and messages to router."""
        mock_router = MockLiteLLMRouter(
            response=make_mock_litellm_response()
        )
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        messages = [{"role": "user", "content": "Hello"}]
        service.completion_sync(model="fast", messages=messages)

        assert len(mock_router.calls) == 1
        assert mock_router.calls[0]["model"] == "fast"
        assert mock_router.calls[0]["messages"] == messages

    def test_completion_sync_calls_router_completion(self):
        """Verify sync completion uses router.completion()."""
        mock_router = MockLiteLLMRouter(
            response=make_mock_litellm_response()
        )
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}]
        )

        assert len(mock_router.calls) == 1

    def test_passes_through_kwargs(self):
        """Verify max_tokens, temperature, tools pass through to router."""
        mock_router = MockLiteLLMRouter(
            response=make_mock_litellm_response()
        )
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=500,
            temperature=0.5,
            tools=[{"type": "function", "function": {"name": "test"}}],
            tool_choice="auto"
        )

        call = mock_router.calls[0]
        assert call["max_tokens"] == 500
        assert call["temperature"] == 0.5
        assert call["tools"] == [{"type": "function", "function": {"name": "test"}}]
        assert call["tool_choice"] == "auto"


class TestAsyncCompletion:
    """Tests for async completion method."""

    @pytest.mark.asyncio
    async def test_async_completion_returns_response(self):
        """Verify async completion works correctly."""
        mock_router = MockLiteLLMRouter(
            response=make_mock_litellm_response(content="Async response")
        )
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        response, task_record = await service.completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}]
        )

        assert response.content == "Async response"

    @pytest.mark.asyncio
    async def test_async_completion_handles_rate_limit(self):
        """Verify async completion handles rate limit errors."""
        mock_error = make_rate_limit_error(provider="groq")

        mock_router = MockLiteLLMRouter(exception=mock_error)
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        with pytest.raises(AllProvidersRateLimitedError):
            await service.completion(
                model="fast",
                messages=[{"role": "user", "content": "test"}]
            )


class TestHandleEmptyModelString:
    """Tests for edge cases with model string."""

    def test_handles_response_with_empty_model_string(self):
        """Verify empty model string is handled gracefully."""
        mock_response = MockLiteLLMResponse(content="test")
        mock_response.model = ""

        mock_router = MockLiteLLMRouter(response=mock_response)
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        response, task_record = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}]
        )

        assert response.provider == "unknown"
        assert task_record["provider"] == "unknown"

    def test_handles_model_without_slash(self):
        """Verify model without provider prefix is handled."""
        mock_response = MockLiteLLMResponse(content="test")
        mock_response.model = "llama-3.1-8b-instant"  # No provider prefix

        mock_router = MockLiteLLMRouter(response=mock_response)
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        response, task_record = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}]
        )

        assert response.provider == "unknown"
