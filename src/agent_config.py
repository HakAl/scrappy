"""
Configuration for CodeAgent.

Centralizes all magic numbers and configurable values.
"""

from dataclasses import dataclass, field
from typing import List, Set

from .platform_utils import get_dangerous_commands, get_interactive_commands
from .infrastructure.config import BaseConfig


@dataclass
class AgentConfig(BaseConfig):
    """Configuration settings for CodeAgent."""

    # File operations
    max_file_read_size: int = 10000
    max_file_listing: int = 100
    max_directory_tree_lines: int = 200

    # Command execution
    command_timeout: int = 300  # 5 minutes for long-running commands
    max_command_output: int = 10000
    dangerous_commands: List[str] = field(
        default_factory=get_dangerous_commands
    )
    # Commands known to be long-running (pattern matches)
    long_running_commands: List[str] = field(
        default_factory=lambda: [
            'create-react-app', 'npm install', 'pip install', 'cargo build',
            'docker build', 'npm run build', 'yarn install', 'pnpm install'
        ]
    )
    # Commands that may prompt for input (should warn user)
    interactive_commands: List[str] = field(
        default_factory=get_interactive_commands
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
    # NOTE: GitHub Models excluded from planner due to aggressive rate limiting
    # (crashes after ~10 requests, unsuitable for multi-step agent tasks)
    # Cerebras llama-3.3-70b preferred for planning (best quality/speed balance)
    # Groq llama-4-scout-17b-16e-instruct as secondary option
    planner_preferences: List[str] = field(
        default_factory=lambda: ['cerebras', 'groq', 'gemini']
    )
    executor_preferences: List[str] = field(
        default_factory=lambda: ['cerebras', 'groq']
    )

    # Completion validation
    meaningful_actions: List[str] = field(
        default_factory=lambda: ['write_file', 'run_command']
    )

    def validate(self) -> None:
        """
        Validate AgentConfig values.

        Raises:
            ValueError: If configuration is invalid
        """
        super().validate()

        # Validate file operations
        if self.max_file_read_size <= 0:
            raise ValueError(
                f"max_file_read_size must be positive, got {self.max_file_read_size}"
            )

        if self.max_file_listing <= 0:
            raise ValueError(
                f"max_file_listing must be positive, got {self.max_file_listing}"
            )

        if self.max_directory_tree_lines <= 0:
            raise ValueError(
                f"max_directory_tree_lines must be positive, got {self.max_directory_tree_lines}"
            )

        # Validate command execution
        if self.command_timeout <= 0:
            raise ValueError(
                f"command_timeout must be positive, got {self.command_timeout}"
            )

        if self.max_command_output <= 0:
            raise ValueError(
                f"max_command_output must be positive, got {self.max_command_output}"
            )

        # Validate git operations
        if self.git_timeout <= 0:
            raise ValueError(
                f"git_timeout must be positive, got {self.git_timeout}"
            )

        if self.git_diff_timeout <= 0:
            raise ValueError(
                f"git_diff_timeout must be positive, got {self.git_diff_timeout}"
            )

        # Validate LLM settings
        if self.default_max_tokens <= 0:
            raise ValueError(
                f"default_max_tokens must be positive, got {self.default_max_tokens}"
            )

        if not (0.0 <= self.default_temperature <= 2.0):
            raise ValueError(
                f"default_temperature must be between 0.0 and 2.0, got {self.default_temperature}"
            )

        # Validate provider preferences
        if not self.planner_preferences:
            raise ValueError("planner_preferences cannot be empty")

        if not self.executor_preferences:
            raise ValueError("executor_preferences cannot be empty")
