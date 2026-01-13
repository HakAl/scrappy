"""
Tests for think delegator components.

Tests ThinkResult, DefaultThinkErrorHandler, MockThinkDelegator,
and LiteLLMThinkDelegator.
"""

import pytest

from scrappy.graph.protocols import ThinkResult
from scrappy.graph.state import ToolCall
from scrappy.graph.nodes.think_error_handler import DefaultThinkErrorHandler
from scrappy.graph.nodes.mock_think_delegator import (
    MockThinkDelegator,
    FailingThinkDelegator,
    SequenceThinkDelegator,
)
from scrappy.infrastructure.exceptions import (
    AuthenticationError,
    NetworkError,
    RateLimitError,
    RecoveryAction,
)
from scrappy.orchestrator.litellm_service import NotConfiguredError
from scrappy.orchestrator.types import StreamChunk


# =============================================================================
# ThinkResult Tests
# =============================================================================


class TestThinkResult:
    """Tests for ThinkResult dataclass."""

    def test_default_values(self):
        """Default ThinkResult is successful with empty content."""
        result = ThinkResult()
        assert result.content == ""
        assert result.tool_calls == ()
        assert result.model_display is None
        assert result.error is None
        assert result.is_success
        assert not result.is_done  # Empty content
        assert not result.has_tool_calls

    def test_successful_text_response(self):
        """Successful response with content is done."""
        result = ThinkResult(
            content="The answer is 42.",
            model_display="cerebras: llama-3.3-70b",
        )
        assert result.is_success
        assert result.is_done
        assert not result.has_tool_calls
        assert result.content == "The answer is 42."

    def test_successful_tool_call_response(self):
        """Response with tool calls is not done."""
        tool_call = ToolCall(
            type="function",
            id="call_123",
            function={"name": "search", "arguments": '{"q": "test"}'},
        )
        result = ThinkResult(
            content="I'll search for that.",
            tool_calls=(tool_call,),
            model_display="groq: llama-3.1-70b",
        )
        assert result.is_success
        assert not result.is_done  # Has tool calls
        assert result.has_tool_calls
        assert len(result.tool_calls) == 1

    def test_error_response(self):
        """Error response is not successful."""
        result = ThinkResult(
            error="Rate limit exceeded",
            recovery_action="fallback",
            error_category="rate_limit",
        )
        assert not result.is_success
        assert not result.is_done
        assert result.error == "Rate limit exceeded"
        assert result.recovery_action == "fallback"

    def test_fatal_error(self):
        """Fatal error has is_fatal flag."""
        result = ThinkResult(
            error="Authentication failed",
            recovery_action="abort",
            error_category="auth",
            is_fatal=True,
        )
        assert not result.is_success
        assert result.is_fatal

    def test_immutability(self):
        """ThinkResult is frozen/immutable."""
        result = ThinkResult(content="test")
        with pytest.raises(AttributeError):
            result.content = "modified"  # type: ignore

    def test_whitespace_only_content_not_done(self):
        """Response with only whitespace is not considered done."""
        result = ThinkResult(content="   \n\t  ")
        assert result.is_success
        assert not result.is_done  # Whitespace-only not done


# =============================================================================
# DefaultThinkErrorHandler Tests
# =============================================================================


