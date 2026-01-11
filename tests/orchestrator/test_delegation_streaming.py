"""
Unit tests for DelegationManager streaming functionality.

Tests the stream_delegate method including:
- Basic streaming with prompt augmentation
- Cache hit returning single chunk
- Cache miss streaming from provider
- Provider not supporting streaming raises NotImplementedError
- Caching of streamed responses
- Context augmentation behavior
"""

import pytest
from typing import Optional, List, Any, AsyncIterator
from unittest.mock import Mock

from scrappy.orchestrator.delegation import DelegationManager
from scrappy.orchestrator.types import StreamChunk
from scrappy.orchestrator.protocols import StreamingCompletionProtocol
from scrappy.orchestrator.provider_types import LLMResponse
from tests.helpers import (
    make_stream_chunk,
    CapturingStreamOutput,
)


# =============================================================================
# Mock Implementations
# =============================================================================

class MockPromptAugmenter:
    """Mock prompt augmenter that tracks augmentation calls."""

    def __init__(self):
        self.calls: List[dict] = []

    def augment(self, prompt: str, use_context: bool = False) -> str:
        """
        Mock augmentation that optionally adds context prefix.

        Args:
            prompt: Original prompt
            use_context: Whether to add context

        Returns:
            Augmented prompt (with "[CONTEXT] " prefix if use_context=True)
        """
        self.calls.append({
            'prompt': prompt,
            'use_context': use_context
        })
        if use_context:
            return f"[CONTEXT] {prompt}"
        return prompt


