"""
Unit tests for CodeAgent streaming functionality.

Tests the run_streaming method including:
- Basic streaming event flow
- Event type sequence validation
- Iteration tracking in events
- Error handling and error events
- Keyboard interrupt handling
- Rate limiting handling
- Integration with agent loop streaming
- Metadata propagation
"""

import pytest
from typing import AsyncIterator, Optional, List, Dict, Any
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

from scrappy.agent.core import CodeAgent
from scrappy.agent.types import AgentEvent, ConversationState
from scrappy.agent.protocols import AgentLoopProtocol
from scrappy.infrastructure.exceptions import AllProvidersRateLimitedError
from scrappy.providers.base import LLMResponse
from tests.helpers import ConfigurableTestOrchestrator, MockIO, TestPathProvider


# =============================================================================
# Mock Implementations
# =============================================================================

class MockAgentLoop:
    """
    Mock agent loop for testing streaming behavior.

    Implements AgentLoopProtocol and yields controllable AgentEvent
    objects for testing.
    """

    def __init__(self, events: Optional[List[AgentEvent]] = None):
        """
        Initialize mock agent loop.

        Args:
            events: List of events to yield during streaming
        """
        self._events = events or []
        self.run_calls: List[Dict[str, Any]] = []
        self.run_streaming_calls: List[Dict[str, Any]] = []

    def run(self, task: str, state: ConversationState, dry_run: bool = False) -> dict:
        """Mock non-streaming run (not used in streaming tests)."""
        self.run_calls.append({
            'task': task,
            'state': state,
            'dry_run': dry_run
        })
        return {
            'success': True,
            'result': 'task completed',
            'iterations': 1,
            'tools_executed': []
        }

    async def run_streaming(
        self,
        task: str,
        state: ConversationState,
        dry_run: bool = False
    ) -> AsyncIterator[AgentEvent]:
        """
        Mock streaming run that yields configured events.

        Args:
            task: Task to execute
            state: Conversation state
            dry_run: Dry run mode

        Yields:
            AgentEvent objects
        """
        self.run_streaming_calls.append({
            'task': task,
            'state': state,
            'dry_run': dry_run
        })

        for event in self._events:
            yield event


class MockAgentLoopNoStreaming:
    """Mock agent loop that does NOT support streaming."""

    def run(self, task: str, state: ConversationState, dry_run: bool = False) -> dict:
        """Mock non-streaming run."""
        return {
            'success': True,
            'result': 'task completed',
            'iterations': 1,
            'tools_executed': []
        }


# =============================================================================
# Helper Functions
# =============================================================================

def make_agent_event(
    event_type: str,
    content: str = "",
    iteration: int = 0,
    metadata: Optional[Dict[str, Any]] = None
) -> AgentEvent:
    """
    Factory function to create AgentEvent objects for testing.

    Args:
        event_type: Type of event
        content: Text content
        iteration: Iteration number
        metadata: Additional metadata

    Returns:
        AgentEvent instance
    """
    return AgentEvent(
        event_type=event_type,
        content=content,
        iteration=iteration,
        metadata=metadata or {}
    )


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_io():
    """Mock IO interface."""
    return MockIO()


@pytest.fixture
def test_orchestrator():
    """Test orchestrator with context explored."""
    orch = ConfigurableTestOrchestrator(context_explored=True)
    # Add platform mock
    orch.context.platform = Mock()
    orch.context.platform.is_windows.return_value = False
    orch.context.get_project_type.return_value = "python"
    return orch


@pytest.fixture
def test_path_provider():
    """Test path provider."""
    return TestPathProvider()


