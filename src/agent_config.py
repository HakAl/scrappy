"""
Configuration for CodeAgent.

Centralizes all magic numbers and configurable values.
"""

from dataclasses import dataclass, field
from typing import List, Set


@dataclass
class AgentConfig:
    """Configuration settings for CodeAgent."""

    # File operations
    max_file_read_size: int = 10000
    max_file_listing: int = 100
    max_directory_tree_lines: int = 200

    # Command execution
    command_timeout: int = 30
    max_command_output: int = 5000
    dangerous_commands: List[str] = field(
        default_factory=lambda: ['rm -rf', 'del /f', 'format', 'mkfs', '> /dev/', 'sudo']
    )

    # Code search
    max_search_results: int = 50

    # Git operations
    git_timeout: int = 10
    git_diff_timeout: int = 30
    max_git_diff_size: int = 5000
    max_git_blame_size: int = 5000
    max_git_show_size: int = 5000
    max_recent_changes_size: int = 15000
    max_recent_commits: int = 10

    # Directory traversal
    skip_directories: Set[str] = field(
        default_factory=lambda: {
            '.git', '__pycache__', 'node_modules', '.venv',
            'venv', 'env', '.tox', '.pytest_cache'
        }
    )
    allowed_hidden_files: Set[str] = field(
        default_factory=lambda: {'.env', '.gitignore'}
    )

    # Display/UI
    audit_log_result_truncation: int = 500
    result_display_truncation: int = 300
    write_preview_truncation: int = 500

    # LLM settings
    default_max_tokens: int = 1500
    default_temperature: float = 0.3

    # Provider preferences (first available will be used)
    planner_preferences: List[str] = field(
        default_factory=lambda: ['gemini', 'groq']
    )
    executor_preferences: List[str] = field(
        default_factory=lambda: ['cerebras']
    )

    # Completion validation
    meaningful_actions: List[str] = field(
        default_factory=lambda: ['write_file', 'run_command']
    )
