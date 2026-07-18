"""Authored default suggestion copy for infrastructure provider errors.

Single owner for the suggestion strings used by the provider exception
hierarchy in this package. Constants are keyed by failure category,
never by orchestrator vocabularies.
"""

from typing import Optional


AUTH_SUGGESTION_TEMPLATE = (
    "Check your API key for {provider}. "
    "Ensure it is valid and has proper permissions."
)

NETWORK_SUGGESTION = "Check your network connection and try again."

TIMEOUT_SUGGESTION = (
    "The request took too long. Try again or check network connection."
)

RATE_LIMIT_WAIT_TEMPLATE = "Wait {seconds:.1f} seconds before retrying."

PROVIDER_NOT_FOUND_TEMPLATE = "Available providers: {providers}"

ROUTER_GROUP_NO_WINDOW_SUGGESTION = (
    "Wait for rate limits to reset or add more provider API keys."
)


def format_wait_time(seconds: float) -> str:
    """Format seconds into human-readable time."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def router_group_suggestion(min_retry: Optional[float]) -> str:
    """Actionable suggestion for router-group exhaustion."""
    if min_retry is not None:
        return f"Wait {format_wait_time(min_retry)} or add another provider API key."
    return ROUTER_GROUP_NO_WINDOW_SUGGESTION
