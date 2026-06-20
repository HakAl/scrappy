"""Tests for the owned console isolation harness."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.integration.real_terminal_harness import RealTerminalSessionSpec
from tests.integration.windows_console_harness import (
    IsolationError,
    OwnedConsoleWindow,
    WindowsOwnedConsoleHarness,
    _wait_for_console_window,
)


@dataclass
class _FakeProcess:
    pid: int
    poll_result: int | None = None
    wait_calls: int = 0
    kill_calls: int = 0

    @property
    def returncode(self) -> int | None:
        return self.poll_result

    def poll(self) -> int | None:
        """Mirror subprocess.Popen.poll: None while alive, the exit code once done."""
        return self.poll_result

    def wait(self, timeout: float) -> None:
        self.wait_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1


class _FakeWindow:
    def __init__(self) -> None:
        self.focus_calls = 0

    def set_focus(self) -> None:
        self.focus_calls += 1

    def type_keys(self, keys: str, set_foreground: bool = False, pause: float = 0.03) -> None:
        return None


class _FakeMouse:
    def __init__(self) -> None:
        self.events: list[tuple[str, tuple[int, int]]] = []

    def click(self, coords: tuple[int, int]) -> None:
        self.events.append(("click", coords))

    def press(self, coords: tuple[int, int]) -> None:
        self.events.append(("press", coords))

    def move(self, coords: tuple[int, int]) -> None:
        self.events.append(("move", coords))

    def release(self, coords: tuple[int, int]) -> None:
        self.events.append(("release", coords))


class _FakeWin32Gui:
    def __init__(
        self,
        *,
        foreground_hwnd: int,
        rect: tuple[int, int, int, int],
        title: str,
        foreground_sequence: list[int] | None = None,
        windows: list[tuple[int, str, str, bool]] | None = None,
    ) -> None:
        self._foreground_hwnd = foreground_hwnd
        self._rect = rect
        self._title = title
        self._foreground_sequence = foreground_sequence or []
        self._windows = windows or []

    def GetWindowRect(self, hwnd: int) -> tuple[int, int, int, int]:
        return self._rect

    def GetForegroundWindow(self) -> int:
        if self._foreground_sequence:
            return self._foreground_sequence.pop(0)
        return self._foreground_hwnd

    def GetWindowText(self, hwnd: int) -> str:
        for candidate_hwnd, candidate_title, _, _ in self._windows:
            if candidate_hwnd == hwnd:
                return candidate_title
        return self._title

    def GetClassName(self, hwnd: int) -> str:
        for candidate_hwnd, _, class_name, _ in self._windows:
            if candidate_hwnd == hwnd:
                return class_name
        return "ConsoleWindowClass"

    def IsWindowVisible(self, hwnd: int) -> bool:
        for candidate_hwnd, _, _, visible in self._windows:
            if candidate_hwnd == hwnd:
                return visible
        return True

    def EnumWindows(self, callback, extra: object) -> None:
        for candidate_hwnd, _, _, _ in self._windows:
            callback(candidate_hwnd, extra)


class _FakeWin32Process:
    def __init__(self, *, owner_pid: int, pid_by_hwnd: dict[int, int] | None = None) -> None:
        self._owner_pid = owner_pid
        self._pid_by_hwnd = pid_by_hwnd or {}

    def GetWindowThreadProcessId(self, hwnd: int) -> tuple[int, int]:
        return (1, self._pid_by_hwnd.get(hwnd, self._owner_pid))


def _build_owned_console(
    *,
    pid: int = 101,
    hwnd: int = 222,
    foreground_hwnd: int = 222,
    owner_pid: int = 101,
    foreground_sequence: list[int] | None = None,
    poll_result: int | None = None,
) -> OwnedConsoleWindow:
    return OwnedConsoleWindow(
        process=_FakeProcess(pid=pid, poll_result=poll_result),
        title="owned-console",
        hwnd=hwnd,
        window=_FakeWindow(),
        keyboard=object(),
        mouse=_FakeMouse(),
        win32gui=_FakeWin32Gui(
            foreground_hwnd=foreground_hwnd,
            rect=(100, 200, 500, 700),
            title="other-window",
            foreground_sequence=foreground_sequence,
        ),
        win32process=_FakeWin32Process(owner_pid=owner_pid),
    )


def test_relative_point_uses_window_bounds():
    """Relative coordinates should stay anchored to the owned window rectangle."""
    owned = _build_owned_console()

    assert owned._relative_point(0.25, 0.50) == (200, 450)


def test_ensure_foreground_refuses_unsafe_input():
    """Harness should refuse input when another window owns the foreground."""
    owned = _build_owned_console(foreground_hwnd=999)

    with pytest.raises(IsolationError, match="Foreground window did not match owned console"):
        owned.ensure_foreground(timeout_seconds=0.01)


def test_close_refuses_pid_mismatch():
    """Harness should refuse teardown when the tracked hwnd no longer belongs to the owned pid."""
    owned = _build_owned_console(owner_pid=404)

    with pytest.raises(IsolationError, match="Refusing teardown because window pid 404 no longer matches owned pid 101"):
        owned.close()


def test_close_reaps_already_exited_host_without_pid_check():
    """A host that already exited (it now propagates an app crash's exit code) is reaped
    directly, skipping the foreground pid-match guard that would otherwise fail against
    the already-gone console window."""
    owned = _build_owned_console(owner_pid=404, poll_result=3)

    owned.close()  # must not raise despite the pid mismatch, because the host is dead

    assert owned.process.wait_calls == 1


def test_drag_relative_aborts_when_foreground_changes(monkeypatch: pytest.MonkeyPatch):
    """Harness should abort a drag if focus leaves the owned window mid-gesture."""
    owned = _build_owned_console(foreground_sequence=[222, 999])

    monkeypatch.setattr("tests.integration.windows_console_harness.time.sleep", lambda _: None)

    with pytest.raises(IsolationError, match="Foreground window changed during drag selection"):
        owned.drag_relative(start=(0.10, 0.10), end=(0.90, 0.90), steps=2)

    assert owned.mouse.events == [
        ("press", (140, 250)),
        ("release", (140, 250)),
    ]


def test_windows_harness_rejects_invalid_env_var_names():
    """Windows launch script generation should reject unsafe environment variable names."""
    harness = WindowsOwnedConsoleHarness()
    session = RealTerminalSessionSpec(
        title="owned-console",
        fixture_repo=Path("fixture"),
        venv_python=Path("python"),
        debug_log_path=Path("debug.jsonl"),
        ready_file=Path("ready.signal"),
        env={"BAD;NAME": "1"},
    )

    with pytest.raises(ValueError, match="Invalid environment variable name"):
        harness.launch(session)


def test_wait_for_console_window_binds_exact_pid_and_title(monkeypatch: pytest.MonkeyPatch):
    """Window discovery should prefer an exact pid/title console match."""
    win32gui = _FakeWin32Gui(
        foreground_hwnd=0,
        rect=(0, 0, 0, 0),
        title="unused",
        windows=[
            (11, "other", "ConsoleWindowClass", True),
            (22, "owned-title", "ConsoleWindowClass", True),
        ],
    )
    win32process = _FakeWin32Process(owner_pid=999, pid_by_hwnd={11: 999, 22: 101})
    monkeypatch.setattr("tests.integration.windows_console_harness.time.sleep", lambda _: None)

    hwnd = _wait_for_console_window(
        process_pid=101,
        title="owned-title",
        win32gui=win32gui,
        win32process=win32process,
        timeout_seconds=0.01,
        debug_log=[],
    )

    assert hwnd == 22


def test_wait_for_console_window_allows_unique_title_match_when_pid_differs(
    monkeypatch: pytest.MonkeyPatch,
):
    """Discovery should bind a unique console title even if the console host owns the hwnd."""
    win32gui = _FakeWin32Gui(
        foreground_hwnd=0,
        rect=(0, 0, 0, 0),
        title="unused",
        windows=[
            (33, "owned-title", "ConsoleWindowClass", True),
            (44, "other", "ConsoleWindowClass", True),
        ],
    )
    win32process = _FakeWin32Process(owner_pid=999, pid_by_hwnd={33: 404, 44: 999})
    monkeypatch.setattr("tests.integration.windows_console_harness.time.sleep", lambda _: None)

    hwnd = _wait_for_console_window(
        process_pid=101,
        title="owned-title",
        win32gui=win32gui,
        win32process=win32process,
        timeout_seconds=0.01,
        debug_log=[],
    )

    assert hwnd == 33


def test_wait_for_console_window_allows_unique_pid_match_when_title_not_set(
    monkeypatch: pytest.MonkeyPatch,
):
    """Discovery should bind a unique console pid even before the title update is visible."""
    win32gui = _FakeWin32Gui(
        foreground_hwnd=0,
        rect=(0, 0, 0, 0),
        title="unused",
        windows=[
            (55, "Windows PowerShell", "ConsoleWindowClass", True),
            (66, "other", "ConsoleWindowClass", True),
        ],
    )
    win32process = _FakeWin32Process(owner_pid=999, pid_by_hwnd={55: 101, 66: 999})
    monkeypatch.setattr("tests.integration.windows_console_harness.time.sleep", lambda _: None)

    hwnd = _wait_for_console_window(
        process_pid=101,
        title="owned-title",
        win32gui=win32gui,
        win32process=win32process,
        timeout_seconds=0.01,
        debug_log=[],
    )

    assert hwnd == 55


def test_wait_for_console_window_includes_observed_candidates_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
):
    """Timeout errors should surface the last observed relevant windows for debugging."""
    win32gui = _FakeWin32Gui(
        foreground_hwnd=0,
        rect=(0, 0, 0, 0),
        title="unused",
        windows=[
            (77, "Windows PowerShell", "ConsoleWindowClass", True),
            (88, "not-it", "OtherClass", True),
        ],
    )
    win32process = _FakeWin32Process(owner_pid=999, pid_by_hwnd={77: 404, 88: 505})
    monkeypatch.setattr("tests.integration.windows_console_harness.time.sleep", lambda _: None)

    with pytest.raises(IsolationError, match="Observed: .*ConsoleWindowClass.*Windows PowerShell"):
        _wait_for_console_window(
            process_pid=101,
            title="owned-title",
            win32gui=win32gui,
            win32process=win32process,
            timeout_seconds=0.01,
            debug_log=[],
        )
