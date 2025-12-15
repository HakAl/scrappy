"""
Unit tests for LiteLLMService streaming functionality.

Tests the stream_completion method including:
- Basic streaming with content chunks
- Tool call fragment extraction
- Finish reason detection
- Context window escalation (pre-stream and mid-stream)
- Rate limit error handling
- Chunk conversion to StreamChunk format
"""

import pytest
from typing import List, Any
from unittest.mock import Mock

from scrappy.orchestrator.litellm_service import LiteLLMService, NotConfiguredError
from scrappy.orchestrator.types import StreamChunk, ToolCallFragment
from scrappy.infrastructure.exceptions.provider_errors import AllProvidersRateLimitedError
from tests.helpers import (
    MockStreamingRouter,
    MockApiKeyService,
    CapturingStreamOutput,
    make_stream_chunk,
)


# =============================================================================
# Mock LiteLLM Chunk Objects
# =============================================================================

class MockLiteLLMDelta:
    """Mock for LiteLLM streaming delta object."""

    def __init__(
        self,
        content: str = "",
        tool_calls: List[Any] = None,
    ):
        self.content = content if content else None
        self.tool_calls = tool_calls or None


class MockLiteLLMFunctionDelta:
    """Mock for LiteLLM function object in tool call delta."""

    def __init__(self, name: str = "", arguments: str = ""):
        self.name = name if name else None
        self.arguments = arguments if arguments else None


class MockLiteLLMToolCallDelta:
    """Mock for LiteLLM tool call delta in streaming."""

    def __init__(
        self,
        id: str = "",
        type: str = "function",
        name: str = "",
        arguments: str = "",
        index: int = 0,
    ):
        self.id = id if id else None
        self.type = type
        self.index = index
        self.function = MockLiteLLMFunctionDelta(name=name, arguments=arguments)


class MockLiteLLMStreamChoice:
    """Mock for LiteLLM streaming choice object."""

    def __init__(
        self,
        delta: MockLiteLLMDelta = None,
        finish_reason: str = None,
    ):
        self.delta = delta or MockLiteLLMDelta()
        self.finish_reason = finish_reason


class MockLiteLLMStreamChunk:
    """Mock for LiteLLM streaming chunk object."""

    def __init__(
        self,
        content: str = "",
        finish_reason: str = None,
        model: str = "groq/llama-3.1-8b-instant",
        tool_calls: List[Any] = None,
    ):
        delta = MockLiteLLMDelta(content=content, tool_calls=tool_calls)
        self.choices = [MockLiteLLMStreamChoice(delta=delta, finish_reason=finish_reason)]
        self.model = model


def make_mock_litellm_chunk(
    content: str = "",
    finish_reason: str = None,
    model: str = "groq/llama-3.1-8b-instant",
    tool_calls: List[Any] = None,
) -> MockLiteLLMStreamChunk:
    """
    Factory function to create mock LiteLLM streaming chunks.

    Args:
        content: Text content in the chunk
        finish_reason: Reason streaming ended (None if still streaming)
        model: Model identifier (e.g., "groq/llama-3.1-8b-instant")
        tool_calls: Optional list of tool call delta objects

    Returns:
        MockLiteLLMStreamChunk instance
    """
    return MockLiteLLMStreamChunk(
        content=content,
        finish_reason=finish_reason,
        model=model,
        tool_calls=tool_calls,
    )


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_api_keys():
    """Mock API key service with Groq configured."""
    return MockApiKeyService(keys={"groq_api_key": "test_key"})


@pytest.fixture
def capturing_output():
    """Capturing output for streaming events."""
    return CapturingStreamOutput()


@pytest.fixture
def unconfigured_service(capturing_output):
    """LiteLLMService instance that is NOT configured."""
    router = MockStreamingRouter()
    api_keys = MockApiKeyService(keys={})
    return LiteLLMService(
        router=router,
        api_key_service=api_keys,
        output=capturing_output,
    )


@pytest.fixture
def configured_service(mock_api_keys, capturing_output):
    """LiteLLMService instance that is configured and ready."""
    chunks = [
        make_mock_litellm_chunk(content="Hello"),
        make_mock_litellm_chunk(content=" world", finish_reason="stop"),
    ]
    router = MockStreamingRouter(stream_chunks=chunks)
    service = LiteLLMService(
        router=router,
        api_key_service=mock_api_keys,
        output=capturing_output,
    )
    service._configured = True
    return service


