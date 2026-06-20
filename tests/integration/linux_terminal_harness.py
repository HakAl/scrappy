"""Linux X11-first real-terminal harness."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Mapping

import pytest

from .real_terminal_harness import (
    CapturedStream,
    LaunchLiveness,
    RealTerminalHarnessProtocol,
    RealTerminalSessionSpec,
    RelativeSelection,
    wait_for_ready_file,
)


LINUX_REQUIRED_TOOLS = ("Xephyr", "xterm", "xdotool", "xclip")
DEFAULT_DISPLAY_SCAN_RANGE = range(90, 110)
DEFAULT_DRAG_STEPS = 14


class LinuxHarnessError(RuntimeError):
    """Raised when the Linux real-terminal harness cannot guarantee execution."""


@dataclass(frozen=True)
class _LinuxWindowGeometry:
    """Window geometry parsed from xdotool shell output."""

    window_id: int
    x: int
    y: int
    width: int
    height: int


def _parse_xdotool_shell_geometry(output: str) -> _LinuxWindowGeometry:
    """Parse `xdotool getwindowgeometry --shell` output."""
    values: dict[str, int] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in {"WINDOW", "X", "Y", "WIDTH", "HEIGHT"}:
            values[key] = int(value)

    required = {"WINDOW", "X", "Y", "WIDTH", "HEIGHT"}
    missing = required - values.keys()
    if missing:
        raise LinuxHarnessError(f"Missing geometry fields from xdotool output: {sorted(missing)}")

    return _LinuxWindowGeometry(
        window_id=values["WINDOW"],
        x=values["X"],
        y=values["Y"],
        width=values["WIDTH"],
        height=values["HEIGHT"],
    )


def _find_free_display_number(
    *,
    display_dir: Path = Path("/tmp/.X11-unix"),
    lock_dir: Path = Path("/tmp"),
    candidates=DEFAULT_DISPLAY_SCAN_RANGE,
) -> int:
    """Return a likely-free X display number by checking sockets and lock files."""
    for display_number in candidates:
        socket_path = display_dir / f"X{display_number}"
        lock_path = lock_dir / f".X{display_number}-lock"
        if socket_path.exists() or lock_path.exists():
            continue
        return display_number
    raise LinuxHarnessError("Unable to find a free X display number for Xephyr")


def build_app_launch_command(
    venv_python: Path, entry_module: str, app_stderr_path: Path
) -> list[str]:
    """Build the ``xterm -e`` command that runs the app with its stderr captured.

    xterm routes a child's stderr to its PTY, so an app crash (for example a Python
    import error before readiness) would otherwise be invisible to the harness. The
    launch is wrapped in ``sh -c 'exec ... 2>>file'`` so the app's stderr is appended
    to a captured file while stdout stays on the PTY and the terminal UI still renders.
    ``exec`` replaces the shell with python, so the process tree stays ``xterm -> python``
    and liveness polling of the xterm child is unaffected. Paths are passed as shell
    positional arguments to avoid quoting issues.
    """
    return [
        "sh",
        "-c",
        'exec "$0" -m "$1" 2>>"$2"',
        str(venv_python),
        entry_module,
        str(app_stderr_path),
    ]


class LinuxTerminalHarness(RealTerminalHarnessProtocol):
    """Linux implementation using Xephyr, xterm, xdotool, and xclip."""

    name = "linux-x11-xephyr"

    def __init__(self) -> None:
        self.debug_log: list[str] = []
        self._session: RealTerminalSessionSpec | None = None
        self._display = ""
        self._cached_display_env: dict[str, str] | None = None
        self._xephyr_process: subprocess.Popen[str] | None = None
        self._xterm_process: subprocess.Popen[str] | None = None
        self._xephyr_stderr: CapturedStream | None = None
        self._xterm_stderr: CapturedStream | None = None
        self._app_stderr: CapturedStream | None = None
        self._window_id: int | None = None

    def launch(self, session: RealTerminalSessionSpec) -> None:
        """Launch scrappy in a nested X11 display under Xephyr."""
        if sys.platform != "linux":
            pytest.skip("Linux harness is only available on linux")

        self._session = session
        self._require_linux_tools()

        display_number = _find_free_display_number()
        self._display = f":{display_number}"
        self._cached_display_env = self._build_display_env(session.env)
        self._xephyr_stderr = CapturedStream.create("scrappy-xephyr-")
        self._xephyr_process = subprocess.Popen(
            [
                "Xephyr",
                self._display,
                "-screen",
                "1400x900x24",
                "-ac",
                "-br",
                "-noreset",
            ],
            stdout=subprocess.DEVNULL,
            stderr=self._xephyr_stderr.handle,
        )
        self._wait_for_display_socket(display_number)

        self._xterm_stderr = CapturedStream.create("scrappy-xterm-")
        self._app_stderr = CapturedStream.create("scrappy-app-")
        self._xterm_process = subprocess.Popen(
            [
                "xterm",
                "-geometry",
                "120x40",
                "-T",
                session.title,
                "-e",
                *build_app_launch_command(
                    session.venv_python, session.entry_module, self._app_stderr.path
                ),
            ],
            cwd=str(session.fixture_repo),
            env=self._cached_display_env,
            stdout=subprocess.DEVNULL,
            stderr=self._xterm_stderr.handle,
        )
        self._window_id = self._find_window_id(session.title)
        self.append_debug_event(
            "linux_launch_complete",
            display=self._display,
            xephyr_pid=self._xephyr_process.pid,
            xterm_pid=self._xterm_process.pid,
            window_id=self._window_id,
        )

    def wait_until_ready(self, timeout_seconds: float) -> None:
        """Wait for readiness, failing fast if xterm/the app dies before signaling."""
        session = self._require_session()
        wait_for_ready_file(
            ready_file=session.ready_file,
            probe=self.probe_launched_app,
            drain_diagnostics=self.drain_launch_diagnostics,
            timeout_seconds=timeout_seconds,
            error_factory=LinuxHarnessError,
        )

    def probe_launched_app(self) -> LaunchLiveness:
        """Report liveness from the xterm child that hosts the launched app.

        ``xterm -e python ...`` exits when the launched python process exits, so xterm
        terminating is the app's death signal for this harness. The reported exit code
        is xterm's own (which does not always mirror the app's), but death itself is
        what makes the readiness wait fail fast instead of blocking.
        """
        process = self._xterm_process
        if process is None:
            return LaunchLiveness(alive=True)
        code = process.poll()
        if code is None:
            return LaunchLiveness(alive=True)
        return LaunchLiveness(alive=False, exit_code=code)

    def drain_launch_diagnostics(self) -> str:
        """Return the launched app's captured stderr, falling back to xterm's own.

        The app runs as ``xterm -e sh -c 'exec python ... 2>>file'``, so a Python crash
        before readiness (the motivating app-death case) lands in the app-stderr file
        rather than being lost to the PTY. When the app wrote nothing, fall back to
        xterm's own stderr (X protocol/display/font errors that explain a failed launch),
        which is the diagnostic that was previously discarded to DEVNULL.
        """
        app = self._app_stderr
        app_tail = app.read_tail() if app is not None else ""
        if app_tail.strip():
            return app_tail
        xterm = self._xterm_stderr
        return xterm.read_tail() if xterm is not None else ""

    def clear_clipboard(self) -> None:
        """Clear the X11 CLIPBOARD selection on the nested display."""
        self._run_display_command(
            ["xclip", "-selection", "clipboard", "-i"],
            input_text="",
            check=False,
        )

    def read_clipboard(self) -> str:
        """Read the X11 CLIPBOARD selection from the nested display."""
        result = self._run_display_command(
            ["xclip", "-selection", "clipboard", "-o"],
            check=False,
        )
        if result.returncode != 0:
            return ""
        return result.stdout

    def focus_input(self, point: tuple[float, float]) -> tuple[int, int]:
        """Focus the xterm window and click the input area."""
        window_id = self._require_window_id()
        geometry = self._get_window_geometry()
        rel_x, rel_y = self._relative_point(geometry, point)
        abs_point = (geometry.x + rel_x, geometry.y + rel_y)

        self._run_display_command(["xdotool", "windowfocus", "--sync", str(window_id)])
        self._run_display_command(
            ["xdotool", "mousemove", "--window", str(window_id), str(rel_x), str(rel_y)]
        )
        self._run_display_command(["xdotool", "click", "1"])
        return abs_point

    def submit_command(self, command: str) -> None:
        """Submit a command and press Enter in the nested terminal."""
        window_id = self._require_window_id()
        self._run_display_command(
            ["xdotool", "key", "--window", str(window_id), "--clearmodifiers", "Escape"]
        )
        self._run_display_command(
            ["xdotool", "type", "--window", str(window_id), "--delay", "20", command]
        )
        self._run_display_command(
            ["xdotool", "key", "--window", str(window_id), "Return"]
        )

    def wait_for_render(self, seconds: float) -> None:
        """Wait for terminal rendering when no stronger hook exists."""
        time.sleep(seconds)

    def drag_select(self, region: RelativeSelection) -> tuple[tuple[int, int], tuple[int, int]]:
        """Drag-select text within the nested xterm window."""
        window_id = self._require_window_id()
        geometry = self._get_window_geometry()
        start_rel = self._relative_point(geometry, region.start)
        end_rel = self._relative_point(geometry, region.end)
        start_abs = (geometry.x + start_rel[0], geometry.y + start_rel[1])
        end_abs = (geometry.x + end_rel[0], geometry.y + end_rel[1])

        self._run_display_command(["xdotool", "windowfocus", "--sync", str(window_id)])
        self._run_display_command(
            ["xdotool", "mousemove", "--window", str(window_id), str(start_rel[0]), str(start_rel[1])]
        )
        self._run_display_command(["xdotool", "mousedown", "1"])
        try:
            for step in range(1, DEFAULT_DRAG_STEPS + 1):
                x = round(start_rel[0] + (end_rel[0] - start_rel[0]) * step / DEFAULT_DRAG_STEPS)
                y = round(start_rel[1] + (end_rel[1] - start_rel[1]) * step / DEFAULT_DRAG_STEPS)
                self._run_display_command(
                    ["xdotool", "mousemove", "--window", str(window_id), str(x), str(y)]
                )
                time.sleep(0.03)
        finally:
            self._run_display_command(["xdotool", "mouseup", "1"], check=False)

        return start_abs, end_abs

    def copy_selection(self) -> None:
        """Try the terminal copy shortcut first."""
        window_id = self._require_window_id()
        self._run_display_command(
            ["xdotool", "key", "--window", str(window_id), "--clearmodifiers", "ctrl+shift+c"],
            check=False,
        )

    def copy_selection_fallback(self) -> None:
        """Transfer the X11 PRIMARY selection into CLIPBOARD explicitly."""
        primary_text = self._run_display_command(
            ["xclip", "-selection", "primary", "-o"],
            check=False,
        ).stdout
        self._run_display_command(
            ["xclip", "-selection", "clipboard", "-i"],
            input_text=primary_text,
            check=False,
        )

    def capture_screen_artifact(self, label: str) -> Path | None:
        """Capture the current terminal screen when the platform supports it."""
        self.append_debug_event("screen_capture_unsupported", label=label)
        return None

    def append_debug_event(self, stage: str, **fields: object) -> None:
        """Append a structured debug event to the session log."""
        session = self._session
        if session is None:
            return

        payload: dict[str, object] = {
            "ts": round(time.time(), 3),
            "source": self.name,
            "stage": stage,
        }
        payload.update(fields)

        session.debug_log_path.parent.mkdir(parents=True, exist_ok=True)
        with session.debug_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

        self.debug_log.append(f"{stage}: {fields}")

    def close(self) -> None:
        """Terminate xterm first, then tear down the nested X server."""
        xterm_process = self._xterm_process
        xephyr_process = self._xephyr_process

        if xterm_process is not None:
            self._terminate_process(xterm_process)
            self.append_debug_event("xterm_closed", pid=xterm_process.pid)

        if xephyr_process is not None:
            self._terminate_process(xephyr_process)
            self.append_debug_event("xephyr_closed", pid=xephyr_process.pid, display=self._display)

        for captured in (self._xterm_stderr, self._xephyr_stderr, self._app_stderr):
            if captured is not None:
                captured.cleanup()
        self._xterm_stderr = None
        self._xephyr_stderr = None
        self._app_stderr = None

    def _stderr_suffix(self, captured: CapturedStream | None) -> str:
        """Format a captured-stderr tail for inclusion in a launch-failure message."""
        if captured is None:
            return ""
        tail = captured.read_tail().strip()
        if not tail:
            return ""
        return f"\ncaptured stderr tail:\n{tail}"

    def _build_display_env(self, extra_env: Mapping[str, str] | None = None) -> dict[str, str]:
        """Build the environment for processes that run inside the nested display."""
        session = self._require_session()
        env = dict(os.environ)
        env["DISPLAY"] = self._display
        env["SCRAPPY_INTEGRATION_LOG_PATH"] = str(session.debug_log_path)
        env["SCRAPPY_READY_FILE"] = str(session.ready_file)
        env.update(extra_env or {})
        return env

    def _run_display_command(
        self,
        command: list[str],
        *,
        input_text: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a command scoped to the nested display."""
        display_env = self._cached_display_env
        if display_env is None:
            raise LinuxHarnessError("Linux display environment is not initialized")
        result = subprocess.run(
            command,
            env=display_env,
            capture_output=True,
            text=True,
            input=input_text,
            check=False,
        )
        if check and result.returncode != 0:
            raise LinuxHarnessError(
                f"Display command failed: {' '.join(command)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def _wait_for_display_socket(self, display_number: int, timeout_seconds: float = 5.0) -> None:
        """Wait for the Xephyr display socket to appear."""
        socket_path = Path("/tmp/.X11-unix") / f"X{display_number}"
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if socket_path.exists():
                return
            xephyr_process = self._xephyr_process
            if xephyr_process is not None and xephyr_process.poll() is not None:
                raise LinuxHarnessError(
                    f"Xephyr exited (code {xephyr_process.returncode}) before opening "
                    f"display {self._display}" + self._stderr_suffix(self._xephyr_stderr)
                )
            time.sleep(0.1)
        raise LinuxHarnessError(f"Timed out waiting for Xephyr display {self._display}")

    def _find_window_id(self, title: str, timeout_seconds: float = 10.0) -> int:
        """Find the xterm window id inside the nested display."""
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            result = self._run_display_command(
                ["xdotool", "search", "--onlyvisible", "--name", title],
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip().splitlines()[0])
            xterm_process = self._xterm_process
            if xterm_process is not None and xterm_process.poll() is not None:
                raise LinuxHarnessError(
                    f"xterm exited (code {xterm_process.returncode}) before window "
                    f"discovery for {title!r}" + self._stderr_suffix(self._xterm_stderr)
                )
            time.sleep(0.1)
        raise LinuxHarnessError(f"Timed out waiting for xterm window titled {title!r}")

    def _get_window_geometry(self) -> _LinuxWindowGeometry:
        """Read geometry for the nested xterm window."""
        window_id = self._require_window_id()
        result = self._run_display_command(
            ["xdotool", "getwindowgeometry", "--shell", str(window_id)]
        )
        return _parse_xdotool_shell_geometry(result.stdout)

    def _relative_point(
        self,
        geometry: _LinuxWindowGeometry,
        point: tuple[float, float],
    ) -> tuple[int, int]:
        """Convert relative coordinates into xterm-window-relative coordinates."""
        x_ratio, y_ratio = point
        if not 0.0 <= x_ratio <= 1.0 or not 0.0 <= y_ratio <= 1.0:
            raise ValueError(f"Relative point out of bounds: {point}")
        return (
            round(geometry.width * x_ratio),
            round(geometry.height * y_ratio),
        )

    def _terminate_process(self, process: subprocess.Popen[str]) -> None:
        """Terminate an owned child process with a kill fallback.

        Linux teardown uses direct `Popen` handles rather than PID/window ownership
        checks because there is no shared terminal host comparable to Windows Terminal.
        """
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def _require_linux_tools(self) -> None:
        """Skip if the required X11 tooling is unavailable."""
        missing = [tool for tool in LINUX_REQUIRED_TOOLS if shutil.which(tool) is None]
        if missing:
            pytest.skip(f"Linux real-terminal harness requires: {', '.join(missing)}")

    def _require_session(self) -> RealTerminalSessionSpec:
        """Return the active session or fail if launch() was never called."""
        if self._session is None:
            raise LinuxHarnessError("Linux harness has no active session")
        return self._session

    def _require_window_id(self) -> int:
        """Return the xterm window id or fail if launch() was never called."""
        if self._window_id is None:
            raise LinuxHarnessError("Linux harness has no active xterm window")
        return self._window_id
