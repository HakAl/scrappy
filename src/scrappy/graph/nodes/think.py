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
import sys
from typing import Any, Callable, Optional

from scrappy.graph.fallbacks import get_next_fallback
from scrappy.graph.nodes.context_manager import ContextManager
from scrappy.graph.nodes.token_estimator import TokenEstimator
from scrappy.graph.nodes.tool_call_processor import ToolCallProcessor
from scrappy.graph.protocols import ContextFactoryProtocol, LLMServiceProtocol, StreamingLLMServiceProtocol, WorkingMemoryProtocol
from scrappy.graph.state import AgentState, Message, ToolCall
from scrappy.graph.tools import ToolAdapterProtocol
from scrappy.infrastructure.exceptions import (
    AllProvidersRateLimitedError,
    AuthenticationError,
    NetworkError,
    ProviderError,
    ProviderExecutionError,
    RateLimitError,
    RecoveryAction,
    TimeoutError as InfraTimeoutError,
)
from scrappy.infrastructure.logging import get_logger
from scrappy.orchestrator.litellm_service import NotConfiguredError
from scrappy.orchestrator.types import StreamChunk, ToolCallFragment
from scrappy.prompts.factory import PromptFactory
from scrappy.prompts.protocols import AgentPromptConfig, Platform

logger = get_logger(__name__)

# Module-level instances for backward compatibility and simple usage
_token_estimator = TokenEstimator()
_context_manager = ContextManager(_token_estimator)
_tool_call_processor = ToolCallProcessor()

# Re-export constants for backward compatibility
DEFAULT_MAX_TOKENS = ContextManager.DEFAULT_MAX_TOKENS
FULL_CONTEXT_WINDOW = ContextManager.DEFAULT_KEEP_FULL

# Callback type for streaming progress
StreamCallback = Callable[[str], None]


# === Backward-compatible function wrappers ===
# These delegate to the class instances for existing callers

def estimate_tokens(text: str) -> int:
    """Estimate token count for text. Delegates to TokenEstimator."""
    return _token_estimator.estimate_text(text)


def estimate_message_tokens(message: dict) -> int:
    """Estimate token count for a message. Delegates to TokenEstimator."""
    return _token_estimator.estimate_message(message)


def mask_old_tool_results(
    messages: list[dict],
    keep_full: int = FULL_CONTEXT_WINDOW,
) -> list[dict]:
    """Replace old tool results with placeholders. Delegates to ContextManager."""
    return _context_manager.mask_old_tool_results(messages, keep_full)


