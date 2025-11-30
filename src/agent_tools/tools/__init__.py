"""Tool abstractions for the code agent."""

from .base import ToolProtocol, ToolBase, ToolResult, ToolContext, ToolParameter
from .registry import ToolRegistry
from .file_tools import ReadFileTool, WriteFileTool, ListFilesTool, ListDirectoryTool
from .git_tools import GitLogTool, GitDiffTool, GitBlameTool, GitShowTool, GitRecentChangesTool, GitStatusTool
from .search_tools import FindExactTextTool
from .web_tools import WebFetchTool, WebSearchTool
from .control_tools import CompleteTool

__all__ = [
    # Protocol (use for type hints)
    'ToolProtocol',
    # Base class (use for inheritance)
    'ToolBase',
    # Data classes
    'ToolResult',
    'ToolContext',
    'ToolParameter',
    'ToolRegistry',
    # Concrete tools - File operations
    'ReadFileTool',
    'WriteFileTool',
    'ListFilesTool',
    'ListDirectoryTool',
    # Concrete tools - Git operations
    'GitLogTool',
    'GitStatusTool',
    'GitDiffTool',
    'GitBlameTool',
    'GitShowTool',
    'GitRecentChangesTool',
    # Concrete tools - Search
    'FindExactTextTool',
    # Concrete tools - Web
    'WebFetchTool',
    'WebSearchTool',
    # Concrete tools - Control
    'CompleteTool',
]
