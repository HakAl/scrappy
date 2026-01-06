"""
Context-aware fallback chains for rate limit handling.

This module provides model fallback chains that consider whether the request
is using tools (agent mode) or just chat (no tools). This distinction is
critical because:

- Agent mode: Requires instruct/tool-capable models. Llama models don't
  properly follow tool-use instructions, so they CANNOT be used for agent tasks.

- Chat mode: Any model works for conversational responses.

The fallback logic lives at the graph level (not LiteLLM Router) because only
the graph knows whether tools are being used for a given request.

See: scrappy-oikp (Integrate tier escalation into graph package)
"""

from typing import Optional


# Agent mode fallback chain
# ONLY instruct/tool-capable models - Llama doesn't follow tool instructions
AGENT_FALLBACK_CHAIN: tuple[str, ...] = (
    "cerebras/qwen-3-235b-a22b-instruct-2507",  # Primary: fast, instruction-tuned
    "gemini/gemini-2.5-flash",  # Fallback: huge context, good tool use
)

# Chat mode fallback chain
# Any model works for conversational responses
CHAT_FALLBACK_CHAIN: tuple[str, ...] = (
    "cerebras/qwen-3-235b-a22b-instruct-2507",  # Primary: fast, quality
    "groq/llama-3.3-70b-versatile",  # Fallback: fast, 32k context
    "groq/moonshotai/kimi-k2-instruct",  # Fallback: 128k context
    "gemini/gemini-2.5-flash",  # Last resort: huge context
)


def get_fallback_chain(has_tools: bool) -> tuple[str, ...]:
    """
    Get the appropriate fallback chain based on whether tools are being used.

    Args:
        has_tools: True if the request is using tools (agent mode)

    Returns:
        Tuple of model names in priority order
    """
    if has_tools:
        return AGENT_FALLBACK_CHAIN
    return CHAT_FALLBACK_CHAIN


def get_next_fallback(
    current_model: Optional[str],
    has_tools: bool,
) -> Optional[str]:
    """
    Get the next model to try after a rate limit error.

    Args:
        current_model: The model that just hit rate limit (None = start fresh)
        has_tools: True if the request is using tools (agent mode)

    Returns:
        Next model to try, or None if chain exhausted
    """
    chain = get_fallback_chain(has_tools)

    if current_model is None:
        # Start of chain
        return chain[0] if chain else None

    # Find current position and return next
    try:
        idx = chain.index(current_model)
        if idx + 1 < len(chain):
            return chain[idx + 1]
    except ValueError:
        # Current model not in chain, start from beginning
        return chain[0] if chain else None

    # Chain exhausted
    return None


def is_chain_exhausted(
    current_model: Optional[str],
    has_tools: bool,
) -> bool:
    """
    Check if we've exhausted all fallback options.

    Args:
        current_model: The model that just hit rate limit
        has_tools: True if the request is using tools (agent mode)

    Returns:
        True if no more models to try
    """
    return get_next_fallback(current_model, has_tools) is None
