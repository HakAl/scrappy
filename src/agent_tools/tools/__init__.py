"""Tool abstractions for the code agent."""

from .base import Tool, ToolResult, ToolContext
from .registry import ToolRegistry
from .file_tools import ReadFileTool, WriteFileTool, ListFilesTool, ListDirectoryTool
from .git_tools import GitLogTool, GitDiffTool, GitBlameTool, GitShowTool, GitRecentChangesTool
from .search_tools import SearchCodeTool
from .web_tools import WebFetchTool, WebSearchTool

__all__ = [
    'Tool',
    'ToolResult',
    'ToolContext',
    'ToolRegistry',
    'ReadFileTool',
    'WriteFileTool',
    'ListFilesTool',
    'ListDirectoryTool',
    'GitLogTool',
    'GitDiffTool',
    'GitBlameTool',
    'GitShowTool',
    'GitRecentChangesTool',
    'SearchCodeTool',
    'WebFetchTool',
    'WebSearchTool',
]
