"""
Response parsing for LLM agent responses.

Abstracts the parsing of LLM responses into structured actions,
supporting both JSON text parsing and native tool calling.

All parsers implement the ResponseParserProtocol from protocols.py.
"""

import json
import re
from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class ParseResult:
    """Result of parsing an LLM response into an action."""
    thought: str
    action: str
    parameters: Dict[str, Any]
    is_complete: bool
    result_text: str = ""
    error: Optional[str] = None


class JSONResponseParser:
    """
    Parser for JSON-formatted LLM responses.

    Handles various edge cases including:
    - Markdown code blocks (```json and ```)
    - Python-style booleans (True/False/None)
    - Malformed JSON with fallback strategies
    - Regex-based field extraction as last resort
    """

    def parse(self, response_text: str) -> ParseResult:
        """Parse JSON response with robust error handling."""
        text = response_text.strip()

        if not text:
            return ParseResult(
                thought="Failed to parse: empty response",
                action="retry_parse",
                parameters={"raw_response": ""},
                is_complete=False,
                error="Empty response"
            )

        # Extract JSON from markdown code blocks
        text = self._extract_from_markdown(text)

        # Try parsing with progressively more lenient strategies
        result = self._try_direct_parse(text)
        if result:
            return result

        result = self._try_python_bool_conversion(text)
        if result:
            return result

        # Try fixing triple-quoted strings (LLMs sometimes use Python syntax)
        result = self._try_triple_quote_fix(text)
        if result:
            return result

        result = self._try_brace_matching(text)
        if result:
            return result

        # Try to salvage truncated JSON (LLM hit token limit mid-response)
        # This handles write_file with partial content better than regex
        result = self._try_truncated_json(text)
        if result:
            return result

        # Last resort: regex extraction for minimal fields
        result = self._try_regex_extraction(text)
        if result:
            return result

        # All strategies failed
        return ParseResult(
            thought="Failed to parse LLM response as JSON",
            action="retry_parse",
            parameters={"raw_response": response_text[:500]},
            is_complete=False,
            error=f"Parse error: {response_text[:200]}"
        )

    def _extract_from_markdown(self, text: str) -> str:
        """Extract JSON from markdown code blocks.

        Handles:
        - Complete code blocks: ```json ... ```
        - Truncated code blocks: ```json ... (no closing ```)
        - Generic code blocks: ``` ... ```
        """
        # Handle ```json blocks
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()
            else:
                # Truncated response - no closing ```, extract everything after ```json
                return text[start:].strip()

        # Handle generic ``` blocks
        if "```" in text:
            start = text.find("```") + 3
            # Skip language identifier if present (e.g., ```javascript)
            newline_pos = text.find("\n", start)
            if newline_pos != -1 and newline_pos < start + 20:
                # Language identifier likely present, skip to newline
                start = newline_pos + 1
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()
            else:
                # Truncated response - extract everything after opening
                return text[start:].strip()

        return text

    def _fix_python_booleans(self, text: str) -> str:
        """Convert Python-style booleans to JSON format."""
        # Replace Python booleans with JSON booleans
        text = re.sub(r'\bTrue\b', 'true', text)
        text = re.sub(r'\bFalse\b', 'false', text)
        text = re.sub(r'\bNone\b', 'null', text)
        return text

    def _fix_triple_quotes(self, text: str) -> str:
        """Convert Python-style triple-quoted strings to JSON strings.

        Handles LLMs that output:
            "content": \"\"\"
            multi-line content
            \"\"\"

        Converts to proper JSON:
            "content": "multi-line content\\n..."
        """
        # Pattern: find triple quotes (""" or ''')
        # We need to find pairs and convert the content between them
        result = text

        # Handle """ triple quotes
        while '"""' in result:
            start = result.find('"""')
            if start == -1:
                break

            # Find closing """
            end = result.find('"""', start + 3)
            if end == -1:
                # No closing triple quote - treat rest as content
                content = result[start + 3:]
                # Escape for JSON
                escaped = self._escape_for_json(content)
                result = result[:start] + '"' + escaped + '"'
                break

            # Extract content between triple quotes
            content = result[start + 3:end]
            # Escape for JSON
            escaped = self._escape_for_json(content)
            # Replace triple-quoted section with proper JSON string
            result = result[:start] + '"' + escaped + '"' + result[end + 3:]

        # Handle ''' triple quotes (less common but possible)
        while "'''" in result:
            start = result.find("'''")
            if start == -1:
                break

            end = result.find("'''", start + 3)
            if end == -1:
                content = result[start + 3:]
                escaped = self._escape_for_json(content)
                result = result[:start] + '"' + escaped + '"'
                break

            content = result[start + 3:end]
            escaped = self._escape_for_json(content)
            result = result[:start] + '"' + escaped + '"' + result[end + 3:]

        return result

    def _escape_for_json(self, content: str) -> str:
        """Escape a string for use in JSON."""
        # Escape backslashes first
        content = content.replace('\\', '\\\\')
        # Escape double quotes
        content = content.replace('"', '\\"')
        # Escape newlines
        content = content.replace('\n', '\\n')
        # Escape carriage returns
        content = content.replace('\r', '\\r')
        # Escape tabs
        content = content.replace('\t', '\\t')
        return content

    def _try_direct_parse(self, text: str) -> Optional[ParseResult]:
        """Try parsing text directly as JSON."""
        try:
            data = json.loads(text)
            return self._dict_to_result(data)
        except json.JSONDecodeError:
            return None

    def _try_triple_quote_fix(self, text: str) -> Optional[ParseResult]:
        """Try parsing after fixing triple-quoted strings."""
        # Only try if triple quotes are present
        if '"""' not in text and "'''" not in text:
            return None

        try:
            fixed_text = self._fix_triple_quotes(text)
            fixed_text = self._fix_python_booleans(fixed_text)
            data = json.loads(fixed_text)
            return self._dict_to_result(data)
        except json.JSONDecodeError:
            return None

    def _try_python_bool_conversion(self, text: str) -> Optional[ParseResult]:
        """Try parsing after converting Python booleans."""
        try:
            fixed_text = self._fix_python_booleans(text)
            data = json.loads(fixed_text)
            return self._dict_to_result(data)
        except json.JSONDecodeError:
            return None

    def _try_brace_matching(self, text: str) -> Optional[ParseResult]:
        """Try to find and parse JSON object using brace matching."""
        try:
            start = text.find("{")
            if start == -1:
                return None

            brace_count = 0
            end = start
            in_string = False
            escape_next = False

            for i in range(start, len(text)):
                char = text[i]

                if escape_next:
                    escape_next = False
                    continue

                if char == "\\":
                    escape_next = True
                    continue

                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue

                if not in_string:
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            end = i + 1
                            break

            if end > start:
                json_str = self._fix_python_booleans(text[start:end])
                data = json.loads(json_str)
                return self._dict_to_result(data)

        except (json.JSONDecodeError, IndexError):
            pass

        return None

    def _try_regex_extraction(self, text: str) -> Optional[ParseResult]:
        """Extract fields using regex as last resort.

        Accepts both "action" and "tool" keys for robustness.
        """
        thought_match = re.search(r'"thought"\s*:\s*"([^"]+)"', text)
        action_match = re.search(r'"action"\s*:\s*"([^"]+)"', text)
        if not action_match:
            action_match = re.search(r'"tool"\s*:\s*"([^"]+)"', text)

        if thought_match and action_match:
            result = ParseResult(
                thought=thought_match.group(1),
                action=action_match.group(1),
                parameters={},
                is_complete=False
            )

            # Try to extract parameters
            params_match = re.search(r'"parameters"\s*:\s*(\{[^}]+\})', text)
            if params_match:
                try:
                    params_str = self._fix_python_booleans(params_match.group(1))
                    result.parameters = json.loads(params_str)
                except Exception:
                    pass

            # Check for is_complete
            if re.search(r'"is_complete"\s*:\s*true', text, re.IGNORECASE):
                result.is_complete = True

            return result

        return None

    def _try_truncated_json(self, text: str) -> Optional[ParseResult]:
        """Try to salvage a truncated JSON response.

        When LLM hits token limit mid-response, we can often still extract
        the thought, action, and partial parameters. This is especially
        useful for write_file actions where content may be cut off.
        """
        # Must have opening brace and look like JSON
        if '{' not in text:
            return None

        # Extract thought using regex (handles escaped quotes)
        thought_match = re.search(r'"thought"\s*:\s*"((?:[^"\\]|\\.)*)(?:"|$)', text)
        thought = thought_match.group(1) if thought_match else "Truncated response"

        # Unescape the thought string
        if thought_match:
            thought = thought.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')

        # Extract action
        action_match = re.search(r'"action"\s*:\s*"([^"]+)"', text)
        if not action_match:
            action_match = re.search(r'"tool"\s*:\s*"([^"]+)"', text)

        if not action_match:
            return None  # Can't determine action

        action = action_match.group(1)

        # Try to extract parameters
        parameters = {}

        # For write_file, extract path and partial content
        if action == 'write_file':
            path_match = re.search(r'"path"\s*:\s*"([^"]+)"', text)
            if path_match:
                parameters['path'] = path_match.group(1)

            # Extract content - may be truncated
            content_match = re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)', text)
            if content_match:
                content = content_match.group(1)
                # Unescape the content
                content = content.replace('\\n', '\n').replace('\\t', '\t')
                content = content.replace('\\"', '"').replace('\\\\', '\\')
                parameters['content'] = content
                parameters['_truncated'] = True  # Mark as truncated

        # For other actions, try to extract simple parameters
        else:
            # Look for simple string parameters
            param_pattern = r'"(\w+)"\s*:\s*"([^"]*)"'
            for match in re.finditer(param_pattern, text):
                key, value = match.groups()
                if key not in ('thought', 'action', 'tool', 'is_complete'):
                    parameters[key] = value

        return ParseResult(
            thought=thought,
            action=action,
            parameters=parameters,
            is_complete=False,
            error="Response JSON incomplete (truncated mid-string)"
        )

    def _dict_to_result(self, data: dict) -> ParseResult:
        """Convert parsed dictionary to ParseResult.

        Accepts both "action" and "tool" keys for robustness since LLMs
        may use either format regardless of prompt instructions.
        """
        return ParseResult(
            thought=data.get("thought", "No thought provided"),
            action=data.get("action") or data.get("tool", "error"),
            parameters=data.get("parameters", {}),
            is_complete=data.get("is_complete", False),
            result_text=data.get("result", "")
        )


