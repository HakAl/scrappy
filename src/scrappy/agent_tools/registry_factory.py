"""
Factory functions for creating tool registries with profile support.

Profiles control which tools are presented to the agent:
- full: All 16 tools (backward compatible)
- optimized: 10 tools (40% token savings, production default)
- minimal: 7 tools (maximum token savings)

Tool code is preserved; profiles only change what's registered.
"""
from typing import Optional, List, Callable, Dict, TYPE_CHECKING

from .tools import ToolRegistry
from .tools.base import ToolBase
from .tools.file_tools import (
    ReadFileTool,
    WriteFileTool,
    ListFilesTool,
)
from .tools.git_tools import (
    GitLogTool,
    GitStatusTool,
    GitDiffTool,
    GitBlameTool,
    GitShowTool,
    GitRecentChangesTool
)
from .tools.search_tools import FindExactTextTool
from .tools.semantic_search_tool import SemanticSearchTool
from .tools.web_tools import WebFetchTool, WebSearchTool
from .tools.command_tool import CommandTool
from .tools.control_tools import CompleteTool
from .tools.task_tools import TaskTool
from .tools.testing_tools import RunTestsTool
from .constants import DEFAULT_COMMAND_TIMEOUT, DEFAULT_MAX_COMMAND_OUTPUT

if TYPE_CHECKING:
    from ..context.protocols import SemanticSearchProtocol


# Tool profiles define which tools are available to the agent
# Tools not in profile are still in codebase but not registered
TOOL_PROFILES: Dict[str, List[str]] = {
    "full": [
        # All 17 tools - backward compatible
        "read_file", "write_file", "list_files",
        "git_log", "git_status", "git_diff", "git_blame", "git_show", "git_recent_changes",
        "find_exact_text", "codebase_search",
        "web_fetch", "web_search",
        "run_command", "run_tests",
        "complete",
        "task",
    ],
    "optimized": [
        # 10 tools - 40% token savings, production default
        # Agent uses run_command for git_log, git_blame, git_show, git_recent_changes
        # Agent uses web_fetch for web_search functionality
        # Task management via system prompt or TODO.md
        "read_file", "write_file", "list_files",
        "git_status", "git_diff",
        "find_exact_text", "codebase_search",
        "web_fetch",
        "run_command",
        "complete",
    ],
    "minimal": [
        # 7 tools - maximum token savings
        # Only essential tools, agent relies heavily on run_command
        "read_file", "write_file", "list_files",
        "codebase_search",
        "git_status",
        "run_command",
        "complete",
    ],
}


def get_available_profiles() -> List[str]:
    """Return list of available profile names."""
    return list(TOOL_PROFILES.keys())


def get_profile_tools(profile: str) -> List[str]:
    """Return list of tool names for a profile."""
    if profile not in TOOL_PROFILES:
        raise ValueError(f"Unknown profile '{profile}'. Available: {get_available_profiles()}")
    return TOOL_PROFILES[profile].copy()


def create_registry_with_profile(
    profile: str = "full",
    command_timeout: int = DEFAULT_COMMAND_TIMEOUT,
    max_command_output: int = DEFAULT_MAX_COMMAND_OUTPUT,
    dangerous_commands: Optional[List[str]] = None,
    semantic_search: Optional['SemanticSearchProtocol'] = None,
) -> ToolRegistry:
    """
    Create a tool registry with the specified profile.

    Args:
        profile: Tool profile name ("full", "optimized", "minimal")
        command_timeout: Command execution timeout in seconds
        max_command_output: Maximum command output size in bytes
        dangerous_commands: List of dangerous command patterns to block
        semantic_search: Optional semantic search provider for codebase_search

    Returns:
        Configured ToolRegistry with tools from the specified profile

    Raises:
        ValueError: If profile name is not recognized
    """
    if profile not in TOOL_PROFILES:
        raise ValueError(f"Unknown profile '{profile}'. Available: {get_available_profiles()}")

    # Tool factories - create tool instances on demand
    tool_factories: Dict[str, Callable[[], ToolBase]] = {
        # File tools
        "read_file": lambda: ReadFileTool(),
        "write_file": lambda: WriteFileTool(),
        "list_files": lambda: ListFilesTool(),
        # Git tools
        "git_log": lambda: GitLogTool(),
        "git_status": lambda: GitStatusTool(),
        "git_diff": lambda: GitDiffTool(),
        "git_blame": lambda: GitBlameTool(),
        "git_show": lambda: GitShowTool(),
        "git_recent_changes": lambda: GitRecentChangesTool(),
        # Search tools
        "find_exact_text": lambda: FindExactTextTool(),
        "codebase_search": lambda: SemanticSearchTool(semantic_search=semantic_search),
        # Web tools
        "web_fetch": lambda: WebFetchTool(),
        "web_search": lambda: WebSearchTool(),
        # Command tool
        "run_command": lambda: CommandTool(
            timeout=command_timeout,
            max_output=max_command_output,
            dangerous_patterns=dangerous_commands or []
        ),
        # Testing tool
        "run_tests": lambda: RunTestsTool(timeout=command_timeout),
        # Control tools
        "complete": lambda: CompleteTool(),
        # Task tools
        "task": lambda: TaskTool(),
    }

    registry = ToolRegistry()
    profile_tools = TOOL_PROFILES[profile]

    for tool_name in profile_tools:
        if tool_name in tool_factories:
            registry.register(tool_factories[tool_name]())

    return registry


def create_default_registry(
    command_timeout: int = DEFAULT_COMMAND_TIMEOUT,
    max_command_output: int = DEFAULT_MAX_COMMAND_OUTPUT,
    dangerous_commands: Optional[List[str]] = None,
    include_web: bool = True,
    include_git: bool = True,
    semantic_search: Optional['SemanticSearchProtocol'] = None,
    profile: str = "full",
) -> ToolRegistry:
    """
    Create the default tool registry with all standard tools.

    Args:
        command_timeout: Command execution timeout in seconds
        max_command_output: Maximum command output size in bytes
        dangerous_commands: List of dangerous command patterns to block
        include_web: Include web fetch/search tools (default True) - ignored if profile set
        include_git: Include git tools (default True) - ignored if profile set
        semantic_search: Optional semantic search provider for codebase_search tool
        profile: Tool profile ("full", "optimized", "minimal"). Default "full" for backward compat.

    Returns:
        Configured ToolRegistry instance
    """
    # Use profile-based creation
    return create_registry_with_profile(
        profile=profile,
        command_timeout=command_timeout,
        max_command_output=max_command_output,
        dangerous_commands=dangerous_commands,
        semantic_search=semantic_search,
    )


def create_minimal_registry() -> ToolRegistry:
    """
    Create a minimal registry with only core file operations.

    Useful for testing or restricted environments.

    Returns:
        ToolRegistry with minimal tools
    """
    return create_registry_with_profile(profile="minimal")
