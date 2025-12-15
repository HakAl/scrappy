"""
Cancellation and interruption stress tests for streaming.

Tests streaming behavior under cancellation scenarios:
- Manual cancellation via asyncio.CancelledError
- Stream interruption mid-chunk
- Cleanup after cancellation
- Partial content recovery
- Concurrent cancellations
- Resource leak prevention
"""

import pytest
import asyncio
from typing import AsyncIterator, List, Optional
from unittest.mock import Mock

from scrappy.orchestrator.types import StreamChunk
from scrappy.orchestrator.protocols import StreamingCompletionProtocol
from tests.helpers import make_stream_chunk


# =============================================================================
# Mock Streaming Service with Cancellation Control
# =============================================================================

class CancellableStreamingService:
    """
    Mock streaming service that allows controlled cancellation testing.

    Supports:
    - Delayed chunk emission
    - Cancellation at specific chunk indices
    - Cleanup tracking
    - Exception injection
    """

    def __init__(
        self,
        chunks: List[StreamChunk],
        chunk_delay_ms: float = 10,
        cancel_at_chunk: Optional[int] = None,
        raise_at_chunk: Optional[int] = None,
        exception_to_raise: Optional[Exception] = None,
    ):
        """
        Initialize cancellable streaming service.

        Args:
            chunks: List of chunks to yield
            chunk_delay_ms: Delay between chunks in milliseconds
            cancel_at_chunk: Chunk index to raise CancelledError (None = no auto-cancel)
            raise_at_chunk: Chunk index to raise exception (None = no exception)
            exception_to_raise: Exception to raise at raise_at_chunk
        """
        self._chunks = chunks
        self._chunk_delay_ms = chunk_delay_ms
        self._cancel_at_chunk = cancel_at_chunk
        self._raise_at_chunk = raise_at_chunk
        self._exception_to_raise = exception_to_raise or RuntimeError("Stream error")

        self.chunks_yielded = 0
        self.cleanup_called = False
        self.stream_started = False
        self.stream_calls: List[dict] = []

    async def stream_completion(
        self,
        model: str,
        messages: list,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream completion with controllable cancellation points.

        Args:
            model: Model group name
            messages: Chat messages
            **kwargs: Additional params

        Yields:
            StreamChunk objects

        Raises:
            asyncio.CancelledError: At configured cancellation point
            Exception: At configured exception point
        """
        self.stream_started = True
        self.stream_calls.append({
            'model': model,
            'messages': messages,
            **kwargs
        })

        try:
            for idx, chunk in enumerate(self._chunks):
                # Check for configured exception
                if self._raise_at_chunk is not None and idx == self._raise_at_chunk:
                    raise self._exception_to_raise

                # Check for configured cancellation
                if self._cancel_at_chunk is not None and idx == self._cancel_at_chunk:
                    raise asyncio.CancelledError("Cancelled at configured point")

                # Simulate network delay
                if self._chunk_delay_ms > 0:
                    await asyncio.sleep(self._chunk_delay_ms / 1000)

                self.chunks_yielded += 1
                yield chunk
        finally:
            # Cleanup tracking
            self.cleanup_called = True


class SlowStreamingService:
    """
    Mock streaming service that streams very slowly.

    Used for timeout and cancellation stress testing.
    """

    def __init__(
        self,
        chunks: List[StreamChunk],
        delay_per_chunk_ms: float = 500,
    ):
        """
        Initialize slow streaming service.

        Args:
            chunks: List of chunks to yield
            delay_per_chunk_ms: Delay between chunks in milliseconds
        """
        self._chunks = chunks
        self._delay_per_chunk_ms = delay_per_chunk_ms

        self.chunks_yielded = 0
        self.cancelled = False

    async def stream_completion(
        self,
        model: str,
        messages: list,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream completion with deliberate delays.

        Args:
            model: Model group name
            messages: Chat messages
            **kwargs: Additional params

        Yields:
            StreamChunk objects
        """
        try:
            for chunk in self._chunks:
                await asyncio.sleep(self._delay_per_chunk_ms / 1000)
                self.chunks_yielded += 1
                yield chunk
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class HangingStreamingService:
    """
    Mock streaming service that hangs indefinitely after N chunks.

    Used for testing timeout and cancellation recovery.
    """

    def __init__(
        self,
        chunks_before_hang: int = 2,
        initial_chunks: Optional[List[StreamChunk]] = None,
    ):
        """
        Initialize hanging streaming service.

        Args:
            chunks_before_hang: Number of chunks to yield before hanging
            initial_chunks: Chunks to yield before hanging
        """
        self._chunks_before_hang = chunks_before_hang
        self._initial_chunks = initial_chunks or [
            make_stream_chunk(content="Start", model="test", provider="test"),
            make_stream_chunk(content=" middle", model="test", provider="test"),
        ]

        self.chunks_yielded = 0
        self.hung = False
        self.cancelled_while_hung = False

    async def stream_completion(
        self,
        model: str,
        messages: list,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream completion that hangs indefinitely.

        Args:
            model: Model group name
            messages: Chat messages
            **kwargs: Additional params

        Yields:
            StreamChunk objects before hanging
        """
        try:
            # Yield initial chunks
            for idx, chunk in enumerate(self._initial_chunks):
                if idx >= self._chunks_before_hang:
                    break
                self.chunks_yielded += 1
                yield chunk
                await asyncio.sleep(0.01)

            # Hang indefinitely
            self.hung = True
            await asyncio.sleep(999999)  # Effectively infinite
        except asyncio.CancelledError:
            if self.hung:
                self.cancelled_while_hung = True
            raise


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def standard_chunks() -> List[StreamChunk]:
    """Standard chunk sequence for testing."""
    return [
        make_stream_chunk(content="Hello", model="test", provider="test"),
        make_stream_chunk(content=" world", model="test", provider="test"),
        make_stream_chunk(content="!", model="test", provider="test"),
        make_stream_chunk(content="", finish_reason="stop", model="test", provider="test"),
    ]


@pytest.fixture
def long_chunk_sequence() -> List[StreamChunk]:
    """Long chunk sequence for stress testing."""
    chunks = []
    for i in range(50):
        chunks.append(
            make_stream_chunk(content=f"chunk{i} ", model="test", provider="test")
        )
    chunks.append(
        make_stream_chunk(content="", finish_reason="stop", model="test", provider="test")
    )
    return chunks


# =============================================================================
# Basic Cancellation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_cancel_before_any_chunks(standard_chunks):
    """Test cancellation before receiving any chunks."""
    service = SlowStreamingService(chunks=standard_chunks, delay_per_chunk_ms=100)

    collected_chunks = []

    async def consume_stream():
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected_chunks.append(chunk)

    # Start task and cancel immediately
    task = asyncio.create_task(consume_stream())
    await asyncio.sleep(0.01)  # Give task a chance to start
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    # Verify cancellation happened early
    assert service.chunks_yielded <= 1
    assert service.cancelled


@pytest.mark.asyncio
async def test_cancel_mid_stream(standard_chunks):
    """Test cancellation in the middle of streaming."""
    service = CancellableStreamingService(
        chunks=standard_chunks,
        chunk_delay_ms=20,
        cancel_at_chunk=2,  # Cancel at third chunk
    )

    collected_chunks = []

    async def consume_stream():
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected_chunks.append(chunk)

    task = asyncio.create_task(consume_stream())

    with pytest.raises(asyncio.CancelledError):
        await task

    # Verify partial chunks were collected before cancellation
    assert len(collected_chunks) == 2
    assert collected_chunks[0].content == "Hello"
    assert collected_chunks[1].content == " world"

    # Verify cleanup was called
    assert service.cleanup_called


@pytest.mark.asyncio
async def test_cancel_at_final_chunk(standard_chunks):
    """Test cancellation at the last chunk before finish."""
    service = CancellableStreamingService(
        chunks=standard_chunks,
        chunk_delay_ms=10,
        cancel_at_chunk=3,  # Cancel at final chunk
    )

    collected_chunks = []

    async def consume_stream():
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected_chunks.append(chunk)

    task = asyncio.create_task(consume_stream())

    with pytest.raises(asyncio.CancelledError):
        await task

    # Verify we got most chunks except the finish chunk
    assert len(collected_chunks) == 3
    assert service.cleanup_called


# =============================================================================
# Cleanup and Resource Tests
# =============================================================================

@pytest.mark.asyncio
async def test_cleanup_called_on_cancellation():
    """Test that cleanup is always called even on cancellation."""
    chunks = [make_stream_chunk(content=f"chunk{i}") for i in range(10)]

    service = CancellableStreamingService(
        chunks=chunks,
        chunk_delay_ms=10,
    )

    async def consume_stream():
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            pass

    task = asyncio.create_task(consume_stream())
    await asyncio.sleep(0.05)  # Let a few chunks through
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    # Verify cleanup was called despite cancellation
    assert service.cleanup_called


@pytest.mark.asyncio
async def test_multiple_consumers_one_cancelled():
    """Test multiple consumers where one is cancelled."""
    chunks = [
        make_stream_chunk(content="A", model="test", provider="test"),
        make_stream_chunk(content="B", model="test", provider="test"),
        make_stream_chunk(content="C", model="test", provider="test"),
        make_stream_chunk(content="", finish_reason="stop", model="test", provider="test"),
    ]

    service1 = CancellableStreamingService(chunks=chunks, chunk_delay_ms=20)
    service2 = CancellableStreamingService(chunks=chunks, chunk_delay_ms=20)

    collected1 = []
    collected2 = []

    async def consume1():
        async for chunk in service1.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected1.append(chunk)

    async def consume2():
        async for chunk in service2.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected2.append(chunk)

    # Start both tasks
    task1 = asyncio.create_task(consume1())
    task2 = asyncio.create_task(consume2())

    # Cancel task1 mid-stream
    await asyncio.sleep(0.04)
    task1.cancel()

    # Wait for both to complete/cancel
    try:
        await task1
    except asyncio.CancelledError:
        pass

    await task2

    # Verify task1 was cancelled but task2 completed
    assert len(collected1) < len(chunks)
    assert len(collected2) == len(chunks)
    assert service1.cleanup_called
    assert service2.cleanup_called


# =============================================================================
# Timeout Tests
# =============================================================================

@pytest.mark.asyncio
async def test_timeout_slow_stream():
    """Test timeout on a stream that's too slow."""
    chunks = [
        make_stream_chunk(content="Slow", model="test", provider="test"),
        make_stream_chunk(content=" stream", model="test", provider="test"),
        make_stream_chunk(content="", finish_reason="stop", model="test", provider="test"),
    ]

    service = SlowStreamingService(chunks=chunks, delay_per_chunk_ms=200)

    collected_chunks = []

    async def consume_stream():
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected_chunks.append(chunk)

    task = asyncio.create_task(consume_stream())

    # Wait with timeout
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(task, timeout=0.3)

    # Verify we got some chunks but not all
    assert service.chunks_yielded < len(chunks)
    assert service.cancelled


@pytest.mark.asyncio
async def test_timeout_hanging_stream():
    """Test timeout recovery from a hanging stream."""
    service = HangingStreamingService(chunks_before_hang=2)

    collected_chunks = []

    async def consume_stream():
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected_chunks.append(chunk)

    task = asyncio.create_task(consume_stream())

    # Wait with timeout
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(task, timeout=0.1)

    # Verify we got initial chunks before hang
    assert len(collected_chunks) == 2
    assert collected_chunks[0].content == "Start"
    assert collected_chunks[1].content == " middle"
    assert service.hung
    assert service.cancelled_while_hung


# =============================================================================
# Exception During Stream Tests
# =============================================================================

@pytest.mark.asyncio
async def test_exception_mid_stream():
    """Test exception raised during streaming."""
    chunks = [
        make_stream_chunk(content="Before", model="test", provider="test"),
        make_stream_chunk(content=" error", model="test", provider="test"),
        make_stream_chunk(content=" after", model="test", provider="test"),
    ]

    service = CancellableStreamingService(
        chunks=chunks,
        chunk_delay_ms=10,
        raise_at_chunk=1,
        exception_to_raise=RuntimeError("Stream failed"),
    )

    collected_chunks = []

    async def consume_stream():
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected_chunks.append(chunk)

    task = asyncio.create_task(consume_stream())

    with pytest.raises(RuntimeError, match="Stream failed"):
        await task

    # Verify we got chunk before exception
    assert len(collected_chunks) == 1
    assert collected_chunks[0].content == "Before"

    # Verify cleanup was called
    assert service.cleanup_called


@pytest.mark.asyncio
async def test_exception_on_first_chunk():
    """Test exception on the very first chunk."""
    chunks = [
        make_stream_chunk(content="Never", model="test", provider="test"),
    ]

    service = CancellableStreamingService(
        chunks=chunks,
        chunk_delay_ms=10,
        raise_at_chunk=0,
        exception_to_raise=ValueError("Immediate failure"),
    )

    collected_chunks = []

    async def consume_stream():
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected_chunks.append(chunk)

    task = asyncio.create_task(consume_stream())

    with pytest.raises(ValueError, match="Immediate failure"):
        await task

    # Verify no chunks were collected
    assert len(collected_chunks) == 0
    assert service.cleanup_called


# =============================================================================
# Concurrent Cancellation Stress Tests
# =============================================================================

@pytest.mark.asyncio
async def test_concurrent_streams_all_cancelled(long_chunk_sequence):
    """Test cancelling multiple concurrent streams."""
    num_streams = 10
    services = [
        CancellableStreamingService(chunks=long_chunk_sequence, chunk_delay_ms=5)
        for _ in range(num_streams)
    ]

    tasks = []

    async def consume_stream(service):
        collected = []
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected.append(chunk)
        return collected

    # Start all tasks
    for service in services:
        task = asyncio.create_task(consume_stream(service))
        tasks.append(task)

    # Let them run a bit
    await asyncio.sleep(0.05)

    # Cancel all tasks
    for task in tasks:
        task.cancel()

    # Collect results
    cancelled_count = 0
    for task in tasks:
        try:
            await task
        except asyncio.CancelledError:
            cancelled_count += 1

    # Verify all were cancelled
    assert cancelled_count == num_streams

    # Verify all cleaned up
    for service in services:
        assert service.cleanup_called


@pytest.mark.asyncio
async def test_concurrent_streams_some_cancelled(standard_chunks):
    """Test cancelling some streams while others complete."""
    num_streams = 6
    services = [
        CancellableStreamingService(chunks=standard_chunks, chunk_delay_ms=15)
        for _ in range(num_streams)
    ]

    tasks = []

    async def consume_stream(service):
        collected = []
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected.append(chunk)
        return collected

    # Start all tasks
    for service in services:
        task = asyncio.create_task(consume_stream(service))
        tasks.append(task)

    # Let them run a bit
    await asyncio.sleep(0.03)

    # Cancel half of them
    for i in range(0, num_streams, 2):
        tasks[i].cancel()

    # Wait for all to complete or cancel
    results = []
    for task in tasks:
        try:
            result = await task
            results.append(('completed', result))
        except asyncio.CancelledError:
            results.append(('cancelled', None))

    # Verify mix of completed and cancelled
    completed = [r for r in results if r[0] == 'completed']
    cancelled = [r for r in results if r[0] == 'cancelled']

    assert len(cancelled) == num_streams // 2
    assert len(completed) == num_streams // 2

    # Verify all cleaned up
    for service in services:
        assert service.cleanup_called


# =============================================================================
# Partial Content Recovery Tests
# =============================================================================

@pytest.mark.asyncio
async def test_recover_partial_content_on_cancel(standard_chunks):
    """Test that partial content can be recovered after cancellation."""
    service = CancellableStreamingService(
        chunks=standard_chunks,
        chunk_delay_ms=20,
    )

    collected_chunks = []

    async def consume_stream():
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected_chunks.append(chunk)

    task = asyncio.create_task(consume_stream())

    # Cancel after some time
    await asyncio.sleep(0.05)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    # Verify we can reconstruct partial content
    partial_content = "".join(chunk.content for chunk in collected_chunks)

    assert len(partial_content) > 0
    assert partial_content in "Hello world!"
    assert service.cleanup_called


@pytest.mark.asyncio
async def test_empty_partial_content_on_immediate_cancel():
    """Test that immediate cancellation results in empty partial content."""
    chunks = [
        make_stream_chunk(content="Never", model="test", provider="test"),
        make_stream_chunk(content=" seen", model="test", provider="test"),
    ]

    service = SlowStreamingService(chunks=chunks, delay_per_chunk_ms=100)

    collected_chunks = []

    async def consume_stream():
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected_chunks.append(chunk)

    task = asyncio.create_task(consume_stream())

    # Cancel immediately
    await asyncio.sleep(0.001)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    # Verify no content was collected
    partial_content = "".join(chunk.content for chunk in collected_chunks)
    assert partial_content == ""


# =============================================================================
# Edge Cases
# =============================================================================

@pytest.mark.asyncio
async def test_cancel_empty_stream():
    """Test cancelling a stream that yields no chunks."""
    service = CancellableStreamingService(chunks=[], chunk_delay_ms=10)

    collected_chunks = []

    async def consume_stream():
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected_chunks.append(chunk)

    task = asyncio.create_task(consume_stream())
    await asyncio.sleep(0.02)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    # Verify no chunks and cleanup called
    assert len(collected_chunks) == 0
    assert service.cleanup_called


@pytest.mark.asyncio
async def test_cancel_after_completion():
    """Test that cancelling after completion is harmless."""
    chunks = [
        make_stream_chunk(content="Done", finish_reason="stop", model="test", provider="test"),
    ]

    service = CancellableStreamingService(chunks=chunks, chunk_delay_ms=5)

    collected_chunks = []

    async def consume_stream():
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected_chunks.append(chunk)

    task = asyncio.create_task(consume_stream())

    # Wait for completion
    await task

    # Try to cancel after completion (should be no-op)
    task.cancel()

    # Verify completed successfully
    assert len(collected_chunks) == 1
    assert collected_chunks[0].content == "Done"
    assert service.cleanup_called
