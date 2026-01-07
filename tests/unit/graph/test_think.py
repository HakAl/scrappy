"""
Unit tests for the Think node.

Tests LLM reasoning step including:
- Basic completion flow
- Tool call extraction
- Context sanitization
- Streaming support
- Error handling
"""

import pytest
from typing import Any, Optional

from scrappy.graph.state import AgentState, Message
from scrappy.graph.nodes.think import (
    think_node,
    think_node_streaming,
    build_system_prompt,
    sanitize_context,
    estimate_tokens,
    estimate_message_tokens,
    accumulate_tool_calls,
    fragments_to_tool_calls,
    mask_old_tool_results,
    FULL_CONTEXT_WINDOW,
)
from scrappy.orchestrator.litellm_service import NotConfiguredError
from scrappy.orchestrator.types import StreamChunk, ToolCallFragment


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


class MockToolCall:
    """Mock tool call object with object attributes."""

    def __init__(self, id: str, name: str, arguments: dict):
        self.id = id
        self.name = name
        self.arguments = arguments


class MockLLMService:
    """Mock LLM service for testing think node."""

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


class MockStreamingLLMService:
    """Mock streaming LLM service for testing."""

    def __init__(
        self,
        chunks: Optional[list[StreamChunk]] = None,
        exception: Optional[Exception] = None,
    ):
        self.chunks = chunks or []
        self.exception = exception
        self.calls: list[dict] = []

    async def stream_completion(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any,
    ):
        """Yield mock chunks."""
        self.calls.append({
            "model": model,
            "messages": messages,
            **kwargs,
        })

        if self.exception:
            raise self.exception

        for chunk in self.chunks:
            yield chunk


class MockToolAdapter:
    """Mock tool adapter for testing."""

    def __init__(
        self,
        tool_names: Optional[list[str]] = None,
        tool_schemas: Optional[list[dict]] = None,
    ):
        self._tool_names = tool_names or []
        self._tool_schemas = tool_schemas or []

    def get_tool_names(self) -> list[str]:
        return self._tool_names

    def get_tool_schemas(self) -> list[dict]:
        return self._tool_schemas


def create_test_state(
    input_text: str = "Write a hello world function",
    working_dir: str = "/tmp/test",
    messages: Optional[list[Message]] = None,
    iteration: int = 0,
    current_tier: str = "fast",
    last_error: Optional[str] = None,
    error_count: int = 0,
    files_changed: Optional[list[str]] = None,
) -> AgentState:
    """Create a test AgentState."""
    return AgentState(
        input=input_text,
        original_task=input_text,
        working_dir=working_dir,
        messages=messages or [],
        iteration=iteration,
        current_tier=current_tier,  # type: ignore[arg-type]
        last_error=last_error,
        error_count=error_count,
        files_changed=files_changed or [],
    )


# =============================================================================
# Token Estimation Tests
# =============================================================================


class TestTokenEstimation:
    """Tests for token estimation functions."""

    def test_estimate_tokens_empty_string(self):
        """Empty string should return 0 tokens."""
        result = estimate_tokens("")
        assert result == 0

    def test_estimate_tokens_short_text(self):
        """Short text should return reasonable estimate."""
        result = estimate_tokens("Hello, world!")
        # 13 chars * 0.25 = ~3 tokens
        assert result >= 1
        assert result <= 10

    def test_estimate_tokens_longer_text(self):
        """Longer text should scale proportionally."""
        short = estimate_tokens("Hi")
        long = estimate_tokens("This is a much longer piece of text")
        assert long > short

    def test_estimate_message_tokens_simple(self):
        """Simple message should include role overhead."""
        msg = {"role": "user", "content": "Hello"}
        result = estimate_message_tokens(msg)
        # Should be > 0 (role overhead + content)
        assert result > 0

    def test_estimate_message_tokens_with_tool_calls(self):
        """Message with tool calls should include their overhead."""
        msg = {
            "role": "assistant",
            "content": "Using tool",
            "tool_calls": [
                {"name": "read_file", "arguments": '{"path": "/test"}'}
            ],
        }
        result = estimate_message_tokens(msg)

        # Should be more than message without tool calls
        simple_msg = {"role": "assistant", "content": "Using tool"}
        simple_result = estimate_message_tokens(simple_msg)
        assert result > simple_result


