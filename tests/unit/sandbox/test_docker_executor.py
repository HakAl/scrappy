"""Unit tests for Docker executor."""

import platform
from pathlib import Path
from unittest.mock import MagicMock, patch


from scrappy.sandbox.docker_executor import (
    CommandResult,
    DockerExecutor,
    HostExecutor,
    create_executor,
    translate_docker_path_to_windows,
    translate_windows_path,
)


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_success_when_exit_code_zero(self):
        """Success is True when exit code is 0."""
        result = CommandResult(stdout="ok", stderr="", exit_code=0)
        assert result.success is True

    def test_not_success_when_exit_code_nonzero(self):
        """Success is False when exit code is not 0."""
        result = CommandResult(stdout="", stderr="error", exit_code=1)
        assert result.success is False

    def test_not_success_when_timed_out(self):
        """Success is False when command timed out."""
        result = CommandResult(stdout="", stderr="", exit_code=0, timed_out=True)
        assert result.success is False

    def test_output_combines_stdout_and_stderr(self):
        """Output property combines stdout and stderr."""
        result = CommandResult(stdout="out", stderr="err", exit_code=0)
        assert "out" in result.output
        assert "STDERR: err" in result.output

    def test_output_includes_timeout_message(self):
        """Output includes timeout message when timed out."""
        result = CommandResult(stdout="", stderr="", exit_code=124, timed_out=True)
        assert "[Command timed out]" in result.output

    def test_output_empty_when_no_content(self):
        """Output is empty string when no stdout/stderr."""
        result = CommandResult(stdout="", stderr="", exit_code=0)
        assert result.output == ""


class TestWindowsPathTranslation:
    """Tests for Windows path translation."""

    @patch("scrappy.sandbox.docker_executor.platform.system")
    def test_translates_c_drive(self, mock_system):
        """Translates C:\\ to /c/ (Docker Desktop format)."""
        mock_system.return_value = "Windows"
        # Note: Path.resolve() will normalize this
        result = translate_windows_path("C:\\Users\\test\\project")
        assert result.startswith("/c/")
        assert "Users" in result
        assert "\\" not in result

    @patch("scrappy.sandbox.docker_executor.platform.system")
    def test_translates_other_drives(self, mock_system):
        """Translates D:\\ to /d/ (Docker Desktop format)."""
        mock_system.return_value = "Windows"
        result = translate_windows_path("D:\\Projects\\app")
        assert result.startswith("/d/")

    @patch("scrappy.sandbox.docker_executor.platform.system")
    def test_noop_on_linux(self, mock_system):
        """Does not translate on Linux."""
        mock_system.return_value = "Linux"
        result = translate_windows_path("/home/user/project")
        assert result == "/home/user/project"

    @patch("scrappy.sandbox.docker_executor.platform.system")
    def test_noop_on_macos(self, mock_system):
        """Does not translate on macOS."""
        mock_system.return_value = "Darwin"
        result = translate_windows_path("/Users/test/project")
        assert result == "/Users/test/project"


class TestDockerPathToWindows:
    """Tests for Docker-to-Windows path translation."""

    def test_translates_workspace_path(self):
        """Translates /workspace/foo to project_dir/foo."""
        result = translate_docker_path_to_windows(
            "/workspace/src/main.py",
            "C:\\Users\\test\\project",
        )
        expected = str(Path("C:\\Users\\test\\project") / "src" / "main.py")
        assert result == expected

    def test_returns_unchanged_for_non_workspace(self):
        """Returns path unchanged if not /workspace."""
        result = translate_docker_path_to_windows(
            "/tmp/test.txt",
            "C:\\Users\\test\\project",
        )
        assert result == "/tmp/test.txt"


