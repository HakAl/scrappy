"""
Unit tests for the LangGraph agent assembly.

Tests graph construction, wiring, and entry points.
"""

import tempfile
from typing import Optional

from scrappy.graph.agent import (
    build_graph,
    create_agent_runner,
    run_agent,
    validate_working_dir,
    _wrap_verify_node,
    _route_after_execute,
)
from scrappy.graph.state import AgentState
from scrappy.graph.edges import MAX_ITERATIONS, MAX_RETRIES
from tests.helpers import MockLLMService, MockLLMResponse, MockToolAdapter, MockOrchestrator


def create_test_state(
    input_text: str = "Test task",
    working_dir: str = "/tmp/test",
    done: bool = False,
    iteration: int = 0,
    error_count: int = 0,
    last_error: Optional[str] = None,
    pending_confirmation: Optional[dict] = None,
    files_changed: Optional[list[str]] = None,
    files_verified: bool = True,
) -> AgentState:
    """Create a test AgentState."""
    return AgentState(
        input=input_text,
        original_task=input_text,
        working_dir=working_dir,
        done=done,
        iteration=iteration,
        error_count=error_count,
        last_error=last_error,
        pending_confirmation=pending_confirmation,  # type: ignore[arg-type]
        files_changed=files_changed or [],
        files_verified=files_verified,
    )


# =============================================================================
# Graph Building Tests
# =============================================================================


class TestBuildGraph:
    """Tests for build_graph function."""

    def test_has_think_as_entry_point(self) -> None:
        """Graph entry point should be 'think' node."""
        orchestrator = MockOrchestrator()
        tool_adapter = MockToolAdapter()
        graph = build_graph(orchestrator, tool_adapter)

        # Verify think node exists in the graph
        assert "think" in graph.nodes

    def test_has_required_nodes(self) -> None:
        """Graph should have all required nodes."""
        orchestrator = MockOrchestrator()
        tool_adapter = MockToolAdapter()
        graph = build_graph(orchestrator, tool_adapter)

        # Get node names from the compiled graph
        node_names = set(graph.nodes.keys())

        # Should have all 5 nodes
        expected_nodes = {"think", "execute", "verify", "confirm", "error"}
        assert expected_nodes.issubset(node_names)

    def test_interrupt_before_confirm(self) -> None:
        """Graph should be compiled with interrupt_before on confirm."""
        llm_service = MockLLMService()
        tool_adapter = MockToolAdapter()
        graph = build_graph(llm_service, tool_adapter)

        # LangGraph stores interrupt configuration in the compiled graph
        # The interrupt_before list should include "confirm"
        assert "confirm" in graph.interrupt_before_nodes


# =============================================================================
# Node Wrapper Tests
# =============================================================================


class TestNodeWrappers:
    """Tests for node wrapper functions."""

    def test_wrap_verify_node_returns_callable(self) -> None:
        """_wrap_verify_node should return a callable."""
        wrapped = _wrap_verify_node()
        assert callable(wrapped)

    def test_wrap_verify_node_accepts_config(self) -> None:
        """_wrap_verify_node should accept run_mypy_check config."""
        wrapped = _wrap_verify_node(run_mypy_check=False)
        assert callable(wrapped)


# =============================================================================
# Routing Tests
# =============================================================================


class TestRouteAfterExecute:
    """Tests for _route_after_execute routing function."""

    def test_routes_to_end_when_done(self) -> None:
        """Should route to end when done=True."""
        state = create_test_state(done=True)
        assert _route_after_execute(state) == "end"

    def test_routes_to_end_on_max_iterations(self) -> None:
        """Should route to end when iteration limit reached."""
        state = create_test_state(iteration=MAX_ITERATIONS)
        assert _route_after_execute(state) == "end"

    def test_routes_to_end_on_max_retries(self) -> None:
        """Should route to end when retry limit reached."""
        state = create_test_state(error_count=MAX_RETRIES)
        assert _route_after_execute(state) == "end"

    def test_routes_to_confirm_on_pending_confirmation(self) -> None:
        """Should route to confirm when pending_confirmation is set."""
        state = create_test_state(
            pending_confirmation={"type": "command", "command": "rm -rf /"}
        )
        assert _route_after_execute(state) == "confirm"

    def test_routes_to_error_on_last_error(self) -> None:
        """Should route to error when last_error is set."""
        state = create_test_state(last_error="Something went wrong")
        assert _route_after_execute(state) == "error"

    def test_routes_to_verify_on_unverified_files(self) -> None:
        """Should route to verify when files changed but not verified."""
        state = create_test_state(
            files_changed=["file.py"],
            files_verified=False,
        )
        assert _route_after_execute(state) == "verify"

    def test_routes_to_think_by_default(self) -> None:
        """Should route to think by default."""
        state = create_test_state()
        assert _route_after_execute(state) == "think"


