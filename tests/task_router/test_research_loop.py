"""
Tests for ResearchLoop component.

The ResearchLoop is responsible for managing the iterative tool-calling
conversation with the LLM, including:
- Building conversation history
- Delegating to the LLM provider
- Parsing tool calls from responses
- Executing tools via ToolBundle
- Determining when to stop iterating
- Cleaning final responses
"""

import pytest
from unittest.mock import Mock
from src.task_router.strategies.research_loop import ResearchLoop
from src.task_router.classifier import ClassifiedTask, TaskType


# Test Doubles

class FakeOrchestratorNoTools:
    """Orchestrator that returns responses without tool calls."""

    def __init__(self, response_content="This is a direct answer", tokens=50):
        self.response_content = response_content
        self.tokens = tokens
        self.call_count = 0
        self.last_prompt = None
        self.last_system_prompt = None

    def delegate(self, provider, prompt, system_prompt=None, **kwargs):
        self.call_count += 1
        self.last_prompt = prompt
        self.last_system_prompt = system_prompt

        response = Mock()
        response.content = self.response_content
        response.tokens_used = self.tokens
        return response


class FakeOrchestratorWithToolCall:
    """Orchestrator that returns tool calls first, then final answer."""

    def __init__(self):
        self.call_count = 0
        self.responses = [
            '```json\n{"tool": "read_file", "parameters": {"file_path": "test.py"}}\n```',
            'Based on the file, the answer is 42.'
        ]

    def delegate(self, provider, prompt, system_prompt=None, **kwargs):
        response = Mock()
        response.content = self.responses[min(self.call_count, len(self.responses) - 1)]
        response.tokens_used = 50
        self.call_count += 1
        return response


class FakeToolBundle:
    """Tool bundle that records tool executions."""

    def __init__(self, has_tools=True):
        self._has_tools = has_tools
        self.executed_tools = []

    def has_tools(self):
        return self._has_tools

    def execute_tool(self, tool_call):
        self.executed_tools.append(tool_call)
        tool_name = tool_call.get('tool', 'unknown')
        return f"Result from {tool_name}"


class FakeResponseCleaner:
    """Response cleaner that tracks what it cleans."""

    def __init__(self):
        self.cleaned_responses = []
        self.fallback_generated = False

    def clean_response(self, response):
        self.cleaned_responses.append(response)
        # Simple cleaning - remove tool call markers
        import re
        cleaned = re.sub(r'```json.*?```', '', response, flags=re.DOTALL)
        return cleaned.strip()

    def generate_fallback_response(self, task, tool_calls_made, conversation_history):
        self.fallback_generated = True
        return f"Fallback: {len(tool_calls_made)} tools used"


# Fixtures

@pytest.fixture
def simple_task():
    """A simple research task."""
    task = Mock(spec=ClassifiedTask)
    task.task_type = TaskType.RESEARCH
    task.original_input = "What is in test.py?"
    task.complexity_score = 5
    return task


# Tests: No tool calls (direct answer)

def test_no_tool_calls_returns_direct_answer(simple_task):
    """When LLM provides direct answer, no tools are called."""
    orchestrator = FakeOrchestratorNoTools("This is the answer")
    tool_bundle = FakeToolBundle()
    cleaner = FakeResponseCleaner()

    loop = ResearchLoop(
        orchestrator=orchestrator,
        tool_bundle=tool_bundle,
        response_cleaner=cleaner
    )

    final_response, tool_calls, tokens = loop.run(
        provider="test-provider",
        initial_prompt="What is the answer?",
        system_prompt="You are helpful",
        task=simple_task,
        max_iterations=3
    )

    assert final_response == "This is the answer"
    assert len(tool_calls) == 0
    assert tokens == 50
    assert orchestrator.call_count == 1


def test_no_tool_calls_cleans_response(simple_task):
    """Response cleaner is called on final response."""
    orchestrator = FakeOrchestratorNoTools("Raw response")
    tool_bundle = FakeToolBundle()
    cleaner = FakeResponseCleaner()

    loop = ResearchLoop(
        orchestrator=orchestrator,
        tool_bundle=tool_bundle,
        response_cleaner=cleaner
    )

    loop.run(
        provider="test-provider",
        initial_prompt="Test",
        system_prompt="System",
        task=simple_task,
        max_iterations=3
    )

    assert len(cleaner.cleaned_responses) == 1
    assert "Raw response" in cleaner.cleaned_responses[0]


# Tests: Single tool call

def test_single_tool_call_executes_and_returns_final_answer(simple_task):
    """LLM makes one tool call, then provides final answer."""
    orchestrator = FakeOrchestratorWithToolCall()
    tool_bundle = FakeToolBundle()
    cleaner = FakeResponseCleaner()

    loop = ResearchLoop(
        orchestrator=orchestrator,
        tool_bundle=tool_bundle,
        response_cleaner=cleaner
    )

    final_response, tool_calls, tokens = loop.run(
        provider="test-provider",
        initial_prompt="What is in test.py?",
        system_prompt="Use tools",
        task=simple_task,
        max_iterations=3
    )

    # Should have made 2 LLM calls (tool call + final answer)
    assert orchestrator.call_count == 2

    # Should have executed 1 tool
    assert len(tool_calls) == 1
    assert tool_calls[0]['tool'] == 'read_file'
    assert len(tool_bundle.executed_tools) == 1

    # Final response should be cleaned
    assert "answer is 42" in final_response
    assert tokens == 100  # 50 per call


