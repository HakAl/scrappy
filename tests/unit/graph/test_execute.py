"""
Unit tests for the Execute node.

Tests tool execution step including:
- Tool call parsing from messages
- Multi-tool execution
- Sequential execution
- Output truncation
- Binary file guard
- File change tracking
- Error handling
"""

from pathlib import Path
from typing import Optional

from scrappy.agent_tools.tools.base import ToolContext
from scrappy.graph.state import AgentState, Message, ToolCall, ToolResult
from scrappy.graph.nodes.execute import (
    execute_node,
    extract_tool_calls,
    truncate_output,
    is_binary_content,
    format_binary_placeholder,
    process_tool_result,
    track_file_changes,
    build_tool_message,
    OUTPUT_TRUNCATION_LIMIT,
)


# =============================================================================
# Test Doubles
# =============================================================================


class MockToolAdapter:
    """Mock tool adapter for testing execute node."""

    def __init__(
        self,
        results: Optional[list[ToolResult]] = None,
        exception: Optional[Exception] = None,
    ):
        self.results = results or []
        self.exception = exception
        self.executed_calls: list[tuple[list[ToolCall], ToolContext]] = []

    def execute(
        self,
        tool_calls: list[ToolCall],
        context: ToolContext,
    ) -> list[ToolResult]:
        """Record calls and return mock results."""
        self.executed_calls.append((tool_calls, context))

        if self.exception:
            raise self.exception

        # Return results for each tool call
        if self.results:
            return self.results
        return [
            ToolResult(name=tc["name"], result="mock result")
            for tc in tool_calls
        ]

    def get_tool_names(self) -> list[str]:
        return ["read_file", "write_file", "execute_shell"]

    def get_tool_schemas(self) -> list[dict]:
        return []


def create_test_state(
    input_text: str = "Test task",
    working_dir: str = "/tmp/test",
    messages: Optional[list[Message]] = None,
    files_changed: Optional[list[str]] = None,
    files_verified: bool = True,
) -> AgentState:
    """Create a test AgentState."""
    return AgentState(
        input=input_text,
        original_task=input_text,
        working_dir=working_dir,
        messages=messages or [],
        files_changed=files_changed or [],
        files_verified=files_verified,
    )


def create_test_context() -> ToolContext:
    """Create a test ToolContext."""
    return ToolContext(
        project_root=Path("/tmp/test"),
        dry_run=True,
    )


# =============================================================================
# Truncation Tests
# =============================================================================


class TestTruncateOutput:
    """Tests for output truncation."""

    def test_no_truncation_under_limit(self):
        """Output under limit should not be truncated."""
        output = "Short output"
        result = truncate_output(output)
        assert result == output

    def test_no_truncation_at_limit(self):
        """Output exactly at limit should not be truncated."""
        output = "x" * OUTPUT_TRUNCATION_LIMIT
        result = truncate_output(output)
        assert result == output

    def test_truncation_over_limit(self):
        """Output over limit should be truncated."""
        output = "x" * (OUTPUT_TRUNCATION_LIMIT + 1000)
        result = truncate_output(output)

        assert len(result) <= OUTPUT_TRUNCATION_LIMIT
        assert "truncated" in result
        assert "1000" in result  # Should show truncated char count

    def test_truncation_preserves_start_and_end(self):
        """Truncation should preserve both start and end content."""
        start_marker = "START_MARKER_123"
        end_marker = "END_MARKER_456"
        middle = "x" * (OUTPUT_TRUNCATION_LIMIT + 1000)
        output = start_marker + middle + end_marker

        result = truncate_output(output)

        assert start_marker in result
        assert end_marker in result

    def test_truncation_with_custom_limit(self):
        """Should respect custom limit."""
        output = "x" * 1000
        result = truncate_output(output, limit=100)

        assert len(result) <= 100
        assert "truncated" in result


# =============================================================================
# Binary Content Detection Tests
# =============================================================================


