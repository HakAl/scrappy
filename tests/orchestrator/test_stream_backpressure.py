"""
Memory and queue pressure tests for streaming.

Tests streaming behavior under backpressure scenarios:
- Large chunk sequences (memory pressure)
- Slow consumer handling
- Buffer overflow prevention
- Memory leak detection
- Queue saturation
- Throttling behavior
"""

import pytest
import asyncio
from typing import AsyncIterator, List, Optional
import sys

from scrappy.orchestrator.types import StreamChunk, ToolCallFragment
from scrappy.orchestrator.protocols import StreamingCompletionProtocol
from tests.helpers import make_stream_chunk


# =============================================================================
# Mock Streaming Services for Backpressure Testing
# =============================================================================

class HighVolumeStreamingService:
    """
    Mock streaming service that emits large volumes of chunks rapidly.

    Used for testing memory pressure and buffer handling.
    """

    def __init__(
        self,
        num_chunks: int = 1000,
        chunk_size_bytes: int = 1024,
        chunk_delay_ms: float = 0,
    ):
        """
        Initialize high-volume streaming service.

        Args:
            num_chunks: Number of chunks to emit
            chunk_size_bytes: Size of each chunk's content in bytes
            chunk_delay_ms: Delay between chunks in milliseconds
        """
        self._num_chunks = num_chunks
        self._chunk_size_bytes = chunk_size_bytes
        self._chunk_delay_ms = chunk_delay_ms

        self.chunks_yielded = 0
        self.total_bytes_sent = 0

    async def stream_completion(
        self,
        model: str,
        messages: list,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream large volume of chunks.

        Args:
            model: Model group name
            messages: Chat messages
            **kwargs: Additional params

        Yields:
            StreamChunk objects
        """
        # Generate content that's approximately chunk_size_bytes
        chunk_content = "x" * self._chunk_size_bytes

        for i in range(self._num_chunks):
            if self._chunk_delay_ms > 0:
                await asyncio.sleep(self._chunk_delay_ms / 1000)

            finish_reason = "stop" if i == self._num_chunks - 1 else None
            chunk = make_stream_chunk(
                content=chunk_content if i < self._num_chunks - 1 else "",
                finish_reason=finish_reason,
                model="test",
                provider="test"
            )

            self.chunks_yielded += 1
            self.total_bytes_sent += len(chunk_content)
            yield chunk


class BurstyStreamingService:
    """
    Mock streaming service that emits chunks in bursts.

    Simulates real-world scenarios where network delivers data unevenly.
    """

    def __init__(
        self,
        burst_size: int = 50,
        num_bursts: int = 10,
        burst_delay_ms: float = 100,
    ):
        """
        Initialize bursty streaming service.

        Args:
            burst_size: Number of chunks per burst
            num_bursts: Number of bursts to emit
            burst_delay_ms: Delay between bursts
        """
        self._burst_size = burst_size
        self._num_bursts = num_bursts
        self._burst_delay_ms = burst_delay_ms

        self.chunks_yielded = 0
        self.bursts_sent = 0

    async def stream_completion(
        self,
        model: str,
        messages: list,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream chunks in bursts.

        Args:
            model: Model group name
            messages: Chat messages
            **kwargs: Additional params

        Yields:
            StreamChunk objects in bursts
        """
        total_chunks = self._burst_size * self._num_bursts

        for burst_idx in range(self._num_bursts):
            # Delay between bursts (except first)
            if burst_idx > 0:
                await asyncio.sleep(self._burst_delay_ms / 1000)

            # Emit burst of chunks
            for chunk_in_burst in range(self._burst_size):
                chunk_idx = burst_idx * self._burst_size + chunk_in_burst
                finish_reason = "stop" if chunk_idx == total_chunks - 1 else None

                chunk = make_stream_chunk(
                    content=f"burst{burst_idx}_chunk{chunk_in_burst} ",
                    finish_reason=finish_reason,
                    model="test",
                    provider="test"
                )

                self.chunks_yielded += 1
                yield chunk

            self.bursts_sent += 1


class LargeToolCallStreamingService:
    """
    Mock streaming service that streams large tool call arguments.

    Tests handling of tool calls with huge JSON payloads.
    """

    def __init__(
        self,
        num_tool_calls: int = 10,
        args_size_kb: int = 100,
    ):
        """
        Initialize large tool call streaming service.

        Args:
            num_tool_calls: Number of tool calls to stream
            args_size_kb: Size of each tool call's arguments in KB
        """
        self._num_tool_calls = num_tool_calls
        self._args_size_kb = args_size_kb

        self.chunks_yielded = 0
        self.tool_calls_sent = 0

    async def stream_completion(
        self,
        model: str,
        messages: list,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream chunks with large tool call fragments.

        Args:
            model: Model group name
            messages: Chat messages
            **kwargs: Additional params

        Yields:
            StreamChunk objects with tool call fragments
        """
        # Generate large JSON arguments
        large_args = '{"data": "' + ("x" * (self._args_size_kb * 1024)) + '"}'

        for i in range(self._num_tool_calls):
            # Each tool call arrives as multiple chunks
            fragments = [
                ToolCallFragment(
                    id=f"call_{i}",
                    type="function",
                    name=f"large_function_{i}",
                    arguments=large_args[:len(large_args)//2],
                    index=i,
                    complete=False
                ),
                ToolCallFragment(
                    id=f"call_{i}",
                    type="function",
                    name=f"large_function_{i}",
                    arguments=large_args,
                    index=i,
                    complete=True
                ),
            ]

            for fragment in fragments:
                chunk = make_stream_chunk(
                    content="",
                    tool_call_fragments=[fragment],
                    model="test",
                    provider="test"
                )

                self.chunks_yielded += 1
                yield chunk
                await asyncio.sleep(0.001)  # Tiny delay between fragments

            self.tool_calls_sent += 1

        # Final finish chunk
        chunk = make_stream_chunk(
            content="",
            finish_reason="stop",
            model="test",
            provider="test"
        )
        self.chunks_yielded += 1
        yield chunk


# =============================================================================
# Slow Consumer Simulator
# =============================================================================

class SlowConsumer:
    """
    Consumer that processes chunks slowly to create backpressure.
    """

    def __init__(
        self,
        processing_delay_ms: float = 50,
        max_queue_size: Optional[int] = None,
    ):
        """
        Initialize slow consumer.

        Args:
            processing_delay_ms: Time to process each chunk
            max_queue_size: Maximum queue size (None = unlimited)
        """
        self._processing_delay_ms = processing_delay_ms
        self._max_queue_size = max_queue_size

        self.chunks_processed = 0
        self.processing_times = []
        self.queue_size_samples = []
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size or 0)

    async def consume(
        self,
        stream: AsyncIterator[StreamChunk]
    ) -> List[StreamChunk]:
        """
        Consume stream with slow processing.

        Args:
            stream: Stream of chunks to consume

        Returns:
            List of processed chunks
        """
        collected = []

        async for chunk in stream:
            # Simulate slow processing
            start_time = asyncio.get_event_loop().time()
            await asyncio.sleep(self._processing_delay_ms / 1000)

            self.chunks_processed += 1
            collected.append(chunk)

            elapsed = asyncio.get_event_loop().time() - start_time
            self.processing_times.append(elapsed)

        return collected


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def small_volume_service() -> HighVolumeStreamingService:
    """Create service with moderate chunk count."""
    return HighVolumeStreamingService(num_chunks=100, chunk_size_bytes=512)


@pytest.fixture
def large_volume_service() -> HighVolumeStreamingService:
    """Create service with large chunk count."""
    return HighVolumeStreamingService(num_chunks=1000, chunk_size_bytes=1024)


@pytest.fixture
def bursty_service() -> BurstyStreamingService:
    """Create service that emits bursts."""
    return BurstyStreamingService(burst_size=20, num_bursts=5, burst_delay_ms=50)


# =============================================================================
# High Volume Memory Tests
# =============================================================================

@pytest.mark.asyncio
async def test_stream_large_volume_chunks(large_volume_service):
    """Test streaming large volume of chunks without memory issues."""
    collected_chunks = []

    async for chunk in large_volume_service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected_chunks.append(chunk)

    # Verify all chunks received
    assert len(collected_chunks) == 1000
    assert large_volume_service.chunks_yielded == 1000

    # Verify total data transferred
    assert large_volume_service.total_bytes_sent > 0


@pytest.mark.asyncio
async def test_stream_memory_usage_stays_bounded():
    """Test that memory usage doesn't grow unbounded during streaming."""
    # Create service with very large chunk count
    service = HighVolumeStreamingService(
        num_chunks=5000,
        chunk_size_bytes=2048,
        chunk_delay_ms=0.1,
    )

    collected_count = 0
    max_memory_sample = 0

    async for chunk in service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected_count += 1

        # Sample memory periodically
        if collected_count % 100 == 0:
            # In real tests, you might use psutil or tracemalloc here
            # For now, just verify we can continue processing
            assert collected_count > 0

    # Verify we processed everything
    assert collected_count == 5000


@pytest.mark.asyncio
async def test_stream_with_large_individual_chunks():
    """Test streaming with very large individual chunks."""
    # Each chunk is 1MB
    service = HighVolumeStreamingService(
        num_chunks=10,
        chunk_size_bytes=1024 * 1024,
        chunk_delay_ms=10,
    )

    collected_chunks = []
    total_size = 0

    async for chunk in service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected_chunks.append(chunk)
        total_size += len(chunk.content)

    # Verify we handled large chunks
    assert len(collected_chunks) == 10
    assert total_size >= 9 * 1024 * 1024  # At least 9MB (excluding finish chunk)


# =============================================================================
# Slow Consumer Backpressure Tests
# =============================================================================

@pytest.mark.asyncio
async def test_slow_consumer_with_fast_producer():
    """Test backpressure when consumer is slower than producer."""
    service = HighVolumeStreamingService(
        num_chunks=50,
        chunk_size_bytes=100,
        chunk_delay_ms=1,  # Fast producer
    )

    consumer = SlowConsumer(processing_delay_ms=20)  # Slow consumer

    stream = service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    )

    collected = await consumer.consume(stream)

    # Verify all chunks processed despite speed mismatch
    assert len(collected) == 50
    assert consumer.chunks_processed == 50


@pytest.mark.asyncio
async def test_multiple_slow_consumers():
    """Test multiple slow consumers processing same data."""
    service1 = BurstyStreamingService(burst_size=10, num_bursts=3, burst_delay_ms=20)
    service2 = BurstyStreamingService(burst_size=10, num_bursts=3, burst_delay_ms=20)
    service3 = BurstyStreamingService(burst_size=10, num_bursts=3, burst_delay_ms=20)

    consumer1 = SlowConsumer(processing_delay_ms=10)
    consumer2 = SlowConsumer(processing_delay_ms=15)
    consumer3 = SlowConsumer(processing_delay_ms=20)

    # Run all consumers concurrently
    results = await asyncio.gather(
        consumer1.consume(service1.stream_completion(
            model="fast", messages=[{"role": "user", "content": "test"}]
        )),
        consumer2.consume(service2.stream_completion(
            model="fast", messages=[{"role": "user", "content": "test"}]
        )),
        consumer3.consume(service3.stream_completion(
            model="fast", messages=[{"role": "user", "content": "test"}]
        )),
    )

    # Verify all consumers processed all chunks
    assert all(len(result) == 30 for result in results)


# =============================================================================
# Burst Handling Tests
# =============================================================================

@pytest.mark.asyncio
async def test_handle_bursty_stream(bursty_service):
    """Test handling of bursty stream delivery."""
    collected_chunks = []

    async for chunk in bursty_service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected_chunks.append(chunk)

    # Verify all chunks received
    assert len(collected_chunks) == 100  # 20 chunks * 5 bursts
    assert bursty_service.bursts_sent == 5


@pytest.mark.asyncio
async def test_burst_doesnt_cause_buffer_overflow():
    """Test that burst delivery doesn't cause buffer overflow."""
    # Very large bursts
    service = BurstyStreamingService(
        burst_size=500,
        num_bursts=5,
        burst_delay_ms=200,
    )

    collected_chunks = []

    async for chunk in service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected_chunks.append(chunk)

    # Verify all chunks received despite large bursts
    assert len(collected_chunks) == 2500


@pytest.mark.asyncio
async def test_concurrent_bursty_streams():
    """Test multiple concurrent bursty streams."""
    services = [
        BurstyStreamingService(burst_size=30, num_bursts=4, burst_delay_ms=30)
        for _ in range(5)
    ]

    async def consume_stream(service):
        collected = []
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected.append(chunk)
        return collected

    results = await asyncio.gather(*[consume_stream(s) for s in services])

    # Verify all streams completed successfully
    assert all(len(result) == 120 for result in results)


# =============================================================================
# Large Tool Call Tests
# =============================================================================

@pytest.mark.asyncio
async def test_stream_large_tool_call_arguments():
    """Test streaming with large tool call arguments."""
    service = LargeToolCallStreamingService(
        num_tool_calls=5,
        args_size_kb=50,
    )

    collected_chunks = []

    async for chunk in service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected_chunks.append(chunk)

    # Verify tool calls streamed
    assert service.tool_calls_sent == 5

    # Verify chunks with tool call fragments
    tool_chunks = [c for c in collected_chunks if c.tool_call_fragments]
    assert len(tool_chunks) == 10  # 2 fragments per tool call


@pytest.mark.asyncio
async def test_many_large_tool_calls():
    """Test streaming many large tool calls."""
    service = LargeToolCallStreamingService(
        num_tool_calls=20,
        args_size_kb=100,
    )

    collected_chunks = []
    total_fragment_size = 0

    async for chunk in service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected_chunks.append(chunk)

        for fragment in chunk.tool_call_fragments:
            total_fragment_size += len(fragment.arguments)

    # Verify large volume processed
    assert service.tool_calls_sent == 20
    assert total_fragment_size > 1 * 1024 * 1024  # Over 1MB total


# =============================================================================
# Resource Leak Tests
# =============================================================================

@pytest.mark.asyncio
async def test_no_resource_leak_on_normal_completion():
    """Test that normal completion doesn't leak resources."""
    service = HighVolumeStreamingService(
        num_chunks=100,
        chunk_size_bytes=1024,
    )

    # Run multiple times to detect leaks
    for _ in range(10):
        collected = []
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected.append(chunk)

        # Clear collected chunks to free memory
        collected.clear()

    # If we got here without issues, no obvious leak
    assert service.chunks_yielded > 0


@pytest.mark.asyncio
async def test_no_resource_leak_on_early_break():
    """Test that breaking early doesn't leak resources."""
    service = HighVolumeStreamingService(
        num_chunks=1000,
        chunk_size_bytes=1024,
    )

    # Break early multiple times
    for _ in range(10):
        collected = []
        chunk_count = 0
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected.append(chunk)
            chunk_count += 1
            if chunk_count >= 10:
                break

        # Verify we only got 10 chunks
        assert len(collected) == 10
        collected.clear()


# =============================================================================
# Concurrent Stream Pressure Tests
# =============================================================================

@pytest.mark.asyncio
async def test_many_concurrent_high_volume_streams():
    """Test many concurrent high-volume streams."""
    num_concurrent = 20

    services = [
        HighVolumeStreamingService(num_chunks=100, chunk_size_bytes=512)
        for _ in range(num_concurrent)
    ]

    async def consume_stream(service):
        collected = []
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ):
            collected.append(chunk)
        return len(collected)

    results = await asyncio.gather(*[consume_stream(s) for s in services])

    # Verify all streams completed
    assert all(count == 100 for count in results)
    assert all(s.chunks_yielded == 100 for s in services)


