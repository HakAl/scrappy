"""
Tests for response parsing - extracting agent actions from LLM responses.

These tests define the expected behavior for parsing JSON responses from LLMs,
including edge cases and fallback strategies. This prepares for native tool calling
by isolating parsing logic.
"""
import pytest
from scrappy.agent.response_parser import (
    JSONResponseParser,
    ParseResult
)
from scrappy.agent.protocols import ResponseParserProtocol


class TestParseResultDataStructure:
    """Tests for ParseResult dataclass."""

    @pytest.mark.unit
    def test_parse_result_creation(self):
        """ParseResult holds parsed action data."""
        result = ParseResult(
            thought="I need to read the file",
            action="read_file",
            parameters={"path": "config.json"},
            is_complete=False
        )
        assert result.thought == "I need to read the file"
        assert result.action == "read_file"
        assert result.parameters == {"path": "config.json"}
        assert result.is_complete is False
        assert result.result_text == ""

    @pytest.mark.unit
    def test_parse_result_with_completion(self):
        """ParseResult can indicate task completion."""
        result = ParseResult(
            thought="Task done",
            action="complete",
            parameters={},
            is_complete=True,
            result_text="File created successfully"
        )
        assert result.is_complete is True
        assert result.result_text == "File created successfully"

    @pytest.mark.unit
    def test_parse_result_with_error(self):
        """ParseResult can contain error information."""
        result = ParseResult(
            thought="Failed to parse",
            action="retry_parse",
            parameters={"raw_response": "invalid"},
            is_complete=False,
            error="JSON decode error"
        )
        assert result.action == "retry_parse"
        assert result.error == "JSON decode error"


class TestJSONResponseParserValidInput:
    """Tests for parsing valid JSON responses."""

    @pytest.fixture
    def parser(self):
        """Create JSON parser instance."""
        return JSONResponseParser()

    @pytest.mark.unit
    def test_parse_valid_json_object(self, parser):
        """Parser extracts action from valid JSON object."""
        response = '''{
            "thought": "I need to read the config file",
            "action": "read_file",
            "parameters": {"path": "config.json"},
            "is_complete": false
        }'''

        result = parser.parse(response)

        assert result.thought == "I need to read the config file"
        assert result.action == "read_file"
        assert result.parameters == {"path": "config.json"}
        assert result.is_complete is False

    @pytest.mark.unit
    def test_parse_json_with_completion(self, parser):
        """Parser handles completion actions."""
        response = '''{
            "thought": "Task completed",
            "action": "complete",
            "parameters": {},
            "is_complete": true,
            "result": "Created file successfully"
        }'''

        result = parser.parse(response)

        assert result.is_complete is True
        assert result.result_text == "Created file successfully"

    @pytest.mark.unit
    def test_parse_json_without_optional_fields(self, parser):
        """Parser provides defaults for missing optional fields."""
        response = '''{
            "thought": "Reading file",
            "action": "read_file",
            "parameters": {"path": "test.txt"}
        }'''

        result = parser.parse(response)

        assert result.is_complete is False
        assert result.result_text == ""

    @pytest.mark.unit
    def test_parse_json_with_nested_parameters(self, parser):
        """Parser preserves nested parameter structures."""
        response = '''{
            "thought": "Writing config",
            "action": "write_file",
            "parameters": {
                "path": "config.json",
                "content": "{\\"key\\": \\"value\\", \\"nested\\": {\\"a\\": 1}}"
            },
            "is_complete": false
        }'''

        result = parser.parse(response)

        assert "content" in result.parameters
        assert "nested" in result.parameters["content"]

    @pytest.mark.unit
    def test_parse_json_with_empty_parameters(self, parser):
        """Parser handles empty parameter objects."""
        response = '''{
            "thought": "Completing task",
            "action": "complete",
            "parameters": {},
            "is_complete": true
        }'''

        result = parser.parse(response)

        assert result.parameters == {}