# =============================================================================
# Create Agent Runner Tests
# =============================================================================


class TestCreateAgentRunner:
    """Tests for create_agent_runner function."""

    def test_returns_graph_and_checkpointer(self) -> None:
        """create_agent_runner should return tuple of graph and checkpointer."""
        from langgraph.graph.state import CompiledStateGraph
        from langgraph.checkpoint.memory import MemorySaver

        llm_service = MockLLMService()
        tool_adapter = MockToolAdapter()
        result = create_agent_runner(llm_service, tool_adapter)

        assert isinstance(result, tuple)
        assert len(result) == 2

        graph, checkpointer = result
        assert isinstance(graph, CompiledStateGraph)
        assert isinstance(checkpointer, MemorySaver)


# =============================================================================
# Run Agent Tests
# =============================================================================


class TestRunAgent:
    """Tests for run_agent function."""

    def test_preserves_original_task(self) -> None:
        """run_agent should preserve the original task."""
        orchestrator = MockOrchestrator.with_response(content="Done.")

        result = run_agent(
            task="My specific task",
            working_dir=tempfile.gettempdir(),
            orchestrator=orchestrator,
        )

        assert result.original_task == "My specific task"

    def test_preserves_working_dir(self) -> None:
        """run_agent should preserve the working directory."""
        from pathlib import Path

        orchestrator = MockOrchestrator.with_response(content="Done.")

        temp_dir = tempfile.gettempdir()
        result = run_agent(
            task="Test",
            working_dir=temp_dir,
            orchestrator=orchestrator,
        )

        # Working dir should be resolved to absolute path matching temp_dir
        assert Path(result.working_dir).resolve() == Path(temp_dir).resolve()

    def test_increments_iteration(self) -> None:
        """run_agent should increment iteration count."""
        orchestrator = MockOrchestrator.with_response(content="Done.")

        result = run_agent(
            task="Test",
            working_dir=tempfile.gettempdir(),
            orchestrator=orchestrator,
        )

        # Should have at least one iteration
        assert result.iteration >= 1

    def test_accepts_custom_thread_id(self) -> None:
        """run_agent should accept custom thread_id without raising."""
        orchestrator = MockOrchestrator.with_response(content="Done.")

        # Should not raise with custom thread_id
        result = run_agent(
            task="Test",
            working_dir=tempfile.gettempdir(),
            orchestrator=orchestrator,
            thread_id="custom-session-123",
        )

        # Verify result was returned (test is about accepting the parameter)
        assert result.original_task == "Test"


# =============================================================================
# Integration-style Tests (without real LLM calls)
# =============================================================================


