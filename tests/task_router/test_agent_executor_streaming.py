"""
Unit tests for AgentExecutor.execute_streaming() method.

Tests the streaming wrapper for CodeAgent.run_streaming() including:
- Basic streaming yields AgentEvent objects
- Event types are correctly propagated
- Task preparation (planning, guidance) is applied
- Resolved provider is passed to CodeAgent
- Error handling (ImportError, Exception)
"""

import pytest
from typing import AsyncIterator, Optional, List, Dict, Any
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from scrappy.task_router.strategies.agent_executor import AgentExecutor
from scrappy.task_router.classifier import ClassifiedTask, TaskType
from scrappy.agent.types import AgentEvent


# =============================================================================
# Mock Implementations
# =============================================================================

class MockAgentEvent:
    """Factory for creating test AgentEvent objects."""

    @staticmethod
    def thought_start(iteration: int = 0) -> AgentEvent:
        return AgentEvent(
            event_type="thought_start",
            content="",
            iteration=iteration,
            metadata={}
        )

    @staticmethod
    def thought_token(content: str, iteration: int = 0) -> AgentEvent:
        return AgentEvent(
            event_type="thought_token",
            content=content,
            iteration=iteration,
            metadata={}
        )

    @staticmethod
    def thought_end(iteration: int = 0) -> AgentEvent:
        return AgentEvent(
            event_type="thought_end",
            content="",
            iteration=iteration,
            metadata={}
        )

    @staticmethod
    def action_start(action: str, iteration: int = 0) -> AgentEvent:
        return AgentEvent(
            event_type="action_start",
            content="",
            iteration=iteration,
            metadata={"action": action}
        )

    @staticmethod
    def action_end(action: str, success: bool = True, iteration: int = 0) -> AgentEvent:
        return AgentEvent(
            event_type="action_end",
            content="",
            iteration=iteration,
            metadata={"action": action, "success": success}
        )

    @staticmethod
    def complete(content: str = "Task completed", success: bool = True) -> AgentEvent:
        return AgentEvent(
            event_type="complete",
            content=content,
            iteration=1,
            metadata={"success": success}
        )

    @staticmethod
    def error(content: str, error_type: str = "execution_error") -> AgentEvent:
        return AgentEvent(
            event_type="error",
            content=content,
            iteration=0,
            metadata={"error": error_type}
        )


class MockCodeAgent:
    """
    Mock CodeAgent that yields configurable AgentEvent streams.

    Implements run_streaming() for testing AgentExecutor.execute_streaming().
    """

    def __init__(self, events: Optional[List[AgentEvent]] = None):
        """
        Initialize mock code agent.

        Args:
            events: List of AgentEvent objects to yield during streaming
        """
        self._events = events or [
            MockAgentEvent.thought_start(),
            MockAgentEvent.thought_token("Analyzing task..."),
            MockAgentEvent.thought_end(),
            MockAgentEvent.complete("Task completed successfully", success=True),
        ]
        self.run_streaming_calls: List[dict] = []
        self.config = Mock()
        self.config.max_iterations = 10
        self.require_approval = True

    async def run_streaming(
        self,
        task: str,
        max_iterations: int = 10,
        auto_confirm: bool = False
    ) -> AsyncIterator[AgentEvent]:
        """
        Mock streaming execution that yields configured events.

        Args:
            task: Task to execute
            max_iterations: Maximum iterations
            auto_confirm: Auto-confirm actions

        Yields:
            AgentEvent objects
        """
        self.run_streaming_calls.append({
            'task': task,
            'max_iterations': max_iterations,
            'auto_confirm': auto_confirm,
        })

        for event in self._events:
            yield event


class MockOrchestratorAdapter:
    """Mock AgentOrchestratorAdapter."""

    def __init__(self):
        self.preferred_provider = None
        self.preferred_model = None
        self.context = Mock()
        self.context.is_explored.return_value = True
        self.context.platform = Mock()
        self.context.platform.is_windows.return_value = False
        self.context.get_project_type.return_value = "python"

    def set_preferred_provider(self, provider: str, model: Optional[str] = None):
        """Set preferred provider for testing."""
        self.preferred_provider = provider
        self.preferred_model = model


