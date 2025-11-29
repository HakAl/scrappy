"""
Configuration for CodeAgent.

Uses @property decorators for encapsulation and automatic validation.
All defaults come from agent_tools.constants for consistency.
"""

from dataclasses import dataclass, field
from typing import List, Set

from src.platform import get_dangerous_commands, get_interactive_commands
from .infrastructure.config import BaseConfig
from .agent_tools.constants import (
    DEFAULT_MAX_FILE_READ_SIZE,
    DEFAULT_MAX_FILE_LISTING,
    DEFAULT_MAX_DIRECTORY_TREE_LINES,
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_MAX_COMMAND_OUTPUT,
    DEFAULT_LONG_RUNNING_COMMANDS,
    DEFAULT_MAX_SEARCH_RESULTS,
    DEFAULT_GIT_TIMEOUT,
    DEFAULT_GIT_DIFF_TIMEOUT,
    DEFAULT_MAX_GIT_DIFF_SIZE,
    DEFAULT_MAX_GIT_BLAME_SIZE,
    DEFAULT_MAX_GIT_SHOW_SIZE,
    DEFAULT_MAX_RECENT_CHANGES_SIZE,
    DEFAULT_MAX_RECENT_COMMITS,
    DEFAULT_SKIP_DIRECTORIES,
    DEFAULT_ALLOWED_HIDDEN_FILES,
    DEFAULT_AUDIT_LOG_RESULT_TRUNCATION,
    DEFAULT_RESULT_DISPLAY_TRUNCATION,
    DEFAULT_WRITE_PREVIEW_TRUNCATION,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_PLANNER_PREFERENCES,
    DEFAULT_EXECUTOR_PREFERENCES,
    DEFAULT_MEANINGFUL_ACTIONS,
)


