"""
Tool call format conversion and streaming accumulation.

Single responsibility: Handle tool call format differences between
LLM provider responses and OpenAI-format state representation.
"""

import json
from typing import Protocol, runtime_checkable

from scrappy.graph.state import ToolCall
from scrappy.infrastructure.logging import get_logger
from scrappy.orchestrator.types import ToolCallFragment

logger = get_logger(__name__)


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


# Default instance for simple usage
default_processor = ToolCallProcessor()
