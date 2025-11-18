"""
Pattern configuration for CLI tool detection.

This module centralizes all regex patterns used for detecting when user queries
need tool support (web fetching, codebase exploration, etc.). All patterns are
pre-compiled at module load time for performance.

Pattern Categories:
- WEB_PATTERNS: Patterns for detecting web/package fetching queries
- CODEBASE_PATTERNS: Patterns for detecting codebase exploration queries
- URL_PATTERN: Pattern for detecting direct URLs
- PATH_PATTERN: Pattern for detecting file path references
"""

import re
from typing import List


# =============================================================================
# Web Fetching Patterns
# =============================================================================
# These patterns detect queries related to fetching documentation, package info,
# or other web resources.

WEB_PATTERNS: List[re.Pattern] = [
    # Fetch docs/documentation/api/website patterns
    re.compile(r'\bfetch\b.*\b(docs?|documentation|api|website|url|page)\b'),

    # Get/retrieve/download from web patterns
    re.compile(r'\b(get|retrieve|download|pull)\b.*\b(from|the)\b.*\b(web|url|site|docs?)\b'),

    # Check package/npm/pypi/github patterns
    re.compile(r'\bcheck\b.*\b(package|npm|pypi|github|version)\b'),

    # Look up package/library patterns
    re.compile(r'\blook\s*up\b.*\b(package|library|module|dependency)\b'),

    # Latest/current/newest version patterns
    re.compile(r'\bwhat\s+(is|are)\s+the\s+(latest|current|newest)\b.*\b(version|release)\b'),

    # Current/latest version mentions
    re.compile(r'\b(current|latest|newest)\s+(versions?|releases?)\b'),

    # Package registry info patterns
    re.compile(r'\b(pypi|npm|github)\b.*\b(info|details|package)\b'),

    # From website/web/url patterns
    re.compile(r'\bfrom\s+(the\s+)?(website|web|url|docs)\b'),

    # Popular library documentation patterns
    re.compile(r'\b(scikit|sklearn|react|django|flask|express|numpy|pandas)\b.*\b(docs?|documentation|api)\b'),
]


# =============================================================================
# Codebase Exploration Patterns
# =============================================================================
# These patterns detect queries about code structure, file contents, and
# project organization.

CODEBASE_PATTERNS: List[re.Pattern] = [
    # File/directory existence questions
    re.compile(r'\b(does|do|is|are|has|have|where)\b.*\b(file|directory|folder|code|class|function|method)\b'),

    # File/directory content questions
    re.compile(r'\b(file|directory|folder)\b.*\b(contain|have|include|exist)\b'),

    # What is in file/directory questions
    re.compile(r'\bwhat\b.*\b(in|inside)\b.*\b(file|directory|folder|codebase|project)\b'),

    # Show file/code/function commands
    re.compile(r'\bshow\s+(me\s+)?(the\s+)?(file|code|function|class|directory)\b'),

    # Read file/code commands
    re.compile(r'\bread\b.*\b(file|code)\b'),

    # List files/directories commands
    re.compile(r'\blist\b.*\b(files?|directories?|folders?)\b'),

    # Structure/architecture questions
    re.compile(r'\b(structure|architecture|layout|organization)\b.*\b(of|in)\b.*\b(project|codebase|code)\b'),

    # How is organized/structured questions
    re.compile(r'\bhow\s+(is|are)\b.*\b(organized|structured|laid out)\b'),

    # Does have/contain/include questions
    re.compile(r'\b(does|do)\b.*\b(have|contain|include|use|import)\b'),

    # Where is/are questions
    re.compile(r'\bwhere\s+(is|are|does|do)\b'),

    # Where tests/files/code is/are questions
    re.compile(r'\bwhere\b.*\b(tests?|files?|code)\b.*\b(is|are)\b'),

    # Find in code/project patterns
    re.compile(r'\bfind\b.*\b(in|inside|within)\b.*\b(code|project|codebase)\b'),

    # File extension patterns
    re.compile(r'\b\w+\.(js|py|ts|tsx|jsx|java|cpp|c|h|rs|go|rb|php|css|html|json|yaml|yml|md|txt)\b'),
]


# =============================================================================
# URL and Path Patterns
# =============================================================================

# Direct URL pattern (HTTP/HTTPS)
URL_PATTERN: re.Pattern = re.compile(r'https?://')

# File path pattern (e.g., "src/main", "frontend/app")
PATH_PATTERN: re.Pattern = re.compile(r'\b\w+/\w+')


# =============================================================================
# All Patterns Combined
# =============================================================================

ALL_PATTERNS: List[re.Pattern] = WEB_PATTERNS + CODEBASE_PATTERNS + [URL_PATTERN, PATH_PATTERN]


# =============================================================================
# Package and Action Keywords
# =============================================================================
# Used for detecting package registry queries with action verbs

PACKAGE_KEYWORDS: List[str] = ['pypi', 'npm', 'github.com', 'registry']

ACTION_KEYWORDS: List[str] = ['fetch', 'get', 'check', 'look', 'find', 'show', 'what']


# =============================================================================
# Pattern Documentation
# =============================================================================
# Describes what each pattern matches for documentation and debugging purposes.

PATTERN_DESCRIPTIONS: dict = {
    'web': {
        0: "Fetch docs/documentation/api/website patterns",
        1: "Get/retrieve/download from web patterns",
        2: "Check package/npm/pypi/github patterns",
        3: "Look up package/library patterns",
        4: "Latest/current/newest version question patterns",
        5: "Current/latest version mention patterns",
        6: "Package registry info patterns",
        7: "From website/web/url patterns",
        8: "Popular library documentation patterns",
    },
    'codebase': {
        0: "File/directory existence questions",
        1: "File/directory content questions",
        2: "What is in file/directory questions",
        3: "Show file/code/function commands",
        4: "Read file/code commands",
        5: "List files/directories commands",
        6: "Structure/architecture questions",
        7: "How is organized/structured questions",
        8: "Does have/contain/include questions",
        9: "Where is/are questions",
        10: "Where tests/files/code is/are questions",
        11: "Find in code/project patterns",
        12: "File extension patterns",
    },
    'url': "Direct HTTP/HTTPS URL detection",
    'path': "File path pattern detection (e.g., src/main)",
}


# =============================================================================
# Helper Functions
# =============================================================================

def match_any_web_pattern(text: str) -> bool:
    """
    Check if text matches any web fetching pattern.

    Args:
        text: The text to check (will be lowercased).

    Returns:
        True if any web pattern matches, False otherwise.
    """
    lower_text = text.lower()
    return any(pattern.search(lower_text) for pattern in WEB_PATTERNS)


def match_any_codebase_pattern(text: str) -> bool:
    """
    Check if text matches any codebase exploration pattern.

    Args:
        text: The text to check (will be lowercased).

    Returns:
        True if any codebase pattern matches, False otherwise.
    """
    lower_text = text.lower()
    return any(pattern.search(lower_text) for pattern in CODEBASE_PATTERNS)
