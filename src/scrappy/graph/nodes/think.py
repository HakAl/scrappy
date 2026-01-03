"""
Think node for LangGraph agent.

The "brain" of the agent - performs LLM reasoning to decide next action.
Takes AgentState, calls LLM with context and tools, returns updated state
with new assistant message (possibly including tool calls).

Features:
- Streaming from day 1 (uses LiteLLMService.stream_completion)
- Context sanitization (trims messages if approaching token limit)
- Tool calling via Instructor
- Langfuse tracing integration
"""

import json
import logging
from typing import Any, AsyncIterator, Callable, Optional, Protocol, runtime_checkable

from scrappy.graph.state import AgentState, Message, ToolCall
from scrappy.graph.tools import ToolAdapterProtocol
from scrappy.orchestrator.types import StreamChunk, ToolCallFragment

logger = logging.getLogger(__name__)

# Token estimation constants
# Average tokens per character (conservative estimate for English text)
TOKENS_PER_CHAR = 0.25
# Safety margin - trim at 80% of limit to leave room for response
TOKEN_LIMIT_MARGIN = 0.8
# Default context window (128k tokens)
DEFAULT_MAX_TOKENS = 128000
# Minimum messages to keep (system + last user message)
MIN_MESSAGES_TO_KEEP = 2


@runtime_checkable
class LLMServiceProtocol(Protocol):
    """
    Protocol for LLM service integration.

    Abstracts the LLM completion interface to enable testing
    without real API calls.
    """

    def completion_sync(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any,
    ) -> tuple[Any, dict]:
        """
        Sync completion call.

        Args:
            model: Model tier ("fast" or "quality")
            messages: Chat messages
            **kwargs: Additional params (tools, tool_choice, max_tokens, etc.)

        Returns:
            Tuple of (LLMResponse, task_record)
        """
        ...


