"""
Execute node for LangGraph agent.

Tool execution step that parses tool calls from the last assistant message
and executes them sequentially via ToolAdapter.

Features:
- Parses tool calls from last message
- Handles List[ToolCall] (multi-tool support)
- Sequential execution (avoids concurrent file write conflicts)
- Output truncation (20k chars max)
- Binary file guard (returns placeholder instead of crashing)
- Tracks files_changed for write operations
- Langfuse tracing integration
"""

import logging
from typing import Optional

from scrappy.agent_tools.tools.base import ToolContext
from scrappy.graph.state import AgentState, Message, ToolCall, ToolResult
from scrappy.graph.tools import ToolAdapterProtocol
from scrappy.graph.tracing import trace_node

logger = logging.getLogger(__name__)

# Output truncation threshold (20k chars)
OUTPUT_TRUNCATION_LIMIT = 20000

# Tool names that modify files
WRITE_TOOL_NAMES = frozenset({
    "write_file",
    "edit_file",
    "create_file",
    "patch_file",
    "delete_file",
})


def truncate_output(output: str, limit: int = OUTPUT_TRUNCATION_LIMIT) -> str:
    """
    Truncate output if it exceeds the limit.

    Truncates from the center to preserve both the beginning (often headers,
    error messages) and the end (often the most recent/relevant info).

    Args:
        output: The output string to potentially truncate
        limit: Maximum allowed length

    Returns:
        Original string if under limit, otherwise truncated with indicator
    """
    if len(output) <= limit:
        return output

    # Calculate how much to keep from start and end
    # Reserve space for the truncation indicator
    truncated_chars = len(output) - limit
    indicator = f"\n...[truncated {truncated_chars} chars]...\n"
    available = limit - len(indicator)

    # Split evenly between start and end
    start_len = available // 2
    end_len = available - start_len

    return output[:start_len] + indicator + output[-end_len:]


def is_binary_content(content: str) -> bool:
    """
    Check if content appears to be binary (non-text).

    Uses heuristic: if content has null bytes or high proportion of
    non-printable characters, it's likely binary.

    Args:
        content: String content to check

    Returns:
        True if content appears to be binary
    """
    if not content:
        return False

    # Check for null bytes (strong indicator of binary)
    if "\x00" in content:
        return True

    # Check ratio of non-printable characters
    sample = content[:1000]  # Check first 1000 chars for performance
    non_printable = sum(
        1 for c in sample
        if not c.isprintable() and c not in "\n\r\t"
    )

    # If more than 10% non-printable, likely binary
    return (non_printable / len(sample)) > 0.1 if sample else False


def format_binary_placeholder(byte_count: int) -> str:
    """
    Format a placeholder message for binary file content.

    Args:
        byte_count: Size of the binary content

    Returns:
        Placeholder string
    """
    return f"[Binary file: {byte_count} bytes]"


def extract_tool_calls(state: AgentState) -> list[ToolCall]:
    """
    Extract tool calls from the last assistant message in state.

    Args:
        state: Current agent state

    Returns:
        List of ToolCall dicts, empty if no tool calls found
    """
    if not state.messages:
        return []

    last_message = state.messages[-1]

    # Only assistant messages can have tool calls
    if last_message.get("role") != "assistant":
        return []

    tool_calls = last_message.get("tool_calls", [])
    return list(tool_calls) if tool_calls else []


def process_tool_result(result: ToolResult) -> ToolResult:
    """
    Post-process a tool result.

    Applies:
    - Binary file guard
    - Output truncation

    Args:
        result: Raw tool result

    Returns:
        Processed tool result
    """
    # If there's an error, don't process further
    if "error" in result and result.get("error"):
        return result

    # Get the result content
    content = result.get("result", "")
    if not content:
        return result

    # Binary file guard
    if is_binary_content(content):
        byte_count = len(content.encode("utf-8", errors="replace"))
        return ToolResult(
            name=result["name"],
            result=format_binary_placeholder(byte_count),
        )

    # Output truncation
    truncated = truncate_output(content)
    if truncated != content:
        logger.debug(
            "Truncated output for tool %s from %d to %d chars",
            result["name"],
            len(content),
            len(truncated),
        )

    return ToolResult(
        name=result["name"],
        result=truncated,
    )


