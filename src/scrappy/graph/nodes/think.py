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

from typing import Callable, Optional

from scrappy.graph.nodes.context_manager import ContextManager
from scrappy.graph.nodes.token_estimator import TokenEstimator
from scrappy.graph.nodes.tool_call_processor import ToolCallProcessor
from scrappy.graph.protocols import (
    ContextFactoryProtocol,
    ThinkDelegatorProtocol,
    ThinkResult,
    WorkingMemoryProtocol,
)
from scrappy.graph.run_context import AgentRunContextProtocol
from scrappy.graph.state import AgentState, Message, ToolCall
from scrappy.graph.tools import ToolAdapterProtocol
from scrappy.infrastructure.logging import get_logger
from scrappy.orchestrator.types import ToolCallFragment
from scrappy.prompts.factory import PromptFactory
from scrappy.prompts.protocols import AgentPromptConfig

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


def _apply_think_result(
    state: AgentState,
    result: ThinkResult,
    user_message_exists: bool,
) -> AgentState:
    """
    Apply ThinkResult to state, returning updated AgentState.

    Centralizes the logic for mapping delegator results to state updates.
    Used by both think_node and think_node_streaming when using delegator.

    Args:
        state: Current agent state
        result: ThinkResult from delegator
        user_message_exists: Whether user message is already in state.messages

    Returns:
        Updated AgentState
    """
    # Handle error result
    if not result.is_success:
        return state.model_copy(
            update={
                "iteration": state.iteration + 1,
                "error_count": state.error_count + 1,
                "last_error": result.error,
                "recovery_action": result.recovery_action,
                "error_category": result.error_category,
                "done": result.is_fatal,
            }
        )

    # Build new assistant message
    new_message: Message = {
        "role": "assistant",
        "content": result.content,
    }
    if result.tool_calls:
        # Convert tuple to list for Message TypedDict
        new_message["tool_calls"] = list(result.tool_calls)

    # Update messages - include user message if not already present
    if user_message_exists:
        new_messages = list(state.messages) + [new_message]
    else:
        user_msg: Message = {"role": "user", "content": state.input}
        new_messages = [user_msg] + list(state.messages) + [new_message]

    # Success - clear fallback mode and error state
    return state.model_copy(
        update={
            "messages": new_messages,
            "iteration": state.iteration + 1,
            "done": result.is_done,
            "error_count": 0,
            "last_error": None,
            "current_model": None,  # Clear fallback mode
            "last_model_display": result.model_display,
        }
    )


def _build_messages_for_llm(
    state: AgentState,
    system_prompt: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> tuple[list[dict], bool]:
    """
    Build messages list for LLM call.

    Args:
        state: Current agent state
        system_prompt: System prompt to use
        max_tokens: Max context tokens for sanitization

    Returns:
        Tuple of (messages list, user_message_exists flag)
    """
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # Add conversation history
    for msg in state.messages:
        messages.append(dict(msg))

    # Check if user message already exists
    user_message_exists = any(
        m.get("role") == "user" and m.get("content") == state.input
        for m in state.messages
    )

    # Add current input if not already in conversation
    if not user_message_exists:
        messages.append({"role": "user", "content": state.input})

    # Sanitize context if too long
    messages = sanitize_context(messages, max_tokens)

    return messages, user_message_exists


def think_node(
    state: AgentState,
    delegator: ThinkDelegatorProtocol,
    tool_adapter: Optional[ToolAdapterProtocol] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    working_memory: Optional[WorkingMemoryProtocol] = None,
    context_factory: Optional[ContextFactoryProtocol] = None,
    run_context: Optional[AgentRunContextProtocol] = None,
) -> AgentState:
    """
    Think node - LLM reasoning step.

    Takes the current state, calls the LLM via delegator, and returns
    updated state with new assistant message.

    The delegator handles all complexity:
    - Model selection (affinity, priority-based, tier fallback)
    - Streaming with cancellation support
    - Error handling with automatic retry/fallback
    - Provider affinity tracking

    Args:
        state: Current agent state
        delegator: Think delegator for LLM calls
        tool_adapter: Optional tool adapter for tool schemas
        max_tokens: Max context tokens (for sanitization)
        working_memory: Optional working memory for session context
        context_factory: Optional factory for RAG context augmentation
        run_context: Optional run context for cancellation support

    Returns:
        Updated AgentState with new assistant message
    """
    # Get tool names and schemas
    tool_names: list[str] = []
    tools = None
    if tool_adapter:
        tool_names = tool_adapter.get_tool_names()
        tool_schemas = tool_adapter.get_tool_schemas()
        if tool_schemas:
            tools = tool_schemas

    # Build system prompt and messages
    system_prompt = build_system_prompt(state, tool_names, working_memory, context_factory)
    messages, user_message_exists = _build_messages_for_llm(state, system_prompt, max_tokens)

    # Call delegator - handles model selection, streaming, errors, fallback
    result = delegator.complete(
        messages=messages,
        tools=tools,
        run_context=run_context,
        current_tier=state.current_tier,
    )

    return _apply_think_result(state, result, user_message_exists)


async def think_node_streaming(
    state: AgentState,
    delegator: ThinkDelegatorProtocol,
    tool_adapter: Optional[ToolAdapterProtocol] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    stream_callback: Optional[StreamCallback] = None,
    working_memory: Optional[WorkingMemoryProtocol] = None,
    context_factory: Optional[ContextFactoryProtocol] = None,
    run_context: Optional[AgentRunContextProtocol] = None,
) -> AgentState:
    """
    Think node with streaming support.

    Async version that streams content chunks via callback as they arrive.
    The delegator handles all complexity including cancellation.

    Args:
        state: Current agent state
        delegator: Think delegator for LLM calls
        tool_adapter: Optional tool adapter for tool schemas
        max_tokens: Max context tokens (for sanitization)
        stream_callback: Callback for streaming progress (content chunks)
        working_memory: Optional working memory for session context
        context_factory: Optional factory for RAG context augmentation
        run_context: Optional run context for cancellation support

    Returns:
        Updated AgentState with new assistant message
    """
    # Get tool names and schemas
    tool_names: list[str] = []
    tools = None
    if tool_adapter:
        tool_names = tool_adapter.get_tool_names()
        tool_schemas = tool_adapter.get_tool_schemas()
        if tool_schemas:
            tools = tool_schemas

    # Build system prompt and messages
    system_prompt = build_system_prompt(state, tool_names, working_memory, context_factory)
    messages, user_message_exists = _build_messages_for_llm(state, system_prompt, max_tokens)

    # Call delegator with streaming - handles model selection, errors, fallback
    result = await delegator.complete_streaming(
        messages=messages,
        tools=tools,
        run_context=run_context,
        current_tier=state.current_tier,
        on_chunk=stream_callback,
    )

    return _apply_think_result(state, result, user_message_exists)