@dataclass
class AgentConfig(BaseConfig):
    """
    Configuration settings for CodeAgent.

    All fields are accessed via @property decorators which provide:
    - Encapsulation of internal state
    - Automatic validation on write
    - Consistent defaults from constants module
    """

    # Private fields - do not access directly
    _max_file_read_size: int = field(default=DEFAULT_MAX_FILE_READ_SIZE, init=False, repr=False)
    _max_file_listing: int = field(default=DEFAULT_MAX_FILE_LISTING, init=False, repr=False)
    _max_directory_tree_lines: int = field(default=DEFAULT_MAX_DIRECTORY_TREE_LINES, init=False, repr=False)
    _command_timeout: int = field(default=DEFAULT_COMMAND_TIMEOUT, init=False, repr=False)
    _max_command_output: int = field(default=DEFAULT_MAX_COMMAND_OUTPUT, init=False, repr=False)
    _dangerous_commands: List[str] = field(default_factory=get_dangerous_commands, init=False, repr=False)
    _long_running_commands: List[str] = field(default_factory=lambda: DEFAULT_LONG_RUNNING_COMMANDS.copy(), init=False, repr=False)
    _interactive_commands: List[str] = field(default_factory=get_interactive_commands, init=False, repr=False)
    _max_search_results: int = field(default=DEFAULT_MAX_SEARCH_RESULTS, init=False, repr=False)
    _git_timeout: int = field(default=DEFAULT_GIT_TIMEOUT, init=False, repr=False)
    _git_diff_timeout: int = field(default=DEFAULT_GIT_DIFF_TIMEOUT, init=False, repr=False)
    _max_git_diff_size: int = field(default=DEFAULT_MAX_GIT_DIFF_SIZE, init=False, repr=False)
    _max_git_blame_size: int = field(default=DEFAULT_MAX_GIT_BLAME_SIZE, init=False, repr=False)
    _max_git_show_size: int = field(default=DEFAULT_MAX_GIT_SHOW_SIZE, init=False, repr=False)
    _max_recent_changes_size: int = field(default=DEFAULT_MAX_RECENT_CHANGES_SIZE, init=False, repr=False)
    _max_recent_commits: int = field(default=DEFAULT_MAX_RECENT_COMMITS, init=False, repr=False)
    _skip_directories: Set[str] = field(default_factory=lambda: DEFAULT_SKIP_DIRECTORIES.copy(), init=False, repr=False)
    _allowed_hidden_files: Set[str] = field(default_factory=lambda: DEFAULT_ALLOWED_HIDDEN_FILES.copy(), init=False, repr=False)
    _audit_log_result_truncation: int = field(default=DEFAULT_AUDIT_LOG_RESULT_TRUNCATION, init=False, repr=False)
    _result_display_truncation: int = field(default=DEFAULT_RESULT_DISPLAY_TRUNCATION, init=False, repr=False)
    _write_preview_truncation: int = field(default=DEFAULT_WRITE_PREVIEW_TRUNCATION, init=False, repr=False)
    _default_max_tokens: int = field(default=DEFAULT_MAX_TOKENS, init=False, repr=False)
    _default_temperature: float = field(default=DEFAULT_TEMPERATURE, init=False, repr=False)
    _planner_preferences: List[str] = field(default_factory=lambda: DEFAULT_PLANNER_PREFERENCES.copy(), init=False, repr=False)
    _executor_preferences: List[str] = field(default_factory=lambda: DEFAULT_EXECUTOR_PREFERENCES.copy(), init=False, repr=False)
    _meaningful_actions: List[str] = field(default_factory=lambda: DEFAULT_MEANINGFUL_ACTIONS.copy(), init=False, repr=False)

    # File operations
    @property
    def max_file_read_size(self) -> int:
        """Maximum file read size in bytes."""
        return self._max_file_read_size

    @max_file_read_size.setter
    def max_file_read_size(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"max_file_read_size must be positive, got {value}")
        self._max_file_read_size = value

    @property
    def max_file_listing(self) -> int:
        """Maximum number of files to list."""
        return self._max_file_listing

    @max_file_listing.setter
    def max_file_listing(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"max_file_listing must be positive, got {value}")
        self._max_file_listing = value

    @property
    def max_directory_tree_lines(self) -> int:
        """Maximum lines in directory tree output."""
        return self._max_directory_tree_lines

    @max_directory_tree_lines.setter
    def max_directory_tree_lines(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"max_directory_tree_lines must be positive, got {value}")
        self._max_directory_tree_lines = value

    # Command execution
    @property
    def command_timeout(self) -> int:
        """Command execution timeout in seconds."""
        return self._command_timeout

    @command_timeout.setter
    def command_timeout(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"command_timeout must be positive, got {value}")
        self._command_timeout = value

    @property
    def max_command_output(self) -> int:
        """Maximum command output size in bytes."""
        return self._max_command_output

    @max_command_output.setter
    def max_command_output(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"max_command_output must be positive, got {value}")
        self._max_command_output = value

    @property
    def dangerous_commands(self) -> List[str]:
        """List of dangerous command patterns to block."""
        return self._dangerous_commands

    @dangerous_commands.setter
    def dangerous_commands(self, value: List[str]) -> None:
        if not isinstance(value, list):
            raise TypeError(f"dangerous_commands must be a list, got {type(value)}")
        self._dangerous_commands = value

    @property
    def long_running_commands(self) -> List[str]:
        """List of known long-running command patterns."""
        return self._long_running_commands

    @long_running_commands.setter
    def long_running_commands(self, value: List[str]) -> None:
        if not isinstance(value, list):
            raise TypeError(f"long_running_commands must be a list, got {type(value)}")
        self._long_running_commands = value

    @property
    def interactive_commands(self) -> List[str]:
        """List of commands that may prompt for input."""
        return self._interactive_commands

    @interactive_commands.setter
    def interactive_commands(self, value: List[str]) -> None:
        if not isinstance(value, list):
            raise TypeError(f"interactive_commands must be a list, got {type(value)}")
        self._interactive_commands = value

    # Code search
    @property
    def max_search_results(self) -> int:
        """Maximum number of search results to return."""
        return self._max_search_results

    @max_search_results.setter
    def max_search_results(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"max_search_results must be positive, got {value}")
        self._max_search_results = value

    # Git operations
    @property
    def git_timeout(self) -> int:
        """Git operation timeout in seconds."""
        return self._git_timeout

    @git_timeout.setter
    def git_timeout(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"git_timeout must be positive, got {value}")
        self._git_timeout = value

    @property
    def git_diff_timeout(self) -> int:
        """Git diff operation timeout in seconds."""
        return self._git_diff_timeout

    @git_diff_timeout.setter
    def git_diff_timeout(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"git_diff_timeout must be positive, got {value}")
        self._git_diff_timeout = value

    @property
    def max_git_diff_size(self) -> int:
        """Maximum git diff output size in bytes."""
        return self._max_git_diff_size

    @max_git_diff_size.setter
    def max_git_diff_size(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"max_git_diff_size must be positive, got {value}")
        self._max_git_diff_size = value

    @property
    def max_git_blame_size(self) -> int:
        """Maximum git blame output size in bytes."""
        return self._max_git_blame_size

    @max_git_blame_size.setter
    def max_git_blame_size(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"max_git_blame_size must be positive, got {value}")
        self._max_git_blame_size = value

    @property
    def max_git_show_size(self) -> int:
        """Maximum git show output size in bytes."""
        return self._max_git_show_size

    @max_git_show_size.setter
    def max_git_show_size(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"max_git_show_size must be positive, got {value}")
        self._max_git_show_size = value

    @property
    def max_recent_changes_size(self) -> int:
        """Maximum git recent changes output size in bytes."""
        return self._max_recent_changes_size

    @max_recent_changes_size.setter
    def max_recent_changes_size(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"max_recent_changes_size must be positive, got {value}")
        self._max_recent_changes_size = value

    @property
    def max_recent_commits(self) -> int:
        """Maximum number of recent commits to fetch."""
        return self._max_recent_commits

    @max_recent_commits.setter
    def max_recent_commits(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"max_recent_commits must be positive, got {value}")
        self._max_recent_commits = value

    # Directory traversal
    @property
    def skip_directories(self) -> Set[str]:
        """Set of directory names to skip during traversal."""
        return self._skip_directories

    @skip_directories.setter
    def skip_directories(self, value: Set[str]) -> None:
        if not isinstance(value, set):
            raise TypeError(f"skip_directories must be a set, got {type(value)}")
        self._skip_directories = value

    @property
    def allowed_hidden_files(self) -> Set[str]:
        """Set of hidden file names that are allowed."""
        return self._allowed_hidden_files

    @allowed_hidden_files.setter
    def allowed_hidden_files(self, value: Set[str]) -> None:
        if not isinstance(value, set):
            raise TypeError(f"allowed_hidden_files must be a set, got {type(value)}")
        self._allowed_hidden_files = value

    # Display/UI
    @property
    def audit_log_result_truncation(self) -> int:
        """Maximum length for audit log result display in characters."""
        return self._audit_log_result_truncation

    @audit_log_result_truncation.setter
    def audit_log_result_truncation(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"audit_log_result_truncation must be positive, got {value}")
        self._audit_log_result_truncation = value

    @property
    def result_display_truncation(self) -> int:
        """Maximum length for result display in characters."""
        return self._result_display_truncation

    @result_display_truncation.setter
    def result_display_truncation(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"result_display_truncation must be positive, got {value}")
        self._result_display_truncation = value

    @property
    def write_preview_truncation(self) -> int:
        """Maximum length for write preview in characters."""
        return self._write_preview_truncation

    @write_preview_truncation.setter
    def write_preview_truncation(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"write_preview_truncation must be positive, got {value}")
        self._write_preview_truncation = value

    # LLM settings
    @property
    def default_max_tokens(self) -> int:
        """Default maximum tokens for LLM responses."""
        return self._default_max_tokens

    @default_max_tokens.setter
    def default_max_tokens(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"default_max_tokens must be positive, got {value}")
        self._default_max_tokens = value

    @property
    def default_temperature(self) -> float:
        """Default temperature for LLM responses."""
        return self._default_temperature

    @default_temperature.setter
    def default_temperature(self, value: float) -> None:
        if not (0.0 <= value <= 2.0):
            raise ValueError(f"default_temperature must be between 0.0 and 2.0, got {value}")
        self._default_temperature = value

    # Provider preferences
    @property
    def planner_preferences(self) -> List[str]:
        """Ordered list of preferred providers for planning."""
        return self._planner_preferences

    @planner_preferences.setter
    def planner_preferences(self, value: List[str]) -> None:
        if not isinstance(value, list):
            raise TypeError(f"planner_preferences must be a list, got {type(value)}")
        if not value:
            raise ValueError("planner_preferences cannot be empty")
        self._planner_preferences = value

    @property
    def executor_preferences(self) -> List[str]:
        """Ordered list of preferred providers for execution."""
        return self._executor_preferences

    @executor_preferences.setter
    def executor_preferences(self, value: List[str]) -> None:
        if not isinstance(value, list):
            raise TypeError(f"executor_preferences must be a list, got {type(value)}")
        if not value:
            raise ValueError("executor_preferences cannot be empty")
        self._executor_preferences = value

    # Completion validation
    @property
    def meaningful_actions(self) -> List[str]:
        """List of action names considered meaningful for completion validation."""
        return self._meaningful_actions

    @meaningful_actions.setter
    def meaningful_actions(self, value: List[str]) -> None:
        if not isinstance(value, list):
            raise TypeError(f"meaningful_actions must be a list, got {type(value)}")
        self._meaningful_actions = value

    def validate(self) -> None:
        """
        Validate AgentConfig values.

        Note: With @property setters, most validation happens automatically.
        This method is kept for BaseConfig compatibility and any cross-field validation.

        Raises:
            ValueError: If configuration is invalid
        """
        super().validate()
        # All single-field validation now happens in setters
        # This method can be used for cross-field validation if needed
