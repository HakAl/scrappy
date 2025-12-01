"""
Tests for native tool calling support.

These tests define the expected behavior for:
1. ToolCall dataclass - structured representation of LLM tool calls
2. LLMResponse with tool_calls field - enhanced response structure
3. NativeToolCallParser - parsing tool calls into ParseResult
4. chat_with_tools method - provider interface for tool-enabled chat

TDD approach: Write failing tests first, then implement to satisfy them.
"""
import pytest
from datetime import datetime


class TestToolCallDataclass:
    """Tests for ToolCall dataclass structure and creation."""

    @pytest.mark.unit
    def test_tool_call_creation_with_required_fields(self):
        """ToolCall holds structured tool call data from LLM."""
        from scrappy.providers.base import ToolCall

        tool_call = ToolCall(
            id="call_abc123",
            name="read_file",
            arguments={"path": "config.json"}
        )

        assert tool_call.id == "call_abc123"
        assert tool_call.name == "read_file"
        assert tool_call.arguments == {"path": "config.json"}

    @pytest.mark.unit
    def test_tool_call_with_empty_arguments(self):
        """ToolCall can have empty arguments dict."""
        from scrappy.providers.base import ToolCall

        tool_call = ToolCall(
            id="call_xyz789",
            name="git_status",
            arguments={}
        )

        assert tool_call.arguments == {}

    @pytest.mark.unit
    def test_tool_call_with_complex_arguments(self):
        """ToolCall preserves complex nested argument structures."""
        from scrappy.providers.base import ToolCall

        tool_call = ToolCall(
            id="call_complex",
            name="write_file",
            arguments={
                "path": "config.json",
                "content": '{"key": "value", "nested": {"a": 1}}',
                "options": {"overwrite": True, "create_dirs": False}
            }
        )

        assert tool_call.arguments["path"] == "config.json"
        assert "nested" in tool_call.arguments["content"]
        assert tool_call.arguments["options"]["overwrite"] is True

class TestLLMResponseWithToolCalls:
    """Tests for LLMResponse extended with tool_calls field."""

    @pytest.mark.unit
    def test_llm_response_backward_compatibility(self):
        """LLMResponse without tool_calls remains backward compatible."""
        from scrappy.providers.base import LLMResponse

        response = LLMResponse(
            content="Here is the answer",
            model="test-model",
            provider="test-provider",
            tokens_used=100,
            input_tokens=50,
            output_tokens=50
        )

        assert response.content == "Here is the answer"
        assert response.model == "test-model"
        assert response.provider == "test-provider"

    @pytest.mark.unit
    def test_llm_response_with_tool_calls_defaults_to_none(self):
        """LLMResponse.tool_calls defaults to None when not specified."""
        from scrappy.providers.base import LLMResponse

        response = LLMResponse(
            content="Response text",
            model="test-model",
            provider="test-provider"
        )

        assert response.tool_calls is None

    @pytest.mark.unit
    def test_llm_response_with_single_tool_call(self):
        """LLMResponse can contain a single tool call."""
        from scrappy.providers.base import LLMResponse, ToolCall

        tool_call = ToolCall(
            id="call_single",
            name="search_code",
            arguments={"pattern": "def main"}
        )

        response = LLMResponse(
            content="Let me search for the main function.",
            model="test-model",
            provider="test-provider",
            tool_calls=[tool_call]
        )

        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "search_code"

    @pytest.mark.unit
    def test_llm_response_with_multiple_tool_calls(self):
        """LLMResponse can contain multiple tool calls."""
        from scrappy.providers.base import LLMResponse, ToolCall

        call1 = ToolCall(id="call_1", name="read_file", arguments={"path": "a.txt"})
        call2 = ToolCall(id="call_2", name="read_file", arguments={"path": "b.txt"})
        call3 = ToolCall(id="call_3", name="git_status", arguments={})

        response = LLMResponse(
            content="Reading multiple files and checking status.",
            model="test-model",
            provider="test-provider",
            tool_calls=[call1, call2, call3]
        )

        assert len(response.tool_calls) == 3
        assert response.tool_calls[0].id == "call_1"
        assert response.tool_calls[2].name == "git_status"

    @pytest.mark.unit
    def test_llm_response_with_empty_tool_calls_list(self):
        """LLMResponse can have empty tool_calls list (LLM decided not to call tools)."""
        from scrappy.providers.base import LLMResponse

        response = LLMResponse(
            content="I don't need to use any tools for this.",
            model="test-model",
            provider="test-provider",
            tool_calls=[]
        )

        assert response.tool_calls == []
        assert len(response.tool_calls) == 0

    @pytest.mark.unit
    def test_llm_response_content_can_be_empty_with_tool_calls(self):
        """LLMResponse can have empty content when tool calls are present."""
        from scrappy.providers.base import LLMResponse, ToolCall

        tool_call = ToolCall(
            id="call_notext",
            name="list_files",
            arguments={"path": "."}
        )

        response = LLMResponse(
            content="",  # Some LLMs may return empty content with tool calls
            model="test-model",
            provider="test-provider",
            tool_calls=[tool_call]
        )

        assert response.content == ""
        assert len(response.tool_calls) == 1


