"""
Unit tests for TaskRouter.route_streaming() method.

Tests the streaming routing including:
- Basic streaming with ResearchExecutor (Pattern A)
- Streaming with AgentExecutor (Pattern B - yields events)
- Fallback to non-streaming when strategy doesn't support it
- Shared preparation logic with route()
- Error handling
"""

import pytest
from typing import Optional, List, Dict, Any, AsyncIterator
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from pathlib import Path
from dataclasses import dataclass

from scrappy.task_router.router import TaskRouter
from scrappy.task_router.classifier import ClassifiedTask, TaskType
from scrappy.task_router.strategies.base import ExecutionResult
from scrappy.task_router.config import ClarificationConfig
from scrappy.agent.types import AgentEvent
from tests.helpers import CapturingStreamOutput


# =============================================================================
# Mock Implementations
# =============================================================================

class MockClassifier:
    """Mock classifier that returns configurable results."""

    def __init__(self, task_type: TaskType = TaskType.RESEARCH, confidence: float = 0.95):
        self._task_type = task_type
        self._confidence = confidence

    def classify(self, user_input: str) -> ClassifiedTask:
        return ClassifiedTask(
            task_type=self._task_type,
            original_input=user_input,
            confidence=self._confidence,
            reasoning="Mock classification",
            complexity_score=2,
            requires_planning=False,
            extracted_files=(),
            extracted_directories=(),
        )


class MockStreamingStrategyPatternA:
    """
    Mock strategy with Pattern A: execute_streaming(task, output) -> ExecutionResult.

    This matches ResearchExecutor's pattern.
    """

    def __init__(self, content: str = "Streamed response"):
        self._content = content
        self.execute_streaming_calls: List[dict] = []
        self.execute_calls: List[dict] = []

    @property
    def name(self) -> str:
        return "MockPatternA"

    def can_handle(self, task: ClassifiedTask) -> bool:
        return True

    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        self.execute_calls.append({"task": task})
        return ExecutionResult(
            success=True,
            output="Non-streaming response",
            execution_time=0.1,
            tokens_used=10,
            provider_used="mock",
        )

    async def execute_streaming(
        self,
        task: ClassifiedTask,
        output  # StreamingOutputProtocol
    ) -> ExecutionResult:
        """Stream to output, return result."""
        self.execute_streaming_calls.append({"task": task, "output": output})

        await output.stream_start(metadata={"task_type": "research"})
        for token in self._content.split():
            await output.stream_token(token + " ")
        await output.stream_end(metadata={"tokens": len(self._content.split())})

        return ExecutionResult(
            success=True,
            output=self._content,
            execution_time=0.1,
            tokens_used=len(self._content.split()),
            provider_used="mock",
            metadata={"streaming": True},
        )


class MockStreamingStrategyPatternB:
    """
    Mock strategy with Pattern B: execute_streaming(task) -> AsyncIterator[AgentEvent].

    This matches AgentExecutor's pattern.
    """

    def __init__(self, events: Optional[List[AgentEvent]] = None):
        self._events = events or [
            AgentEvent(event_type="thought_start", content="", iteration=0),
            AgentEvent(event_type="thought_token", content="Thinking...", iteration=0),
            AgentEvent(event_type="thought_end", content="", iteration=0),
            AgentEvent(event_type="complete", content="Done", iteration=1, metadata={"success": True}),
        ]
        self.execute_streaming_calls: List[dict] = []
        self.execute_calls: List[dict] = []

    @property
    def name(self) -> str:
        return "MockPatternB"

    def can_handle(self, task: ClassifiedTask) -> bool:
        return True

    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        self.execute_calls.append({"task": task})
        return ExecutionResult(
            success=True,
            output="Non-streaming response",
            execution_time=0.1,
            tokens_used=10,
            provider_used="mock",
        )

    async def execute_streaming(self, task: ClassifiedTask) -> AsyncIterator[AgentEvent]:
        """Yield events."""
        self.execute_streaming_calls.append({"task": task})
        for event in self._events:
            yield event


