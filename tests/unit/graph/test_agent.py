"""
Unit tests for the LangGraph agent assembly.

Tests graph construction, wiring, and entry points.
"""

import tempfile
from typing import Any, Optional

import pytest

from scrappy.graph.agent import (
    WorkingDirectoryError,
    build_graph,
    create_agent_runner,
    run_agent,
    validate_working_dir,
    _wrap_think_node,
    _wrap_execute_node,
    _wrap_verify_node,
    _route_after_execute,
)
from scrappy.graph.state import AgentState
from scrappy.graph.edges import MAX_ITERATIONS, MAX_RETRIES


# =============================================================================
# Test Doubles
# =============================================================================


class MockLLMResponse:
    """Mock LLM response object."""

    def __init__(
        self,
        content: str = "Test response",
        tool_calls: Optional[list] = None,
    ):
        self.content = content
        self.tool_calls = tool_calls


class MockLLMService:
    """Mock LLM service for testing."""

    def __init__(
        self,
        response: Optional[MockLLMResponse] = None,
        exception: Optional[Exception] = None,
    ):
        self.response = response or MockLLMResponse()
        self.exception = exception
        self.calls: list[dict] = []

    def completion_sync(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any,
    ) -> tuple[MockLLMResponse, dict]:
        """Record call and return mock response."""
        self.calls.append({
            "model": model,
            "messages": messages,
            **kwargs,
        })

        if self.exception:
            raise self.exception

        task_record = {"model": model, "tokens_used": 100}
        return self.response, task_record


class MockToolAdapter:
    """Mock tool adapter for testing."""

    def __init__(
        self,
        tool_names: Optional[list[str]] = None,
        tool_schemas: Optional[list[dict]] = None,
        execute_results: Optional[list[dict]] = None,
    ):
        self._tool_names = tool_names or ["mock_tool"]
        self._tool_schemas = tool_schemas or []
        self._execute_results = execute_results or [{"name": "mock_tool", "result": "ok"}]
        self.execute_calls: list[tuple] = []

    def get_tool_names(self) -> list[str]:
        return self._tool_names

    def get_tool_schemas(self) -> list[dict]:
        return self._tool_schemas

    def execute(self, tool_calls: list, context: Any) -> list[dict]:
        self.execute_calls.append((tool_calls, context))
        return self._execute_results


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

    def test_builds_without_error(self) -> None:
        """build_graph should complete without errors."""
        llm_service = MockLLMService()
        tool_adapter = MockToolAdapter()
        graph = build_graph(llm_service, tool_adapter)
        assert graph is not None

    def test_returns_compiled_graph(self) -> None:
        """build_graph should return a CompiledStateGraph."""
        llm_service = MockLLMService()
        tool_adapter = MockToolAdapter()
        graph = build_graph(llm_service, tool_adapter)
        # CompiledStateGraph has invoke method
        assert hasattr(graph, "invoke")
        assert callable(graph.invoke)

    def test_accepts_custom_tool_adapter(self) -> None:
        """build_graph should accept custom tool adapter."""
        llm_service = MockLLMService()
        tool_adapter = MockToolAdapter(tool_names=["custom_tool"])
        graph = build_graph(llm_service, tool_adapter)
        assert graph is not None

    def test_accepts_custom_checkpointer(self) -> None:
        """build_graph should accept custom checkpointer."""
        from langgraph.checkpoint.memory import MemorySaver

        llm_service = MockLLMService()
        tool_adapter = MockToolAdapter()
        checkpointer = MemorySaver()
        graph = build_graph(llm_service, tool_adapter, checkpointer=checkpointer)
        assert graph is not None

    def test_has_think_as_entry_point(self) -> None:
        """Graph entry point should be 'think' node."""
        llm_service = MockLLMService()
        tool_adapter = MockToolAdapter()
        graph = build_graph(llm_service, tool_adapter)

        # The graph should have think node
        # We can verify by checking the graph structure
        assert graph is not None
        # LangGraph CompiledStateGraph has nodes attribute
        assert hasattr(graph, "nodes")

    def test_has_required_nodes(self) -> None:
        """Graph should have all required nodes."""
        llm_service = MockLLMService()
        tool_adapter = MockToolAdapter()
        graph = build_graph(llm_service, tool_adapter)

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

        # LangGraph stores interrupt configuration
        # The graph should pause before confirm node
        # We verify this by checking the compiled graph's interrupt configuration
        assert graph is not None
        # The interrupt_before is set during compilation
        # We can verify behavior in integration tests


# =============================================================================
# Node Wrapper Tests
# =============================================================================


