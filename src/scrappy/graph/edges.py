"""
Conditional edge routing logic for the LangGraph agent.

This module defines the routing functions used by StateGraph conditional edges
to determine which node to execute next based on current state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .state import AgentState

# Type alias for routing destinations
RouteDestination = Literal["think", "execute", "verify", "confirm", "error", "end"]

# Safety limit constants (adjust these to tune agent behavior)
MAX_ITERATIONS: int = 50
MAX_RETRIES: int = 3


def should_continue(state: AgentState) -> RouteDestination:
    """
    Determine the next node based on current state.

    Routing logic:
    - done=True -> "end"
    - iteration > max_iterations -> "end"
    - error_count > max_retries -> "end"
    - pending_confirmation is set -> "confirm"
    - last_error is set -> "error"
    - files_changed is non-empty -> "verify"
    - otherwise -> "think"

    Args:
        state: Current AgentState

    Returns:
        Name of the next node to execute
    """
    # Import at runtime for isinstance check (TYPE_CHECKING import is type-only)
    from .state import AgentState as AgentStateClass

    # Type narrowing for mypy
    assert isinstance(state, AgentStateClass)

    # Terminal conditions
    if state.done:
        return "end"

    # Safety limits
    if state.iteration >= MAX_ITERATIONS:
        return "end"

    if state.error_count >= MAX_RETRIES:
        return "end"

    # Human-in-the-loop
    if state.pending_confirmation is not None:
        return "confirm"

    # Error recovery
    if state.last_error is not None:
        return "error"

    # Verification needed (only if files changed and not yet verified)
    if state.files_changed and not state.files_verified:
        return "verify"

    # Default: continue thinking
    return "think"
