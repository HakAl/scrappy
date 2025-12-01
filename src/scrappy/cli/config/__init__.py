"""
CLI configuration module.

Contains configuration constants and patterns for the CLI.
"""

from scrappy.cli.config.patterns import (
    WEB_PATTERNS,
    CODEBASE_PATTERNS,
    URL_PATTERN,
    PATH_PATTERN,
    ALL_PATTERNS,
    PATTERN_DESCRIPTIONS,
    PACKAGE_KEYWORDS,
    ACTION_KEYWORDS,
    match_any_web_pattern,
    match_any_codebase_pattern,
)

__all__ = [
    'WEB_PATTERNS',
    'CODEBASE_PATTERNS',
    'URL_PATTERN',
    'PATH_PATTERN',
    'ALL_PATTERNS',
    'PATTERN_DESCRIPTIONS',
    'PACKAGE_KEYWORDS',
    'ACTION_KEYWORDS',
    'match_any_web_pattern',
    'match_any_codebase_pattern',
]