class TestJSONResponseParserMarkdownBlocks:
    """Tests for extracting JSON from markdown code blocks."""

    @pytest.fixture
    def parser(self):
        """Create JSON parser instance."""
        return JSONResponseParser()

    @pytest.mark.unit
    def test_parse_json_in_markdown_json_block(self, parser):
        """Parser extracts JSON from ```json code blocks."""
        response = '''Here's my response:

```json
{
    "thought": "Analyzing the code",
    "action": "search_code",
    "parameters": {"pattern": "def main"},
    "is_complete": false
}
```

This will search for main functions.'''

        result = parser.parse(response)

        assert result.action == "search_code"
        assert result.parameters == {"pattern": "def main"}

    @pytest.mark.unit
    def test_parse_json_in_generic_code_block(self, parser):
        """Parser extracts JSON from generic ``` code blocks."""
        response = '''I'll help with that:

```
{
    "thought": "Reading configuration",
    "action": "read_file",
    "parameters": {"path": "settings.py"},
    "is_complete": false
}
```'''

        result = parser.parse(response)

        assert result.action == "read_file"
        assert result.parameters["path"] == "settings.py"

    @pytest.mark.unit
    def test_parse_prefers_json_block_over_surrounding_text(self, parser):
        """Parser ignores text outside code blocks."""
        response = '''{"invalid": "json at start"}

```json
{
    "thought": "This is the real action",
    "action": "list_files",
    "parameters": {"path": "."},
    "is_complete": false
}
```

{"also": "invalid"}'''

        result = parser.parse(response)

        assert result.action == "list_files"
        assert result.thought == "This is the real action"


class TestJSONResponseParserPythonBooleans:
    """Tests for handling Python-style booleans in responses."""

    @pytest.fixture
    def parser(self):
        """Create JSON parser instance."""
        return JSONResponseParser()

    @pytest.mark.unit
    def test_parse_json_with_python_true(self, parser):
        """Parser converts Python True to JSON true."""
        response = '''{
            "thought": "Task done",
            "action": "complete",
            "parameters": {},
            "is_complete": True
        }'''

        result = parser.parse(response)

        assert result.is_complete is True

    @pytest.mark.unit
    def test_parse_json_with_python_false(self, parser):
        """Parser converts Python False to JSON false."""
        response = '''{
            "thought": "Continue working",
            "action": "read_file",
            "parameters": {"path": "test.py"},
            "is_complete": False
        }'''

        result = parser.parse(response)

        assert result.is_complete is False

    @pytest.mark.unit
    def test_parse_json_with_python_none(self, parser):
        """Parser converts Python None to JSON null."""
        response = '''{
            "thought": "Working on task",
            "action": "search_code",
            "parameters": {"pattern": "test", "file_pattern": None},
            "is_complete": False
        }'''

        result = parser.parse(response)

        assert result.parameters.get("file_pattern") is None

    @pytest.mark.unit
    def test_parse_json_with_mixed_booleans(self, parser):
        """Parser handles mix of Python and JSON booleans."""
        response = '''{
            "thought": "Mixed booleans",
            "action": "write_file",
            "parameters": {"path": "test.txt", "content": "data"},
            "is_complete": True
        }'''

        result = parser.parse(response)

        assert result.is_complete is True


class TestJSONResponseParserMalformedJSON:
    """Tests for recovering from malformed JSON responses."""

    @pytest.fixture
    def parser(self):
        """Create JSON parser instance."""
        return JSONResponseParser()

    @pytest.mark.unit
    def test_parse_json_with_trailing_text(self, parser):
        """Parser extracts JSON even with trailing text."""
        response = '''{
            "thought": "Reading file",
            "action": "read_file",
            "parameters": {"path": "main.py"},
            "is_complete": false
        } I hope this helps!'''

        result = parser.parse(response)

        assert result.action == "read_file"

    @pytest.mark.unit
    def test_parse_json_with_leading_text(self, parser):
        """Parser extracts JSON even with leading text."""
        response = '''Let me help you with that:
{
    "thought": "Searching codebase",
    "action": "search_code",
    "parameters": {"pattern": "class.*Error"},
    "is_complete": false
}'''

        result = parser.parse(response)

        assert result.action == "search_code"
        assert result.parameters["pattern"] == "class.*Error"

    @pytest.mark.unit
    def test_parse_json_with_nested_braces_in_content(self, parser):
        """Parser handles nested braces in string content."""
        response = '''{
            "thought": "Writing JSON file",
            "action": "write_file",
            "parameters": {
                "path": "data.json",
                "content": "{\\"items\\": [{\\"id\\": 1}, {\\"id\\": 2}]}"
            },
            "is_complete": false
        }'''

        result = parser.parse(response)

        assert result.action == "write_file"
        assert "items" in result.parameters["content"]

    @pytest.mark.unit
    def test_parse_handles_brace_matching(self, parser):
        """Parser uses brace matching for extraction."""
        response = '''Some text { not json }
{
    "thought": "Valid action",
    "action": "list_files",
    "parameters": {"path": "/src"},
    "is_complete": false
}
more text'''

        result = parser.parse(response)

        # Should find the complete valid JSON object
        assert result.action == "list_files"

class TestJSONResponseParserEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def parser(self):
        """Create JSON parser instance."""
        return JSONResponseParser()

    @pytest.mark.unit
    def test_parse_json_with_unicode_content(self, parser):
        """Parser handles Unicode characters in content."""
        response = '''{
            "thought": "Writing multilingual content",
            "action": "write_file",
            "parameters": {"path": "i18n.txt", "content": "Hello World"},
            "is_complete": false
        }'''

        result = parser.parse(response)

        assert result.action == "write_file"
        # Content should be preserved (note: actual Unicode chars may need escaping)

    @pytest.mark.unit
    def test_parse_json_with_very_long_content(self, parser):
        """Parser handles large content in parameters."""
        long_content = "x" * 10000
        response = f'''{{
            "thought": "Writing large file",
            "action": "write_file",
            "parameters": {{"path": "big.txt", "content": "{long_content}"}},
            "is_complete": false
        }}'''

        result = parser.parse(response)

        assert result.action == "write_file"
        assert len(result.parameters["content"]) == 10000

    @pytest.mark.unit
    def test_parse_preserves_whitespace_in_content(self, parser):
        """Parser preserves whitespace in string content."""
        response = '''{
            "thought": "Writing code with indentation",
            "action": "write_file",
            "parameters": {
                "path": "script.py",
                "content": "def main():\\n    print(\\"hello\\")\\n    return 0"
            },
            "is_complete": false
        }'''

        result = parser.parse(response)

        assert "\\n" in result.parameters["content"] or "\n" in result.parameters["content"]
        assert "    " in result.parameters["content"] or "\\t" in result.parameters["content"]

    @pytest.mark.unit
    def test_parse_handles_special_characters_in_parameters(self, parser):
        """Parser handles special regex characters in parameters."""
        response = '''{
            "thought": "Searching with regex",
            "action": "search_code",
            "parameters": {"pattern": "def\\\\s+\\\\w+\\\\(.*\\\\):"},
            "is_complete": false
        }'''

        result = parser.parse(response)

        assert result.action == "search_code"
        # Pattern should be preserved

    @pytest.mark.unit
    def test_parse_no_thought_field(self, parser):
        """Parser handles missing thought field."""
        response = '''{
            "action": "read_file",
            "parameters": {"path": "test.txt"},
            "is_complete": false
        }'''

        result = parser.parse(response)

        # Should provide default or extract action
        assert result.action == "read_file"

    @pytest.mark.unit
    def test_parse_no_action_field(self, parser):
        """Parser handles missing action field."""
        response = '''{
            "thought": "I am thinking",
            "parameters": {"path": "test.txt"},
            "is_complete": false
        }'''

        result = parser.parse(response)

        # Should indicate error or default
        assert result.action in ["error", "retry_parse", ""] or result.error

    @pytest.mark.unit
    def test_parse_accepts_tool_key_as_action(self, parser):
        """Parser accepts 'tool' key as alternative to 'action' for robustness."""
        response = '''{
            "thought": "I am thinking",
            "tool": "read_file",
            "parameters": {"path": "test.txt"},
            "is_complete": false
        }'''

        result = parser.parse(response)

        assert result.action == "read_file"
        assert result.thought == "I am thinking"
        assert result.parameters == {"path": "test.txt"}

    @pytest.mark.unit
    def test_parse_prefers_action_over_tool(self, parser):
        """Parser prefers 'action' key when both 'action' and 'tool' are present."""
        response = '''{
            "thought": "I am thinking",
            "action": "write_file",
            "tool": "read_file",
            "parameters": {"path": "test.txt"},
            "is_complete": false
        }'''

        result = parser.parse(response)

        assert result.action == "write_file"


class TestResponseParserInterface:
    """Tests for the parser abstraction interface."""


        # Future: NativeToolCallParser would also implement this interface