def sanitize_context(
    messages: list[dict],
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[dict]:
    """Trim message history if approaching token limit. Delegates to ContextManager."""
    return _context_manager.sanitize(messages, max_tokens)


def convert_tool_calls(response_tool_calls: Optional[list]) -> list[ToolCall]:
    """Convert tool calls from LLM response format. Delegates to ToolCallProcessor."""
    return _tool_call_processor.convert(response_tool_calls)


def accumulate_tool_calls(fragments: list[ToolCallFragment]) -> dict[int, dict]:
    """Accumulate streaming tool call fragments. Delegates to ToolCallProcessor."""
    return _tool_call_processor.accumulate(fragments)


def fragments_to_tool_calls(accumulated: dict[int, dict]) -> list[ToolCall]:
    """Convert accumulated fragments to ToolCall list. Delegates to ToolCallProcessor."""
    return _tool_call_processor.fragments_to_calls(accumulated)


def _handle_llm_error(
    error: Exception,
    state: AgentState,
    has_tools: bool,
    log_context: str = "think node",
) -> AgentState:
    """
    Handle LLM errors and return updated state.

    Centralizes error handling logic shared between think_node (sync) and
    think_node_streaming (async). Each error type has specific recovery behavior.

    Args:
        error: The exception that was raised
        state: Current agent state
        has_tools: Whether tools are being used (affects fallback chain selection)
        log_context: Context string for log messages (e.g., "think node", "streaming think node")

    Returns:
        Updated AgentState with error information set appropriately
    """
    if isinstance(error, NotConfiguredError):
        # LLM not configured - fatal error, stop the graph immediately
        logger.error("LLM not configured. User needs to run setup.")
        return state.model_copy(
            update={
                "iteration": state.iteration + 1,
                "done": True,  # Stop the graph, no point in retrying
                "last_error": "LLM not configured. Run /setup",
                "recovery_action": RecoveryAction.ABORT.value,
            }
        )

    if isinstance(error, AuthenticationError):
        # Auth error - non-retryable, user needs to fix API keys
        logger.error("Authentication error: %s", error)
        return state.model_copy(
            update={
                "iteration": state.iteration + 1,
                "done": True,  # Fatal - can't retry without valid credentials
                "last_error": str(error),
                "recovery_action": error.recovery_action.value,
                "error_category": error.category.value,
            }
        )

    if isinstance(error, AllProvidersRateLimitedError):
        # All providers rate limited - try fallback model if available
        # Use context-aware fallback chain based on whether tools are being used
        current_model = state.current_model
        next_model = get_next_fallback(current_model, has_tools=has_tools)

        if next_model:
            logger.warning(
                "Rate limited on %s, falling back to %s (has_tools=%s)",
                current_model or state.current_tier,
                next_model,
                has_tools,
            )
            # Return state with next fallback model - graph will loop back to think
            return state.model_copy(
                update={
                    "iteration": state.iteration + 1,
                    "current_model": next_model,
                    "last_error": f"Rate limited, trying fallback: {next_model}",
                    "recovery_action": RecoveryAction.FALLBACK.value,
                    "error_category": error.category.value,
                }
            )
        else:
            # Fallback chain exhausted - fatal error
            logger.error("All fallback models exhausted. Cannot continue.")
            return state.model_copy(
                update={
                    "iteration": state.iteration + 1,
                    "done": True,
                    "error_count": state.error_count + 1,
                    "last_error": "All providers rate limited. Please try again later.",
                    "recovery_action": RecoveryAction.ABORT.value,
                    "error_category": error.category.value,
                }
            )

    if isinstance(error, RateLimitError):
        # Single provider rate limit - retryable
        logger.warning(
            "Rate limit on provider %s: %s",
            error.provider_name or "unknown",
            error,
            extra=error.logging_extra(),
        )
        return state.model_copy(
            update={
                "iteration": state.iteration + 1,
                "error_count": state.error_count + 1,
                "last_error": str(error),
                "recovery_action": error.recovery_action.value,
                "error_category": error.category.value,
            }
        )

    if isinstance(error, (NetworkError, InfraTimeoutError)):
        # Network/timeout errors - retryable
        logger.warning(
            "Network error in %s: %s",
            log_context,
            error,
            extra=error.logging_extra(),
        )
        return state.model_copy(
            update={
                "iteration": state.iteration + 1,
                "error_count": state.error_count + 1,
                "last_error": str(error),
                "recovery_action": error.recovery_action.value,
                "error_category": error.category.value,
            }
        )

    if isinstance(error, (ConnectionError, TimeoutError, OSError)):
        # Stdlib network errors (fallback for non-wrapped errors)
        logger.warning("Network error in %s: %s", log_context, error)
        return state.model_copy(
            update={
                "iteration": state.iteration + 1,
                "error_count": state.error_count + 1,
                "last_error": f"Connection error: {error}",
                "recovery_action": RecoveryAction.RETRY.value,
                "error_category": "network",
            }
        )

    if isinstance(error, ProviderExecutionError):
        # Provider execution error - may be retryable
        logger.warning(
            "Provider execution error: %s",
            error,
            extra=error.logging_extra(),
        )
        return state.model_copy(
            update={
                "iteration": state.iteration + 1,
                "error_count": state.error_count + 1,
                "last_error": str(error),
                "recovery_action": error.recovery_action.value,
                "error_category": error.category.value,
            }
        )

    if isinstance(error, ProviderError):
        # Generic provider error - check if retryable
        log_method = logger.warning if error.is_retryable else logger.error
        log_method(
            "Provider error: %s",
            error,
            extra=error.logging_extra(),
        )
        return state.model_copy(
            update={
                "iteration": state.iteration + 1,
                "error_count": state.error_count + 1,
                "last_error": str(error),
                "recovery_action": error.recovery_action.value,
                "error_category": error.category.value,
                "done": not error.is_retryable,  # Stop if non-retryable
            }
        )

    if isinstance(error, (json.JSONDecodeError, ValueError, TypeError, AttributeError)):
        # Response parsing/handling errors - may be retryable (API returned bad format)
        logger.warning("Response parsing error in %s: %s", log_context, error)
        return state.model_copy(
            update={
                "iteration": state.iteration + 1,
                "error_count": state.error_count + 1,
                "last_error": f"Response error: {error}",
                "recovery_action": RecoveryAction.RETRY.value,
                "error_category": "parse",
            }
        )

    # Unexpected error - log with full traceback for debugging
    logger.exception(f"Unexpected error in {log_context}: {type(error).__name__}: {error}")
    return state.model_copy(
        update={
            "iteration": state.iteration + 1,
            "error_count": state.error_count + 1,
            "last_error": str(error),
            "recovery_action": RecoveryAction.ABORT.value,
            "error_category": "system",
        }
    )


def _detect_platform() -> Platform:
    """Detect the current operating system platform."""
    if sys.platform == "win32":
        return Platform.WINDOWS
    return Platform.UNIX


def build_system_prompt(
    state: AgentState,
    tool_names: list[str],
    working_memory: Optional[WorkingMemoryProtocol] = None,
    context_factory: Optional[ContextFactoryProtocol] = None,
) -> str:
    """
    Build the system prompt for the agent using PromptFactory.

    Creates an AgentPromptConfig with current state and delegates to
    PromptFactory.create_agent_system_prompt() for consistent prompt generation.

    Args:
        state: Current agent state
        tool_names: List of available tool names
        working_memory: Optional working memory for session context
        context_factory: Optional factory for RAG context augmentation

    Returns:
        System prompt string
    """
    # Gather optional context
    working_memory_context = None
    if working_memory:
        working_memory_context = working_memory.get_context()

    search_strategy = None
    rag_context = None
    if context_factory:
        search_strategy = context_factory.build_search_strategy_section(tool_names)
        rag_context = context_factory.build_rag_context(state.original_task)

    # Build config with all state
    config = AgentPromptConfig(
        platform=_detect_platform(),
        tool_names=tuple(tool_names),
        original_task=state.original_task,
        working_dir=state.working_dir,
        iteration=state.iteration,
        last_error=state.last_error,
        files_changed=tuple(state.files_changed),
        working_memory_context=working_memory_context or None,
        search_strategy=search_strategy or None,
        rag_context=rag_context or None,
    )

    # Delegate to factory
    factory = PromptFactory()
    return factory.create_agent_system_prompt(config)


def think_node(
    state: AgentState,
    llm_service: LLMServiceProtocol,
    tool_adapter: Optional[ToolAdapterProtocol] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    working_memory: Optional[WorkingMemoryProtocol] = None,
    context_factory: Optional[ContextFactoryProtocol] = None,
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
        working_memory: Optional working memory for session context
        context_factory: Optional factory for RAG context augmentation

    Returns:
        Updated AgentState with new assistant message
    """
    # Build system prompt
    tool_names = tool_adapter.get_tool_names() if tool_adapter else []
    system_prompt = build_system_prompt(state, tool_names, working_memory, context_factory)

    # Build messages list
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # Add conversation history
    for msg in state.messages:
        messages.append(dict(msg))

    # Check if user message already exists in state.messages
    # (Bug fix: previously checked only last message role, causing re-adds after tool results)
    user_message_exists = any(
        m.get("role") == "user" and m.get("content") == state.input
        for m in state.messages
    )

    # Add current input if not already in conversation history
    if not user_message_exists:
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
    # If current_model is set (fallback mode), use direct call to specific model
    # Otherwise use Router-based tier selection
    has_tools = tool_adapter is not None
    try:
        if state.current_model:
            # Fallback mode: call specific model directly (bypass Router)
            logger.info("Using fallback model: %s", state.current_model)
            response, task_record = llm_service.completion_direct(
                model=state.current_model,
                messages=messages,
                **llm_kwargs,
            )
        else:
            # Normal mode: use user-selected tier from state
            response, task_record = llm_service.completion_sync(
                model=state.current_tier,
                messages=messages,
                **llm_kwargs,
            )

        # LLMResponse.content is already normalized to string by litellm_service
        # (handles None, dict-in-content, etc.)
        content = response.content

        # Convert tool calls from LLMResponse format to OpenAI format
        # litellm_service already extracted tool calls from malformed content (dict, XML)
        tool_calls = convert_tool_calls(response.tool_calls)

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

        # Update state - include user message if this is first iteration
        # (Bug fix: user message must persist in state.messages for conversation history)
        if user_message_exists:
            new_messages = list(state.messages) + [new_message]
        else:
            user_msg: Message = {"role": "user", "content": state.input}
            new_messages = [user_msg] + list(state.messages) + [new_message]

        # Check if we should mark as done (no tool calls = final response)
        # Note: We already handled empty content case above, so content is non-empty here
        is_done = len(tool_calls) == 0

        # Format model display string (e.g., "cerebras: llama-3.3-70b")
        model_display = None
        if response.provider and response.model:
            # Strip provider prefix from model if present (e.g., "cerebras/llama-3.3-70b" -> "llama-3.3-70b")
            model_name = response.model
            if "/" in model_name:
                model_name = model_name.split("/", 1)[1]
            model_display = f"{response.provider}: {model_name}"

        # Success - clear fallback mode (current_model) since we got a response
        return state.model_copy(
            update={
                "messages": new_messages,
                "iteration": state.iteration + 1,
                "done": is_done,
                "error_count": 0,  # Reset on success - tracks consecutive errors
                "last_error": None,
                "current_model": None,  # Clear fallback mode on success
                "last_model_display": model_display,
            }
        )

    except Exception as e:
        return _handle_llm_error(e, state, has_tools, log_context="think node")


async def think_node_streaming(
    state: AgentState,
    llm_service: StreamingLLMServiceProtocol,
    tool_adapter: Optional[ToolAdapterProtocol] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    stream_callback: Optional[StreamCallback] = None,
    working_memory: Optional[WorkingMemoryProtocol] = None,
    context_factory: Optional[ContextFactoryProtocol] = None,
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
        working_memory: Optional working memory for session context
        context_factory: Optional factory for RAG context augmentation

    Returns:
        Updated AgentState with new assistant message
    """
    # Build system prompt
    tool_names = tool_adapter.get_tool_names() if tool_adapter else []
    system_prompt = build_system_prompt(state, tool_names, working_memory, context_factory)

    # Build messages list
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # Add conversation history
    for msg in state.messages:
        messages.append(dict(msg))

    # Check if user message already exists in state.messages
    # (Bug fix: previously checked only last message role, causing re-adds after tool results)
    user_message_exists = any(
        m.get("role") == "user" and m.get("content") == state.input
        for m in state.messages
    )

    # Add current input if not already in conversation history
    if not user_message_exists:
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
    # If current_model is set (fallback mode), use direct completion (loses streaming)
    # Otherwise use Router-based streaming
    has_tools = tool_adapter is not None
    try:
        # Fallback mode: use sync completion_direct (loses streaming but provides fallback)
        if state.current_model:
            logger.info("Using fallback model (non-streaming): %s", state.current_model)
            response, task_record = llm_service.completion_direct(
                model=state.current_model,
                messages=messages,
                **llm_kwargs,
            )
            # LLMResponse.content is already normalized to string by litellm_service
            accumulated_content = response.content
            if stream_callback and accumulated_content:
                stream_callback(accumulated_content)  # Send all at once
            # Convert tool calls from LLMResponse format to OpenAI format
            tool_calls = convert_tool_calls(response.tool_calls)
        else:
            # Normal streaming mode
            # Use list accumulator for O(n) total instead of O(n^2) string concat
            content_parts: list[str] = []
            all_fragments: list[ToolCallFragment] = []
            stream_model: str = ""
            stream_provider: str = ""

            # Use user-selected tier from state
            async for chunk in llm_service.stream_completion(
                model=state.current_tier,
                messages=messages,
                **llm_kwargs,
            ):
                # Type check - should be StreamChunk
                if isinstance(chunk, StreamChunk):
                    # Accumulate content (O(1) append)
                    if chunk.content:
                        content_parts.append(chunk.content)
                        if stream_callback:
                            stream_callback(chunk.content)

                    # Accumulate tool call fragments
                    if chunk.tool_call_fragments:
                        all_fragments.extend(chunk.tool_call_fragments)

                    # Capture model/provider from chunks (may be populated later)
                    if chunk.model:
                        stream_model = chunk.model
                    if chunk.provider:
                        stream_provider = chunk.provider

            # Join once at end (O(n) total)
            accumulated_content = "".join(content_parts)

            # Convert accumulated fragments to tool calls
            accumulated_tc = accumulate_tool_calls(all_fragments)
            tool_calls = fragments_to_tool_calls(accumulated_tc)

        # Check for empty response (no content AND no tool calls)
        # This is an error condition - LLM should return either content or tool calls
        if not tool_calls and not accumulated_content.strip():
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
            "content": accumulated_content,
        }
        if tool_calls:
            new_message["tool_calls"] = tool_calls

        # Update state - include user message if this is first iteration
        # (Bug fix: user message must persist in state.messages for conversation history)
        if user_message_exists:
            new_messages = list(state.messages) + [new_message]
        else:
            user_msg: Message = {"role": "user", "content": state.input}
            new_messages = [user_msg] + list(state.messages) + [new_message]

        # Check if we should mark as done (no tool calls = final response)
        is_done = len(tool_calls) == 0 and accumulated_content.strip() != ""

        # Format model display string (e.g., "cerebras: llama-3.3-70b")
        model_display = None
        # Use response object if available (non-streaming fallback), else streaming vars
        display_provider = response.provider if 'response' in dir() and response else stream_provider
        display_model = response.model if 'response' in dir() and response else stream_model
        if display_provider and display_model:
            # Strip provider prefix from model if present
            model_name = display_model
            if "/" in model_name:
                model_name = model_name.split("/", 1)[1]
            model_display = f"{display_provider}: {model_name}"

        # Success - clear fallback mode (current_model) since we got a response
        return state.model_copy(
            update={
                "messages": new_messages,
                "iteration": state.iteration + 1,
                "done": is_done,
                "error_count": 0,  # Reset on success - tracks consecutive errors
                "last_error": None,
                "current_model": None,  # Clear fallback mode on success
                "last_model_display": model_display,
            }
        )

    except Exception as e:
        return _handle_llm_error(e, state, has_tools, log_context="streaming think node")
