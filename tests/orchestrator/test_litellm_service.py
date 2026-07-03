"""
Tests for LiteLLMService.

Tests response conversion, exception mapping, and completion flow.
Uses test doubles from tests/helpers.py to avoid real API calls.
"""

import pytest
from unittest.mock import Mock

from scrappy.orchestrator.litellm_service import (
    LiteLLMService,
    _extract_retry_after,
    _map_litellm_error,
    _map_rate_limit_error,
)
from scrappy.orchestrator.fallback_metrics import provider_fallback_metrics
from scrappy.infrastructure.exceptions.failure_kinds import FailureKind
from scrappy.infrastructure.exceptions.provider_errors import (
    AllProvidersRateLimitedError,
    RouterGroupExhaustedError,
    RateLimitError as ProviderRateLimitError,
    ProviderExecutionError,
)

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
        assert response.latency_ms >= 0  # May be 0 on fast systems with mocks

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

    def test_extracts_tool_calls_from_malformed_content(self):
        """Verify tool calls in content field (malformed format) are extracted.

        Some providers return tool calls in the content field as a dict
        instead of the standard tool_calls array. This is malformed but
        we handle it gracefully.
        """
        # Create response with tool call in content field (malformed)
        mock_response = MockLiteLLMResponse(content="")
        # Simulate malformed response: content is dict, tool_calls is None
        mock_response.choices[0].message.content = {
            "name": "write_file",
            "arguments": {"path": "test.txt", "content": "hello"}
        }
        mock_response.choices[0].message.tool_calls = None

        mock_router = MockLiteLLMRouter(response=mock_response)
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        response, task_record = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "Write a file"}]
        )

        # Tool call should be extracted from malformed content
        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "write_file"
        assert response.tool_calls[0].arguments == {"path": "test.txt", "content": "hello"}
        # Content should be normalized to empty string
        assert response.content == ""

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
        assert task_record["latency_ms"] >= 0  # May be 0 on fast systems with mocks

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
        assert exc_info.value.failure_kind == FailureKind.EXHAUSTED

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

    def test_direct_model_rate_limit_maps_to_single_model_error(self, monkeypatch):
        """A direct concrete-model 429 is not router-group exhaustion."""
        import litellm

        mock_error = make_rate_limit_error(provider="groq")

        def raise_rate_limit(*args, **kwargs):
            raise mock_error

        monkeypatch.setattr(litellm, "completion", raise_rate_limit)
        service = make_configured_service(
            router=MockLiteLLMRouter(),
            output=MockOutputForLiteLLM(),
        )

        with pytest.raises(ProviderRateLimitError) as exc_info:
            service.completion_direct(
                model="groq/llama-3.1-8b-instant",
                messages=[{"role": "user", "content": "test"}],
            )

        assert exc_info.value.failure_kind == FailureKind.RATE_LIMIT
        assert exc_info.value.provider_name == "groq"

    def test_unknown_group_name_classified_as_concrete_and_warns(self, caplog):
        """A malformed group-like name is treated as one concrete model failure."""
        mock_error = make_rate_limit_error(provider="groq")

        with caplog.at_level("WARNING"):
            mapped = _map_rate_limit_error(mock_error, provider="", model="fasst")

        assert isinstance(mapped, ProviderRateLimitError)
        assert not isinstance(mapped, RouterGroupExhaustedError)
        assert "fasst" in caplog.text

    def test_router_group_name_produces_router_exhaustion(self):
        """A known router group preserves router-exhaustion semantics."""
        mock_error = make_rate_limit_error(provider="groq")

        mapped = _map_rate_limit_error(
            mock_error,
            provider="groq",
            model="fast",
        )

        assert isinstance(mapped, RouterGroupExhaustedError)
        assert mapped.failure_kind == FailureKind.EXHAUSTED

    def test_retry_after_http_date_header_uses_injected_clock(self):
        """Retry-After HTTP-date is parsed into deterministic seconds."""
        import httpx

        error = Exception("rate")
        error.response = httpx.Response(
            status_code=429,
            headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"},
        )

        result = _extract_retry_after(error, now=lambda: 1445412470.0)

        assert result == 10.0

    @pytest.mark.parametrize(
        ("message", "kind"),
        [
            ("401 unauthorized", FailureKind.AUTH),
            ("402 payment required", FailureKind.PAYMENT_REQUIRED),
            ("429 rate limit exceeded", FailureKind.RATE_LIMIT),
            ("connection refused", FailureKind.NETWORK),
            ("request timed out", FailureKind.TIMEOUT),
            ("content blocked by safety filters", FailureKind.CONTENT_REFUSED),
            ("model not found", FailureKind.DEPRECATED),
            ("503 service unavailable", FailureKind.SERVER_ERROR),
            ("400 bad request", FailureKind.UNKNOWN),
            ("totally weird provider failure", FailureKind.UNKNOWN),
        ],
    )
    def test_map_litellm_error_assigns_failure_kind(self, message, kind):
        """Every classifier branch assigns a concrete failure kind."""
        mapped = _map_litellm_error(
            Exception(message),
            provider="groq",
            model="groq/llama-3.1-8b-instant",
        )

        assert mapped.failure_kind == kind
        if kind == FailureKind.UNKNOWN:
            assert isinstance(mapped, ProviderExecutionError)

    def test_unknown_classification_increments_labeled_counter(self):
        """UNKNOWN failures are visible by provider and source error type."""
        provider_fallback_metrics.reset()

        mapped = _map_litellm_error(
            ValueError("totally weird provider failure"),
            provider="groq",
            model="groq/llama-3.1-8b-instant",
        )

        snapshot = provider_fallback_metrics.snapshot()
        assert mapped.failure_kind == FailureKind.UNKNOWN
        assert snapshot.provider_failure_unknown_total[
            ("groq", "ValueError")
        ] == 1

    def test_bad_request_unknown_classification_warns_and_counts(self, caplog):
        """Bad-request UNKNOWN failures have both log and counter signals."""
        provider_fallback_metrics.reset()

        with caplog.at_level("WARNING"):
            mapped = _map_litellm_error(
                ValueError("400 bad request"),
                provider="groq",
                model="groq/llama-3.1-8b-instant",
            )

        snapshot = provider_fallback_metrics.snapshot()
        assert mapped.failure_kind == FailureKind.UNKNOWN
        assert snapshot.provider_failure_unknown_total[
            ("groq", "ValueError")
        ] == 1
        assert "Unknown LiteLLM error classification" in caplog.text
        assert "400 bad request" in caplog.text


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


