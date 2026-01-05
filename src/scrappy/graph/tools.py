"""
Tool registry adapter for LangGraph integration.

Wraps the existing ToolRegistry from agent_tools to provide:
- OpenAI-compatible tool schemas for Instructor/function calling
- Execute method for the Execute node (supports multi-tool calls)

This adapter bridges existing tools to work with LangGraph's tool calling
without modifying agent_tools/ internals.
"""

import json
import logging
from typing import Any, Protocol, runtime_checkable

from scrappy.agent_tools.registry_factory import create_default_registry
from scrappy.agent_tools.tools.base import ToolContext
from scrappy.agent_tools.tools.registry import ToolRegistry
from scrappy.graph.state import ToolCall, ToolResult

logger = logging.getLogger(__name__)


@runtime_checkable
class ToolAdapterProtocol(Protocol):
    """
    Protocol for tool adapters.

    Abstracts tool schema generation and execution for LangGraph nodes.
    Enables testing with mock implementations and supports different
    tool registry implementations.

    Implementations:
    - ToolAdapter: Wraps real ToolRegistry for production
    - MockToolAdapter: Returns preset results for testing
    """

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """
        Get OpenAI-compatible tool schemas for function calling.

        Returns:
            List of tool definitions in OpenAI format:
            [{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}]
        """
        ...

    def execute(
        self,
        tool_calls: list[ToolCall],
        context: ToolContext,
    ) -> list[ToolResult]:
        """
        Execute a list of tool calls sequentially.

        Args:
            tool_calls: List of tool calls to execute
            context: ToolContext for tool execution

        Returns:
            List of ToolResult dicts with name, result, and optional error
        """
        ...

    def get_tool_names(self) -> list[str]:
        """
        Get list of available tool names.

        Returns:
            List of registered tool names
        """
        ...


class ToolAdapter:
    """
    Adapter that wraps ToolRegistry for LangGraph integration.

    Provides:
    - get_tool_schemas(): OpenAI-compatible schemas for Instructor
    - execute(): Multi-tool execution for Execute node
    - get_tool_names(): List of available tools

    Example:
        registry = ToolRegistry.create_default()
        adapter = ToolAdapter(registry)

        # Get schemas for LLM
        schemas = adapter.get_tool_schemas()

        # Execute tool calls from LLM response
        results = adapter.execute(tool_calls, context)
    """

    def __init__(self, registry: ToolRegistry) -> None:
        """
        Initialize adapter with a ToolRegistry.

        Args:
            registry: ToolRegistry instance to wrap
        """
        self._registry = registry
        # Cache tool schemas at init - they don't change during session
        # Avoids O(n log n) schema regeneration on every think_node call
        self._cached_schemas: list[dict[str, Any]] | None = None

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """
        Get OpenAI-compatible tool schemas for function calling.

        Returns cached schemas (generated once at first call).
        Tool schemas are immutable during a session.

        Returns:
            List of tool definitions in OpenAI format
        """
        if self._cached_schemas is None:
            self._cached_schemas = self._registry.to_openai_schema()
        return self._cached_schemas

    def execute(
        self,
        tool_calls: list[ToolCall],
        context: ToolContext,
    ) -> list[ToolResult]:
        """
        Execute a list of tool calls sequentially.

        Executes each tool call in order, capturing results and errors.
        Continues executing remaining tools even if one fails.

        Args:
            tool_calls: List of tool calls with id, name, and arguments
            context: ToolContext for tool execution

        Returns:
            List of ToolResult dicts with name and either result or error
        """
        results: list[ToolResult] = []

        for tool_call in tool_calls:
            result = self._execute_single(tool_call, context)
            results.append(result)

        return results

    def _execute_single(
        self,
        tool_call: ToolCall,
        context: ToolContext,
    ) -> ToolResult:
        """
        Execute a single tool call.

        Args:
            tool_call: Tool call in OpenAI format with type, id, and function
            context: ToolContext for tool execution

        Returns:
            ToolResult with name and either result or error
        """
        # Extract from OpenAI format: {"type": "function", "id": "...", "function": {"name": "...", "arguments": "..."}}
        function_data = tool_call.get("function", {})
        tool_name = function_data.get("name", "")

        # Parse arguments (may be JSON string or already parsed)
        arguments = function_data.get("arguments", "{}")
        if isinstance(arguments, str):
            try:
                kwargs = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError as e:
                return ToolResult(
                    name=tool_name,
                    error=f"Invalid arguments JSON: {e}",
                )
        else:
            # Already a dict (shouldn't happen per TypedDict, but handle it)
            kwargs = arguments if arguments else {}

        # Ensure kwargs is a dict (JSON array would parse to list)
        if not isinstance(kwargs, dict):
            return ToolResult(
                name=tool_name,
                error=f"Invalid arguments: expected object, got {type(kwargs).__name__}",
            )

        # Get the tool directly (not via execute() which returns string)
        tool = self._registry.get(tool_name)
        if not tool:
            return ToolResult(
                name=tool_name,
                error=f"Tool '{tool_name}' not found",
            )

        # Validate parameters first
        is_valid, validation_error = tool.validate(**kwargs)
        if not is_valid:
            return ToolResult(
                name=tool_name,
                error=validation_error or "Parameter validation failed",
            )

        # Execute the tool directly to get ToolResult dataclass (not string)
        try:
            tool_result = tool.execute(context, **kwargs)
            # tool_result is a ToolResult dataclass with success, output, error, metadata
            if not tool_result.success:
                result: ToolResult = {
                    "name": tool_name,
                    "error": tool_result.error or tool_result.output or "Tool execution failed",
                }
                if tool_result.metadata:
                    result["metadata"] = tool_result.metadata
                return result
            result = ToolResult(
                name=tool_name,
                result=tool_result.output,
            )
            if tool_result.metadata:
                result["metadata"] = tool_result.metadata
            return result
        except (OSError, IOError, ValueError, TypeError, RuntimeError) as e:
            # Expected errors from tool execution (file ops, validation, etc.)
            logger.debug("Tool '%s' raised expected error: %s", tool_name, e)
            return ToolResult(
                name=tool_name,
                error=str(e),
            )
        except Exception as e:
            # Unexpected error - log at warning level for visibility
            # Tool execution can raise many exception types from external code,
            # so we catch broadly but log to help identify programming bugs
            logger.warning("Tool '%s' raised unexpected error: %s: %s", tool_name, type(e).__name__, e)
            return ToolResult(
                name=tool_name,
                error=str(e),
            )

    def get_tool_names(self) -> list[str]:
        """
        Get list of available tool names.

        Returns:
            List of registered tool names
        """
        return self._registry.list_tools()

    def cleanup(self) -> None:
        """
        Clean up tool resources.

        Calls cleanup on the underlying registry which cleans up
        any tools with resources (e.g., CommandTool's Docker containers).
        """
        self._registry.cleanup()

    @classmethod
    def create_default(cls, profile: str = "full") -> "ToolAdapter":
        """
        Create a ToolAdapter with the default tool registry.

        Convenience factory that creates a registry with all standard tools
        and wraps it in an adapter. Uses registry_factory which includes
        the complete tool for signaling task completion.

        Args:
            profile: Tool profile ("full", "optimized", "minimal")

        Returns:
            ToolAdapter with default tools registered
        """
        registry = create_default_registry(profile=profile)
        return cls(registry)