class TestBinaryContentDetection:
    """Tests for binary content detection."""

    def test_empty_string_not_binary(self):
        """Empty string should not be detected as binary."""
        assert is_binary_content("") is False

    def test_regular_text_not_binary(self):
        """Regular text should not be detected as binary."""
        content = "Hello, world!\nThis is regular text.\n"
        assert is_binary_content(content) is False

    def test_code_not_binary(self):
        """Source code should not be detected as binary."""
        content = """
def hello():
    print("Hello, world!")

if __name__ == "__main__":
    hello()
"""
        assert is_binary_content(content) is False

    def test_null_bytes_detected_as_binary(self):
        """Content with null bytes should be detected as binary."""
        content = "Hello\x00World"
        assert is_binary_content(content) is True

    def test_high_non_printable_ratio_detected_as_binary(self):
        """Content with many non-printable chars should be binary."""
        # Create content with >10% non-printable characters
        content = "a" * 80 + "\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0b" * 3
        assert is_binary_content(content) is True


class TestBinaryPlaceholder:
    """Tests for binary placeholder formatting."""

    def test_format_placeholder(self):
        """Should format placeholder with byte count."""
        result = format_binary_placeholder(1024)
        assert "Binary file" in result
        assert "1024" in result
        assert "bytes" in result

    def test_format_placeholder_zero_bytes(self):
        """Should handle zero bytes."""
        result = format_binary_placeholder(0)
        assert "0 bytes" in result


# =============================================================================
# Tool Call Extraction Tests
# =============================================================================


class TestExtractToolCalls:
    """Tests for extracting tool calls from state."""

    def test_extract_from_empty_messages(self):
        """Empty messages should return empty list."""
        state = create_test_state(messages=[])
        result = extract_tool_calls(state)
        assert result == []

    def test_extract_from_user_message(self):
        """User message should return empty list."""
        state = create_test_state(
            messages=[{"role": "user", "content": "Hello"}]
        )
        result = extract_tool_calls(state)
        assert result == []

    def test_extract_from_assistant_without_tool_calls(self):
        """Assistant message without tool calls should return empty list."""
        state = create_test_state(
            messages=[{"role": "assistant", "content": "Hello"}]
        )
        result = extract_tool_calls(state)
        assert result == []

    def test_extract_single_tool_call(self):
        """Should extract single tool call."""
        tool_call: ToolCall = {
            "id": "call_1",
            "name": "read_file",
            "arguments": '{"path": "/test"}',
        }
        state = create_test_state(
            messages=[{
                "role": "assistant",
                "content": "",
                "tool_calls": [tool_call],
            }]
        )

        result = extract_tool_calls(state)

        assert len(result) == 1
        assert result[0]["name"] == "read_file"

    def test_extract_multiple_tool_calls(self):
        """Should extract multiple tool calls."""
        tool_calls: list[ToolCall] = [
            {"id": "call_1", "name": "read_file", "arguments": "{}"},
            {"id": "call_2", "name": "write_file", "arguments": "{}"},
        ]
        state = create_test_state(
            messages=[{
                "role": "assistant",
                "content": "",
                "tool_calls": tool_calls,
            }]
        )

        result = extract_tool_calls(state)

        assert len(result) == 2
        assert result[0]["name"] == "read_file"
        assert result[1]["name"] == "write_file"

    def test_only_extracts_from_last_message(self):
        """Should only extract from the last message."""
        old_tool_call: ToolCall = {"id": "old", "name": "old_tool"}
        new_tool_call: ToolCall = {"id": "new", "name": "new_tool"}

        state = create_test_state(
            messages=[
                {"role": "assistant", "content": "", "tool_calls": [old_tool_call]},
                {"role": "tool", "content": "result", "tool_call_id": "old"},
                {"role": "assistant", "content": "", "tool_calls": [new_tool_call]},
            ]
        )

        result = extract_tool_calls(state)

        assert len(result) == 1
        assert result[0]["name"] == "new_tool"


# =============================================================================
# Process Tool Result Tests
# =============================================================================