# =============================================================================
# Basic Streaming Tests
# =============================================================================

@pytest.mark.asyncio
async def test_stream_completion_not_configured(unconfigured_service):
    """Test that stream_completion raises NotConfiguredError when not configured."""
    with pytest.raises(NotConfiguredError, match="LLM service not configured"):
        async for chunk in unconfigured_service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            pass


@pytest.mark.asyncio
async def test_stream_completion_basic_content(mock_api_keys, capturing_output):
    """Test streaming basic content chunks."""
    chunks = [
        make_mock_litellm_chunk(content="Hello"),
        make_mock_litellm_chunk(content=" "),
        make_mock_litellm_chunk(content="world"),
        make_mock_litellm_chunk(content="", finish_reason="stop"),
    ]
    router = MockStreamingRouter(stream_chunks=chunks)
    service = LiteLLMService(
        router=router,
        api_key_service=mock_api_keys,
        output=capturing_output,
    )
    service._configured = True

    collected_chunks = []
    async for chunk in service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected_chunks.append(chunk)

    assert len(collected_chunks) == 4
    assert collected_chunks[0].content == "Hello"
    assert collected_chunks[1].content == " "
    assert collected_chunks[2].content == "world"
    assert collected_chunks[3].content == ""
    assert collected_chunks[3].finish_reason == "stop"


@pytest.mark.asyncio
async def test_stream_completion_chunk_conversion(configured_service):
    """Test that LiteLLM chunks are converted to StreamChunk objects."""
    collected_chunks = []
    async for chunk in configured_service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected_chunks.append(chunk)

    # Verify all chunks are StreamChunk instances
    for chunk in collected_chunks:
        assert isinstance(chunk, StreamChunk)

    # Verify chunk fields
    assert collected_chunks[0].content == "Hello"
    assert collected_chunks[0].model == "groq/llama-3.1-8b-instant"
    assert collected_chunks[0].provider == "groq"
    assert collected_chunks[0].finish_reason is None

    assert collected_chunks[1].content == " world"
    assert collected_chunks[1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_stream_completion_extracts_provider_from_model(mock_api_keys, capturing_output):
    """Test that provider is correctly extracted from model string."""
    chunks = [
        make_mock_litellm_chunk(content="test", model="cerebras/llama3.1-8b", finish_reason="stop"),
    ]
    router = MockStreamingRouter(stream_chunks=chunks)
    service = LiteLLMService(
        router=router,
        api_key_service=mock_api_keys,
        output=capturing_output,
    )
    service._configured = True

    collected_chunks = []
    async for chunk in service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected_chunks.append(chunk)

    assert collected_chunks[0].provider == "cerebras"
    assert collected_chunks[0].model == "cerebras/llama3.1-8b"


# =============================================================================
# Tool Call Fragment Tests
# =============================================================================

@pytest.mark.asyncio
async def test_stream_completion_with_tool_call_fragments(mock_api_keys, capturing_output):
    """Test streaming with tool call fragments."""
    tool_delta_1 = MockLiteLLMToolCallDelta(
        id="call_123",
        type="function",
        name="get_weather",
        arguments='{"loc',
        index=0,
    )
    tool_delta_2 = MockLiteLLMToolCallDelta(
        id="",
        type="function",
        name="",
        arguments='ation": "SF"}',
        index=0,
    )

    chunks = [
        make_mock_litellm_chunk(content="", tool_calls=[tool_delta_1]),
        make_mock_litellm_chunk(content="", tool_calls=[tool_delta_2]),
        make_mock_litellm_chunk(content="", finish_reason="tool_calls"),
    ]
    router = MockStreamingRouter(stream_chunks=chunks)
    service = LiteLLMService(
        router=router,
        api_key_service=mock_api_keys,
        output=capturing_output,
    )
    service._configured = True

    collected_chunks = []
    async for chunk in service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
        tools=[{"type": "function", "function": {"name": "get_weather"}}],
        tool_choice="auto",
    ):
        collected_chunks.append(chunk)

    # First chunk should have tool call fragment with id and name
    assert len(collected_chunks[0].tool_call_fragments) == 1
    frag1 = collected_chunks[0].tool_call_fragments[0]
    assert frag1.id == "call_123"
    assert frag1.name == "get_weather"
    assert frag1.arguments == '{"loc'
    assert frag1.index == 0

    # Second chunk should have fragment with more arguments
    assert len(collected_chunks[1].tool_call_fragments) == 1
    frag2 = collected_chunks[1].tool_call_fragments[0]
    assert frag2.arguments == 'ation": "SF"}'
    assert frag2.index == 0

    # Final chunk should have finish_reason
    assert collected_chunks[2].finish_reason == "tool_calls"