class TestHostExecutor:
    """Tests for HostExecutor."""

    def test_is_always_available(self, tmp_path):
        """Host executor is always available."""
        executor = HostExecutor(str(tmp_path))
        assert executor.is_available() is True

    def test_executor_type_is_host(self, tmp_path):
        """Executor type is 'host'."""
        executor = HostExecutor(str(tmp_path))
        assert executor.executor_type == "host"

    def test_runs_simple_command(self, tmp_path):
        """Runs a simple echo command."""
        executor = HostExecutor(str(tmp_path))
        result = executor.run("echo hello")
        assert result.success is True
        assert "hello" in result.stdout

    def test_captures_exit_code(self, tmp_path):
        """Captures non-zero exit code."""
        executor = HostExecutor(str(tmp_path))
        # Use a command that will fail
        if platform.system() == "Windows":
            result = executor.run("cmd /c exit 42")
        else:
            result = executor.run("exit 42")
        assert result.exit_code == 42

    def test_handles_timeout(self, tmp_path):
        """Handles command timeout."""
        executor = HostExecutor(str(tmp_path))
        # Sleep command that exceeds timeout
        if platform.system() == "Windows":
            result = executor.run("ping -n 10 127.0.0.1", timeout=0.1)
        else:
            result = executor.run("sleep 10", timeout=0.1)
        assert result.timed_out is True
        assert result.success is False

    def test_working_dir_relative_to_project(self, tmp_path):
        """Working directory is relative to project root."""
        # Create subdirectory
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        test_file = subdir / "test.txt"
        test_file.write_text("content")

        executor = HostExecutor(str(tmp_path))

        if platform.system() == "Windows":
            result = executor.run("dir", working_dir="subdir")
        else:
            result = executor.run("ls", working_dir="subdir")

        assert result.success is True
        assert "test.txt" in result.stdout  # Should not raise

    def test_context_manager(self, tmp_path):
        """Works as context manager."""
        with HostExecutor(str(tmp_path)) as executor:
            result = executor.run("echo test")
            assert result.success is True


