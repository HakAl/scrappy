"""macOS real-terminal harness using iTerm2 and frontmost-app guards."""

from __future__ import annotations

import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any

import pytest

from .real_terminal_harness import RealTerminalHarnessProtocol, RealTerminalSessionSpec, RelativeSelection


MACOS_REQUIRED_TOOLS = ("osascript", "pbcopy", "pbpaste")


class MacOSHarnessError(RuntimeError):
    """Raised when the macOS real-terminal harness cannot guarantee safe execution."""


def _escape_applescript_string(value: str) -> str:
    """Escape a string for use inside a double-quoted AppleScript literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_shell_command(session: RealTerminalSessionSpec) -> str:
    """Build the shell command that iTerm2 should run in its new session."""
    parts = [f"cd {shlex.quote(str(session.fixture_repo))}"]
    env_pairs = {
        "SCRAPPY_INTEGRATION_LOG_PATH": str(session.debug_log_path),
        "SCRAPPY_READY_FILE": str(session.ready_file),
        **dict(session.env),
    }
    for key, value in env_pairs.items():
        parts.append(f"export {key}={shlex.quote(value)}")
    parts.append(f"exec {shlex.quote(str(session.venv_python))} -m {shlex.quote(session.entry_module)}")
    return " && ".join(parts)


def _parse_launch_identity(output: str) -> tuple[int, str]:
    """Parse the `windowId|sessionUniqueId` output from the iTerm2 launch script."""
    line = output.strip().splitlines()[-1]
    if "|" not in line:
        raise MacOSHarnessError(f"Unexpected iTerm2 launch identity output: {output!r}")
    window_id_text, session_id = line.split("|", 1)
    return int(window_id_text), session_id


def _wait_for_file(path: Path, *, timeout_seconds: float, description: str) -> None:
    """Wait for a file-based readiness marker produced by the launched app."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.1)
    raise MacOSHarnessError(f"Timed out waiting for {description} at {path}")


