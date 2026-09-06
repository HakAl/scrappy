"""Headless real-terminal harness for app-level TUI behavior, driven via tmux.

Scope (deliberately narrow -- see .docs/plans/tui-interaction-redesign.md):
tmux gives a real PTY with real VT emulation, so this harness reproduces
APP-LEVEL terminal behavior that headless Textual Pilot cannot -- real input
decoding (keys + SGR mouse), the app's own selection/scroll, and mouse-reporting
state -- with no GUI and no operator.

It does NOT and CANNOT verify native terminal selection or the macOS Cmd+C
gesture: once mouse reporting is off those are terminal-emulator GUI behaviors
that never arrive as tmux SGR events and that capture-pane cannot observe. Native
select + Cmd+C stays with the GUI drivers behind RealTerminalHarnessProtocol
(macos_terminal_harness, etc.). This harness is intentionally separate from that
protocol rather than a second implementation of it.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from tests.containment.env import forward_env

REPO_ROOT = Path(__file__).resolve().parents[2]


def tmux_available() -> bool:
    """Return whether a tmux binary is on PATH."""
    return shutil.which("tmux") is not None


class TmuxTerminal:
    """Drive the scrappy TUI in a detached tmux pane and observe it."""

    def __init__(
        self,
        session: str = "scrappy_tui_test",
        width: int = 90,
        height: int = 24,
        repo_root: Path = REPO_ROOT,
        python: str | None = None,
    ) -> None:
        self.session = session
        self.width = width
        self.height = height
        self.repo_root = repo_root
        self.python = python or sys.executable

    def _tmux(self, *args: str) -> str:
        return subprocess.run(
            ["tmux", *args], capture_output=True, text=True
        ).stdout

    def start(self) -> None:
        """Launch scrappy in mock-LLM mode in a fresh detached tmux session."""
        self._tmux("kill-session", "-t", self.session)
        self._tmux(
            "new-session", "-d", "-s", self.session,
            "-x", str(self.width), "-y", str(self.height),
        )
        # The tmux pane inherits the tmux SERVER's environment, NOT the pytest process
        # (plan S-5), so the containment set is prefixed onto the launch string here.
        # tmux has no caller env mapping today, so there is nothing to guard yet (3c).
        containment_prefix = " ".join(
            f"{key}={shlex.quote(value)}" for key, value in forward_env(os.environ).items()
        )
        launch = (
            f"cd {self.repo_root} && {containment_prefix} SCRAPPY_MOCK_LLM=1 "
            f"{self.python} -m scrappy.cli.commands"
        )
        self._tmux("send-keys", "-t", self.session, "-l", launch)
        self._tmux("send-keys", "-t", self.session, "Enter")

    def wait_for(self, needle: str, timeout: float = 20.0) -> bool:
        """Poll the pane until needle appears or the timeout elapses."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if needle in self.capture():
                return True
            time.sleep(0.3)
        return False

    def send_text(self, text: str) -> None:
        """Type literal text into the pane."""
        self._tmux("send-keys", "-t", self.session, "-l", text)

    def send_keys(self, *keys: str) -> None:
        """Send named tmux keys (e.g. 'Enter', 'C-c')."""
        self._tmux("send-keys", "-t", self.session, *keys)

    def send_raw(self, *hex_bytes: str) -> None:
        """Send raw input bytes (hex pairs), e.g. an escape sequence."""
        self._tmux("send-keys", "-t", self.session, "-H", *hex_bytes)

    def _seq(self, text: str) -> list[str]:
        return [f"{b:02x}" for b in text.encode()]

    def key_seq(self, sequence: str, n: int = 1, pause: float = 0.15) -> None:
        """Send a terminal escape sequence n times (decoded by the app)."""
        for _ in range(n):
            self.send_raw(*self._seq(sequence))
            time.sleep(pause)

    def _mouse(self, button: int, col: int, row: int, press: bool = True) -> None:
        self.key_seq(f"\x1b[<{button};{col};{row}{'M' if press else 'm'}", pause=0.1)

    def mouse_drag(self, col1: int, row1: int, col2: int, row2: int) -> None:
        """Left-button drag from (col1,row1) to (col2,row2), 1-based cells."""
        self._mouse(0, col1, row1, press=True)
        self._mouse(32, col2, row2, press=True)
        self._mouse(0, col2, row2, press=False)

    def mouse_reporting_enabled(self) -> bool:
        """Return whether tmux sees the pane as requesting mouse reporting."""
        flags = self._tmux(
            "display-message",
            "-p",
            "-t",
            self.session,
            "#{mouse_any_flag} #{mouse_sgr_flag} #{mouse_all_flag} #{mouse_button_flag}",
        ).split()
        return any(flag == "1" for flag in flags)

    def capture(self) -> str:
        """Capture the pane as plain text (the 'screenshot')."""
        return self._tmux("capture-pane", "-t", self.session, "-p")

    def capture_styled(self) -> str:
        """Capture the pane including SGR styling escape sequences."""
        return self._tmux("capture-pane", "-t", self.session, "-e", "-p")

    def clear_clipboard(self) -> None:
        """Clear the macOS pasteboard."""
        subprocess.run(["pbcopy"], input="", text=True)

    def clipboard(self) -> str:
        """Read the macOS pasteboard."""
        return subprocess.run(["pbpaste"], capture_output=True, text=True).stdout

    def kill(self) -> None:
        """Tear down the tmux session."""
        self._tmux("kill-session", "-t", self.session)
