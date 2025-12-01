"""
Factory functions for creating tool registries.

Extracted from CodeAgent._create_default_registry() for:
- Independent testing of registry configuration
- Dependency injection of different registries
- Separation of concerns (configuration vs orchestration)
"""
from typing import Optional, List

from .tools import ToolRegistry
from .tools.file_tools import (
    ReadFileTool,
    WriteFileTool,
    ListFilesTool,
    ListDirectoryTool
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
from .tools.web_tools import WebFetchTool, WebSearchTool
from .tools.python_tools import AnalyzePythonDependenciesTool
from .tools.command_tool import CommandTool
from .tools.control_tools import CompleteTool
from .constants import DEFAULT_COMMAND_TIMEOUT, DEFAULT_MAX_COMMAND_OUTPUT


def create_default_registry(
    command_timeout: int = DEFAULT_COMMAND_TIMEOUT,
    max_command_output: int = DEFAULT_MAX_COMMAND_OUTPUT,
    dangerous_commands: Optional[List[str]] = None,
    include_web: bool = True,
    include_git: bool = True
) -> ToolRegistry:
    """
    Create the default tool registry with all standard tools.

    Args:
        command_timeout: Command execution timeout in seconds
        max_command_output: Maximum command output size in bytes
        dangerous_commands: List of dangerous command patterns to block
        include_web: Include web fetch/search tools (default True)
        include_git: Include git tools (default True)

    Returns:
        Configured ToolRegistry instance
    """
    registry = ToolRegistry()

    # Register file tools (always included)
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(ListFilesTool())
    registry.register(ListDirectoryTool())

    # Register git tools (optional)
    if include_git:
        registry.register(GitLogTool())
        registry.register(GitStatusTool())
        registry.register(GitDiffTool())
        registry.register(GitBlameTool())
        registry.register(GitShowTool())
        registry.register(GitRecentChangesTool())

    # Register search tools
    registry.register(FindExactTextTool())

    # Register web tools (optional)
    if include_web:
        registry.register(WebFetchTool())
        registry.register(WebSearchTool())

    # Register Python tools
    registry.register(AnalyzePythonDependenciesTool())

    # Register command execution tool
    registry.register(CommandTool(
        timeout=command_timeout,
        max_output=max_command_output,
        dangerous_patterns=dangerous_commands or []
    ))

    # Register control tools
    registry.register(CompleteTool())

    return registry


def create_minimal_registry() -> ToolRegistry:
    """
    Create a minimal registry with only core file operations.

    Useful for testing or restricted environments.

    Returns:
        ToolRegistry with minimal tools
    """
    registry = ToolRegistry()

    # Only core file tools
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(ListDirectoryTool())

    return registry
