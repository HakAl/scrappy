"""
Command execution protocol.

Defines the interface for command execution strategies.
"""

from typing import Protocol, Optional, runtime_checkable
from dataclasses import dataclass


@dataclass
class ExecutionResult:
    """
    Data class for command execution results.

    NOTE: This is a dataclass, not a Protocol, because it represents
    data structure, not behavior. Protocols are for behavior contracts.

    Attributes:
        output: Command output (stdout + stderr)
        returncode: Exit code (0 = success)
        method: Execution method used (native/translated/python_fallback/timeout/error)
    """

    output: str
    returncode: int
    method: str

    @property
    def success(self) -> bool:
        """
        Check if execution was successful.

        Returns:
            True if returncode is 0, False otherwise
        """
        return self.returncode == 0

    @property
    def error_message(self) -> Optional[str]:
        """
        Get error message if execution failed.

        Returns:
            Output string if failed, None if successful
        """
        return self.output if not self.success else None

    @classmethod
    def error(cls, message: str) -> "ExecutionResult":
        """
        Create an error result.

        Args:
            message: Error message

        Returns:
            ExecutionResult with returncode 1 and method 'error'
        """
        return cls(output=message, returncode=1, method="error")


@runtime_checkable
class CommandExecutorProtocol(Protocol):
    """
    Protocol for executing shell commands.

    Implementations provide different execution strategies
    (native, translated, fallback).

    Example:
        def run_with_executor(executor: CommandExecutorProtocol, cmd: str):
            result = executor.execute(cmd)
            if result.success:
                print(f"Output: {result.output}")
                print(f"Method: {result.method}")
            else:
                print(f"Error: {result.error_message}")
    """

    def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30
    ) -> ExecutionResult:
        """
        Execute a command with the specific strategy.

        Args:
            command: Command to execute
            cwd: Working directory (defaults to current directory)
            timeout: Timeout in seconds

        Returns:
            ExecutionResult with output, returncode, and method used

        Example:
            >>> executor.execute("ls -la", cwd="/tmp", timeout=10)
            ExecutionResult(output="...", returncode=0, method="native")
        """
        ...
