"""Unit tests for SandboxedSubprocessRunner."""

from unittest.mock import MagicMock, patch

import pytest

from scrappy.agent_tools.components.sandboxed_runner import (
    SandboxedSubprocessRunner,
    create_sandboxed_runner,
)
from scrappy.agent_tools.protocols import ExecutionResult
from scrappy.sandbox.docker_executor import CommandResult


class TestSandboxedSubprocessRunner:
    """Tests for SandboxedSubprocessRunner."""

    def test_uses_provided_executor(self, tmp_path):
        """Uses the provided executor instead of creating one."""
        mock_executor = MagicMock()
        mock_executor.run.return_value = CommandResult(
            stdout="output",
            stderr="",
            exit_code=0,
        )
        mock_executor.executor_type = "mock"

        runner = SandboxedSubprocessRunner(
            project_dir=str(tmp_path),
            executor=mock_executor,
        )
        result = runner.execute("ls", str(tmp_path))

        mock_executor.run.assert_called_once()
        assert result.stdout == "output"
        assert result.exit_code == 0

    def test_returns_execution_result(self, tmp_path):
        """Returns an ExecutionResult with correct fields."""
        mock_executor = MagicMock()
        mock_executor.run.return_value = CommandResult(
            stdout="hello",
            stderr="warn",
            exit_code=0,
        )
        mock_executor.executor_type = "mock"

        runner = SandboxedSubprocessRunner(
            project_dir=str(tmp_path),
            executor=mock_executor,
        )
        result = runner.execute("echo hello", str(tmp_path))

        assert isinstance(result, ExecutionResult)
        assert result.stdout == "hello"
        assert result.stderr == "warn"
        assert result.exit_code == 0
        assert result.execution_time >= 0

    def test_passes_timeout_to_executor(self, tmp_path):
        """Passes timeout to the underlying executor."""
        mock_executor = MagicMock()
        mock_executor.run.return_value = CommandResult(
            stdout="",
            stderr="",
            exit_code=0,
        )
        mock_executor.executor_type = "mock"

        runner = SandboxedSubprocessRunner(
            project_dir=str(tmp_path),
            executor=mock_executor,
        )
        runner.execute("ls", str(tmp_path), timeout=30.0)

        call_kwargs = mock_executor.run.call_args[1]
        assert call_kwargs["timeout"] == 30.0

    def test_default_timeout_is_120_seconds(self, tmp_path):
        """Default timeout is 120 seconds."""
        mock_executor = MagicMock()
        mock_executor.run.return_value = CommandResult(
            stdout="",
            stderr="",
            exit_code=0,
        )
        mock_executor.executor_type = "mock"

        runner = SandboxedSubprocessRunner(
            project_dir=str(tmp_path),
            executor=mock_executor,
        )
        runner.execute("ls", str(tmp_path))

        call_kwargs = mock_executor.run.call_args[1]
        assert call_kwargs["timeout"] == 120.0

    def test_calculates_relative_workdir(self, tmp_path):
        """Calculates relative working directory from project root."""
        subdir = tmp_path / "src" / "app"
        subdir.mkdir(parents=True)

        mock_executor = MagicMock()
        mock_executor.run.return_value = CommandResult(
            stdout="",
            stderr="",
            exit_code=0,
        )
        mock_executor.executor_type = "mock"

        runner = SandboxedSubprocessRunner(
            project_dir=str(tmp_path),
            executor=mock_executor,
        )
        runner.execute("ls", str(subdir))

        call_kwargs = mock_executor.run.call_args[1]
        # Should be relative path
        assert call_kwargs["working_dir"] in ["src/app", "src\\app"]

    def test_none_workdir_for_project_root(self, tmp_path):
        """Returns None for working_dir when cwd is project root."""
        mock_executor = MagicMock()
        mock_executor.run.return_value = CommandResult(
            stdout="",
            stderr="",
            exit_code=0,
        )
        mock_executor.executor_type = "mock"

        runner = SandboxedSubprocessRunner(
            project_dir=str(tmp_path),
            executor=mock_executor,
        )
        runner.execute("ls", str(tmp_path))

        call_kwargs = mock_executor.run.call_args[1]
        assert call_kwargs["working_dir"] is None

    def test_execute_list_joins_command(self, tmp_path):
        """execute_list joins command list into string."""
        mock_executor = MagicMock()
        mock_executor.run.return_value = CommandResult(
            stdout="",
            stderr="",
            exit_code=0,
        )
        mock_executor.executor_type = "mock"

        runner = SandboxedSubprocessRunner(
            project_dir=str(tmp_path),
            executor=mock_executor,
        )
        runner.execute_list(["ls", "-la", "/tmp"], str(tmp_path))

        call_args = mock_executor.run.call_args[1]
        assert call_args["command"] == "ls -la /tmp"

    def test_executor_type_property(self, tmp_path):
        """executor_type returns underlying executor type."""
        mock_executor = MagicMock()
        mock_executor.executor_type = "docker"

        runner = SandboxedSubprocessRunner(
            project_dir=str(tmp_path),
            executor=mock_executor,
        )

        assert runner.executor_type == "docker"

    def test_warns_once_for_host_execution(self, tmp_path, caplog):
        """Logs warning once when using host execution."""
        mock_executor = MagicMock()
        mock_executor.run.return_value = CommandResult(
            stdout="",
            stderr="",
            exit_code=0,
        )
        mock_executor.executor_type = "host"

        runner = SandboxedSubprocessRunner(
            project_dir=str(tmp_path),
            executor=mock_executor,
        )

        # First call should warn
        runner.execute("ls", str(tmp_path))
        # Second call should not warn again
        runner.execute("pwd", str(tmp_path))

        # Check that warning was logged only once
        warning_count = sum(
            1 for record in caplog.records
            if "no Docker sandbox" in record.message
        )
        assert warning_count == 1

    def test_no_output_returns_placeholder(self, tmp_path):
        """Returns '(no output)' when stdout is empty."""
        mock_executor = MagicMock()
        mock_executor.run.return_value = CommandResult(
            stdout="",
            stderr="",
            exit_code=0,
        )
        mock_executor.executor_type = "mock"

        runner = SandboxedSubprocessRunner(
            project_dir=str(tmp_path),
            executor=mock_executor,
        )
        result = runner.execute("true", str(tmp_path))

        assert result.stdout == "(no output)"


class TestCreateSandboxedRunner:
    """Tests for create_sandboxed_runner factory function."""

    @patch("scrappy.agent_tools.components.sandboxed_runner.create_executor")
    def test_passes_network_enabled_option(self, mock_create_executor, tmp_path):
        """Passes network_enabled option to executor factory."""
        mock_executor = MagicMock()
        mock_executor.executor_type = "docker"
        mock_create_executor.return_value = mock_executor

        create_sandboxed_runner(str(tmp_path), network_enabled=True)

        call_kwargs = mock_create_executor.call_args[1]
        assert call_kwargs["network_enabled"] is True

    @patch("scrappy.agent_tools.components.sandboxed_runner.create_executor")
    def test_passes_prefer_docker_option(self, mock_create_executor, tmp_path):
        """Passes prefer_docker option to executor factory."""
        mock_executor = MagicMock()
        mock_executor.executor_type = "host"
        mock_create_executor.return_value = mock_executor

        create_sandboxed_runner(str(tmp_path), prefer_docker=False)

        call_kwargs = mock_create_executor.call_args[1]
        assert call_kwargs["prefer_docker"] is False