@runtime_checkable
class StreamingLLMServiceProtocol(Protocol):
    """
    Protocol for streaming LLM service integration.

    Extends LLMServiceProtocol with streaming capabilities.
    """

    def stream_completion(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """
        Streaming completion call.

        Args:
            model: Model tier ("fast" or "quality")
            messages: Chat messages
            **kwargs: Additional params (tools, tool_choice, max_tokens, etc.)

        Returns:
            AsyncIterator of StreamChunk objects
        """
        ...


# Callback type for streaming progress
StreamCallback = Callable[[str], None]


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.

    Uses character-based estimation. Not perfectly accurate but
    sufficient for context trimming decisions.

    Args:
        text: Text to estimate tokens for

    Returns:
        Estimated token count
    """
    return int(len(text) * TOKENS_PER_CHAR)


def estimate_message_tokens(message: dict) -> int:
    """
    Estimate token count for a message.

    Includes role, content, and tool calls if present.

    Args:
        message: Message dict with role, content, etc.

    Returns:
        Estimated token count
    """
    tokens = 0

    # Role overhead (e.g., "user:", "assistant:")
    tokens += 4

    # Content tokens
    content = message.get("content", "")
    if content:
        tokens += estimate_tokens(content)

    # Tool calls overhead
    tool_calls = message.get("tool_calls", [])
    if tool_calls:
        for tc in tool_calls:
            # Name + arguments JSON
            name = tc.get("name", "")
            args = tc.get("arguments", "{}")
            tokens += estimate_tokens(name) + estimate_tokens(args) + 10  # Overhead

    return tokens


def sanitize_context(
    messages: list[dict],
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[dict]:
    """
    Trim message history if approaching token limit.

    Strategy:
    1. Always keep first message (system prompt) if present
    2. Always keep last few messages (current conversation)
    3. Summarize or drop middle messages if needed

    Args:
        messages: Full message history
        max_tokens: Maximum allowed tokens

    Returns:
        Trimmed message list within token budget
    """
    if not messages:
        return messages

    # Calculate current token usage
    total_tokens = sum(estimate_message_tokens(m) for m in messages)

    # Calculate effective limit with margin
    effective_limit = int(max_tokens * TOKEN_LIMIT_MARGIN)

    # If within limit, return as-is
    if total_tokens <= effective_limit:
        return messages

    logger.warning(
        "Context approaching limit: %d tokens (limit: %d). Trimming.",
        total_tokens,
        effective_limit,
    )

    # Strategy: Keep first message (system) and last N messages
    # Drop middle messages one by one until within limit
    if len(messages) <= MIN_MESSAGES_TO_KEEP:
        # Can't trim further, just return what we have
        return messages

    # Separate system message if present
    first_message = messages[0] if messages else None
    has_system = first_message is not None and first_message.get("role") == "system"

    if has_system:
        # Keep system + trim middle + keep recent
        system_msg: dict = messages[0]
        remaining: list[dict] = messages[1:]
    else:
        remaining = messages[:]

    # Binary search for how many recent messages we can keep
    for keep_count in range(len(remaining), 0, -1):
        recent_msgs: list[dict] = remaining[-keep_count:]
        if has_system:
            candidate: list[dict] = [system_msg] + recent_msgs
        else:
            candidate = recent_msgs

        candidate_tokens = sum(estimate_message_tokens(m) for m in candidate)
        if candidate_tokens <= effective_limit:
            if keep_count < len(remaining):
                dropped = len(remaining) - keep_count
                logger.info("Dropped %d messages to fit context window.", dropped)

                # Add a summary message to indicate trimming occurred
                summary_msg: dict = {
                    "role": "system",
                    "content": f"[Earlier conversation of {dropped} messages omitted for context limit]",
                }
                if has_system:
                    return [system_msg, summary_msg] + recent_msgs
                else:
                    return [summary_msg] + recent_msgs
            return candidate

    # Worst case: just keep the minimum
    logger.warning("Had to drop all but minimum messages for context limit.")
    if has_system:
        return [system_msg, remaining[-1]] if remaining else [system_msg]
    return [remaining[-1]] if remaining else []


def build_system_prompt(state: AgentState, tool_names: list[str]) -> str:
    """
    Build the system prompt for the agent.

    Includes task context, available tools, and guidelines.

    Args:
        state: Current agent state
        tool_names: List of available tool names

    Returns:
        System prompt string
    """
    tools_list = ", ".join(tool_names) if tool_names else "none"

    prompt = f"""You are a helpful AI coding assistant with access to tools.

## Current Task
{state.original_task}

## Available Tools
{tools_list}

## Guidelines
1. Analyze the task carefully before taking action
2. Use tools when needed to accomplish the task
3. If a task requires multiple steps, break it down
4. Verify your work when appropriate
5. Ask for clarification if the task is ambiguous
6. When the task is complete, call the `complete` tool with a summary of what you accomplished

## Working Directory
{state.working_dir}

## Iteration
{state.iteration} (safety limit helps prevent infinite loops)
"""

    # Add error context if recovering from error
    if state.last_error:
        prompt += f"""
## Previous Error
{state.last_error}
Please address this error in your response.
"""

    # Add files changed context
    if state.files_changed:
        files_list = "\n".join(f"- {f}" for f in state.files_changed)
        prompt += f"""
## Files Modified This Session
{files_list}
"""

    return prompt


def accumulate_tool_calls(fragments: list[ToolCallFragment]) -> dict[int, dict]:
    """
    Accumulate tool call fragments into complete tool calls.

    Streaming responses deliver tool calls in fragments across multiple chunks.
    This function accumulates them by index.

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


def fragments_to_tool_calls(accumulated: dict[int, dict]) -> list[ToolCall]:
    """
    Convert accumulated fragments to ToolCall dicts in OpenAI format.

    Args:
        accumulated: Dict from accumulate_tool_calls

    Returns:
        List of ToolCall TypedDicts in OpenAI format
    """
    tool_calls: list[ToolCall] = []

    for idx in sorted(accumulated.keys()):
        tc_data = accumulated[idx]
        if tc_data["name"]:  # Only include if we have a name
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


def think_node(
    state: AgentState,
    llm_service: LLMServiceProtocol,
    tool_adapter: Optional[ToolAdapterProtocol] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    stream_callback: Optional[StreamCallback] = None,
) -> AgentState:
    """
    Think node - LLM reasoning step.

    Takes the current state, calls the LLM with context and tools,
    and returns updated state with new assistant message.

    This is the synchronous version for simple execution contexts.
    Use think_node_streaming for async streaming support.

    Args:
        state: Current agent state
        llm_service: LLM service for completions
        tool_adapter: Optional tool adapter for tool schemas
        max_tokens: Max context tokens (for sanitization)
        stream_callback: Optional callback for streaming progress

    Returns:
        Updated AgentState with new assistant message
    """
    # Build system prompt
    tool_names = tool_adapter.get_tool_names() if tool_adapter else []
    system_prompt = build_system_prompt(state, tool_names)

    # Build messages list
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # Add conversation history
    for msg in state.messages:
        messages.append(dict(msg))

    # Add current input if not already in messages
    if not state.messages or state.messages[-1].get("role") != "user":
        messages.append({"role": "user", "content": state.input})

    # Sanitize context if too long
    messages = sanitize_context(messages, max_tokens)

    # Prepare LLM call kwargs
    llm_kwargs: dict[str, Any] = {
        "max_tokens": 4096,  # Response max tokens
        "temperature": 0.3,  # Lower temperature for more focused responses
    }

    # Add tool schemas if available
    if tool_adapter:
        tool_schemas = tool_adapter.get_tool_schemas()
        if tool_schemas:
            llm_kwargs["tools"] = tool_schemas
            llm_kwargs["tool_choice"] = "auto"

    # Call LLM
    try:
        response, task_record = llm_service.completion_sync(
            model=state.current_tier,
            messages=messages,
            **llm_kwargs,
        )

        # Extract response content
        content = response.content if hasattr(response, "content") else ""

        # Notify via callback if provided
        if stream_callback and content:
            stream_callback(content)

        # Extract tool calls if present, converting to OpenAI format
        tool_calls: list[ToolCall] = []
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                # Handle both dict and object tool calls, normalize to OpenAI format
                if isinstance(tc, dict):
                    # Could be OpenAI format or flat format
                    if "function" in tc:
                        # Already OpenAI format
                        tool_calls.append(tc)  # type: ignore[arg-type]
                    else:
                        # Flat format - convert to OpenAI
                        args = tc.get("arguments", {})
                        if isinstance(args, dict):
                            args = json.dumps(args)
                        tool_calls.append(
                            ToolCall(
                                type="function",
                                id=tc.get("id", ""),
                                function={
                                    "name": tc.get("name", ""),
                                    "arguments": args if args else "{}",
                                },
                            )
                        )
                else:
                    # Object with id, name, arguments attributes
                    args = tc.arguments
                    if isinstance(args, dict):
                        args = json.dumps(args)
                    tool_calls.append(
                        ToolCall(
                            type="function",
                            id=tc.id,
                            function={
                                "name": tc.name,
                                "arguments": args if isinstance(args, str) else "{}",
                            },
                        )
                    )

        # Check for empty response (no content AND no tool calls)
        # This is an error condition - LLM should return either content or tool calls
        if not tool_calls and not content.strip():
            logger.warning("LLM returned empty response (no content, no tool calls)")
            return state.model_copy(
                update={
                    "iteration": state.iteration + 1,
                    "error_count": state.error_count + 1,
                    "last_error": "LLM returned empty response. This may indicate an API issue or rate limiting.",
                }
            )

        # Build new assistant message
        new_message: Message = {
            "role": "assistant",
            "content": content,
        }
        if tool_calls:
            new_message["tool_calls"] = tool_calls

        # Update state
        new_messages = list(state.messages) + [new_message]

        # Check if we should mark as done (no tool calls = final response)
        # Note: We already handled empty content case above, so content is non-empty here
        is_done = len(tool_calls) == 0

        return state.model_copy(
            update={
                "messages": new_messages,
                "iteration": state.iteration + 1,
                "done": is_done,
                "error_count": 0,  # Reset error count on successful response
                "last_error": None,
            }
        )

    except (ConnectionError, TimeoutError, OSError) as e:
        # Network/connection errors - expected in distributed systems
        logger.warning("Network error in think node: %s", e)
        return state.model_copy(
            update={
                "iteration": state.iteration + 1,
                "error_count": state.error_count + 1,
                "last_error": f"Connection error: {e}",
            }
        )
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError) as e:
        # Response parsing/handling errors - expected when API returns unexpected format
        logger.warning("Response parsing error in think node: %s", e)
        return state.model_copy(
            update={
                "iteration": state.iteration + 1,
                "error_count": state.error_count + 1,
                "last_error": f"Response error: {e}",
            }
        )
    except Exception as e:
        # Unexpected error - log with full traceback for debugging
        logger.exception("Unexpected error in think node: %s: %s", type(e).__name__, e)
        return state.model_copy(
            update={
                "iteration": state.iteration + 1,
                "error_count": state.error_count + 1,
                "last_error": str(e),
            }
        )