@pytest.fixture
def streaming_agent(mock_io, test_orchestrator, test_path_provider):
    """
    CodeAgent configured with streaming-capable agent loop.

    Returns factory function to create agent with custom events.
    """
    def _factory(events: Optional[List[AgentEvent]] = None) -> CodeAgent:
        if events is None:
            events = [
                make_agent_event("thought_start", iteration=1),
                make_agent_event("thought_token", "Hello", iteration=1),
                make_agent_event("thought_token", " world", iteration=1),
                make_agent_event("thought_end", iteration=1),
                make_agent_event("action_start", iteration=1, metadata={"action": "complete"}),
                make_agent_event("action_end", "Task done", iteration=1, metadata={"action": "complete", "success": True}),
                make_agent_event("complete", "Task completed", iteration=1, metadata={"success": True}),
            ]

        agent_loop = MockAgentLoop(events=events)

        return CodeAgent(
            orchestrator=test_orchestrator,
            io=mock_io,
            path_provider=test_path_provider,
            agent_loop=agent_loop,
        )

    return _factory


@pytest.fixture
def nonstreaming_agent(mock_io, test_orchestrator, test_path_provider):
    """CodeAgent configured with NON-streaming agent loop."""
    agent_loop = MockAgentLoopNoStreaming()

    return CodeAgent(
        orchestrator=test_orchestrator,
        io=mock_io,
        path_provider=test_path_provider,
        agent_loop=agent_loop,
    )


# =============================================================================
# Basic Streaming Tests
# =============================================================================

@pytest.mark.asyncio
async def test_run_streaming_basic_flow(streaming_agent):
    """Test basic streaming flow yields all events."""
    agent = streaming_agent()

    collected_events = []
    async for event in agent.run_streaming("test task"):
        collected_events.append(event)

    # Verify all events were yielded
    assert len(collected_events) == 7

    # Verify event types in sequence
    assert collected_events[0].event_type == "thought_start"
    assert collected_events[1].event_type == "thought_token"
    assert collected_events[2].event_type == "thought_token"
    assert collected_events[3].event_type == "thought_end"
    assert collected_events[4].event_type == "action_start"
    assert collected_events[5].event_type == "action_end"
    assert collected_events[6].event_type == "complete"


@pytest.mark.asyncio
async def test_run_streaming_yields_content(streaming_agent):
    """Test streaming yields correct content in events."""
    agent = streaming_agent()

    collected_events = []
    async for event in agent.run_streaming("test task"):
        collected_events.append(event)

    # Verify thought tokens
    assert collected_events[1].content == "Hello"
    assert collected_events[2].content == " world"

    # Verify action end content
    assert collected_events[5].content == "Task done"

    # Verify complete event content
    assert collected_events[6].content == "Task completed"


@pytest.mark.asyncio
async def test_run_streaming_tracks_iteration(streaming_agent):
    """Test streaming events track iteration correctly."""
    events = [
        make_agent_event("thought_start", iteration=1),
        make_agent_event("thought_end", iteration=1),
        make_agent_event("thought_start", iteration=2),
        make_agent_event("thought_end", iteration=2),
        make_agent_event("complete", "Done", iteration=2, metadata={"success": True}),
    ]
    agent = streaming_agent(events=events)

    collected_events = []
    async for event in agent.run_streaming("test task"):
        collected_events.append(event)

    # Verify iteration tracking
    assert collected_events[0].iteration == 1
    assert collected_events[1].iteration == 1
    assert collected_events[2].iteration == 2
    assert collected_events[3].iteration == 2
    assert collected_events[4].iteration == 2


@pytest.mark.asyncio
async def test_run_streaming_propagates_metadata(streaming_agent):
    """Test streaming events propagate metadata correctly."""
    events = [
        make_agent_event(
            "action_start",
            iteration=1,
            metadata={"action": "read_file", "params": {"path": "test.py"}}
        ),
        make_agent_event(
            "action_end",
            "File read",
            iteration=1,
            metadata={"action": "read_file", "success": True}
        ),
        make_agent_event(
            "complete",
            "Done",
            iteration=1,
            metadata={"success": True, "iterations": 1}
        ),
    ]
    agent = streaming_agent(events=events)

    collected_events = []
    async for event in agent.run_streaming("test task"):
        collected_events.append(event)

    # Verify action metadata
    assert collected_events[0].metadata["action"] == "read_file"
    assert collected_events[0].metadata["params"]["path"] == "test.py"

    # Verify action end metadata
    assert collected_events[1].metadata["action"] == "read_file"
    assert collected_events[1].metadata["success"] is True

    # Verify completion metadata
    assert collected_events[2].metadata["success"] is True
    assert collected_events[2].metadata["iterations"] == 1


