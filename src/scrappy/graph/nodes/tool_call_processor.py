"""
Tool call format conversion and streaming accumulation.

Single responsibility: Handle tool call format differences between
LLM provider responses and OpenAI-format state representation.
"""

import json
import re
from typing import Protocol, runtime_checkable

from scrappy.graph.state import ToolCall
from scrappy.infrastructure.logging import get_logger
from scrappy.orchestrator.types import ToolCallFragment

logger = get_logger(__name__)


_TEXT_FUNCTION_END = "</function>"
_TEXT_FUNCTION_START_PATTERNS = (
    (
        re.compile(r"<function\(\s*([A-Za-z_][\w-]*)\s+", re.DOTALL),
        ")>",
    ),
    (
        re.compile(r"<function=([A-Za-z_][\w-]*)>\s*", re.DOTALL),
        "",
    ),
)
_JSON_DECODER = json.JSONDecoder()


@runtime_checkable
class ToolCallProcessorProtocol(Protocol):
    """Protocol for tool call processing implementations."""

    def convert(self, response_tool_calls: list | None) -> list[ToolCall]:
        """Convert tool calls from LLM response format to OpenAI format."""
        ...

    def accumulate(self, fragments: list[ToolCallFragment]) -> dict[int, dict]:
        """Accumulate streaming fragments by index."""
        ...

    def fragments_to_calls(self, accumulated: dict[int, dict]) -> list[ToolCall]:
        """Convert accumulated fragments to ToolCall list."""
        ...

    def extract_text_tool_calls(self, content: str) -> tuple[str, list[ToolCall]]:
        """Extract provider-rendered textual tool calls from assistant content."""
        ...