class MockCache:
    """Mock cache that tracks get/put operations."""

    def __init__(self):
        self._store: dict = {}
        self.get_calls: List[dict] = []
        self.put_calls: List[dict] = []

    def get(
        self,
        provider: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Optional[LLMResponse]:
        """Get cached response."""
        self.get_calls.append({
            'provider': provider,
            'prompt': prompt,
            'model': model,
            'system_prompt': system_prompt,
            'max_tokens': max_tokens,
            'temperature': temperature,
        })
        cache_key = f"{provider}:{prompt}"
        return self._store.get(cache_key)

    def put(
        self,
        response: LLMResponse,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> None:
        """Store response in cache."""
        self.put_calls.append({
            'response': response,
            'prompt': prompt,
            'model': model,
            'system_prompt': system_prompt,
            'max_tokens': max_tokens,
            'temperature': temperature,
        })
        cache_key = f"{response.provider}:{prompt}"
        self._store[cache_key] = response

    def get_by_intent(self, *args, **kwargs) -> Optional[LLMResponse]:
        """Mock intent-based cache (not used in streaming tests)."""
        return None

    def put_by_intent(self, *args, **kwargs) -> None:
        """Mock intent-based cache put (not used in streaming tests)."""
        pass


class MockBatchScheduler:
    """Mock batch scheduler (not used in streaming tests)."""
    pass


class MockStreamingLLMService:
    """
    Mock LLM service that supports streaming.

    Implements StreamingCompletionProtocol and returns controllable
    stream chunks for testing.
    """

    def __init__(self, stream_chunks: Optional[List[StreamChunk]] = None):
        """
        Initialize mock streaming service.

        Args:
            stream_chunks: List of chunks to yield during streaming
        """
        self._stream_chunks = stream_chunks or []
        self.stream_calls: List[dict] = []

    async def stream_completion(
        self,
        model: str,
        messages: list,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Mock streaming completion that yields configured chunks.

        Args:
            model: Model group name
            messages: Chat messages
            **kwargs: Additional params

        Yields:
            StreamChunk objects
        """
        self.stream_calls.append({
            'model': model,
            'messages': messages,
            **kwargs
        })

        for chunk in self._stream_chunks:
            yield chunk

    async def completion(self, model: str, messages: list, **kwargs):
        """Non-streaming completion (not used in streaming tests)."""
        raise NotImplementedError("Use stream_completion")

    def completion_sync(self, model: str, messages: list, **kwargs):
        """Sync completion (not used in streaming tests)."""
        raise NotImplementedError("Use stream_completion")


class MockNonStreamingLLMService:
    """
    Mock LLM service that does NOT support streaming.

    This service does not implement StreamingCompletionProtocol,
    so stream_delegate should raise NotImplementedError.
    """

    async def completion(self, model: str, messages: list, **kwargs):
        """Non-streaming completion."""
        return (
            LLMResponse(
                content="test response",
                model="groq/llama-3.1-8b-instant",
                provider="groq",
                tokens_used=10,
            ),
            {}
        )

    def completion_sync(self, model: str, messages: list, **kwargs):
        """Sync completion."""
        return (
            LLMResponse(
                content="test response",
                model="groq/llama-3.1-8b-instant",
                provider="groq",
                tokens_used=10,
            ),
            {}
        )


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_augmenter():
    """Mock prompt augmenter."""
    return MockPromptAugmenter()


@pytest.fixture
def mock_cache():
    """Mock cache."""
    return MockCache()


@pytest.fixture
def mock_output():
    """Mock output interface."""
    return CapturingStreamOutput()


@pytest.fixture
def mock_batch_scheduler():
    """Mock batch scheduler."""
    return MockBatchScheduler()


@pytest.fixture
def delegation_manager_streaming(mock_augmenter, mock_cache, mock_output, mock_batch_scheduler):
    """
    DelegationManager configured with streaming-capable LLM service.

    Returns factory function to create DelegationManager with custom chunks.
    """
    def _factory(
        stream_chunks: Optional[List[StreamChunk]] = None,
        context_aware: bool = False,
    ) -> DelegationManager:
        if stream_chunks is None:
            chunks = [
                make_stream_chunk(content="Hello", model="groq/llama-3.1-8b-instant", provider="groq"),
                make_stream_chunk(content=" world", finish_reason="stop", model="groq/llama-3.1-8b-instant", provider="groq"),
            ]
        else:
            chunks = stream_chunks
        llm_service = MockStreamingLLMService(stream_chunks=chunks)

        return DelegationManager(
            llm_service=llm_service,
            cache=mock_cache,
            output=mock_output,
            prompt_augmenter=mock_augmenter,
            batch_scheduler=mock_batch_scheduler,
            context_aware=context_aware,
        )

    return _factory


@pytest.fixture
def delegation_manager_nonstreaming(mock_augmenter, mock_cache, mock_output, mock_batch_scheduler):
    """DelegationManager configured with NON-streaming LLM service."""
    llm_service = MockNonStreamingLLMService()

    return DelegationManager(
        llm_service=llm_service,
        cache=mock_cache,
        output=mock_output,
        prompt_augmenter=mock_augmenter,
        batch_scheduler=mock_batch_scheduler,
        context_aware=False,
    )


# =============================================================================
# Basic Streaming Tests
# =============================================================================

@pytest.mark.asyncio
async def test_stream_delegate_basic_streaming(delegation_manager_streaming, mock_augmenter, mock_cache):
    """Test basic streaming delegates to LLM service and yields chunks."""
    manager = delegation_manager_streaming()

    collected_chunks = []
    async for chunk in manager.stream_delegate(
        provider_name="fast",
        prompt="test prompt",
    ):
        collected_chunks.append(chunk)

    # Verify chunks were yielded
    assert len(collected_chunks) == 2
    assert collected_chunks[0].content == "Hello"
    assert collected_chunks[1].content == " world"
    assert collected_chunks[1].finish_reason == "stop"

    # Verify prompt was augmented
    assert len(mock_augmenter.calls) == 1
    assert mock_augmenter.calls[0]['prompt'] == "test prompt"
    assert mock_augmenter.calls[0]['use_context'] is False

    # Verify cache was checked (miss)
    assert len(mock_cache.get_calls) == 1
    assert mock_cache.get_calls[0]['provider'] == "fast"
    assert mock_cache.get_calls[0]['prompt'] == "test prompt"


@pytest.mark.asyncio
async def test_stream_delegate_augments_prompt(delegation_manager_streaming, mock_augmenter):
    """Test that stream_delegate augments prompt with context when enabled."""
    manager = delegation_manager_streaming(context_aware=True)

    collected_chunks = []
    async for chunk in manager.stream_delegate(
        provider_name="fast",
        prompt="test prompt",
    ):
        collected_chunks.append(chunk)

    # Verify prompt was augmented with context
    assert len(mock_augmenter.calls) == 1
    assert mock_augmenter.calls[0]['prompt'] == "test prompt"
    assert mock_augmenter.calls[0]['use_context'] is True


@pytest.mark.asyncio
async def test_stream_delegate_use_context_override(delegation_manager_streaming, mock_augmenter):
    """Test that use_context parameter overrides context_aware setting."""
    manager = delegation_manager_streaming(context_aware=False)

    collected_chunks = []
    async for chunk in manager.stream_delegate(
        provider_name="fast",
        prompt="test prompt",
        use_context=True,  # Override context_aware=False
    ):
        collected_chunks.append(chunk)

    # Verify context was enabled via override
    assert mock_augmenter.calls[0]['use_context'] is True


@pytest.mark.asyncio
async def test_stream_delegate_passes_params_to_service(delegation_manager_streaming):
    """Test that stream_delegate passes all parameters to LLM service."""
    chunks = [
        make_stream_chunk(content="response", finish_reason="stop", model="test", provider="test")
    ]
    manager = delegation_manager_streaming(stream_chunks=chunks)

    collected_chunks = []
    async for chunk in manager.stream_delegate(
        provider_name="quality",
        prompt="test prompt",
        model="custom-model",
        system_prompt="You are helpful",
        max_tokens=500,
        temperature=0.9,
    ):
        collected_chunks.append(chunk)

    # Verify LLM service received correct parameters
    llm_service = manager._llm_service
    assert len(llm_service.stream_calls) == 1
    call = llm_service.stream_calls[0]

    # When specific model is provided, it should be used directly (not resolved to group)
    assert call['model'] == "custom-model"
    assert call['messages'] == [
        {"role": "system", "content": "You are helpful"},
        {"role": "user", "content": "test prompt"}
    ]
    assert call['max_tokens'] == 500
    assert call['temperature'] == 0.9


# =============================================================================
# Cache Behavior Tests
# =============================================================================

@pytest.mark.asyncio
async def test_stream_delegate_cache_hit_returns_single_chunk(delegation_manager_streaming, mock_cache):
    """Test that cache hit yields single chunk with full cached content."""
    # Pre-populate cache
    cached_response = LLMResponse(
        content="Cached response",
        model="groq/llama-3.1-8b-instant",
        provider="groq",
        tokens_used=50,
    )
    mock_cache._store["fast:test prompt"] = cached_response

    manager = delegation_manager_streaming()

    collected_chunks = []
    async for chunk in manager.stream_delegate(
        provider_name="fast",
        prompt="test prompt",
    ):
        collected_chunks.append(chunk)

    # Verify single chunk with full cached content
    assert len(collected_chunks) == 1
    assert collected_chunks[0].content == "Cached response"
    assert collected_chunks[0].finish_reason == "stop"
    assert collected_chunks[0].model == "groq/llama-3.1-8b-instant"
    assert collected_chunks[0].provider == "groq"
    assert collected_chunks[0].metadata['cached'] is True

    # Verify LLM service was NOT called
    llm_service = manager._llm_service
    assert len(llm_service.stream_calls) == 0


@pytest.mark.asyncio
async def test_stream_delegate_cache_miss_streams_and_caches(delegation_manager_streaming, mock_cache):
    """Test that cache miss streams from provider and caches result."""
    chunks = [
        make_stream_chunk(content="Streamed ", model="groq/test", provider="groq"),
        make_stream_chunk(content="response", finish_reason="stop", model="groq/test", provider="groq"),
    ]
    manager = delegation_manager_streaming(stream_chunks=chunks)

    collected_chunks = []
    async for chunk in manager.stream_delegate(
        provider_name="fast",
        prompt="new prompt",
        max_tokens=100,
        temperature=0.7,
    ):
        collected_chunks.append(chunk)

    # Verify chunks were streamed
    assert len(collected_chunks) == 2
    assert collected_chunks[0].content == "Streamed "
    assert collected_chunks[1].content == "response"

    # Verify result was cached
    assert len(mock_cache.put_calls) == 1
    put_call = mock_cache.put_calls[0]

    assert put_call['response'].content == "Streamed response"  # Accumulated content
    assert put_call['response'].model == "groq/test"
    assert put_call['response'].provider == "groq"
    assert put_call['prompt'] == "new prompt"
    assert put_call['max_tokens'] == 100
    assert put_call['temperature'] == 0.7


@pytest.mark.asyncio
async def test_stream_delegate_use_cache_false_skips_cache(delegation_manager_streaming, mock_cache):
    """Test that use_cache=False skips cache check and put."""
    # Pre-populate cache (should be ignored)
    cached_response = LLMResponse(
        content="Cached",
        model="test",
        provider="test",
        tokens_used=10,
    )
    mock_cache._store["fast:test prompt"] = cached_response

    chunks = [
        make_stream_chunk(content="Live", finish_reason="stop", model="test", provider="test")
    ]
    manager = delegation_manager_streaming(stream_chunks=chunks)

    collected_chunks = []
    async for chunk in manager.stream_delegate(
        provider_name="fast",
        prompt="test prompt",
        use_cache=False,
    ):
        collected_chunks.append(chunk)

    # Verify streamed from provider, not cache
    assert len(collected_chunks) == 1
    assert collected_chunks[0].content == "Live"

    # Verify cache was NOT checked
    assert len(mock_cache.get_calls) == 0

    # Verify result was NOT cached
    assert len(mock_cache.put_calls) == 0


# =============================================================================
# Provider Support Tests
# =============================================================================


# =============================================================================
# Model Group Resolution Tests
# =============================================================================

@pytest.mark.asyncio
async def test_stream_delegate_resolves_fast_model_group(delegation_manager_streaming):
    """Test that provider name is resolved to model group."""
    chunks = [
        make_stream_chunk(content="test", finish_reason="stop", model="test", provider="test")
    ]
    manager = delegation_manager_streaming(stream_chunks=chunks)

    collected_chunks = []
    async for chunk in manager.stream_delegate(
        provider_name="fast",
        prompt="test prompt",
    ):
        collected_chunks.append(chunk)

    # Verify model group was passed to service
    llm_service = manager._llm_service
    assert llm_service.stream_calls[0]['model'] == "fast"


@pytest.mark.asyncio
async def test_stream_delegate_resolves_quality_to_chat(delegation_manager_streaming):
    """Test that legacy 'quality' maps to 'chat' model group."""
    chunks = [
        make_stream_chunk(content="test", finish_reason="stop", model="test", provider="test")
    ]
    manager = delegation_manager_streaming(stream_chunks=chunks)

    collected_chunks = []
    async for chunk in manager.stream_delegate(
        provider_name="quality",  # Legacy name
        prompt="test prompt",
    ):
        collected_chunks.append(chunk)

    # Verify legacy "quality" maps to "chat" model group
    llm_service = manager._llm_service
    assert llm_service.stream_calls[0]['model'] == "chat"


@pytest.mark.asyncio
async def test_stream_delegate_resolves_legacy_provider_names(delegation_manager_streaming):
    """Test that legacy provider names (groq, cerebras) map to model groups."""
    chunks = [
        make_stream_chunk(content="test", finish_reason="stop", model="test", provider="test")
    ]
    manager = delegation_manager_streaming(stream_chunks=chunks)

    # Test legacy "groq" -> "fast"
    collected_chunks = []
    async for chunk in manager.stream_delegate(
        provider_name="groq",
        prompt="test prompt",
    ):
        collected_chunks.append(chunk)

    llm_service = manager._llm_service
    assert llm_service.stream_calls[0]['model'] == "fast"


# =============================================================================
# Edge Cases
# =============================================================================

@pytest.mark.asyncio
async def test_stream_delegate_empty_stream(delegation_manager_streaming):
    """Test streaming with no chunks (edge case)."""
    manager = delegation_manager_streaming(stream_chunks=[])

    collected_chunks = []
    async for chunk in manager.stream_delegate(
        provider_name="fast",
        prompt="test prompt",
    ):
        collected_chunks.append(chunk)

    # Verify no chunks yielded
    assert len(collected_chunks) == 0


@pytest.mark.asyncio
async def test_stream_delegate_only_finish_chunk(delegation_manager_streaming, mock_cache):
    """Test stream with only finish chunk (no content)."""
    chunks = [
        make_stream_chunk(content="", finish_reason="stop", model="test", provider="test")
    ]
    manager = delegation_manager_streaming(stream_chunks=chunks)

    collected_chunks = []
    async for chunk in manager.stream_delegate(
        provider_name="fast",
        prompt="test prompt",
    ):
        collected_chunks.append(chunk)

    # Verify chunk was yielded
    assert len(collected_chunks) == 1
    assert collected_chunks[0].content == ""
    assert collected_chunks[0].finish_reason == "stop"

    # Verify empty content was cached
    assert len(mock_cache.put_calls) == 1
    assert mock_cache.put_calls[0]['response'].content == ""


@pytest.mark.asyncio
async def test_stream_delegate_no_finish_reason(delegation_manager_streaming, mock_cache):
    """Test stream that ends without finish_reason (edge case)."""
    chunks = [
        make_stream_chunk(content="Incomplete", model="test", provider="test")
    ]
    manager = delegation_manager_streaming(stream_chunks=chunks)

    collected_chunks = []
    async for chunk in manager.stream_delegate(
        provider_name="fast",
        prompt="test prompt",
    ):
        collected_chunks.append(chunk)

    # Verify chunk was yielded
    assert len(collected_chunks) == 1
    assert collected_chunks[0].content == "Incomplete"
    assert collected_chunks[0].finish_reason is None

    # Verify incomplete response was still cached
    assert len(mock_cache.put_calls) == 1
    assert mock_cache.put_calls[0]['response'].content == "Incomplete"


@pytest.mark.asyncio
async def test_stream_delegate_filters_internal_kwargs(delegation_manager_streaming):
    """Test that internal kwargs are filtered before passing to service."""
    chunks = [
        make_stream_chunk(content="test", finish_reason="stop", model="test", provider="test")
    ]
    manager = delegation_manager_streaming(stream_chunks=chunks)

    collected_chunks = []
    async for chunk in manager.stream_delegate(
        provider_name="fast",
        prompt="test prompt",
        task_type="planning",  # Internal kwarg (should be filtered)
        selection_type="quality",  # Internal kwarg (should be filtered)
        min_context=4096,  # Internal kwarg (should be filtered)
        max_tokens=100,  # Valid kwarg (should be passed)
    ):
        collected_chunks.append(chunk)

    # Verify internal kwargs were filtered out
    llm_service = manager._llm_service
    call = llm_service.stream_calls[0]

    assert 'task_type' not in call
    assert 'selection_type' not in call
    assert 'min_context' not in call
    assert call['max_tokens'] == 100


@pytest.mark.asyncio
async def test_stream_delegate_accumulates_multi_chunk_content(delegation_manager_streaming, mock_cache):
    """Test that multi-chunk responses are accumulated correctly for caching."""
    chunks = [
        make_stream_chunk(content="Part ", model="test", provider="test"),
        make_stream_chunk(content="one ", model="test", provider="test"),
        make_stream_chunk(content="part ", model="test", provider="test"),
        make_stream_chunk(content="two", finish_reason="stop", model="test", provider="test"),
    ]
    manager = delegation_manager_streaming(stream_chunks=chunks)

    collected_chunks = []
    async for chunk in manager.stream_delegate(
        provider_name="fast",
        prompt="test prompt",
    ):
        collected_chunks.append(chunk)

    # Verify all chunks were yielded
    assert len(collected_chunks) == 4

    # Verify accumulated content was cached
    assert len(mock_cache.put_calls) == 1
    assert mock_cache.put_calls[0]['response'].content == "Part one part two"