class TestParseToolArguments:
    """Tests for _parse_tool_arguments method - handles various argument formats."""

    def test_handles_dict_arguments(self):
        """Already-parsed dict should be returned as-is."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        result = service._parse_tool_arguments({"path": "test.py", "content": "code"})
        assert result == {"path": "test.py", "content": "code"}

    def test_handles_json_string_arguments(self):
        """JSON string should be parsed correctly."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        result = service._parse_tool_arguments('{"path": "test.py", "content": "code"}')
        assert result == {"path": "test.py", "content": "code"}

    def test_handles_markdown_wrapped_json(self):
        """JSON wrapped in ```json code fences should be extracted."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        markdown_json = '```json\n{"path": "test.py", "content": "code"}\n```'
        result = service._parse_tool_arguments(markdown_json)
        assert result == {"path": "test.py", "content": "code"}

    def test_handles_truncated_markdown_json(self):
        """Truncated markdown (no closing ```) should still parse."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        truncated = '```json\n{"path": "test.py", "content": "code"}'
        result = service._parse_tool_arguments(truncated)
        assert result == {"path": "test.py", "content": "code"}

    def test_handles_generic_code_fence(self):
        """Generic ``` code fence should be handled."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        generic_fence = '```\n{"path": "test.py", "content": "code"}\n```'
        result = service._parse_tool_arguments(generic_fence)
        assert result == {"path": "test.py", "content": "code"}

    def test_returns_empty_dict_on_invalid_json(self):
        """Invalid JSON should return empty dict."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        result = service._parse_tool_arguments("not valid json")
        assert result == {}

    def test_returns_empty_dict_on_empty_string(self):
        """Empty string should return empty dict."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        result = service._parse_tool_arguments("")
        assert result == {}

    def test_logs_warning_on_parse_failure(self):
        """Should log warning when parsing fails."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()

        # Create mock logger
        mock_logger = Mock()
        service = make_configured_service(router=mock_router, output=mock_output)
        service._logger = mock_logger

        service._parse_tool_arguments("invalid json", tool_name="write_file")

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0][0]
        assert "write_file" in call_args
        assert "failed to parse" in call_args


class TestExtractXmlToolCalls:
    """Tests for _extract_xml_tool_calls method - handles XML-style tool calls in content."""

    def test_extracts_single_xml_tool_call(self):
        """Single XML-style tool call should be extracted."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        content = '<write_file>{"path": "test.py", "content": "code"}</write_file>'
        result = service._extract_xml_tool_calls(content)

        assert result is not None
        assert len(result) == 1
        assert result[0].name == "write_file"
        assert result[0].arguments == {"path": "test.py", "content": "code"}

    def test_extracts_multiple_xml_tool_calls(self):
        """Multiple XML-style tool calls should all be extracted."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        content = '''<write_file>{"path": "a.py", "content": "foo"}</write_file>
