"""Tests for the platform-neutral real-terminal scenario runner."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import sys
import uuid

from tests.integration.real_terminal_harness import (
    HelpSelectionScenario,
    RealTerminalSessionSpec,
    RelativeSelection,
)
from tests.integration import real_terminal_scenario
from tests.integration.real_terminal_scenario import (
    count_jsonl_events,
    create_isolated_venv,
    execute_help_selection_clipboard_scenario,
    poll_for_new_jsonl_event,
)


class _FakeHarness:
    name = "fake-terminal"

    def __init__(self) -> None:
        self.debug_log: list[str] = []
        self.operations: list[str] = []
        self.clipboard_value = ""
        self.closed = False

    def launch(self, session: RealTerminalSessionSpec) -> None:
        self.operations.append("launch")

    def wait_until_ready(self, timeout_seconds: float) -> None:
        self.operations.append(f"wait_until_ready:{timeout_seconds}")

    def clear_clipboard(self) -> None:
        self.operations.append("clear_clipboard")
        self.clipboard_value = ""

    def read_clipboard(self) -> str:
        self.operations.append("read_clipboard")
        return self.clipboard_value

    def focus_input(self, point: tuple[float, float]) -> tuple[int, int]:
        self.operations.append(f"focus_input:{point}")
        return (111, 222)

    def submit_command(self, command: str) -> None:
        self.operations.append(f"submit_command:{command}")

    def wait_for_render(self, seconds: float) -> None:
        self.operations.append(f"wait_for_render:{seconds}")

    def drag_select(self, region: RelativeSelection) -> tuple[tuple[int, int], tuple[int, int]]:
        self.operations.append(f"drag_select:{region.start}->{region.end}")
        return ((10, 20), (30, 40))

    def copy_selection(self) -> None:
        self.operations.append("copy_selection")

    def copy_selection_fallback(self) -> None:
        self.operations.append("copy_selection_fallback")
        self.clipboard_value = "/quit, /exit"

    def capture_screen_artifact(self, label: str) -> Path | None:
        self.operations.append(f"capture_screen_artifact:{label}")
        return None

    def append_debug_event(self, stage: str, **fields: object) -> None:
        self.operations.append(f"append_debug_event:{stage}")
        self.debug_log.append(f"{stage}: {fields}")

    def close(self) -> None:
        self.operations.append("close")
        self.closed = True


def test_shared_scenario_uses_fallback_copy_and_closes_harness():
    """The platform-neutral scenario should handle empty primary copy and still close the harness."""
    harness = _FakeHarness()
    session = RealTerminalSessionSpec(
        title="fake-title",
        fixture_repo=Path("fixture"),
        venv_python=Path("python"),
        debug_log_path=Path("log.jsonl"),
        ready_file=Path("ready.signal"),
    )
    scenario = HelpSelectionScenario(
        expected_substrings=("/quit, /exit",),
        post_focus_wait_seconds=0.0,
        post_command_wait_seconds=0.0,
        command_idle_timeout_seconds=0.01,
        post_drag_wait_seconds=0.0,
        clipboard_timeout_seconds=0.01,
    )

    execute_help_selection_clipboard_scenario(
        harness=harness,
        session=session,
        scenario=scenario,
    )

    assert harness.closed is True
    assert "copy_selection" in harness.operations
    assert "copy_selection_fallback" in harness.operations
    assert harness.operations[-1] == "close"


def test_create_isolated_venv_uses_platform_python_path(monkeypatch):
    """The shared venv helper should select the interpreter path for the current platform."""
    calls: list[list[str]] = []
    base_dir = Path(".tmp_test_real_terminal_scenario") / str(uuid.uuid4())
    base_dir.mkdir(parents=True, exist_ok=True)

    def fake_run_command(command: list[str], *, cwd: Path | None = None):
        calls.append(command)
        if command[:3] == [sys.executable, "-m", "venv"]:
            if sys.platform == "win32":
                expected = base_dir / "venv" / "Scripts"
                expected.mkdir(parents=True, exist_ok=True)
                (expected / "python.exe").write_text("", encoding="utf-8")
            else:
                expected = base_dir / "venv" / "bin"
                expected.mkdir(parents=True, exist_ok=True)
                (expected / "python").write_text("", encoding="utf-8")
        return None

    monkeypatch.setattr(real_terminal_scenario, "run_command", fake_run_command)

    repo_root = Path("repo")
    venv_python = create_isolated_venv(base_dir, repo_root)

    if sys.platform == "win32":
        assert venv_python == base_dir / "venv" / "Scripts" / "python.exe"
    else:
        assert venv_python == base_dir / "venv" / "bin" / "python"
    assert calls[-1][-1] == str(repo_root)


def test_scenario_runner_does_not_import_platform_drivers():
    """The shared scenario must only depend on the protocol layer, not concrete drivers."""
    source = Path("tests/integration/real_terminal_scenario.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    platform_drivers = {
        "tests.integration.windows_console_harness",
        "tests.integration.macos_terminal_harness",
        "tests.integration.linux_terminal_harness",
        ".windows_console_harness",
        ".macos_terminal_harness",
        ".linux_terminal_harness",
    }

    violations = imported_modules & platform_drivers
    assert not violations, f"Scenario runner imports platform drivers directly: {sorted(violations)}"


def test_count_jsonl_events_counts_named_events(tmp_path: Path):
    """The JSONL counter should count only events matching the given name."""
    log = tmp_path / "events.jsonl"
    log.write_text(
        json.dumps({"event": "command_idle", "rendered": True}) + "\n"
        + json.dumps({"event": "cli_ready", "ready": True}) + "\n"
        + json.dumps({"event": "command_idle", "rendered": True}) + "\n",
        encoding="utf-8",
    )

    assert count_jsonl_events(log, "command_idle") == 2
    assert count_jsonl_events(log, "cli_ready") == 1
    assert count_jsonl_events(log, "nonexistent") == 0


def test_count_jsonl_events_returns_zero_for_missing_file(tmp_path: Path):
    """The JSONL counter should return 0 when the log file does not exist."""
    assert count_jsonl_events(tmp_path / "missing.jsonl", "command_idle") == 0


def test_poll_for_new_jsonl_event_finds_new_event(tmp_path: Path):
    """The JSONL poller should detect a new event written after the baseline."""
    log = tmp_path / "events.jsonl"
    log.write_text(
        json.dumps({"event": "command_idle", "rendered": True}) + "\n",
        encoding="utf-8",
    )
    baseline = count_jsonl_events(log, "command_idle")

    # Simulate the app writing a new event
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "command_idle", "rendered": True}) + "\n")

    assert poll_for_new_jsonl_event(
        log_path=log,
        event_name="command_idle",
        baseline_count=baseline,
        timeout_seconds=1.0,
    )


def test_poll_for_new_jsonl_event_times_out_when_no_new_event(tmp_path: Path):
    """The JSONL poller should return False when no new event appears before timeout."""
    log = tmp_path / "events.jsonl"
    log.write_text(
        json.dumps({"event": "command_idle", "rendered": True}) + "\n",
        encoding="utf-8",
    )
    baseline = count_jsonl_events(log, "command_idle")

    assert not poll_for_new_jsonl_event(
        log_path=log,
        event_name="command_idle",
        baseline_count=baseline,
        timeout_seconds=0.01,
    )


def test_scenario_uses_jsonl_poll_when_event_is_available(tmp_path: Path):
    """The scenario should observe command_idle from the JSONL log instead of sleeping."""
    log_path = tmp_path / "events.jsonl"

    class _JsonlAwareHarness(_FakeHarness):
        def submit_command(self, command: str) -> None:
            super().submit_command(command)
            # Simulate the app writing command_idle after processing
            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"event": "command_idle", "rendered": True}) + "\n")

    harness = _JsonlAwareHarness()
    session = RealTerminalSessionSpec(
        title="fake-title",
        fixture_repo=Path("fixture"),
        venv_python=Path("python"),
        debug_log_path=log_path,
        ready_file=Path("ready.signal"),
    )
    scenario = HelpSelectionScenario(
        expected_substrings=("/quit, /exit",),
        post_focus_wait_seconds=0.0,
        post_command_wait_seconds=0.0,
        command_idle_timeout_seconds=1.0,
        post_drag_wait_seconds=0.0,
        clipboard_timeout_seconds=0.01,
    )

    execute_help_selection_clipboard_scenario(
        harness=harness,
        session=session,
        scenario=scenario,
    )

    assert "append_debug_event:command_idle_observed" in harness.operations
    assert "append_debug_event:command_idle_timeout_fallback" not in harness.operations