class TestProcessToolResult:
    """Tests for tool result processing."""

    def test_passes_through_error_results(self):
        """Error results should pass through unchanged."""
        result = ToolResult(name="test", error="Something went wrong")

        processed = process_tool_result(result)

        assert processed["error"] == "Something went wrong"

    def test_truncates_long_output(self):
        """Long output should be truncated."""
        long_content = "x" * (OUTPUT_TRUNCATION_LIMIT + 5000)
        result = ToolResult(name="test", result=long_content)

        processed = process_tool_result(result)

        assert len(processed["result"]) <= OUTPUT_TRUNCATION_LIMIT
        assert "truncated" in processed["result"]

    def test_detects_binary_content(self):
        """Binary content should be replaced with placeholder."""
        binary_content = "Hello\x00World\x00Binary\x00Data"
        result = ToolResult(name="test", result=binary_content)

        processed = process_tool_result(result)

        assert "Binary file" in processed["result"]
        assert "bytes" in processed["result"]

    def test_preserves_normal_output(self):
        """Normal output should be preserved."""
        content = "Normal text output"
        result = ToolResult(name="test", result=content)

        processed = process_tool_result(result)

        assert processed["result"] == content


# =============================================================================
# File Change Tracking Tests
# =============================================================================


class TestTrackFileChanges:
    """Tests for file change tracking."""

    def test_ignores_read_operations(self):
        """Read operations should not track changes."""
        tool_call: ToolCall = {
            "id": "1",
            "name": "read_file",
            "arguments": '{"path": "/test/file.py"}',
        }

        result = track_file_changes(tool_call, [])

        assert result == []

    def test_tracks_write_file(self):
        """write_file should track file path."""
        tool_call: ToolCall = {
            "id": "1",
            "name": "write_file",
            "arguments": '{"path": "/test/new_file.py"}',
        }

        result = track_file_changes(tool_call, [])

        assert "/test/new_file.py" in result

    def test_tracks_edit_file(self):
        """edit_file should track file path."""
        tool_call: ToolCall = {
            "id": "1",
            "name": "edit_file",
            "arguments": '{"file_path": "/test/edited.py"}',
        }

        result = track_file_changes(tool_call, [])

        assert "/test/edited.py" in result

    def test_no_duplicate_tracking(self):
        """Should not add duplicate file paths."""
        tool_call: ToolCall = {
            "id": "1",
            "name": "write_file",
            "arguments": '{"path": "/test/file.py"}',
        }

        result = track_file_changes(tool_call, ["/test/file.py"])

        assert result.count("/test/file.py") == 1

    def test_handles_invalid_json(self):
        """Should handle invalid JSON arguments gracefully."""
        tool_call: ToolCall = {
            "id": "1",
            "name": "write_file",
            "arguments": "not valid json",
        }

        result = track_file_changes(tool_call, [])

        # Should not crash, just return unchanged
        assert result == []

    def test_preserves_existing_files(self):
        """Should preserve existing tracked files."""
        tool_call: ToolCall = {
            "id": "1",
            "name": "write_file",
            "arguments": '{"path": "/new_file.py"}',
        }

        result = track_file_changes(tool_call, ["/old_file.py"])

        assert "/old_file.py" in result
        assert "/new_file.py" in result


# =============================================================================
# Build Tool Message Tests
# =============================================================================


class TestBuildToolMessage:
    """Tests for building tool messages."""

    def test_builds_message_with_result(self):
        """Should build message with result content."""
        tool_call: ToolCall = {"id": "call_123", "name": "read_file"}
        result = ToolResult(name="read_file", result="File content here")

        message = build_tool_message(tool_call, result)

        assert message["role"] == "tool"
        assert message["content"] == "File content here"
        assert message["tool_call_id"] == "call_123"

    def test_builds_message_with_error(self):
        """Should build message with error content."""
        tool_call: ToolCall = {"id": "call_456", "name": "write_file"}
        result = ToolResult(name="write_file", error="Permission denied")

        message = build_tool_message(tool_call, result)

        assert message["role"] == "tool"
        assert message["content"] == "Permission denied"
        assert message["tool_call_id"] == "call_456"


# =============================================================================
# Execute Node Tests
# =============================================================================


