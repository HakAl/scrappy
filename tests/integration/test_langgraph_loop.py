"""
Test to debug the infinite loop issue in LangGraph agent.

Run with: python -m pytest tests/integration/test_langgraph_loop.py -v -s
"""

import pytest
from unittest.mock import Mock, MagicMock
from langgraph.checkpoint.memory import MemorySaver

from scrappy.graph.agent import build_graph
from scrappy.graph.state import AgentState
from scrappy.graph.tools import ToolAdapter


class MockLLMResponse:
    """Mock LLM response object."""

    def __init__(self, content: str = "", tool_calls: list | None = None):
        self.content = content
        self.tool_calls = tool_calls or []


class TracingLLMService:
    """LLM service that traces all calls for debugging."""

    def __init__(self, responses: list):
        """
        Args:
            responses: List of (content, tool_calls) tuples to return in sequence
        """
        self._responses = responses
        self._call_index = 0
        self.calls = []

    def completion_sync(self, model, messages, **kwargs):
        """Return pre-configured response and trace the call."""
        print(f"\n{'='*60}")
        print(f"LLM CALL #{self._call_index + 1}")
        print(f"Model: {model}")
        print(f"Messages count: {len(messages)}")

        if messages:
            last_msg = messages[-1]
            print(f"Last message role: {last_msg.get('role')}")
            content = str(last_msg.get('content', ''))[:200]
            print(f"Last message content: {content}...")
        print(f"Tools provided: {'tools' in kwargs}")
        print(f"{'='*60}")

        # Get next response
        if self._call_index < len(self._responses):
            content, tool_calls = self._responses[self._call_index]
        else:
            # Default: return done response
            content = "Task completed."
            tool_calls = []

        self._call_index += 1

        response = MockLLMResponse(content, tool_calls)

        print(f"\nRESPONSE:")
        print(f"Content: {response.content[:200] if response.content else '(empty)'}...")
        print(f"Tool calls: {len(response.tool_calls)}")
        for tc in response.tool_calls:
            print(f"  - {tc.get('name') or tc.get('function', {}).get('name')}")
        print(f"{'='*60}\n")

        self.calls.append({
            'messages': messages,
            'response_content': response.content,
            'tool_calls': response.tool_calls,
        })

        # Return (response, task_record)
        return response, {}


class MockToolAdapter:
    """Tool adapter that returns mock results."""

    def get_tool_names(self) -> list[str]:
        return ["write_file", "read_file", "run_command"]

    def get_tool_schemas(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write content to a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                },
            }
        ]

    def execute(self, tool_calls, context):
        """Execute tools and return results."""
        from scrappy.graph.state import ToolResult
        results = []
        for tc in tool_calls:
            func_name = tc.get("function", {}).get("name", "unknown")
            print(f"  [EXECUTE] {func_name}")
            results.append(ToolResult(name=func_name, result="Success"))
        return results


def test_simple_task_completes_with_mocks():
    """
    A simple task should complete in a few iterations.

    Flow expected:
    1. think: LLM returns tool call (write_file)
    2. execute: Tool runs
    3. should_continue: files_changed -> verify
    4. verify: runs checks
    5. think: LLM returns final message (no tool calls)
    6. execute: no-op
    7. should_continue: done=True -> end
    """
    # Mock responses: first a tool call, then final message
    responses = [
        # First call: LLM decides to write a file
        (
            "I'll create the hello.cpp file for you.",
            [
                {
                    "type": "function",
                    "id": "call_1",
                    "function": {
                        "name": "write_file",
                        "arguments": '{"path": "hello.cpp", "content": "#include <iostream>\\nint main() { std::cout << \\"Hello World\\"; return 0; }"}',
                    },
                }
            ],
        ),
        # Second call: LLM confirms done (no tool calls)
        ("I've created hello.cpp with a Hello World program in C++.", []),
    ]

    llm_service = TracingLLMService(responses)
    tool_adapter = MockToolAdapter()

    # Build graph
    graph = build_graph(
        llm_service=llm_service,
        tool_adapter=tool_adapter,
        checkpointer=MemorySaver(),
        run_mypy_check=False,  # Skip mypy for speed
    )

    initial_state = AgentState.create_initial(
        "create a file called hello.cpp with a hello world program in c++",
        "/tmp/test",
    )
    config = {
        "configurable": {"thread_id": "test-loop"},
        "recursion_limit": 50,
    }

    print("\n\n=== STARTING GRAPH EXECUTION ===\n")

    result = graph.invoke(initial_state, config)

    if isinstance(result, dict):
        final_state = AgentState(**result)
    else:
        final_state = result

    print(f"\n\n=== FINAL STATE ===")
    print(f"Done: {final_state.done}")
    print(f"Iterations: {final_state.iteration}")
    print(f"Last error: {final_state.last_error}")
    print(f"Files changed: {final_state.files_changed}")
    print(f"Total LLM calls: {len(llm_service.calls)}")
    print(f"Message count: {len(final_state.messages)}")

    # Print message trace
    print("\n=== MESSAGE TRACE ===")
    for i, msg in enumerate(final_state.messages):
        role = msg.get("role", "?")
        content = str(msg.get("content", ""))[:100]
        tc = msg.get("tool_calls", [])
        tc_id = msg.get("tool_call_id", "")
        print(f"{i}: {role} - {content}... [tool_calls={len(tc)}, tool_call_id={tc_id}]")

    # Should complete successfully
    assert final_state.done, f"Agent did not complete. Last error: {final_state.last_error}"
    assert final_state.iteration <= 10, f"Too many iterations: {final_state.iteration}"


