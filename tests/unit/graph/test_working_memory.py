"""
Unit tests for working memory integration in the graph package.

Tests:
- WorkingMemoryProtocol compliance
- WorkingMemoryAdapter wrapping
- execute_node working memory tracking
- think_node context augmentation
"""

from pathlib import Path
from typing import Optional

import pytest

from scrappy.graph.protocols import WorkingMemoryProtocol
from scrappy.graph.nodes.execute import (
    WorkingMemoryAdapter,
    execute_node,
    _default_context_factory,
)
from scrappy.graph.nodes.think import build_system_prompt
from scrappy.graph.state import AgentState, Message, ToolCall, ToolResult


# =============================================================================
# Test Doubles
# =============================================================================


class MockWorkingMemory:
    """Mock implementation of WorkingMemoryProtocol for testing."""

    def __init__(self):
        self.file_reads: list[tuple[str, str, int]] = []
        self.searches: list[tuple[str, list]] = []
        self.git_operations: list[tuple[str, str]] = []
        self.discoveries: list[tuple[str, str]] = []
        self._context = ""

    def remember_file_read(self, path: str, content: str, lines: int = 0) -> None:
        self.file_reads.append((path, content, lines))

    def remember_search(self, query: str, results: list) -> None:
        self.searches.append((query, results))

    def remember_git_operation(self, operation: str, output: str) -> None:
        self.git_operations.append((operation, output))

    def add_discovery(self, finding: str, location: str = "") -> None:
        self.discoveries.append((finding, location))

    def get_context(self) -> str:
        return self._context

    def set_context(self, context: str) -> None:
        """Test helper to set context string."""
        self._context = context


class MockToolAdapter:
    """Mock tool adapter for testing execute node."""

    def __init__(
        self,
        results: Optional[list[ToolResult]] = None,
        exception: Optional[Exception] = None,
    ):
        self.results = results or []
        self.exception = exception
        self.executed_calls: list = []

    def execute(self, tool_calls: list[ToolCall], context) -> list[ToolResult]:
        """Record calls and return mock results."""
        self.executed_calls.append((tool_calls, context))

        if self.exception:
            raise self.exception

        if self.results:
            return self.results
        return [
            ToolResult(name=tc["function"]["name"], result="mock result")
            for tc in tool_calls
        ]

    def get_tool_names(self) -> list[str]:
        return ["read_file", "write_file"]

    def get_tool_schemas(self) -> list[dict]:
        return []


def make_tool_call(id: str, name: str, arguments: str = "{}") -> ToolCall:
    """Create a ToolCall in OpenAI format for testing."""
    return {
        "type": "function",
        "id": id,
        "function": {
            "name": name,
            "arguments": arguments,
        },
    }


def create_test_state(
    input_text: str = "Test task",
    working_dir: str = "/tmp/test",
    messages: Optional[list[Message]] = None,
    files_changed: Optional[list[str]] = None,
) -> AgentState:
    """Create a test AgentState."""
    return AgentState(
        input=input_text,
        original_task=input_text,
        working_dir=working_dir,
        messages=messages or [],
        files_changed=files_changed or [],
    )


# =============================================================================
# WorkingMemoryProtocol Tests
# =============================================================================


class TestWorkingMemoryProtocol:
    """Tests for WorkingMemoryProtocol compliance."""

    def test_mock_implements_protocol(self):
        """MockWorkingMemory should implement WorkingMemoryProtocol."""
        memory = MockWorkingMemory()
        assert isinstance(memory, WorkingMemoryProtocol)

    def test_remember_file_read(self):
        """Should track file reads."""
        memory = MockWorkingMemory()
        memory.remember_file_read("test.py", "print('hello')", 1)
        assert len(memory.file_reads) == 1
        assert memory.file_reads[0] == ("test.py", "print('hello')", 1)

    def test_remember_search(self):
        """Should track searches."""
        memory = MockWorkingMemory()
        memory.remember_search("test query", ["result1", "result2"])
        assert len(memory.searches) == 1
        assert memory.searches[0] == ("test query", ["result1", "result2"])

    def test_remember_git_operation(self):
        """Should track git operations."""
        memory = MockWorkingMemory()
        memory.remember_git_operation("git status", "On branch main")
        assert len(memory.git_operations) == 1
        assert memory.git_operations[0] == ("git status", "On branch main")

    def test_add_discovery(self):
        """Should track discoveries."""
        memory = MockWorkingMemory()
        memory.add_discovery("Found config file", "config.yaml")
        assert len(memory.discoveries) == 1
        assert memory.discoveries[0] == ("Found config file", "config.yaml")

    def test_get_context(self):
        """Should return context string."""
        memory = MockWorkingMemory()
        memory.set_context("test context")
        assert memory.get_context() == "test context"


