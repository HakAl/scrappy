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
from typing import TYPE_CHECKING, Dict, List, Optional, Protocol, Union, runtime_checkable

from rich.syntax import Syntax
from rich.text import Text

from scrappy.infrastructure.theme import DEFAULT_THEME

if TYPE_CHECKING:
    from ...agent_config import AgentConfig
    from ...context.protocols import SemanticSearchProtocol
    from ...graph.run_context import AgentRunContextProtocol
    from ...infrastructure.threading.protocols import CancellationTokenProtocol
    from ...protocols.tasks import TaskStorageProtocol


@dataclass
class FileAccess:
    """Record of a file access in the working set.

    Tracks when and how a file was accessed, including line ranges
    to help the LLM understand what portions of a file it has seen.
    """

    path: str
    line_start: Optional[int] = None  # None = full file read
    line_end: Optional[int] = None
    read_turn: Optional[int] = None
    write_turn: Optional[int] = None


class WorkingSet:
    """Tracks files the agent has read/written during the session.

    Used by the HUD to show the agent's "mental focus" - which files
    are currently relevant. Helps prevent hallucinations about file
    contents the agent hasn't actually seen.

    Features:
    - Tracks line ranges to remind LLM it only saw a snippet
    - Limits to most recent N files to manage cognitive load
    - Supports ghost file removal when files are deleted
    """

    def __init__(self, max_files: int = 5) -> None:
        """Initialize working set.

        Args:
            max_files: Maximum number of files to track (oldest dropped).
        """
        self._files: Dict[str, FileAccess] = {}
        self._max_files = max_files

    def record_read(
        self,
        path: str,
        turn: int,
        line_start: Optional[int] = None,
        line_end: Optional[int] = None,
    ) -> None:
        """Record a file read operation.

        Args:
            path: File path (relative to project root).
            turn: Current turn number.
            line_start: Starting line if partial read (1-indexed).
            line_end: Ending line if partial read.
        """
        if path in self._files:
            access = self._files[path]
            access.read_turn = turn
            access.line_start = line_start
            access.line_end = line_end
        else:
            self._files[path] = FileAccess(
                path=path,
                line_start=line_start,
                line_end=line_end,
                read_turn=turn,
            )
        self._enforce_limit()

    def record_write(self, path: str, turn: int) -> None:
        """Record a file write operation.

        Args:
            path: File path (relative to project root).
            turn: Current turn number.
        """
        if path in self._files:
            self._files[path].write_turn = turn
        else:
            self._files[path] = FileAccess(path=path, write_turn=turn)
        self._enforce_limit()

    def remove_deleted(self, path: str) -> None:
        """Remove a file from the working set (ghost file prevention).

        Call this when a file is deleted to prevent the HUD from
        showing files that no longer exist.

        Args:
            path: File path to remove.
        """
        self._files.pop(path, None)

    def get_recent(self) -> List[FileAccess]:
        """Get files ordered by most recent access.

        Returns:
            List of FileAccess objects, most recent first, up to max_files.
        """
        return sorted(
            self._files.values(),
            key=lambda f: max(f.read_turn or 0, f.write_turn or 0),
            reverse=True,
        )[: self._max_files]

    def _enforce_limit(self) -> None:
        """Drop oldest files beyond the limit."""
        while len(self._files) > self._max_files:
            # Find oldest file
            oldest_path = min(
                self._files.keys(),
                key=lambda p: max(
                    self._files[p].read_turn or 0,
                    self._files[p].write_turn or 0,
                ),
            )
            del self._files[oldest_path]


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
    memory access, and HUD state tracking.
    """

    # Paths that are blocked from agent access (security)
    BLOCKED_PATHS = [".git", ".git/", ".git\\"]

    project_root: Path
    dry_run: bool = False
    config: Optional["AgentConfig"] = None
    orchestrator: Optional[MemoryProvider] = None
    semantic_search: Optional["SemanticSearchProtocol"] = None

    # HUD state tracking (session-scoped)
    task_storage: Optional["TaskStorageProtocol"] = None
    working_set: Optional[WorkingSet] = None
    turn: int = 0  # Incremented each iteration by AgentLoop

    # Ephemeral run context (for file caching, status updates)
    run_context: Optional["AgentRunContextProtocol"] = None

    def get_project_root(self) -> Path:
        """Get project root directory."""
        return self.project_root

    def is_safe_path(self, path: str) -> bool:
        """Check if path is within project sandbox and not in blocked paths.

        Uses Path.relative_to() for robust checking that:
        - Handles Windows case-insensitivity correctly
        - Cannot be fooled by sibling directories with similar names
        - Properly resolves symlinks and relative paths
        - Blocks access to sensitive directories like .git/
        """
        # Normalize path for comparison
        normalized = path.replace("\\", "/").lower()

        # Block access to sensitive directories
        for blocked in self.BLOCKED_PATHS:
            blocked_norm = blocked.replace("\\", "/").lower()
            if normalized == blocked_norm or normalized.startswith(blocked_norm.rstrip("/") + "/"):
                return False

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

    @property
    def cancellation_token(self) -> Optional["CancellationTokenProtocol"]:
        """Get cancellation token from run context if available.

        Allows tools to check for user cancellation during long-running operations.
        Returns None if no run_context or no token is set.
        """
        if self.run_context is not None:
            return getattr(self.run_context, "cancellation_token", None)
        return None


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
            return Text(f"Error: {self.error}", style=f"bold {DEFAULT_THEME.error}")

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

            # Array types require 'items' field for Cerebras/Gemini compatibility
            if param.param_type is list:
                param_schema["items"] = {"type": "string"}

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
                if param.param_type is str and not isinstance(value, str):
                    return False, f"Parameter {param.name} must be string"
                elif param.param_type is int and not isinstance(value, int):
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


