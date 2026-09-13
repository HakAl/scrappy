"""Tests for the macOS real-terminal harness helpers."""

from __future__ import annotations

from pathlib import Path
import shlex

import pytest

from tests.containment.env import ContainmentConflictError
from tests.integration.macos_terminal_harness import (
    MacOSHarnessError,
    MacOSTerminalHarness,
    _build_shell_command,
    _escape_applescript_string,
    _parse_launch_identity,
)
from tests.integration.real_terminal_harness import RealTerminalSessionSpec


def _session_with_env(env):
    return RealTerminalSessionSpec(
        title="title",
        fixture_repo=Path("/fixture/repo"),
        venv_python=Path("/venv/bin/python"),
        debug_log_path=Path("/logs/log.jsonl"),
        ready_file=Path("/logs/ready.signal"),
        env=env,
        entry_module="scrappy.cli.commands",
    )


def test_build_shell_command_rejects_a_containment_key_in_session_env():
    """CONFLICT RULE (plan 3c): a containment key via session.env is a hard error."""
    with pytest.raises(ContainmentConflictError, match="CLI_CONFIG_PATH"):
        _build_shell_command(_session_with_env({"CLI_CONFIG_PATH": "/outside/cfg.json"}))


def test_build_shell_command_forwards_the_containment_set(monkeypatch):
    """The containment set from the environment is exported explicitly for the
    independently-based iTerm2 child (plan S-5)."""
    monkeypatch.setenv("HOME", "/contained/home")
    monkeypatch.setenv("TMPDIR", "/contained/scratch/os")
    monkeypatch.setenv("CLI_CONFIG_PATH", "/contained/home/absent.json")
    command = _build_shell_command(_session_with_env({"SCRAPPY_MOCK_LLM": "1"}))
    assert "export HOME=/contained/home" in command
    assert "export TMPDIR=/contained/scratch/os" in command
    assert "export CLI_CONFIG_PATH=/contained/home/absent.json" in command


def test_escape_applescript_string_escapes_quotes_and_backslashes():
    """AppleScript string escaping should preserve backslashes and quotes."""
    escaped = _escape_applescript_string('say "hello" \\ goodbye')

    assert escaped == 'say \\"hello\\" \\\\ goodbye'


def test_build_shell_command_includes_repo_env_and_entrypoint():
    """The macOS launch command should export session env vars before exec."""
    session = RealTerminalSessionSpec(
        title="title",
        fixture_repo=Path("/tmp/repo"),
        venv_python=Path("/tmp/venv/bin/python"),
        debug_log_path=Path("/tmp/log.jsonl"),
        ready_file=Path("/tmp/ready.signal"),
        env={"SCRAPPY_MOCK_LLM": "1", "CUSTOM_FLAG": "value with spaces"},
        entry_module="scrappy.cli.commands",
    )

    command = _build_shell_command(session)

    assert f"cd {shlex.quote(str(session.fixture_repo))}" in command
    assert "export SCRAPPY_MOCK_LLM=1" in command
    assert "export CUSTOM_FLAG='value with spaces'" in command
    assert f"export SCRAPPY_INTEGRATION_LOG_PATH={shlex.quote(str(session.debug_log_path))}" in command
    assert f"export SCRAPPY_READY_FILE={shlex.quote(str(session.ready_file))}" in command
    assert f"exec {shlex.quote(str(session.venv_python))} -m scrappy.cli.commands" in command


def test_parse_launch_identity_reads_window_and_session_ids():
    """The macOS harness should parse iTerm2 launch identity output."""
    window_id, session_id = _parse_launch_identity("48151623|w0t-session-id\n")

    assert window_id == 48151623
    assert session_id == "w0t-session-id"


def test_parse_launch_identity_rejects_invalid_output():
    """Malformed launch identity output should fail fast."""
    with pytest.raises(MacOSHarnessError, match="Unexpected iTerm2 launch identity output"):
        _parse_launch_identity("missing-separator")


def test_relative_point_uses_window_geometry():
    """Relative coordinates should scale against the front window geometry."""
    harness = MacOSTerminalHarness()

    assert harness._relative_point((100, 200, 1200, 800), (0.25, 0.50)) == (400, 600)


def test_submit_command_activates_owned_window_before_typing(monkeypatch: pytest.MonkeyPatch):
    """Command submission should reacquire the owned iTerm2 window before typing."""
    harness = MacOSTerminalHarness()
    calls: list[object] = []

    def fake_activate() -> None:
        calls.append("activate")

    def fake_run_osascript(lines: list[str], *, check: bool = True) -> str:
        calls.append(tuple(lines))
        return ""

    monkeypatch.setattr(harness, "_activate_owned_window", fake_activate)
    monkeypatch.setattr(harness, "_run_osascript", fake_run_osascript)

    harness.submit_command("/help")

    assert calls[0] == "activate"
    assert calls[1] == (
        'tell application "System Events"',
        'keystroke "/help"',
        "key code 36",
        "end tell",
    )


def test_copy_selection_activates_owned_window_before_copy(monkeypatch: pytest.MonkeyPatch):
    """Copy should reacquire the owned iTerm2 window before sending Command-C."""
    harness = MacOSTerminalHarness()
    calls: list[object] = []

    def fake_activate() -> None:
        calls.append("activate")

    def fake_run_osascript(lines: list[str], *, check: bool = True) -> str:
        calls.append(tuple(lines))
        return ""

    monkeypatch.setattr(harness, "_activate_owned_window", fake_activate)
    monkeypatch.setattr(harness, "_run_osascript", fake_run_osascript)

    harness.copy_selection()

    assert calls[0] == "activate"
    assert calls[1] == (
        'tell application "System Events"',
        'keystroke "c" using {command down}',
        "end tell",
    )


def test_copy_selection_fallback_activates_owned_window_before_menu_copy(
    monkeypatch: pytest.MonkeyPatch,
):
    """Fallback copy should reacquire the owned iTerm2 window before using the Edit menu."""
    harness = MacOSTerminalHarness()
    calls: list[object] = []

    def fake_activate() -> None:
        calls.append("activate")

    def fake_run_osascript(lines: list[str], *, check: bool = True) -> str:
        calls.append((tuple(lines), check))
        return ""

    monkeypatch.setattr(harness, "_activate_owned_window", fake_activate)
    monkeypatch.setattr(harness, "_run_osascript", fake_run_osascript)

    harness.copy_selection_fallback()

    assert calls[0] == "activate"
    assert calls[1] == (
        (
            'tell application "System Events"',
            'tell process "iTerm2"',
            'click menu item "Copy" of menu "Edit" of menu bar 1',
            "end tell",
            "end tell",
        ),
        False,
    )


def test_get_owned_window_geometry_queries_owned_window_id(monkeypatch: pytest.MonkeyPatch):
    """Geometry lookup should target the harness-owned iTerm2 window id."""
    harness = MacOSTerminalHarness()
    harness._window_id = 314
    captured_lines: list[str] = []

    def fake_run_osascript(lines: list[str], *, check: bool = True) -> str:
        captured_lines.extend(lines)
        return "100,200|1200,800\n"

    monkeypatch.setattr(harness, "_run_osascript", fake_run_osascript)

    assert harness._get_owned_window_geometry() == (100, 200, 1200, 800)
    assert "if id of aWindow is 314 then" in captured_lines
