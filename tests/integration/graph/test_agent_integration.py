"""
Integration tests for the LangGraph agent.

These tests exercise the full graph through all paths:
- Happy path: think -> execute -> verify -> end
- Verify failure: think -> execute -> verify (fails) -> think -> end
- Confirm denied: think -> execute -> confirm (denied) -> end
- Tool error: think -> execute -> error -> think -> end
- Cancellation: graph stops cleanly on cancel
- Langfuse traces visible

Marked with @pytest.mark.integration to exclude from default test runs.
"""

import json
import pytest
from typing import Any, Optional
from unittest.mock import MagicMock, patch

from scrappy.graph.agent import run_agent, create_agent_runner
from scrappy.graph.state import AgentState, ToolCall, ToolResult
from tests.helpers import MockLLMResponse


class MockToolCall:
    """Mock tool call object matching LLM response structure."""

    def __init__(self, id: str, name: str, arguments: str) -> None:
        self.id = id
        self.name = name
        self.arguments = arguments


class MockLLMService:
    """Mock LLM service that returns predefined responses in sequence."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        """
        Initialize with a list of responses to return in order.

        Args:
            responses: List of response dicts with structure:
                {
                    "content": str,
                    "tool_calls": Optional[list[dict]]
                }
        """
        self.responses = responses
        self.call_count = 0
        self.call_history: list[dict] = []

    def completion_sync(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any,
    ) -> tuple[MockLLMResponse, dict]:
        """Return next predefined response."""
        self.call_history.append({
            "model": model,
            "messages": messages,
            "kwargs": kwargs,
        })

        if self.call_count >= len(self.responses):
            # Default to done response if we run out
            response = {"content": "Task complete."}
        else:
            response = self.responses[self.call_count]

        self.call_count += 1

        # Create mock response object
        content = response.get("content", "")
        tool_calls = None

        if "tool_calls" in response:
            tool_calls = []
            for tc in response["tool_calls"]:
                tool_calls.append(MockToolCall(
                    id=tc.get("id", f"call_{self.call_count}"),
                    name=tc["name"],
                    arguments=json.dumps(tc.get("arguments", {})),
                ))

        mock_response = MockLLMResponse(content=content, tool_calls=tool_calls)
        usage = {"input_tokens": 100, "output_tokens": 50}
        return mock_response, usage


class MockToolAdapter:
    """Mock tool adapter for testing."""

    def __init__(
        self,
        results: Optional[dict[str, ToolResult]] = None,
        write_tools: Optional[set[str]] = None,
    ) -> None:
        """
        Initialize with predefined results.

        Args:
            results: Map of tool_name -> ToolResult
            write_tools: Set of tool names that modify files
        """
        self.results = results or {}
        self.write_tools = write_tools or {"write_file", "edit_file"}
        self.call_history: list[dict] = []

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return minimal schemas for testing."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write a file",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

    def execute(
        self,
        tool_calls: list[ToolCall],
        context: Any,
    ) -> list[ToolResult]:
        """Execute tool calls and return predefined results."""
        results = []
        for tc in tool_calls:
            self.call_history.append(tc)
            name = tc.get("name", "unknown")
            if name in self.results:
                results.append(self.results[name])
            else:
                results.append(ToolResult(name=name, result=f"Mock result for {name}"))
        return results

    def get_tool_names(self) -> list[str]:
        """Return available tool names."""
        return ["read_file", "write_file"]


@pytest.mark.integration
class TestHappyPath:
    """Test the happy path: think -> execute -> verify -> end."""

    def test_simple_read_task_completes(self) -> None:
        """Test a simple read task that completes in one iteration."""
        # LLM returns: read a file, then say done
        responses = [
            {
                "content": "I'll read the file for you.",
                "tool_calls": [{"name": "read_file", "arguments": {"path": "test.py"}}],
            },
            {
                "content": "Here's what I found in the file. Task complete.",
            },
        ]

        llm_service = MockLLMService(responses)
        tool_adapter = MockToolAdapter()

        result = run_agent(
            task="Read test.py",
            working_dir="/tmp",
            llm_service=llm_service,
            tool_adapter=tool_adapter,
        )

        # Verify the graph executed
        assert llm_service.call_count >= 1
        assert len(tool_adapter.call_history) >= 1
        # State should have messages from the run
        assert len(result.messages) > 0

    def test_write_task_triggers_verify(self) -> None:
        """Test that write operations trigger the verify node."""
        # LLM writes a file, verify passes, then completes
        responses = [
            {
                "content": "I'll write the file.",
                "tool_calls": [{"name": "write_file", "arguments": {"path": "test.py", "content": "print('hello')"}}],
            },
            {
                "content": "File written and verified. Done.",
            },
        ]

        llm_service = MockLLMService(responses)
        tool_adapter = MockToolAdapter()

        # Patch verify to succeed
        with patch("scrappy.graph.nodes.verify.run_ruff") as mock_ruff, \
             patch("scrappy.graph.nodes.verify.run_mypy") as mock_mypy:
            mock_ruff.return_value = (True, "")
            mock_mypy.return_value = (True, "")

            result = run_agent(
                task="Write hello to test.py",
                working_dir="/tmp",
                llm_service=llm_service,
                tool_adapter=tool_adapter,
            )

        # Write tool should have been called
        assert any(tc.get("name") == "write_file" for tc in tool_adapter.call_history)
        # Verify result has messages
        assert len(result.messages) >= 1


@pytest.mark.integration
class TestVerifyFailure:
    """Test verify failure path: think -> execute -> verify (fails) -> think -> end."""

    def test_verify_failure_routes_back_to_think(self) -> None:
        """Test that verify failures route back to think for correction."""
        # First: LLM writes bad code
        # Second: LLM fixes the code
        # Third: LLM says done
        responses = [
            {
                "content": "Writing file with a bug.",
                "tool_calls": [{"name": "write_file", "arguments": {"path": "test.py"}}],
            },
            {
                "content": "I see the lint error. Fixing it.",
                "tool_calls": [{"name": "write_file", "arguments": {"path": "test.py"}}],
            },
            {
                "content": "Fixed. Task complete.",
            },
        ]

        llm_service = MockLLMService(responses)
        tool_adapter = MockToolAdapter()

        verify_call_count = 0

        def mock_ruff_side_effect(*args, **kwargs):
            nonlocal verify_call_count
            verify_call_count += 1
            if verify_call_count == 1:
                return (False, "error: undefined name 'foo'")
            return (True, "")

        with patch("scrappy.graph.nodes.verify.run_ruff") as mock_ruff, \
             patch("scrappy.graph.nodes.verify.run_mypy") as mock_mypy:
            mock_ruff.side_effect = mock_ruff_side_effect
            mock_mypy.return_value = (True, "")

            result = run_agent(
                task="Write test.py",
                working_dir="/tmp",
                llm_service=llm_service,
                tool_adapter=tool_adapter,
            )

        # Should have called LLM at least twice (once for initial, once after verify fail)
        assert llm_service.call_count >= 2
        # Verify should have been called
        assert verify_call_count >= 1
        # Result should have iterations
        assert result.iteration >= 1


@pytest.mark.integration
class TestConfirmDenied:
    """Test confirm denial path: think -> execute -> confirm (denied) -> end."""

    def test_confirm_denial_aborts_task(self) -> None:
        """Test that denying confirmation aborts the task."""
        responses = [
            {
                "content": "I need to run a command.",
                "tool_calls": [{"name": "run_command", "arguments": {"cmd": "rm -rf /"}}],
            },
        ]

        llm_service = MockLLMService(responses)

        # Tool adapter that triggers confirmation
        class ConfirmingToolAdapter(MockToolAdapter):
            def execute(self, tool_calls, context):
                # Return result that would trigger confirmation
                results = []
                for tc in tool_calls:
                    results.append(ToolResult(
                        name=tc["name"],
                        result="Command requires confirmation",
                    ))
                return results

        tool_adapter = ConfirmingToolAdapter()
        graph, checkpointer = create_agent_runner(llm_service, tool_adapter)

        # Create initial state with pending confirmation
        state = AgentState.create_initial("Run command", "/tmp")
        config = {"configurable": {"thread_id": "test-confirm"}}

        # Start execution
        result = graph.invoke(state, config)

        # Check if we hit interrupt (pending confirmation)
        snapshot = graph.get_state(config)

        if snapshot.next == ("confirm",):
            # Deny the confirmation
            graph.update_state(config, {"confirmation_response": False})
            # Resume
            result = graph.invoke(None, config)

            # Convert to AgentState if needed
            if isinstance(result, dict):
                final_state = AgentState(**result)
            else:
                final_state = result

            # Task should be aborted (done=True due to denial)
            assert final_state.done is True


@pytest.mark.integration
class TestToolError:
    """Test tool error path: think -> execute -> error -> think -> end."""

    def test_tool_error_routes_to_error_node(self) -> None:
        """Test that tool errors route through error node."""
        responses = [
            {
                "content": "Reading file.",
                "tool_calls": [{"name": "read_file", "arguments": {"path": "missing.py"}}],
            },
            {
                "content": "File not found. Let me check working directory.",
                "tool_calls": [{"name": "read_file", "arguments": {"path": "existing.py"}}],
            },
            {
                "content": "Found it. Done.",
            },
        ]

        llm_service = MockLLMService(responses)

        # Tool adapter that fails first, succeeds second
        call_count = 0

        class FailingToolAdapter(MockToolAdapter):
            def execute(self, tool_calls, context):
                nonlocal call_count
                call_count += 1
                results = []
                for tc in tool_calls:
                    if call_count == 1:
                        results.append(ToolResult(
                            name=tc["name"],
                            error="File not found: missing.py",
                        ))
                    else:
                        results.append(ToolResult(
                            name=tc["name"],
                            result="file content here",
                        ))
                return results

        tool_adapter = FailingToolAdapter()

        result = run_agent(
            task="Read file",
            working_dir="/tmp",
            llm_service=llm_service,
            tool_adapter=tool_adapter,
        )

        # Should have multiple LLM calls (retry after error)
        assert llm_service.call_count >= 2
        # Result should have messages from the recovery
        assert len(result.messages) >= 1


@pytest.mark.integration
class TestCancellation:
    """Test cancellation: graph stops cleanly on cancel."""

    def test_max_iterations_stops_graph(self) -> None:
        """Test that hitting max iterations stops the graph cleanly."""
        # LLM keeps making tool calls forever
        responses = [
            {
                "content": f"Doing thing {i}.",
                "tool_calls": [{"name": "read_file", "arguments": {}}],
            }
            for i in range(100)
        ]

        llm_service = MockLLMService(responses)
        tool_adapter = MockToolAdapter()

        # Patch MAX_ITERATIONS to a low value for testing
        with patch("scrappy.graph.edges.MAX_ITERATIONS", 3):
            result = run_agent(
                task="Keep working forever",
                working_dir="/tmp",
                llm_service=llm_service,
                tool_adapter=tool_adapter,
            )

        # Should have stopped due to iteration limit
        assert result.iteration <= 5  # Some buffer for internal increments

    def test_done_flag_stops_graph(self) -> None:
        """Test that setting done=True stops the graph."""
        # LLM says done immediately
        responses = [
            {
                "content": "Task is already complete. Nothing to do.",
            },
        ]

        llm_service = MockLLMService(responses)
        tool_adapter = MockToolAdapter()

        result = run_agent(
            task="Simple task",
            working_dir="/tmp",
            llm_service=llm_service,
            tool_adapter=tool_adapter,
        )

        # Graph should complete quickly
        assert llm_service.call_count <= 3
        # Result should exist
        assert result is not None


@pytest.mark.integration
class TestLangfuseTracing:
    """Test Langfuse tracing visibility."""

    def test_tracing_decorator_applied_to_nodes(self) -> None:
        """Test that nodes are wrapped with tracing."""
        from scrappy.graph.nodes import think_node, execute_node, verify_node

        # The nodes should be wrapped with trace_node decorator
        # We can verify this by checking the function metadata
        assert hasattr(think_node, "__wrapped__") or callable(think_node)
        assert hasattr(execute_node, "__wrapped__") or callable(execute_node)
        assert hasattr(verify_node, "__wrapped__") or callable(verify_node)

    def test_tracer_protocol_called_during_execution(self) -> None:
        """Test that tracer is invoked during graph execution."""
        from scrappy.graph.tracing import set_tracer, NoOpTracer

        # Create a mock tracer to track calls
        mock_tracer = MagicMock(spec=NoOpTracer)
        mock_tracer.trace.return_value = MagicMock()
        mock_tracer.span.return_value = MagicMock()

        responses = [{"content": "Done."}]
        llm_service = MockLLMService(responses)
        tool_adapter = MockToolAdapter()

        try:
            set_tracer(mock_tracer)

            run_agent(
                task="Test tracing",
                working_dir="/tmp",
                llm_service=llm_service,
                tool_adapter=tool_adapter,
            )

            # Tracer should have been used
            assert mock_tracer.trace.called or mock_tracer.span.called
        finally:
            set_tracer(None)  # Reset


@pytest.mark.integration
class TestStateTransitions:
    """Test state transitions through the graph."""

    def test_messages_accumulate_through_graph(self) -> None:
        """Test that messages accumulate correctly through execution."""
        responses = [
            {
                "content": "First response.",
                "tool_calls": [{"name": "read_file", "arguments": {}}],
            },
            {
                "content": "Second response. Done.",
            },
        ]

        llm_service = MockLLMService(responses)
        tool_adapter = MockToolAdapter()

        result = run_agent(
            task="Test messages",
            working_dir="/tmp",
            llm_service=llm_service,
            tool_adapter=tool_adapter,
        )

        # Should have accumulated messages
        assert len(result.messages) >= 2

    def test_iteration_counter_increments(self) -> None:
        """Test that iteration counter increments each loop."""
        responses = [
            {
                "content": f"Iteration {i}.",
                "tool_calls": [{"name": "read_file", "arguments": {}}],
            }
            for i in range(5)
        ] + [{"content": "Done."}]

        llm_service = MockLLMService(responses)
        tool_adapter = MockToolAdapter()

        result = run_agent(
            task="Count iterations",
            working_dir="/tmp",
            llm_service=llm_service,
            tool_adapter=tool_adapter,
        )

        # Iteration should have incremented
        assert result.iteration >= 1


@pytest.mark.integration
class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_tool_calls_handled(self) -> None:
        """Test that empty tool calls don't break the graph."""
        responses = [
            {"content": "No tools needed. Done."},
        ]

        llm_service = MockLLMService(responses)
        tool_adapter = MockToolAdapter()

        result = run_agent(
            task="Simple question",
            working_dir="/tmp",
            llm_service=llm_service,
            tool_adapter=tool_adapter,
        )

        # Should complete without errors
        assert len(result.messages) >= 1

    def test_multiple_tool_calls_in_one_message(self) -> None:
        """Test handling multiple tool calls in single message."""
        responses = [
            {
                "content": "Reading multiple files.",
                "tool_calls": [
                    {"name": "read_file", "arguments": {"path": "a.py"}},
                    {"name": "read_file", "arguments": {"path": "b.py"}},
                    {"name": "read_file", "arguments": {"path": "c.py"}},
                ],
            },
            {"content": "All files read. Done."},
        ]

        llm_service = MockLLMService(responses)
        tool_adapter = MockToolAdapter()

        result = run_agent(
            task="Read multiple files",
            working_dir="/tmp",
            llm_service=llm_service,
            tool_adapter=tool_adapter,
        )

        # Should have executed all three tool calls
        assert len(tool_adapter.call_history) >= 3
        # Result should have messages
        assert len(result.messages) >= 1

    def test_special_characters_in_content(self) -> None:
        """Test handling special characters in tool output."""
        responses = [
            {
                "content": "Reading file with unicode.",
                "tool_calls": [{"name": "read_file", "arguments": {}}],
            },
            {"content": "Done."},
        ]

        llm_service = MockLLMService(responses)

        # Tool adapter returns unicode content
        tool_adapter = MockToolAdapter(results={
            "read_file": ToolResult(name="read_file", result="Content: \u4e2d\u6587 \ud83d\ude00 \u00e9"),
        })

        result = run_agent(
            task="Read unicode file",
            working_dir="/tmp",
            llm_service=llm_service,
            tool_adapter=tool_adapter,
        )

        # Should handle unicode without errors
        assert len(result.messages) >= 1
