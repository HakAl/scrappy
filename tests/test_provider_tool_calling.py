"""
Tests for Groq and Cerebras provider native tool calling implementations.

These tests verify that the providers properly implement chat_with_tools
and return structured tool calls. Uses mocking to avoid requiring API keys.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
import json


class TestGroqProviderToolCalling:
    """Tests for Groq provider native tool calling."""

    @pytest.fixture
    def mock_groq_client(self):
        """Create a mock Groq client."""
        with patch('src.providers.groq_provider.GROQ_AVAILABLE', True):
            with patch('src.providers.groq_provider.Groq') as mock_groq:
                mock_client = MagicMock()
                mock_groq.return_value = mock_client
                yield mock_client

    @pytest.fixture
    def groq_provider(self, mock_groq_client):
        """Create Groq provider with mock client."""
        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            from src.providers.groq_provider import GroqProvider
            provider = GroqProvider()
            provider._client = mock_groq_client
            return provider

    @pytest.mark.unit
    def test_groq_supports_tool_calling_property(self, groq_provider):
        """Groq provider reports support for tool calling."""
        assert groq_provider.supports_tool_calling is True

    @pytest.mark.unit
    def test_groq_chat_with_tools_single_call(self, groq_provider, mock_groq_client):
        """Groq returns single tool call from API."""
        from src.providers.base import ToolCall

        # Mock API response with tool call
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "I'll read the file."

        # Create function mock with proper attributes
        mock_function = MagicMock()
        mock_function.name = "read_file"
        mock_function.arguments = '{"path": "config.json"}'

        mock_response.choices[0].message.tool_calls = [
            MagicMock(id="call_abc123", function=mock_function)
        ]
        mock_response.choices[0].finish_reason = "tool_calls"
        mock_response.usage = MagicMock(
            prompt_tokens=50,
            completion_tokens=20
        )

        mock_groq_client.chat.completions.create.return_value = mock_response

        messages = [{"role": "user", "content": "Read config.json"}]
        tools = [{"type": "function", "function": {"name": "read_file"}}]

        response = groq_provider.chat_with_tools(messages, tools)

        assert response.content == "I'll read the file."
        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].id == "call_abc123"
        assert response.tool_calls[0].name == "read_file"
        assert response.tool_calls[0].arguments == {"path": "config.json"}

    @pytest.mark.unit
    def test_groq_chat_with_tools_multiple_calls(self, groq_provider, mock_groq_client):
        """Groq returns multiple tool calls from API."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Reading both files."
        mock_response.choices[0].message.tool_calls = [
            MagicMock(
                id="call_1",
                function=MagicMock(
                    name="read_file",
                    arguments='{"path": "a.txt"}'
                )
            ),
            MagicMock(
                id="call_2",
                function=MagicMock(
                    name="read_file",
                    arguments='{"path": "b.txt"}'
                )
            )
        ]
        mock_response.choices[0].finish_reason = "tool_calls"
        mock_response.usage = MagicMock(prompt_tokens=60, completion_tokens=30)

        mock_groq_client.chat.completions.create.return_value = mock_response

        response = groq_provider.chat_with_tools(
            [{"role": "user", "content": "Read both files"}],
            [{"type": "function", "function": {"name": "read_file"}}]
        )

        assert len(response.tool_calls) == 2
        assert response.tool_calls[0].id == "call_1"
        assert response.tool_calls[1].id == "call_2"

    @pytest.mark.unit
    def test_groq_chat_with_tools_no_tool_calls(self, groq_provider, mock_groq_client):
        """Groq returns no tool calls when model doesn't use them."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "I don't need to use any tools."
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock(prompt_tokens=40, completion_tokens=15)

        mock_groq_client.chat.completions.create.return_value = mock_response

        response = groq_provider.chat_with_tools(
            [{"role": "user", "content": "What's 2+2?"}],
            [{"type": "function", "function": {"name": "calculator"}}]
        )

        assert response.content == "I don't need to use any tools."
        assert response.tool_calls is None or len(response.tool_calls) == 0

    @pytest.mark.unit
    def test_groq_chat_with_tools_passes_tool_choice(self, groq_provider, mock_groq_client):
        """Groq passes tool_choice parameter to API."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock(prompt_tokens=30, completion_tokens=10)

        mock_groq_client.chat.completions.create.return_value = mock_response

        groq_provider.chat_with_tools(
            [{"role": "user", "content": "test"}],
            [{"type": "function", "function": {"name": "test"}}],
            tool_choice="none"
        )

        # Verify tool_choice was passed to API
        call_kwargs = mock_groq_client.chat.completions.create.call_args.kwargs
        assert call_kwargs.get("tool_choice") == "none"

    @pytest.mark.unit
    def test_groq_chat_with_tools_complex_arguments(self, groq_provider, mock_groq_client):
        """Groq parses complex nested arguments correctly."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Writing file."
        mock_response.choices[0].message.tool_calls = [
            MagicMock(
                id="call_complex",
                function=MagicMock(
                    name="write_file",
                    arguments='{"path": "data.json", "content": "{\\"key\\": \\"value\\"}", "options": {"overwrite": true}}'
                )
            )
        ]
        mock_response.choices[0].finish_reason = "tool_calls"
        mock_response.usage = MagicMock(prompt_tokens=70, completion_tokens=40)

        mock_groq_client.chat.completions.create.return_value = mock_response

        response = groq_provider.chat_with_tools(
            [{"role": "user", "content": "Write JSON file"}],
            [{"type": "function", "function": {"name": "write_file"}}]
        )

        assert response.tool_calls[0].arguments["path"] == "data.json"
        assert "key" in response.tool_calls[0].arguments["content"]
        assert response.tool_calls[0].arguments["options"]["overwrite"] is True

    @pytest.mark.unit
    def test_groq_response_includes_metadata(self, groq_provider, mock_groq_client):
        """Groq response includes proper metadata."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Using tool."
        mock_response.choices[0].message.tool_calls = [
            MagicMock(
                id="call_meta",
                function=MagicMock(name="test", arguments='{}')
            )
        ]
        mock_response.choices[0].finish_reason = "tool_calls"
        mock_response.usage = MagicMock(prompt_tokens=50, completion_tokens=25)

        mock_groq_client.chat.completions.create.return_value = mock_response

        response = groq_provider.chat_with_tools(
            [{"role": "user", "content": "test"}],
            [{"type": "function", "function": {"name": "test"}}]
        )

        assert response.provider == "groq"
        assert response.input_tokens == 50
        assert response.output_tokens == 25
        assert response.tokens_used == 75
        assert "finish_reason" in response.metadata