class MockOrchestrator:
    """Mock orchestrator with plan support."""

    def __init__(self):
        self.plan_calls: List[str] = []
        self.brain = "test-brain"

    def plan(self, task: str) -> List[str]:
        """Mock planning that returns simple steps."""
        self.plan_calls.append(task)
        return ["Step 1: Analyze", "Step 2: Implement"]


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def classified_task():
    """Create a basic classified code generation task."""
    return ClassifiedTask(
        task_type=TaskType.CODE_GENERATION,
        original_input="Write a function to sort a list",
        confidence=0.95,
        reasoning="Code generation task",
        complexity_score=3,
        requires_planning=False,
        extracted_files=(),
        extracted_directories=(),
    )


@pytest.fixture
def classified_task_with_planning():
    """Create a code generation task that requires planning."""
    return ClassifiedTask(
        task_type=TaskType.CODE_GENERATION,
        original_input="Implement a complex feature",
        confidence=0.95,
        reasoning="Complex task requiring planning",
        complexity_score=5,
        requires_planning=True,
        extracted_files=(),
        extracted_directories=(),
    )


@pytest.fixture
def mock_orchestrator():
    """Create mock orchestrator."""
    return MockOrchestrator()


@pytest.fixture
def mock_io():
    """Create mock IO interface."""
    return Mock()


# =============================================================================
# Basic Streaming Tests
# =============================================================================

@pytest.mark.asyncio
async def test_execute_streaming_yields_agent_events(mock_orchestrator, mock_io, classified_task):
    """Test that execute_streaming yields AgentEvent objects."""
    events = [
        MockAgentEvent.thought_start(),
        MockAgentEvent.thought_token("Processing..."),
        MockAgentEvent.thought_end(),
        MockAgentEvent.complete("Done"),
    ]

    with patch('scrappy.agent.CodeAgent') as MockCodeAgentClass:
        mock_agent = MockCodeAgent(events=events)
        MockCodeAgentClass.return_value = mock_agent

        with patch('scrappy.orchestrator_adapter.AgentOrchestratorAdapter') as MockAdapter:
            MockAdapter.return_value = MockOrchestratorAdapter()

            executor = AgentExecutor(
                orchestrator=mock_orchestrator,
                project_root=Path("/test"),
                io=mock_io,
            )

            collected_events = []
            async for event in executor.execute_streaming(classified_task):
                collected_events.append(event)

    # Verify events were yielded
    assert len(collected_events) == 4
    assert collected_events[0].event_type == "thought_start"
    assert collected_events[1].event_type == "thought_token"
    assert collected_events[1].content == "Processing..."
    assert collected_events[2].event_type == "thought_end"
    assert collected_events[3].event_type == "complete"


@pytest.mark.asyncio
async def test_execute_streaming_passes_task_to_agent(mock_orchestrator, mock_io, classified_task):
    """Test that task content is passed to CodeAgent.run_streaming()."""
    with patch('scrappy.agent.CodeAgent') as MockCodeAgentClass:
        mock_agent = MockCodeAgent()
        MockCodeAgentClass.return_value = mock_agent

        with patch('scrappy.orchestrator_adapter.AgentOrchestratorAdapter') as MockAdapter:
            MockAdapter.return_value = MockOrchestratorAdapter()

            executor = AgentExecutor(
                orchestrator=mock_orchestrator,
                project_root=Path("/test"),
                io=mock_io,
            )

            async for _ in executor.execute_streaming(classified_task):
                pass

    # Verify task was passed to agent
    assert len(mock_agent.run_streaming_calls) == 1
    call = mock_agent.run_streaming_calls[0]
    assert classified_task.original_input in call['task']


