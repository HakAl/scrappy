"""
Tool detector module for CLI.

Detects when user queries need tool support based on pattern matching.
This module contains pure functions with no side effects.
"""

import re


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

    # Web fetching patterns
    web_patterns = [
        r'\bfetch\b.*\b(docs?|documentation|api|website|url|page)\b',
        r'\b(get|retrieve|download|pull)\b.*\b(from|the)\b.*\b(web|url|site|docs?)\b',
        r'\bcheck\b.*\b(package|npm|pypi|github|version)\b',
        r'\blook\s*up\b.*\b(package|library|module|dependency)\b',
        r'\bwhat\s+(is|are)\s+the\s+(latest|current|newest)\b.*\b(version|release)\b',
        r'\b(current|latest|newest)\s+(versions?|releases?)\b',
        r'\b(pypi|npm|github)\b.*\b(info|details|package)\b',
        r'\bfrom\s+(the\s+)?(website|web|url|docs)\b',
        r'\b(scikit|sklearn|react|django|flask|express|numpy|pandas)\b.*\b(docs?|documentation|api)\b',
    ]

    for pattern in web_patterns:
        if re.search(pattern, lower_input):
            return True

    # Direct URL mention
    if re.search(r'https?://', user_input):
        return True

    # Package registry keywords with action verbs
    package_keywords = ['pypi', 'npm', 'github.com', 'registry']
    action_keywords = ['fetch', 'get', 'check', 'look', 'find', 'show', 'what']

    has_package = any(kw in lower_input for kw in package_keywords)
    has_action = any(kw in lower_input for kw in action_keywords)

    if has_package and has_action:
        return True

    # Codebase exploration patterns - questions about the code
    codebase_patterns = [
        # File-specific questions
        r'\b(does|do|is|are|has|have|where)\b.*\b(file|directory|folder|code|class|function|method)\b',
        r'\b(file|directory|folder)\b.*\b(contain|have|include|exist)\b',
        r'\bwhat\b.*\b(in|inside)\b.*\b(file|directory|folder|codebase|project)\b',
        r'\bshow\s+(me\s+)?(the\s+)?(file|code|function|class|directory)\b',
        r'\bread\b.*\b(file|code)\b',
        r'\blist\b.*\b(files?|directories?|folders?)\b',
        # Structure questions
        r'\b(structure|architecture|layout|organization)\b.*\b(of|in)\b.*\b(project|codebase|code)\b',
        r'\bhow\s+(is|are)\b.*\b(organized|structured|laid out)\b',
        # Content questions
        r'\b(does|do)\b.*\b(have|contain|include|use|import)\b',
        r'\bwhere\s+(is|are|does|do)\b',
        r'\bwhere\b.*\b(tests?|files?|code)\b.*\b(is|are)\b',
        r'\bfind\b.*\b(in|inside|within)\b.*\b(code|project|codebase)\b',
        # Specific file extensions/names
        r'\b\w+\.(js|py|ts|tsx|jsx|java|cpp|c|h|rs|go|rb|php|css|html|json|yaml|yml|md|txt)\b',
    ]

    for pattern in codebase_patterns:
        if re.search(pattern, lower_input):
            return True

    # File path patterns (e.g., "frontend/app.js", "src/main.py")
    if re.search(r'\b\w+/\w+', user_input):  # path-like pattern
        return True

    return False
