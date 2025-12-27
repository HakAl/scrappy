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
from scrappy.task_router.strategies.research_loop import ResearchLoop
from scrappy.task_router.classifier import ClassifiedTask, TaskType


# Test Doubles

class FakeOrchestratorNoTools:
    """Orchestrator that returns responses without tool calls."""

    def __init__(self, response_content="This is a direct answer", tokens=50, input_tokens=100):
        self.response_content = response_content
        self.tokens = tokens
        self.input_tokens = input_tokens
        self.call_count = 0
        self.last_messages = None
        self.last_prompt = None
        self.last_system_prompt = None

    def delegate(self, provider, prompt="", system_prompt=None, messages=None, **kwargs):
        self.call_count += 1
        self.last_prompt = prompt
        self.last_system_prompt = system_prompt
        self.last_messages = messages

        response = Mock()
        response.content = self.response_content
        response.tokens_used = self.tokens
        response.input_tokens = self.input_tokens
        return response


class FakeOrchestratorWithToolCall:
    """Orchestrator that returns tool calls first, then final answer."""

    def __init__(self):
        self.call_count = 0
        self.last_messages = None
        self.responses = [
            '```json\n{"tool": "read_file", "parameters": {"file_path": "test.py"}}\n```',
            'Based on the file, the answer is 42.'
        ]

    def delegate(self, provider, prompt="", system_prompt=None, messages=None, **kwargs):
        self.last_messages = messages
        response = Mock()
        response.content = self.responses[min(self.call_count, len(self.responses) - 1)]
        response.tokens_used = 50
        response.input_tokens = 100
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
        tokens_used=50,
        input_tokens=100
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
        response.input_tokens = 100
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
        Mock(content='{"tool": "bad_tool", "parameters": {}}', tokens_used=50, input_tokens=100),
        Mock(content='Final answer after error', tokens_used=50, input_tokens=100)
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
        tokens_used=50,
        input_tokens=100
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
        Mock(content='{"tool": "read_file", "parameters": {}}', tokens_used=50, input_tokens=100),
        Mock(content='```json\n{"tool": "test", "parameters": {}}\n```', tokens_used=50, input_tokens=100),  # Tool call
        Mock(content='```json\n{"not": "a tool call"}\n```', tokens_used=50, input_tokens=100)  # Empty after cleaning
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
        Mock(content='{"tool": "read_file", "parameters": {}}', tokens_used=100, input_tokens=50),
        Mock(content='{"tool": "search_code", "parameters": {}}', tokens_used=150, input_tokens=50),
        Mock(content='Final answer', tokens_used=200, input_tokens=50)
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
    """Conversation history contains tool calls and results in structured messages."""
    task = Mock(spec=ClassifiedTask)
    task.original_input = "Test"

    messages_received = []

    def capture_messages(*args, **kwargs):
        messages_received.append(kwargs.get('messages', []))
        response = Mock()
        response.input_tokens = 100
        if len(messages_received) == 1:
            response.content = '{"tool": "read_file", "parameters": {}}'
            response.tokens_used = 50
        else:
            response.content = 'Final answer'
            response.tokens_used = 50
        return response

    orchestrator = Mock()
    orchestrator.delegate = Mock(side_effect=capture_messages)

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

    # First call should have system + user messages
    first_messages = messages_received[0]
    assert first_messages[0]['role'] == 'system'
    assert first_messages[1]['role'] == 'user'
    assert 'Initial prompt' in first_messages[1]['content']

    # Second call should include tool history
    second_messages = messages_received[1]
    assert len(second_messages) > 2  # Has history
    # Should have assistant message with tool_calls
    tool_call_msg = next((m for m in second_messages if m.get('role') == 'assistant' and m.get('tool_calls')), None)
    assert tool_call_msg is not None
    # Should have tool result message
    tool_result_msg = next((m for m in second_messages if m.get('role') == 'tool'), None)
    assert tool_result_msg is not None


# Tests: Multiple tool calls

