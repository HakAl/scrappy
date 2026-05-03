"""Factory for selecting the platform-specific real-terminal harness."""

from __future__ import annotations

import sys

import pytest

from .linux_terminal_harness import LinuxTerminalHarness
from .macos_terminal_harness import MacOSTerminalHarness
from .real_terminal_harness import RealTerminalHarnessProtocol
from .windows_console_harness import WindowsOwnedConsoleHarness


def create_platform_terminal_harness() -> RealTerminalHarnessProtocol:
    """Return the best available real-terminal harness for the current platform."""
    if sys.platform == "win32":
        return WindowsOwnedConsoleHarness()
    if sys.platform == "darwin":
        return MacOSTerminalHarness()
    if sys.platform.startswith("linux"):
        return LinuxTerminalHarness()
    pytest.skip(f"No real-terminal harness is registered for {sys.platform}")
