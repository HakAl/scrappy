"""
Factory functions for creating tool registries.

Extracted from CodeAgent._create_default_registry() for:
- Independent testing of registry configuration
- Dependency injection of different registries
- Separation of concerns (configuration vs orchestration)
"""
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
from .tools.search_tools import SearchCodeTool
from .tools.web_tools import WebFetchTool, WebSearchTool
from .tools.python_tools import AnalyzePythonDependenciesTool


def create_default_registry(
    include_web: bool = True,
    include_git: bool = True
) -> ToolRegistry:
    """
    Create the default tool registry with all standard tools.

    Args:
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
    registry.register(SearchCodeTool())

    # Register web tools (optional)
    if include_web:
        registry.register(WebFetchTool())
        registry.register(WebSearchTool())

    # Register Python tools
    registry.register(AnalyzePythonDependenciesTool())

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