class NativeToolCallParser:
    """
    Parser for native tool calling responses.

    This parser handles LLMResponse objects that contain tool_calls directly,
    rather than parsing JSON text from the response content. This is the modern
    approach used by OpenAI, Groq, and other providers that support function calling.
    """

    def parse(self, response_text: str) -> ParseResult:
        """
        Parse text response (legacy interface).

        NativeToolCallParser expects LLMResponse objects, not text.
        This method provides backward compatibility but indicates that
        native tool calling is expected.

        Args:
            response_text: Raw text response (not expected for native tool calling)

        Returns:
            ParseResult indicating that native tool calling is expected
        """
        return ParseResult(
            thought="NativeToolCallParser expects LLMResponse with tool_calls, not text",
            action="retry_parse",
            parameters={"raw_response": response_text[:500] if response_text else ""},
            is_complete=False,
            error="Native tool call parser received text instead of LLMResponse. "
                  "Use parse_response() with LLMResponse object instead."
        )

    def parse_response(self, response) -> ParseResult:
        """
        Parse an LLMResponse with native tool calls.

        This is the primary method for parsing responses from providers that
        support native tool calling.

        Args:
            response: LLMResponse object with tool_calls field

        Returns:
            ParseResult containing the parsed action details
        """
        # Handle None or empty tool_calls as completion
        if response.tool_calls is None or len(response.tool_calls) == 0:
            # No tool calls means the model is done or responding without tools
            return ParseResult(
                thought=response.content,
                action="complete",
                parameters={},
                is_complete=True,
                result_text=response.content
            )

        # Use the first tool call (most common case)
        tool_call = response.tool_calls[0]

        # Handle "complete" action specially
        is_complete = tool_call.name == "complete"
        result_text = ""
        if is_complete:
            result_text = tool_call.arguments.get("result", response.content)

        return ParseResult(
            thought=response.content,  # LLM's explanation/reasoning
            action=tool_call.name,     # Tool to execute
            parameters=tool_call.arguments,  # Tool parameters
            is_complete=is_complete,
            result_text=result_text
        )