@pytest.mark.asyncio
async def test_execute_streaming_respects_max_iterations(mock_orchestrator, mock_io, classified_task):
    """Test that max_iterations setting is passed to agent."""
    with patch('scrappy.agent.CodeAgent') as MockCodeAgentClass:
        mock_agent = MockCodeAgent()
        MockCodeAgentClass.return_value = mock_agent

        with patch('scrappy.orchestrator_adapter.AgentOrchestratorAdapter') as MockAdapter:
            MockAdapter.return_value = MockOrchestratorAdapter()

            executor = AgentExecutor(
                orchestrator=mock_orchestrator,
                project_root=Path("/test"),
                io=mock_io,
                max_iterations=5,
            )

            async for _ in executor.execute_streaming(classified_task):
                pass

    # Verify max_iterations was passed
    call = mock_agent.run_streaming_calls[0]
    assert call['max_iterations'] == 5


@pytest.mark.asyncio
async def test_execute_streaming_respects_require_approval(mock_orchestrator, mock_io, classified_task):
    """Test that require_approval setting affects auto_confirm."""
    with patch('scrappy.agent.CodeAgent') as MockCodeAgentClass:
        mock_agent = MockCodeAgent()
        MockCodeAgentClass.return_value = mock_agent

        with patch('scrappy.orchestrator_adapter.AgentOrchestratorAdapter') as MockAdapter:
            MockAdapter.return_value = MockOrchestratorAdapter()

            # With require_approval=True, auto_confirm should be False
            executor = AgentExecutor(
                orchestrator=mock_orchestrator,
                project_root=Path("/test"),
                io=mock_io,
                require_approval=True,
            )

            async for _ in executor.execute_streaming(classified_task):
                pass

    call = mock_agent.run_streaming_calls[0]
    assert call['auto_confirm'] is False


@pytest.mark.asyncio
async def test_execute_streaming_auto_confirm_when_no_approval(mock_orchestrator, mock_io, classified_task):
    """Test that auto_confirm=True when require_approval=False."""
    with patch('scrappy.agent.CodeAgent') as MockCodeAgentClass:
        mock_agent = MockCodeAgent()
        MockCodeAgentClass.return_value = mock_agent

        with patch('scrappy.orchestrator_adapter.AgentOrchestratorAdapter') as MockAdapter:
            MockAdapter.return_value = MockOrchestratorAdapter()

            executor = AgentExecutor(
                orchestrator=mock_orchestrator,
                project_root=Path("/test"),
                io=mock_io,
                require_approval=False,
            )

            async for _ in executor.execute_streaming(classified_task):
                pass

    call = mock_agent.run_streaming_calls[0]
    assert call['auto_confirm'] is True


# =============================================================================
# Planning and Guidance Tests
# =============================================================================

@pytest.mark.asyncio
async def test_execute_streaming_adds_planning_when_required(mock_orchestrator, mock_io, classified_task_with_planning):
    """Test that planning is added to task when requires_planning=True."""
    with patch('scrappy.agent.CodeAgent') as MockCodeAgentClass:
        mock_agent = MockCodeAgent()
        MockCodeAgentClass.return_value = mock_agent

        with patch('scrappy.orchestrator_adapter.AgentOrchestratorAdapter') as MockAdapter:
            MockAdapter.return_value = MockOrchestratorAdapter()

            executor = AgentExecutor(
                orchestrator=mock_orchestrator,
                project_root=Path("/test"),
                io=mock_io,
            )

            async for _ in executor.execute_streaming(classified_task_with_planning):
                pass

    # Verify orchestrator.plan was called
    assert len(mock_orchestrator.plan_calls) == 1

    # Verify plan was included in task
    call = mock_agent.run_streaming_calls[0]
    assert "Plan:" in call['task']
    assert "Step 1:" in call['task']


