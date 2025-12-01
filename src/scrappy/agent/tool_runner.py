"""
Tool runner implementation.

Pure execution logic for running tools from the registry.
"""

from typing import Dict, Any, Callable

from ..agent_tools.tools import ToolRegistry, ToolContext, ToolResult
from ..agent_tools.tools.command_tool import ShellCommandExecutor
from .protocols import ToolRunnerProtocol, ToolRegistryProtocol  # Protocols for type hints (DI)


class ToolRunner:
    """
    Tool execution coordinator.

    Implements ToolRunnerProtocol with registry integration.

    Single Responsibility: Execute tools
    Dependencies: ToolRegistry, ShellCommandExecutor, ToolContext (injected)
    """

    def __init__(
        self,
        tool_registry: ToolRegistryProtocol,
        command_executor: ShellCommandExecutor,
        tool_context: ToolContext,
    ):
        """
        Initialize tool runner.

        Args:
            tool_registry: Registry of available tools (ToolRegistryProtocol for DI)
            command_executor: Executor for shell commands
            tool_context: Context for tool execution
        """
        self.tool_registry = tool_registry
        self.command_executor = command_executor
        self.tool_context = tool_context

        # Build tool mapping from registry
        self.tools: Dict[str, Callable] = {}
        for tool in self.tool_registry.list_all():
            # Create closure that captures tool instance and context
            def make_tool_wrapper(t):
                return lambda **kwargs: t.execute(self.tool_context, **kwargs)
            self.tools[tool.name] = make_tool_wrapper(tool)

        # Special handling for run_command
        self.tools['run_command'] = self._run_command_tool

    def run_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        """
        Execute a tool and return its result.

        Args:
            tool_name: Name of tool to execute
            parameters: Tool-specific parameters

        Returns:
            ToolResult with output, success status, and metadata

        Raises:
            ValueError: If tool not found
        """
        if tool_name not in self.tools:
            available = ', '.join(self.tools.keys())
            raise ValueError(
                f"Unknown tool: {tool_name}. Available tools: {available}"
            )

        try:
            result = self.tools[tool_name](**parameters)
            # Tools return ToolResult - pass it through
            if isinstance(result, ToolResult):
                return result
            # Fallback for legacy tools that return strings
            return ToolResult(success=True, output=str(result))
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _run_command_tool(self, command: str, **kwargs) -> str:
        """
        Special handler for run_command with interactive CLI detection.

        Args:
            command: Shell command to execute

        Returns:
            Command output
        """
        # Check for interactive CLIs that need special handling
        interactive_patterns = ['npx', 'npm create', 'yarn create']
        needs_interaction = any(pattern in command for pattern in interactive_patterns)

        if needs_interaction:
            # Add --yes or equivalent flags
            if 'npx' in command and '--yes' not in command:
                command = command.replace('npx', 'npx --yes')

        # Delegate to command executor
        return self.command_executor.run(
            command,
            cwd=str(self.tool_context.get_project_root())
        )
