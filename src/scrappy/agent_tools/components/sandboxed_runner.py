"""
Sandboxed subprocess runner that uses Docker for isolation.

Provides a drop-in replacement for SubprocessRunner that executes
commands in a Docker container for isolation, with graceful fallback
to host execution when Docker is unavailable.
"""

import logging
import time
from typing import Optional, List

from scrappy.sandbox import (
    CommandExecutorProtocol,
    CommandResult,
    create_executor,
)
from ..protocols import ExecutionResult

logger = logging.getLogger(__name__)


class SandboxedSubprocessRunner:
    """
    Subprocess runner that executes commands in a Docker sandbox.

    Implements the same interface as SubprocessRunner but delegates
    to a CommandExecutorProtocol (DockerExecutor or HostExecutor).

    This allows the existing CommandTool and ShellCommandExecutor to
    use Docker-based isolation via dependency injection.
    """

    def __init__(
        self,
        project_dir: str,
        executor: Optional[CommandExecutorProtocol] = None,
        prefer_docker: bool = True,
        network_enabled: bool = False,
    ):
        """
        Initialize sandboxed runner.

        Args:
            project_dir: Project directory to mount in container
            executor: Optional pre-configured executor (for testing)
            prefer_docker: Try Docker first, fall back to host
            network_enabled: Enable network access in Docker container
        """
        self._project_dir = project_dir
        self._executor = executor or create_executor(
            project_dir=project_dir,
            prefer_docker=prefer_docker,
            network_enabled=network_enabled,
        )
        self._warned_host_execution = False

    def execute(
        self,
        command: str,
        cwd: str,
        timeout: Optional[float] = None,
        stream_output: bool = False,
    ) -> ExecutionResult:
        """
        Execute command via sandbox executor.

        Args:
            command: Command to execute
            cwd: Working directory (relative to project root)
            timeout: Optional timeout in seconds
            stream_output: Whether to stream output (note: limited in Docker)

        Returns:
            ExecutionResult with stdout, stderr, and exit code

        Raises:
            TimeoutError: If execution exceeds timeout
        """
        timeout = timeout or 120.0  # Default 2 minutes
        start_time = time.time()

        # Log execution type if using host (warn once per session)
        if self._executor.executor_type == "host" and not self._warned_host_execution:
            logger.warning(
                "Executing commands on host (no Docker sandbox). "
                "Install Docker for isolated execution."
            )
            self._warned_host_execution = True

        # Calculate relative working directory from project root
        working_dir = self._get_relative_workdir(cwd)

        # Execute via sandbox
        result: CommandResult = self._executor.run(
            command=command,
            timeout=timeout,
            working_dir=working_dir,
        )

        execution_time = time.time() - start_time

        # Check for timeout
        if result.timed_out:
            raise TimeoutError(f"Command timed out after {timeout}s")

        return ExecutionResult(
            stdout=result.stdout if result.stdout else "(no output)",
            stderr=result.stderr,
            exit_code=result.exit_code,
            execution_time=execution_time,
        )

    def execute_list(
        self,
        command: List[str],
        cwd: str,
        timeout: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Execute command as list.

        Joins the command list and delegates to execute().
        Note: In Docker mode, this still uses shell execution.

        Args:
            command: Command as list of arguments
            cwd: Working directory
            timeout: Optional timeout in seconds

        Returns:
            ExecutionResult with stdout, stderr, and exit code
        """
        # Join command list into string for sandbox execution
        # Note: This loses the shell=False security benefit when using Docker
        # but maintains compatibility with the interface
        command_str = " ".join(command)
        return self.execute(command_str, cwd, timeout, stream_output=False)

    def _get_relative_workdir(self, cwd: str) -> Optional[str]:
        """
        Get working directory relative to project root.

        Args:
            cwd: Absolute or relative working directory

        Returns:
            Relative path from project root, or None if same as project root
        """
        from pathlib import Path

        cwd_path = Path(cwd).resolve()
        project_path = Path(self._project_dir).resolve()

        try:
            relative = cwd_path.relative_to(project_path)
            return str(relative) if str(relative) != "." else None
        except ValueError:
            # cwd is not under project root - use as-is
            # This may fail in Docker but is a fallback
            return str(cwd_path)

    def cleanup(self) -> None:
        """Clean up sandbox resources."""
        self._executor.cleanup()

    @property
    def executor_type(self) -> str:
        """Return the underlying executor type."""
        return self._executor.executor_type

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup."""
        self.cleanup()
        return False


def create_sandboxed_runner(
    project_dir: str,
    prefer_docker: bool = True,
    network_enabled: bool = False,
) -> SandboxedSubprocessRunner:
    """
    Factory function for creating SandboxedSubprocessRunner.

    Creates a runner that uses Docker for isolation when available,
    with automatic fallback to host execution.

    Args:
        project_dir: Project directory to mount
        prefer_docker: Try Docker first (default: True)
        network_enabled: Enable network in Docker

    Returns:
        Configured SandboxedSubprocessRunner
    """
    return SandboxedSubprocessRunner(
        project_dir=project_dir,
        prefer_docker=prefer_docker,
        network_enabled=network_enabled,
    )