# =============================================================================
# WorkingMemoryAdapter Tests
# =============================================================================


class TestWorkingMemoryAdapter:
    """Tests for WorkingMemoryAdapter wrapping."""

    def test_adapter_wraps_working_memory(self):
        """Adapter should expose working_memory attribute."""
        memory = MockWorkingMemory()
        adapter = WorkingMemoryAdapter(memory)
        assert adapter.working_memory is memory

    def test_adapter_can_be_used_as_orchestrator(self):
        """Adapter should be usable as ToolContext.orchestrator."""
        memory = MockWorkingMemory()
        adapter = WorkingMemoryAdapter(memory)

        # Simulate what ToolContext does
        adapter.working_memory.remember_file_read("test.py", "content", 10)

        assert len(memory.file_reads) == 1


# =============================================================================
# execute_node Integration Tests
# =============================================================================


class TestExecuteNodeWorkingMemory:
    """Tests for working memory integration in execute_node."""

    def test_default_context_factory_with_working_memory(self):
        """Default factory should create context with working memory adapter."""
        memory = MockWorkingMemory()
        context = _default_context_factory("/tmp/test", memory)

        # Context should have orchestrator set
        assert context.orchestrator is not None
        assert context.orchestrator.working_memory is memory

    def test_default_context_factory_without_working_memory(self):
        """Default factory should work without working memory."""
        context = _default_context_factory("/tmp/test", None)

        # Context should have no orchestrator
        assert context.orchestrator is None

    def test_execute_node_accepts_working_memory(self):
        """execute_node should accept working_memory parameter."""
        # Create state with a tool call
        state = create_test_state(
            messages=[
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [make_tool_call("1", "read_file", '{"path": "test.py"}')],
                }
            ]
        )

        memory = MockWorkingMemory()
        adapter = MockToolAdapter(results=[ToolResult(name="read_file", result="file content")])

        # Should not raise
        result = execute_node(state, adapter, working_memory=memory)

        # Verify execution happened
        assert len(adapter.executed_calls) == 1


# =============================================================================
# think_node Integration Tests
# =============================================================================


class TestThinkNodeWorkingMemory:
    """Tests for working memory integration in think_node."""

    def test_build_system_prompt_without_working_memory(self):
        """build_system_prompt should work without working memory."""
        state = create_test_state()
        prompt = build_system_prompt(state, ["read_file", "write_file"])

        # Should not contain working memory section
        assert "<working_memory>" not in prompt

    def test_build_system_prompt_with_empty_context(self):
        """build_system_prompt should not add section if context is empty."""
        state = create_test_state()
        memory = MockWorkingMemory()
        memory.set_context("")  # Empty context

        prompt = build_system_prompt(state, ["read_file"], memory)

        # Should not contain working memory section
        assert "<working_memory>" not in prompt

    def test_build_system_prompt_with_context(self):
        """build_system_prompt should include working memory context."""
        state = create_test_state()
        memory = MockWorkingMemory()
        memory.set_context("[Session Working Memory]\nRecently accessed files:\n  - test.py (10 lines)")

        prompt = build_system_prompt(state, ["read_file"], memory)

        # Should contain working memory section
        assert "<working_memory>" in prompt
        assert "Recently accessed files" in prompt
        assert "test.py" in prompt

    def test_build_system_prompt_preserves_other_sections(self):
        """Working memory should not interfere with other prompt sections."""
        state = create_test_state(files_changed=["modified.py"])
        memory = MockWorkingMemory()
        memory.set_context("test context")

        prompt = build_system_prompt(state, ["read_file"], memory)

        # Should have both sections
        assert "<files_changed>" in prompt
        assert "<working_memory>" in prompt
        assert "modified.py" in prompt
        assert "test context" in prompt


# =============================================================================
# End-to-end Integration Tests
# =============================================================================


class TestWorkingMemoryEndToEnd:
    """End-to-end tests for working memory flow."""

    def test_memory_flows_through_graph_components(self):
        """Working memory should be accessible throughout the graph."""
        memory = MockWorkingMemory()

        # Simulate the flow:
        # 1. Create context with memory
        context = _default_context_factory("/tmp/test", memory)

        # 2. Tool execution would call context.remember_*
        context.remember_file_read("test.py", "content", 5)

        # 3. Memory should be updated
        assert len(memory.file_reads) == 1

        # 4. Context should be available for think node
        memory.set_context("[Session Working Memory]\nRecently accessed files:\n  - test.py (5 lines)")

        # 5. build_system_prompt should include it
        state = create_test_state()
        prompt = build_system_prompt(state, [], memory)

        assert "test.py (5 lines)" in prompt
