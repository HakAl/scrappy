"""Helpers for isolated real-console automation on Windows."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import types
from typing import Any

import pyperclip
import pytest

from .real_terminal_harness import (
    DEFAULT_DIAGNOSTICS_TAIL_CHARS,
    LaunchLiveness,
    RealTerminalHarnessProtocol,
    RealTerminalSessionSpec,
    RelativeSelection,
    wait_for_ready_file,
)


CONSOLE_READY_TIMEOUT_SECONDS = 20.0
FOREGROUND_TIMEOUT_SECONDS = 2.0
FOREGROUND_POLL_INTERVAL_SECONDS = 0.05
FOREGROUND_REASSERT_INTERVAL_SECONDS = 0.5


class IsolationError(RuntimeError):
    """Raised when the harness cannot prove input is isolated to its own window."""


def _prepare_windows_automation() -> tuple[Any, Any, Any, Any]:
    """Import Windows automation modules with a writable comtypes cache."""
    if sys.platform != "win32":  # pragma: no cover - Windows only
        pytest.skip("Windows automation is only available on win32")

    try:
        import comtypes
    except ImportError as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"comtypes is unavailable: {exc}")

    gen_dir = Path(__file__).resolve().parents[2] / ".tmp_comtypes_gen"
    gen_dir.mkdir(exist_ok=True)

    gen_module = types.ModuleType("comtypes.gen")
    gen_module.__path__ = [str(gen_dir)]
    sys.modules["comtypes.gen"] = gen_module
    comtypes.gen = gen_module

    try:
        from pywinauto import Application, keyboard, mouse
        import win32gui
        import win32process
    except ImportError as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"Windows automation dependencies are unavailable: {exc}")

    return Application, keyboard, mouse, (win32gui, win32process)


def _encode_powershell_command(script: str) -> str:
    """Encode a PowerShell script for -EncodedCommand."""
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def _escape_powershell_single_quoted(value: str) -> str:
    """Escape a string for safe embedding in single-quoted PowerShell."""
    return value.replace("'", "''")


def _validate_env_var_name(name: str) -> None:
    """Reject environment variable names that would be unsafe in PowerShell."""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
        raise ValueError(f"Invalid environment variable name for PowerShell launch: {name!r}")


@dataclass(frozen=True)
class _WindowCandidate:
    """Observed top-level window metadata used for owned-console binding."""

    hwnd: int
    pid: int
    title: str
    class_name: str
    visible: bool


CONSOLE_WINDOW_CLASSES = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"}


def _collect_top_level_windows(win32gui: Any, win32process: Any) -> list[_WindowCandidate]:
    """Enumerate top-level windows with enough metadata to bind safely."""
    candidates: list[_WindowCandidate] = []

    def _collect(hwnd: int, _: object) -> None:
        _, owner_pid = win32process.GetWindowThreadProcessId(hwnd)
        candidates.append(
            _WindowCandidate(
                hwnd=hwnd,
                pid=owner_pid,
                title=win32gui.GetWindowText(hwnd),
                class_name=win32gui.GetClassName(hwnd),
                visible=bool(win32gui.IsWindowVisible(hwnd)),
            )
        )

    win32gui.EnumWindows(_collect, None)
    return candidates


def _is_console_candidate(candidate: _WindowCandidate) -> bool:
    """Restrict matching to known console-like top-level windows."""
    return candidate.visible and candidate.class_name in CONSOLE_WINDOW_CLASSES


def _select_owned_console_window(
    *,
    candidates: list[_WindowCandidate],
    process_pid: int,
    title: str,
) -> _WindowCandidate | None:
    """Choose the safest matching console window for the launched session."""
    console_candidates = [candidate for candidate in candidates if _is_console_candidate(candidate)]

    exact_matches = [
        candidate
        for candidate in console_candidates
        if candidate.pid == process_pid and candidate.title == title
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        raise IsolationError(
            f"Multiple console windows matched owned pid/title pid={process_pid} title={title!r}"
        )

    title_matches = [candidate for candidate in console_candidates if candidate.title == title]
    if len(title_matches) == 1:
        return title_matches[0]
    if len(title_matches) > 1:
        raise IsolationError(f"Multiple console windows matched owned title {title!r}")

    pid_matches = [candidate for candidate in console_candidates if candidate.pid == process_pid]
    if len(pid_matches) == 1:
        return pid_matches[0]
    if len(pid_matches) > 1:
        raise IsolationError(f"Multiple console windows matched owned pid {process_pid}")

    return None


def _describe_window_candidates(
    candidates: list[_WindowCandidate],
    *,
    process_pid: int,
    title: str,
) -> str:
    """Summarize observed windows that are relevant to the owned-console lookup."""
    relevant = [
        candidate
        for candidate in candidates
        if candidate.pid == process_pid
        or candidate.title == title
        or candidate.class_name in CONSOLE_WINDOW_CLASSES
    ]
    if not relevant:
        return "no relevant windows observed"
    return "; ".join(
        (
            f"hwnd={candidate.hwnd} pid={candidate.pid} class={candidate.class_name!r} "
            f"visible={candidate.visible} title={candidate.title!r}"
        )
        for candidate in relevant
    )


def _wait_for_console_window(
    *,
    process_pid: int,
    title: str,
    win32gui: Any,
    win32process: Any,
    timeout_seconds: float,
    debug_log: list[str] | None = None,
) -> int:
    """Wait for the exact top-level window owned by the launched console process."""
    deadline = time.time() + timeout_seconds
    last_snapshot = ""
    while time.time() < deadline:
        candidates = _collect_top_level_windows(win32gui, win32process)
        snapshot = _describe_window_candidates(candidates, process_pid=process_pid, title=title)
        if debug_log is not None and snapshot != last_snapshot:
            debug_log.append(f"window_snapshot {snapshot}")
        last_snapshot = snapshot

        candidate = _select_owned_console_window(
            candidates=candidates,
            process_pid=process_pid,
            title=title,
        )
        if candidate is not None:
            if debug_log is not None:
                debug_log.append(
                    "window_bound "
                    f"hwnd={candidate.hwnd} pid={candidate.pid} class={candidate.class_name!r} "
                    f"title={candidate.title!r}"
                )
            return candidate.hwnd
        time.sleep(0.1)
    raise IsolationError(
        "Timed out waiting for owned console window "
        f"title={title!r} pid={process_pid}. Observed: {last_snapshot}"
    )


@dataclass
class OwnedConsoleWindow:
    """A dedicated console window with guarded input and scoped teardown."""

    process: subprocess.Popen[str]
    title: str
    hwnd: int
    window: Any
    keyboard: Any
    mouse: Any
    win32gui: Any
    win32process: Any
    debug_log: list[str] = field(default_factory=list)

    @property
    def pid(self) -> int:
        """Return the launched console process id."""
        return self.process.pid

    def rectangle(self) -> tuple[int, int, int, int]:
        """Return the owned window rectangle."""
        return self.win32gui.GetWindowRect(self.hwnd)

    def _relative_point(self, x_ratio: float, y_ratio: float) -> tuple[int, int]:
        """Convert window-relative percentages into absolute screen coordinates."""
        if not 0.0 <= x_ratio <= 1.0 or not 0.0 <= y_ratio <= 1.0:
            raise ValueError(f"Relative point out of bounds: {(x_ratio, y_ratio)}")
        left, top, right, bottom = self.rectangle()
        x = left + round((right - left) * x_ratio)
        y = top + round((bottom - top) * y_ratio)
        return (x, y)

    def ensure_foreground(self, timeout_seconds: float = FOREGROUND_TIMEOUT_SECONDS) -> None:
        """Refuse to send input unless the owned window is the foreground window."""
        deadline = time.time() + timeout_seconds
        next_focus_attempt = time.time()
        self.window.set_focus()
        while time.time() < deadline:
            foreground_hwnd = self.win32gui.GetForegroundWindow()
            if foreground_hwnd == self.hwnd:
                return
            now = time.time()
            if now >= next_focus_attempt:
                self.window.set_focus()
                next_focus_attempt = now + FOREGROUND_REASSERT_INTERVAL_SECONDS
            time.sleep(FOREGROUND_POLL_INTERVAL_SECONDS)
        actual_hwnd = self.win32gui.GetForegroundWindow()
        actual_title = self.win32gui.GetWindowText(actual_hwnd)
        raise IsolationError(
            "Foreground window did not match owned console before input. "
            f"owned_hwnd={self.hwnd} actual_hwnd={actual_hwnd} actual_title={actual_title!r}"
        )

    def click_relative(self, x_ratio: float, y_ratio: float) -> tuple[int, int]:
        """Click inside the owned window after verifying focus."""
        coords = self._relative_point(x_ratio, y_ratio)
        self.ensure_foreground()
        self.mouse.click(coords=coords)
        self.debug_log.append(f"click_relative coords={coords}")
        return coords

    def type_keys(self, keys: str, *, pause: float = 0.03) -> None:
        """Type keys only when the owned console is confirmed foreground."""
        self.ensure_foreground()
        self.window.type_keys(keys, set_foreground=False, pause=pause)
        self.debug_log.append(f"type_keys keys={keys!r}")

    def drag_relative(
        self,
        *,
        start: tuple[float, float],
        end: tuple[float, float],
        steps: int = 14,
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        """Drag within the owned window and abort if focus is stolen mid-gesture."""
        start_coords = self._relative_point(*start)
        end_coords = self._relative_point(*end)
        last_coords = start_coords

        self.ensure_foreground()
        self.mouse.press(coords=start_coords)
        try:
            for step in range(1, steps + 1):
                if self.win32gui.GetForegroundWindow() != self.hwnd:
                    raise IsolationError("Foreground window changed during drag selection")
                x = round(start_coords[0] + (end_coords[0] - start_coords[0]) * step / steps)
                y = round(start_coords[1] + (end_coords[1] - start_coords[1]) * step / steps)
                last_coords = (x, y)
                self.mouse.move(coords=last_coords)
                time.sleep(0.03)
        finally:
            self.mouse.release(coords=last_coords)

        self.debug_log.append(f"drag_relative start={start_coords} end={end_coords}")
        return start_coords, end_coords

    def close(self) -> None:
        """Terminate only the owned console tree launched by this harness."""
        if self.process.pid <= 0:
            return

        # The host now exits with the app on a crash (no -NoExit), so by teardown it
        # may already be gone and its window with it. Reap it directly and skip the
        # foreground pid-match guard, which would spuriously fail against a missing
        # window.
        if self.process.poll() is not None:
            self.process.wait(timeout=5)
            self.debug_log.append(
                f"closed (already exited) pid={self.process.pid} code={self.process.returncode}"
            )
            return

        foreground_hwnd = self.win32gui.GetForegroundWindow()
        _, window_pid = self.win32process.GetWindowThreadProcessId(self.hwnd)
        if window_pid != self.process.pid:
            raise IsolationError(
                f"Refusing teardown because window pid {window_pid} "
                f"no longer matches owned pid {self.process.pid}"
            )

        taskkill_result = subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(self.process.pid)],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.debug_log.append(
            "closed "
            f"pid={self.process.pid} hwnd={self.hwnd} foreground_before_close={foreground_hwnd} "
            f"taskkill_returncode={taskkill_result.returncode}"
        )

    def capture_screen_artifact(self, path: Path) -> Path:
        """Capture the current owned window image to path."""
        self.window.capture_as_image().save(path)
        self.debug_log.append(f"capture_screen_artifact path={path}")
        return path


def launch_owned_console(
    *,
    title: str,
    script: str,
    cwd: Path,
    timeout_seconds: float = CONSOLE_READY_TIMEOUT_SECONDS,
) -> OwnedConsoleWindow:
    """Launch a dedicated PowerShell console and bind to its exact hwnd/pid."""
    Application, keyboard, mouse, win32_modules = _prepare_windows_automation()
    win32gui, win32process = win32_modules
    debug_log: list[str] = []

    safe_title = _escape_powershell_single_quoted(title)
    encoded_script = _encode_powershell_command(
        f"$host.UI.RawUI.WindowTitle = '{safe_title}'\n{script}\n"
    )
    # No -NoExit: the host must terminate when the launched app exits so that an
    # app-only crash (Python dying before readiness) ends the host process and is
    # observable via process liveness. The script ends with `exit $LASTEXITCODE`, so
    # the host's exit code mirrors the app's.
    process = subprocess.Popen(
        [
            "powershell.exe",
            "-NoLogo",
            "-EncodedCommand",
            encoded_script,
        ],
        cwd=str(cwd),
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )

    hwnd = _wait_for_console_window(
        process_pid=process.pid,
        title=title,
        win32gui=win32gui,
        win32process=win32process,
        timeout_seconds=timeout_seconds,
        debug_log=debug_log,
    )
    window = Application(backend="win32").connect(handle=hwnd).window(handle=hwnd)

    harness = OwnedConsoleWindow(
        process=process,
        title=title,
        hwnd=hwnd,
        window=window,
        keyboard=keyboard,
        mouse=mouse,
        win32gui=win32gui,
        win32process=win32process,
        debug_log=debug_log,
    )
    harness.debug_log.append(f"launched title={title!r} pid={process.pid} hwnd={hwnd}")
    return harness


class WindowsOwnedConsoleHarness(RealTerminalHarnessProtocol):
    """Windows implementation of the platform-neutral real-terminal harness."""

    name = "windows-owned-console"

    def __init__(self) -> None:
        self.debug_log: list[str] = []
        self._console: OwnedConsoleWindow | None = None
        self._session: RealTerminalSessionSpec | None = None
        self._previous_clipboard: str = ""
        self._app_stderr_path: Path | None = None

    def launch(self, session: RealTerminalSessionSpec) -> None:
        """Launch scrappy in an owned PowerShell console."""
        self._session = session
        for key in session.env:
            _validate_env_var_name(key)

        self._previous_clipboard = pyperclip.paste()

        # Capture the launched app's stderr to a file so a Python crash before
        # readiness is preserved rather than scrolling past in the console. The temp
        # handle is closed immediately so PowerShell can open the path for writing
        # (Windows would otherwise raise a sharing violation against an open handle).
        stderr_tmp = tempfile.NamedTemporaryFile(
            prefix="scrappy-winapp-", suffix=".stderr.log", delete=False
        )
        stderr_tmp.close()
        self._app_stderr_path = Path(stderr_tmp.name)

        launch_script_lines = [
            f"Set-Location -LiteralPath '{_escape_powershell_single_quoted(str(session.fixture_repo))}'",
        ]
        for key, value in session.env.items():
            launch_script_lines.append(
                f"$env:{key} = '{_escape_powershell_single_quoted(str(value))}'"
            )
        launch_script_lines.extend(
            [
                f"$env:SCRAPPY_INTEGRATION_LOG_PATH = '{_escape_powershell_single_quoted(str(session.debug_log_path))}'",
                f"$env:SCRAPPY_READY_FILE = '{_escape_powershell_single_quoted(str(session.ready_file))}'",
                # Redirect app stderr to the capture file (stdout stays on the console
                # so the TUI still renders), then propagate the app's exit code so the
                # host (launched without -NoExit) dies with the child on a crash.
                f"& '{_escape_powershell_single_quoted(str(session.venv_python))}' -m {session.entry_module}"
                f" 2> '{_escape_powershell_single_quoted(str(self._app_stderr_path))}'",
                "exit $LASTEXITCODE",
            ]
        )
        launch_script = "\n".join(launch_script_lines) + "\n"

        self._console = launch_owned_console(
            title=session.title,
            script=launch_script,
            cwd=session.fixture_repo,
        )
        self.debug_log = self._console.debug_log
        self.append_debug_event("console_launched", pid=self._console.pid, hwnd=self._console.hwnd)

    def wait_until_ready(self, timeout_seconds: float) -> None:
        """Wait for readiness, failing fast if the owned console dies before signaling."""
        session = self._require_session()
        wait_for_ready_file(
            ready_file=session.ready_file,
            probe=self.probe_launched_app,
            drain_diagnostics=self.drain_launch_diagnostics,
            timeout_seconds=timeout_seconds,
            error_factory=IsolationError,
        )

    def probe_launched_app(self) -> LaunchLiveness:
        """Report liveness from the owned PowerShell console process.

        The host is launched without ``-NoExit`` and its script ends with
        ``exit $LASTEXITCODE``, so when the inner python process crashes the host exits
        with the app's code rather than dropping to a prompt. Polling the host process
        therefore detects an app-only crash and reports the propagated exit code, which
        lets the readiness wait fail fast instead of blocking to the timeout. The exit
        code path could not be verified from macOS.
        """
        console = self._console
        if console is None:
            return LaunchLiveness(alive=True)
        code = console.process.poll()
        if code is None:
            return LaunchLiveness(alive=True)
        return LaunchLiveness(alive=False, exit_code=code)

    def drain_launch_diagnostics(self) -> str:
        """Return the launched app's captured stderr, falling back to the debug log.

        The app's stderr is redirected to a capture file in the launch script, so a
        Python crash before readiness lands there. When that file is empty (for example
        a host/console failure before the app ran), fall back to the structured
        debug-event trail.
        """
        path = self._app_stderr_path
        if path is not None:
            try:
                tail = path.read_text(encoding="utf-8", errors="replace")[-DEFAULT_DIAGNOSTICS_TAIL_CHARS:]
            except OSError:
                tail = ""
            if tail.strip():
                return tail
        if not self.debug_log:
            return ""
        return "\n".join(self.debug_log[-20:])

    def clear_clipboard(self) -> None:
        """Clear the Windows clipboard."""
        pyperclip.copy("")

    def read_clipboard(self) -> str:
        """Read the Windows clipboard."""
        return pyperclip.paste()

    def focus_input(self, point: tuple[float, float]) -> tuple[int, int]:
        """Focus the scrappy input area in the owned console."""
        return self._require_console().click_relative(*point)

    def submit_command(self, command: str) -> None:
        """Submit a command followed by Enter."""
        self._require_console().type_keys(f"{command}{{ENTER}}")

    def wait_for_render(self, seconds: float) -> None:
        """Wait for the console to render follow-up output."""
        time.sleep(seconds)

    def drag_select(self, region: RelativeSelection) -> tuple[tuple[int, int], tuple[int, int]]:
        """Drag-select an output region in the owned console."""
        return self._require_console().drag_relative(start=region.start, end=region.end)

    def copy_selection(self) -> None:
        """Send the primary Windows copy shortcut."""
        self._require_console().type_keys("^c")

    def copy_selection_fallback(self) -> None:
        """Send the alternate Windows copy shortcut."""
        self._require_console().type_keys("^+c")

    def capture_screen_artifact(self, label: str) -> Path | None:
        """Capture the owned terminal window to an artifact PNG."""
        session = self._require_session()
        safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "-", label).strip("-") or "screen"
        path = session.debug_log_path.with_name(
            f"{session.debug_log_path.stem}-{safe_label}.png"
        )
        captured_path = self._require_console().capture_screen_artifact(path)
        self.append_debug_event(
            "screen_captured",
            label=label,
            path=str(captured_path),
        )
        return captured_path

    def append_debug_event(self, stage: str, **fields: object) -> None:
        """Append a structured event to the workspace-local debug log."""
        session = self._session
        if session is None:
            return

        payload: dict[str, object] = {
            "ts": round(time.time(), 3),
            "source": self.name,
            "stage": stage,
        }
        payload.update(fields)

        log_path = session.debug_log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

        self.debug_log.append(f"{stage}: {fields}")

    def close(self) -> None:
        """Close the owned console and restore the prior clipboard contents."""
        try:
            console = self._console
            if console is not None:
                console.close()
                self.append_debug_event("console_closed", pid=console.pid)
        finally:
            try:
                pyperclip.copy(self._previous_clipboard)
                self.append_debug_event("clipboard_restored")
            except pyperclip.PyperclipException:
                pass
            stderr_path = self._app_stderr_path
            if stderr_path is not None:
                try:
                    stderr_path.unlink()
                except OSError:
                    pass
                self._app_stderr_path = None

    def _require_console(self) -> OwnedConsoleWindow:
        """Return the launched console or fail if launch() was never called."""
        if self._console is None:
            raise IsolationError("Console harness used before launch()")
        return self._console

    def _require_session(self) -> RealTerminalSessionSpec:
        """Return the current session or fail if launch() was never called."""
        if self._session is None:
            raise IsolationError("Console harness has no active session")
        return self._session