class TestDefaultThinkErrorHandler:
    """Tests for DefaultThinkErrorHandler."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""
        return DefaultThinkErrorHandler()

    def test_not_configured_error(self, handler):
        """NotConfiguredError is fatal."""
        error = NotConfiguredError("No API keys")
        result = handler.handle(error)

        assert not result.is_success
        assert result.is_fatal
        assert "not configured" in result.error.lower()
        assert result.recovery_action == RecoveryAction.ABORT.value

    def test_authentication_error(self, handler):
        """AuthenticationError is fatal."""
        error = AuthenticationError(
            message="Invalid API key",
            provider_name="openai",
        )
        result = handler.handle(error)

        assert not result.is_success
        assert result.is_fatal
        assert "Invalid API key" in result.error
        assert result.error_category == "authentication"  # Full enum value

    def test_rate_limit_error(self, handler):
        """RateLimitError triggers retry (inherits from RetryableError)."""
        error = RateLimitError(
            message="Rate limit exceeded",
            provider_name="groq",
        )
        result = handler.handle(error)

        assert not result.is_success
        assert not result.is_fatal
        # RateLimitError inherits from RetryableError, so recovery_action is RETRY
        # The delegator's fallback logic handles getting alternate models
        assert result.recovery_action == RecoveryAction.RETRY.value
        assert result.error_category == "rate_limit"

    def test_network_error(self, handler):
        """NetworkError triggers retry, not fatal."""
        # NetworkError doesn't take provider_name in __init__
        error = NetworkError(message="Connection timeout")
        result = handler.handle(error)

        assert not result.is_success
        assert not result.is_fatal
        assert result.recovery_action == RecoveryAction.RETRY.value
        assert result.error_category == "network"

    def test_connection_error_stdlib(self, handler):
        """Standard ConnectionError triggers retry."""
        error = ConnectionError("Connection refused")
        result = handler.handle(error)

        assert not result.is_success
        assert not result.is_fatal
        assert result.recovery_action == RecoveryAction.RETRY.value
        assert result.error_category == "network"

    def test_value_error_parsing(self, handler):
        """ValueError (parsing) triggers retry."""
        error = ValueError("Invalid JSON response")
        result = handler.handle(error)

        assert not result.is_success
        assert not result.is_fatal
        assert result.recovery_action == RecoveryAction.RETRY.value
        assert result.error_category == "parse"

    def test_unexpected_error(self, handler):
        """Unknown errors are fatal with abort."""
        error = RuntimeError("Something unexpected")
        result = handler.handle(error)

        assert not result.is_success
        assert result.is_fatal
        assert result.recovery_action == RecoveryAction.ABORT.value
        assert result.error_category == "system"


# =============================================================================
# MockThinkDelegator Tests
# =============================================================================


class TestMockThinkDelegator:
    """Tests for MockThinkDelegator."""

    def test_returns_scripted_responses_in_order(self):
        """Mock returns responses in order."""
        responses = [
            ThinkResult(content="First"),
            ThinkResult(content="Second"),
            ThinkResult(content="Third"),
        ]
        delegator = MockThinkDelegator(responses)

        assert delegator.complete([], None, None, "instruct").content == "First"
        assert delegator.complete([], None, None, "instruct").content == "Second"
        assert delegator.complete([], None, None, "instruct").content == "Third"

    def test_returns_default_after_exhausted(self):
        """Mock returns default after scripted responses exhausted."""
        responses = [ThinkResult(content="Only one")]
        default = ThinkResult(content="Default")
        delegator = MockThinkDelegator(responses, default)

        assert delegator.complete([], None, None, "instruct").content == "Only one"
        assert delegator.complete([], None, None, "instruct").content == "Default"
        assert delegator.complete([], None, None, "instruct").content == "Default"

    def test_tracks_call_count(self):
        """Mock tracks number of calls."""
        delegator = MockThinkDelegator()
        assert delegator.call_count == 0

        delegator.complete([], None, None, "instruct")
        assert delegator.call_count == 1

        delegator.complete([], None, None, "instruct")
        assert delegator.call_count == 2

    def test_records_last_call_details(self):
        """Mock records details of last call."""
        delegator = MockThinkDelegator()

        messages = [{"role": "user", "content": "Hello"}]
        tools = [{"type": "function", "function": {"name": "test"}}]

        delegator.complete(messages, tools, None, "chat")

        assert delegator.last_messages == messages
        assert delegator.last_tools == tools
        assert delegator.last_tier == "chat"

    @pytest.mark.asyncio
    async def test_streaming_calls_on_chunk(self):
        """Streaming mode calls on_chunk callback."""
        delegator = MockThinkDelegator([
            ThinkResult(content="Hello world test")
        ])

        chunks: list[str] = []
        result = await delegator.complete_streaming(
            [], None, None, "instruct",
            on_chunk=chunks.append
        )

        assert result.content == "Hello world test"
        assert len(chunks) == 3  # "Hello ", "world ", "test"
        assert "".join(chunks) == "Hello world test"


class TestFailingThinkDelegator:
    """Tests for FailingThinkDelegator."""

    def test_raises_configured_error(self):
        """Delegator raises the configured error."""
        error = ValueError("Test error")
        delegator = FailingThinkDelegator(error)

        with pytest.raises(ValueError, match="Test error"):
            delegator.complete([], None, None, "instruct")

    def test_tracks_call_count_before_failure(self):
        """Tracks call count even when failing."""
        delegator = FailingThinkDelegator(ValueError("fail"))

        for _ in range(3):
            try:
                delegator.complete([], None, None, "instruct")
            except ValueError:
                pass

        assert delegator.call_count == 3


class TestSequenceThinkDelegator:
    """Tests for SequenceThinkDelegator."""

    def test_returns_response_based_on_content_match(self):
        """Returns response when message content matches pattern."""
        delegator = SequenceThinkDelegator()
        delegator.when_messages_contain("search", ThinkResult(content="Search result"))
        # Use lowercase to match the pattern (case-sensitive matching)
        delegator.when_messages_contain("calculate", ThinkResult(content="Calculation result"))

        messages_search = [{"role": "user", "content": "Please search for info"}]
        # Use lowercase "calculate" to match the pattern
        messages_calc = [{"role": "user", "content": "Please calculate 2+2"}]

        assert delegator.complete(messages_search, None, None, "instruct").content == "Search result"
        assert delegator.complete(messages_calc, None, None, "instruct").content == "Calculation result"

    def test_returns_default_when_no_match(self):
        """Returns default when no pattern matches."""
        delegator = SequenceThinkDelegator()
        delegator.when_messages_contain("search", ThinkResult(content="Search"))
        delegator.set_default(ThinkResult(content="No match"))

        messages = [{"role": "user", "content": "Hello"}]
        assert delegator.complete(messages, None, None, "instruct").content == "No match"

    def test_records_call_history(self):
        """Records all calls in history."""
        delegator = SequenceThinkDelegator()

        delegator.complete([{"role": "user", "content": "First"}], None, None, "fast")
        delegator.complete([{"role": "user", "content": "Second"}], None, None, "chat")

        assert len(delegator.call_history) == 2
        assert delegator.call_history[0]["tier"] == "fast"
        assert delegator.call_history[1]["tier"] == "chat"


# =============================================================================
# LiteLLMThinkDelegator Tests (with mocked LLMService)
# =============================================================================


class MockLLMService:
    """Mock LLM service for testing LiteLLMThinkDelegator."""

    def __init__(self, chunks: list = None, error: Exception = None):
        self._chunks = chunks or []
        self._error = error
        self.call_count = 0
        self.last_model = None
        self.last_messages = None

    def stream_completion_sync(self, model, messages, **kwargs):
        self.call_count += 1
        self.last_model = model
        self.last_messages = messages

        if self._error:
            raise self._error

        return iter(self._chunks)

    def stream_completion_direct(self, model, messages, **kwargs):
        return self.stream_completion_sync(model, messages, **kwargs)


def make_chunk(content="", model="", provider="", tool_call_fragments=None):
    """Create a real StreamChunk for testing."""
    return StreamChunk(
        content=content,
        model=model,
        provider=provider,
        tool_call_fragments=tool_call_fragments or [],
    )


class TestLiteLLMThinkDelegator:
    """Tests for LiteLLMThinkDelegator with mocked dependencies."""

    def test_complete_returns_content(self):
        """Basic completion returns content."""
        from scrappy.graph.nodes.think_delegator import LiteLLMThinkDelegator

        chunks = [
            make_chunk(content="Hello "),
            make_chunk(content="world", model="test-model", provider="test"),
        ]
        llm_service = MockLLMService(chunks=chunks)

        delegator = LiteLLMThinkDelegator(llm_service)
        result = delegator.complete(
            messages=[{"role": "user", "content": "Hi"}],
            tools=None,
            run_context=None,
            current_tier="instruct",
        )

        assert result.is_success
        assert result.content == "Hello world"
        assert result.model_display == "test: test-model"

    def test_complete_with_error_uses_handler(self):
        """Errors are handled by error handler."""
        from scrappy.graph.nodes.think_delegator import LiteLLMThinkDelegator

        error = RateLimitError("Rate limited", provider_name="test")
        llm_service = MockLLMService(error=error)

        delegator = LiteLLMThinkDelegator(llm_service)
        result = delegator.complete(
            messages=[{"role": "user", "content": "Hi"}],
            tools=None,
            run_context=None,
            current_tier="instruct",
        )

        # Should return error result (retries exhaust since same error every time)
        assert not result.is_success
        assert result.is_fatal  # Max retries exhausted

    def test_complete_empty_response_returns_error(self):
        """Empty response is treated as error."""
        from scrappy.graph.nodes.think_delegator import LiteLLMThinkDelegator

        # Empty chunks
        chunks = [make_chunk(content="", model="test", provider="test")]
        llm_service = MockLLMService(chunks=chunks)

        delegator = LiteLLMThinkDelegator(llm_service)
        result = delegator.complete(
            messages=[{"role": "user", "content": "Hi"}],
            tools=None,
            run_context=None,
            current_tier="instruct",
        )

        assert not result.is_success
        assert "empty response" in result.error.lower()

    def test_tier_passed_to_llm_service(self):
        """Tier is passed through to LLM service."""
        from scrappy.graph.nodes.think_delegator import LiteLLMThinkDelegator

        chunks = [make_chunk(content="OK", model="m", provider="p")]
        llm_service = MockLLMService(chunks=chunks)

        delegator = LiteLLMThinkDelegator(llm_service)
        delegator.complete([], None, None, current_tier="chat")

        assert llm_service.last_model == "chat"

    def test_model_display_strips_provider_prefix(self):
        """Model display strips provider/ prefix from model name."""
        from scrappy.graph.nodes.think_delegator import LiteLLMThinkDelegator

        chunks = [
            make_chunk(
                content="OK",
                model="groq/llama-3.1-70b-versatile",
                provider="groq"
            )
        ]
        llm_service = MockLLMService(chunks=chunks)

        delegator = LiteLLMThinkDelegator(llm_service)
        result = delegator.complete([], None, None, "instruct")

        assert result.model_display == "groq: llama-3.1-70b-versatile"
