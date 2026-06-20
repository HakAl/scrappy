"""Tests for capturing the launched app's stderr in the real-terminal harnesses.

Review follow-up to the readiness-diagnostics work (scrappy-harness-ready-blind-
timeout-z9l6): the fail-fast path previously reported ``<none captured>`` for the
motivating case, a Python crash before readiness, because the app's stderr was lost
(it goes to the xterm PTY on Linux, and was never captured on Windows).

These tests are GUI-free and run on macOS: the Linux launch-command test really runs
``sh`` + ``python`` to prove the redirect routes child stderr to a file; the drain
tests exercise the diagnostic-selection logic directly. The full Xephyr / Windows
console launch paths remain unverifiable from macOS.
"""

from pathlib import Path
import subprocess
import sys

from .linux_terminal_harness import LinuxTerminalHarness, build_app_launch_command
from .real_terminal_harness import CapturedStream
from .windows_console_harness import WindowsOwnedConsoleHarness


def test_linux_app_launch_command_routes_child_stderr_to_file(tmp_path: Path) -> None:
    """The Linux launch wrapper must send the app's stderr to the capture file, not
    the inherited stderr stream, so a crash-before-ready leaves a diagnostic behind."""
    stderr_file = tmp_path / "app.stderr.log"
    command = build_app_launch_command(
        Path(sys.executable), "scrappy_definitely_missing_module_xyz", stderr_file
    )

    result = subprocess.run(command, capture_output=True, text=True)

    # `python -m <missing>` writes its error to stderr and exits non-zero.
    assert result.returncode != 0
    captured = stderr_file.read_text(encoding="utf-8")
    assert "scrappy_definitely_missing_module_xyz" in captured
    # The child's stderr was redirected into the file, so the parent stream is empty.
    # This is exactly the diagnostic that was previously lost to the PTY.
    assert result.stderr == ""


def test_linux_drain_prefers_app_stderr_then_falls_back_to_xterm() -> None:
    """drain_launch_diagnostics surfaces the app traceback when present, and otherwise
    falls back to xterm's own stderr (launch-phase X/display errors)."""
    harness = LinuxTerminalHarness()
    assert harness.drain_launch_diagnostics() == ""

    xterm = CapturedStream.create("test-xterm-")
    app = CapturedStream.create("test-app-")
    try:
        harness._xterm_stderr = xterm
        harness._app_stderr = app

        # App wrote nothing yet -> fall back to xterm stderr.
        xterm.handle.write(b"xterm: cannot open display :99\n")
        xterm.handle.flush()
        assert "cannot open display" in harness.drain_launch_diagnostics()

        # App stderr present -> it wins over the xterm fallback.
        app.handle.write(b"Traceback: ImportError onnxruntime boom\n")
        app.handle.flush()
        result = harness.drain_launch_diagnostics()
        assert "onnxruntime boom" in result
        assert "cannot open display" not in result
    finally:
        xterm.cleanup()
        app.cleanup()


def test_windows_drain_prefers_app_stderr_then_falls_back_to_debug_log(tmp_path: Path) -> None:
    """The Windows drain returns the captured app stderr when present, otherwise the
    structured debug-event trail."""
    harness = WindowsOwnedConsoleHarness()
    harness.debug_log = ["event: console_launched", "event: ready_wait_started"]

    # No capture file -> debug-log fallback.
    assert "ready_wait_started" in harness.drain_launch_diagnostics()

    stderr_file = tmp_path / "app.stderr.log"
    stderr_file.write_text("", encoding="utf-8")
    harness._app_stderr_path = stderr_file
    # Empty capture file -> still the debug-log fallback.
    assert "ready_wait_started" in harness.drain_launch_diagnostics()

    # Captured app stderr present -> it wins over the debug log.
    stderr_file.write_text("Traceback: ImportError onnxruntime boom\n", encoding="utf-8")
    result = harness.drain_launch_diagnostics()
    assert "onnxruntime boom" in result
    assert "ready_wait_started" not in result
