"""Platform-neutral contract for isolated real-terminal selection tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol, runtime_checkable


@dataclass(frozen=True)
class RelativeSelection:
    """A drag-selection region expressed in window-relative coordinates."""

    start: tuple[float, float]
    end: tuple[float, float]


@dataclass(frozen=True)
class RealTerminalSessionSpec:
    """Launch settings and workspace artifact paths for a real-terminal run."""

    title: str
    fixture_repo: Path
    venv_python: Path
    debug_log_path: Path
    ready_file: Path
    env: Mapping[str, str] = field(default_factory=dict)
    entry_module: str = "scrappy.cli.commands"


@dataclass(frozen=True)
class HelpSelectionScenario:
    """Shared scenario parameters for help-selection clipboard verification."""

    command: str = "/help"
    expected_substrings: tuple[str, ...] = ("/quit, /exit", "/model [mode]", "/agent <task>")
    input_focus_point: tuple[float, float] = (0.50, 0.88)
    selection_region: RelativeSelection = field(
        default_factory=lambda: RelativeSelection(start=(0.08, 0.20), end=(0.88, 0.78))
    )
    startup_timeout_seconds: float = 20.0
    post_focus_wait_seconds: float = 0.2
    post_command_wait_seconds: float = 1.5
    command_idle_timeout_seconds: float = 10.0
    post_drag_wait_seconds: float = 0.4
    clipboard_timeout_seconds: float = 3.0


@runtime_checkable
class RealTerminalHarnessProtocol(Protocol):
    """A platform-specific driver for real-terminal selection and clipboard tests."""

    name: str
    debug_log: list[str]

    def launch(self, session: RealTerminalSessionSpec) -> None:
        """Launch scrappy in an isolated real terminal for this platform."""

    def wait_until_ready(self, timeout_seconds: float) -> None:
        """Block until the launched app emits a readiness signal."""

    def clear_clipboard(self) -> None:
        """Clear the active clipboard for this harness session."""

    def read_clipboard(self) -> str:
        """Read the current clipboard contents."""

    def focus_input(self, point: tuple[float, float]) -> tuple[int, int]:
        """Focus the terminal input area and return the absolute click point."""

    def submit_command(self, command: str) -> None:
        """Submit a command to the running terminal app."""

    def wait_for_render(self, seconds: float) -> None:
        """Wait for terminal rendering when no stronger readiness hook exists."""

    def drag_select(self, region: RelativeSelection) -> tuple[tuple[int, int], tuple[int, int]]:
        """Perform a selection gesture over the output area."""

    def copy_selection(self) -> None:
        """Invoke the platform's primary copy shortcut."""

    def copy_selection_fallback(self) -> None:
        """Invoke an alternate copy shortcut when the primary one yields nothing."""

    def append_debug_event(self, stage: str, **fields: object) -> None:
        """Persist a structured debug event for post-run inspection."""

    def close(self) -> None:
        """Tear down session-owned terminal resources and restore transient state when applicable."""