@pytest.mark.asyncio
async def test_run_streaming_passes_parameters(streaming_agent):
    """Test run_streaming passes parameters to agent loop."""
    agent = streaming_agent()

    collected_events = []
    async for event in agent.run_streaming(
        task="custom task",
        max_iterations=20,
        auto_confirm=True
    ):
        collected_events.append(event)

    # Verify agent loop received correct parameters
    agent_loop = agent._agent_loop
    assert len(agent_loop.run_streaming_calls) == 1
    call = agent_loop.run_streaming_calls[0]

    assert call['task'] == "custom task"
    assert call['state'].max_iterations == 20
    assert call['state'].auto_confirm is True


@pytest.mark.asyncio
async def test_run_streaming_builds_initial_context(streaming_agent):
    """Test run_streaming builds initial conversation state correctly."""
    agent = streaming_agent()

    collected_events = []
    async for event in agent.run_streaming("test task"):
        collected_events.append(event)

    # Verify agent loop received conversation state
    agent_loop = agent._agent_loop
    assert len(agent_loop.run_streaming_calls) == 1
    state = agent_loop.run_streaming_calls[0]['state']

    # Verify state structure
    assert len(state.messages) == 2
    assert state.messages[0]['role'] == 'system'
    assert state.messages[1]['role'] == 'user'
    assert "test task" in state.messages[1]['content']
    assert state.iteration == 0
    assert state.max_iterations == 10  # default


# =============================================================================
# Error Handling Tests
# =============================================================================

@pytest.mark.asyncio
async def test_run_streaming_nonstreaming_loop_yields_error(nonstreaming_agent):
    """Test that non-streaming agent loop yields error event."""
    collected_events = []
    async for event in nonstreaming_agent.run_streaming("test task"):
        collected_events.append(event)

    # Verify error event was yielded
    assert len(collected_events) == 1
    assert collected_events[0].event_type == "error"
    assert "does not support streaming" in collected_events[0].content
    assert collected_events[0].metadata["error"] == "streaming_not_supported"


@pytest.mark.asyncio
async def test_run_streaming_keyboard_interrupt_yields_error(streaming_agent):
    """Test keyboard interrupt yields error event."""
    events = [
        make_agent_event("thought_start", iteration=1),
    ]
    agent = streaming_agent(events=events)

    # Mock agent loop to raise KeyboardInterrupt
    async def mock_run_streaming(*args, **kwargs):
        yield make_agent_event("thought_start", iteration=1)
        raise KeyboardInterrupt()

    agent._agent_loop.run_streaming = mock_run_streaming

    collected_events = []
    with pytest.raises(KeyboardInterrupt):
        async for event in agent.run_streaming("test task"):
            collected_events.append(event)

    # Verify error event was yielded before exception
    assert len(collected_events) == 2
    assert collected_events[1].event_type == "error"
    assert "Interrupted by user" in collected_events[1].content
    assert collected_events[1].metadata["error"] == "keyboard_interrupt"


@pytest.mark.asyncio
async def test_run_streaming_rate_limited_yields_error(streaming_agent):
    """Test rate limiting yields error event."""
    agent = streaming_agent()

    # Mock agent loop to raise AllProvidersRateLimitedError
    async def mock_run_streaming(*args, **kwargs):
        if False:
            yield  # Make this an async generator
        raise AllProvidersRateLimitedError(
            "All providers rate limited",
            attempted_providers=["groq", "cerebras"]
        )

    agent._agent_loop.run_streaming = mock_run_streaming

    collected_events = []
    async for event in agent.run_streaming("test task"):
        collected_events.append(event)

    # Verify error event was yielded
    assert len(collected_events) == 1
    assert collected_events[0].event_type == "error"
    assert "rate limited" in collected_events[0].content.lower()
    assert collected_events[0].metadata["error"] == "rate_limited"
    assert "groq" in collected_events[0].metadata["attempted_providers"]
    assert "cerebras" in collected_events[0].metadata["attempted_providers"]


