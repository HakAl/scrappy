"""Reproduce-first tests for the shared real-terminal readiness primitive.

These exercise :func:`wait_for_ready_file` through a minimal fake harness that
implements only the two new Protocol methods (``probe_launched_app`` and
``drain_launch_diagnostics``), backed by a real child process and a real
``CapturedStream``. No GUI terminal, X server, or Windows console is required, so the
whole module runs on macOS in the dogfood worktree.

The bug under repair: the old per-driver ``_wait_for_file`` helper polled only the
ready_file against a deadline and never checked whether the launched app was still
alive, so an app that crashed before writing the marker (for example the 3.14-venv
onnxruntime startup crash) produced a blind, diagnostically empty timeout.
``test_legacy_ready_file_only_wait_is_blind`` reproduces that failure mode;
``test_app_death_fails_fast_with_exit_code_and_stderr`` locks in the fix.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import time

import pytest

from .real_terminal_harness import (
    CapturedStream,
    LaunchLiveness,
    ReadinessTimeout,
    wait_for_ready_file,
)


class _FakeLaunchedApp:
    """Stand-in implementing only the readiness Protocol methods, backed by a child.

    It drives the exact composition path the real drivers use: a liveness probe over a
    real process and a diagnostics drain over a real captured-stderr temp file.
    """

    def __init__(
        self,
        *,
        stderr_text: str,
        exit_code: int,
        ready_file: Path | None,
        delay_seconds: float = 0.0,
    ) -> None:
        self._capture = CapturedStream.create("scrappy-readytest-")
        script_lines = ["import sys, time", f"time.sleep({delay_seconds!r})"]
        if ready_file is not None:
            script_lines.append(f"open({str(ready_file)!r}, 'w').close()")
        script_lines.append(f"sys.stderr.write({stderr_text!r})")
        script_lines.append("sys.stderr.flush()")
        script_lines.append(f"sys.exit({exit_code})")
        self._process = subprocess.Popen(
            [sys.executable, "-c", "\n".join(script_lines)],
            stdout=subprocess.DEVNULL,
            stderr=self._capture.handle,
        )

    def probe_launched_app(self) -> LaunchLiveness:
        code = self._process.poll()
        if code is None:
            return LaunchLiveness(alive=True)
        return LaunchLiveness(alive=False, exit_code=code)

    def drain_launch_diagnostics(self) -> str:
        return self._capture.read_tail()

    def cleanup(self) -> None:
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)
        self._capture.cleanup()


def _legacy_ready_file_only_wait(path: Path, *, timeout_seconds: float) -> None:
    """The pre-fix readiness wait: poll only the ready_file against a deadline.

    Reproduced verbatim (minus the platform error type) to demonstrate the original
    diagnostic blindness that the shared primitive removes.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.02)
    raise RuntimeError(f"Timed out waiting for scrappy readiness signal at {path}")


def test_legacy_ready_file_only_wait_is_blind(tmp_path: Path) -> None:
    """Before the fix: a dead app produces a full-duration, diagnostic-free timeout."""
    ready_file = tmp_path / "never_written.ready"
    app = _FakeLaunchedApp(stderr_text="onnxruntime import boom\n", exit_code=3, ready_file=None)
    app.cleanup()  # the app is already dead (and reaped) well before the wait starts

    timeout_seconds = 0.5
    start = time.monotonic()
    with pytest.raises(RuntimeError) as excinfo:
        _legacy_ready_file_only_wait(ready_file, timeout_seconds=timeout_seconds)
    elapsed = time.monotonic() - start

    # The blindness: it burned the whole timeout despite the app being long dead...
    assert elapsed >= timeout_seconds * 0.8
    # ...and the message carries none of the new primitive's diagnostics.
    message = str(excinfo.value)
    assert "exited" not in message
    assert "captured stderr tail" not in message
    assert "boom" not in message


def test_app_death_fails_fast_with_exit_code_and_stderr(tmp_path: Path) -> None:
    """After the fix: a dead app fails fast, with the exit code and stderr tail."""
    ready_file = tmp_path / "never_written.ready"
    app = _FakeLaunchedApp(stderr_text="onnxruntime import boom\n", exit_code=3, ready_file=None)
    try:
        timeout_seconds = 5.0
        start = time.monotonic()
        with pytest.raises(ReadinessTimeout) as excinfo:
            wait_for_ready_file(
                ready_file=ready_file,
                probe=app.probe_launched_app,
                drain_diagnostics=app.drain_launch_diagnostics,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=0.02,
            )
        elapsed = time.monotonic() - start
    finally:
        app.cleanup()

    # Fail-fast: nowhere near the timeout.
    assert elapsed < timeout_seconds / 2
    message = str(excinfo.value)
    assert "code 3" in message
    assert "boom" in message


def test_custom_error_factory_preserves_platform_error_type(tmp_path: Path) -> None:
    """Drivers keep their own error type via error_factory (backward compatibility)."""

    class _PlatformError(RuntimeError):
        pass

    ready_file = tmp_path / "never_written.ready"
    app = _FakeLaunchedApp(stderr_text="startup failed\n", exit_code=7, ready_file=None)
    try:
        with pytest.raises(_PlatformError) as excinfo:
            wait_for_ready_file(
                ready_file=ready_file,
                probe=app.probe_launched_app,
                drain_diagnostics=app.drain_launch_diagnostics,
                timeout_seconds=5.0,
                poll_interval_seconds=0.02,
                error_factory=_PlatformError,
            )
    finally:
        app.cleanup()
    assert "code 7" in str(excinfo.value)


def test_ready_file_present_returns_immediately(tmp_path: Path) -> None:
    """A marker already on disk returns without consulting liveness."""
    ready_file = tmp_path / "ready.now"
    ready_file.write_text("ok", encoding="utf-8")

    def _explode() -> LaunchLiveness:  # pragma: no cover - must not be called
        raise AssertionError("probe should not run when the marker already exists")

    wait_for_ready_file(
        ready_file=ready_file,
        probe=_explode,
        drain_diagnostics=lambda: "",
        timeout_seconds=5.0,
    )


def test_ready_file_written_during_wait_succeeds(tmp_path: Path) -> None:
    """A marker that appears mid-wait resolves the wait successfully."""
    ready_file = tmp_path / "deferred.ready"
    app = _FakeLaunchedApp(
        stderr_text="",
        exit_code=0,
        ready_file=ready_file,
        delay_seconds=0.3,
    )
    try:
        wait_for_ready_file(
            ready_file=ready_file,
            probe=app.probe_launched_app,
            drain_diagnostics=app.drain_launch_diagnostics,
            timeout_seconds=5.0,
            poll_interval_seconds=0.02,
        )
    finally:
        app.cleanup()
    assert ready_file.exists()


def test_marker_written_then_immediate_exit_is_treated_as_ready(tmp_path: Path) -> None:
    """If the app writes the marker and exits in the same instant, that is success."""
    ready_file = tmp_path / "ready_then_exit.ready"
    app = _FakeLaunchedApp(stderr_text="", exit_code=0, ready_file=ready_file)
    app.cleanup()  # guarantee the process is fully dead before we wait
    wait_for_ready_file(
        ready_file=ready_file,
        probe=lambda: LaunchLiveness(alive=False, exit_code=0),
        drain_diagnostics=lambda: "",
        timeout_seconds=5.0,
        poll_interval_seconds=0.02,
    )
    assert ready_file.exists()
