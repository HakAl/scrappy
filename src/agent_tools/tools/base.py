"""
Base tool abstraction for the code agent.

Provides a clean interface for creating tools with automatic
parameter validation and description generation.

Architecture:
- ToolProtocol: Defines the contract (what tools MUST implement)
- ToolBase: Optional base class with shared utilities (tools MAY extend)
- Tool: Legacy alias for backward compatibility (use ToolBase instead)
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Protocol, Union, runtime_checkable

from rich.syntax import Syntax
from rich.text import Text

if TYPE_CHECKING:
    from ...agent_config import AgentConfig


class MemoryProvider(Protocol):
    """Protocol for memory operations in tools."""

    def remember_file_read(self, path: str, content: str, lines: int) -> None:
        """Store file read in working memory."""
        ...

    def remember_search(self, query: str, results: list) -> None:
        """Store search results in working memory."""
        ...

    def remember_git_operation(self, operation: str, result: str) -> None:
        """Store git operation result in working memory."""
        ...


@dataclass
class ToolContext:
    """
    Context provided to tools during execution.

    Contains shared resources like project path, configuration,
    and memory access.
    """

    project_root: Path
    dry_run: bool = False
    config: Optional["AgentConfig"] = None
    orchestrator: Optional[MemoryProvider] = None

    def is_safe_path(self, path: str) -> bool:
        """Check if path is within project sandbox.

        Uses Path.relative_to() for robust checking that:
        - Handles Windows case-insensitivity correctly
        - Cannot be fooled by sibling directories with similar names
        - Properly resolves symlinks and relative paths
        """
        try:
            target = (self.project_root / path).resolve()
            project_abs = self.project_root.resolve()
            # relative_to raises ValueError if target is not relative to project_abs
            target.relative_to(project_abs)
            return True
        except (ValueError, Exception):
            return False

    def remember_file_read(self, path: str, content: str, lines: int):
        """Store file read in working memory."""
        if self.orchestrator:
            self.orchestrator.working_memory.remember_file_read(path, content, lines)

    def remember_search(self, query: str, results: list):
        """Store search results in working memory."""
        if self.orchestrator:
            self.orchestrator.working_memory.remember_search(query, results)

    def remember_git_operation(self, operation: str, result: str):
        """Store git operation result in working memory."""
        if self.orchestrator:
            self.orchestrator.working_memory.remember_git_operation(operation, result)


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""

    name: str
    param_type: type
    description: str
    required: bool = True
    default: object = None


@dataclass
class ToolResult:
    """Result of a tool execution."""

    success: bool
    output: str
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def __str__(self) -> str:
        """Return human-readable output for display.

        Returns error message if present, otherwise the output string.
        This avoids escaped newlines and dataclass repr noise.
        """
        if self.error:
            return f"Error: {self.error}"
        return self.output

    def __rich__(self) -> Union[Text, Syntax]:
        """Rich-compatible rendering with syntax highlighting.

        Rich's console automatically calls this when printing.
        """
        if self.error:
            return Text(f"Error: {self.error}", style="bold red")

        # Detect language from metadata
        language = self.metadata.get("language", "text")

        # Use syntax highlighting for code with multiple lines
        if language != "text" and "\n" in self.output:
            return Syntax(
                self.output,
                language,
                theme="monokai",
                line_numbers=True,
            )

        return Text(self.output)


@runtime_checkable
class ToolProtocol(Protocol):
    """
    Protocol defining the contract for agent tools.

    This is the minimal interface that ALL tools MUST implement.
    Use this for type hints and dependency injection.

    Tools implementing this protocol must provide:
    - name: Tool identifier
    - description: Human-readable description
    - parameters: List of ToolParameter definitions
    - execute(): Core execution logic
    """

    @property
    def name(self) -> str:
        """Unique identifier for the tool."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description of what the tool does."""
        ...

    @property
    def parameters(self) -> list[ToolParameter]:
        """List of parameters this tool accepts."""
        ...

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        """
        Execute the tool with given parameters.

        Args:
            context: ToolContext with shared resources
            **kwargs: Tool-specific parameters

        Returns:
            ToolResult with success status and output
        """
        ...


class ToolBase:
    """
    Optional base class for agent tools with shared utilities.

    Provides default implementations for common functionality.
    Tools MAY extend this class to get these utilities for free,
    but they don't have to - they only need to satisfy ToolProtocol.

    Includes:
    - Parameter schema generation (OpenAI-compatible JSON)
    - Parameter validation
    - Signature generation
    - Description formatting
    - __call__ convenience method
    """

    @property
    def name(self) -> str:
        """Unique identifier for the tool. MUST be overridden."""
        raise NotImplementedError("Subclasses must implement 'name' property")

    @property
    def description(self) -> str:
        """Human-readable description of what the tool does. MUST be overridden."""
        raise NotImplementedError("Subclasses must implement 'description' property")

    @property
    def parameters(self) -> list[ToolParameter]:
        """List of parameters this tool accepts. MUST be overridden."""
        raise NotImplementedError("Subclasses must implement 'parameters' property")

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        """Execute the tool with given parameters. MUST be overridden."""
        raise NotImplementedError("Subclasses must implement 'execute' method")

    @property
    def parameters_schema(self) -> dict:
        """
        Get OpenAI-compatible JSON schema for tool parameters.

        Can be overridden by subclasses for custom schemas.
        Default implementation converts ToolParameter list to JSON schema.

        Returns:
            Dict representing JSON schema for parameters
        """
        properties = {}
        required = []

        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object"
        }

        for param in self.parameters:
            param_schema = {
                "type": type_map.get(param.param_type, "string"),
                "description": param.description
            }
            properties[param.name] = param_schema

            if param.required:
                required.append(param.name)

        return {
            "type": "object",
            "properties": properties,
            "required": required
        }

    def validate(self, **kwargs) -> tuple[bool, Optional[str]]:
        """
        Validate parameters before execution.

        Returns:
            Tuple of (is_valid, error_message)
        """
        for param in self.parameters:
            if param.required and param.name not in kwargs:
                return False, f"Missing required parameter: {param.name}"

            if param.name in kwargs:
                value = kwargs[param.name]
                # Type checking (basic)
                if param.param_type == str and not isinstance(value, str):
                    return False, f"Parameter {param.name} must be string"
                elif param.param_type == int and not isinstance(value, int):
                    return False, f"Parameter {param.name} must be integer"

        return True, None

    def get_signature(self) -> str:
        """
        Generate function signature string.

        Returns:
            String like "tool_name(param1: str, param2: int = 10)"
        """
        params = []
        for p in self.parameters:
            if p.required:
                params.append(f"{p.name}: {p.param_type.__name__}")
            else:
                default_repr = repr(p.default) if isinstance(p.default, str) else str(p.default)
                params.append(f"{p.name}: {p.param_type.__name__} = {default_repr}")

        return f"{self.name}({', '.join(params)})"

    def get_full_description(self) -> str:
        """
        Generate complete tool description for LLM.

        Returns:
            String with signature and description
        """
        return f"{self.get_signature()} - {self.description}"

    def __call__(self, context: ToolContext, **kwargs) -> str:
        """
        Convenience method to execute tool.

        Validates parameters and returns output string directly.
        Raises ValueError on validation failure.
        """
        is_valid, error = self.validate(**kwargs)
        if not is_valid:
            return f"Error: {error}"

        result = self.execute(context, **kwargs)
        if result.success:
            return result.output
        else:
            return f"Error: {result.error or result.output}"


