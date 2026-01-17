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

from pathlib import Path
from typing import Optional

from scrappy.graph.protocols import ToolContextFactory, ToolContextProtocol, WorkingMemoryProtocol
from scrappy.graph.run_context import AgentRunContextProtocol
from scrappy.graph.state import AgentState, Message, ToolCall, ToolResult
from scrappy.graph.tools import ToolAdapterProtocol
from scrappy.infrastructure.exceptions import CancelledException
from scrappy.infrastructure.logging import get_logger


class WorkingMemoryAdapter:
    """
    Adapter to expose WorkingMemory as expected by ToolContext.

    ToolContext expects orchestrator.working_memory, so this wraps
    a WorkingMemoryProtocol instance with that interface.
    """

    def __init__(self, working_memory: WorkingMemoryProtocol):
        self.working_memory = working_memory

logger = get_logger(__name__)

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


def normalize_file_path(file_path: str, working_dir: str) -> str:
    """
    Normalize a file path to be relative to working_dir.

    Handles both absolute and relative paths, resolving them to a
    consistent relative path within working_dir.

    Args:
        file_path: The file path to normalize (absolute or relative)
        working_dir: The working directory to make paths relative to

    Returns:
        Normalized relative path string
    """
    try:
        working_path = Path(working_dir).resolve()
        file_abs = Path(working_dir, file_path).resolve()

        # Make relative to working_dir if within it
        try:
            return str(file_abs.relative_to(working_path))
        except ValueError:
            # Path is outside working_dir, keep as-is
            return file_path
    except (OSError, ValueError):
        # Invalid path, return as-is
        return file_path


def track_file_changes(
    tool_call: ToolCall,
    files_changed: list[str],
    working_dir: str,
) -> list[str]:
    """
    Track file changes based on tool call.

    Detects write operations and extracts file paths.
    Normalizes paths to relative form to prevent duplicates.

    Args:
        tool_call: The tool call in OpenAI format
        files_changed: Current list of changed files
        working_dir: Working directory for path normalization

    Returns:
        Updated list of changed files (all paths normalized to relative)
    """
    # Extract from OpenAI format
    function_data = tool_call.get("function", {})
    tool_name = function_data.get("name", "")

    if tool_name not in WRITE_TOOL_NAMES:
        return files_changed

    # Parse arguments to extract file path
    import json

    arguments = function_data.get("arguments", "{}")
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

    if not file_path:
        return files_changed

    # Normalize to relative path for deduplication
    normalized_path = normalize_file_path(file_path, working_dir)

    # Check against normalized versions of existing paths
    normalized_existing = [normalize_file_path(f, working_dir) for f in files_changed]
    if normalized_path not in normalized_existing:
        return files_changed + [normalized_path]

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
    # Note: Check key existence, not truthiness - empty result is valid (e.g., no files found)
    if "result" in result:
        content = result["result"] if result["result"] else "(empty result)"
    elif "error" in result:
        content = result["error"] or "Tool execution failed"
    else:
        content = "Tool execution failed"

    message: Message = {
        "role": "tool",
        "content": content,
        "tool_call_id": tool_call.get("id", ""),
    }

    return message


def _default_context_factory(
    working_dir: str,
    working_memory: Optional[WorkingMemoryProtocol] = None,
    run_context: Optional[AgentRunContextProtocol] = None,
) -> ToolContextProtocol:
    """
    Default factory for creating tool contexts.

    Creates a ToolContext from the agent_tools package.
    This is used when no factory is injected.

    Args:
        working_dir: Working directory for file operations
        working_memory: Optional working memory for tracking tool results
        run_context: Optional ephemeral run context for file caching/status
    """
    from scrappy.agent_config import AgentConfig
    from scrappy.agent_tools.tools.base import ToolContext

    # Wrap working_memory in adapter if provided
    orchestrator = WorkingMemoryAdapter(working_memory) if working_memory else None

    # Get semantic search from run context if available
    semantic_search = None
    if run_context and hasattr(run_context, 'semantic_search'):
        semantic_search = run_context.semantic_search

    return ToolContext(
        project_root=Path(working_dir),
        dry_run=False,
        config=AgentConfig(),
        orchestrator=orchestrator,
        run_context=run_context,
        semantic_search=semantic_search,
    )


