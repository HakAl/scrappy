"""
Protocol definitions for command execution components.

This module defines the contracts that all command execution components
must follow, enabling dependency injection and testability.
"""

from dataclasses import dataclass
from typing import Protocol, Optional, List
from pathlib import Path


@dataclass
class ExecutionResult:
    """Result of command execution."""
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float


@dataclass
class SearchMatch:
    """Single search match result."""
    file_path: str
    line_number: int
    line_content: str
    is_match: bool = True  # False for context lines


@dataclass
class SearchMetadata:
    """Typed metadata from search operations."""
    warning: Optional[str] = None
    context_lines_supported: bool = True
    error: Optional[str] = None
    stderr: Optional[str] = None


class CommandSecurityProtocol(Protocol):
    """Contract for validating command safety.

    Implementations must check commands against security policies
    and raise exceptions for dangerous operations.
    """

    def validate(self, command: str) -> None:
        """Validate command safety.

        Args:
            command: The command string to validate

        Raises:
            SecurityError: If command violates security policy
        """
        ...


class OutputParserProtocol(Protocol):
    """Contract for parsing and formatting command output.

    Implementations handle truncation, format detection (JSON/YAML),
    and consistent output formatting.
    """

    def parse(self, raw_output: str, max_length: int = 30000) -> str:
        """Parse and format raw command output.

        Args:
            raw_output: Raw output from command execution
            max_length: Maximum output length before truncation

        Returns:
            Formatted output string
        """
        ...

    def detect_format(self, output: str) -> str:
        """Detect output format (json, yaml, text, error).

        Args:
            output: Command output to analyze

        Returns:
            Format type identifier
        """
        ...


class CommandAdvisorProtocol(Protocol):
    """Contract for providing command advice and context.

    Implementations provide framework-specific guidance and
    enrich error messages with helpful context.
    """

    def analyze_command(self, command: str) -> Optional[str]:
        """Analyze command and provide pre-execution advice.

        Args:
            command: Command to analyze

        Returns:
            Advisory message if applicable, None otherwise
        """
        ...

    def enrich_output(self, output: str, command: str) -> str:
        """Enrich output with contextual information.

        Args:
            output: Raw command output
            command: Original command that was executed

        Returns:
            Enriched output with additional context
        """
        ...


class PlatformSanitizerProtocol(Protocol):
    """Contract for platform-specific command sanitization.

    Implementations handle OS-specific command adjustments,
    path normalization, and command translation.
    """

    def sanitize(self, command: str) -> str:
        """Apply platform-specific command fixes.

        Args:
            command: Original command string

        Returns:
            Sanitized command appropriate for current platform
        """
        ...

    def normalize_path(self, path: str) -> str:
        """Normalize path for current platform.

        Args:
            path: Path to normalize

        Returns:
            Platform-appropriate path
        """
        ...


class SubprocessRunnerProtocol(Protocol):
    """Contract for executing subprocesses.

    Implementations handle the low-level mechanics of process
    execution, streaming, timeout handling, and signal management.
    """

    def execute(
        self,
        command: str,
        cwd: str,
        timeout: Optional[float] = None,
        stream_output: bool = False,
    ) -> ExecutionResult:
        """Execute command in subprocess.

        Args:
            command: Command to execute
            cwd: Working directory
            timeout: Optional timeout in seconds
            stream_output: Whether to stream output in real-time

        Returns:
            ExecutionResult with stdout, stderr, and exit code

        Raises:
            TimeoutError: If execution exceeds timeout
            ExecutionError: If execution fails
        """
        ...

    def execute_list(
        self,
        command: List[str],
        cwd: str,
        timeout: Optional[float] = None,
    ) -> ExecutionResult:
        """Execute command as list (no shell interpolation).

        Safer than execute() - no shell injection risk.

        Args:
            command: Command as list of arguments
            cwd: Working directory
            timeout: Optional timeout in seconds

        Returns:
            ExecutionResult with stdout, stderr, and exit code

        Raises:
            TimeoutError: If execution exceeds timeout
            ExecutionError: If execution fails
        """
        ...


class ThreadSafeOutputCollectorProtocol(Protocol):
    """Contract for thread-safe output collection.

    Implementations provide synchronized access to output lines
    collected from subprocess streams, ensuring data integrity
    when accessed from multiple threads.
    """

    def append(self, line: str) -> None:
        """Thread-safe append of output line.

        Args:
            line: Output line to append
        """
        ...

    def get_lines(self) -> List[str]:
        """Get copy of all collected lines.

        Returns:
            Copy of the lines list (not a reference)
        """
        ...

    def get_last_output_time(self) -> float:
        """Get timestamp of last output.

        Returns:
            Unix timestamp of last append operation
        """
        ...

    def line_count(self) -> int:
        """Get current line count.

        Returns:
            Number of lines collected
        """
        ...


class SearchOutputParserProtocol(Protocol):
    """Contract for parsing search tool output.

    Distinct from PlatformSanitizerProtocol which handles command sanitization.
    This protocol handles parsing rg/grep/findstr output formats.
    """

    def parse_line(self, line: str) -> Optional[tuple[str, int, str, bool]]:
        """Parse a search tool output line.

        Args:
            line: Raw output line from rg/grep/findstr

        Returns:
            Tuple of (file_path, line_number, content, is_match) or None if unparseable.
            is_match is False for context lines (marked with - instead of :).
        """
        ...

    def normalize_path(self, path: str) -> str:
        """Normalize path separators for consistent output."""
        ...


class TextSearchProtocol(Protocol):
    """Contract for text-based code search."""

    def search(
        self,
        pattern: str,
        path: Path,
        file_glob: str = "*",
        use_regex: bool = False,
        case_sensitive: bool = False,
        context_lines: int = 0,
        max_results: int = 100,
    ) -> tuple[List[SearchMatch], SearchMetadata]:
        """Search for pattern in files.

        Returns:
            Tuple of (matches, metadata). Metadata contains warnings/errors.
            Never silently returns empty list on error - always populate metadata.error.
        """
        ...

    def is_available(self) -> bool:
        """Check if this search backend is available."""
        ...

    @property
    def name(self) -> str:
        """Backend name for logging/debugging."""
        ...


class NoSearchToolError(Exception):
    """Raised when no search tool is available."""
    pass


__all__ = [
    'ExecutionResult',
    'SearchMatch',
    'SearchMetadata',
    'CommandSecurityProtocol',
    'OutputParserProtocol',
    'CommandAdvisorProtocol',
    'PlatformSanitizerProtocol',
    'SubprocessRunnerProtocol',
    'ThreadSafeOutputCollectorProtocol',
    'SearchOutputParserProtocol',
    'TextSearchProtocol',
    'NoSearchToolError',
]
