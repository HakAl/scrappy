"""
Response parsing for LLM agent responses.

Abstracts the parsing of LLM responses into structured actions,
supporting both JSON text parsing and future native tool calling.
"""

import json
import re
from abc import ABC, abstractmethod
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


class ResponseParser(ABC):
    """Abstract base class for parsing LLM responses into actions."""

    @abstractmethod
    def parse(self, response_text: str) -> ParseResult:
        """
        Parse an LLM response into a structured action.

        Args:
            response_text: Raw text response from the LLM

        Returns:
            ParseResult containing the parsed action details
        """
        pass


class JSONResponseParser(ResponseParser):
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

        result = self._try_brace_matching(text)
        if result:
            return result

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
        """Extract JSON from markdown code blocks."""
        # Handle ```json blocks
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()

        # Handle generic ``` blocks
        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()

        return text

    def _fix_python_booleans(self, text: str) -> str:
        """Convert Python-style booleans to JSON format."""
        # Replace Python booleans with JSON booleans
        text = re.sub(r'\bTrue\b', 'true', text)
        text = re.sub(r'\bFalse\b', 'false', text)
        text = re.sub(r'\bNone\b', 'null', text)
        return text

    def _try_direct_parse(self, text: str) -> Optional[ParseResult]:
        """Try parsing text directly as JSON."""
        try:
            data = json.loads(text)
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
        """Extract fields using regex as last resort."""
        thought_match = re.search(r'"thought"\s*:\s*"([^"]+)"', text)
        action_match = re.search(r'"action"\s*:\s*"([^"]+)"', text)

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

    def _dict_to_result(self, data: dict) -> ParseResult:
        """Convert parsed dictionary to ParseResult."""
        return ParseResult(
            thought=data.get("thought", "No thought provided"),
            action=data.get("action", "error"),
            parameters=data.get("parameters", {}),
            is_complete=data.get("is_complete", False),
            result_text=data.get("result", "")
        )


class NativeToolCallParser(ResponseParser):
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


class UnifiedResponseParser(ResponseParser):
    """
    Parser that auto-detects between JSON text and native tool calling.

    This parser handles both:
    - String input (JSON text) - uses JSONResponseParser
    - LLMResponse objects - checks for tool_calls and routes appropriately

    This allows the agent to work with both old JSON-based responses and
    modern native tool calling without changing the agent loop.
    """

    def __init__(self):
        """Initialize with both parser types."""
        self._json_parser = JSONResponseParser()
        self._native_parser = NativeToolCallParser()

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
            # Check if it has tool_calls
            if response.tool_calls and len(response.tool_calls) > 0:
                # Use native tool calling parser
                return self._native_parser.parse_response(response)
            else:
                # No tool_calls, parse content as JSON
                return self._json_parser.parse(response.content)
        else:
            # String input - use JSON parser
            return self._json_parser.parse(response)