class TestCerebrasProviderToolCalling:
    """Tests for Cerebras provider native tool calling."""

    @pytest.fixture
    def mock_cerebras_client(self):
        """Create a mock OpenAI client for Cerebras."""
        with patch('src.providers.cerebras_provider.OPENAI_AVAILABLE', True):
            with patch('src.providers.cerebras_provider.OpenAI') as mock_openai:
                mock_client = MagicMock()
                mock_openai.return_value = mock_client
                yield mock_client

    @pytest.fixture
    def cerebras_provider(self, mock_cerebras_client):
        """Create Cerebras provider with mock client."""
        with patch.dict('os.environ', {'CEREBRAS_API_KEY': 'test-key'}):
            from src.providers.cerebras_provider import CerebrasProvider
            provider = CerebrasProvider()
            provider._client = mock_cerebras_client
            return provider

    @pytest.mark.unit
    def test_cerebras_supports_tool_calling_property(self, cerebras_provider):
        """Cerebras provider reports support for tool calling."""
        assert cerebras_provider.supports_tool_calling is True

    @pytest.mark.unit
    def test_cerebras_chat_with_tools_single_call(self, cerebras_provider, mock_cerebras_client):
        """Cerebras returns single tool call from API."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Searching code."

        # Create function mock with proper attributes
        mock_function = MagicMock()
        mock_function.name = "search_code"
        mock_function.arguments = '{"pattern": "def main"}'

        mock_response.choices[0].message.tool_calls = [
            MagicMock(id="call_search", function=mock_function)
        ]
        mock_response.choices[0].finish_reason = "tool_calls"
        mock_response.usage = MagicMock(prompt_tokens=45, completion_tokens=22)

        mock_cerebras_client.chat.completions.create.return_value = mock_response

        response = cerebras_provider.chat_with_tools(
            [{"role": "user", "content": "Find main function"}],
            [{"type": "function", "function": {"name": "search_code"}}]
        )

        assert response.content == "Searching code."
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "search_code"
        assert response.tool_calls[0].arguments == {"pattern": "def main"}

    @pytest.mark.unit
    def test_cerebras_chat_with_tools_no_calls(self, cerebras_provider, mock_cerebras_client):
        """Cerebras returns no tool calls when not needed."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "The answer is 42."
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock(prompt_tokens=30, completion_tokens=10)

        mock_cerebras_client.chat.completions.create.return_value = mock_response

        response = cerebras_provider.chat_with_tools(
            [{"role": "user", "content": "What's the meaning of life?"}],
            [{"type": "function", "function": {"name": "calculator"}}]
        )

        assert response.content == "The answer is 42."
        assert response.tool_calls is None or len(response.tool_calls) == 0

    @pytest.mark.unit
    def test_cerebras_response_includes_provider_info(self, cerebras_provider, mock_cerebras_client):
        """Cerebras response includes proper provider identification."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Done."
        mock_response.choices[0].message.tool_calls = [
            MagicMock(
                id="call_test",
                function=MagicMock(name="test", arguments='{}')
            )
        ]
        mock_response.choices[0].finish_reason = "tool_calls"
        mock_response.usage = MagicMock(prompt_tokens=35, completion_tokens=15)

        mock_cerebras_client.chat.completions.create.return_value = mock_response

        response = cerebras_provider.chat_with_tools(
            [{"role": "user", "content": "test"}],
            [{"type": "function", "function": {"name": "test"}}]
        )

        assert response.provider == "cerebras"
        assert response.model == cerebras_provider.default_model

    @pytest.mark.unit
    def test_cerebras_passes_tools_to_api(self, cerebras_provider, mock_cerebras_client):
        """Cerebras passes tool schemas to the API correctly."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock(prompt_tokens=20, completion_tokens=5)

        mock_cerebras_client.chat.completions.create.return_value = mock_response

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"]
                    }
                }
            }
        ]

        cerebras_provider.chat_with_tools(
            [{"role": "user", "content": "test"}],
            tools
        )

        call_kwargs = mock_cerebras_client.chat.completions.create.call_args.kwargs
        assert "tools" in call_kwargs
        assert call_kwargs["tools"] == tools