class MockNonStreamingStrategy:
    """Mock strategy without streaming support."""

    def __init__(self):
        self.execute_calls: List[dict] = []

    @property
    def name(self) -> str:
        return "MockNonStreaming"

    def can_handle(self, task: ClassifiedTask) -> bool:
        return True

    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        self.execute_calls.append({"task": task})
        return ExecutionResult(
            success=True,
            output="Non-streaming only",
            execution_time=0.1,
            tokens_used=5,
            provider_used="mock",
        )


class MockOutputHandler:
    """Mock output handler."""

    def log_classification(self, **kwargs):
        pass

    def log_info(self, msg: str):
        pass

    def log_provider_selection(self, **kwargs):
        pass

    def log_execution_start(self, strategy_name: str):
        pass


class MockInputHandler:
    """Mock input handler."""

    def __init__(self, confirm_result: bool = True):
        self._confirm_result = confirm_result

    def confirm(self, prompt: str, default: bool = False) -> bool:
        return self._confirm_result


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_output():
    """Create capturing stream output for testing."""
    return CapturingStreamOutput()


@pytest.fixture
def router_with_pattern_a():
    """Router with Pattern A streaming strategy (ResearchExecutor-style)."""
    strategy = MockStreamingStrategyPatternA()
    classifier = MockClassifier(task_type=TaskType.RESEARCH)

    router = TaskRouter(
        orchestrator=None,
        project_root=Path("/test"),
        verbose=False,
        classifier=classifier,
        output_handler=MockOutputHandler(),
        input_handler=MockInputHandler(),
        clarification_config=ClarificationConfig(),
        strategies={TaskType.RESEARCH: strategy},
    )
    router.clarify_on_low_confidence = False
    router.use_llm_classification = False

    return router, strategy


@pytest.fixture
def router_with_pattern_b():
    """Router with Pattern B streaming strategy (AgentExecutor-style)."""
    strategy = MockStreamingStrategyPatternB()
    classifier = MockClassifier(task_type=TaskType.CODE_GENERATION)

    router = TaskRouter(
        orchestrator=None,
        project_root=Path("/test"),
        verbose=False,
        classifier=classifier,
        output_handler=MockOutputHandler(),
        input_handler=MockInputHandler(),
        clarification_config=ClarificationConfig(),
        strategies={TaskType.CODE_GENERATION: strategy},
    )
    router.clarify_on_low_confidence = False
    router.use_llm_classification = False

    return router, strategy


@pytest.fixture
def router_nonstreaming():
    """Router with non-streaming strategy."""
    strategy = MockNonStreamingStrategy()
    classifier = MockClassifier(task_type=TaskType.CONVERSATION)

    router = TaskRouter(
        orchestrator=None,
        project_root=Path("/test"),
        verbose=False,
        classifier=classifier,
        output_handler=MockOutputHandler(),
        input_handler=MockInputHandler(),
        clarification_config=ClarificationConfig(),
        strategies={TaskType.CONVERSATION: strategy},
    )
    router.clarify_on_low_confidence = False
    router.use_llm_classification = False

    return router, strategy


# =============================================================================
# Pattern A Tests (ResearchExecutor-style)
# =============================================================================

@pytest.mark.asyncio
async def test_route_streaming_pattern_a_basic(router_with_pattern_a, mock_output):
    """Test basic streaming with Pattern A strategy."""
    router, strategy = router_with_pattern_a

    result = await router.route_streaming("What is Python?", mock_output)

    # Verify result
    assert result.success is True
    assert result.output == "Streamed response"
    assert result.metadata.get("streaming") is True

    # Verify strategy was called with streaming
    assert len(strategy.execute_streaming_calls) == 1
    assert len(strategy.execute_calls) == 0  # Not the sync version


@pytest.mark.asyncio
async def test_route_streaming_pattern_a_streams_to_output(router_with_pattern_a, mock_output):
    """Test that Pattern A streams tokens to output."""
    router, strategy = router_with_pattern_a

    await router.route_streaming("What is Python?", mock_output)

    # Verify output received tokens
    assert mock_output.started is True
    assert mock_output.ended is True
    assert len(mock_output.streamed_tokens) > 0
    assert "Streamed " in mock_output.get_streamed_text()