async def think_node_streaming(
    state: AgentState,
    llm_service: StreamingLLMServiceProtocol,
    tool_adapter: Optional[ToolAdapterProtocol] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    stream_callback: Optional[StreamCallback] = None,
) -> AgentState:
    """
    Think node with streaming support.

    Async version that uses streaming completion for real-time output.
    Yields chunks via stream_callback as they arrive.

    Args:
        state: Current agent state
        llm_service: LLM service with streaming support
        tool_adapter: Optional tool adapter for tool schemas
        max_tokens: Max context tokens (for sanitization)
        stream_callback: Callback for streaming progress (content chunks)

    Returns:
        Updated AgentState with new assistant message
    """
    # Build system prompt
    tool_names = tool_adapter.get_tool_names() if tool_adapter else []
    system_prompt = build_system_prompt(state, tool_names)

    # Build messages list
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # Add conversation history
    for msg in state.messages:
        messages.append(dict(msg))

    # Add current input if not already in messages
    if not state.messages or state.messages[-1].get("role") != "user":
        messages.append({"role": "user", "content": state.input})

    # Sanitize context if too long
    messages = sanitize_context(messages, max_tokens)

    # Prepare LLM call kwargs
    llm_kwargs: dict[str, Any] = {
        "max_tokens": 4096,
        "temperature": 0.3,
    }

    # Add tool schemas if available
    if tool_adapter:
        tool_schemas = tool_adapter.get_tool_schemas()
        if tool_schemas:
            llm_kwargs["tools"] = tool_schemas
            llm_kwargs["tool_choice"] = "auto"

    # Stream LLM response
    try:
        accumulated_content = ""
        all_fragments: list[ToolCallFragment] = []

        async for chunk in llm_service.stream_completion(
            model=state.current_tier,
            messages=messages,
            **llm_kwargs,
        ):
            # Type check - should be StreamChunk
            if isinstance(chunk, StreamChunk):
                # Accumulate content
                if chunk.content:
                    accumulated_content += chunk.content
                    if stream_callback:
                        stream_callback(chunk.content)

                # Accumulate tool call fragments
                if chunk.tool_call_fragments:
                    all_fragments.extend(chunk.tool_call_fragments)

        # Convert accumulated fragments to tool calls
        accumulated_tc = accumulate_tool_calls(all_fragments)
        tool_calls = fragments_to_tool_calls(accumulated_tc)

        # Build new assistant message
        new_message: Message = {
            "role": "assistant",
            "content": accumulated_content,
        }
        if tool_calls:
            new_message["tool_calls"] = tool_calls

        # Update state
        new_messages = list(state.messages) + [new_message]

        # Check if we should mark as done (no tool calls = final response)
        is_done = len(tool_calls) == 0 and accumulated_content.strip() != ""

        return state.model_copy(
            update={
                "messages": new_messages,
                "iteration": state.iteration + 1,
                "done": is_done,
                "error_count": 0,
                "last_error": None,
            }
        )

    except (ConnectionError, TimeoutError, OSError) as e:
        # Network/connection errors - expected in distributed systems
        logger.warning("Network error in streaming think node: %s", e)
        return state.model_copy(
            update={
                "iteration": state.iteration + 1,
                "error_count": state.error_count + 1,
                "last_error": f"Connection error: {e}",
            }
        )
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError) as e:
        # Response parsing/handling errors - expected when API returns unexpected format
        logger.warning("Response parsing error in streaming think node: %s", e)
        return state.model_copy(
            update={
                "iteration": state.iteration + 1,
                "error_count": state.error_count + 1,
                "last_error": f"Response error: {e}",
            }
        )
    except Exception as e:
        # Unexpected error - log with full traceback for debugging
        logger.exception("Unexpected error in streaming think node: %s: %s", type(e).__name__, e)
        return state.model_copy(
            update={
                "iteration": state.iteration + 1,
                "error_count": state.error_count + 1,
                "last_error": str(e),
            }
        )