<run_command>{"command": "python a.py"}</run_command>'''
        result = service._extract_xml_tool_calls(content)

        assert result is not None
        assert len(result) == 2
        assert result[0].name == "write_file"
        assert result[1].name == "run_command"

    def test_handles_multiline_json(self):
        """XML tool calls with multiline JSON should parse correctly."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        content = '''<write_file>{
    "path": "test.py",
    "content": "def hello():\\n    print('hi')"
}</write_file>'''
        result = service._extract_xml_tool_calls(content)

        assert result is not None
        assert len(result) == 1
        assert result[0].arguments["path"] == "test.py"

    def test_returns_none_for_no_matches(self):
        """Content without XML tool calls should return None."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        content = "Just regular text without any tool calls"
        result = service._extract_xml_tool_calls(content)

        assert result is None

    def test_returns_none_for_malformed_xml(self):
        """Malformed XML (mismatched tags) should not match."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        content = '<write_file>{"path": "test.py"}</read_file>'
        result = service._extract_xml_tool_calls(content)

        assert result is None

    def test_handles_escaped_json_in_content(self):
        """JSON with escaped characters should parse correctly."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        content = '<write_file>{"path": "test.py", "content": "print(\\"hello\\")"}</write_file>'
        result = service._extract_xml_tool_calls(content)

        assert result is not None
        assert result[0].arguments["content"] == 'print("hello")'


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


class TestModeSelection:
    """Tests for _pick_mode method - selects Instructor mode based on model."""

    def test_picks_tools_mode_for_gpt_models(self):
        """GPT models should use TOOLS mode."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        import instructor
        assert service._pick_mode("gpt-4") == instructor.Mode.TOOLS
        assert service._pick_mode("gpt-3.5-turbo") == instructor.Mode.TOOLS
        assert service._pick_mode("openai/gpt-4-turbo") == instructor.Mode.TOOLS

    def test_picks_tools_mode_for_claude_models(self):
        """Claude models should use TOOLS mode."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        import instructor
        assert service._pick_mode("claude-3-opus") == instructor.Mode.TOOLS
        assert service._pick_mode("anthropic/claude-3-haiku") == instructor.Mode.TOOLS

    def test_picks_tools_mode_for_cohere_models(self):
        """Cohere command-r models should use TOOLS mode."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        import instructor
        assert service._pick_mode("command-r") == instructor.Mode.TOOLS
        assert service._pick_mode("cohere/command-r-plus") == instructor.Mode.TOOLS

    def test_picks_json_mode_for_other_models(self):
        """Other models should use JSON mode."""
        mock_router = MockLiteLLMRouter(response=make_mock_litellm_response())
        mock_output = MockOutputForLiteLLM()
        service = make_configured_service(router=mock_router, output=mock_output)

        import instructor
        assert service._pick_mode("groq/llama-3.1-8b") == instructor.Mode.JSON
        assert service._pick_mode("cerebras/llama-3.3-70b") == instructor.Mode.JSON
        assert service._pick_mode("together/mistral-7b") == instructor.Mode.JSON


class TestStructuredOutput:
    """Tests for completion_structured and completion_structured_sync methods."""

    def test_instructor_default_retries_is_one(self):
        """Verify DEFAULT_INSTRUCTOR_RETRIES is set to 1."""
        from scrappy.orchestrator.litellm_service import DEFAULT_INSTRUCTOR_RETRIES
        assert DEFAULT_INSTRUCTOR_RETRIES == 1


class FakeAsyncHTTPClient:
    """Stands in for the httpx AsyncClient litellm keeps as aclient_session."""

    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


class FakeAiohttpSession:
    """Stands in for the aiohttp ClientSession litellm keeps as _client_session."""

    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class TestClose:
    """Behavior tests for close(): async HTTP sessions must actually close.

    Regression for scrappy-odbo: close() called helper methods that did not
    exist, the resulting AttributeError was swallowed by the app-level
    except, and async session cleanup silently never ran.
    """

    @pytest.fixture
    def litellm_module(self):
        """Expose the litellm module with session attributes saved/restored."""
        import litellm

        saved = {
            attr: getattr(litellm, attr, None)
            for attr in ("client_session", "aclient_session", "_client_session")
        }
        yield litellm
        for attr, value in saved.items():
            setattr(litellm, attr, value)

    @pytest.fixture
    def owned_event_loop(self):
        """Provide a fresh event loop installed as the current one."""
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        yield loop
        if not loop.is_closed():
            loop.close()
        asyncio.set_event_loop(None)

    def test_close_awaits_async_session_closes(self, litellm_module, owned_event_loop):
        """With a usable loop, close() must await both async session closes."""
        litellm_module.client_session = None
        async_client = FakeAsyncHTTPClient()
        aiohttp_session = FakeAiohttpSession()
        litellm_module.aclient_session = async_client
        litellm_module._client_session = aiohttp_session

        service = make_configured_service(
            router=MockLiteLLMRouter(), output=MockOutputForLiteLLM()
        )
        service.close()

        assert async_client.closed is True
        assert aiohttp_session.closed is True
        assert litellm_module.aclient_session is None
        assert litellm_module._client_session is None

    def test_close_with_closed_loop_clears_references_without_error(
        self, litellm_module, owned_event_loop
    ):
        """With no usable loop, close() clears references and lets GC clean up.

        It must not raise and must not create coroutines it cannot await
        (those trigger 'coroutine was never awaited' warnings).
        """
        import warnings

        litellm_module.client_session = None
        async_client = FakeAsyncHTTPClient()
        litellm_module.aclient_session = async_client
        litellm_module._client_session = None

        owned_event_loop.close()

        service = make_configured_service(
            router=MockLiteLLMRouter(), output=MockOutputForLiteLLM()
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            service.close()

        assert litellm_module.aclient_session is None
        assert async_client.closed is False
