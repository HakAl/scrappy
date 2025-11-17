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
        from src.providers.base import ToolCall

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
        from src.providers.base import ToolCall

        tool_call = ToolCall(
            id="call_xyz789",
            name="git_status",
            arguments={}
        )

        assert tool_call.arguments == {}

    @pytest.mark.unit
    def test_tool_call_with_complex_arguments(self):
        """ToolCall preserves complex nested argument structures."""
        from src.providers.base import ToolCall

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

    @pytest.mark.unit
    def test_tool_call_id_uniqueness_assumption(self):
        """ToolCall IDs are unique identifiers from the LLM."""
        from src.providers.base import ToolCall

        call1 = ToolCall(id="call_001", name="read_file", arguments={"path": "a.txt"})
        call2 = ToolCall(id="call_002", name="read_file", arguments={"path": "b.txt"})

        assert call1.id != call2.id
        # Same tool name, different IDs
        assert call1.name == call2.name


class TestLLMResponseWithToolCalls:
    """Tests for LLMResponse extended with tool_calls field."""

    @pytest.mark.unit
    def test_llm_response_backward_compatibility(self):
        """LLMResponse without tool_calls remains backward compatible."""
        from src.providers.base import LLMResponse

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
        from src.providers.base import LLMResponse

        response = LLMResponse(
            content="Response text",
            model="test-model",
            provider="test-provider"
        )

        assert response.tool_calls is None

    @pytest.mark.unit
    def test_llm_response_with_single_tool_call(self):
        """LLMResponse can contain a single tool call."""
        from src.providers.base import LLMResponse, ToolCall

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
        from src.providers.base import LLMResponse, ToolCall

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
        from src.providers.base import LLMResponse

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
        from src.providers.base import LLMResponse, ToolCall

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
        from src.agent.response_parser import NativeToolCallParser, ParseResult
        from src.providers.base import LLMResponse, ToolCall

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
        from src.agent.response_parser import NativeToolCallParser
        from src.providers.base import LLMResponse, ToolCall

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
        from src.agent.response_parser import NativeToolCallParser
        from src.providers.base import LLMResponse

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
        from src.agent.response_parser import NativeToolCallParser
        from src.providers.base import LLMResponse

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
        from src.agent.response_parser import NativeToolCallParser
        from src.providers.base import LLMResponse, ToolCall

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
        from src.agent.response_parser import NativeToolCallParser
        from src.providers.base import LLMResponse, ToolCall

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
        from src.agent.response_parser import NativeToolCallParser
        from src.providers.base import LLMResponse, ToolCall

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
        from src.agent.response_parser import NativeToolCallParser
        from src.providers.base import LLMResponse, ToolCall

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


class TestNativeToolCallParserInterface:
    """Tests for NativeToolCallParser interface compatibility."""

    @pytest.mark.unit
    def test_parser_implements_response_parser_interface(self):
        """NativeToolCallParser implements ResponseParser interface."""
        from src.agent.response_parser import NativeToolCallParser, ResponseParser

        parser = NativeToolCallParser()

        assert isinstance(parser, ResponseParser)

    @pytest.mark.unit
    def test_parser_has_parse_response_method(self):
        """NativeToolCallParser has parse_response method for LLMResponse."""
        from src.agent.response_parser import NativeToolCallParser

        parser = NativeToolCallParser()

        assert hasattr(parser, 'parse_response')
        assert callable(parser.parse_response)

    @pytest.mark.unit
    def test_parser_has_parse_method_for_backward_compat(self):
        """NativeToolCallParser has parse(str) method for backward compat."""
        from src.agent.response_parser import NativeToolCallParser

        parser = NativeToolCallParser()

        # Should still have parse() method from base class
        assert hasattr(parser, 'parse')
        assert callable(parser.parse)

    @pytest.mark.unit
    def test_parser_parse_text_raises_for_native_parser(self):
        """parse() method indicates native tool calling is expected."""
        from src.agent.response_parser import NativeToolCallParser

        parser = NativeToolCallParser()

        # Calling parse with text should indicate this parser expects LLMResponse
        result = parser.parse("some text response")

        # Should indicate error since native parser expects LLMResponse not text
        assert result.error is not None or result.action == "retry_parse"


