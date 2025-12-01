"""
Platform orchestrator protocol.

Defines the interface for the main platform orchestrator that coordinates
all platform-related operations.
"""

from typing import Protocol, Optional, Dict, Any, List, runtime_checkable

from .detection import PlatformDetectorProtocol
from .translation import CommandTranslatorProtocol
from .validation import CommandValidatorProtocol
from .execution import CommandExecutorProtocol, ExecutionResult


@runtime_checkable
class PlatformOrchestratorProtocol(Protocol):
    """
    Main protocol for platform-aware command execution.

    Orchestrates platform detection, command translation, validation,
    and execution strategies.

    This protocol enables:
    - Type hints that accept any conforming implementation
    - Easy substitution of test mocks for unit testing
    - Loose coupling between components and the orchestrator

    Example:
        def execute_safely(orchestrator: PlatformOrchestratorProtocol, cmd: str):
            result = orchestrator.smart_execute_command(cmd)
            if result.success:
                print(f"Success! Method: {result.method}")
                print(result.output)
            else:
                print(f"Failed: {result.error_message}")
    """

    @property
    def detector(self) -> PlatformDetectorProtocol:
        """
        Get platform detector implementation.

        Returns:
            Platform detector instance
        """
        ...

    @property
    def translator(self) -> CommandTranslatorProtocol:
        """
        Get command translator implementation.

        Returns:
            Command translator instance
        """
        ...

    @property
    def validator(self) -> CommandValidatorProtocol:
        """
        Get command validator implementation.

        Returns:
            Command validator instance
        """
        ...

    @property
    def executors(self) -> List[CommandExecutorProtocol]:
        """
        Get list of available command executors in priority order.

        Returns:
            List of command executors (tried in order until one succeeds)
        """
        ...

    def smart_execute_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30
    ) -> ExecutionResult:
        """
        Execute a command with automatic platform translation and Python fallback.

        This is the main entry point for platform-aware command execution.
        It orchestrates:
        1. Command validation
        2. Command translation (if needed)
        3. Execution with fallback strategies

        Args:
            command: Command to execute
            cwd: Working directory (defaults to current directory)
            timeout: Timeout in seconds

        Returns:
            ExecutionResult with output, returncode, and method used

        Example:
            >>> result = orchestrator.smart_execute_command("ls -la /tmp")
            >>> print(f"Method: {result.method}")  # "native" or "translated" or "fallback"
            >>> print(f"Output: {result.output}")
        """
        ...

    def get_usage_report(self) -> Dict[str, Any]:
        """
        Get usage statistics report.

        Returns:
            Dictionary containing usage statistics including:
            - total_commands: Total commands executed
            - by_method: Execution method breakdown (native/translated/fallback)
            - by_platform: Platform-specific statistics
            - error_rate: Error rate statistics

        Example:
            >>> stats = orchestrator.get_usage_report()
            >>> print(f"Total: {stats['total_commands']}")
            >>> print(f"Methods: {stats['by_method']}")
        """
        ...
