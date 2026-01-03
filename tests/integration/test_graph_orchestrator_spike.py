"""
Spike: Prove LangGraph can integrate with orchestrator.

This spike proves:
1. Graph nodes can call orchestrator.delegate_with_tools()
2. Classification can be done via orchestrator.delegate_structured()
3. Context (system_prompt, tools) can vary by task_type via state

Run with: python -m pytest tests/integration/test_graph_orchestrator_spike.py -v -s
"""

import pytest
from typing import Any, Literal, Optional
from unittest.mock import Mock, MagicMock
from pydantic import BaseModel, Field

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver


# =============================================================================
# Extended State with task-specific context
# =============================================================================

class SpikeState(BaseModel):
    """Extended state proving context injection works."""

    # Core fields
    input: str
    working_dir: str = "."
    messages: list[dict] = Field(default_factory=list)
    iteration: int = 0
    done: bool = False

    # Task-specific context (set by classify, used by think)
    task_type: Optional[Literal["agent", "research", "chat", "direct"]] = None
    system_prompt: Optional[str] = None
    active_tools: list[dict] = Field(default_factory=list)

    # For assertions
    orchestrator_calls: list[dict] = Field(default_factory=list)


# =============================================================================
# Classification model (for delegate_structured)
# =============================================================================

class TaskClassification(BaseModel):
    """Pydantic model for structured classification response."""

    task_type: Literal["agent", "research", "chat", "direct"]
    reasoning: str


# =============================================================================
# Mock Orchestrator Protocol
# =============================================================================

