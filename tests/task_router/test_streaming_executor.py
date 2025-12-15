"""
Unit tests for ResearchExecutor streaming functionality.

Tests the execute_streaming method including:
- General research streaming with direct LLM response
- Codebase research fallback to non-streaming
- Streaming output protocol integration
- Error handling during streaming
- Edge cases (empty streams, provider failures)
"""

import pytest
from typing import Optional, List, Any, AsyncIterator
from unittest.mock import Mock, AsyncMock
from pathlib import Path

from scrappy.task_router.strategies.research_executor import ResearchExecutor
from scrappy.task_router.strategies.base import ExecutionResult
from scrappy.task_router.classifier import ClassifiedTask, TaskType
from scrappy.task_router.strategies.research_subtype import ResearchSubtype
from scrappy.task_router.strategies.research_subclassifier import SubclassificationResult
from scrappy.orchestrator.types import StreamChunk
from tests.helpers import (
    make_stream_chunk,
    CapturingStreamOutput,
)


# =============================================================================
# Mock Implementations
# =============================================================================

class MockStreamingOrchestrator:
    """
    Mock orchestrator that supports streaming.

    Implements stream_delegate for testing ResearchExecutor streaming.
    """

    def __init__(self, stream_chunks: Optional[List[StreamChunk]] = None):
        """
        Initialize mock streaming orchestrator.

        Args:
            stream_chunks: List of chunks to yield during streaming
        """
        self._stream_chunks = stream_chunks or []
        self.stream_calls: List[dict] = []
        self.delegate_calls: List[dict] = []
        self.brain = "cerebras"  # Default provider fallback
        self.context = Mock()
        self.context.is_explored.return_value = False
        self.context.get_summary.return_value = None
        self.context.get_cached_file_index.return_value = None
        self.context.is_semantic_search_ready.return_value = False

    async def stream_delegate(
        self,
        provider_name: str,
        prompt: str,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Mock streaming delegate that yields configured chunks.

        Args:
            provider_name: Provider/model group name
            prompt: User prompt
            **kwargs: Additional params

        Yields:
            StreamChunk objects
        """
        self.stream_calls.append({
            'provider_name': provider_name,
            'prompt': prompt,
            **kwargs
        })

        for chunk in self._stream_chunks:
            yield chunk

    def delegate(self, provider: str, prompt: str, **kwargs):
        """Non-streaming delegate (for fallback tests)."""
        self.delegate_calls.append({
            'provider': provider,
            'prompt': prompt,
            **kwargs
        })

        # Return a mock response
        from scrappy.providers.base import LLMResponse
        return LLMResponse(
            content="Non-streaming response",
            model="test-model",
            provider=provider,
            tokens_used=50,
        )


class MockNonStreamingOrchestrator:
    """
    Mock orchestrator that does NOT support streaming.

    Should cause execute_streaming to fall back to execute().
    """

    def __init__(self):
        """Initialize mock non-streaming orchestrator."""
        self.delegate_calls: List[dict] = []
        self.brain = "cerebras"  # Default provider fallback
        self.context = Mock()
        self.context.is_explored.return_value = False
        self.context.get_summary.return_value = None
        self.context.get_cached_file_index.return_value = None
        self.context.is_semantic_search_ready.return_value = False

    def delegate(self, provider: str, prompt: str, **kwargs):
        """Non-streaming delegate."""
        self.delegate_calls.append({
            'provider': provider,
            'prompt': prompt,
            **kwargs
        })

        from scrappy.providers.base import LLMResponse
        return LLMResponse(
            content="Non-streaming fallback",
            model="test-model",
            provider=provider,
            tokens_used=50,
        )


class MockSubclassifier:
    """Mock research subclassifier with configurable results."""

    def __init__(self, subtype: ResearchSubtype = ResearchSubtype.GENERAL):
        """
        Initialize mock subclassifier.

        Args:
            subtype: Research subtype to return
        """
        self._subtype = subtype
        self.calls: List[str] = []

    def classify_with_matches(self, query: str, file_index: Optional[dict]) -> SubclassificationResult:
        """
        Mock classification that returns configured subtype.

        Args:
            query: User query
            file_index: File index (ignored)

        Returns:
            SubclassificationResult with configured subtype
        """
        self.calls.append(query)
        return SubclassificationResult(
            subtype=self._subtype,
            matched_files=(),
        )


class MockToolBundle:
    """Mock tool bundle that returns empty tools."""

    def has_tools(self) -> bool:
        """Check if tools are available."""
        return False

    def has_web_tools(self) -> bool:
        """Check if web tools are available."""
        return False

    def get_tool_descriptions(self) -> Optional[str]:
        """Get tool descriptions."""
        return None

    def get_web_tool_descriptions(self) -> Optional[str]:
        """Get web tool descriptions."""
        return None


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def classified_task():
    """Create a basic classified research task."""
    return ClassifiedTask(
        task_type=TaskType.RESEARCH,
        original_input="What is Python?",
        confidence=0.95,
        reasoning="General knowledge query about Python",
        complexity_score=1,
        extracted_files=(),
        extracted_directories=(),
    )


@pytest.fixture
def mock_output():
    """Mock streaming output."""
    return CapturingStreamOutput()


@pytest.fixture
def executor_streaming():
    """
    Factory for creating ResearchExecutor with streaming orchestrator.

    Returns factory function to create executor with custom chunks.
    """
    def _factory(
        stream_chunks: Optional[List[StreamChunk]] = None,
        subtype: ResearchSubtype = ResearchSubtype.GENERAL,
    ) -> ResearchExecutor:
        if stream_chunks is None:
            chunks = [
                make_stream_chunk(content="Python is ", model="test", provider="test"),
                make_stream_chunk(
                    content="a programming language",
                    finish_reason="stop",
                    model="test",
                    provider="test",
                    metadata={"tokens_used": 25}
                ),
            ]
        else:
            chunks = stream_chunks

        orchestrator = MockStreamingOrchestrator(stream_chunks=chunks)
        subclassifier = MockSubclassifier(subtype=subtype)
        tool_bundle = MockToolBundle()

        return ResearchExecutor(
            orchestrator=orchestrator,
            preferred_provider="cerebras",
            project_root=Path("/test/project"),
            subclassifier=subclassifier,
            tool_bundle=tool_bundle,
        )

    return _factory


@pytest.fixture
def executor_nonstreaming():
    """ResearchExecutor with non-streaming orchestrator."""
    orchestrator = MockNonStreamingOrchestrator()
    subclassifier = MockSubclassifier(subtype=ResearchSubtype.GENERAL)
    tool_bundle = MockToolBundle()

    return ResearchExecutor(
        orchestrator=orchestrator,
        preferred_provider="cerebras",
        project_root=Path("/test/project"),
        subclassifier=subclassifier,
        tool_bundle=tool_bundle,
    )


# =============================================================================
# General Research Streaming Tests
# =============================================================================

@pytest.mark.asyncio
async def test_execute_streaming_general_research_basic(executor_streaming, classified_task, mock_output):
    """Test basic streaming execution for general research."""
    executor = executor_streaming()

    result = await executor.execute_streaming(classified_task, mock_output)

    # Verify result contains accumulated content
    assert result.success is True
    assert result.output == "Python is a programming language"
    assert result.tokens_used > 0
    assert result.metadata['research_subtype'] == "general"
    assert result.metadata['streaming'] is True

    # Verify streaming callbacks were invoked
    assert mock_output.started is True
    assert mock_output.ended is True
    assert len(mock_output.streamed_tokens) == 2
    assert mock_output.streamed_tokens[0] == "Python is "
    assert mock_output.streamed_tokens[1] == "a programming language"


@pytest.mark.asyncio
async def test_execute_streaming_general_research_calls_stream_start(executor_streaming, classified_task, mock_output):
    """Test that stream_start is called with metadata."""
    executor = executor_streaming()

    await executor.execute_streaming(classified_task, mock_output)

    # Verify stream_start was called
    assert mock_output.started is True
    assert len(mock_output.stream_events) > 0

    # Find stream_start event
    start_events = [e for e in mock_output.stream_events if e['event'] == 'start']
    assert len(start_events) == 1

    start_event = start_events[0]
    assert start_event['metadata']['task_type'] == "research"


@pytest.mark.asyncio
async def test_execute_streaming_general_research_calls_stream_end(executor_streaming, classified_task, mock_output):
    """Test that stream_end is called with token count."""
    executor = executor_streaming()

    await executor.execute_streaming(classified_task, mock_output)

    # Verify stream_end was called
    assert mock_output.ended is True

    # Find stream_end event
    end_events = [e for e in mock_output.stream_events if e['event'] == 'end']
    assert len(end_events) == 1

    end_event = end_events[0]
    assert 'tokens' in end_event['metadata']


@pytest.mark.asyncio
async def test_execute_streaming_general_research_accumulates_chunks(executor_streaming, classified_task, mock_output):
    """Test that streaming accumulates chunks correctly."""
    chunks = [
        make_stream_chunk(content="First ", model="test", provider="test"),
        make_stream_chunk(content="second ", model="test", provider="test"),
        make_stream_chunk(content="third", finish_reason="stop", model="test", provider="test"),
    ]
    executor = executor_streaming(stream_chunks=chunks)

    result = await executor.execute_streaming(classified_task, mock_output)

    # Verify content was accumulated
    assert result.output == "First second third"
    assert len(mock_output.streamed_tokens) == 3


@pytest.mark.asyncio
async def test_execute_streaming_general_research_passes_system_prompt(executor_streaming, classified_task, mock_output):
    """Test that system prompt is passed to streaming delegate."""
    executor = executor_streaming()

    await executor.execute_streaming(classified_task, mock_output)

    # Verify orchestrator received system_prompt
    orchestrator = executor.orchestrator
    assert len(orchestrator.stream_calls) == 1
    call = orchestrator.stream_calls[0]

    assert 'system_prompt' in call
    assert call['system_prompt'] is not None


@pytest.mark.asyncio
async def test_execute_streaming_general_research_uses_preferred_provider(executor_streaming, classified_task, mock_output):
    """Test that preferred provider is used for streaming."""
    executor = executor_streaming()

    await executor.execute_streaming(classified_task, mock_output)

    # Verify preferred provider was used
    orchestrator = executor.orchestrator
    assert len(orchestrator.stream_calls) == 1
    call = orchestrator.stream_calls[0]

    # ResearchExecutor validates and resolves provider
    assert call['provider_name'] in ['cerebras', 'fast', 'quality']


# =============================================================================
# Codebase Research Streaming Tests
# =============================================================================

@pytest.mark.asyncio
async def test_execute_streaming_codebase_research_fallback(executor_streaming, classified_task, mock_output):
    """Test that codebase research falls back to non-streaming execution."""
    executor = executor_streaming(subtype=ResearchSubtype.CODEBASE)

    result = await executor.execute_streaming(classified_task, mock_output)

    # Verify result exists (fallback to execute())
    assert result.success is True
    assert result.metadata['research_subtype'] == "codebase"

    # Verify streaming was NOT used (fallback path)
    # Codebase research with tools doesn't support streaming yet
    assert result.metadata.get('streaming') is None


# =============================================================================
# Fallback and Edge Cases
# =============================================================================

@pytest.mark.asyncio
async def test_execute_streaming_nonstreaming_orchestrator_fallback(executor_nonstreaming, classified_task, mock_output):
    """Test fallback to execute() when orchestrator doesn't support streaming."""
    result = await executor_nonstreaming.execute_streaming(classified_task, mock_output)

    # Verify fallback to non-streaming execution
    assert result.success is True
    assert result.output == "Non-streaming fallback"

    # Verify delegate was called instead of stream_delegate
    orchestrator = executor_nonstreaming.orchestrator
    assert len(orchestrator.delegate_calls) == 1


@pytest.mark.asyncio
async def test_execute_streaming_empty_stream(executor_streaming, classified_task, mock_output):
    """Test streaming with empty chunks (edge case)."""
    executor = executor_streaming(stream_chunks=[])

    result = await executor.execute_streaming(classified_task, mock_output)

    # Verify result with empty content
    assert result.success is True
    assert result.output == ""
    assert result.tokens_used == 0


@pytest.mark.asyncio
async def test_execute_streaming_only_finish_chunk(executor_streaming, classified_task, mock_output):
    """Test stream with only finish chunk (no content)."""
    chunks = [
        make_stream_chunk(content="", finish_reason="stop", model="test", provider="test")
    ]
    executor = executor_streaming(stream_chunks=chunks)

    result = await executor.execute_streaming(classified_task, mock_output)

    # Verify empty response
    assert result.success is True
    assert result.output == ""


@pytest.mark.asyncio
async def test_execute_streaming_no_finish_reason(executor_streaming, classified_task, mock_output):
    """Test stream that ends without finish_reason."""
    chunks = [
        make_stream_chunk(content="Incomplete", model="test", provider="test")
    ]
    executor = executor_streaming(stream_chunks=chunks)

    result = await executor.execute_streaming(classified_task, mock_output)

    # Verify incomplete response is still returned
    assert result.success is True
    assert result.output == "Incomplete"


@pytest.mark.asyncio
async def test_execute_streaming_handles_exception(executor_streaming, classified_task, mock_output):
    """Test error handling during streaming execution."""
    # Create executor that will raise exception during streaming
    class FailingOrchestrator:
        brain = "cerebras"
        context = Mock()
        context.is_explored.return_value = False
        context.get_summary.return_value = None
        context.get_cached_file_index.return_value = None
        context.is_semantic_search_ready.return_value = False

        async def stream_delegate(self, **kwargs):
            raise ValueError("Streaming failed")
            # Make this an async generator
            yield  # This line is unreachable but makes it a generator

    orchestrator = FailingOrchestrator()
    subclassifier = MockSubclassifier(subtype=ResearchSubtype.GENERAL)
    tool_bundle = MockToolBundle()

    executor = ResearchExecutor(
        orchestrator=orchestrator,
        preferred_provider="cerebras",
        project_root=Path("/test/project"),
        subclassifier=subclassifier,
        tool_bundle=tool_bundle,
    )

    result = await executor.execute_streaming(classified_task, mock_output)

    # Verify error was captured in result
    assert result.success is False
    assert "failed" in result.error.lower()


# =============================================================================
# Metadata and Tracking Tests
# =============================================================================

@pytest.mark.asyncio
async def test_execute_streaming_includes_metadata(executor_streaming, classified_task, mock_output):
    """Test that streaming result includes correct metadata."""
    executor = executor_streaming()

    result = await executor.execute_streaming(classified_task, mock_output)

    # Verify metadata fields
    assert result.metadata['task_type'] == "research"
    assert result.metadata['research_subtype'] == "general"
    assert result.metadata['complexity'] == classified_task.complexity_score
    assert result.metadata['streaming'] is True
    assert result.metadata['tool_calls'] == []
    assert result.metadata['iterations'] == 1


@pytest.mark.asyncio
async def test_execute_streaming_tracks_execution_time(executor_streaming, classified_task, mock_output):
    """Test that execution time is tracked."""
    executor = executor_streaming()

    result = await executor.execute_streaming(classified_task, mock_output)

    # Verify execution time is recorded
    assert result.execution_time >= 0
    assert result.execution_time < 1.0  # Should be fast for mock


@pytest.mark.asyncio
async def test_execute_streaming_records_provider_used(executor_streaming, classified_task, mock_output):
    """Test that provider used is recorded in result."""
    executor = executor_streaming()

    result = await executor.execute_streaming(classified_task, mock_output)

    # Verify provider is recorded
    assert result.provider_used is not None
    assert len(result.provider_used) > 0


@pytest.mark.asyncio
async def test_execute_streaming_extracts_token_count_from_chunk(executor_streaming, classified_task, mock_output):
    """Test that token count is extracted from final chunk metadata."""
    chunks = [
        make_stream_chunk(
            content="Test",
            finish_reason="stop",
            model="test",
            provider="test",
            metadata={"tokens_used": 42}
        )
    ]
    executor = executor_streaming(stream_chunks=chunks)

    result = await executor.execute_streaming(classified_task, mock_output)

    # Verify token count was extracted
    assert result.tokens_used == 42


# =============================================================================
# Classification and Routing Tests
# =============================================================================

@pytest.mark.asyncio
async def test_execute_streaming_calls_subclassifier(executor_streaming, classified_task, mock_output):
    """Test that subclassifier is invoked to determine research type."""
    executor = executor_streaming()

    await executor.execute_streaming(classified_task, mock_output)

    # Verify subclassifier was called
    subclassifier = executor._subclassifier
    assert len(subclassifier.calls) == 1
    assert subclassifier.calls[0] == classified_task.original_input


@pytest.mark.asyncio
async def test_execute_streaming_routes_based_on_subtype(executor_streaming, classified_task, mock_output):
    """Test that execution route is based on research subtype."""
    # Test GENERAL route
    executor_general = executor_streaming(subtype=ResearchSubtype.GENERAL)
    result_general = await executor_general.execute_streaming(classified_task, mock_output)
    assert result_general.metadata['research_subtype'] == "general"

    # Test CODEBASE route (falls back to non-streaming)
    executor_codebase = executor_streaming(subtype=ResearchSubtype.CODEBASE)
    result_codebase = await executor_codebase.execute_streaming(classified_task, mock_output)
    assert result_codebase.metadata['research_subtype'] == "codebase"


# =============================================================================
# Output Protocol Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_execute_streaming_output_receives_all_tokens(executor_streaming, classified_task, mock_output):
    """Test that output protocol receives all streamed tokens."""
    chunks = [
        make_stream_chunk(content="A", model="test", provider="test"),
        make_stream_chunk(content="B", model="test", provider="test"),
        make_stream_chunk(content="C", finish_reason="stop", model="test", provider="test"),
    ]
    executor = executor_streaming(stream_chunks=chunks)

    await executor.execute_streaming(classified_task, mock_output)

    # Verify all tokens were passed to output
    assert mock_output.get_streamed_text() == "ABC"
    assert len(mock_output.streamed_tokens) == 3


@pytest.mark.asyncio
async def test_execute_streaming_output_stream_lifecycle(executor_streaming, classified_task, mock_output):
    """Test complete streaming lifecycle: start -> tokens -> end."""
    executor = executor_streaming()

    await executor.execute_streaming(classified_task, mock_output)

    # Verify lifecycle events in order
    events = [e['event'] for e in mock_output.stream_events]
    assert events[0] == 'start'
    assert 'token' in events  # At least one token event
    assert events[-1] == 'end'