class TestExecuteNode:
    """Tests for the main execute_node function."""

    def test_no_tool_calls_returns_unchanged(self):
        """No tool calls should return state unchanged."""
        state = create_test_state(
            messages=[{"role": "assistant", "content": "Hello"}]
        )
        adapter = MockToolAdapter()
        context = create_test_context()

        result = execute_node(state, adapter, context)

        assert result.messages == state.messages
        assert len(adapter.executed_calls) == 0

    def test_executes_single_tool_call(self):
        """Should execute a single tool call."""
        tool_call: ToolCall = {
            "id": "call_1",
            "name": "read_file",
            "arguments": '{"path": "/test.py"}',
        }
        state = create_test_state(
            messages=[{
                "role": "assistant",
                "content": "",
                "tool_calls": [tool_call],
            }]
        )
        adapter = MockToolAdapter(
            results=[ToolResult(name="read_file", result="file contents")]
        )
        context = create_test_context()

        result = execute_node(state, adapter, context)

        # Should have called adapter
        assert len(adapter.executed_calls) == 1
        assert len(adapter.executed_calls[0][0]) == 1

        # Should have added tool message
        assert len(result.messages) == 2
        assert result.messages[1]["role"] == "tool"
        assert result.messages[1]["content"] == "file contents"

    def test_executes_multiple_tool_calls_sequentially(self):
        """Should execute multiple tool calls in order."""
        tool_calls: list[ToolCall] = [
            {"id": "call_1", "name": "read_file", "arguments": "{}"},
            {"id": "call_2", "name": "write_file", "arguments": "{}"},
        ]
        state = create_test_state(
            messages=[{
                "role": "assistant",
                "content": "",
                "tool_calls": tool_calls,
            }]
        )
        adapter = MockToolAdapter(
            results=[
                ToolResult(name="read_file", result="read result"),
                ToolResult(name="write_file", result="write result"),
            ]
        )
        context = create_test_context()

        result = execute_node(state, adapter, context)

        # Should have one batch call (sequential in adapter.execute)
        assert len(adapter.executed_calls) == 1
        assert len(adapter.executed_calls[0][0]) == 2

        # Should have added two tool messages
        assert len(result.messages) == 3  # Original + 2 tool messages
        assert result.messages[1]["role"] == "tool"
        assert result.messages[2]["role"] == "tool"

    def test_tracks_file_changes(self):
        """Should track file changes from write operations."""
        tool_call: ToolCall = {
            "id": "call_1",
            "name": "write_file",
            "arguments": '{"path": "/new_file.py"}',
        }
        state = create_test_state(
            messages=[{
                "role": "assistant",
                "content": "",
                "tool_calls": [tool_call],
            }],
            files_changed=[],
            files_verified=True,
        )
        adapter = MockToolAdapter(
            results=[ToolResult(name="write_file", result="written")]
        )
        context = create_test_context()

        result = execute_node(state, adapter, context)

        assert "/new_file.py" in result.files_changed
        assert result.files_verified is False  # Should be invalidated

    def test_preserves_existing_file_changes(self):
        """Should preserve existing files_changed."""
        tool_call: ToolCall = {
            "id": "call_1",
            "name": "write_file",
            "arguments": '{"path": "/new.py"}',
        }
        state = create_test_state(
            messages=[{
                "role": "assistant",
                "content": "",
                "tool_calls": [tool_call],
            }],
            files_changed=["/old.py"],
        )
        adapter = MockToolAdapter(
            results=[ToolResult(name="write_file", result="ok")]
        )
        context = create_test_context()

        result = execute_node(state, adapter, context)

        assert "/old.py" in result.files_changed
        assert "/new.py" in result.files_changed

    def test_stores_tool_results(self):
        """Should store tool results in state."""
        tool_call: ToolCall = {"id": "call_1", "name": "test_tool"}
        state = create_test_state(
            messages=[{
                "role": "assistant",
                "content": "",
                "tool_calls": [tool_call],
            }]
        )
        expected_result = ToolResult(name="test_tool", result="output")
        adapter = MockToolAdapter(results=[expected_result])
        context = create_test_context()

        result = execute_node(state, adapter, context)

        assert len(result.tool_results) == 1
        assert result.tool_results[0]["name"] == "test_tool"

    def test_creates_default_context(self):
        """Should create default context if none provided."""
        tool_call: ToolCall = {"id": "call_1", "name": "test_tool"}
        state = create_test_state(
            working_dir="/project/root",
            messages=[{
                "role": "assistant",
                "content": "",
                "tool_calls": [tool_call],
            }]
        )
        adapter = MockToolAdapter()

        # Execute without context
        execute_node(state, adapter)

        # Should have called with a context
        assert len(adapter.executed_calls) == 1
        used_context = adapter.executed_calls[0][1]
        # Use Path comparison for cross-platform compatibility
        assert used_context.project_root == Path("/project/root")

    def test_handles_tool_errors(self):
        """Should handle tool execution errors."""
        tool_call: ToolCall = {"id": "call_1", "name": "failing_tool"}
        state = create_test_state(
            messages=[{
                "role": "assistant",
                "content": "",
                "tool_calls": [tool_call],
            }]
        )
        adapter = MockToolAdapter(
            results=[ToolResult(name="failing_tool", error="Tool failed")]
        )
        context = create_test_context()

        result = execute_node(state, adapter, context)

        # Should still add message with error
        assert len(result.messages) == 2
        assert result.messages[1]["content"] == "Tool failed"

    def test_truncates_long_tool_output(self):
        """Should truncate long tool output."""
        long_output = "x" * (OUTPUT_TRUNCATION_LIMIT + 5000)
        tool_call: ToolCall = {"id": "call_1", "name": "verbose_tool"}
        state = create_test_state(
            messages=[{
                "role": "assistant",
                "content": "",
                "tool_calls": [tool_call],
            }]
        )
        adapter = MockToolAdapter(
            results=[ToolResult(name="verbose_tool", result=long_output)]
        )
        context = create_test_context()

        result = execute_node(state, adapter, context)

        # Message content should be truncated
        assert len(result.messages[1]["content"]) <= OUTPUT_TRUNCATION_LIMIT
        assert "truncated" in result.messages[1]["content"]

    def test_handles_binary_output(self):
        """Should replace binary output with placeholder."""
        binary_output = "Hello\x00World\x00Binary"
        tool_call: ToolCall = {"id": "call_1", "name": "binary_tool"}
        state = create_test_state(
            messages=[{
                "role": "assistant",
                "content": "",
                "tool_calls": [tool_call],
            }]
        )
        adapter = MockToolAdapter(
            results=[ToolResult(name="binary_tool", result=binary_output)]
        )
        context = create_test_context()

        result = execute_node(state, adapter, context)

        assert "Binary file" in result.messages[1]["content"]