class TestGraphIntegration:
    """Integration-style tests for graph behavior."""

    def test_think_execute_loop(self) -> None:
        """Graph should support think -> execute loop."""
        # First call: LLM returns tool call
        # Second call: LLM returns final response
        call_count = [0]

        class MultiStepOrchestrator:
            def stream_completion_with_fallback(self, messages, model=None, selection_type=None, **kwargs):
                from scrappy.orchestrator.types import StreamChunk, ToolCallFragment
                call_count[0] += 1
                if call_count[0] == 1:
                    # First call - return tool call
                    yield StreamChunk(
                        tool_call_fragments=[ToolCallFragment(
                            index=0, id="call_1", type="function", name="mock_tool", arguments="{}"
                        )],
                        model="mock-model", provider="mock"
                    )
                else:
                    # Subsequent calls - return final response
                    yield StreamChunk(content="Task completed successfully.", model="mock-model", provider="mock")
                yield StreamChunk(finish_reason="stop", model="mock-model", provider="mock")

        orchestrator = MultiStepOrchestrator()
        tool_adapter = MockToolAdapter()

        result = run_agent(
            task="Test multi-step",
            working_dir=tempfile.gettempdir(),
            orchestrator=orchestrator,
            tool_adapter=tool_adapter,
        )

        # Should have completed (done=True after final response)
        assert result.done is True
        # Should have made at least 2 LLM calls
        assert call_count[0] >= 2

    def test_error_recovery_loop(self) -> None:
        """Graph should support error recovery."""
        call_count = [0]

        class ErrorRecoveryOrchestrator:
            def stream_completion_with_fallback(self, messages, model=None, selection_type=None, **kwargs):
                from scrappy.orchestrator.types import StreamChunk
                call_count[0] += 1
                if call_count[0] == 1:
                    # First call - raise error
                    raise ValueError("Simulated API error")
                else:
                    # Recovery call - return success
                    yield StreamChunk(content="Recovered successfully.", model="mock-model", provider="mock")
                    yield StreamChunk(finish_reason="stop", model="mock-model", provider="mock")

        orchestrator = ErrorRecoveryOrchestrator()

        result = run_agent(
            task="Test error recovery",
            working_dir=tempfile.gettempdir(),
            orchestrator=orchestrator,
        )

        # Should have recovered and completed
        assert result.done is True
        assert call_count[0] >= 2

    def test_max_iterations_safety(self) -> None:
        """Graph should stop at max iterations or LangGraph recursion limit."""
        from langgraph.errors import GraphRecursionError

        # LLM always returns tool call, never completing
        class InfiniteLoopOrchestrator:
            def stream_completion_with_fallback(self, messages, model=None, selection_type=None, **kwargs):
                from scrappy.orchestrator.types import StreamChunk, ToolCallFragment
                yield StreamChunk(
                    tool_call_fragments=[ToolCallFragment(
                        index=0, id="call_loop", type="function", name="mock_tool", arguments="{}"
                    )],
                    model="mock-model", provider="mock"
                )
                yield StreamChunk(finish_reason="stop", model="mock-model", provider="mock")

        orchestrator = InfiniteLoopOrchestrator()
        tool_adapter = MockToolAdapter()

        # LangGraph has its own recursion limit (default 25) which may trigger
        # before our MAX_ITERATIONS limit. Either way, the graph stops safely.
        try:
            result = run_agent(
                task="Test max iterations",
                working_dir=tempfile.gettempdir(),
                orchestrator=orchestrator,
                tool_adapter=tool_adapter,
            )
            # If we get here, our iteration limit stopped it
            assert result.iteration >= MAX_ITERATIONS
        except GraphRecursionError:
            # LangGraph's recursion limit stopped it - this is also safe
            pass  # Test passes - graph was stopped safely


# =============================================================================
# Graph Configuration Tests
# =============================================================================


class TestGraphConfiguration:
    """Tests for graph configuration options."""

    def test_default_checkpointer_creation(self) -> None:
        """Graph should create default checkpointer if not provided."""
        from langgraph.graph.state import CompiledStateGraph

        orchestrator = MockOrchestrator()
        tool_adapter = MockToolAdapter()

        # Should build with all required nodes even without explicit checkpointer
        graph = build_graph(orchestrator, tool_adapter)
        assert isinstance(graph, CompiledStateGraph)
        assert "think" in graph.nodes


# =============================================================================
# State Conversion Tests
# =============================================================================


class TestStateConversion:
    """Tests for state conversion in run_agent."""

    def test_initial_state_creation(self) -> None:
        """run_agent should create proper initial state."""
        from pathlib import Path

        orchestrator = MockOrchestrator.with_response(content="Done.")

        temp_dir = tempfile.gettempdir()
        result = run_agent(
            task="Create initial state test",
            working_dir=temp_dir,
            orchestrator=orchestrator,
        )

        # Initial state values should be preserved
        assert result.input == "Create initial state test"
        assert result.original_task == "Create initial state test"
        # Working dir is resolved to absolute path
        assert Path(result.working_dir).resolve() == Path(temp_dir).resolve()


# =============================================================================
# Working Directory Validation Tests
# =============================================================================


class TestValidateWorkingDir:
    """Tests for working directory validation."""

    def test_valid_temp_directory(self) -> None:
        """validate_working_dir should accept valid temp directory."""
        temp_dir = tempfile.gettempdir()
        result = validate_working_dir(temp_dir)
        assert result.exists()
        assert result.is_dir()