class MacOSTerminalHarness(RealTerminalHarnessProtocol):
    """macOS implementation using iTerm2 session ownership and frontmost-app guards."""

    name = "macos-iterm2"

    def __init__(self) -> None:
        self.debug_log: list[str] = []
        self._session: RealTerminalSessionSpec | None = None
        self._window_id: int | None = None
        self._session_unique_id: str | None = None
        self._previous_clipboard: str = ""

    def launch(self, session: RealTerminalSessionSpec) -> None:
        """Launch scrappy in a new iTerm2 window and record its owned identity."""
        if sys.platform != "darwin":
            pytest.skip("macOS harness is only available on darwin")

        self._session = session
        self._require_macos_tools()
        self._require_iterm2()
        self._previous_clipboard = self.read_clipboard()

        shell_command = _build_shell_command(session)
        output = self._run_osascript(
            [
                'tell application "iTerm2"',
                "activate",
                f'set newWindow to (create window with default profile command "{_escape_applescript_string(shell_command)}")',
                "set newSession to current session of current tab of newWindow",
                'return ((id of newWindow) as string) & "|" & (unique id of newSession)',
                "end tell",
            ]
        )
        self._window_id, self._session_unique_id = _parse_launch_identity(output)
        self.append_debug_event(
            "macos_launch_complete",
            window_id=self._window_id,
            session_id=self._session_unique_id,
        )

    def wait_until_ready(self, timeout_seconds: float) -> None:
        """Wait for the app's file-based readiness signal."""
        session = self._require_session()
        _wait_for_file(
            session.ready_file,
            timeout_seconds=timeout_seconds,
            description="scrappy readiness signal",
        )

    def clear_clipboard(self) -> None:
        """Clear the macOS clipboard."""
        self._run_command(["pbcopy"], input_text="")

    def read_clipboard(self) -> str:
        """Read the macOS clipboard."""
        result = self._run_command(["pbpaste"], check=False)
        return result.stdout if result.returncode == 0 else ""

    def focus_input(self, point: tuple[float, float]) -> tuple[int, int]:
        """Activate the owned iTerm2 window and click the input area."""
        self._activate_owned_window()
        geometry = self._get_owned_window_geometry()
        absolute_point = self._relative_point(geometry, point)
        self._post_mouse_click(absolute_point)
        return absolute_point

    def submit_command(self, command: str) -> None:
        """Type a command with System Events and press Return."""
        self._activate_owned_window()
        self._run_osascript(
            [
                'tell application "System Events"',
                f'keystroke "{_escape_applescript_string(command)}"',
                "key code 36",
                "end tell",
            ]
        )

    def wait_for_render(self, seconds: float) -> None:
        """Wait for terminal rendering when no stronger hook exists."""
        time.sleep(seconds)

    def drag_select(self, region: RelativeSelection) -> tuple[tuple[int, int], tuple[int, int]]:
        """Drag-select output text using Quartz mouse events with frontmost-app guards."""
        self._activate_owned_window()
        geometry = self._get_owned_window_geometry()
        start = self._relative_point(geometry, region.start)
        end = self._relative_point(geometry, region.end)

        self._post_mouse_drag(start, end, steps=14)
        return start, end

    def copy_selection(self) -> None:
        """Use Command-C on the frontmost iTerm2 window."""
        self._activate_owned_window()
        self._run_osascript(
            [
                'tell application "System Events"',
                'keystroke "c" using {command down}',
                "end tell",
            ]
        )

    def copy_selection_fallback(self) -> None:
        """Use the Edit > Copy menu item as a fallback copy path."""
        self._activate_owned_window()
        self._run_osascript(
            [
                'tell application "System Events"',
                'tell process "iTerm2"',
                'click menu item "Copy" of menu "Edit" of menu bar 1',
                "end tell",
                "end tell",
            ],
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
        """Close the owned iTerm2 window and restore the prior clipboard state."""
        try:
            window_id = self._window_id
            if window_id is not None:
                self._run_osascript(
                    [
                        'tell application "iTerm2"',
                        "repeat with aWindow in windows",
                        f"if id of aWindow is {window_id} then",
                        "close aWindow",
                        "exit repeat",
                        "end if",
                        "end repeat",
                        "end tell",
                    ],
                    check=False,
                )
                self.append_debug_event("iterm_window_closed", window_id=window_id)
        finally:
            self._run_command(["pbcopy"], input_text=self._previous_clipboard, check=False)
            self.append_debug_event("clipboard_restored")

    def _require_macos_tools(self) -> None:
        """Skip if the core macOS CLI tools are unavailable."""
        missing = [tool for tool in MACOS_REQUIRED_TOOLS if shutil.which(tool) is None]
        if missing:
            pytest.skip(f"macOS real-terminal harness requires: {', '.join(missing)}")

    def _require_iterm2(self) -> None:
        """Skip if iTerm2 is not installed or not scriptable."""
        result = self._run_command(
            ["osascript", "-e", 'tell application "iTerm2" to return version'],
            check=False,
        )
        if result.returncode != 0:
            pytest.skip("iTerm2 is unavailable or AppleScript cannot control it")

    def _run_command(
        self,
        command: list[str],
        *,
        input_text: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a local command and surface stdout/stderr on failure."""
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            input=input_text,
            check=False,
        )
        if check and result.returncode != 0:
            raise MacOSHarnessError(
                f"Command failed: {' '.join(command)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def _run_osascript(self, lines: list[str], *, check: bool = True) -> str:
        """Run AppleScript and return stdout."""
        result = self._run_command(["osascript", "-e", "\n".join(lines)], check=check)
        return result.stdout

    def _activate_owned_window(self) -> None:
        """Bring the owned iTerm2 window to the front and verify the app is frontmost."""
        window_id = self._require_window_id()
        self._run_osascript(
            [
                'tell application "iTerm2"',
                "activate",
                "repeat with aWindow in windows",
                f"if id of aWindow is {window_id} then",
                "select aWindow",
                "exit repeat",
                "end if",
                "end repeat",
                "end tell",
            ]
        )
        self._ensure_iterm_frontmost()

    def _ensure_iterm_frontmost(self) -> None:
        """Fail closed unless iTerm2 is currently frontmost."""
        frontmost = self._run_osascript(
            [
                'tell application "System Events"',
                'return name of first application process whose frontmost is true',
                "end tell",
            ]
        ).strip()
        if frontmost != "iTerm2":
            raise MacOSHarnessError(f"iTerm2 is not frontmost before input: {frontmost!r}")

    def _get_owned_window_geometry(self) -> tuple[int, int, int, int]:
        """Get the owned iTerm2 window position and size by its recorded window id."""
        window_id = self._require_window_id()
        output = self._run_osascript(
            [
                'tell application "iTerm2"',
                "repeat with aWindow in windows",
                f"if id of aWindow is {window_id} then",
                "set winPosition to position of aWindow",
                "set winSize to size of aWindow",
                'return (item 1 of winPosition as string) & "," & (item 2 of winPosition as string) & "|" & '
                '(item 1 of winSize as string) & "," & (item 2 of winSize as string)',
                "end if",
                "end repeat",
                'error "Owned iTerm2 window not found"',
                "end tell",
            ]
        ).strip()
        position_text, size_text = output.split("|", 1)
        left_text, top_text = position_text.split(",", 1)
        width_text, height_text = size_text.split(",", 1)
        return (int(left_text), int(top_text), int(width_text), int(height_text))

    def _relative_point(self, geometry: tuple[int, int, int, int], point: tuple[float, float]) -> tuple[int, int]:
        """Convert relative window coordinates into absolute screen coordinates."""
        x_ratio, y_ratio = point
        if not 0.0 <= x_ratio <= 1.0 or not 0.0 <= y_ratio <= 1.0:
            raise ValueError(f"Relative point out of bounds: {point}")
        left, top, width, height = geometry
        return (left + round(width * x_ratio), top + round(height * y_ratio))

    def _post_mouse_click(self, point: tuple[int, int]) -> None:
        """Post a left mouse click using Quartz events."""
        self._post_mouse_drag(point, point, steps=1)

    def _post_mouse_drag(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        *,
        steps: int,
    ) -> None:
        """Post a guarded drag gesture using Quartz mouse events."""
        try:
            import Quartz
        except ImportError as exc:  # pragma: no cover - mac-only dependency
            pytest.skip(f"Quartz accessibility APIs are unavailable: {exc}")

        self._ensure_iterm_frontmost()
        self._post_quartz_mouse_event(Quartz, Quartz.kCGEventMouseMoved, start)
        self._post_quartz_mouse_event(Quartz, Quartz.kCGEventLeftMouseDown, start)
        last_point = start
        try:
            for step in range(1, steps + 1):
                self._ensure_iterm_frontmost()
                x = round(start[0] + (end[0] - start[0]) * step / steps)
                y = round(start[1] + (end[1] - start[1]) * step / steps)
                last_point = (x, y)
                self._post_quartz_mouse_event(Quartz, Quartz.kCGEventLeftMouseDragged, last_point)
                time.sleep(0.03)
        finally:
            self._post_quartz_mouse_event(Quartz, Quartz.kCGEventLeftMouseUp, last_point)

    def _post_quartz_mouse_event(self, quartz: Any, event_type: int, point: tuple[int, int]) -> None:
        """Post a single Quartz mouse event to the HID event tap."""
        event = quartz.CGEventCreateMouseEvent(None, event_type, point, quartz.kCGMouseButtonLeft)
        quartz.CGEventPost(quartz.kCGHIDEventTap, event)

    def _require_session(self) -> RealTerminalSessionSpec:
        """Return the current session or fail if launch() was never called."""
        if self._session is None:
            raise MacOSHarnessError("macOS harness has no active session")
        return self._session

    def _require_window_id(self) -> int:
        """Return the owned iTerm2 window id or fail if launch() was never called."""
        if self._window_id is None:
            raise MacOSHarnessError("macOS harness has no owned window id")
        return self._window_id
