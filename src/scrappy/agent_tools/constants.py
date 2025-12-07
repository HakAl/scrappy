"""
Default configuration constants for agent tools.

These constants represent sensible defaults for command execution,
file operations, and other tool behaviors. They are used by both
AgentConfig and individual tool implementations to ensure consistency.

All values are documented with their rationale.
"""

from typing import List, Set

# File operation limits
DEFAULT_MAX_FILE_READ_SIZE = 10000  # bytes - balance between context and memory
DEFAULT_MAX_FILE_LISTING = 100  # files - prevents overwhelming output
DEFAULT_MAX_DIRECTORY_TREE_LINES = 200  # lines - keeps tree output manageable

# Command execution limits
DEFAULT_COMMAND_TIMEOUT = 300  # seconds (5 minutes) - allows long builds/installs
DEFAULT_MAX_COMMAND_OUTPUT = 10000  # bytes - prevents memory issues with verbose commands

# Commands known to be long-running (pattern matches)
DEFAULT_LONG_RUNNING_COMMANDS: List[str] = [
    'create-react-app',
    'npm install',
    'pip install',
    'cargo build',
    'docker build',
    'npm run build',
    'yarn install',
    'pnpm install'
]

# Code search limits
DEFAULT_MAX_SEARCH_RESULTS = 50  # results - balance between completeness and noise

# Git operation limits
DEFAULT_GIT_TIMEOUT = 10  # seconds - git operations should be fast
DEFAULT_GIT_DIFF_TIMEOUT = 30  # seconds - diffs can be slower on large repos
DEFAULT_MAX_GIT_DIFF_SIZE = 5000  # bytes - keep diff output readable
DEFAULT_MAX_GIT_BLAME_SIZE = 5000  # bytes - blame can be verbose
DEFAULT_MAX_GIT_SHOW_SIZE = 5000  # bytes - show output can be large
DEFAULT_MAX_RECENT_CHANGES_SIZE = 15000  # bytes - more context for recent work
DEFAULT_MAX_RECENT_COMMITS = 10  # commits - enough for recent context

# Directory traversal
DEFAULT_SKIP_DIRECTORIES: Set[str] = {
    '.git',
    '__pycache__',
    'node_modules',
    '.venv',
    'venv',
    'env',
    '.tox',
    '.pytest_cache'
}

DEFAULT_ALLOWED_HIDDEN_FILES: Set[str] = {
    '.env',
    '.gitignore'
}

# Display/UI limits
DEFAULT_AUDIT_LOG_RESULT_TRUNCATION = 500  # chars - keep logs readable
DEFAULT_RESULT_DISPLAY_TRUNCATION = 300  # chars - prevent terminal spam
DEFAULT_WRITE_PREVIEW_TRUNCATION = 500  # chars - show enough to verify

# LLM settings
DEFAULT_MAX_TOKENS = 1500  # tokens - balance between completeness and cost
DEFAULT_TEMPERATURE = 0.3  # temperature - low for deterministic code generation

# Provider preferences (first available will be used)
# NOTE: GitHub Models excluded from planner due to aggressive rate limiting
# (crashes after ~10 requests, unsuitable for multi-step agent tasks)
# Cerebras llama-3.3-70b preferred for planning (best quality/speed balance)
# Groq llama-4-scout-17b-16e-instruct as secondary option
DEFAULT_PLANNER_PREFERENCES: List[str] = ['cerebras', 'groq', 'gemini']
DEFAULT_EXECUTOR_PREFERENCES: List[str] = ['cerebras', 'groq']

# Passive RAG settings
DEFAULT_PASSIVE_RAG_ENABLED = True  # bool - enable passive RAG context injection
DEFAULT_PASSIVE_RAG_MAX_TOKENS = 2000  # tokens - max tokens for passive RAG context

# Completion validation
DEFAULT_MEANINGFUL_ACTIONS: List[str] = ['write_file', 'run_command']
