"""
Agent component protocols.

Defines abstract interfaces for agent components including audit logging,
response parsing, prompt building, tool management, and checkpointing.
"""

from typing import Protocol, Dict, Any, List, Optional, Callable, runtime_checkable
from pathlib import Path
from datetime import datetime


@runtime_checkable
class AuditLoggerProtocol(Protocol):
    """
    Protocol for audit logging.

    Abstracts audit logging to enable testing without file I/O
    and support different logging strategies.

    Implementations:
    - AuditLogger: File-based audit logging
    - InMemoryAuditLogger: In-memory logging for testing
    - NullAuditor: No-op auditor for testing

    Example:
        def log_action(auditor: AuditLoggerProtocol, action: str, result: Any) -> None:
            auditor.log_action(action, {"status": "success"})
            auditor.log_result(result)
    """

    def log_action(
        self,
        action: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log an action.

        Args:
            action: Action description
            metadata: Optional action metadata
        """
        ...

    def log_result(
        self,
        result: Any,
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log action result.

        Args:
            result: Result data
            success: Whether action succeeded
            metadata: Optional result metadata
        """
        ...

    def get_history(
        self,
        limit: Optional[int] = None,
        filter_by: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get audit history.

        Args:
            limit: Maximum entries to return
            filter_by: Filter criteria

        Returns:
            List of audit log entries
        """
        ...

    def export(self, format: str = "json") -> str:
        """
        Export audit log in specified format.

        Args:
            format: Export format (json, csv, etc.)

        Returns:
            Formatted audit log
        """
        ...

    def clear(self) -> None:
        """
        Clear audit log.
        """
        ...


@runtime_checkable
class ResponseParserProtocol(Protocol):
    """
    Protocol for response parsing.

    Abstracts LLM response parsing to enable testing with controlled
    responses and support different parsing strategies.

    Implementations:
    - UnifiedResponseParser: Auto-detects format (JSON/native tools)
    - JSONResponseParser: Parses JSON-formatted responses
    - NativeToolParser: Parses native tool call responses
    - MockParser: Returns preset parse results for testing

    Example:
        def parse_response(parser: ResponseParserProtocol, text: str) -> List[Dict[str, Any]]:
            result = parser.parse(text)
            return result.actions
    """

    def parse(self, response_text: str) -> Any:
        """
        Parse LLM response into structured format.

        Args:
            response_text: Raw LLM response text

        Returns:
            Parsed result object containing:
            - thoughts: List of agent thoughts
            - actions: List of actions to execute
            - raw_text: Original response text
        """
        ...

    def extract_actions(self, response_text: str) -> List[Dict[str, Any]]:
        """
        Extract actions from response.

        Args:
            response_text: Raw LLM response text

        Returns:
            List of action dictionaries
        """
        ...

    def validate(self, response_text: str) -> bool:
        """
        Validate response format.

        Args:
            response_text: Raw LLM response text

        Returns:
            True if response is valid, False otherwise
        """
        ...


@runtime_checkable
class PromptBuilderProtocol(Protocol):
    """
    Protocol for prompt construction.

    Abstracts prompt building to enable testing with controlled
    prompts and support different prompt strategies.

    Implementations:
    - PromptBuilder: Full prompt construction with templates
    - SimplePromptBuilder: Basic prompt building for testing
    - TemplatePromptBuilder: Template-based prompt construction

    Example:
        def build_query(builder: PromptBuilderProtocol, task: str) -> str:
            builder.add_context("Project: My App")
            return builder.build(task)
    """

    def build(
        self,
        task: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Build prompt from task and context.

        Args:
            task: Task description
            system_prompt: Optional system prompt

        Returns:
            Formatted prompt string
        """
        ...

    def add_context(self, context: str) -> None:
        """
        Add context to prompt.

        Args:
            context: Context information to include
        """
        ...

    def add_examples(self, examples: List[Dict[str, str]]) -> None:
        """
        Add examples to prompt.

        Args:
            examples: List of example dictionaries with 'input' and 'output'
        """
        ...

    def clear_context(self) -> None:
        """
        Clear all context.
        """
        ...

    def set_template(self, template: str) -> None:
        """
        Set prompt template.

        Args:
            template: Prompt template with placeholders
        """
        ...


@runtime_checkable
class ToolRegistryProtocol(Protocol):
    """
    Protocol for tool registry.

    Abstracts tool registration and execution to enable testing
    with mock tools and support different tool sets.

    Implementations:
    - ToolRegistry: Full tool registry with dynamic loading
    - TestToolRegistry: Registry with mock tools for testing
    - RestrictedToolRegistry: Registry with limited tool set

    Example:
        def execute_tool(registry: ToolRegistryProtocol, name: str, **kwargs: Any) -> Any:
            tool = registry.get(name)
            return registry.execute(tool, **kwargs)
    """

    def register(
        self,
        tool: Any,
        name: Optional[str] = None,
    ) -> None:
        """
        Register a tool.

        Args:
            tool: Tool object/function to register
            name: Tool name (uses tool.name if not provided)

        Raises:
            ValueError: If tool with same name already registered
        """
        ...

    def get(self, name: str) -> Any:
        """
        Get tool by name.

        Args:
            name: Tool name

        Returns:
            Tool object/function

        Raises:
            KeyError: If tool not found
        """
        ...

    def list_all(self) -> List[Any]:
        """
        List all registered tools.

        Returns:
            List of tool objects
        """
        ...

    def execute(
        self,
        tool_name: str,
        context: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Execute tool with arguments.

        Args:
            tool_name: Name of tool to execute
            context: Tool execution context
            **kwargs: Tool-specific arguments

        Returns:
            Tool execution result
        """
        ...

    def unregister(self, name: str) -> bool:
        """
        Unregister a tool.

        Args:
            name: Tool name

        Returns:
            True if tool was unregistered, False if not found
        """
        ...

    def exists(self, name: str) -> bool:
        """
        Check if tool is registered.

        Args:
            name: Tool name

        Returns:
            True if tool is registered, False otherwise
        """
        ...


@runtime_checkable
class ToolContextProtocol(Protocol):
    """
    Protocol for tool execution context.

    Abstracts tool context to enable testing with controlled
    environments and support different execution contexts.

    Implementations:
    - ToolContext: Full tool context with project awareness
    - TestToolContext: Minimal context for testing
    - RestrictedToolContext: Sandboxed context with restrictions

    Example:
        def get_project_path(ctx: ToolContextProtocol) -> Path:
            return ctx.get_project_root()
    """

    def get_project_root(self) -> Path:
        """
        Get project root directory.

        Returns:
            Project root path
        """
        ...

    def get_config(self) -> Dict[str, Any]:
        """
        Get agent configuration.

        Returns:
            Configuration dictionary
        """
        ...

    def is_dry_run(self) -> bool:
        """
        Check if in dry-run mode.

        Returns:
            True if dry-run mode enabled, False otherwise
        """
        ...

    def is_path_allowed(self, path: str) -> bool:
        """
        Check if path is within allowed scope.

        Args:
            path: Path to check

        Returns:
            True if path is allowed, False otherwise
        """
        ...

    def get_orchestrator(self) -> Any:
        """
        Get orchestrator instance.

        Returns:
            Orchestrator or adapter instance
        """
        ...


@runtime_checkable
class CheckpointManagerProtocol(Protocol):
    """
    Protocol for git checkpointing.

    Abstracts git checkpoint operations to enable testing without
    real git operations and support different checkpoint strategies.

    Implementations:
    - GitCheckpointManager: Real git-based checkpointing
    - InMemoryCheckpointManager: In-memory checkpoints for testing
    - NoOpCheckpointManager: No-op for testing

    Example:
        def save_state(mgr: CheckpointManagerProtocol, message: str) -> str:
            return mgr.create_checkpoint(message)

        def undo_changes(mgr: CheckpointManagerProtocol, checkpoint_id: str) -> None:
            mgr.rollback(checkpoint_id)
    """

    def create_checkpoint(
        self,
        message: str,
        files: Optional[List[str]] = None,
    ) -> str:
        """
        Create checkpoint of current state.

        Args:
            message: Checkpoint description
            files: Specific files to checkpoint (None for all changes)

        Returns:
            Checkpoint identifier (e.g., commit hash)
        """
        ...

    def rollback(self, checkpoint_id: str) -> None:
        """
        Rollback to checkpoint.

        Args:
            checkpoint_id: Checkpoint to rollback to

        Raises:
            ValueError: If checkpoint not found
        """
        ...

    def list_checkpoints(
        self,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        List available checkpoints.

        Args:
            limit: Maximum checkpoints to return

        Returns:
            List of checkpoint dictionaries containing:
            - id: Checkpoint identifier
            - message: Checkpoint description
            - timestamp: Creation time
            - files: List of files in checkpoint
        """
        ...

    def get_checkpoint_diff(
        self,
        checkpoint_id: str,
    ) -> str:
        """
        Get diff for checkpoint.

        Args:
            checkpoint_id: Checkpoint to get diff for

        Returns:
            Diff text
        """
        ...

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """
        Delete checkpoint.

        Args:
            checkpoint_id: Checkpoint to delete

        Returns:
            True if deleted, False if not found
        """
        ...


@runtime_checkable
class FileSystemProtocol(Protocol):
    """
    Protocol for file system operations.

    Abstracts file system operations to enable testing without
    real file I/O and support different storage backends.

    Implementations:
    - RealFileSystem: Standard file system operations via pathlib
    - InMemoryFileSystem: In-memory file system for testing
    - SandboxedFileSystem: Restricted file system with path validation

    Example:
        def read_config(fs: FileSystemProtocol, path: str) -> str:
            return fs.read_file(path)

        def write_output(fs: FileSystemProtocol, path: str, data: str) -> None:
            fs.write_file(path, data)
    """

    def read_file(self, path: str) -> str:
        """
        Read file contents.

        Args:
            path: File path to read

        Returns:
            File contents as string

        Raises:
            FileNotFoundError: If file does not exist
            PermissionError: If file cannot be read
        """
        ...

    def write_file(self, path: str, content: str) -> None:
        """
        Write content to file.

        Args:
            path: File path to write
            content: Content to write

        Raises:
            PermissionError: If file cannot be written
        """
        ...

    def exists(self, path: str) -> bool:
        """
        Check if path exists.

        Args:
            path: Path to check

        Returns:
            True if path exists, False otherwise
        """
        ...

    def is_file(self, path: str) -> bool:
        """
        Check if path is a file.

        Args:
            path: Path to check

        Returns:
            True if path is a file, False otherwise
        """
        ...

    def is_dir(self, path: str) -> bool:
        """
        Check if path is a directory.

        Args:
            path: Path to check

        Returns:
            True if path is a directory, False otherwise
        """
        ...

    def mkdir(self, path: str, parents: bool = False, exist_ok: bool = False) -> None:
        """
        Create directory.

        Args:
            path: Directory path to create
            parents: Create parent directories if needed
            exist_ok: Don't raise error if directory exists

        Raises:
            FileExistsError: If directory exists and exist_ok is False
        """
        ...

    def resolve(self, path: str) -> Path:
        """
        Resolve path to absolute path.

        Args:
            path: Path to resolve

        Returns:
            Resolved absolute path
        """
        ...

    def join_path(self, *parts: str) -> str:
        """
        Join path components.

        Args:
            *parts: Path components to join

        Returns:
            Joined path as string
        """
        ...


@runtime_checkable
class PlatformUtilsProtocol(Protocol):
    """
    Protocol for platform-specific utilities.

    Abstracts platform detection and command translation to enable
    testing across different platforms and support mock platforms.

    Implementations:
    - RealPlatformUtils: System platform utilities
    - MockPlatformUtils: Configurable platform for testing
    - UnixPlatformUtils: Unix-specific utilities
    - WindowsPlatformUtils: Windows-specific utilities

    Example:
        def run_command(utils: PlatformUtilsProtocol, cmd: str) -> str:
            if utils.is_windows():
                cmd = utils.translate_command(cmd)
            return execute(cmd)
    """

    def is_windows(self) -> bool:
        """
        Check if running on Windows.

        Returns:
            True if Windows, False otherwise
        """
        ...

    def is_unix(self) -> bool:
        """
        Check if running on Unix-like OS.

        Returns:
            True if Unix-like, False otherwise
        """
        ...

    def is_macos(self) -> bool:
        """
        Check if running on macOS.

        Returns:
            True if macOS, False otherwise
        """
        ...

    def get_platform_name(self) -> str:
        """
        Get platform name.

        Returns:
            Platform name (e.g., 'windows', 'linux', 'darwin')
        """
        ...

    def validate_command(self, command: str) -> tuple[bool, str]:
        """
        Validate command for current platform.

        Args:
            command: Command to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        ...

    def translate_command(self, command: str) -> tuple[str, bool]:
        """
        Translate command for current platform.

        Args:
            command: Command to translate

        Returns:
            Tuple of (translated_command, was_modified)
        """
        ...
