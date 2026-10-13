"""Tests for the SubprocessRunner elapsed-timeout contract.

The runner documents built-in TimeoutError for an elapsed timeout, and
RunTestsTool and ShellCommandExecutor have dedicated responses for it.
These tests drive the real runner loop and real callers; only the external
process and clock boundaries are replaced.
"""

import errno
import io
import os
import subprocess
import threading
from types import SimpleNamespace

import pytest

from scrappy.agent_tools.components import subprocess_runner
from scrappy.agent_tools.components.subprocess_runner import SubprocessRunner
from scrappy.agent_tools.tools.base import ToolContext
from scrappy.agent_tools.tools.command_tool import ShellCommandExecutor
from scrappy.agent_tools.tools.testing_tools import RunTestsTool


class ControlledClock:
    """Clock that advances only when the fake process is polled.

    Reads never move time, so the result does not depend on how many times
    the runner, collector or reader thread read the clock.
    """

    def __init__(self) -> None:
        self.now = 1000.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        pass


class FakeProcess:
    """Popen boundary double for a process that never exits on its own."""

    def __init__(self, clock: ControlledClock, poll_step: float, args: object) -> None:
        self.args = args
        self._clock = clock
        self._poll_step = poll_step
        # Empty pipes reach EOF at once, so the real reader threads finish.
        self.stdout = io.StringIO("")
        self.stderr = io.StringIO("")
        self.returncode = None
        self.kill_requested = False

    def poll(self) -> None:
        self._clock.now += self._poll_step
        return None

    def kill(self) -> None:
        self.kill_requested = True


class ProcessBoundary:
    """Replaces only the runner's process and clock modules."""

    def __init__(self) -> None:
        self.clock = ControlledClock()
        self.poll_step = 0.75
        self.launches: list[FakeProcess] = []
        self.launch_error: OSError | None = None

    def popen(self, args: object, **kwargs: object) -> FakeProcess:
        if self.launch_error is not None:
            raise self.launch_error
        process = FakeProcess(self.clock, self.poll_step, args)
        self.launches.append(process)
        return process


@pytest.fixture
def boundary(monkeypatch: pytest.MonkeyPatch) -> ProcessBoundary:
    fake = ProcessBoundary()
    monkeypatch.setattr(
        subprocess_runner,
        "subprocess",
        SimpleNamespace(
            Popen=fake.popen,
            PIPE=subprocess.PIPE,
            STDOUT=subprocess.STDOUT,
            TimeoutExpired=subprocess.TimeoutExpired,
            SubprocessError=subprocess.SubprocessError,
        ),
    )
    monkeypatch.setattr(
        subprocess_runner,
        "time",
        SimpleNamespace(time=fake.clock.time, sleep=fake.clock.sleep),
    )
    return fake


@pytest.fixture(autouse=True)
def no_reader_thread_left_running():
    """Fail if a reader thread started by a test is still alive afterwards."""
    before = set(threading.enumerate())
    yield
    # Unnamed threads carry their target name, e.g. "Thread-3 (read_output)".
    started = [
        t for t in threading.enumerate()
        if t not in before and "(read_" in t.name
    ]
    for thread in started:
        thread.join(timeout=2)
    assert [t for t in started if t.is_alive()] == []


class TestSubprocessTimeoutContract:
    """Elapsed timeouts reach callers as built-in TimeoutError."""

    def test_execute_preserves_elapsed_timeout(self, boundary, tmp_path):
        """execute should raise built-in TimeoutError when the limit elapses."""
        runner = SubprocessRunner()

        with pytest.raises(TimeoutError) as exc_info:
            runner.execute("long-task", str(tmp_path), timeout=1)

        assert type(exc_info.value) is TimeoutError
        assert str(exc_info.value) == "Command timed out after 1s"
        assert len(boundary.launches) == 1
        assert boundary.launches[0].kill_requested

    def test_run_tests_reports_real_runner_timeout(self, boundary, tmp_path):
        """RunTestsTool should give its dedicated timeout response."""
        tool = RunTestsTool(runner=SubprocessRunner())
        context = ToolContext(project_root=tmp_path)

        result = tool.execute(context, command="pytest -q", timeout=1)

        assert result.success is False
        assert result.output == ""
        assert result.error == (
            "Test command timed out after 1 seconds. "
            "Consider running a subset of tests or increasing timeout."
        )

    def test_shell_retry_reports_real_runner_timeout_without_retry(
        self, boundary, tmp_path
    ):
        """ShellCommandExecutor should report the timeout and not retry it."""
        executor = ShellCommandExecutor(timeout=1, runner=SubprocessRunner())

        output = executor.run("echo hello", tmp_path)

        assert output == "Error: Command timed out after 1s"
        assert len(boundary.launches) == 1

    def test_execute_preserves_launch_error_wrapping(self, boundary, tmp_path):
        """A launch failure should keep its RuntimeError classification.

        This includes an external TimeoutError from the launch itself, which
        is not the runner's own elapsed timeout.
        """
        missing_cwd = str(tmp_path / "missing")
        launch_errors = [
            FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), missing_cwd),
            TimeoutError(errno.ETIMEDOUT, os.strerror(errno.ETIMEDOUT)),
        ]
        runner = SubprocessRunner()

        for launch_error in launch_errors:
            boundary.launch_error = launch_error

            with pytest.raises(RuntimeError) as exc_info:
                runner.execute("echo hello", missing_cwd, timeout=1)

            assert type(exc_info.value) is RuntimeError
            assert str(exc_info.value) == f"Error running command: {launch_error}"
        assert boundary.launches == []

    def test_execute_list_preserves_elapsed_timeout(self, boundary, tmp_path):
        """execute_list should raise built-in TimeoutError when the limit elapses."""
        runner = SubprocessRunner()

        with pytest.raises(TimeoutError) as exc_info:
            runner.execute_list(["long-task"], str(tmp_path), timeout=1)

        assert type(exc_info.value) is TimeoutError
        assert str(exc_info.value) == "Command timed out after 1s"
        assert len(boundary.launches) == 1
        assert boundary.launches[0].kill_requested