class TestDockerExecutor:
    """Tests for DockerExecutor (with mocked Docker client)."""

    def test_executor_type_is_docker(self, tmp_path):
        """Executor type is 'docker'."""
        executor = DockerExecutor(str(tmp_path))
        assert executor.executor_type == "docker"

    @patch("scrappy.sandbox.docker_executor.docker")
    def test_is_available_when_docker_responds(self, mock_docker, tmp_path):
        """Is available when Docker client pings successfully."""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client

        executor = DockerExecutor(str(tmp_path))
        assert executor.is_available() is True
        mock_client.ping.assert_called_once()

    @patch("scrappy.sandbox.docker_executor.docker")
    def test_not_available_when_docker_fails(self, mock_docker, tmp_path):
        """Not available when Docker client fails."""
        mock_docker.from_env.side_effect = Exception("Docker not running")

        executor = DockerExecutor(str(tmp_path))
        assert executor.is_available() is False

    @patch("scrappy.sandbox.docker_executor.docker")
    def test_creates_container_on_first_run(self, mock_docker, tmp_path):
        """Creates container on first command execution."""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client

        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.short_id = "abc123"
        mock_container.exec_run.return_value = MagicMock(
            output=(b"output", b""),
            exit_code=0,
        )
        mock_client.containers.run.return_value = mock_container
        mock_client.images.get.return_value = MagicMock()

        executor = DockerExecutor(str(tmp_path))
        result = executor.run("ls")

        mock_client.containers.run.assert_called_once()
        assert result.success is True
        assert result.stdout == "output"

    @patch("scrappy.sandbox.docker_executor.docker")
    def test_reuses_container_on_subsequent_runs(self, mock_docker, tmp_path):
        """Reuses existing container for subsequent commands."""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client

        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.short_id = "abc123"
        mock_container.exec_run.return_value = MagicMock(
            output=(b"output", b""),
            exit_code=0,
        )
        mock_client.containers.run.return_value = mock_container
        mock_client.images.get.return_value = MagicMock()

        executor = DockerExecutor(str(tmp_path))
        executor.run("ls")
        executor.run("pwd")

        # Container created only once
        assert mock_client.containers.run.call_count == 1
        # Exec run called twice
        assert mock_container.exec_run.call_count == 2

    @patch("scrappy.sandbox.docker_executor.docker")
    def test_network_isolation_by_default(self, mock_docker, tmp_path):
        """Network is isolated by default."""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client

        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.short_id = "abc123"
        mock_container.exec_run.return_value = MagicMock(
            output=(b"", b""),
            exit_code=0,
        )
        mock_client.containers.run.return_value = mock_container
        mock_client.images.get.return_value = MagicMock()

        executor = DockerExecutor(str(tmp_path), network_enabled=False)
        result = executor.run("ls")

        # Verify container created with network isolation
        call_kwargs = mock_client.containers.run.call_args[1]
        assert call_kwargs["network_mode"] == "none"
        # Verify command was executed
        mock_container.exec_run.assert_called_once()
        assert result.success is True

    @patch("scrappy.sandbox.docker_executor.docker")
    def test_network_enabled_when_requested(self, mock_docker, tmp_path):
        """Network is enabled when requested."""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client

        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.short_id = "abc123"
        mock_container.exec_run.return_value = MagicMock(
            output=(b"", b""),
            exit_code=0,
        )
        mock_client.containers.run.return_value = mock_container
        mock_client.images.get.return_value = MagicMock()

        executor = DockerExecutor(str(tmp_path), network_enabled=True)
        result = executor.run("ls")

        # Verify container created with network enabled
        call_kwargs = mock_client.containers.run.call_args[1]
        assert call_kwargs["network_mode"] == "bridge"
        # Verify command was executed
        mock_container.exec_run.assert_called_once()
        assert result.success is True

    @patch("scrappy.sandbox.docker_executor.docker")
    def test_falls_back_to_basic_image(self, mock_docker, tmp_path):
        """Falls back to python:3.11-slim if custom image not found."""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client

        # First call (custom image) raises, second (fallback) succeeds
        mock_client.images.get.side_effect = [
            Exception("Image not found"),
            MagicMock(),
        ]

        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.short_id = "abc123"
        mock_container.exec_run.return_value = MagicMock(
            output=(b"", b""),
            exit_code=0,
        )
        mock_client.containers.run.return_value = mock_container

        executor = DockerExecutor(str(tmp_path))
        result = executor.run("ls")

        # Should have tried custom image first, then fallback
        assert mock_client.images.get.call_count == 2
        # Command should still execute successfully
        mock_container.exec_run.assert_called_once()
        assert result.success is True


class TestCreateExecutor:
    """Tests for create_executor factory function."""

    @patch("scrappy.sandbox.docker_executor.DockerExecutor")
    def test_returns_docker_when_available(self, mock_docker_class, tmp_path):
        """Returns DockerExecutor when Docker is available."""
        mock_instance = MagicMock()
        mock_instance.is_available.return_value = True
        mock_docker_class.return_value = mock_instance

        executor = create_executor(str(tmp_path), prefer_docker=True)

        assert executor == mock_instance

    def test_returns_host_when_docker_not_preferred(self, tmp_path):
        """Returns HostExecutor when Docker not preferred."""
        executor = create_executor(str(tmp_path), prefer_docker=False)
        assert isinstance(executor, HostExecutor)


class TestCommandExecutorProtocol:
    """Tests that executors implement the protocol."""

    def test_host_executor_implements_protocol(self, tmp_path):
        """HostExecutor implements CommandExecutorProtocol methods."""
        executor = HostExecutor(str(tmp_path))

        # Verify methods are callable and return expected types
        assert executor.executor_type == "host"
        assert executor.is_available() is True
        result = executor.run("echo test")
        assert result.exit_code == 0
        # cleanup should not raise
        executor.cleanup()

    def test_docker_executor_implements_protocol(self, tmp_path):
        """DockerExecutor implements CommandExecutorProtocol methods."""
        executor = DockerExecutor(str(tmp_path))

        # Verify methods are callable and return expected types
        assert executor.executor_type == "docker"
        # is_available may return False if Docker not running - that's fine
        available = executor.is_available()
        assert isinstance(available, bool)
        # cleanup should not raise even without container
        executor.cleanup()