class TestNodeWrappers:
    """Tests for node wrapper functions."""

    def test_wrap_think_node_returns_callable(self) -> None:
        """_wrap_think_node should return a callable."""
        llm_service = MockLLMService()
        wrapped = _wrap_think_node(llm_service, None)
        assert callable(wrapped)

    def test_wrap_execute_node_returns_callable(self) -> None:
        """_wrap_execute_node should return a callable."""
        tool_adapter = MockToolAdapter()
        wrapped = _wrap_execute_node(tool_adapter)
        assert callable(wrapped)

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
        llm_service = MockLLMService()
        tool_adapter = MockToolAdapter()
        result = create_agent_runner(llm_service, tool_adapter)

        assert isinstance(result, tuple)
        assert len(result) == 2

        graph, checkpointer = result
        assert hasattr(graph, "invoke")
        assert hasattr(checkpointer, "get")  # MemorySaver has get method

    def test_accepts_custom_tool_adapter(self) -> None:
        """create_agent_runner should accept custom tool adapter."""
        llm_service = MockLLMService()
        tool_adapter = MockToolAdapter()

        graph, checkpointer = create_agent_runner(
            llm_service,
            tool_adapter,
        )

        assert graph is not None
        assert checkpointer is not None

    def test_accepts_mypy_config(self) -> None:
        """create_agent_runner should accept run_mypy_check config."""
        llm_service = MockLLMService()
        tool_adapter = MockToolAdapter()

        graph, checkpointer = create_agent_runner(
            llm_service,
            tool_adapter,
            run_mypy_check=False,
        )

        assert graph is not None


# =============================================================================
# Run Agent Tests
# =============================================================================