class UnifiedResponseParser:
    """
    Parser that auto-detects between JSON text and native tool calling.

    This parser handles both:
    - String input (JSON text) - uses JSONResponseParser
    - LLMResponse objects - checks for tool_calls and routes appropriately

    This allows the agent to work with both old JSON-based responses and
    modern native tool calling without changing the agent loop.
    """

    def __init__(
        self,
        json_parser: Optional[JSONResponseParser] = None,
        native_parser: Optional['NativeToolCallParser'] = None
    ):
        """
        Initialize with both parser types.

        Args:
            json_parser: Injectable JSON parser (default: creates new JSONResponseParser)
            native_parser: Injectable native tool call parser (default: creates new NativeToolCallParser)
        """
        self._json_parser = json_parser or self._create_default_json_parser()
        self._native_parser = native_parser or self._create_default_native_parser()

    def _create_default_json_parser(self) -> JSONResponseParser:
        """Create default JSON response parser."""
        return JSONResponseParser()

    def _create_default_native_parser(self) -> 'NativeToolCallParser':
        """Create default native tool call parser."""
        return NativeToolCallParser()

    def parse(self, response) -> ParseResult:
        """
        Parse response, auto-detecting the format.

        Args:
            response: Either a string (JSON text) or LLMResponse object

        Returns:
            ParseResult containing the parsed action details
        """
        # Import here to avoid circular dependency
        from ..providers.base import LLMResponse

        # Check if it's an LLMResponse object
        if isinstance(response, LLMResponse):
            # Check if it has tool_calls with actual calls (not None, not empty)
            if response.tool_calls is not None and len(response.tool_calls) > 0:
                # Use native tool calling parser
                return self._native_parser.parse_response(response)
            else:
                # No tool_calls or empty list - parse content as JSON
                return self._json_parser.parse(response.content)
        else:
            # String input - use JSON parser
            return self._json_parser.parse(response)