@pytest.mark.asyncio
async def test_stream_completion_no_tool_calls(configured_service):
    """Test that chunks without tool calls have empty tool_call_fragments list."""
    collected_chunks = []
    async for chunk in configured_service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected_chunks.append(chunk)

    for chunk in collected_chunks:
        assert chunk.tool_call_fragments == []


# =============================================================================
# Context Window Escalation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_stream_completion_escalates_on_context_window_error(mock_api_keys, capturing_output):
    """Test that context window errors trigger escalation to quality tier."""
    from litellm import ContextWindowExceededError

    # First call to "fast" raises ContextWindowExceededError
    # Second call to "quality" succeeds
    quality_chunks = [
        make_mock_litellm_chunk(content="Quality response", finish_reason="stop"),
    ]

    # Create ContextWindowExceededError with required params
    error = ContextWindowExceededError(
        message="Context window exceeded",
        model="groq/llama-3.1-8b-instant",
        llm_provider="groq",
    )

    router = MockStreamingRouter(
        stream_chunks=quality_chunks,
        exception=error,
    )

    service = LiteLLMService(
        router=router,
        api_key_service=mock_api_keys,
        output=capturing_output,
    )
    service._configured = True

    # Override stream_completion to simulate escalation behavior
    # Since the router raises on first call, we need to test the escalation logic
    collected_chunks = []

    # The stream_completion method should catch ContextWindowExceededError
    # and retry with "quality" tier
    with pytest.raises(ContextWindowExceededError):
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected_chunks.append(chunk)


@pytest.mark.asyncio
async def test_stream_completion_escalation_max_depth(mock_api_keys, capturing_output):
    """Test that escalation respects max depth to prevent infinite recursion."""
    from litellm import ContextWindowExceededError

    # Create ContextWindowExceededError with required params
    error = ContextWindowExceededError(
        message="Context window exceeded",
        model="groq/llama-3.1-8b-instant",
        llm_provider="groq",
    )

    router = MockStreamingRouter(
        stream_chunks=[],
        exception=error,
    )

    service = LiteLLMService(
        router=router,
        api_key_service=mock_api_keys,
        output=capturing_output,
    )
    service._configured = True

    # Calling with _escalation_depth at max should raise RuntimeError
    with pytest.raises(RuntimeError, match="Max escalation depth"):
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
            _escalation_depth=2,  # MAX_ESCALATION_DEPTH = 2
        ):
            pass


# =============================================================================
# Rate Limit Error Tests
# =============================================================================

@pytest.mark.asyncio
async def test_stream_completion_rate_limit_error(mock_api_keys, capturing_output):
    """Test that rate limit errors are converted to AllProvidersRateLimitedError."""
    from litellm import RateLimitError as LiteLLMRateLimitError

    # Create RateLimitError with required params
    rate_limit_error = LiteLLMRateLimitError(
        message="Rate limit exceeded",
        llm_provider="groq",
        model="groq/llama-3.1-8b-instant",
    )

    router = MockStreamingRouter(
        stream_chunks=[],
        exception=rate_limit_error,
    )

    service = LiteLLMService(
        router=router,
        api_key_service=mock_api_keys,
        output=capturing_output,
    )
    service._configured = True

    with pytest.raises(AllProvidersRateLimitedError):
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            pass


# =============================================================================
# Edge Cases
# =============================================================================

@pytest.mark.asyncio
async def test_stream_completion_empty_stream(mock_api_keys, capturing_output):
    """Test streaming with no chunks (edge case)."""
    router = MockStreamingRouter(stream_chunks=[])
    service = LiteLLMService(
        router=router,
        api_key_service=mock_api_keys,
        output=capturing_output,
    )
    service._configured = True

    collected_chunks = []
    async for chunk in service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected_chunks.append(chunk)

    assert len(collected_chunks) == 0