def test_multiple_sequential_tool_calls():
    """Loop handles multiple tool calls in sequence."""
    task = Mock(spec=ClassifiedTask)
    task.original_input = "Test"

    orchestrator = Mock()
    orchestrator.delegate = Mock(side_effect=[
        Mock(content='{"tool": "read_file", "parameters": {"file_path": "a.py"}}', tokens_used=50, input_tokens=100),
        Mock(content='{"tool": "read_file", "parameters": {"file_path": "b.py"}}', tokens_used=50, input_tokens=100),
        Mock(content='{"tool": "search_code", "parameters": {"pattern": "test"}}', tokens_used=50, input_tokens=100),
        Mock(content='All done!', tokens_used=50, input_tokens=100)
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


# Tests: Empty response edge cases (Issue: NO_OUTPUT.md)

def test_json_only_response_without_tools_available_returns_nonempty(simple_task):
    """
    ISSUE: When LLM outputs ONLY tool-call JSON but no tools are available,
    the response becomes empty after cleaning. Fallback doesn't trigger because
    tool_calls_made is empty.

    EXPECTED: Should return a user-friendly message, not empty string.
    """
    from scrappy.task_router.strategies.response_cleaner import ResponseCleaner

    orchestrator = Mock()
    # LLM outputs only tool-call JSON (common with llama3.1-8b)
    orchestrator.delegate = Mock(return_value=Mock(
        content='{"tool": "web_search", "parameters": {"query": "test"}}',
        tokens_used=50,
        input_tokens=100
    ))

    # No tools available - tool call cannot be executed
    tool_bundle = FakeToolBundle(has_tools=False)
    cleaner = ResponseCleaner()  # Use real cleaner to demonstrate the issue

    loop = ResearchLoop(
        orchestrator=orchestrator,
        tool_bundle=tool_bundle,
        response_cleaner=cleaner
    )

    final_response, tool_calls, tokens = loop.run(
        provider="test-provider",
        initial_prompt="How do I add RAG to my codebase?",
        system_prompt="You are a helpful assistant with tool access.",
        task=simple_task,
        max_iterations=3
    )

    # CURRENT BEHAVIOR: final_response is "" (empty)
    # EXPECTED BEHAVIOR: final_response should be non-empty with helpful message
    assert final_response != "", "Response should not be empty when LLM outputs only tool JSON"
    assert len(tool_calls) == 0


def test_rejected_tool_due_to_allowed_list_returns_nonempty(simple_task):
    """
    ISSUE: When LLM calls a tool that's not in allowed_tools list,
    the tool_call is set to None, response is cleaned to empty,
    and fallback doesn't trigger because tool_calls_made is empty.

    EXPECTED: Should return a user-friendly message, not empty string.
    """
    from scrappy.task_router.strategies.response_cleaner import ResponseCleaner

    orchestrator = Mock()
    # LLM tries to use read_file tool
    orchestrator.delegate = Mock(return_value=Mock(
        content='{"tool": "read_file", "parameters": {"file_path": "src/main.py"}}',
        tokens_used=50,
        input_tokens=100
    ))

    tool_bundle = FakeToolBundle(has_tools=True)
    cleaner = ResponseCleaner()

    loop = ResearchLoop(
        orchestrator=orchestrator,
        tool_bundle=tool_bundle,
        response_cleaner=cleaner
    )

    # Only allow web tools - read_file is NOT in this list
    # This simulates GENERAL research subtype which restricts to web-only tools
    final_response, tool_calls, tokens = loop.run(
        provider="test-provider",
        initial_prompt="What is in src/main.py?",
        system_prompt="You have access to tools.",
        task=simple_task,
        max_iterations=3,
        allowed_tools=["web_search", "web_fetch"]
    )

    # CURRENT BEHAVIOR: final_response is "" (empty)
    # EXPECTED BEHAVIOR: final_response should be non-empty
    assert final_response != "", "Response should not be empty when tool is rejected"
    assert len(tool_calls) == 0


def test_malformed_tool_json_returns_nonempty(simple_task):
    """
    ISSUE: When LLM outputs JSON that looks like a tool call but is malformed,
    parsing fails, and response becomes empty after cleaning.

    EXPECTED: Should return a user-friendly message, not empty string.
    """
    from scrappy.task_router.strategies.response_cleaner import ResponseCleaner

    orchestrator = Mock()
    # LLM outputs malformed tool call (missing closing brace)
    orchestrator.delegate = Mock(return_value=Mock(
        content='{"tool": "web_search", "parameters": {"query": "test"}',  # Missing }
        tokens_used=50,
        input_tokens=100
    ))

    tool_bundle = FakeToolBundle(has_tools=True)
    cleaner = ResponseCleaner()

    loop = ResearchLoop(
        orchestrator=orchestrator,
        tool_bundle=tool_bundle,
        response_cleaner=cleaner
    )

    final_response, tool_calls, tokens = loop.run(
        provider="test-provider",
        initial_prompt="Search for something",
        system_prompt="You have tools.",
        task=simple_task,
        max_iterations=3
    )

    # Response cleaner will strip lines starting with {"tool"
    # Even though parsing failed, user should get SOMETHING back
    assert final_response != "", "Response should not be empty when tool JSON is malformed"


# Tests: Native Tool Protocol Compliance

def test_uses_native_tool_protocol():
    """Messages use native tool protocol: assistant with tool_calls, role: 'tool' for results."""
    task = Mock(spec=ClassifiedTask)
    task.original_input = "Test"

    messages_received = []

    def capture_messages(*args, **kwargs):
        messages_received.append(kwargs.get('messages', []))
        response = Mock()
        response.input_tokens = 100
        if len(messages_received) == 1:
            response.content = '{"tool": "read_file", "parameters": {"path": "test.py"}}'
            response.tokens_used = 50
        else:
            response.content = 'Done'
            response.tokens_used = 50
        return response

    orchestrator = Mock()
    orchestrator.delegate = Mock(side_effect=capture_messages)

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
        task=task,
        max_iterations=3
    )

    # Second call should have tool protocol messages
    second_messages = messages_received[1]

    # Find assistant message with tool_calls
    assistant_msg = next((m for m in second_messages if m.get('role') == 'assistant'), None)
    assert assistant_msg is not None
    assert 'tool_calls' in assistant_msg
    assert assistant_msg['tool_calls'][0]['type'] == 'function'
    assert assistant_msg['tool_calls'][0]['function']['name'] == 'read_file'

    # Find tool result message
    tool_msg = next((m for m in second_messages if m.get('role') == 'tool'), None)
    assert tool_msg is not None
    assert 'tool_call_id' in tool_msg


def test_tool_call_ids_match():
    """Tool call ID in assistant message matches ID in tool result message."""
    task = Mock(spec=ClassifiedTask)
    task.original_input = "Test"

    messages_received = []

    def capture_messages(*args, **kwargs):
        messages_received.append(kwargs.get('messages', []))
        response = Mock()
        response.input_tokens = 100
        if len(messages_received) == 1:
            response.content = '{"tool": "read_file", "parameters": {}}'
            response.tokens_used = 50
        else:
            response.content = 'Done'
            response.tokens_used = 50
        return response

    orchestrator = Mock()
    orchestrator.delegate = Mock(side_effect=capture_messages)

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
        task=task,
        max_iterations=3
    )

    second_messages = messages_received[1]

    assistant_msg = next((m for m in second_messages if m.get('role') == 'assistant' and m.get('tool_calls')), None)
    tool_msg = next((m for m in second_messages if m.get('role') == 'tool'), None)

    assert assistant_msg is not None
    assert tool_msg is not None
    # IDs must match
    assert assistant_msg['tool_calls'][0]['id'] == tool_msg['tool_call_id']