class TestNativeToolCallParser:
    """Tests for NativeToolCallParser that parses LLMResponse tool calls."""

    @pytest.mark.unit
    def test_parser_parses_single_tool_call(self):
        """Parser extracts action from single tool call in LLMResponse."""
        from scrappy.agent.response_parser import NativeToolCallParser, ParseResult
        from scrappy.providers.base import LLMResponse, ToolCall

        tool_call = ToolCall(
            id="call_test",
            name="read_file",
            arguments={"path": "config.json"}
        )

        response = LLMResponse(
            content="I need to read the config file.",
            model="test-model",
            provider="test-provider",
            tool_calls=[tool_call]
        )

        parser = NativeToolCallParser()
        result = parser.parse_response(response)

        assert isinstance(result, ParseResult)
        assert result.action == "read_file"
        assert result.parameters == {"path": "config.json"}
        assert result.thought == "I need to read the config file."
        assert result.is_complete is False

    @pytest.mark.unit
    def test_parser_uses_first_tool_call_when_multiple(self):
        """Parser uses the first tool call when LLM returns multiple."""
        from scrappy.agent.response_parser import NativeToolCallParser
        from scrappy.providers.base import LLMResponse, ToolCall

        call1 = ToolCall(id="call_1", name="search_code", arguments={"pattern": "def"})
        call2 = ToolCall(id="call_2", name="list_files", arguments={"path": "."})

        response = LLMResponse(
            content="Searching and listing.",
            model="test-model",
            provider="test-provider",
            tool_calls=[call1, call2]
        )

        parser = NativeToolCallParser()
        result = parser.parse_response(response)

        # Should use first tool call
        assert result.action == "search_code"
        assert result.parameters == {"pattern": "def"}

    @pytest.mark.unit
    def test_parser_handles_no_tool_calls_as_completion(self):
        """Parser treats no tool calls as task completion."""
        from scrappy.agent.response_parser import NativeToolCallParser
        from scrappy.providers.base import LLMResponse

        response = LLMResponse(
            content="Task completed successfully. The file has been created.",
            model="test-model",
            provider="test-provider",
            tool_calls=None
        )

        parser = NativeToolCallParser()
        result = parser.parse_response(response)

        assert result.is_complete is True
        assert result.action == "complete"
        assert result.result_text == "Task completed successfully. The file has been created."

    @pytest.mark.unit
    def test_parser_handles_empty_tool_calls_list_as_completion(self):
        """Parser treats empty tool_calls list as completion."""
        from scrappy.agent.response_parser import NativeToolCallParser
        from scrappy.providers.base import LLMResponse

        response = LLMResponse(
            content="All done!",
            model="test-model",
            provider="test-provider",
            tool_calls=[]
        )

        parser = NativeToolCallParser()
        result = parser.parse_response(response)

        assert result.is_complete is True
        assert result.action == "complete"

    @pytest.mark.unit
    def test_parser_uses_content_as_thought(self):
        """Parser uses response content as the thought field."""
        from scrappy.agent.response_parser import NativeToolCallParser
        from scrappy.providers.base import LLMResponse, ToolCall

        tool_call = ToolCall(
            id="call_x",
            name="git_status",
            arguments={}
        )

        response = LLMResponse(
            content="Let me check the git status to see what files have changed.",
            model="test-model",
            provider="test-provider",
            tool_calls=[tool_call]
        )

        parser = NativeToolCallParser()
        result = parser.parse_response(response)

        assert result.thought == "Let me check the git status to see what files have changed."

    @pytest.mark.unit
    def test_parser_handles_empty_content_with_tool_call(self):
        """Parser handles empty content when tool calls are present."""
        from scrappy.agent.response_parser import NativeToolCallParser
        from scrappy.providers.base import LLMResponse, ToolCall

        tool_call = ToolCall(
            id="call_silent",
            name="list_directory",
            arguments={"path": "/src"}
        )

        response = LLMResponse(
            content="",
            model="test-model",
            provider="test-provider",
            tool_calls=[tool_call]
        )

        parser = NativeToolCallParser()
        result = parser.parse_response(response)

        assert result.action == "list_directory"
        assert result.thought == ""  # Empty but valid
        assert result.is_complete is False

    @pytest.mark.unit
    def test_parser_preserves_complex_arguments(self):
        """Parser preserves complex nested arguments from tool calls."""
        from scrappy.agent.response_parser import NativeToolCallParser
        from scrappy.providers.base import LLMResponse, ToolCall

        tool_call = ToolCall(
            id="call_complex",
            name="write_file",
            arguments={
                "path": "data.json",
                "content": '{"users": [{"id": 1, "name": "Alice"}]}',
                "options": {"mode": "overwrite"}
            }
        )

        response = LLMResponse(
            content="Writing the data file.",
            model="test-model",
            provider="test-provider",
            tool_calls=[tool_call]
        )

        parser = NativeToolCallParser()
        result = parser.parse_response(response)

        assert result.parameters["path"] == "data.json"
        assert "users" in result.parameters["content"]
        assert result.parameters["options"]["mode"] == "overwrite"

    @pytest.mark.unit
    def test_parser_returns_no_error_for_valid_response(self):
        """Parser returns no error for valid tool call response."""
        from scrappy.agent.response_parser import NativeToolCallParser
        from scrappy.providers.base import LLMResponse, ToolCall

        tool_call = ToolCall(
            id="call_ok",
            name="search_code",
            arguments={"pattern": "TODO"}
        )

        response = LLMResponse(
            content="Searching for TODOs.",
            model="test-model",
            provider="test-provider",
            tool_calls=[tool_call]
        )

        parser = NativeToolCallParser()
        result = parser.parse_response(response)

        assert result.error is None