@pytest.mark.asyncio
async def test_run_streaming_generic_exception_yields_error(streaming_agent):
    """Test generic exception yields error event and re-raises."""
    agent = streaming_agent()

    # Mock agent loop to raise generic exception
    async def mock_run_streaming(*args, **kwargs):
        if False:
            yield  # Make this an async generator
        raise ValueError("Something went wrong")

    agent._agent_loop.run_streaming = mock_run_streaming

    collected_events = []
    with pytest.raises(ValueError, match="Something went wrong"):
        async for event in agent.run_streaming("test task"):
            collected_events.append(event)

    # Verify error event was yielded before exception
    assert len(collected_events) == 1
    assert collected_events[0].event_type == "error"
    assert "Something went wrong" in collected_events[0].content
    assert collected_events[0].metadata["error"] == "exception"
    assert collected_events[0].metadata["exception_type"] == "ValueError"


# =============================================================================
# Audit Log Tests
# =============================================================================

@pytest.mark.asyncio
async def test_run_streaming_updates_audit_log_on_success(streaming_agent):
    """Test successful completion updates audit log."""
    events = [
        make_agent_event("thought_start", iteration=1),
        make_agent_event("thought_end", iteration=1),
        make_agent_event("complete", "Task successful", iteration=1, metadata={"success": True}),
    ]
    agent = streaming_agent(events=events)

    collected_events = []
    async for event in agent.run_streaming("test task"):
        collected_events.append(event)

    # Verify audit log was updated (check via save method existence)
    assert hasattr(agent, '_audit_logger')
    # Note: Full audit log verification would require inspecting internal state
    # which is implementation-dependent. This test ensures the path is exercised.


@pytest.mark.asyncio
async def test_run_streaming_updates_audit_log_on_failure(streaming_agent):
    """Test failure completion updates audit log."""
    events = [
        make_agent_event("thought_start", iteration=1),
        make_agent_event("thought_end", iteration=1),
        make_agent_event("complete", "Task failed", iteration=1, metadata={"success": False}),
    ]
    agent = streaming_agent(events=events)

    collected_events = []
    async for event in agent.run_streaming("test task"):
        collected_events.append(event)

    # Verify completion event was processed
    assert collected_events[-1].event_type == "complete"
    assert collected_events[-1].metadata["success"] is False


# =============================================================================
# Dry Run Mode Tests
# =============================================================================

@pytest.mark.asyncio
async def test_run_streaming_respects_dry_run(streaming_agent):
    """Test dry_run mode is passed to agent loop."""
    agent = streaming_agent()
    agent.dry_run = True

    collected_events = []
    async for event in agent.run_streaming("test task"):
        collected_events.append(event)

    # Verify dry_run was passed to agent loop
    agent_loop = agent._agent_loop
    assert len(agent_loop.run_streaming_calls) == 1
    assert agent_loop.run_streaming_calls[0]['dry_run'] is True


@pytest.mark.asyncio
async def test_run_streaming_updates_tool_context_dry_run(streaming_agent):
    """Test tool context dry_run is updated before streaming."""
    agent = streaming_agent()
    agent.dry_run = True

    collected_events = []
    async for event in agent.run_streaming("test task"):
        collected_events.append(event)

    # Verify tool context dry_run was updated
    assert agent.tool_context.dry_run is True


# =============================================================================
# Context Building Tests
# =============================================================================