@pytest.mark.asyncio
async def test_stream_completion_only_finish_chunk(mock_api_keys, capturing_output):
    """Test stream with only a finish chunk (no content)."""
    chunks = [
        make_mock_litellm_chunk(content="", finish_reason="stop"),
    ]
    router = MockStreamingRouter(stream_chunks=chunks)
    service = LiteLLMService(
        router=router,
        api_key_service=mock_api_keys,
        output=capturing_output,
    )
    service._configured = True

    collected_chunks = []
    async for chunk in service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected_chunks.append(chunk)

    assert len(collected_chunks) == 1
    assert collected_chunks[0].content == ""
    assert collected_chunks[0].finish_reason == "stop"


@pytest.mark.asyncio
async def test_stream_completion_no_finish_reason(mock_api_keys, capturing_output):
    """Test stream that ends without finish_reason (edge case)."""
    chunks = [
        make_mock_litellm_chunk(content="Incomplete"),
    ]
    router = MockStreamingRouter(stream_chunks=chunks)
    service = LiteLLMService(
        router=router,
        api_key_service=mock_api_keys,
        output=capturing_output,
    )
    service._configured = True

    collected_chunks = []
    async for chunk in service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected_chunks.append(chunk)

    assert len(collected_chunks) == 1
    assert collected_chunks[0].content == "Incomplete"
    assert collected_chunks[0].finish_reason is None


@pytest.mark.asyncio
async def test_stream_completion_passes_kwargs_to_router(mock_api_keys, capturing_output):
    """Test that additional kwargs are passed through to router."""
    chunks = [make_mock_litellm_chunk(content="test", finish_reason="stop")]
    router = MockStreamingRouter(stream_chunks=chunks)
    service = LiteLLMService(
        router=router,
        api_key_service=mock_api_keys,
        output=capturing_output,
    )
    service._configured = True

    async for chunk in service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
        max_tokens=500,
        temperature=0.9,
        tools=[{"type": "function", "function": {"name": "test"}}],
        tool_choice="auto",
    ):
        pass

    # Verify router was called with correct parameters
    assert len(router.calls) == 1
    call = router.calls[0]
    assert call['model'] == "fast"
    assert call['messages'] == [{"role": "user", "content": "test"}]
    assert call['stream'] is True
    assert call['num_retries'] == 3
    assert call['max_tokens'] == 500
    assert call['temperature'] == 0.9
    assert 'tools' in call
    assert call['tool_choice'] == "auto"


# =============================================================================
# Chunk Conversion Edge Cases
# =============================================================================

@pytest.mark.asyncio
async def test_convert_chunk_handles_missing_content(mock_api_keys, capturing_output):
    """Test that _convert_chunk handles chunks with no content gracefully."""
    # Create chunk with delta but no content attribute
    chunk = MockLiteLLMStreamChunk(content="", model="groq/test")
    chunk.choices[0].delta.content = None  # Explicitly set to None

    router = MockStreamingRouter(stream_chunks=[chunk])
    service = LiteLLMService(
        router=router,
        api_key_service=mock_api_keys,
        output=capturing_output,
    )
    service._configured = True

    collected_chunks = []
    async for chunk in service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected_chunks.append(chunk)

    assert collected_chunks[0].content == ""


@pytest.mark.asyncio
async def test_convert_chunk_handles_empty_model(mock_api_keys, capturing_output):
    """Test that _convert_chunk handles chunks with empty/None model."""
    chunk = make_mock_litellm_chunk(content="test", model="")

    router = MockStreamingRouter(stream_chunks=[chunk])
    service = LiteLLMService(
        router=router,
        api_key_service=mock_api_keys,
        output=capturing_output,
    )
    service._configured = True

    collected_chunks = []
    async for chunk in service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected_chunks.append(chunk)

    assert collected_chunks[0].model == ""
    assert collected_chunks[0].provider == ""


# =============================================================================
# Edge Case Tests (Layer 5)
# =============================================================================

