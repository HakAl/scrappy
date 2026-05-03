"""Shared scenario runner for isolated real-terminal clipboard tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

import pytest

from .real_terminal_harness import (
    HelpSelectionScenario,
    RealTerminalHarnessProtocol,
    RealTerminalSessionSpec,
)


REAL_TERMINAL_ENV = "SCRAPPY_RUN_REAL_TERMINAL_SELECTION"


def require_real_terminal_opt_in() -> None:
    """Skip unless the operator explicitly enables the live terminal scenario."""
    if os.getenv(REAL_TERMINAL_ENV) != "1":
        pytest.skip(
            f"Set {REAL_TERMINAL_ENV}=1 to run the real-terminal selection scenario"
        )


def run_command(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and surface stdout/stderr on failure."""
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def create_fixture_repo(tmp_path: Path) -> Path:
    """Create a disposable git repository for the shared scenario."""
    if shutil.which("git") is None:
        pytest.skip("git is unavailable")

    repo_dir = tmp_path / "fixture-repo"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("# Clipboard Spike Fixture\n", encoding="utf-8")
    run_command(["git", "init"], cwd=repo_dir)
    return repo_dir


def create_isolated_venv(tmp_path: Path, repo_root: Path) -> Path:
    """Install scrappy into a disposable venv without fetching dependencies."""
    venv_dir = tmp_path / "venv"
    run_command([sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)])

    if sys.platform == "win32":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"
    if not venv_python.exists():
        raise RuntimeError(f"Expected venv interpreter at {venv_python}")

    run_command([str(venv_python), "-m", "pip", "install", "--no-deps", "-e", str(repo_root)])
    return venv_python


def workspace_artifact_path(prefix: str, suffix: str) -> Path:
    """Create a workspace-local artifact path for a real-terminal session."""
    artifact_dir = Path(__file__).resolve().parents[2] / ".tmp_terminal_spike_logs"
    artifact_dir.mkdir(exist_ok=True)
    return artifact_dir / f"{prefix}-{uuid.uuid4()}{suffix}"


def build_session_spec(
    *,
    tmp_path: Path,
    repo_root: Path,
    title_prefix: str = "scrappy-selection-spike",
    env: dict[str, str] | None = None,
) -> RealTerminalSessionSpec:
    """Create the shared session bundle for a platform-specific harness."""
    fixture_repo = create_fixture_repo(tmp_path)
    venv_python = create_isolated_venv(tmp_path, repo_root)
    return RealTerminalSessionSpec(
        title=f"{title_prefix}-{uuid.uuid4()}",
        fixture_repo=fixture_repo,
        venv_python=venv_python,
        debug_log_path=workspace_artifact_path(title_prefix, ".jsonl"),
        ready_file=workspace_artifact_path(title_prefix, ".ready"),
        env={"SCRAPPY_MOCK_LLM": "1", **(env or {})},
    )


def execute_help_selection_clipboard_scenario(
    *,
    harness: RealTerminalHarnessProtocol,
    session: RealTerminalSessionSpec,
    scenario: HelpSelectionScenario | None = None,
) -> None:
    """Run the shared /help selection-and-copy scenario against a platform harness."""
    scenario = scenario or HelpSelectionScenario()

    harness.launch(session)
    harness.append_debug_event("scenario_started", harness=harness.name, title=session.title)

    try:
        harness.clear_clipboard()
        harness.append_debug_event("clipboard_cleared")

        harness.wait_until_ready(scenario.startup_timeout_seconds)
        harness.append_debug_event("ready_observed", ready_file=str(session.ready_file))

        click_point = harness.focus_input(scenario.input_focus_point)
        harness.append_debug_event("input_focused", coords=click_point)
        harness.wait_for_render(scenario.post_focus_wait_seconds)

        idle_baseline = count_jsonl_events(session.debug_log_path, "command_idle")
        harness.submit_command(scenario.command)
        harness.append_debug_event("command_submitted", command=scenario.command)
        if not poll_for_new_jsonl_event(
            log_path=session.debug_log_path,
            event_name="command_idle",
            baseline_count=idle_baseline,
            timeout_seconds=scenario.command_idle_timeout_seconds,
        ):
            harness.append_debug_event("command_idle_timeout_fallback")
            harness.wait_for_render(scenario.post_command_wait_seconds)
        else:
            harness.append_debug_event("command_idle_observed")

        harness.clear_clipboard()
        harness.append_debug_event("clipboard_cleared_before_drag")
        drag_start, drag_end = harness.drag_select(scenario.selection_region)
        harness.append_debug_event("drag_completed", start=drag_start, end=drag_end)
        harness.wait_for_render(scenario.post_drag_wait_seconds)

        auto_copy_value = harness.read_clipboard()
        harness.append_debug_event("clipboard_after_drag", value=auto_copy_value)
        if auto_copy_value:
            pytest.skip("Clipboard changed immediately after drag; terminal is auto-copying selection")

        harness.copy_selection()
        harness.append_debug_event("copy_shortcut_sent", shortcut="primary")
        clipboard_text = _poll_clipboard_contains(
            harness=harness,
            expected_substrings=scenario.expected_substrings,
            timeout=scenario.clipboard_timeout_seconds,
        )
        harness.append_debug_event("clipboard_after_primary_copy", value=clipboard_text)

        if not any(substring in clipboard_text for substring in scenario.expected_substrings):
            harness.clear_clipboard()
            harness.append_debug_event("clipboard_cleared_before_fallback_copy")
            harness.copy_selection_fallback()
            harness.append_debug_event("copy_shortcut_sent", shortcut="fallback")
            clipboard_text = _poll_clipboard_contains(
                harness=harness,
                expected_substrings=scenario.expected_substrings,
                timeout=scenario.clipboard_timeout_seconds,
            )
            harness.append_debug_event("clipboard_after_fallback_copy", value=clipboard_text)

        assert any(
            substring in clipboard_text for substring in scenario.expected_substrings
        ), "Real-terminal selection/copy did not put expected /help output on the clipboard\n" + "\n".join(
            harness.debug_log
        )
    finally:
        harness.close()


def _poll_clipboard_contains(
    *,
    harness: RealTerminalHarnessProtocol,
    expected_substrings: tuple[str, ...],
    timeout: float,
) -> str:
    """Poll clipboard until one of the expected substrings appears."""
    import time

    deadline = time.time() + timeout
    last_value = ""
    while time.time() < deadline:
        last_value = harness.read_clipboard()
        if any(substring in last_value for substring in expected_substrings):
            return last_value
        time.sleep(0.1)
    return last_value


def count_jsonl_events(log_path: Path, event_name: str) -> int:
    """Count occurrences of a named event in a JSONL integration log."""
    if not log_path.exists():
        return 0
    count = 0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("event") == event_name:
            count += 1
    return count


def poll_for_new_jsonl_event(
    *,
    log_path: Path,
    event_name: str,
    baseline_count: int,
    timeout_seconds: float,
) -> bool:
    """Poll a JSONL log until a new occurrence of the named event appears."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if count_jsonl_events(log_path, event_name) > baseline_count:
            return True
        time.sleep(0.1)
    return False