class ToolCallProcessor:
    """
    Converts tool calls between LLM response and OpenAI state formats.

    LLM providers return tool calls in various formats:
    - Dataclass: {id, name, arguments: dict}
    - Dict flat: {id, name, arguments: dict}
    - OpenAI: {type, id, function: {name, arguments: str}}

    Graph state uses OpenAI TypedDict format consistently.

    Also handles streaming where tool calls arrive as fragments
    that need to be accumulated across multiple chunks.
    """

    def convert(self, response_tool_calls: list | None) -> list[ToolCall]:
        """
        Convert tool calls from LLMResponse format to OpenAI format.

        Args:
            response_tool_calls: List of tool calls from LLMResponse, or None

        Returns:
            List of OpenAI-format ToolCall dicts
        """
        if not response_tool_calls:
            return []

        tool_calls: list[ToolCall] = []
        for tc in response_tool_calls:
            # Handle dataclass format (has attributes)
            if hasattr(tc, "name"):
                tc_id = getattr(tc, "id", "") or ""
                tc_name = tc.name
                tc_args = tc.arguments
            # Handle dict formats
            elif isinstance(tc, dict):
                # Already OpenAI format - passthrough
                if "function" in tc:
                    tool_calls.append(tc)  # type: ignore[arg-type]
                    continue
                # Flat dict format
                tc_id = tc.get("id", "") or ""
                tc_name = tc.get("name", "")
                tc_args = tc.get("arguments", {})
            else:
                logger.warning("Unknown tool call format: %s", type(tc))
                continue

            # Normalize arguments to JSON string
            if isinstance(tc_args, dict):
                tc_args = json.dumps(tc_args)
            elif not isinstance(tc_args, str):
                tc_args = "{}"

            tool_calls.append(
                ToolCall(
                    type="function",
                    id=tc_id,
                    function={
                        "name": tc_name,
                        "arguments": tc_args,
                    },
                )
            )

        return tool_calls

    def accumulate(self, fragments: list[ToolCallFragment]) -> dict[int, dict]:
        """
        Accumulate tool call fragments into complete tool calls.

        Streaming responses deliver tool calls in fragments across multiple
        chunks. This accumulates them by index.

        Args:
            fragments: List of tool call fragments from streaming

        Returns:
            Dict mapping index to accumulated tool call data
        """
        accumulated: dict[int, dict] = {}

        for frag in fragments:
            idx = frag.index
            if idx not in accumulated:
                accumulated[idx] = {
                    "id": "",
                    "name": "",
                    "arguments": "",
                }

            if frag.id:
                accumulated[idx]["id"] = frag.id
            if frag.name:
                accumulated[idx]["name"] += frag.name
            if frag.arguments:
                accumulated[idx]["arguments"] += frag.arguments

        return accumulated

    def fragments_to_calls(self, accumulated: dict[int, dict]) -> list[ToolCall]:
        """
        Convert accumulated fragments to ToolCall dicts in OpenAI format.

        Args:
            accumulated: Dict from accumulate()

        Returns:
            List of ToolCall TypedDicts in OpenAI format
        """
        tool_calls: list[ToolCall] = []

        for idx in sorted(accumulated.keys()):
            tc_data = accumulated[idx]
            # Only include if we have a name
            if tc_data["name"]:
                tool_calls.append(
                    ToolCall(
                        type="function",
                        id=tc_data["id"],
                        function={
                            "name": tc_data["name"],
                            "arguments": tc_data["arguments"],
                        },
                    )
                )

        return tool_calls

    def extract_text_tool_calls(self, content: str) -> tuple[str, list[ToolCall]]:
        """
        Extract textual tool calls that some providers emit as content.

        A few tool-capable-looking models stream tool calls as assistant text,
        for example:
        <function(codebase_search {"query": "x"})></function>

        Graph execution needs those as structured tool_calls, not transcript
        text. Invalid matches are left in content so the user can see the
        provider's malformed output instead of silently dropping it.
        """
        if not content:
            return content, []

        remaining_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        cursor = 0

        while next_match := self._find_next_text_function_start(content, cursor):
            match, argument_suffix = next_match
            remaining_parts.append(content[cursor : match.start()])
            parsed = self._parse_text_tool_call(
                content,
                match,
                argument_suffix,
                len(tool_calls),
            )
            if parsed is None:
                remaining_parts.append(content[match.start() : match.end()])
                cursor = match.end()
                continue

            tool_call, cursor = parsed
            tool_calls.append(tool_call)

        remaining_parts.append(content[cursor:])
        if tool_calls:
            return "".join(remaining_parts).strip(), tool_calls

        return content, []

    def _find_next_text_function_start(
        self,
        content: str,
        start: int,
    ) -> tuple[re.Match[str], str] | None:
        """Find the next supported textual tool-call prefix."""
        matches: list[tuple[int, int, re.Match[str], str]] = []
        for index, (pattern, argument_suffix) in enumerate(_TEXT_FUNCTION_START_PATTERNS):
            match = pattern.search(content, start)
            if match is not None:
                matches.append((match.start(), index, match, argument_suffix))

        if not matches:
            return None

        _, _, match, argument_suffix = min(matches, key=lambda item: (item[0], item[1]))
        return match, argument_suffix

    def _parse_text_tool_call(
        self,
        content: str,
        match: re.Match[str],
        argument_suffix: str,
        index: int,
    ) -> tuple[ToolCall, int] | None:
        """Convert textual tool-call content to OpenAI format and return its end."""
        tool_name = match.group(1)
        try:
            parsed_arguments, relative_argument_end = _JSON_DECODER.raw_decode(
                content[match.end() :]
            )
        except json.JSONDecodeError:
            logger.warning(
                "Provider emitted malformed textual tool call for %s: %s",
                tool_name,
                content[match.end() : match.end() + 200],
            )
            return None

        argument_end = match.end() + relative_argument_end
        close_start = content.find(_TEXT_FUNCTION_END, argument_end)
        if close_start == -1:
            logger.warning(
                "Provider emitted textual tool call for %s without closing tag",
                tool_name,
            )
            return None

        if content[argument_end:close_start].strip() != argument_suffix:
            logger.warning(
                "Provider emitted textual tool call for %s with malformed closing syntax",
                tool_name,
            )
            return None

        if not isinstance(parsed_arguments, dict):
            logger.warning(
                "Provider emitted non-object textual tool call arguments for %s",
                tool_name,
            )
            return None

        return (
            ToolCall(
                type="function",
                id=f"text_{tool_name}_{index}",
                function={
                    "name": tool_name,
                    "arguments": json.dumps(parsed_arguments),
                },
            ),
            close_start + len(_TEXT_FUNCTION_END),
        )


# Default instance for simple usage
default_processor = ToolCallProcessor()