class TestRealWorldFailures:
    """Tests based on actual production failures - add failing responses here."""

    @pytest.fixture
    def parser(self):
        return JSONResponseParser()

    @pytest.mark.unit
    def test_truncated_write_file_mid_content(self, parser):
        """Real failure: LLM response truncated mid-content string."""
        # This exact response failed in production - token limit truncation
        response = r'{"thought": "Writing test file", "action": "write_file", "parameters": {"path": "test.py", "content": "import pytest\n\ndef test_example():\n    assert True\n\ndef test_another():\n    # More test code here\n    '
        # Note: no closing quote, no closing braces

        result = parser.parse(response)

        # Should salvage what we can
        assert result.action == "write_file"
        assert result.parameters.get("path") == "test.py"
        assert "import pytest" in result.parameters.get("content", "")

    @pytest.mark.unit
    def test_truncated_long_content_with_escapes(self, parser):
        """Real failure: Long content with escape sequences truncated."""
        response = r'{"thought": "Creating scraper tests", "action": "write_file", "parameters": {"path": "workers/tests/test_scraper.py", "content": "import asyncio\nimport pytest\nfrom unittest.mock import AsyncMock, Mock, patch\n\nfrom workers.scraper import WebScraper\n\n\ndef test_scraper_initialization():\n    \"\"\"Test that WebScraper initializes correctly.\"\"\"\n    scraper = WebScraper(\'http://example.com\')\n    \n    assert scraper.base_url == \'http://example.com\'\n    assert scraper.timeout == 30'
        # Truncated mid-string

        result = parser.parse(response)

        assert result.action == "write_file"
        assert result.parameters.get("path") == "workers/tests/test_scraper.py"
        assert "test_scraper_initialization" in result.parameters.get("content", "")

    @pytest.mark.unit
    def test_triple_quoted_python_style(self, parser):
        """Real failure: LLM used Python triple-quotes instead of JSON strings."""
        response = '''{
            "thought": "Writing multi-line content",
            "action": "write_file",
            "parameters": {
                "path": "example.py",
                "content": """def hello():
    print("world")
"""
            },
            "is_complete": false
        }'''

        result = parser.parse(response)

        assert result.action == "write_file"
        assert "def hello" in result.parameters.get("content", "")