class TestChatWithToolsProviderInterface:
    """Tests for chat_with_tools method in provider interface."""

    @pytest.mark.unit
    def test_provider_has_chat_with_tools_method(self):
        """LLMProvider has chat_with_tools method."""
        from src.providers.base import LLMProvider

        # Check that the method exists in the class
        assert hasattr(LLMProvider, 'chat_with_tools')

    @pytest.mark.unit
    def test_chat_with_tools_accepts_tool_schemas(self):
        """chat_with_tools accepts OpenAI-compatible tool schemas."""
        from src.providers.base import LLMProvider
        import inspect

        # Check signature includes tools parameter
        sig = inspect.signature(LLMProvider.chat_with_tools)
        params = sig.parameters

        assert 'tools' in params
        assert 'messages' in params

    @pytest.mark.unit
    def test_chat_with_tools_returns_llm_response(self):
        """chat_with_tools returns LLMResponse with tool_calls."""
        from src.providers.base import LLMProvider, LLMResponse, ProviderLimits
        from unittest.mock import MagicMock

        # Create a concrete implementation for testing
        class TestProvider(LLMProvider):
            @property
            def name(self):
                return "test"

            @property
            def available_models(self):
                return ["test-model"]

            @property
            def default_model(self):
                return "test-model"

            def chat(self, messages, model=None, max_tokens=1000, temperature=0.7, **kwargs):
                return LLMResponse(
                    content="test",
                    model="test-model",
                    provider="test"
                )

            def get_limits(self):
                return ProviderLimits()

            def chat_with_tools(self, messages, tools, tool_choice="auto", **kwargs):
                # This would be implemented to call actual API with tools
                # For test, return a mock response
                return LLMResponse(
                    content="Using tool",
                    model="test-model",
                    provider="test",
                    tool_calls=[]
                )

        provider = TestProvider()
        messages = [{"role": "user", "content": "test"}]
        tools = [{"type": "function", "function": {"name": "test_tool"}}]

        response = provider.chat_with_tools(messages, tools)

        assert isinstance(response, LLMResponse)
        assert response.tool_calls is not None

    @pytest.mark.unit
    def test_chat_with_tools_default_tool_choice_is_auto(self):
        """chat_with_tools defaults tool_choice to 'auto'."""
        from src.providers.base import LLMProvider
        import inspect

        sig = inspect.signature(LLMProvider.chat_with_tools)
        params = sig.parameters

        assert 'tool_choice' in params
        assert params['tool_choice'].default == "auto"


class TestToolSchemaConversion:
    """Tests for converting tool registry to OpenAI-compatible schemas."""

    @pytest.mark.unit
    def test_tool_registry_has_to_openai_schema_method(self):
        """ToolRegistry has method to generate OpenAI tool schemas."""
        from src.agent_tools.tools import ToolRegistry

        registry = ToolRegistry()

        assert hasattr(registry, 'to_openai_schema')
        assert callable(registry.to_openai_schema)

    @pytest.mark.unit
    def test_to_openai_schema_returns_list(self):
        """to_openai_schema returns a list of tool definitions."""
        from src.agent_tools.tools import ToolRegistry

        registry = ToolRegistry()
        # Register a mock tool

        schemas = registry.to_openai_schema()

        assert isinstance(schemas, list)

    @pytest.mark.unit
    def test_to_openai_schema_format(self):
        """Tool schema follows OpenAI format structure."""
        from src.agent_tools.tools import ToolRegistry, Tool, ToolContext, ToolResult
        from src.agent_tools.tools.base import ToolParameter
        from pathlib import Path
        from unittest.mock import MagicMock

        # Create a test tool
        class TestTool(Tool):
            @property
            def name(self):
                return "test_tool"

            @property
            def description(self):
                return "A test tool"

            @property
            def parameters(self):
                return [
                    ToolParameter(
                        name="param1",
                        param_type=str,
                        description="First param",
                        required=True
                    )
                ]

            @property
            def parameters_schema(self):
                return {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "First param"}
                    },
                    "required": ["param1"]
                }

            def execute(self, context, **kwargs):
                return ToolResult(success=True, output="test")

        registry = ToolRegistry()
        registry.register(TestTool())

        schemas = registry.to_openai_schema()

        assert len(schemas) == 1
        schema = schemas[0]

        # Check OpenAI format
        assert schema["type"] == "function"
        assert "function" in schema
        assert schema["function"]["name"] == "test_tool"
        assert schema["function"]["description"] == "A test tool"
        assert "parameters" in schema["function"]
        assert schema["function"]["parameters"]["type"] == "object"