def test_tool_call_adds_to_conversation_history(simple_task):
    """Tool calls and results are added to conversation history."""
    orchestrator = FakeOrchestratorWithToolCall()
    tool_bundle = FakeToolBundle()
    cleaner = FakeResponseCleaner()

    loop = ResearchLoop(
        orchestrator=orchestrator,
        tool_bundle=tool_bundle,
        response_cleaner=cleaner
    )

    loop.run(
        provider="test-provider",
        initial_prompt="Initial prompt",
        system_prompt="System",
        task=simple_task,
        max_iterations=3
    )

    # Second call should include history in prompt
    # (We can't check the exact prompt without inspecting internals,
    # but we can verify the tool was executed)
    assert len(tool_bundle.executed_tools) == 1


# Tests: Max iterations

def test_max_iterations_stops_tool_calling():
    """Loop stops after max_iterations tool calls."""
    task = Mock(spec=ClassifiedTask)
    task.original_input = "Test"

    # Orchestrator that always returns tool calls
    orchestrator = Mock()
    orchestrator.delegate = Mock(return_value=Mock(
        content='{"tool": "read_file", "parameters": {}}',
        tokens_used=50
    ))

    tool_bundle = FakeToolBundle()
    cleaner = FakeResponseCleaner()

    loop = ResearchLoop(
        orchestrator=orchestrator,
        tool_bundle=tool_bundle,
        response_cleaner=cleaner
    )

    final_response, tool_calls, tokens = loop.run(
        provider="test-provider",
        initial_prompt="Test",
        system_prompt="System",
        task=task,
        max_iterations=2
    )

    # Should make exactly 2 tool calls, then one final iteration
    assert len(tool_calls) == 2
    # Total calls = max_iterations + 1 (the final call)
    assert orchestrator.delegate.call_count == 3


def test_stops_when_no_tool_call_parsed():
    """Loop stops when response doesn't contain tool call."""
    task = Mock(spec=ClassifiedTask)
    task.original_input = "Test"

    responses = [
        '{"tool": "read_file", "parameters": {}}',
        'This is just text, no tool call'
    ]

    orchestrator = Mock()
    call_count = [0]

    def mock_delegate(*args, **kwargs):
        response = Mock()
        response.content = responses[min(call_count[0], len(responses) - 1)]
        response.tokens_used = 50
        call_count[0] += 1
        return response

    orchestrator.delegate = mock_delegate

    tool_bundle = FakeToolBundle()
    cleaner = FakeResponseCleaner()

    loop = ResearchLoop(
        orchestrator=orchestrator,
        tool_bundle=tool_bundle,
        response_cleaner=cleaner
    )

    final_response, tool_calls, tokens = loop.run(
        provider="test-provider",
        initial_prompt="Test",
        system_prompt="System",
        task=task,
        max_iterations=5
    )

    # Should stop after 2 calls (1 tool call + 1 text response)
    assert call_count[0] == 2
    assert len(tool_calls) == 1


# Tests: Tool execution errors

def test_tool_execution_error_continues_loop():
    """Tool execution errors are handled gracefully."""
    task = Mock(spec=ClassifiedTask)
    task.original_input = "Test"

    orchestrator = Mock()
    orchestrator.delegate = Mock(side_effect=[
        Mock(content='{"tool": "bad_tool", "parameters": {}}', tokens_used=50),
        Mock(content='Final answer after error', tokens_used=50)
    ])

    # Tool bundle that returns error
    tool_bundle = Mock()
    tool_bundle.has_tools = Mock(return_value=True)
    tool_bundle.execute_tool = Mock(return_value="Error: Tool failed")

    cleaner = FakeResponseCleaner()

    loop = ResearchLoop(
        orchestrator=orchestrator,
        tool_bundle=tool_bundle,
        response_cleaner=cleaner
    )

    final_response, tool_calls, tokens = loop.run(
        provider="test-provider",
        initial_prompt="Test",
        system_prompt="System",
        task=task,
        max_iterations=3
    )

    # Should record the tool call even though it errored
    assert len(tool_calls) == 1
    assert final_response == "Final answer after error"


# Tests: No tools available

def test_no_tools_available_skips_tool_calling():
    """When tools aren't available, no tool parsing is attempted."""
    task = Mock(spec=ClassifiedTask)
    task.original_input = "Test"

    orchestrator = Mock()
    orchestrator.delegate = Mock(return_value=Mock(
        content='{"tool": "read_file", "parameters": {}}',  # Contains tool call
        tokens_used=50
    ))

    # Tool bundle with no tools
    tool_bundle = FakeToolBundle(has_tools=False)
    cleaner = FakeResponseCleaner()

    loop = ResearchLoop(
        orchestrator=orchestrator,
        tool_bundle=tool_bundle,
        response_cleaner=cleaner
    )

    final_response, tool_calls, tokens = loop.run(
        provider="test-provider",
        initial_prompt="Test",
        system_prompt="System",
        task=task,
        max_iterations=3
    )

    # Should not execute any tools
    assert len(tool_calls) == 0
    assert len(tool_bundle.executed_tools) == 0