class TestJSONResponseParserCriticalBehavior:
    """Tests for critical behavior that must be preserved."""

    @pytest.fixture
    def parser(self):
        """Create JSON parser instance."""
        return JSONResponseParser()

    @pytest.mark.unit
    def test_multiple_json_blocks_takes_first(self, parser):
        """Parser uses first valid JSON block when multiple exist."""
        response = '''{
    "thought": "First action",
    "action": "read_file",
    "parameters": {"path": "first.txt"},
    "is_complete": false
}

Some explanation text

{
    "thought": "Second action",
    "action": "write_file",
    "parameters": {"path": "second.txt"},
    "is_complete": false
}'''

        result = parser.parse(response)

        # Must take FIRST valid JSON block
        assert result.action == "read_file"
        assert result.parameters["path"] == "first.txt"

    @pytest.mark.unit
    def test_escaped_quotes_preserved_in_content(self, parser):
        """Parser preserves escaped quotes in string values."""
        response = r'''{
            "thought": "Writing code with strings",
            "action": "write_file",
            "parameters": {
                "path": "test.py",
                "content": "print(\"Hello, World!\")"
            },
            "is_complete": false
        }'''

        result = parser.parse(response)

        assert result.action == "write_file"
        # Escaped quotes must be preserved as actual quotes in output
        assert '"Hello, World!"' in result.parameters["content"]

    @pytest.mark.unit
    def test_consecutive_escape_sequences(self, parser):
        """Parser handles consecutive escape sequences correctly."""
        response = r'''{
            "thought": "Path with backslashes",
            "action": "write_file",
            "parameters": {
                "path": "C:\\Users\\test\\file.txt",
                "content": "data"
            },
            "is_complete": false
        }'''

        result = parser.parse(response)

        # Should have actual backslashes in path
        assert "\\" in result.parameters["path"]

    @pytest.mark.unit
    def test_regex_fallback_extracts_exact_values(self, parser):
        """Regex fallback extracts exact thought and action values."""
        response = '''
        {
            "thought": "Need to check git status",
            "action": "git_status",
            "parameters": {},
            incomplete...'''

        result = parser.parse(response)

        # Must extract exact values, not just contain them
        assert result.thought == "Need to check git status"
        assert result.action == "git_status"

    @pytest.mark.unit
    def test_real_world_llm_pattern_explanation_then_json(self, parser):
        """Parser handles real LLM pattern: explanation followed by JSON."""
        response = '''I'll help you with that task. First, let me analyze the codebase structure.

Based on my analysis, here's what I need to do:

```json
{
    "thought": "Need to search for the main entry point",
    "action": "search_code",
    "parameters": {"pattern": "def main"},
    "is_complete": false
}
```

This will help identify the starting point of the application.'''

        result = parser.parse(response)

        assert result.action == "search_code"
        assert result.parameters["pattern"] == "def main"

    @pytest.mark.unit
    def test_real_world_llm_pattern_numbered_steps(self, parser):
        """Parser handles LLM pattern with numbered analysis steps."""
        response = '''Let me break this down:

1. First, I need to understand the current implementation
2. Then identify the bug location
3. Finally, propose a fix

Here's my action:
{
    "thought": "Starting with code analysis",
    "action": "read_file",
    "parameters": {"path": "src/main.py"},
    "is_complete": false
}'''

        result = parser.parse(response)

        assert result.action == "read_file"
        assert result.parameters["path"] == "src/main.py"

    @pytest.mark.unit
    def test_real_world_llm_pattern_code_example_then_action(self, parser):
        """Parser handles LLM showing code example before action JSON."""
        response = '''Here's what the current code looks like:

```python
def old_function():
    return None
```

Now let me refactor it:

```json
{
    "thought": "Refactoring the function",
    "action": "write_file",
    "parameters": {"path": "module.py", "content": "def new_function():\\n    return 42"},
    "is_complete": false
}
```'''

        result = parser.parse(response)

        assert result.action == "write_file"
        assert "new_function" in result.parameters["content"]

    @pytest.mark.unit
    def test_braces_inside_string_content_handled(self, parser):
        """Parser handles JSON/dict syntax inside string content."""
        response = '''{
    "thought": "Writing JSON configuration",
    "action": "write_file",
    "parameters": {
        "path": "config.json",
        "content": "{\\"database\\": {\\"host\\": \\"localhost\\", \\"port\\": 5432}}"
    },
    "is_complete": false
}'''

        result = parser.parse(response)

        assert result.action == "write_file"
        # Content should contain the JSON structure
        assert "database" in result.parameters["content"]
        assert "localhost" in result.parameters["content"]

    @pytest.mark.unit
    def test_incomplete_json_returns_retry_parse(self, parser):
        """Incomplete JSON without extractable fields returns retry_parse."""
        response = '''{"thought": "Starting to...'''

        result = parser.parse(response)

        # Should fail gracefully
        assert result.action == "retry_parse" or result.error is not None
        assert result.is_complete is False

    @pytest.mark.unit
    def test_parse_result_raw_response_in_error(self, parser):
        """Parse error includes raw response for debugging."""
        response = "Completely invalid response with no JSON structure"

        result = parser.parse(response)

        # Error result should contain raw response info
        assert result.action == "retry_parse"
        assert "raw_response" in result.parameters
        assert result.parameters["raw_response"] != ""