# =============================================================================
# Context Sanitization Tests
# =============================================================================


class TestContextSanitization:
    """Tests for context trimming/sanitization."""

    def test_sanitize_empty_messages(self):
        """Empty messages should return empty list."""
        result = sanitize_context([])
        assert result == []

    def test_sanitize_within_limit(self):
        """Messages within limit should be unchanged."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        result = sanitize_context(messages, max_tokens=10000)
        assert result == messages

    def test_sanitize_trims_middle_messages(self):
        """Long conversation should trim middle messages."""
        # Create a long conversation
        messages = [{"role": "system", "content": "System prompt."}]
        for i in range(50):
            messages.append({"role": "user", "content": f"Message {i} " * 100})
            messages.append({"role": "assistant", "content": f"Response {i} " * 100})

        # Use a small token limit to force trimming
        result = sanitize_context(messages, max_tokens=1000)

        # Should have fewer messages than original
        assert len(result) < len(messages)

        # Should keep system message
        assert result[0]["role"] == "system"

    def test_sanitize_keeps_recent_messages(self):
        """Should prioritize keeping recent messages."""
        messages = [
            {"role": "system", "content": "System."},
            {"role": "user", "content": "Old message " * 100},
            {"role": "assistant", "content": "Old response " * 100},
            {"role": "user", "content": "Recent message"},
            {"role": "assistant", "content": "Recent response"},
        ]

        result = sanitize_context(messages, max_tokens=500)

        # Last messages should be preserved
        assert any("Recent" in str(m.get("content", "")) for m in result)

    def test_sanitize_minimum_messages(self):
        """Should keep at least MIN_MESSAGES_TO_KEEP messages."""
        messages = [
            {"role": "user", "content": "Very long " * 1000},
            {"role": "assistant", "content": "Also very long " * 1000},
        ]

        result = sanitize_context(messages, max_tokens=100)

        # Should have at least 1 message (can't drop everything)
        assert len(result) >= 1


# =============================================================================
# Observation Masking Tests
# =============================================================================


class TestObservationMasking:
    """Tests for tool result masking to save context."""

    def test_mask_empty_messages(self):
        """Empty messages should return empty list."""
        result = mask_old_tool_results([])
        assert result == []

    def test_mask_no_tool_messages(self):
        """Messages without tool results should be unchanged."""
        messages = [
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = mask_old_tool_results(messages)
        assert result == messages

    def test_mask_fewer_than_window(self):
        """Fewer tool results than window should not be masked."""
        messages = [
            {"role": "user", "content": "Run a command"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "type": "function", "function": {"name": "run", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "1", "content": "Command output here"},
        ]
        result = mask_old_tool_results(messages, keep_full=2)
        # Only 1 tool result, window is 2, so no masking
        assert result[2]["content"] == "Command output here"

    def test_mask_old_tool_results_preserves_recent(self):
        """Old tool results should be masked, recent ones preserved."""
        messages = [
            {"role": "user", "content": "Do tasks"},
            # First tool call/result (will be masked)
            {"role": "assistant", "content": "Calling tool 1"},
            {"role": "tool", "tool_call_id": "1", "content": "Result from tool 1 with lots of data"},
            # Second tool call/result (will be masked)
            {"role": "assistant", "content": "Calling tool 2"},
            {"role": "tool", "tool_call_id": "2", "content": "Result from tool 2"},
            # Third tool call/result (recent - preserved)
            {"role": "assistant", "content": "Calling tool 3"},
            {"role": "tool", "tool_call_id": "3", "content": "Recent result 3"},
            # Fourth tool call/result (recent - preserved)
            {"role": "assistant", "content": "Calling tool 4"},
            {"role": "tool", "tool_call_id": "4", "content": "Recent result 4"},
        ]

        result = mask_old_tool_results(messages, keep_full=2)

        # First two tool results should be masked
        assert "[" in result[2]["content"] and "chars returned]" in result[2]["content"]
        assert "[" in result[4]["content"] and "chars returned]" in result[4]["content"]

        # Last two tool results should be preserved
        assert result[6]["content"] == "Recent result 3"
        assert result[8]["content"] == "Recent result 4"

    def test_mask_preserves_non_tool_messages(self):
        """Non-tool messages (user, assistant, system) should never be masked."""
        messages = [
            {"role": "system", "content": "Important system instructions"},
            {"role": "user", "content": "User input"},
            {"role": "assistant", "content": "Assistant reasoning - should not be masked"},
            {"role": "tool", "tool_call_id": "1", "content": "Old tool result"},
            {"role": "assistant", "content": "More reasoning"},
            {"role": "tool", "tool_call_id": "2", "content": "Newer tool result"},
            {"role": "assistant", "content": "Final reasoning"},
            {"role": "tool", "tool_call_id": "3", "content": "Newest tool result"},
        ]

        result = mask_old_tool_results(messages, keep_full=2)

        # All non-tool messages should be unchanged
        assert result[0]["content"] == "Important system instructions"
        assert result[1]["content"] == "User input"
        assert result[2]["content"] == "Assistant reasoning - should not be masked"
        assert result[4]["content"] == "More reasoning"
        assert result[6]["content"] == "Final reasoning"

    def test_mask_placeholder_format(self):
        """Masked content should show character count."""
        messages = [
            {"role": "tool", "tool_call_id": "1", "content": "x" * 100},  # 100 chars
            {"role": "tool", "tool_call_id": "2", "content": "y" * 50},   # 50 chars
            {"role": "tool", "tool_call_id": "3", "content": "z" * 25},   # preserved
        ]

        result = mask_old_tool_results(messages, keep_full=1)

        # First two should be masked with char counts
        assert result[0]["content"] == "[100 chars returned]"
        assert result[1]["content"] == "[50 chars returned]"
        # Last one preserved
        assert result[2]["content"] == "z" * 25

    def test_default_window_matches_constant(self):
        """Default keep_full should match FULL_CONTEXT_WINDOW constant."""
        # Create messages with more tool results than default window
        messages = []
        for i in range(5):
            messages.append({"role": "tool", "tool_call_id": str(i), "content": f"Result {i}"})

        result = mask_old_tool_results(messages)  # Use default

        # Count how many are NOT masked
        unmasked = sum(1 for m in result if "chars returned]" not in m["content"])
        assert unmasked == FULL_CONTEXT_WINDOW


# =============================================================================
# System Prompt Tests
# =============================================================================


class TestBuildSystemPrompt:
    """Tests for system prompt generation."""

    def test_includes_task(self):
        """System prompt should include the task."""
        state = create_test_state(input_text="Create a REST API")
        prompt = build_system_prompt(state, [])
        assert "Create a REST API" in prompt

    def test_includes_tool_names(self):
        """System prompt should list available tools."""
        state = create_test_state()
        tools = ["read_file", "write_file", "execute_shell"]
        prompt = build_system_prompt(state, tools)

        assert "read_file" in prompt
        assert "write_file" in prompt
        assert "execute_shell" in prompt

    def test_includes_working_dir(self):
        """System prompt should include working directory."""
        state = create_test_state(working_dir="/home/user/project")
        prompt = build_system_prompt(state, [])
        assert "/home/user/project" in prompt

    def test_includes_error_context(self):
        """System prompt should include last error if present."""
        state = create_test_state(last_error="File not found: config.py")
        prompt = build_system_prompt(state, [])
        assert "File not found: config.py" in prompt
        assert "Previous Error" in prompt

    def test_includes_files_changed(self):
        """System prompt should include files changed."""
        state = create_test_state(files_changed=["src/main.py", "tests/test_main.py"])
        prompt = build_system_prompt(state, [])
        assert "src/main.py" in prompt
        assert "tests/test_main.py" in prompt

    def test_no_tools_shows_none(self):
        """System prompt should show 'none' when no tools available."""
        state = create_test_state()
        prompt = build_system_prompt(state, [])
        assert "none" in prompt


# =============================================================================
# Tool Call Accumulation Tests
# =============================================================================


class TestToolCallAccumulation:
    """Tests for streaming tool call fragment accumulation."""

    def test_accumulate_single_complete_fragment(self):
        """Single complete fragment should accumulate correctly."""
        fragments = [
            ToolCallFragment(
                id="call_123",
                type="function",
                name="read_file",
                arguments='{"path": "/test"}',
                index=0,
            )
        ]

        result = accumulate_tool_calls(fragments)

        assert 0 in result
        assert result[0]["id"] == "call_123"
        assert result[0]["name"] == "read_file"
        assert result[0]["arguments"] == '{"path": "/test"}'

    def test_accumulate_split_fragments(self):
        """Fragments split across chunks should concatenate."""
        fragments = [
            ToolCallFragment(
                id="call_123",
                type="function",
                name="read",
                arguments='{"path":',
                index=0,
            ),
            ToolCallFragment(
                id="",
                type="function",
                name="_file",
                arguments=' "/test"}',
                index=0,
            ),
        ]

        result = accumulate_tool_calls(fragments)

        assert result[0]["name"] == "read_file"
        assert result[0]["arguments"] == '{"path": "/test"}'

    def test_accumulate_multiple_tool_calls(self):
        """Multiple tool calls should be tracked by index."""
        fragments = [
            ToolCallFragment(
                id="call_1",
                type="function",
                name="read_file",
                arguments='{"path": "/a"}',
                index=0,
            ),
            ToolCallFragment(
                id="call_2",
                type="function",
                name="write_file",
                arguments='{"path": "/b"}',
                index=1,
            ),
        ]

        result = accumulate_tool_calls(fragments)

        assert len(result) == 2
        assert result[0]["name"] == "read_file"
        assert result[1]["name"] == "write_file"

    def test_fragments_to_tool_calls_conversion(self):
        """Accumulated fragments should convert to ToolCall list."""
        accumulated = {
            0: {"id": "call_1", "name": "read_file", "arguments": '{}'},
            1: {"id": "call_2", "name": "write_file", "arguments": '{}'},
        }

        result = fragments_to_tool_calls(accumulated)

        assert len(result) == 2
        assert result[0]["id"] == "call_1"
        assert result[0]["function"]["name"] == "read_file"
        assert result[1]["id"] == "call_2"
        assert result[1]["function"]["name"] == "write_file"

    def test_fragments_skips_empty_names(self):
        """Tool calls without names should be skipped."""
        accumulated = {
            0: {"id": "call_1", "name": "", "arguments": '{}'},
            1: {"id": "call_2", "name": "valid_tool", "arguments": '{}'},
        }

        result = fragments_to_tool_calls(accumulated)

        assert len(result) == 1
        assert result[0]["function"]["name"] == "valid_tool"


# =============================================================================
# Think Node Tests
# =============================================================================


class TestThinkNode:
    """Tests for the main think_node function."""

    def test_basic_completion(self):
        """Think node should call LLM and return updated state."""
        state = create_test_state()
        llm_service = MockLLMService(
            response=MockLLMResponse(content="Here is your function...")
        )

        result = think_node(state, llm_service)

        # Should have called LLM
        assert len(llm_service.calls) == 1

        # State should be updated - includes user message + assistant response
        assert len(result.messages) == 2
        assert result.messages[0]["role"] == "user"
        assert result.messages[1]["role"] == "assistant"
        assert "Here is your function" in result.messages[1]["content"]

        # Iteration should increment
        assert result.iteration == 1

        # Should be marked done (no tool calls)
        assert result.done is True

    def test_uses_state_tier_without_tools(self):
        """Think node should use state.current_tier even without tools."""
        state = create_test_state(current_tier="chat")
        llm_service = MockLLMService()

        # No tool_adapter, uses state.current_tier
        think_node(state, llm_service, tool_adapter=None)

        assert llm_service.calls[0]["model"] == "chat"

    def test_uses_state_tier_with_tools(self):
        """Think node should use state.current_tier when tool_adapter is provided."""
        state = create_test_state(current_tier="instruct")
        llm_service = MockLLMService()
        tool_adapter = MockToolAdapter(tool_names=["test_tool"])

        # With tool_adapter = agent mode = use state.current_tier
        think_node(state, llm_service, tool_adapter=tool_adapter)

        assert llm_service.calls[0]["model"] == "instruct"

    def test_includes_conversation_history(self):
        """Think node should include previous messages."""
        prior_messages: list[Message] = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a programming language."},
        ]
        state = create_test_state(
            messages=prior_messages,
            input_text="Tell me more",
        )
        llm_service = MockLLMService()

        think_node(state, llm_service)

        # Messages should include history + system + current input
        call_messages = llm_service.calls[0]["messages"]
        assert any("What is Python?" in str(m) for m in call_messages)
        assert any("programming language" in str(m) for m in call_messages)

    def test_extracts_tool_calls_from_response(self):
        """Think node should extract tool calls from LLM response."""
        state = create_test_state()
        tool_call = MockToolCall(
            id="call_abc",
            name="read_file",
            arguments={"path": "/test/file.py"},
        )
        llm_service = MockLLMService(
            response=MockLLMResponse(
                content="",
                tool_calls=[tool_call],
            )
        )

        result = think_node(state, llm_service)

        # Should have user message + assistant with tool calls
        assert len(result.messages) == 2
        assert result.messages[0]["role"] == "user"
        assert "tool_calls" in result.messages[1]
        assert len(result.messages[1]["tool_calls"]) == 1
        assert result.messages[1]["tool_calls"][0]["function"]["name"] == "read_file"

        # Should NOT be done (has tool calls)
        assert result.done is False

    def test_passes_tool_schemas(self):
        """Think node should pass tool schemas to LLM."""
        state = create_test_state()
        llm_service = MockLLMService()
        tool_adapter = MockToolAdapter(
            tool_names=["read_file"],
            tool_schemas=[{
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {"type": "object"},
                },
            }],
        )

        think_node(state, llm_service, tool_adapter=tool_adapter)

        # Should have tools in call
        assert "tools" in llm_service.calls[0]
        assert len(llm_service.calls[0]["tools"]) == 1

    def test_handles_llm_error(self):
        """Think node should handle LLM errors gracefully."""
        state = create_test_state()
        llm_service = MockLLMService(
            exception=Exception("API rate limit exceeded")
        )

        result = think_node(state, llm_service)

        # Should not crash
        assert result is not None

        # Error should be tracked
        assert result.error_count == 1
        assert "rate limit" in result.last_error

        # Iteration should still increment
        assert result.iteration == 1

    def test_handles_not_configured_error(self):
        """Think node should handle NotConfiguredError specially - sets done=True."""
        state = create_test_state()
        llm_service = MockLLMService(
            exception=NotConfiguredError("LLM service not configured")
        )

        result = think_node(state, llm_service)

        # Should not crash
        assert result is not None

        # Should set done=True to stop the graph (no point retrying)
        assert result.done is True

        # Should have clear error message directing user to setup
        assert result.last_error is not None
        assert "/setup" in result.last_error

        # error_count should NOT be incremented (not a retryable error)
        assert result.error_count == 0

        # Iteration should still increment
        assert result.iteration == 1

    def test_resets_error_count_on_success(self):
        """Successful completion should reset error count and clear last_error.

        error_count tracks consecutive errors for retry logic.
        Resetting on success prevents premature termination from transient errors.
        """
        state = create_test_state()
        state = state.model_copy(update={"error_count": 2, "last_error": "Previous error"})
        llm_service = MockLLMService()

        result = think_node(state, llm_service)

        # error_count is reset (tracks consecutive errors)
        assert result.error_count == 0
        # last_error is cleared (no current error)
        assert result.last_error is None


# =============================================================================
# Streaming Think Node Tests
# =============================================================================


class TestThinkNodeStreaming:
    """Tests for the streaming think_node_streaming function."""

    @pytest.mark.asyncio
    async def test_basic_streaming(self):
        """Streaming think node should accumulate chunks."""
        state = create_test_state()
        chunks = [
            StreamChunk(content="Hello, "),
            StreamChunk(content="world!"),
            StreamChunk(content="", finish_reason="stop"),
        ]
        llm_service = MockStreamingLLMService(chunks=chunks)

        result = await think_node_streaming(state, llm_service)

        # Should have user message + accumulated assistant content
        assert len(result.messages) == 2
        assert result.messages[0]["role"] == "user"
        assert "Hello, world!" in result.messages[1]["content"]

    @pytest.mark.asyncio
    async def test_streaming_callback(self):
        """Streaming should call callback for each chunk."""
        state = create_test_state()
        chunks = [
            StreamChunk(content="A"),
            StreamChunk(content="B"),
            StreamChunk(content="C"),
        ]
        llm_service = MockStreamingLLMService(chunks=chunks)
        received: list[str] = []

        def callback(content: str):
            received.append(content)

        await think_node_streaming(state, llm_service, stream_callback=callback)

        assert received == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_streaming_tool_calls(self):
        """Streaming should accumulate tool call fragments."""
        state = create_test_state()
        chunks = [
            StreamChunk(
                content="",
                tool_call_fragments=[
                    ToolCallFragment(
                        id="call_123",
                        type="function",
                        name="read_file",
                        arguments='{"path": "/test"}',
                        index=0,
                    )
                ],
            ),
            StreamChunk(content="", finish_reason="tool_calls"),
        ]
        llm_service = MockStreamingLLMService(chunks=chunks)

        result = await think_node_streaming(state, llm_service)

        # Should have user message + assistant with tool calls
        assert len(result.messages) == 2
        assert result.messages[0]["role"] == "user"
        assert "tool_calls" in result.messages[1]
        assert result.messages[1]["tool_calls"][0]["function"]["name"] == "read_file"
        assert result.done is False

    @pytest.mark.asyncio
    async def test_streaming_handles_error(self):
        """Streaming should handle errors gracefully."""
        state = create_test_state()
        llm_service = MockStreamingLLMService(
            exception=Exception("Stream timeout")
        )

        result = await think_node_streaming(state, llm_service)

        assert result.error_count == 1
        assert "timeout" in result.last_error.lower()

    @pytest.mark.asyncio
    async def test_streaming_handles_not_configured_error(self):
        """Streaming should handle NotConfiguredError specially - sets done=True."""
        state = create_test_state()
        llm_service = MockStreamingLLMService(
            exception=NotConfiguredError("LLM service not configured")
        )

        result = await think_node_streaming(state, llm_service)

        # Should set done=True to stop the graph
        assert result.done is True

        # Should have clear error message
        assert result.last_error is not None
        assert "/setup" in result.last_error

        # error_count should NOT be incremented
        assert result.error_count == 0

    @pytest.mark.asyncio
    async def test_streaming_uses_state_tier_without_tools(self):
        """Streaming should use state.current_tier even without tools."""
        state = create_test_state(current_tier="chat")
        llm_service = MockStreamingLLMService(chunks=[
            StreamChunk(content="Test", finish_reason="stop")
        ])

        # No tool_adapter, uses state.current_tier
        await think_node_streaming(state, llm_service, tool_adapter=None)

        assert llm_service.calls[0]["model"] == "chat"

    @pytest.mark.asyncio
    async def test_streaming_uses_state_tier_with_tools(self):
        """Streaming should use state.current_tier when tool_adapter is provided."""
        state = create_test_state(current_tier="instruct")
        llm_service = MockStreamingLLMService(chunks=[
            StreamChunk(content="Test", finish_reason="stop")
        ])
        tool_adapter = MockToolAdapter(tool_names=["test_tool"])

        # With tool_adapter = agent mode = use state.current_tier
        await think_node_streaming(state, llm_service, tool_adapter=tool_adapter)

        assert llm_service.calls[0]["model"] == "instruct"


# =============================================================================
# Integration-style Tests
# =============================================================================


class TestThinkNodeIntegration:
    """Integration-style tests for think node behavior."""

    def test_multi_turn_conversation(self):
        """Think node should work correctly in multi-turn conversations."""
        # Turn 1
        state = create_test_state(input_text="What is Python?")
        llm_service = MockLLMService(
            response=MockLLMResponse(content="Python is a programming language.")
        )

        state = think_node(state, llm_service)

        # After turn 1: [user1, assistant1]
        assert len(state.messages) == 2

        # Turn 2 - user follow-up
        state = state.model_copy(update={
            "input": "What are its main features?",
            "messages": state.messages + [
                {"role": "user", "content": "What are its main features?"}
            ],
            "done": False,
        })
        llm_service = MockLLMService(
            response=MockLLMResponse(content="Python features include...")
        )

        state = think_node(state, llm_service)

        # Should have 4 messages total (user1 + assistant1 + user2 + assistant2)
        assert len(state.messages) == 4
        assert state.messages[0]["role"] == "user"
        assert state.messages[1]["role"] == "assistant"
        assert state.messages[2]["role"] == "user"
        assert state.messages[3]["role"] == "assistant"
        assert state.iteration == 2

    def test_tool_use_flow(self):
        """Think node should support multi-step tool use."""
        state = create_test_state(input_text="Read the config file")
        tool_adapter = MockToolAdapter(
            tool_names=["read_file"],
            tool_schemas=[{
                "type": "function",
                "function": {"name": "read_file"},
            }],
        )

        # Step 1: LLM decides to use tool
        tool_call = MockToolCall(
            id="call_1",
            name="read_file",
            arguments={"path": "config.py"},
        )
        llm_service = MockLLMService(
            response=MockLLMResponse(content="", tool_calls=[tool_call])
        )

        state = think_node(state, llm_service, tool_adapter=tool_adapter)

        # Should have [user, assistant_with_tool_calls], not be done
        assert len(state.messages) == 2
        assert state.messages[0]["role"] == "user"
        assert "tool_calls" in state.messages[1]
        assert state.done is False

        # Step 2: After tool execution, LLM provides final answer
        # (In real flow, execute node would run between these)
        state = state.model_copy(update={
            "messages": state.messages + [
                {"role": "tool", "content": "config data...", "tool_call_id": "call_1"}
            ]
        })
        llm_service = MockLLMService(
            response=MockLLMResponse(content="The config contains...")
        )

        state = think_node(state, llm_service, tool_adapter=tool_adapter)

        # Now should be done with [user, assistant_tool, tool_result, assistant_final]
        assert state.done is True
        assert len(state.messages) == 4
        assert "config contains" in state.messages[-1]["content"]

    def test_error_recovery_flow(self):
        """Think node should support error recovery."""
        state = create_test_state(
            last_error="FileNotFoundError: config.py not found",
            error_count=1,
        )
        llm_service = MockLLMService(
            response=MockLLMResponse(
                content="I see the file was not found. Let me check the directory..."
            )
        )

        result = think_node(state, llm_service)

        # error_count reset on successful recovery, last_error cleared
        assert result.error_count == 0  # Reset on success
        assert result.last_error is None  # Cleared on success

        # LLM should have received error context
        call_messages = llm_service.calls[0]["messages"]
        system_prompt = next(m["content"] for m in call_messages if m["role"] == "system")
        assert "FileNotFoundError" in system_prompt
