"""
Tool management for research tasks.

Handles tool registry creation, tool execution, and tool descriptions.
"""

from pathlib import Path
from typing import Dict, Optional


class ToolBundle:
    """
    Manages tools for research tasks.

    Single responsibility: Provide access to read-only research tools,
    execute tool calls, and provide tool descriptions.
    """

    RESEARCH_TOOLS = [
        'web_fetch',
        'web_search',
        'read_file',
        'list_files',
        'list_directory',
        'search_code',
        'git_log',
        'git_diff',
        'git_blame',
        'git_show',
        'git_recent_changes',
    ]

    def __init__(
        self,
        tool_registry: Optional["ToolRegistry"] = None,
        tool_context: Optional["ToolContext"] = None,
        project_root: Optional[Path] = None
    ):
        """
        Initialize tool bundle.

        Args:
            tool_registry: Tool registry instance (creates default if None)
            tool_context: Tool context instance (creates default if None)
            project_root: Project root directory (for default context creation)
        """
        self._project_root = project_root or Path.cwd()
        self._tool_registry = tool_registry or self._create_default_tool_registry()
        self._tool_context = tool_context or self._create_default_tool_context()

    def has_tools(self) -> bool:
        """Check if tools are available."""
        return self._tool_registry is not None

    def get_tool_descriptions(self) -> str:
        """
        Get formatted descriptions of all available tools.

        Returns:
            Multi-line string with tool descriptions
        """
        if not self._tool_registry:
            return ""

        descriptions = []
        for tool_name in self.RESEARCH_TOOLS:
            tool = self._tool_registry.get(tool_name)
            if tool:
                descriptions.append(f"- {tool.get_full_description()}")

        return "\n".join(descriptions)

    def is_allowed_tool(self, tool_name: str) -> bool:
        """
        Check if a tool is allowed for research tasks.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool is allowed, False otherwise
        """
        return tool_name in self.RESEARCH_TOOLS

    def execute_tool(self, tool_call: Dict[str, object]) -> str:
        """
        Execute a tool call and return the result.

        Args:
            tool_call: Dictionary with 'tool' and 'parameters' keys

        Returns:
            Tool execution result as string
        """
        tool_name = tool_call.get('tool')
        params = tool_call.get('parameters', {})

        if not tool_name:
            return "Error: No tool name specified"

        if not self.is_allowed_tool(tool_name):
            return f"Error: Tool '{tool_name}' is not available for research tasks"

        if not self._tool_registry:
            return "Error: Tool registry not available"

        tool = self._tool_registry.get(tool_name)
        if not tool:
            return f"Error: Tool '{tool_name}' not found"

        try:
            result = tool(self._tool_context, **params)
            # Truncate long results
            if result and len(result) > 10000:
                result = result[:10000] + "\n... [truncated]"
            return result
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    def _create_default_tool_registry(self) -> Optional["ToolRegistry"]:
        """Create default tool registry with read-only tools."""
        try:
            from ..agent_tools.tools import (
                ToolRegistry,
                ReadFileTool,
                ListFilesTool,
                ListDirectoryTool,
                SearchCodeTool,
                GitLogTool,
                GitDiffTool,
                GitBlameTool,
                GitShowTool,
                GitRecentChangesTool,
            )
            from ..agent_tools.tools.web_tools import WebFetchTool, WebSearchTool

            registry = ToolRegistry()
            registry.register(ReadFileTool())
            registry.register(ListFilesTool())
            registry.register(ListDirectoryTool())
            registry.register(SearchCodeTool())
            registry.register(GitLogTool())
            registry.register(GitDiffTool())
            registry.register(GitBlameTool())
            registry.register(GitShowTool())
            registry.register(GitRecentChangesTool())
            registry.register(WebFetchTool())
            registry.register(WebSearchTool())

            return registry
        except ImportError:
            # Tools not available, proceed without them
            return None

    def _create_default_tool_context(self) -> Optional["ToolContext"]:
        """Create default tool context."""
        try:
            from ..agent_tools.tools import ToolContext

            return ToolContext(
                project_root=self._project_root,
                dry_run=False,
                orchestrator=None
            )
        except ImportError:
            # Tools not available, proceed without them
            return None

    @classmethod
    def create_with_orchestrator(
        cls,
        orchestrator: "OrchestratorLike",
        project_root: Optional[Path] = None
    ) -> "ToolBundle":
        """
        Factory method to create ToolBundle with orchestrator integration.

        Args:
            orchestrator: Orchestrator instance for tool context
            project_root: Project root directory

        Returns:
            ToolBundle instance with orchestrator-aware context
        """
        try:
            from ..agent_tools.tools import ToolContext

            context = ToolContext(
                project_root=project_root or Path.cwd(),
                dry_run=False,
                orchestrator=orchestrator if hasattr(orchestrator, 'remember_file_read') else None
            )

            return cls(
                tool_registry=None,  # Will create default
                tool_context=context,
                project_root=project_root
            )
        except ImportError:
            # Tools not available, create without context
            return cls(project_root=project_root)
