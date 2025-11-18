"""
Tool detector module for CLI.

Detects when user queries need tool support based on pattern matching.
This module contains pure functions with no side effects.
"""

from src.cli.config.patterns import (
    WEB_PATTERNS,
    CODEBASE_PATTERNS,
    URL_PATTERN,
    PATH_PATTERN,
    PACKAGE_KEYWORDS,
    ACTION_KEYWORDS,
)


def needs_tool_support(user_input: str) -> bool:
    """
    Detect if the user query needs tool support (web fetch, package lookup, codebase exploration, etc.)

    This allows auto-enabling tool use for research queries even when auto_route_mode is OFF.

    Args:
        user_input: The user's query string.

    Returns:
        True if the query needs tool support, False otherwise.
    """
    lower_input = user_input.lower()

    # Check web fetching patterns
    for pattern in WEB_PATTERNS:
        if pattern.search(lower_input):
            return True

    # Direct URL mention
    if URL_PATTERN.search(user_input):
        return True

    # Package registry keywords with action verbs
    has_package = any(kw in lower_input for kw in PACKAGE_KEYWORDS)
    has_action = any(kw in lower_input for kw in ACTION_KEYWORDS)

    if has_package and has_action:
        return True

    # Check codebase exploration patterns
    for pattern in CODEBASE_PATTERNS:
        if pattern.search(lower_input):
            return True

    # File path patterns (e.g., "frontend/app.js", "src/main.py")
    if PATH_PATTERN.search(user_input):
        return True

    return False