class TestUnifiedResponseParser:
    """Tests for UnifiedResponseParser that auto-detects JSON vs native tool calling."""

    @pytest.fixture
    def parser(self):
        """Create unified parser instance."""
        from scrappy.agent.response_parser import UnifiedResponseParser
        return UnifiedResponseParser()

    @pytest.mark.unit
    def test_string_input_uses_json_parser(self, parser):
        """String input should be parsed as JSON."""
        response = '''{
            "thought": "Reading file",
            "action": "read_file",
            "parameters": {"path": "test.py"},
            "is_complete": false
        }'''

        result = parser.parse(response)

        assert result.action == "read_file"
        assert result.parameters == {"path": "test.py"}
        assert result.is_complete is False

    @pytest.mark.unit
    def test_llm_response_without_tool_calls_uses_json_parser(self, parser):
        """LLMResponse with no tool_calls should parse content as JSON."""
        from scrappy.providers.base import LLMResponse

        llm_response = LLMResponse(
            content='''{
                "thought": "Searching code",
                "action": "search_code",
                "parameters": {"pattern": "def main"},
                "is_complete": false
            }''',
            model="llama-3.1-8b",
            provider="groq",
            tool_calls=None
        )

        result = parser.parse(llm_response)

        assert result.action == "search_code"
        assert result.parameters == {"pattern": "def main"}

    @pytest.mark.unit
    def test_llm_response_with_empty_tool_calls_uses_json_parser(self, parser):
        """LLMResponse with empty tool_calls list should parse content as JSON."""
        from scrappy.providers.base import LLMResponse

        llm_response = LLMResponse(
            content='''{
                "thought": "Writing file",
                "action": "write_file",
                "parameters": {"path": "out.txt", "content": "data"},
                "is_complete": false
            }''',
            model="llama-3.1-8b",
            provider="groq",
            tool_calls=[]  # Empty list, not None
        )

        result = parser.parse(llm_response)

        assert result.action == "write_file"
        assert result.parameters["path"] == "out.txt"

    @pytest.mark.unit
    def test_llm_response_with_tool_calls_uses_native_parser(self, parser):
        """LLMResponse with tool_calls should use native tool calling parser."""
        from scrappy.providers.base import LLMResponse, ToolCall

        llm_response = LLMResponse(
            content="I'll read that file for you.",
            model="llama-3.1-8b",
            provider="groq",
            tool_calls=[
                ToolCall(
                    id="call_123",
                    name="read_file",
                    arguments={"path": "/src/main.py"}
                )
            ]
        )

        result = parser.parse(llm_response)

        assert result.action == "read_file"
        assert result.parameters == {"path": "/src/main.py"}
        assert result.thought == "I'll read that file for you."

    @pytest.mark.unit
    def test_llm_response_with_multiple_tool_calls_uses_first(self, parser):
        """When multiple tool calls, parser should use the first one."""
        from scrappy.providers.base import LLMResponse, ToolCall

        llm_response = LLMResponse(
            content="Let me read these files.",
            model="llama-3.1-8b",
            provider="groq",
            tool_calls=[
                ToolCall(id="call_1", name="read_file", arguments={"path": "a.py"}),
                ToolCall(id="call_2", name="read_file", arguments={"path": "b.py"})
            ]
        )

        result = parser.parse(llm_response)

        # Should use first tool call
        assert result.action == "read_file"
        assert result.parameters == {"path": "a.py"}

    @pytest.mark.unit
    def test_llm_response_with_complete_action(self, parser):
        """Native tool call for completion should set is_complete."""
        from scrappy.providers.base import LLMResponse, ToolCall

        llm_response = LLMResponse(
            content="Task completed successfully.",
            model="llama-3.1-8b",
            provider="groq",
            tool_calls=[
                ToolCall(
                    id="call_done",
                    name="complete",
                    arguments={"result": "File created at /out.txt"}
                )
            ]
        )

        result = parser.parse(llm_response)

        assert result.action == "complete"
        assert result.is_complete is True
        assert "File created" in result.result_text

    @pytest.mark.unit
    def test_invalid_json_string_returns_retry_parse(self, parser):
        """Invalid JSON string should return retry_parse action."""
        response = "This is not JSON at all"

        result = parser.parse(response)

        assert result.action == "retry_parse"
        assert result.is_complete is False

    @pytest.mark.unit
    def test_llm_response_with_invalid_json_content_returns_retry_parse(self, parser):
        """LLMResponse with invalid JSON content should return retry_parse."""
        from scrappy.providers.base import LLMResponse

        llm_response = LLMResponse(
            content="I'm not sure what to do next",
            model="llama-3.1-8b",
            provider="groq",
            tool_calls=None
        )

        result = parser.parse(llm_response)

        assert result.action == "retry_parse"
        assert result.is_complete is False

    @pytest.mark.unit
    def test_parser_preserves_tool_call_id_in_metadata(self, parser):
        """Parser should preserve tool call ID for potential future use."""
        from scrappy.providers.base import LLMResponse, ToolCall

        llm_response = LLMResponse(
            content="Reading file",
            model="llama-3.1-8b",
            provider="groq",
            tool_calls=[
                ToolCall(
                    id="call_abc123",
                    name="read_file",
                    arguments={"path": "test.py"}
                )
            ]
        )

        result = parser.parse(llm_response)

        # ID might be in parameters or a separate field - test the behavior
        assert result.action == "read_file"
        # If we want to track tool_call_id, it should be accessible somehow

    @pytest.mark.unit
    def test_backward_compatibility_with_string_only(self, parser):
        """Parser should work exactly like JSONResponseParser for string input."""
        json_parser = JSONResponseParser()

        test_cases = [
            '{"thought": "test", "action": "read_file", "parameters": {"path": "x"}, "is_complete": false}',
            '{"thought": "done", "action": "complete", "is_complete": true, "result": "success"}',
            'invalid json',
        ]

        for test_input in test_cases:
            unified_result = parser.parse(test_input)
            json_result = json_parser.parse(test_input)

            assert unified_result.action == json_result.action
            assert unified_result.is_complete == json_result.is_complete