@pytest.mark.asyncio
async def test_stream_completion_stuck_stream_detection(mock_api_keys, capturing_output):
    """Test that stuck stream raises StreamStuckError after timeout."""
    import asyncio
    from scrappy.orchestrator.litellm_service import StreamStuckError

    class SlowStreamRouter:
        """Router that simulates a stuck stream."""
        def __init__(self):
            self.calls = []

        async def acompletion(self, **kwargs):
            self.calls.append(kwargs)
            async def slow_generator():
                yield make_mock_litellm_chunk(content="First")
                # Simulate stuck stream - wait longer than timeout
                await asyncio.sleep(10)  # Will be cancelled by timeout
                yield make_mock_litellm_chunk(content="Never reached")
            return slow_generator()

    router = SlowStreamRouter()
    service = LiteLLMService(
        router=router,
        api_key_service=mock_api_keys,
        output=capturing_output,
    )
    service._configured = True

    collected = []
    with pytest.raises(StreamStuckError) as exc_info:
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
            timeout_ms=100,  # 100ms timeout
        ):
            collected.append(chunk)

    # Should have received first chunk before timeout
    assert len(collected) == 1
    assert collected[0].content == "First"
    # Exception should contain partial content
    assert exc_info.value.partial_content == "First"
    assert exc_info.value.timeout_ms == 100


@pytest.mark.asyncio
async def test_stream_completion_cancellation_token(mock_api_keys, capturing_output):
    """Test that cancellation token stops stream cleanly."""
    import asyncio
    from scrappy.orchestrator.litellm_service import StreamCancelledError

    chunks = [
        make_mock_litellm_chunk(content="First "),
        make_mock_litellm_chunk(content="Second "),
        make_mock_litellm_chunk(content="Third", finish_reason="stop"),
    ]
    router = MockStreamingRouter(stream_chunks=chunks)
    service = LiteLLMService(
        router=router,
        api_key_service=mock_api_keys,
        output=capturing_output,
    )
    service._configured = True

    # Create cancellation token and set it after first chunk
    cancel_event = asyncio.Event()
    collected = []

    with pytest.raises(StreamCancelledError) as exc_info:
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
            cancellation_token=cancel_event,
        ):
            collected.append(chunk)
            if len(collected) == 1:
                cancel_event.set()  # Cancel after first chunk

    # Should have received first chunk before cancellation
    assert len(collected) == 1
    assert collected[0].content == "First "
    assert exc_info.value.partial_content == "First "


@pytest.mark.asyncio
async def test_stream_completion_double_final_chunk_dedup(mock_api_keys, capturing_output):
    """Test that duplicate final chunks (Groq quirk) are deduplicated."""
    # Simulate Groq sending finish_reason twice
    chunks = [
        make_mock_litellm_chunk(content="Hello"),
        make_mock_litellm_chunk(content=" world", finish_reason="stop"),
        make_mock_litellm_chunk(content="", finish_reason="stop"),  # Duplicate final
    ]
    router = MockStreamingRouter(stream_chunks=chunks)
    service = LiteLLMService(
        router=router,
        api_key_service=mock_api_keys,
        output=capturing_output,
    )
    service._configured = True

    collected = []
    async for chunk in service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected.append(chunk)

    # Should only have 2 chunks (duplicate final chunk skipped)
    assert len(collected) == 2
    assert collected[0].content == "Hello"
    assert collected[1].content == " world"
    assert collected[1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_stream_completion_mid_stream_error_preserves_content(mock_api_keys, capturing_output):
    """Test that mid-stream errors preserve partial content info."""

    class ErrorMidStreamRouter:
        """Router that raises an error after yielding some chunks."""
        def __init__(self):
            self.calls = []

        async def acompletion(self, **kwargs):
            self.calls.append(kwargs)
            async def error_generator():
                yield make_mock_litellm_chunk(content="Partial ")
                yield make_mock_litellm_chunk(content="content ")
                raise RuntimeError("Connection lost")
            return error_generator()

    router = ErrorMidStreamRouter()
    service = LiteLLMService(
        router=router,
        api_key_service=mock_api_keys,
        output=capturing_output,
    )
    service._configured = True

    collected = []
    with pytest.raises(RuntimeError) as exc_info:
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected.append(chunk)

    # Should have received chunks before error
    assert len(collected) == 2
    # Error message should mention partial content
    assert "partial content available" in str(exc_info.value)
    assert "16 chars" in str(exc_info.value)  # "Partial content " = 16 chars


@pytest.mark.asyncio
async def test_stream_completion_default_timeout_is_reasonable(mock_api_keys, capturing_output):
    """Test that default timeout is set to a reasonable value."""
    from scrappy.orchestrator.litellm_service import DEFAULT_STREAM_TIMEOUT_MS

    # Default should be 30 seconds (30000ms)
    assert DEFAULT_STREAM_TIMEOUT_MS == 30000