def test_handles_null_content():
    """Handles response.content being None (some models skip straight to tool calls)."""
    task = Mock(spec=ClassifiedTask)
    task.original_input = "Test"

    orchestrator = Mock()
    response1 = Mock()
    response1.content = None  # Null content
    response1.tokens_used = 50
    response1.input_tokens = 100

    response2 = Mock()
    response2.content = 'Final answer'
    response2.tokens_used = 50
    response2.input_tokens = 100

    orchestrator.delegate = Mock(side_effect=[response1, response2])

    tool_bundle = FakeToolBundle(has_tools=False)  # No tools, so null content triggers direct response
    cleaner = FakeResponseCleaner()

    loop = ResearchLoop(
        orchestrator=orchestrator,
        tool_bundle=tool_bundle,
        response_cleaner=cleaner
    )

    # Should not raise NoneType error
    final_response, tool_calls, tokens = loop.run(
        provider="test-provider",
        initial_prompt="Test",
        system_prompt="System",
        task=task,
        max_iterations=3
    )

    # Should handle gracefully - returns fallback message for null/empty content
    assert final_response != ""  # Should have fallback message, not empty
    assert "unable to generate" in final_response.lower() or "rephras" in final_response.lower()


# Tests: Context Compaction (Observation Masking)

def test_masks_old_tool_results():
    """Old tool results are masked to '[X chars returned]' after FULL_CONTEXT_WINDOW iterations."""

    task = Mock(spec=ClassifiedTask)
    task.original_input = "Test"

    messages_received = []

    def capture_messages(*args, **kwargs):
        messages_received.append(kwargs.get('messages', []))
        response = Mock()
        response.input_tokens = 100
        response.tokens_used = 50
        # Return tool calls for first 4 iterations, then final answer
        if len(messages_received) < 5:
            response.content = f'{{"tool": "read_file", "parameters": {{"n": {len(messages_received)}}}}}'
        else:
            response.content = 'Final answer'
        return response

    orchestrator = Mock()
    orchestrator.delegate = Mock(side_effect=capture_messages)

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
        task=task,
        max_iterations=5
    )

    # After 4 tool calls, 5th call should have masked results for iterations 0, 1
    # (keeping only last 2 iterations full)
    last_messages = messages_received[-1]
    tool_results = [m for m in last_messages if m.get('role') == 'tool']

    # First 2 results should be masked (iteration 0, 1)
    assert '[' in tool_results[0]['content'] and 'chars returned]' in tool_results[0]['content']
    assert '[' in tool_results[1]['content'] and 'chars returned]' in tool_results[1]['content']

    # Last 2 results should be full (iteration 2, 3)
    assert 'Result from read_file' in tool_results[2]['content']
    assert 'Result from read_file' in tool_results[3]['content']