class TestProviderToolCallIntegration:
    """Integration tests for provider tool calling with parser."""

    @pytest.mark.unit
    def test_groq_response_works_with_native_parser(self):
        """Groq response can be parsed by NativeToolCallParser."""
        from src.agent.response_parser import NativeToolCallParser
        from src.providers.base import LLMResponse, ToolCall

        # Simulate what Groq would return
        response = LLMResponse(
            content="I need to read the config file to understand the settings.",
            model="llama-3.1-8b-instant",
            provider="groq",
            tokens_used=75,
            input_tokens=50,
            output_tokens=25,
            tool_calls=[
                ToolCall(
                    id="call_groq_123",
                    name="read_file",
                    arguments={"path": "config.json"}
                )
            ]
        )

        parser = NativeToolCallParser()
        result = parser.parse_response(response)

        assert result.action == "read_file"
        assert result.parameters == {"path": "config.json"}
        assert result.thought == "I need to read the config file to understand the settings."
        assert result.is_complete is False

    @pytest.mark.unit
    def test_cerebras_response_works_with_native_parser(self):
        """Cerebras response can be parsed by NativeToolCallParser."""
        from src.agent.response_parser import NativeToolCallParser
        from src.providers.base import LLMResponse, ToolCall

        response = LLMResponse(
            content="Let me search for that pattern.",
            model="llama3.1-8b",
            provider="cerebras",
            tokens_used=60,
            input_tokens=40,
            output_tokens=20,
            tool_calls=[
                ToolCall(
                    id="call_cerebras_456",
                    name="search_code",
                    arguments={"pattern": "class.*Agent"}
                )
            ]
        )

        parser = NativeToolCallParser()
        result = parser.parse_response(response)

        assert result.action == "search_code"
        assert result.parameters == {"pattern": "class.*Agent"}

    @pytest.mark.unit
    def test_no_tool_calls_parsed_as_completion(self):
        """Provider response without tool calls is parsed as completion."""
        from src.agent.response_parser import NativeToolCallParser
        from src.providers.base import LLMResponse

        response = LLMResponse(
            content="Task completed successfully. All files have been created.",
            model="llama-3.1-8b-instant",
            provider="groq",
            tokens_used=50,
            input_tokens=30,
            output_tokens=20,
            tool_calls=None
        )

        parser = NativeToolCallParser()
        result = parser.parse_response(response)

        assert result.is_complete is True
        assert result.action == "complete"
        assert "Task completed" in result.result_text
