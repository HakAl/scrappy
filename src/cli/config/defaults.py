"""
CLI default values configuration module.

Centralizes all numeric default values used throughout the CLI.
This eliminates magic numbers scattered across the codebase and
provides a single source of truth for default configuration.
"""

# Temperature defaults for LLM responses
TEMPERATURE_LOW = 0.3  # For precise, deterministic responses
TEMPERATURE_DEFAULT = 0.7  # Standard temperature for general use

# Token limit defaults
MAX_TOKENS_QUERY = 1000  # Max tokens for CLI queries
MAX_TOKENS_SUMMARY = 2000  # Max tokens for file summaries

# Line limit defaults
MAX_LINES_CONFIG = 100  # Max lines when reading config files
MAX_LINES_DEPENDENCY = 50  # Max lines when reading dependency files
MAX_TEST_RESULTS = 20  # Max test files to display in listings

# Content truncation thresholds (ordered by size)
TRUNCATE_ERROR_MESSAGE = 500  # Error message truncation
TRUNCATE_RESEARCH_MEDIUM = 1000  # Medium research content
TRUNCATE_RESEARCH_LARGE = 1500  # Large research content
TRUNCATE_FILE_CONTENT = 2000  # General file content
TRUNCATE_PRIORITY_FILE = 3000  # Priority/important files

# String preview length defaults
PREVIEW_SHORT = 40  # Short preview (e.g., filenames)
PREVIEW_STANDARD = 50  # Standard preview length
PREVIEW_CONCLUSION = 200  # Conclusion/summary previews

# Rate limit warning thresholds (as percentages)
CACHE_HIT_GOOD = 0.50  # Good cache hit rate (50%)
RATE_LIMIT_WARNING = 0.75  # Warning threshold (75%)
RATE_LIMIT_CRITICAL = 0.90  # Critical threshold (90%)

# Display defaults
MAX_DISPLAY_MESSAGES = 4  # Max messages to display in UI
PROGRESS_BAR_WIDTH = 20  # Width of progress bars
DASHBOARD_ENABLED = True  # Enable live dashboard display by default
DASHBOARD_REFRESH_RATE = 4  # Dashboard refresh rate (updates per second)

# Separator widths for console output
SEPARATOR_WIDTH_NARROW = 40  # Narrow separators
SEPARATOR_WIDTH_STANDARD = 50  # Standard separators
SEPARATOR_WIDTH_WIDE = 60  # Wide separators

# Command defaults
MAX_ITERATIONS = 10  # Max iterations for iterative commands

# Input length limits
MAX_INPUT_CHARS = 50000  # ~50KB, approximately 12,500 tokens
MAX_INPUT_LINES = 1000   # Sanity limit on line count

# Convenience dictionaries for grouped access
TEMPERATURES = {
    'low': TEMPERATURE_LOW,
    'default': TEMPERATURE_DEFAULT,
}

TRUNCATION_LIMITS = {
    'error_message': TRUNCATE_ERROR_MESSAGE,
    'research_medium': TRUNCATE_RESEARCH_MEDIUM,
    'research_large': TRUNCATE_RESEARCH_LARGE,
    'file_content': TRUNCATE_FILE_CONTENT,
    'priority_file': TRUNCATE_PRIORITY_FILE,
}

SEPARATOR_WIDTHS = {
    'narrow': SEPARATOR_WIDTH_NARROW,
    'standard': SEPARATOR_WIDTH_STANDARD,
    'wide': SEPARATOR_WIDTH_WIDE,
}