@pytest.mark.asyncio
async def test_route_streaming_pattern_a_passes_task(router_with_pattern_a, mock_output):
    """Test that task is passed to strategy."""
    router, strategy = router_with_pattern_a

    await router.route_streaming("Test query", mock_output)

    call = strategy.execute_streaming_calls[0]
    assert call["task"].original_input == "Test query"
    assert call["task"].task_type == TaskType.RESEARCH


# =============================================================================
# Pattern B Tests (AgentExecutor-style)
# =============================================================================

@pytest.mark.asyncio
async def test_route_streaming_pattern_b_basic(router_with_pattern_b, mock_output):
    """Test basic streaming with Pattern B strategy."""
    router, strategy = router_with_pattern_b

    result = await router.route_streaming("Write some code", mock_output)

    # Verify result
    assert result.success is True

    # Verify strategy was called with streaming
    assert len(strategy.execute_streaming_calls) == 1
    assert len(strategy.execute_calls) == 0


@pytest.mark.asyncio
async def test_route_streaming_pattern_b_handles_events(router_with_pattern_b, mock_output):
    """Test that Pattern B events are converted to output tokens."""
    events = [
        AgentEvent(event_type="thought_start", content="", iteration=0),
        AgentEvent(event_type="thought_token", content="Hello", iteration=0),
        AgentEvent(event_type="thought_token", content=" world", iteration=0),
        AgentEvent(event_type="thought_end", content="", iteration=0),
        AgentEvent(event_type="complete", content="Done", iteration=1, metadata={"success": True}),
    ]

    strategy = MockStreamingStrategyPatternB(events=events)
    classifier = MockClassifier(task_type=TaskType.CODE_GENERATION)

    router = TaskRouter(
        orchestrator=None,
        project_root=Path("/test"),
        verbose=False,
        classifier=classifier,
        output_handler=MockOutputHandler(),
        input_handler=MockInputHandler(),
        clarification_config=ClarificationConfig(),
        strategies={TaskType.CODE_GENERATION: strategy},
    )
    router.clarify_on_low_confidence = False
    router.use_llm_classification = False

    await router.route_streaming("Test", mock_output)

    # Verify thought tokens were streamed
    assert "Hello" in mock_output.get_streamed_text()
    assert " world" in mock_output.get_streamed_text()


@pytest.mark.asyncio
async def test_route_streaming_pattern_b_handles_action_events(router_with_pattern_b, mock_output):
    """Test that Pattern B action events are formatted correctly."""
    events = [
        AgentEvent(event_type="action_start", content="", iteration=0, metadata={"action": "read_file"}),
        AgentEvent(event_type="action_end", content="", iteration=0, metadata={"action": "read_file", "success": True}),
        AgentEvent(event_type="complete", content="Done", iteration=1, metadata={"success": True}),
    ]

    strategy = MockStreamingStrategyPatternB(events=events)
    classifier = MockClassifier(task_type=TaskType.CODE_GENERATION)

    router = TaskRouter(
        orchestrator=None,
        project_root=Path("/test"),
        verbose=False,
        classifier=classifier,
        output_handler=MockOutputHandler(),
        input_handler=MockInputHandler(),
        clarification_config=ClarificationConfig(),
        strategies={TaskType.CODE_GENERATION: strategy},
    )
    router.clarify_on_low_confidence = False
    router.use_llm_classification = False

    await router.route_streaming("Test", mock_output)

    output_text = mock_output.get_streamed_text()
    assert "[Action: read_file]" in output_text
    assert "[read_file: done]" in output_text


@pytest.mark.asyncio
async def test_route_streaming_pattern_b_handles_error_event(router_with_pattern_b, mock_output):
    """Test that Pattern B error events result in failed result."""
    events = [
        AgentEvent(event_type="error", content="Something went wrong", iteration=0, metadata={"error": "test_error"}),
    ]

    strategy = MockStreamingStrategyPatternB(events=events)
    classifier = MockClassifier(task_type=TaskType.CODE_GENERATION)

    router = TaskRouter(
        orchestrator=None,
        project_root=Path("/test"),
        verbose=False,
        classifier=classifier,
        output_handler=MockOutputHandler(),
        input_handler=MockInputHandler(),
        clarification_config=ClarificationConfig(),
        strategies={TaskType.CODE_GENERATION: strategy},
    )
    router.clarify_on_low_confidence = False
    router.use_llm_classification = False

    result = await router.route_streaming("Test", mock_output)

    assert result.success is False
    assert "Something went wrong" in result.output