# =============================================================================
# Integration-style Tests
# =============================================================================


class TestExecuteNodeIntegration:
    """Integration-style tests for execute node behavior."""

    def test_full_tool_execution_flow(self):
        """Test complete flow from assistant message to tool results."""
        # Simulate assistant requesting multiple tools
        tool_calls: list[ToolCall] = [
            {"id": "call_1", "name": "read_file", "arguments": '{"path": "/src/main.py"}'},
            {"id": "call_2", "name": "write_file", "arguments": '{"path": "/src/new.py"}'},
        ]

        state = create_test_state(
            messages=[{
                "role": "assistant",
                "content": "Let me read the file and create a new one.",
                "tool_calls": tool_calls,
            }]
        )

        adapter = MockToolAdapter(
            results=[
                ToolResult(name="read_file", result="def main(): pass"),
                ToolResult(name="write_file", result="File created"),
            ]
        )
        context = create_test_context()

        result = execute_node(state, adapter, context)

        # Check messages
        assert len(result.messages) == 3
        assert result.messages[0]["role"] == "assistant"
        assert result.messages[1]["role"] == "tool"
        assert result.messages[1]["tool_call_id"] == "call_1"
        assert result.messages[2]["role"] == "tool"
        assert result.messages[2]["tool_call_id"] == "call_2"

        # Check file tracking
        assert "/src/new.py" in result.files_changed
        assert result.files_verified is False

    def test_read_only_operations_preserve_verified(self):
        """Read-only operations should not invalidate verification."""
        tool_call: ToolCall = {
            "id": "call_1",
            "name": "read_file",
            "arguments": '{"path": "/src/main.py"}',
        }
        state = create_test_state(
            messages=[{
                "role": "assistant",
                "content": "",
                "tool_calls": [tool_call],
            }],
            files_verified=True,
        )
        adapter = MockToolAdapter(
            results=[ToolResult(name="read_file", result="content")]
        )
        context = create_test_context()

        result = execute_node(state, adapter, context)

        # Verified should still be True (no writes)
        assert result.files_verified is True