class MockOrchestratorAdapter:
    """Mock orchestrator that records calls for assertions."""

    def __init__(self, classification_response: TaskClassification, llm_response: str):
        self._classification = classification_response
        self._llm_response = llm_response
        self.calls: list[dict] = []

    def delegate_structured(
        self,
        provider_name: str,
        prompt: str,
        response_model: type,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Mock structured response for classification."""
        self.calls.append({
            "method": "delegate_structured",
            "provider_name": provider_name,
            "prompt": prompt,
            "response_model": response_model.__name__,
            "system_prompt": system_prompt,
        })
        return self._classification

    def delegate_with_tools(
        self,
        provider_name: Optional[str] = None,
        prompt: str = "",
        tools: list[dict] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Mock:
        """Mock LLM response with tools."""
        self.calls.append({
            "method": "delegate_with_tools",
            "provider_name": provider_name,
            "prompt": prompt,
            "tools": tools,
            "system_prompt": system_prompt,
        })
        response = Mock()
        response.content = self._llm_response
        response.tool_calls = []
        return response


# =============================================================================
# Context builders (would live in prompts module)
# =============================================================================

SYSTEM_PROMPTS = {
    "agent": "You are a coding assistant. Use tools to modify files and run commands.",
    "research": "You are a research assistant. Search and read files to answer questions.",
    "chat": "You are a helpful assistant. Answer conversationally.",
    "direct": "Execute the command directly without additional processing.",
}

TOOL_SETS = {
    "agent": [
        {"type": "function", "function": {"name": "write_file", "description": "Write to file"}},
        {"type": "function", "function": {"name": "run_command", "description": "Run shell command"}},
    ],
    "research": [
        {"type": "function", "function": {"name": "read_file", "description": "Read file"}},
        {"type": "function", "function": {"name": "search", "description": "Search codebase"}},
    ],
    "chat": [],  # No tools for chat
    "direct": [
        {"type": "function", "function": {"name": "run_command", "description": "Run shell command"}},
    ],
}


def build_context(task_type: str) -> tuple[str, list[dict]]:
    """Build system prompt and tools for task type."""
    return SYSTEM_PROMPTS.get(task_type, ""), TOOL_SETS.get(task_type, [])


# =============================================================================
# Graph Nodes using Orchestrator
# =============================================================================

def make_classify_node(orchestrator: MockOrchestratorAdapter):
    """Create classify node that uses orchestrator.delegate_structured()."""

    def classify_node(state: SpikeState) -> SpikeState:
        """Classify task and inject context into state."""

        # Call orchestrator for classification
        classification = orchestrator.delegate_structured(
            provider_name="fast",
            prompt=f"Classify this task: {state.input}",
            response_model=TaskClassification,
            system_prompt="You are a task classifier.",
        )

        # Build context based on classification
        system_prompt, tools = build_context(classification.task_type)

        # Update state with classification results
        return state.model_copy(update={
            "task_type": classification.task_type,
            "system_prompt": system_prompt,
            "active_tools": tools,
            "orchestrator_calls": orchestrator.calls.copy(),
        })

    return classify_node


def make_think_node(orchestrator: MockOrchestratorAdapter):
    """Create think node that uses orchestrator.delegate_with_tools()."""

    def think_node(state: SpikeState) -> SpikeState:
        """Think using orchestrator with injected context."""

        # Use context from state (set by classify_node)
        response = orchestrator.delegate_with_tools(
            provider_name="quality",
            prompt=state.input,
            tools=state.active_tools,  # Tools filtered by task_type
            system_prompt=state.system_prompt,  # Prompt for task_type
        )

        # Build message
        new_message = {
            "role": "assistant",
            "content": response.content,
        }

        return state.model_copy(update={
            "messages": state.messages + [new_message],
            "iteration": state.iteration + 1,
            "done": True,
            "orchestrator_calls": orchestrator.calls.copy(),
        })

    return think_node


def should_continue(state: SpikeState) -> str:
    """Route based on done flag."""
    return "end" if state.done else "think"


# =============================================================================
# Tests
# =============================================================================

class TestOrchestratorIntegrationSpike:
    """Prove orchestrator integration works with LangGraph."""

    def test_classify_node_calls_delegate_structured(self):
        """Prove classify_node can call orchestrator.delegate_structured()."""

        # Setup
        orchestrator = MockOrchestratorAdapter(
            classification_response=TaskClassification(
                task_type="agent",
                reasoning="User wants to write code",
            ),
            llm_response="I'll help you code.",
        )

        # Create node
        classify = make_classify_node(orchestrator)

        # Execute
        initial_state = SpikeState(input="write hello world in python")
        result = classify(initial_state)

        # Assert - orchestrator was called correctly
        assert len(orchestrator.calls) == 1
        call = orchestrator.calls[0]
        assert call["method"] == "delegate_structured"
        assert call["response_model"] == "TaskClassification"
        assert "write hello world" in call["prompt"]

        # Assert - state was updated with classification
        assert result.task_type == "agent"
        assert result.system_prompt == SYSTEM_PROMPTS["agent"]
        assert len(result.active_tools) == 2  # write_file, run_command

    def test_think_node_uses_context_from_state(self):
        """Prove think_node uses system_prompt and tools from state."""

        # Setup
        orchestrator = MockOrchestratorAdapter(
            classification_response=TaskClassification(task_type="research", reasoning=""),
            llm_response="Here's what I found.",
        )

        # Create node with pre-set context (as if classify ran)
        think = make_think_node(orchestrator)

        # State with context already set
        state = SpikeState(
            input="what does this function do?",
            task_type="research",
            system_prompt=SYSTEM_PROMPTS["research"],
            active_tools=TOOL_SETS["research"],
        )

        # Execute
        result = think(state)

        # Assert - delegate_with_tools was called with injected context
        assert len(orchestrator.calls) == 1
        call = orchestrator.calls[0]
        assert call["method"] == "delegate_with_tools"
        assert call["system_prompt"] == SYSTEM_PROMPTS["research"]
        assert call["tools"] == TOOL_SETS["research"]

        # Assert - response was added to messages
        assert result.done is True
        assert len(result.messages) == 1
        assert result.messages[0]["content"] == "Here's what I found."

    def test_full_graph_with_classify_then_think(self):
        """Prove full graph: classify -> think using orchestrator throughout."""

        # Setup orchestrator
        orchestrator = MockOrchestratorAdapter(
            classification_response=TaskClassification(
                task_type="chat",
                reasoning="Just a greeting",
            ),
            llm_response="Hello! How can I help you today?",
        )

        # Build graph
        builder: StateGraph[SpikeState] = StateGraph(SpikeState)

        builder.add_node("classify", make_classify_node(orchestrator))
        builder.add_node("think", make_think_node(orchestrator))

        builder.set_entry_point("classify")
        builder.add_edge("classify", "think")
        builder.add_conditional_edges(
            "think",
            should_continue,
            {"think": "think", "end": END},
        )

        graph = builder.compile(checkpointer=MemorySaver())

        # Execute
        initial_state = SpikeState(input="hello")
        config = {"configurable": {"thread_id": "spike-test"}}

        result = graph.invoke(initial_state, config)

        # Convert result
        if isinstance(result, dict):
            final_state = SpikeState(**result)
        else:
            final_state = result

        # Assert - both orchestrator methods were called
        assert len(orchestrator.calls) == 2

        # First call: classify
        assert orchestrator.calls[0]["method"] == "delegate_structured"

        # Second call: think (with chat context - no tools)
        assert orchestrator.calls[1]["method"] == "delegate_with_tools"
        assert orchestrator.calls[1]["system_prompt"] == SYSTEM_PROMPTS["chat"]
        assert orchestrator.calls[1]["tools"] == []  # Chat has no tools

        # Assert - final state
        assert final_state.done is True
        assert final_state.task_type == "chat"
        assert "Hello!" in final_state.messages[0]["content"]

    def test_different_task_types_get_different_tools(self):
        """Prove task_type determines which tools are available."""

        test_cases = [
            ("agent", ["write_file", "run_command"]),
            ("research", ["read_file", "search"]),
            ("chat", []),
            ("direct", ["run_command"]),
        ]

        for task_type, expected_tool_names in test_cases:
            orchestrator = MockOrchestratorAdapter(
                classification_response=TaskClassification(
                    task_type=task_type,
                    reasoning="test",
                ),
                llm_response="response",
            )

            classify = make_classify_node(orchestrator)
            state = SpikeState(input="test")
            result = classify(state)

            # Extract tool names from schemas
            actual_tool_names = [
                t["function"]["name"] for t in result.active_tools
            ]

            assert actual_tool_names == expected_tool_names, (
                f"task_type={task_type}: expected {expected_tool_names}, got {actual_tool_names}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