@pytest.mark.asyncio
async def test_execute_streaming_adds_guidance_for_requirements(mock_orchestrator, mock_io):
    """Test that task-specific guidance is added for requirements.txt creation."""
    task = ClassifiedTask(
        task_type=TaskType.CODE_GENERATION,
        original_input="Create requirements.txt for this project",
        confidence=0.95,
        reasoning="Requirements file creation",
        complexity_score=2,
        requires_planning=False,
        extracted_files=(),
        extracted_directories=(),
    )

    with patch('scrappy.agent.CodeAgent') as MockCodeAgentClass:
        mock_agent = MockCodeAgent()
        MockCodeAgentClass.return_value = mock_agent

        with patch('scrappy.orchestrator_adapter.AgentOrchestratorAdapter') as MockAdapter:
            MockAdapter.return_value = MockOrchestratorAdapter()

            executor = AgentExecutor(
                orchestrator=mock_orchestrator,
                project_root=Path("/test"),
                io=mock_io,
            )

            async for _ in executor.execute_streaming(task):
                pass

    # Verify guidance was added
    call = mock_agent.run_streaming_calls[0]
    assert "CRITICAL GUIDANCE" in call['task'] or "requirements" in call['task'].lower()


# =============================================================================
# Provider Resolution Tests
# =============================================================================

@pytest.mark.asyncio
async def test_execute_streaming_uses_resolved_provider(mock_orchestrator, mock_io, classified_task):
    """Test that resolved provider is passed to CodeAgent."""
    adapter = MockOrchestratorAdapter()

    with patch('scrappy.agent.CodeAgent') as MockCodeAgentClass:
        mock_agent = MockCodeAgent()
        MockCodeAgentClass.return_value = mock_agent

        with patch('scrappy.orchestrator_adapter.AgentOrchestratorAdapter') as MockAdapter:
            MockAdapter.return_value = adapter

            executor = AgentExecutor(
                orchestrator=mock_orchestrator,
                project_root=Path("/test"),
                io=mock_io,
            )

            # Set resolved provider before execution
            executor._resolved_provider = "groq"
            executor._resolved_model = "llama-3.1-8b"

            async for _ in executor.execute_streaming(classified_task):
                pass

    # Verify provider was set on adapter
    assert adapter.preferred_provider == "groq"
    assert adapter.preferred_model == "llama-3.1-8b"


@pytest.mark.asyncio
async def test_execute_streaming_clears_resolved_provider_after_use(mock_orchestrator, mock_io, classified_task):
    """Test that resolved provider is cleared after execution."""
    with patch('scrappy.agent.CodeAgent') as MockCodeAgentClass:
        mock_agent = MockCodeAgent()
        MockCodeAgentClass.return_value = mock_agent

        with patch('scrappy.orchestrator_adapter.AgentOrchestratorAdapter') as MockAdapter:
            MockAdapter.return_value = MockOrchestratorAdapter()

            executor = AgentExecutor(
                orchestrator=mock_orchestrator,
                project_root=Path("/test"),
                io=mock_io,
            )

            # Set resolved provider before execution
            executor._resolved_provider = "groq"
            executor._resolved_model = "llama-3.1-8b"

            async for _ in executor.execute_streaming(classified_task):
                pass

    # Verify provider was cleared
    assert executor._resolved_provider is None
    assert executor._resolved_model is None


# =============================================================================
# Error Handling Tests
# =============================================================================

@pytest.mark.asyncio
async def test_execute_streaming_handles_import_error(mock_orchestrator, mock_io, classified_task):
    """Test that ImportError yields error event."""
    with patch('scrappy.agent.CodeAgent') as MockCodeAgentClass:
        MockCodeAgentClass.side_effect = ImportError("CodeAgent not available")

        with patch('scrappy.orchestrator_adapter.AgentOrchestratorAdapter') as MockAdapter:
            MockAdapter.return_value = MockOrchestratorAdapter()

            executor = AgentExecutor(
                orchestrator=mock_orchestrator,
                project_root=Path("/test"),
                io=mock_io,
            )

            collected_events = []
            async for event in executor.execute_streaming(classified_task):
                collected_events.append(event)

    # Verify error event was yielded
    assert len(collected_events) == 1
    assert collected_events[0].event_type == "error"
    assert "CodeAgent not available" in collected_events[0].content
    assert collected_events[0].metadata['error'] == "import_error"


