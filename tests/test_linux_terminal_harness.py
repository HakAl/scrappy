"""Tests for Linux X11 real-terminal harness helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.linux_terminal_harness import (
    LinuxHarnessError,
    LinuxTerminalHarness,
    _LinuxWindowGeometry,
    _find_free_display_number,
    _parse_xdotool_shell_geometry,
)


def test_parse_xdotool_shell_geometry_reads_required_fields():
    """The Linux harness should parse xdotool shell geometry output into typed fields."""
    geometry = _parse_xdotool_shell_geometry(
        "WINDOW=73400325\nX=12\nY=34\nWIDTH=800\nHEIGHT=600\nSCREEN=0\n"
    )

    assert geometry == _LinuxWindowGeometry(
        window_id=73400325,
        x=12,
        y=34,
        width=800,
        height=600,
    )


def test_parse_xdotool_shell_geometry_rejects_missing_fields():
    """Missing geometry fields should fail fast with a clear error."""
    with pytest.raises(LinuxHarnessError, match="Missing geometry fields"):
        _parse_xdotool_shell_geometry("WINDOW=1\nX=2\nY=3\nWIDTH=4\n")


def test_find_free_display_number_skips_existing_socket_and_lock(tmp_path: Path):
    """Display selection should skip numbers already claimed by sockets or lock files."""
    display_dir = tmp_path / ".X11-unix"
    lock_dir = tmp_path / "locks"
    display_dir.mkdir(parents=True, exist_ok=True)
    lock_dir.mkdir(parents=True, exist_ok=True)
    (display_dir / "X90").write_text("", encoding="utf-8")
    (lock_dir / ".X91-lock").write_text("", encoding="utf-8")

    display_number = _find_free_display_number(
        display_dir=display_dir,
        lock_dir=lock_dir,
        candidates=range(90, 94),
    )

    assert display_number == 92


def test_relative_point_uses_linux_window_geometry():
    """Relative coordinates should scale against the xterm window geometry."""
    harness = LinuxTerminalHarness()
    geometry = _LinuxWindowGeometry(window_id=1, x=10, y=20, width=1000, height=500)

    assert harness._relative_point(geometry, (0.25, 0.50)) == (250, 250)