def test_keeps_recent_results_full():
    """Last FULL_CONTEXT_WINDOW iterations keep full tool results."""
    task = Mock(spec=ClassifiedTask)
    task.original_input = "Test"

    messages_received = []

    def capture_messages(*args, **kwargs):
        messages_received.append(kwargs.get('messages', []))
        response = Mock()
        response.input_tokens = 100
        response.tokens_used = 50
        if len(messages_received) < 3:
            response.content = '{"tool": "read_file", "parameters": {}}'
        else:
            response.content = 'Final'
        return response

    orchestrator = Mock()
    orchestrator.delegate = Mock(side_effect=capture_messages)

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
        task=task,
        max_iterations=3
    )

    # With only 2 tool calls and FULL_CONTEXT_WINDOW=2, both should be full
    last_messages = messages_received[-1]
    tool_results = [m for m in last_messages if m.get('role') == 'tool']

    for result in tool_results:
        # All should be full (not masked)
        assert 'chars returned]' not in result['content']


def test_preserves_reasoning_trace():
    """Assistant content (reasoning) is never masked, only tool results."""
    task = Mock(spec=ClassifiedTask)
    task.original_input = "Test"

    messages_received = []

    def capture_messages(*args, **kwargs):
        messages_received.append(kwargs.get('messages', []))
        response = Mock()
        response.input_tokens = 100
        response.tokens_used = 50
        if len(messages_received) < 5:
            response.content = f'Thinking about iteration {len(messages_received)}... {{"tool": "read_file", "parameters": {{}}}}'
        else:
            response.content = 'Final'
        return response

    orchestrator = Mock()
    orchestrator.delegate = Mock(side_effect=capture_messages)

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
        task=task,
        max_iterations=5
    )

    last_messages = messages_received[-1]
    assistant_msgs = [m for m in last_messages if m.get('role') == 'assistant']

    # All assistant messages should have full reasoning content
    for msg in assistant_msgs:
        assert 'Thinking about iteration' in msg['content']
        # Should NOT be masked
        assert 'chars returned]' not in msg['content']


def test_tracks_input_tokens():
    """Token tracking uses input_tokens from API response."""
    task = Mock(spec=ClassifiedTask)
    task.original_input = "Test"

    orchestrator = Mock()
    response = Mock()
    response.content = 'Answer'
    response.tokens_used = 100
    response.input_tokens = 500  # Specific input token count
    orchestrator.delegate = Mock(return_value=response)

    tool_bundle = FakeToolBundle(has_tools=False)
    cleaner = FakeResponseCleaner()

    loop = ResearchLoop(
        orchestrator=orchestrator,
        tool_bundle=tool_bundle,
        response_cleaner=cleaner
    )

    # The loop should track input_tokens internally
    # We can verify by checking that it doesn't error
    final_response, tool_calls, tokens = loop.run(
        provider="test-provider",
        initial_prompt="Test",
        system_prompt="System",
        task=task,
        max_iterations=3
    )

    assert tokens == 100  # Total tokens used


def test_aggressive_compact_at_threshold():
    """When input_tokens exceeds threshold, window shrinks to 1."""
    task = Mock(spec=ClassifiedTask)
    task.original_input = "Test"

    messages_received = []
    call_count = [0]

    def capture_messages(*args, **kwargs):
        messages_received.append(kwargs.get('messages', []))
        response = Mock()
        call_count[0] += 1

        if call_count[0] < 4:
            response.content = '{"tool": "read_file", "parameters": {}}'
            # Simulate high token usage to trigger aggressive compaction
            response.input_tokens = 60000  # Above 80% of 65536
        else:
            response.content = 'Final'
            response.input_tokens = 100

        response.tokens_used = 50
        return response

    orchestrator = Mock()
    orchestrator.delegate = Mock(side_effect=capture_messages)

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
        task=task,
        max_iterations=4
    )

    # After hitting threshold, later calls should have more masked results
    # (window shrinks from 2 to 1)
    if len(messages_received) >= 4:
        last_messages = messages_received[-1]
        tool_results = [m for m in last_messages if m.get('role') == 'tool']
        # With window=1, all but last result should be masked
        if len(tool_results) >= 2:
            # At least first result should be masked
            assert 'chars returned]' in tool_results[0]['content']