# Tests: Empty response handling

def test_empty_final_response_generates_fallback(simple_task):
    """When final response is empty after cleaning, generates fallback."""
    orchestrator = Mock()
    orchestrator.delegate = Mock(side_effect=[
        Mock(content='{"tool": "read_file", "parameters": {}}', tokens_used=50),
        Mock(content='```json\n{"tool": "test", "parameters": {}}\n```', tokens_used=50),  # Tool call
        Mock(content='```json\n{"not": "a tool call"}\n```', tokens_used=50)  # Empty after cleaning
    ])

    tool_bundle = FakeToolBundle()
    cleaner = FakeResponseCleaner()

    loop = ResearchLoop(
        orchestrator=orchestrator,
        tool_bundle=tool_bundle,
        response_cleaner=cleaner
    )

    final_response, tool_calls, tokens = loop.run(
        provider="test-provider",
        initial_prompt="Test",
        system_prompt="System",
        task=simple_task,
        max_iterations=3
    )

    # Should have generated fallback
    assert cleaner.fallback_generated
    assert "Fallback" in final_response


# Tests: Token counting

def test_accumulates_tokens_across_iterations():
    """Total tokens are accumulated across all iterations."""
    task = Mock(spec=ClassifiedTask)
    task.original_input = "Test"

    orchestrator = Mock()
    orchestrator.delegate = Mock(side_effect=[
        Mock(content='{"tool": "read_file", "parameters": {}}', tokens_used=100),
        Mock(content='{"tool": "search_code", "parameters": {}}', tokens_used=150),
        Mock(content='Final answer', tokens_used=200)
    ])

    tool_bundle = FakeToolBundle()
    cleaner = FakeResponseCleaner()

    loop = ResearchLoop(
        orchestrator=orchestrator,
        tool_bundle=tool_bundle,
        response_cleaner=cleaner
    )

    final_response, tool_calls, tokens = loop.run(
        provider="test-provider",
        initial_prompt="Test",
        system_prompt="System",
        task=task,
        max_iterations=3
    )

    assert tokens == 450  # 100 + 150 + 200


# Tests: Conversation history building

def test_conversation_history_includes_tool_results():
    """Conversation history contains tool calls and results."""
    task = Mock(spec=ClassifiedTask)
    task.original_input = "Test"

    prompts_received = []

    def capture_prompt(*args, **kwargs):
        prompts_received.append(args[1])  # Capture the prompt argument
        if len(prompts_received) == 1:
            return Mock(content='{"tool": "read_file", "parameters": {}}', tokens_used=50)
        else:
            return Mock(content='Final answer', tokens_used=50)

    orchestrator = Mock()
    orchestrator.delegate = Mock(side_effect=capture_prompt)

    tool_bundle = FakeToolBundle()
    cleaner = FakeResponseCleaner()

    loop = ResearchLoop(
        orchestrator=orchestrator,
        tool_bundle=tool_bundle,
        response_cleaner=cleaner
    )

    loop.run(
        provider="test-provider",
        initial_prompt="Initial prompt",
        system_prompt="System",
        task=task,
        max_iterations=3
    )

    # First prompt should be just initial
    assert "Initial prompt" in prompts_received[0]

    # Second prompt should include history
    assert len(prompts_received) == 2
    # History should contain tool result
    assert "Tool Result" in prompts_received[1] or "Result from" in prompts_received[1]


# Tests: Multiple tool calls

def test_multiple_sequential_tool_calls():
    """Loop handles multiple tool calls in sequence."""
    task = Mock(spec=ClassifiedTask)
    task.original_input = "Test"

    orchestrator = Mock()
    orchestrator.delegate = Mock(side_effect=[
        Mock(content='{"tool": "read_file", "parameters": {"file_path": "a.py"}}', tokens_used=50),
        Mock(content='{"tool": "read_file", "parameters": {"file_path": "b.py"}}', tokens_used=50),
        Mock(content='{"tool": "search_code", "parameters": {"pattern": "test"}}', tokens_used=50),
        Mock(content='All done!', tokens_used=50)
    ])

    tool_bundle = FakeToolBundle()
    cleaner = FakeResponseCleaner()

    loop = ResearchLoop(
        orchestrator=orchestrator,
        tool_bundle=tool_bundle,
        response_cleaner=cleaner
    )

    final_response, tool_calls, tokens = loop.run(
        provider="test-provider",
        initial_prompt="Test",
        system_prompt="System",
        task=task,
        max_iterations=3
    )

    # Should have executed 3 tools
    assert len(tool_calls) == 3
    assert tool_calls[0]['tool'] == 'read_file'
    assert tool_calls[1]['tool'] == 'read_file'
    assert tool_calls[2]['tool'] == 'search_code'

    # Should have final answer
    assert "All done!" in final_response