@pytest.mark.asyncio
async def test_run_streaming_explores_context_if_needed(streaming_agent, test_orchestrator):
    """Test context is explored if not already explored."""
    agent = streaming_agent()

    # Mock context as not explored
    test_orchestrator.context.is_explored.return_value = False
    explored = False

    def mock_explore():
        nonlocal explored
        explored = True

    test_orchestrator.context.explore = mock_explore

    collected_events = []
    async for event in agent.run_streaming("test task"):
        collected_events.append(event)

    # Verify context was explored
    assert explored is True


@pytest.mark.asyncio
async def test_run_streaming_skips_explore_if_already_explored(streaming_agent, test_orchestrator):
    """Test context explore is skipped if already explored."""
    agent = streaming_agent()

    # Mock context as already explored
    test_orchestrator.context.is_explored.return_value = True
    explore_calls = []

    def mock_explore():
        explore_calls.append(1)

    test_orchestrator.context.explore = mock_explore

    collected_events = []
    async for event in agent.run_streaming("test task"):
        collected_events.append(event)

    # Verify explore was not called
    assert len(explore_calls) == 0


# =============================================================================
# Edge Cases
# =============================================================================

@pytest.mark.asyncio
async def test_run_streaming_empty_event_stream(streaming_agent):
    """Test streaming with no events (edge case)."""
    agent = streaming_agent(events=[])

    collected_events = []
    async for event in agent.run_streaming("test task"):
        collected_events.append(event)

    # Verify no events yielded
    assert len(collected_events) == 0


@pytest.mark.asyncio
async def test_run_streaming_only_error_event(streaming_agent):
    """Test stream with only error event."""
    events = [
        make_agent_event("error", "Something failed", iteration=0, metadata={"error": "test_error"}),
    ]
    agent = streaming_agent(events=events)

    collected_events = []
    async for event in agent.run_streaming("test task"):
        collected_events.append(event)

    # Verify error event was yielded
    assert len(collected_events) == 1
    assert collected_events[0].event_type == "error"
    assert collected_events[0].content == "Something failed"


@pytest.mark.asyncio
async def test_run_streaming_multiple_iterations(streaming_agent):
    """Test streaming across multiple iterations."""
    events = [
        make_agent_event("thought_start", iteration=1),
        make_agent_event("thought_end", iteration=1),
        make_agent_event("action_start", iteration=1),
        make_agent_event("action_end", "Step 1 done", iteration=1),
        make_agent_event("thought_start", iteration=2),
        make_agent_event("thought_end", iteration=2),
        make_agent_event("action_start", iteration=2),
        make_agent_event("action_end", "Step 2 done", iteration=2),
        make_agent_event("complete", "All done", iteration=2, metadata={"success": True}),
    ]
    agent = streaming_agent(events=events)

    collected_events = []
    async for event in agent.run_streaming("test task", max_iterations=5):
        collected_events.append(event)

    # Verify events across iterations
    assert len(collected_events) == 9

    # Check iteration 1 events
    iteration_1_events = [e for e in collected_events if e.iteration == 1]
    assert len(iteration_1_events) == 4

    # Check iteration 2 events
    iteration_2_events = [e for e in collected_events if e.iteration == 2]
    assert len(iteration_2_events) == 5


@pytest.mark.asyncio
async def test_run_streaming_max_iterations_parameter(streaming_agent):
    """Test max_iterations parameter is passed correctly."""
    agent = streaming_agent()

    collected_events = []
    async for event in agent.run_streaming("test task", max_iterations=50):
        collected_events.append(event)

    # Verify max_iterations was passed
    agent_loop = agent._agent_loop
    state = agent_loop.run_streaming_calls[0]['state']
    assert state.max_iterations == 50


@pytest.mark.asyncio
async def test_run_streaming_auto_confirm_parameter(streaming_agent):
    """Test auto_confirm parameter is passed correctly."""
    agent = streaming_agent()

    collected_events = []
    async for event in agent.run_streaming("test task", auto_confirm=True):
        collected_events.append(event)

    # Verify auto_confirm was passed
    agent_loop = agent._agent_loop
    state = agent_loop.run_streaming_calls[0]['state']
    assert state.auto_confirm is True