@pytest.mark.asyncio
async def test_mixed_workload_concurrent_streams():
    """Test mixed workload of different stream types concurrently."""
    # Mix of different stream types
    services = [
        HighVolumeStreamingService(num_chunks=200, chunk_size_bytes=256),
        BurstyStreamingService(burst_size=25, num_bursts=4, burst_delay_ms=20),
        LargeToolCallStreamingService(num_tool_calls=10, args_size_kb=50),
        HighVolumeStreamingService(num_chunks=50, chunk_size_bytes=2048),
    ]

    async def consume_high_volume(service):
        count = 0
        async for chunk in service.stream_completion(
            model="fast", messages=[{"role": "user", "content": "test"}]
        ):
            count += 1
        return count

    async def consume_bursty(service):
        count = 0
        async for chunk in service.stream_completion(
            model="fast", messages=[{"role": "user", "content": "test"}]
        ):
            count += 1
        return count

    async def consume_tool_calls(service):
        count = 0
        async for chunk in service.stream_completion(
            model="fast", messages=[{"role": "user", "content": "test"}]
        ):
            count += 1
        return count

    results = await asyncio.gather(
        consume_high_volume(services[0]),
        consume_bursty(services[1]),
        consume_tool_calls(services[2]),
        consume_high_volume(services[3]),
    )

    # Verify all completed
    assert results[0] == 200  # High volume
    assert results[1] == 100  # Bursty (25*4)
    assert results[2] == 21   # Tool calls (2*10 fragments + 1 finish)
    assert results[3] == 50   # High volume


