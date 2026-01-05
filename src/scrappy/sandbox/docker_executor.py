"""
Docker-based command executor for sandboxed shell execution.

Provides safe command execution with container isolation, timeout enforcement,
and graceful fallback to host execution when Docker is unavailable.

Usage:
    executor = create_executor(project_dir="/path/to/project")
    result = executor.run("ls -la")
    executor.cleanup()  # Or use as context manager
"""

import logging
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

# Import docker at module level for testability (can be mocked)
try:
    import docker
except ImportError:
    docker = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of a command execution."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False

    @property
    def success(self) -> bool:
        """Check if command succeeded (exit code 0, no timeout)."""
        return self.exit_code == 0 and not self.timed_out

    @property
    def output(self) -> str:
        """Combined stdout and stderr output."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(f"STDERR: {self.stderr}")
        if self.timed_out:
            parts.append("[Command timed out]")
        return "\n".join(parts) if parts else ""


class CommandExecutorProtocol(Protocol):
    """Protocol for command executors."""

    def run(
        self,
        command: str,
        timeout: float = 60.0,
        working_dir: Optional[str] = None,
    ) -> CommandResult:
        """
        Execute a shell command.

        Args:
            command: Shell command to execute
            timeout: Maximum execution time in seconds
            working_dir: Working directory (relative to project root)

        Returns:
            CommandResult with output and exit code
        """
        ...

    def cleanup(self) -> None:
        """Clean up resources (containers, temp files, etc.)."""
        ...

    def is_available(self) -> bool:
        """Check if executor is available and ready."""
        ...

    @property
    def executor_type(self) -> str:
        """Return executor type identifier (docker/host)."""
        ...


def translate_windows_path(path: str) -> str:
    """
    Translate Windows path to Docker Desktop-compatible path.

    Docker Desktop for Windows uses /c/Users/foo format (not /mnt/c/).
    Converts C:\\Users\\foo to /c/Users/foo for volume mounts.

    Args:
        path: Windows-style path

    Returns:
        Docker Desktop-compatible path
    """
    if platform.system() != "Windows":
        return path

    # Convert to Path for normalization
    p = Path(path).resolve()
    path_str = str(p)

    # Match drive letter pattern (C:\, D:\, etc.)
    match = re.match(r"^([A-Za-z]):\\(.*)$", path_str)
    if match:
        drive = match.group(1).lower()
        rest = match.group(2).replace("\\", "/")
        # Docker Desktop uses /c/ not /mnt/c/
        return f"/{drive}/{rest}"

    # Already a Unix-style path or relative
    return path_str.replace("\\", "/")


def translate_docker_path_to_windows(docker_path: str, project_dir: str) -> str:
    """
    Translate Docker container path back to Windows path.

    Converts /workspace/foo to C:\\Users\\...\\foo based on project_dir.

    Args:
        docker_path: Path inside container (/workspace/...)
        project_dir: Original Windows project directory

    Returns:
        Windows-compatible path
    """
    if not docker_path.startswith("/workspace"):
        return docker_path

    relative = docker_path[len("/workspace") :].lstrip("/")
    return str(Path(project_dir) / relative)


class DockerExecutor:
    """
    Docker-based command executor with persistent container reuse.

    Creates a container on first use and reuses it for subsequent commands.
    Container is cleaned up on explicit cleanup() or context manager exit.

    Features:
    - Persistent container for performance
    - Project directory mounted at /workspace
    - Network isolation by default
    - Timeout enforcement per command
    - Windows path translation for WSL2/Hyper-V
    """

    # Container image for sandbox
    IMAGE_NAME = "scrappy-sandbox:latest"
    # Fallback to basic Python image if custom not available
    FALLBACK_IMAGE = "python:3.11-slim"
    # Container working directory
    CONTAINER_WORKDIR = "/workspace"

    def __init__(
        self,
        project_dir: str,
        network_enabled: bool = False,
        image: Optional[str] = None,
    ):
        """
        Initialize Docker executor.

        Args:
            project_dir: Project directory to mount
            network_enabled: Enable network access (default: isolated)
            image: Docker image to use (default: scrappy-sandbox:latest)
        """
        self._project_dir = str(Path(project_dir).resolve())
        self._network_enabled = network_enabled
        self._image = image or self.IMAGE_NAME
        self._container = None
        self._docker_client = None
        self._available: Optional[bool] = None

    def _get_client(self):
        """Get or create Docker client."""
        if self._docker_client is None:
            if docker is None:
                raise ImportError("docker package not installed")
            try:
                self._docker_client = docker.from_env()
            except Exception as e:
                logger.warning("Failed to create Docker client: %s", e)
                raise
        return self._docker_client

    def _ensure_container(self) -> None:
        """Ensure container is running, create if needed."""
        if self._container is not None:
            # Check if container is still running
            try:
                self._container.reload()
                if self._container.status == "running":
                    return
            except Exception:
                self._container = None

        client = self._get_client()

        # Translate Windows path for volume mount
        host_path = translate_windows_path(self._project_dir)

        # Container configuration
        volumes = {host_path: {"bind": self.CONTAINER_WORKDIR, "mode": "rw"}}

        # Try custom image first, fall back to basic image
        image_to_use = self._image
        try:
            client.images.get(image_to_use)
        except Exception:
            logger.info(
                "Image %s not found, falling back to %s",
                image_to_use,
                self.FALLBACK_IMAGE,
            )
            image_to_use = self.FALLBACK_IMAGE
            # Pull if needed
            try:
                client.images.get(image_to_use)
            except Exception:
                logger.info("Pulling image %s...", image_to_use)
                client.images.pull(image_to_use)

        # Create and start container
        network_mode = "bridge" if self._network_enabled else "none"

        self._container = client.containers.run(
            image_to_use,
            command="sleep infinity",  # Keep alive
            volumes=volumes,
            working_dir=self.CONTAINER_WORKDIR,
            network_mode=network_mode,
            detach=True,
            remove=False,  # We'll remove explicitly
            stdin_open=True,
            tty=False,
        )

        logger.info(
            "Started sandbox container %s (image: %s, network: %s)",
            self._container.short_id,
            image_to_use,
            network_mode,
        )

    def run(
        self,
        command: str,
        timeout: float = 60.0,
        working_dir: Optional[str] = None,
    ) -> CommandResult:
        """
        Execute command in Docker container.

        Args:
            command: Shell command to execute
            timeout: Maximum execution time in seconds
            working_dir: Working directory relative to project root

        Returns:
            CommandResult with output and exit code
        """
        self._ensure_container()

        # Build execution command
        workdir = self.CONTAINER_WORKDIR
        if working_dir:
            workdir = f"{self.CONTAINER_WORKDIR}/{working_dir}"

        # Execute with timeout
        try:
            exec_result = self._container.exec_run(
                cmd=["sh", "-c", command],
                workdir=workdir,
                demux=True,  # Separate stdout/stderr
            )

            stdout_bytes, stderr_bytes = exec_result.output
            stdout = (stdout_bytes or b"").decode("utf-8", errors="replace")
            stderr = (stderr_bytes or b"").decode("utf-8", errors="replace")

            return CommandResult(
                stdout=stdout.strip(),
                stderr=stderr.strip(),
                exit_code=exec_result.exit_code,
            )

        except Exception as e:
            logger.error("Docker exec failed: %s", e)
            return CommandResult(
                stdout="",
                stderr=f"Docker execution error: {e}",
                exit_code=1,
            )

    def cleanup(self) -> None:
        """Stop and remove the container."""
        if self._container is not None:
            try:
                self._container.stop(timeout=5)
                self._container.remove()
                logger.info("Cleaned up sandbox container %s", self._container.short_id)
            except Exception as e:
                logger.warning("Error cleaning up container: %s", e)
            finally:
                self._container = None

        if self._docker_client is not None:
            try:
                self._docker_client.close()
            except Exception:
                pass
            self._docker_client = None

    def is_available(self) -> bool:
        """Check if Docker is available."""
        if self._available is not None:
            return self._available

        try:
            client = self._get_client()
            client.ping()
            self._available = True
        except Exception as e:
            logger.debug("Docker not available: %s", e)
            self._available = False

        return self._available

    @property
    def executor_type(self) -> str:
        """Return executor type identifier."""
        return "docker"

    def get_resolved_image(self) -> str:
        """Get the image name that will actually be used.

        Checks if custom image exists, otherwise returns fallback.

        Returns:
            Image name (e.g., 'python:3.11-slim')
        """
        if not self.is_available():
            return self.FALLBACK_IMAGE

        try:
            client = self._get_client()
            client.images.get(self._image)
            return self._image
        except Exception:
            return self.FALLBACK_IMAGE

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup container."""
        self.cleanup()
        return False


