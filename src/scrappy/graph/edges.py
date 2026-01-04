"""
Conditional edge routing logic for the LangGraph agent.

This module defines the routing functions used by StateGraph conditional edges
to determine which node to execute next based on current state.
"""

from __future__ import annotations

from enum import StrEnum

# Import AgentState directly (not TYPE_CHECKING) because LangGraph uses
# get_type_hints() at runtime to infer schema from routing function signatures.
from .state import AgentState


class Route(StrEnum):
    """Route destinations for graph edges.

    StrEnum ensures values work as strings with LangGraph while providing
    type safety and IDE completion.
    """
    THINK = "think"
    EXECUTE = "execute"
    VERIFY = "verify"
    CONFIRM = "confirm"
    ERROR = "error"
    END = "end"


# Safety limit constants (adjust these to tune agent behavior)
MAX_ITERATIONS: int = 50
MAX_RETRIES: int = 3


def route_after_think(state: AgentState) -> Route:
    """
    Route after think node completes.

    Checks if think node set an error that should bypass execute.

    Routing logic:
    - done=True -> END (fatal error like NotConfiguredError, stop immediately)
    - last_error is set -> ERROR (recoverable error, go to error node)
    - otherwise -> EXECUTE (normal flow, execute tool calls)

    Args:
        state: Current AgentState

    Returns:
        Route destination for the next node
    """
    # Import at runtime for isinstance check (TYPE_CHECKING import is type-only)
    from .state import AgentState as AgentStateClass

    # Type narrowing for mypy
    assert isinstance(state, AgentStateClass)

    # If think node marked as done (e.g., fatal/unrecoverable error), end immediately
    # MUST check done BEFORE last_error - NotConfiguredError sets both, and we want to stop
    if state.done:
        return Route.END

    # If think node set an error (but not done), route to error node for recovery
    if state.last_error is not None:
        return Route.ERROR

    # Normal flow: execute tool calls
    return Route.EXECUTE


def should_continue(state: AgentState) -> Route:
    """
    Determine the next node based on current state.

    Routing logic:
    - done=True -> END
    - iteration > max_iterations -> END
    - error_count > max_retries -> END
    - pending_confirmation is set -> CONFIRM
    - last_error is set -> ERROR
    - files_changed is non-empty -> VERIFY
    - otherwise -> THINK

    Args:
        state: Current AgentState

    Returns:
        Route destination for the next node
    """
    # Import at runtime for isinstance check (TYPE_CHECKING import is type-only)
    from .state import AgentState as AgentStateClass

    # Type narrowing for mypy
    assert isinstance(state, AgentStateClass)

    # Terminal conditions
    if state.done:
        return Route.END

    # Safety limits
    if state.iteration >= MAX_ITERATIONS:
        return Route.END

    if state.error_count >= MAX_RETRIES:
        return Route.END

    # Human-in-the-loop
    if state.pending_confirmation is not None:
        return Route.CONFIRM

    # Error recovery
    if state.last_error is not None:
        return Route.ERROR

    # Verification needed (only if files changed and not yet verified)
    if state.files_changed and not state.files_verified:
        return Route.VERIFY

    # Default: continue thinking
    return Route.THINK