def track_file_changes(
    tool_call: ToolCall,
    files_changed: list[str],
) -> list[str]:
    """
    Track file changes based on tool call.

    Detects write operations and extracts file paths.

    Args:
        tool_call: The tool call that was executed
        files_changed: Current list of changed files

    Returns:
        Updated list of changed files
    """
    tool_name = tool_call.get("name", "")

    if tool_name not in WRITE_TOOL_NAMES:
        return files_changed

    # Parse arguments to extract file path
    import json

    arguments = tool_call.get("arguments", "{}")
    try:
        if isinstance(arguments, str):
            args = json.loads(arguments) if arguments else {}
        else:
            args = arguments if arguments else {}
    except json.JSONDecodeError:
        return files_changed

    # Common parameter names for file paths
    file_path = (
        args.get("path")
        or args.get("file_path")
        or args.get("filepath")
        or args.get("file")
    )

    if file_path and file_path not in files_changed:
        return files_changed + [file_path]

    return files_changed


def build_tool_message(tool_call: ToolCall, result: ToolResult) -> Message:
    """
    Build a tool message for the conversation history.

    Args:
        tool_call: The original tool call
        result: The tool execution result

    Returns:
        Message dict in tool message format
    """
    # Get content from result or error
    content = result.get("result", "") or result.get("error", "Tool execution failed")

    message: Message = {
        "role": "tool",
        "content": content,
        "tool_call_id": tool_call.get("id", ""),
    }

    return message


@trace_node("execute")
def execute_node(
    state: AgentState,
    tool_adapter: ToolAdapterProtocol,
    context: Optional[ToolContext] = None,
) -> AgentState:
    """
    Execute node - tool execution step.

    Parses tool calls from the last assistant message and executes them
    sequentially via the tool adapter. Results are appended as tool messages.

    Args:
        state: Current agent state
        tool_adapter: Tool adapter for executing tools
        context: Optional ToolContext (creates default if not provided)

    Returns:
        Updated AgentState with tool results appended to messages
    """
    # Extract tool calls from last message
    tool_calls = extract_tool_calls(state)

    if not tool_calls:
        logger.debug("No tool calls to execute")
        return state

    logger.info("Executing %d tool call(s)", len(tool_calls))

    # Create context if not provided
    if context is None:
        from pathlib import Path
        context = ToolContext(
            project_root=Path(state.working_dir),
            dry_run=False,
        )

    # Execute tools sequentially (not parallel to avoid file conflicts)
    raw_results = tool_adapter.execute(tool_calls, context)

    # Process results and build messages
    new_messages = list(state.messages)
    files_changed = list(state.files_changed)
    files_modified = False

    for tool_call, raw_result in zip(tool_calls, raw_results):
        # Process result (truncation, binary guard)
        processed_result = process_tool_result(raw_result)

        # Track file changes
        new_files = track_file_changes(tool_call, files_changed)
        if new_files != files_changed:
            files_changed = new_files
            files_modified = True

        # Build and append tool message
        tool_message = build_tool_message(tool_call, processed_result)
        new_messages.append(tool_message)

        # Log execution
        if "error" in processed_result and processed_result.get("error"):
            logger.warning(
                "Tool %s failed: %s",
                tool_call.get("name"),
                processed_result.get("error"),
            )
        else:
            logger.debug("Tool %s executed successfully", tool_call.get("name"))

    # Update state
    # files_verified = False when files change (triggers verify node)
    return state.model_copy(
        update={
            "messages": new_messages,
            "files_changed": files_changed,
            "files_verified": not files_modified,
            "tool_results": raw_results,  # Store raw results for easier access
        }
    )