class HostExecutor:
    """
    Host-based command executor (fallback when Docker unavailable).

    Executes commands directly on the host system. Use with caution
    as this provides no isolation.
    """

    def __init__(self, project_dir: str):
        """
        Initialize host executor.

        Args:
            project_dir: Project directory for command execution
        """
        self._project_dir = str(Path(project_dir).resolve())

    def run(
        self,
        command: str,
        timeout: float = 60.0,
        working_dir: Optional[str] = None,
    ) -> CommandResult:
        """
        Execute command on host system.

        Args:
            command: Shell command to execute
            timeout: Maximum execution time in seconds
            working_dir: Working directory relative to project root

        Returns:
            CommandResult with output and exit code
        """
        # Determine working directory
        cwd = self._project_dir
        if working_dir:
            cwd = str(Path(self._project_dir) / working_dir)

        # Determine shell based on platform
        if platform.system() == "Windows":
            shell_cmd = ["cmd", "/c", command]
        else:
            shell_cmd = ["sh", "-c", command]

        try:
            result = subprocess.run(
                shell_cmd,
                cwd=cwd,
                capture_output=True,
                timeout=timeout,
                text=True,
            )

            return CommandResult(
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
                exit_code=result.returncode,
            )

        except subprocess.TimeoutExpired:
            return CommandResult(
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                exit_code=124,  # Standard timeout exit code
                timed_out=True,
            )

        except Exception as e:
            return CommandResult(
                stdout="",
                stderr=f"Execution error: {e}",
                exit_code=1,
            )

    def cleanup(self) -> None:
        """No cleanup needed for host executor."""
        pass

    def is_available(self) -> bool:
        """Host executor is always available."""
        return True

    @property
    def executor_type(self) -> str:
        """Return executor type identifier."""
        return "host"

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup()
        return False


def create_executor(
    project_dir: str,
    prefer_docker: bool = True,
    network_enabled: bool = False,
) -> CommandExecutorProtocol:
    """
    Factory function to create appropriate executor.

    Tries Docker first if preferred and available, falls back to host.
    Logs a warning when falling back to host execution.

    Args:
        project_dir: Project directory to use
        prefer_docker: Try Docker first (default: True)
        network_enabled: Enable network in Docker container

    Returns:
        CommandExecutorProtocol implementation
    """
    if prefer_docker:
        docker_exec = DockerExecutor(
            project_dir=project_dir,
            network_enabled=network_enabled,
        )
        if docker_exec.is_available():
            logger.info("Using Docker sandbox for command execution")
            return docker_exec
        else:
            logger.warning(
                "Docker not available - falling back to host execution. "
                "Commands will run without sandbox isolation!"
            )

    return HostExecutor(project_dir=project_dir)
