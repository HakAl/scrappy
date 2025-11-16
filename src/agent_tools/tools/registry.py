"""
Tool registry for dynamic tool registration and management.

Provides centralized tool management with auto-generated descriptions.
"""

from typing import Optional

from .base import Tool, ToolContext


class ToolRegistry:
    """
    Registry for managing available tools.

    Features:
    - Dynamic tool registration
    - Auto-generated tool descriptions
    - Tool lookup by name
    - Tool execution wrapper
    """

    def __init__(self):
        """Initialize empty registry."""
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """
        Register a tool in the registry.

        Args:
            tool: Tool instance to register

        Raises:
            ValueError: If tool with same name already exists
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """
        Remove a tool from the registry.

        Args:
            name: Tool name to remove
        """
        if name in self._tools:
            del self._tools[name]

    def get(self, name: str) -> Optional[Tool]:
        """
        Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """
        List all registered tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def list_all(self) -> list[Tool]:
        """
        List all registered tool instances.

        Returns:
            List of Tool objects
        """
        return list(self._tools.values())

    def execute(self, name: str, context: ToolContext, **kwargs) -> str:
        """
        Execute a tool by name.

        Args:
            name: Tool name
            context: ToolContext for execution
            **kwargs: Tool parameters

        Returns:
            Tool output string

        Raises:
            KeyError: If tool not found
        """
        tool = self._tools.get(name)
        if not tool:
            raise KeyError(f"Tool '{name}' not found")

        return tool(context, **kwargs)

    def generate_descriptions(self, numbered: bool = True) -> str:
        """
        Generate formatted descriptions for all tools.

        Args:
            numbered: Whether to number the tools

        Returns:
            Formatted multi-line string with tool descriptions
        """
        lines = ["Available tools:"]

        tools = sorted(self._tools.values(), key=lambda t: t.name)
        for i, tool in enumerate(tools, 1):
            if numbered:
                lines.append(f"{i}. {tool.get_full_description()}")
            else:
                lines.append(f"- {tool.get_full_description()}")

        return "\n".join(lines)

    def get_response_format(self) -> str:
        """
        Get the standard JSON response format for tools.

        Returns:
            String describing expected JSON format
        """
        return """
Response format (JSON):
{
    "thought": "What I'm thinking about the task",
    "action": "tool_name",
    "parameters": {"param1": "value1"},
    "is_complete": false
}

When task is complete:
{
    "thought": "Task completed successfully",
    "action": "complete",
    "result": "Summary of what was done",
    "is_complete": true
}"""

    def get_full_prompt_section(self) -> str:
        """
        Generate complete tool section for LLM prompts.

        Returns:
            String with tools and response format
        """
        return f"{self.generate_descriptions()}\n{self.get_response_format()}"

    @classmethod
    def create_default(cls) -> "ToolRegistry":
        """
        Create a registry with all standard tools registered.

        Returns:
            ToolRegistry with default tools
        """
        from .file_tools import (
            ReadFileTool,
            WriteFileTool,
            ListFilesTool,
            ListDirectoryTool
        )
        from .git_tools import (
            GitLogTool,
            GitDiffTool,
            GitBlameTool,
            GitShowTool,
            GitRecentChangesTool
        )
        from .search_tools import SearchCodeTool

        registry = cls()

        # Register file tools
        registry.register(ReadFileTool())
        registry.register(WriteFileTool())
        registry.register(ListFilesTool())
        registry.register(ListDirectoryTool())

        # Register git tools
        registry.register(GitLogTool())
        registry.register(GitDiffTool())
        registry.register(GitBlameTool())
        registry.register(GitShowTool())
        registry.register(GitRecentChangesTool())

        # Register search tools
        registry.register(SearchCodeTool())

        return registry
