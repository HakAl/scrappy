"""
Tool detector module for CLI.

Detects when user queries need tool support based on pattern matching.
This module contains pure functions with no side effects.
"""

from src.cli.cli_config import CLIConfig
from src.cli.config_factory import get_config


def needs_tool_support(user_input: str, config: CLIConfig = None) -> bool:
    """
    Detect if the user query needs tool support (web fetch, package lookup, codebase exploration, etc.)

    This allows auto-enabling tool use for research queries even when auto_route_mode is OFF.

    Args:
        user_input: The user's query string.
        config: Optional CLIConfig instance (uses global config if not provided).

    Returns:
        True if the query needs tool support, False otherwise.
    """
    if config is None:
        config = get_config()

    lower_input = user_input.lower()

    # Check web fetching patterns
    for pattern in config.web_patterns:
        if pattern.search(lower_input):
            return True

    # Direct URL mention
    if config.url_pattern.search(user_input):
        return True

    # Package registry keywords with action verbs
    has_package = any(kw in lower_input for kw in config.package_keywords)
    has_action = any(kw in lower_input for kw in config.action_keywords)

    if has_package and has_action:
        return True

    # Check codebase exploration patterns
    for pattern in config.codebase_patterns:
        if pattern.search(lower_input):
            return True

    # File path patterns (e.g., "frontend/app.js", "src/main.py")
    if config.path_pattern.search(user_input):
        return True

    return False