# =============================================================================
# Fallback Tests
# =============================================================================

@pytest.mark.asyncio
async def test_route_streaming_fallback_to_sync(router_nonstreaming, mock_output):
    """Test fallback to execute() when strategy doesn't support streaming."""
    router, strategy = router_nonstreaming

    result = await router.route_streaming("Hello", mock_output)

    # Verify fallback to sync
    assert result.success is True
    assert result.output == "Non-streaming only"

    # Verify sync execute was called
    assert len(strategy.execute_calls) == 1


# =============================================================================
# Shared Logic Tests
# =============================================================================

@pytest.mark.asyncio
async def test_route_streaming_validates_input(mock_output):
    """Test that invalid input is rejected."""
    classifier = MockClassifier()

    router = TaskRouter(
        orchestrator=None,
        project_root=Path("/test"),
        verbose=False,
        classifier=classifier,
        output_handler=MockOutputHandler(),
        input_handler=MockInputHandler(),
        clarification_config=ClarificationConfig(),
    )

    # Empty input should fail validation
    result = await router.route_streaming("", mock_output)

    assert result.success is False
    assert "Invalid input" in result.error


@pytest.mark.asyncio
async def test_route_streaming_respects_provider_hint(router_with_pattern_a, mock_output):
    """Test that provider hint is respected."""
    router, strategy = router_with_pattern_a

    # Add set_provider method to track calls
    strategy.set_provider_calls = []

    def mock_set_provider(provider, model):
        strategy.set_provider_calls.append((provider, model))

    strategy.set_provider = mock_set_provider

    await router.route_streaming("Test", mock_output, provider="fast")

    # Provider should have been resolved and passed
    # (actual resolution depends on provider_resolver)
    assert len(strategy.execute_streaming_calls) == 1


@pytest.mark.asyncio
async def test_route_streaming_returns_classification_metadata(router_with_pattern_a, mock_output):
    """Test that classification metadata is included in result."""
    router, strategy = router_with_pattern_a

    result = await router.route_streaming("What is Python?", mock_output)

    assert "classification" in result.metadata
    classification = result.metadata["classification"]
    assert classification["type"] == "research"


@pytest.mark.asyncio
async def test_route_streaming_cancelled_by_user(mock_output):
    """Test that cancelled execution returns appropriate result."""
    strategy = MockStreamingStrategyPatternA()
    classifier = MockClassifier(task_type=TaskType.DIRECT_COMMAND)

    # Mock input handler that denies confirmation
    input_handler = MockInputHandler(confirm_result=False)

    router = TaskRouter(
        orchestrator=None,
        project_root=Path("/test"),
        verbose=False,
        classifier=classifier,
        output_handler=MockOutputHandler(),
        input_handler=input_handler,
        clarification_config=ClarificationConfig(),
        strategies={TaskType.DIRECT_COMMAND: strategy},
        auto_confirm_direct=False,
    )
    router.clarify_on_low_confidence = False
    router.use_llm_classification = False

    # Create task that will require confirmation
    classifier._task_type = TaskType.DIRECT_COMMAND

    result = await router.route_streaming("rm -rf /", mock_output)

    assert result.success is False
    assert "cancelled" in result.error.lower()


# =============================================================================
# Hook Tests
# =============================================================================

@pytest.mark.asyncio
async def test_route_streaming_applies_post_hooks(router_with_pattern_a, mock_output):
    """Test that post-execution hooks are applied."""
    router, strategy = router_with_pattern_a

    # Add a hook that modifies the result
    def add_metadata_hook(result: ExecutionResult) -> ExecutionResult:
        result.metadata["hook_applied"] = True
        return result

    router.add_post_hook(add_metadata_hook)

    result = await router.route_streaming("Test", mock_output)

    assert result.metadata.get("hook_applied") is True
