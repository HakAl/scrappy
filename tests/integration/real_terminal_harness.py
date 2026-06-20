"""Platform-neutral contract for isolated real-terminal selection tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tempfile
import time
from typing import BinaryIO, Callable, Mapping, Protocol, runtime_checkable


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


DEFAULT_READY_POLL_INTERVAL_SECONDS = 0.1
DEFAULT_DIAGNOSTICS_TAIL_CHARS = 4000


@dataclass(frozen=True)
class LaunchLiveness:
    """Snapshot of whether a launched app is still running.

    ``alive`` is True while the launched process is running. When it is False the app
    has exited; ``exit_code`` carries the platform-reported exit status when the driver
    can observe it, or None when the platform can detect death but not the numeric code
    (for example macOS, where the app runs inside an iTerm2 session rather than as a
    direct child process).
    """

    alive: bool
    exit_code: int | None = None


class ReadinessTimeout(RuntimeError):
    """Default error raised when an app never signals readiness.

    Drivers pass their own ``error_factory`` to :func:`wait_for_ready_file` so the
    platform-specific error type is preserved for existing callers; this class is only
    the fallback when no factory is supplied.
    """


@dataclass
class CapturedStream:
    """A temp file capturing a child process's stderr for later diagnostics.

    A temp file (rather than a pipe) is used deliberately: the child can write an
    unbounded amount of stderr without the parent having to drain it, so teardown can
    never deadlock on a full pipe buffer.
    """

    path: Path
    handle: BinaryIO

    @classmethod
    def create(cls, prefix: str) -> CapturedStream:
        """Open a fresh temp file ready to receive a child's stderr stream."""
        # The write handle is owned by the caller, which closes it during teardown.
        tmp = tempfile.NamedTemporaryFile(
            mode="wb", prefix=prefix, suffix=".stderr.log", delete=False
        )
        return cls(path=Path(tmp.name), handle=tmp)

    def read_tail(self, limit: int = DEFAULT_DIAGNOSTICS_TAIL_CHARS) -> str:
        """Return the last ``limit`` characters captured so far, decoded leniently."""
        try:
            self.handle.flush()
        except (OSError, ValueError):
            pass
        try:
            data = self.path.read_bytes()
        except OSError:
            return ""
        return data.decode("utf-8", errors="replace")[-limit:]

    def cleanup(self) -> None:
        """Close the write handle and remove the temp file."""
        try:
            self.handle.close()
        except (OSError, ValueError):
            pass
        try:
            self.path.unlink()
        except OSError:
            pass


def _format_not_ready(
    *,
    description: str,
    ready_file: Path,
    liveness: LaunchLiveness,
    diagnostics: str,
    waited_seconds: float,
) -> str:
    """Build a diagnostic message for a failed readiness wait."""
    if not liveness.alive:
        code = "unknown" if liveness.exit_code is None else liveness.exit_code
        headline = (
            f"Launched app exited (code {code}) before writing {description} "
            f"at {ready_file} after {waited_seconds:.1f}s"
        )
    else:
        headline = (
            f"Timed out after {waited_seconds:.1f}s waiting for {description} at {ready_file}; "
            "launched app was still alive"
        )
    tail = diagnostics.strip()
    if tail:
        return f"{headline}\ncaptured stderr tail:\n{tail}"
    return f"{headline}\ncaptured stderr tail: <none captured>"


def _safe_drain(drain_diagnostics: Callable[[], str]) -> str:
    """Drain diagnostics without letting a drain failure mask the readiness error."""
    try:
        text = drain_diagnostics()
    except Exception as exc:  # diagnostics must never hide the real readiness failure
        return f"<diagnostics drain failed: {exc!r}>"
    if not text:
        return ""
    return text[-DEFAULT_DIAGNOSTICS_TAIL_CHARS:]


def wait_for_ready_file(
    *,
    ready_file: Path,
    probe: Callable[[], LaunchLiveness],
    drain_diagnostics: Callable[[], str],
    timeout_seconds: float,
    description: str = "scrappy readiness signal",
    poll_interval_seconds: float = DEFAULT_READY_POLL_INTERVAL_SECONDS,
    error_factory: Callable[[str], Exception] = ReadinessTimeout,
) -> None:
    """Block until ``ready_file`` appears, the launched app dies, or time runs out.

    This is the single shared readiness primitive for every platform driver. Each tick
    checks the readiness marker first and then the liveness probe, so a launched app
    that crashes before writing the marker fails fast (instead of a blind timeout) and
    the raised error carries the app exit code plus a captured-stderr tail. Drivers
    supply ``probe`` and ``drain_diagnostics`` (and their own ``error_factory``); this
    primitive only composes them and never reaches into driver internals.
    """
    start = time.monotonic()
    deadline = start + timeout_seconds
    while True:
        if ready_file.exists():
            return
        liveness = probe()
        if not liveness.alive:
            # The app may have written the marker and exited within the same tick.
            if ready_file.exists():
                return
            raise error_factory(
                _format_not_ready(
                    description=description,
                    ready_file=ready_file,
                    liveness=liveness,
                    diagnostics=_safe_drain(drain_diagnostics),
                    waited_seconds=time.monotonic() - start,
                )
            )
        if time.monotonic() >= deadline:
            if ready_file.exists():
                return
            raise error_factory(
                _format_not_ready(
                    description=description,
                    ready_file=ready_file,
                    liveness=liveness,
                    diagnostics=_safe_drain(drain_diagnostics),
                    waited_seconds=time.monotonic() - start,
                )
            )
        time.sleep(poll_interval_seconds)


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

    def probe_launched_app(self) -> LaunchLiveness:
        """Report whether the launched app is still running and its exit code if known.

        Composed by :func:`wait_for_ready_file` so readiness waits fail fast when the
        app dies instead of blocking until the timeout. Returns ``alive=True`` before
        launch so the primitive treats an un-launched harness as still pending.
        """

    def drain_launch_diagnostics(self) -> str:
        """Return a captured-stderr (or equivalent) tail for readiness failure messages.

        Composed by :func:`wait_for_ready_file`. Returns an empty string when the
        platform has nothing captured rather than raising.
        """

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

    def capture_screen_artifact(self, label: str) -> Path | None:
        """Capture the current terminal window for post-run inspection, if supported."""

    def append_debug_event(self, stage: str, **fields: object) -> None:
        """Persist a structured debug event for post-run inspection."""

    def close(self) -> None:
        """Tear down session-owned terminal resources and restore transient state when applicable."""