def test_immediate_completion():
    """
    If LLM returns final message with no tools, should complete immediately.
    """
    responses = [
        ("Hello! I can help you with coding tasks.", []),  # No tool calls
    ]

    llm_service = TracingLLMService(responses)
    tool_adapter = MockToolAdapter()

    graph = build_graph(
        llm_service=llm_service,
        tool_adapter=tool_adapter,
        checkpointer=MemorySaver(),
        run_mypy_check=False,
    )

    initial_state = AgentState.create_initial("say hello", "/tmp/test")
    config = {
        "configurable": {"thread_id": "test-immediate"},
        "recursion_limit": 10,
    }

    result = graph.invoke(initial_state, config)

    if isinstance(result, dict):
        final_state = AgentState(**result)
    else:
        final_state = result

    print(f"\nDone: {final_state.done}")
    print(f"Iterations: {final_state.iteration}")

    # Should complete in 1 iteration
    assert final_state.done, "Agent should be done"
    assert final_state.iteration == 1, f"Should be 1 iteration, got {final_state.iteration}"


def test_error_loop_terminates():
    """
    If LLM keeps erroring, should terminate after MAX_RETRIES (3).
    """
    class FailingLLMService:
        """LLM service that always fails."""

        def __init__(self):
            self.call_count = 0

        def completion_sync(self, model, messages, **kwargs):
            self.call_count += 1
            print(f"\n[LLM CALL #{self.call_count}] Raising exception...")
            raise ConnectionError("Simulated API failure")

    llm_service = FailingLLMService()
    tool_adapter = MockToolAdapter()

    graph = build_graph(
        llm_service=llm_service,
        tool_adapter=tool_adapter,
        checkpointer=MemorySaver(),
        run_mypy_check=False,
    )

    initial_state = AgentState.create_initial("test task", "/tmp/test")
    config = {
        "configurable": {"thread_id": "test-error-loop"},
        "recursion_limit": 50,
    }

    result = graph.invoke(initial_state, config)

    if isinstance(result, dict):
        final_state = AgentState(**result)
    else:
        final_state = result

    print(f"\nDone: {final_state.done}")
    print(f"Iterations: {final_state.iteration}")
    print(f"Error count: {final_state.error_count}")
    print(f"Last error: {final_state.last_error}")
    print(f"LLM calls: {llm_service.call_count}")

    # Should terminate after MAX_RETRIES (3) errors
    # Note: error_count in edges.py is checked with >= MAX_RETRIES (3)
    assert llm_service.call_count <= 5, f"Too many LLM calls: {llm_service.call_count}"
    assert final_state.iteration <= 10, f"Too many iterations: {final_state.iteration}"


def test_verify_failure_loop():
    """
    Test that verification failures don't cause infinite loops.

    Scenario:
    1. LLM returns tool call to write a Python file
    2. Tool executes successfully
    3. Verify runs ruff/mypy and fails
    4. Error is processed, LLM tries again
    5. Eventually should terminate
    """
    call_count = [0]

    class CountingLLMService:
        """LLM service that counts calls and returns predictable responses."""

        def completion_sync(self, model, messages, **kwargs):
            call_count[0] += 1
            print(f"\n[LLM CALL #{call_count[0]}]")

            # First call: write a file
            if call_count[0] == 1:
                return MockLLMResponse(
                    "I'll create the file.",
                    [
                        {
                            "type": "function",
                            "id": "call_1",
                            "function": {
                                "name": "write_file",
                                "arguments": '{"path": "test.py", "content": "bad syntax {{{"}',
                            },
                        }
                    ],
                ), {}

            # Subsequent calls: return done
            return MockLLMResponse("Task completed.", []), {}

    llm_service = CountingLLMService()
    tool_adapter = MockToolAdapter()

    graph = build_graph(
        llm_service=llm_service,
        tool_adapter=tool_adapter,
        checkpointer=MemorySaver(),
        run_mypy_check=False,  # Skip mypy, but ruff would still run if file exists
    )

    initial_state = AgentState.create_initial("write test.py", "/tmp/test")
    config = {
        "configurable": {"thread_id": "test-verify-loop"},
        "recursion_limit": 20,
    }

    result = graph.invoke(initial_state, config)

    if isinstance(result, dict):
        final_state = AgentState(**result)
    else:
        final_state = result

    print(f"\nDone: {final_state.done}")
    print(f"Iterations: {final_state.iteration}")
    print(f"Files verified: {final_state.files_verified}")
    print(f"LLM calls: {call_count[0]}")

    # Should complete (file doesn't actually exist, so verify will pass/skip)
    assert final_state.done, "Agent should complete"
    assert call_count[0] <= 5, f"Too many LLM calls: {call_count[0]}"