def execute_node(
    state: AgentState,
    tool_adapter: ToolAdapterProtocol,
    context_factory: Optional[ToolContextFactory] = None,
    working_memory: Optional[WorkingMemoryProtocol] = None,
    run_context: Optional[AgentRunContextProtocol] = None,
) -> AgentState:
    """
    Execute node - tool execution step.

    Parses tool calls from the last assistant message and executes them
    sequentially via the tool adapter. Results are appended as tool messages.

    Args:
        state: Current agent state
        tool_adapter: Tool adapter for executing tools
        context_factory: Factory to create ToolContext (uses default if not provided)
        working_memory: Optional working memory for tracking tool results
        run_context: Optional ephemeral run context for file caching/status

    Returns:
        Updated AgentState with tool results appended to messages
    """
    # Check cancellation before starting any execution
    if run_context is not None and run_context.is_cancelled():
        logger.info("Execute node cancelled before start")
        return state.model_copy(
            update={
                "done": True,
                "last_error": "Cancelled by user",
            }
        )

    # Extract tool calls from last message
    tool_calls = extract_tool_calls(state)

    if not tool_calls:
        # Check if last message has tool_calls field but extraction returned empty
        # This indicates malformed tool calls that should be treated as an error
        if state.messages:
            last_msg = state.messages[-1]
            if last_msg.get("role") == "assistant" and "tool_calls" in last_msg:
                logger.warning(
                    "Last message has tool_calls field but extraction returned empty. "
                    "Tool calls may be malformed."
                )
                return state.model_copy(
                    update={
                        "error_count": state.error_count + 1,
                        "last_error": "Tool call extraction failed: malformed tool_calls in response",
                    }
                )
        logger.debug("No tool calls to execute")
        return state

    logger.info("Executing %d tool call(s)", len(tool_calls))

    # Create context using factory
    # If custom factory provided, use it (won't have working_memory or run_context)
    # Otherwise use default factory with full support
    if context_factory:
        context = context_factory(state.working_dir)
    else:
        context = _default_context_factory(state.working_dir, working_memory, run_context)

    # Execute tools sequentially (not parallel to avoid file conflicts)
    # Wrap in try/except to prevent graph crash on tool adapter failures
    try:
        raw_results = tool_adapter.execute(tool_calls, context)
    except CancelledException:
        # User cancelled during tool execution
        logger.info("Tool execution cancelled by user")
        return state.model_copy(
            update={
                "done": True,
                "last_error": "Cancelled by user",
            }
        )
    except Exception as e:
        # Tool adapter crashed - increment error count and set last_error
        # so routing goes to error node for recovery
        logger.exception("Tool adapter crashed: %s: %s", type(e).__name__, e)
        return state.model_copy(
            update={
                "error_count": state.error_count + 1,
                "last_error": f"Tool execution failed: {type(e).__name__}: {e}",
            }
        )

    # Process results and build messages
    new_messages = list(state.messages)
    files_changed = list(state.files_changed)
    files_modified = False
    task_complete = False
    tool_errors: list[str] = []

    for tool_call, raw_result in zip(tool_calls, raw_results):
        # Check cancellation between result processing
        if run_context is not None and run_context.is_cancelled():
            logger.info("Tool result processing cancelled - returning partial results")
            return state.model_copy(
                update={
                    "messages": new_messages,
                    "files_changed": files_changed,
                    "done": True,
                    "last_error": "Cancelled by user",
                }
            )

        # Process result (truncation, binary guard)
        processed_result = process_tool_result(raw_result)

        # Track file changes (paths normalized to relative)
        new_files = track_file_changes(tool_call, files_changed, state.working_dir)
        if new_files != files_changed:
            files_changed = new_files
            files_modified = True

        # Build and append tool message
        tool_message = build_tool_message(tool_call, processed_result)
        new_messages.append(tool_message)

        # Log execution (extract name from OpenAI format)
        func_name = tool_call.get("function", {}).get("name", "unknown")
        if "error" in processed_result and processed_result.get("error"):
            error_msg = processed_result.get("error", "Unknown error")
            logger.warning("Tool %s failed: %s", func_name, error_msg)
            tool_errors.append(f"{func_name}: {error_msg}")
        else:
            logger.debug("Tool %s executed successfully", func_name)

        # Check if complete tool was called (signals task completion)
        if func_name == "complete":
            task_complete = True
            logger.info("Task marked complete via complete tool")

    # Build update dict
    # Include pending_tool_calls for UX display (bridge extracts key params)
    update: dict[str, object] = {
        "messages": new_messages,
        "files_changed": files_changed,
        "files_verified": not files_modified,
        "tool_results": raw_results,
        "pending_tool_calls": tool_calls,  # For UX display
        "done": task_complete or state.done,
    }

    # If any tools failed, track errors so routing goes to error node
    if tool_errors:
        error_summary = "; ".join(tool_errors)
        update["error_count"] = state.error_count + 1
        update["last_error"] = f"Tool error(s): {error_summary}"
        logger.info("Tool errors detected, routing to error node for recovery")

    return state.model_copy(update=update)  # type: ignore[arg-type]