@pytest.mark.asyncio
async def test_execute_streaming_handles_execution_error(mock_orchestrator, mock_io, classified_task):
    """Test that execution errors yield error event."""
    with patch('scrappy.agent.CodeAgent') as MockCodeAgentClass:
        mock_agent = Mock()
        # Make run_streaming raise an exception
        async def failing_stream(*args, **kwargs):
            raise RuntimeError("Execution failed")
            yield  # Make it a generator

        mock_agent.run_streaming = failing_stream
        mock_agent.config = Mock()
        mock_agent.config.max_iterations = 10
        mock_agent.require_approval = True
        MockCodeAgentClass.return_value = mock_agent

        with patch('scrappy.orchestrator_adapter.AgentOrchestratorAdapter') as MockAdapter:
            MockAdapter.return_value = MockOrchestratorAdapter()

            executor = AgentExecutor(
                orchestrator=mock_orchestrator,
                project_root=Path("/test"),
                io=mock_io,
            )

            collected_events = []
            async for event in executor.execute_streaming(classified_task):
                collected_events.append(event)

    # Verify error event was yielded
    assert len(collected_events) == 1
    assert collected_events[0].event_type == "error"
    assert "failed" in collected_events[0].content.lower()
    assert collected_events[0].metadata['error'] == "execution_error"


# =============================================================================
# Event Propagation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_execute_streaming_propagates_all_event_types(mock_orchestrator, mock_io, classified_task):
    """Test that all event types are propagated correctly."""
    events = [
        MockAgentEvent.thought_start(iteration=0),
        MockAgentEvent.thought_token("Thinking...", iteration=0),
        MockAgentEvent.thought_end(iteration=0),
        MockAgentEvent.action_start("read_file", iteration=0),
        MockAgentEvent.action_end("read_file", success=True, iteration=0),
        MockAgentEvent.complete("Done", success=True),
    ]

    with patch('scrappy.agent.CodeAgent') as MockCodeAgentClass:
        mock_agent = MockCodeAgent(events=events)
        MockCodeAgentClass.return_value = mock_agent

        with patch('scrappy.orchestrator_adapter.AgentOrchestratorAdapter') as MockAdapter:
            MockAdapter.return_value = MockOrchestratorAdapter()

            executor = AgentExecutor(
                orchestrator=mock_orchestrator,
                project_root=Path("/test"),
                io=mock_io,
            )

            collected_events = []
            async for event in executor.execute_streaming(classified_task):
                collected_events.append(event)

    # Verify all events were propagated
    assert len(collected_events) == 6
    event_types = [e.event_type for e in collected_events]
    assert event_types == [
        "thought_start",
        "thought_token",
        "thought_end",
        "action_start",
        "action_end",
        "complete",
    ]


@pytest.mark.asyncio
async def test_execute_streaming_preserves_event_metadata(mock_orchestrator, mock_io, classified_task):
    """Test that event metadata is preserved."""
    events = [
        AgentEvent(
            event_type="action_end",
            content="File written",
            iteration=2,
            metadata={"action": "write_file", "path": "/test/file.py", "success": True}
        ),
        MockAgentEvent.complete("Done"),
    ]

    with patch('scrappy.agent.CodeAgent') as MockCodeAgentClass:
        mock_agent = MockCodeAgent(events=events)
        MockCodeAgentClass.return_value = mock_agent

        with patch('scrappy.orchestrator_adapter.AgentOrchestratorAdapter') as MockAdapter:
            MockAdapter.return_value = MockOrchestratorAdapter()

            executor = AgentExecutor(
                orchestrator=mock_orchestrator,
                project_root=Path("/test"),
                io=mock_io,
            )

            collected_events = []
            async for event in executor.execute_streaming(classified_task):
                collected_events.append(event)

    # Verify metadata was preserved
    action_event = collected_events[0]
    assert action_event.event_type == "action_end"
    assert action_event.iteration == 2
    assert action_event.metadata["action"] == "write_file"
    assert action_event.metadata["path"] == "/test/file.py"
    assert action_event.metadata["success"] is True