def test_infinite_tool_calls_hits_iteration_limit():
    """
    If LLM keeps returning tool calls forever, should hit MAX_ITERATIONS (50).

    Note: LangGraph recursion_limit counts TOTAL node invocations.
    With think->execute pattern, each iteration = 2 nodes.
    MAX_ITERATIONS=50 means up to 100 node invocations.
    Set recursion_limit higher to let our check trigger.
    """
    call_count = [0]

    class InfiniteToolCallsLLM:
        """LLM that always returns tool calls, never done."""

        def completion_sync(self, model, messages, **kwargs):
            call_count[0] += 1
            # Only print every 10th call to reduce noise
            if call_count[0] % 10 == 1:
                print(f"\n[LLM CALL #{call_count[0]}] Returning tool call...")

            return MockLLMResponse(
                "Let me read a file.",
                [
                    {
                        "type": "function",
                        "id": f"call_{call_count[0]}",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path": "test.txt"}',
                        },
                    }
                ],
            ), {}

    llm_service = InfiniteToolCallsLLM()
    tool_adapter = MockToolAdapter()

    graph = build_graph(
        llm_service=llm_service,
        tool_adapter=tool_adapter,
        checkpointer=MemorySaver(),
        run_mypy_check=False,
    )

    initial_state = AgentState.create_initial("read all files", "/tmp/test")
    config = {
        "configurable": {"thread_id": "test-infinite-tools"},
        # MAX_ITERATIONS=50, each iteration = 2 nodes (think+execute)
        # Need recursion_limit > 100 to let our check trigger
        "recursion_limit": 150,
    }

    result = graph.invoke(initial_state, config)

    if isinstance(result, dict):
        final_state = AgentState(**result)
    else:
        final_state = result

    print(f"\nDone: {final_state.done}")
    print(f"Iterations: {final_state.iteration}")
    print(f"LLM calls: {call_count[0]}")

    # Should terminate at MAX_ITERATIONS (50)
    from scrappy.graph.edges import MAX_ITERATIONS
    assert final_state.iteration >= MAX_ITERATIONS, (
        f"Should reach MAX_ITERATIONS ({MAX_ITERATIONS}), got {final_state.iteration}"
    )
    # done=False because we never returned a final message
    assert not final_state.done, "Should not be done (never returned final message)"


def test_empty_response_terminates():
    """
    Empty LLM response (no content, no tool calls) should be treated as an error
    and terminate after MAX_RETRIES (3).

    This test verifies the fix for the infinite loop bug.
    """
    call_count = [0]

    class EmptyResponseLLM:
        """LLM that returns empty response - simulates API returning nothing."""

        def completion_sync(self, model, messages, **kwargs):
            call_count[0] += 1
            print(f"\n[LLM CALL #{call_count[0]}] Returning EMPTY response...")
            # Empty content, no tool calls - treated as error now
            return MockLLMResponse("", []), {}

    llm_service = EmptyResponseLLM()
    tool_adapter = MockToolAdapter()

    graph = build_graph(
        llm_service=llm_service,
        tool_adapter=tool_adapter,
        checkpointer=MemorySaver(),
        run_mypy_check=False,
    )

    initial_state = AgentState.create_initial("say hello", "/tmp/test")
    config = {
        "configurable": {"thread_id": "test-empty"},
        "recursion_limit": 30,
    }

    result = graph.invoke(initial_state, config)
    if isinstance(result, dict):
        final_state = AgentState(**result)
    else:
        final_state = result

    print(f"\nDone: {final_state.done}")
    print(f"Iterations: {final_state.iteration}")
    print(f"Error count: {final_state.error_count}")
    print(f"Last error: {final_state.last_error}")
    print(f"LLM calls: {call_count[0]}")

    # Should terminate after MAX_RETRIES (3) errors
    assert call_count[0] == 3, f"Should stop after 3 errors, got {call_count[0]}"
    assert final_state.error_count == 3, f"Error count should be 3, got {final_state.error_count}"
    assert "empty response" in final_state.last_error.lower(), "Should have empty response error"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