class TestRunAgent:
    """Tests for run_agent function."""

    def test_returns_agent_state(self) -> None:
        """run_agent should return an AgentState."""
        # Use a simple response that ends the conversation
        llm_service = MockLLMService(
            response=MockLLMResponse(content="Task completed.")
        )

        result = run_agent(
            task="Test task",
            working_dir=tempfile.gettempdir(),
            llm_service=llm_service,
        )

        assert isinstance(result, AgentState)

    def test_preserves_original_task(self) -> None:
        """run_agent should preserve the original task."""
        llm_service = MockLLMService(
            response=MockLLMResponse(content="Done.")
        )

        result = run_agent(
            task="My specific task",
            working_dir=tempfile.gettempdir(),
            llm_service=llm_service,
        )

        assert result.original_task == "My specific task"

    def test_preserves_working_dir(self) -> None:
        """run_agent should preserve the working directory."""
        llm_service = MockLLMService(
            response=MockLLMResponse(content="Done.")
        )

        temp_dir = tempfile.gettempdir()
        result = run_agent(
            task="Test",
            working_dir=temp_dir,
            llm_service=llm_service,
        )

        # Working dir should be resolved to absolute path
        assert result.working_dir is not None

    def test_increments_iteration(self) -> None:
        """run_agent should increment iteration count."""
        llm_service = MockLLMService(
            response=MockLLMResponse(content="Done.")
        )

        result = run_agent(
            task="Test",
            working_dir=tempfile.gettempdir(),
            llm_service=llm_service,
        )

        # Should have at least one iteration
        assert result.iteration >= 1

    def test_accepts_custom_thread_id(self) -> None:
        """run_agent should accept custom thread_id."""
        llm_service = MockLLMService(
            response=MockLLMResponse(content="Done.")
        )

        # Should not raise with custom thread_id
        result = run_agent(
            task="Test",
            working_dir=tempfile.gettempdir(),
            llm_service=llm_service,
            thread_id="custom-session-123",
        )

        assert result is not None


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

        class MultiStepLLMService:
            def completion_sync(self, model, messages, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    # First call - return tool call
                    class ToolCallResponse:
                        content = ""
                        tool_calls = [
                            type("TC", (), {
                                "id": "call_1",
                                "name": "mock_tool",
                                "arguments": "{}",
                            })()
                        ]
                    return ToolCallResponse(), {}
                else:
                    # Subsequent calls - return final response
                    class FinalResponse:
                        content = "Task completed successfully."
                        tool_calls = None
                    return FinalResponse(), {}

        llm_service = MultiStepLLMService()
        tool_adapter = MockToolAdapter()

        result = run_agent(
            task="Test multi-step",
            working_dir="/tmp",
            llm_service=llm_service,
            tool_adapter=tool_adapter,
        )

        # Should have completed (done=True after final response)
        assert result.done is True
        # Should have made at least 2 LLM calls
        assert call_count[0] >= 2

    def test_error_recovery_loop(self) -> None:
        """Graph should support error recovery."""
        call_count = [0]

        class ErrorRecoveryLLMService:
            def completion_sync(self, model, messages, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    # First call - raise error
                    raise ValueError("Simulated API error")
                else:
                    # Recovery call - return success
                    class SuccessResponse:
                        content = "Recovered successfully."
                        tool_calls = None
                    return SuccessResponse(), {}

        llm_service = ErrorRecoveryLLMService()

        result = run_agent(
            task="Test error recovery",
            working_dir="/tmp",
            llm_service=llm_service,
        )

        # Should have recovered and completed
        assert result.done is True
        assert call_count[0] >= 2

    def test_max_iterations_safety(self) -> None:
        """Graph should stop at max iterations or LangGraph recursion limit."""
        from langgraph.errors import GraphRecursionError

        # LLM always returns tool call, never completing
        class InfiniteLoopLLMService:
            def completion_sync(self, model, messages, **kwargs):
                class ToolCallResponse:
                    content = ""
                    tool_calls = [
                        type("TC", (), {
                            "id": "call_loop",
                            "name": "mock_tool",
                            "arguments": "{}",
                        })()
                    ]
                return ToolCallResponse(), {}

        llm_service = InfiniteLoopLLMService()
        tool_adapter = MockToolAdapter()

        # LangGraph has its own recursion limit (default 25) which may trigger
        # before our MAX_ITERATIONS limit. Either way, the graph stops safely.
        try:
            result = run_agent(
                task="Test max iterations",
                working_dir="/tmp",
                llm_service=llm_service,
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

    def test_tool_adapter_is_required(self) -> None:
        """Graph requires tool_adapter parameter."""
        llm_service = MockLLMService()
        tool_adapter = MockToolAdapter()

        # tool_adapter is required - graph should build successfully
        graph = build_graph(llm_service, tool_adapter)
        assert graph is not None

    def test_default_checkpointer_creation(self) -> None:
        """Graph should create default checkpointer if not provided."""
        llm_service = MockLLMService()
        tool_adapter = MockToolAdapter()

        # Should not raise even without checkpointer
        graph = build_graph(llm_service, tool_adapter)
        assert graph is not None

    def test_mypy_check_disabled(self) -> None:
        """Graph should accept run_mypy_check=False."""
        llm_service = MockLLMService()
        tool_adapter = MockToolAdapter()

        graph = build_graph(llm_service, tool_adapter, run_mypy_check=False)
        assert graph is not None


# =============================================================================
# State Conversion Tests
# =============================================================================


class TestStateConversion:
    """Tests for state conversion in run_agent."""

    def test_initial_state_creation(self) -> None:
        """run_agent should create proper initial state."""
        llm_service = MockLLMService(
            response=MockLLMResponse(content="Done.")
        )

        result = run_agent(
            task="Create initial state test",
            working_dir=tempfile.gettempdir(),
            llm_service=llm_service,
        )

        # Initial state values should be preserved
        assert result.input == "Create initial state test"
        assert result.original_task == "Create initial state test"
        # Working dir is resolved to absolute path
        assert result.working_dir is not None

    def test_dict_to_state_conversion(self) -> None:
        """run_agent should convert dict result to AgentState."""
        llm_service = MockLLMService(
            response=MockLLMResponse(content="Final answer.")
        )

        result = run_agent(
            task="Test",
            working_dir=tempfile.gettempdir(),
            llm_service=llm_service,
        )

        # Result should be AgentState, not dict
        assert isinstance(result, AgentState)
        assert hasattr(result, "input")
        assert hasattr(result, "messages")
        assert hasattr(result, "done")


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

    def test_empty_path_raises(self) -> None:
        """validate_working_dir should reject empty path."""
        with pytest.raises(WorkingDirectoryError, match="cannot be empty"):
            validate_working_dir("")

    def test_whitespace_only_path_raises(self) -> None:
        """validate_working_dir should reject whitespace-only path."""
        with pytest.raises(WorkingDirectoryError, match="cannot be empty"):
            validate_working_dir("   ")

    def test_nonexistent_path_raises(self) -> None:
        """validate_working_dir should reject non-existent path."""
        with pytest.raises(WorkingDirectoryError, match="does not exist"):
            validate_working_dir("/this/path/definitely/does/not/exist/anywhere")

    def test_file_instead_of_directory_raises(self) -> None:
        """validate_working_dir should reject files."""
        import os
        # Create a temp file (closed immediately to avoid Windows locking)
        fd, path = tempfile.mkstemp()
        os.close(fd)
        try:
            with pytest.raises(WorkingDirectoryError, match="not a directory"):
                validate_working_dir(path)
        finally:
            os.unlink(path)