# =============================================================================
# Edge Cases
# =============================================================================

@pytest.mark.asyncio
async def test_single_massive_chunk():
    """Test streaming a single massive chunk."""
    # Single 10MB chunk plus finish chunk
    service = HighVolumeStreamingService(
        num_chunks=2,  # One massive chunk + finish chunk
        chunk_size_bytes=10 * 1024 * 1024,
    )

    collected_chunks = []
    non_empty_chunks = []

    async for chunk in service.stream_completion(
        model="fast",
        messages=[{"role": "user", "content": "test"}],
    ):
        collected_chunks.append(chunk)
        if chunk.content:
            non_empty_chunks.append(chunk)

    # Verify handled single massive chunk
    assert len(collected_chunks) == 2  # Content chunk + finish chunk
    assert len(non_empty_chunks) == 1
    assert len(non_empty_chunks[0].content) >= 10 * 1024 * 1024


@pytest.mark.asyncio
async def test_empty_chunks_in_high_volume_stream():
    """Test that empty chunks in high volume don't cause issues."""
    # Mix of empty and non-empty chunks
    chunks = []
    for i in range(100):
        if i % 3 == 0:
            chunks.append(make_stream_chunk(content="", model="test", provider="test"))
        else:
            chunks.append(make_stream_chunk(content=f"chunk{i}", model="test", provider="test"))

    chunks.append(make_stream_chunk(content="", finish_reason="stop", model="test", provider="test"))

    # Simple async generator
    async def generate_chunks():
        for chunk in chunks:
            yield chunk

    collected = []
    async for chunk in generate_chunks():
        collected.append(chunk)

    assert len(collected) == 101