class TestNativeToolCallParserEdgeCases:
    """Tests for edge cases in native tool call parsing."""

    @pytest.mark.unit
    def test_parser_handles_tool_call_with_no_id(self):
        """Parser handles tool call gracefully even with unusual ID."""
        from src.agent.response_parser import NativeToolCallParser
        from src.providers.base import LLMResponse, ToolCall

        tool_call = ToolCall(
            id="",  # Empty ID (unusual but possible)
            name="git_log",
            arguments={"n": 10}
        )

        response = LLMResponse(
            content="Checking git history.",
            model="test-model",
            provider="test-provider",
            tool_calls=[tool_call]
        )

        parser = NativeToolCallParser()
        result = parser.parse_response(response)

        assert result.action == "git_log"
        assert result.parameters == {"n": 10}

    @pytest.mark.unit
    def test_parser_handles_very_long_content(self):
        """Parser handles very long content in thought."""
        from src.agent.response_parser import NativeToolCallParser
        from src.providers.base import LLMResponse, ToolCall

        long_thought = "I need to analyze this carefully. " * 100
        tool_call = ToolCall(
            id="call_long",
            name="read_file",
            arguments={"path": "big.txt"}
        )

        response = LLMResponse(
            content=long_thought,
            model="test-model",
            provider="test-provider",
            tool_calls=[tool_call]
        )

        parser = NativeToolCallParser()
        result = parser.parse_response(response)

        assert result.thought == long_thought
        assert result.action == "read_file"

    @pytest.mark.unit
    def test_parser_handles_unicode_in_arguments(self):
        """Parser handles Unicode characters in tool arguments."""
        from src.agent.response_parser import NativeToolCallParser
        from src.providers.base import LLMResponse, ToolCall

        tool_call = ToolCall(
            id="call_unicode",
            name="write_file",
            arguments={
                "path": "output.txt",
                "content": "Hello World - Multilingual content"
            }
        )

        response = LLMResponse(
            content="Writing multilingual content.",
            model="test-model",
            provider="test-provider",
            tool_calls=[tool_call]
        )

        parser = NativeToolCallParser()
        result = parser.parse_response(response)

        assert "content" in result.parameters
        assert "Hello World" in result.parameters["content"]

    @pytest.mark.unit
    def test_parser_handles_arguments_with_special_chars(self):
        """Parser preserves special characters in arguments."""
        from src.agent.response_parser import NativeToolCallParser
        from src.providers.base import LLMResponse, ToolCall

        tool_call = ToolCall(
            id="call_special",
            name="search_code",
            arguments={"pattern": r"def\s+\w+\(.*\):"}
        )

        response = LLMResponse(
            content="Searching with regex.",
            model="test-model",
            provider="test-provider",
            tool_calls=[tool_call]
        )

        parser = NativeToolCallParser()
        result = parser.parse_response(response)

        assert r"\s+" in result.parameters["pattern"]
        assert r"\w+" in result.parameters["pattern"]


class TestIntegrationWithAgentCore:
    """Tests for integration with agent core response parsing flow."""

    @pytest.mark.unit
    def test_parse_result_compatible_with_agent_action(self):
        """ParseResult from NativeToolCallParser works with AgentAction."""
        from src.agent.response_parser import NativeToolCallParser
        from src.providers.base import LLMResponse, ToolCall
        from src.agent.types import AgentAction

        tool_call = ToolCall(
            id="call_integration",
            name="read_file",
            arguments={"path": "test.py"}
        )

        response = LLMResponse(
            content="Reading the test file.",
            model="test-model",
            provider="test-provider",
            tool_calls=[tool_call]
        )

        parser = NativeToolCallParser()
        parse_result = parser.parse_response(response)

        # Convert to AgentAction (as done in core.py _plan_action)
        action = AgentAction(
            thought=parse_result.thought,
            action=parse_result.action,
            parameters=parse_result.parameters,
            is_complete=parse_result.is_complete,
            result_text=parse_result.result_text
        )

        assert action.thought == "Reading the test file."
        assert action.action == "read_file"
        assert action.parameters == {"path": "test.py"}
        assert action.is_complete is False

    @pytest.mark.unit
    def test_completion_parse_result_matches_expected_format(self):
        """Completion ParseResult has correct structure for agent evaluation."""
        from src.agent.response_parser import NativeToolCallParser
        from src.providers.base import LLMResponse

        response = LLMResponse(
            content="Task completed. File was created successfully.",
            model="test-model",
            provider="test-provider",
            tool_calls=None  # No tool calls = completion
        )

        parser = NativeToolCallParser()
        result = parser.parse_response(response)

        # Must match what agent evaluator expects
        assert result.is_complete is True
        assert result.action == "complete"
        assert result.result_text == "Task completed. File was created successfully."
        assert result.parameters == {}
