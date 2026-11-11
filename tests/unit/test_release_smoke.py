"""Offline composer protocol and PTY handshake behavior."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "release_smoke", Path(__file__).resolve().parents[2] / "scripts/release_smoke.py",
)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)

PLACEHOLDER_FULL_ROW = bytes.fromhex('1b5b33393b31481b5b34383b353b3233326d201b5b306d1b5b33383b353b35313b34383b353b3233326d3e1b5b306d1b5b33383b353b35313b34383b353b3233326d201b5b306d1b5b34383b353b3233326d201b5b306d1b5b33383b353b3233343b34383b353b3233316d541b5b306d1b5b33383b353b3234363b34383b353b3233326d79706520276f6b2720746f20636f6e74696e75652c206f722027712720746f20717569741b5b306d')
PLACEHOLDER_CELL = bytes.fromhex('1b5b33393b34481b5b34383b353b3233326d201b5b306d1b5b33383b353b3233343b34383b353b3233316d541b5b306d1b5b33383b353b3234363b34383b353b3233326d79706520276f6b2720746f20636f6e74696e75652c206f722027712720746f20717569741b5b306d')
ACCEPTED_Q_FULL_ROW = bytes.fromhex('1b5b33393b31481b5b34383b353b3233326d201b5b306d1b5b33383b353b35313b34383b353b3233326d3e1b5b306d1b5b33383b353b35313b34383b353b3233326d201b5b306d1b5b34383b353b3233326d201b5b306d1b5b33383b353b3233313b34383b353b3233326d711b5b306d1b5b33383b353b3233343b34383b353b3233316d201b5b306d')
ACCEPTED_Q_INCREMENTAL_CELL = bytes.fromhex('1b5b33393b34481b5b34383b353b3233326d201b5b306d1b5b33383b353b3233313b34383b353b3233326d711b5b306d1b5b33383b353b3233343b34383b353b3233316d201b5b306d')
WARNING_ROW = bytes.fromhex('1b5b31303b31481b5b34383b353b3233326d201b5b306d1b5b33383b353b3232363b34383b353b3233326d506c65617365207479706520276f6b2720746f20636f6e74696e7565206f722027712720746f20717569742e1b5b306d')


def placeholder_screen():
    screen = smoke.VirtualScreen()
    screen.feed(PLACEHOLDER_FULL_ROW)
    return screen


def test_placeholder():
    screen = placeholder_screen()
    assert screen.prompt_position() == (39, 5)
    assert screen.cell((39, 5)) == "T"


def test_full_row_ack():
    screen = placeholder_screen()
    screen.feed(ACCEPTED_Q_FULL_ROW)
    assert screen.cell((39, 5)) == "q"


def test_incremental_ack():
    screen = placeholder_screen()
    screen.feed(ACCEPTED_Q_INCREMENTAL_CELL)
    assert screen.cell((39, 5)) == "q"


def test_incidental_q_is_not_ack():
    screen = placeholder_screen()
    screen.feed(WARNING_ROW + b"\x1b[2;1HTerms of Use 'q'" + PLACEHOLDER_CELL)
    assert screen.cell((39, 5)) == "T"


def test_every_byte_split():
    for paint, expected in ((ACCEPTED_Q_FULL_ROW, "q"),
                            (ACCEPTED_Q_INCREMENTAL_CELL, "q"),
                            (PLACEHOLDER_FULL_ROW, "T")):
        for split in range(len(paint) + 1):
            screen = placeholder_screen()
            screen.feed(paint[:split])
            screen.feed(paint[split:])
            assert screen.cell((39, 5)) == expected, split
    screen = placeholder_screen()
    screen.feed(b"\x1b[1;1H\xc3")
    screen.feed(b"\xa9")
    assert screen.cell((1, 1)) == "\u00e9"


def test_unknown_and_destructive_sequences():
    screen = placeholder_screen()
    screen.feed(b"\x1b[39;5H\x1b[2Cq")
    assert screen.cell((39, 5)) == "T"
    for command in (b"J", b"K", b"X", b"L", b"M", b"P", b"@", b"S", b"T", b"r",
                    b"?1049h", b"?1049l"):
        screen.feed(ACCEPTED_Q_FULL_ROW)
        screen.feed(b"\x1b[2" + command if not command.startswith(b"?") else b"\x1b[" + command)
        assert screen.cell((39, 5)) == ""
        screen.feed(b"q")
        assert screen.cell((39, 5)) == ""
    screen.feed(ACCEPTED_Q_INCREMENTAL_CELL)
    assert screen.cell((39, 5)) == "q"


def child_script(tmp_path, mode):
    child = tmp_path / "child"
    received = tmp_path / "received"
    child.write_text(f"#!{sys.executable}\n" + r"""
import os
import select
import sys
import tty
from pathlib import Path

tty.setraw(0)
mode = MODE
received = Path(RECEIVED)
received.write_bytes(b"")
def record(data):
    with received.open("ab") as stream:
        stream.write(data)
def emit(data):
    os.write(1, data)
def read(timeout=0.3):
    if select.select([0], [], [], timeout)[0]:
        data = os.read(0, 1024)
        record(data)
        return data
    return b""
emit(b"Terms of Use")
if mode == "no_prompt":
    while True:
        read()
if mode == "title_before_prompt":
    early = read(0.15)
    Path(EARLY).write_bytes(early)
emit(PLACEHOLDER)
first = read(5)
if mode == "post_write_redraw_no_accept":
    emit(WARNING + b"\x1b[2;1HTerms of Use 'q'" + PLACEHOLDER)
    while True:
        read()
if b"q" in first and b"\r" in first:
    emit(WARNING + ACCEPTED)
    while True:
        read()
if first != b"q":
    sys.exit(5)
emit(ACCEPTED)
second = read(5)
if second != b"\r":
    sys.exit(6)
if mode == "echo_no_exit":
    while True:
        read()
sys.exit(3 if mode == "nonzero_exit" else 0)
""".replace("MODE", repr(mode)).replace("RECEIVED", repr(str(received))))
    text = child.read_text()
    text = text.replace("EARLY", repr(str(tmp_path / "early")))
    text = text.replace("PLACEHOLDER", repr(PLACEHOLDER_FULL_ROW))
    text = text.replace("WARNING", repr(WARNING_ROW))
    text = text.replace("ACCEPTED", repr(ACCEPTED_Q_INCREMENTAL_CELL))
    child.write_text(text)
    child.chmod(0o755)
    return child, received


def run_child(tmp_path, mode, *, ready_timeout=10, quit_timeout=10):
    child, received = child_script(tmp_path, mode)
    result = smoke.terms_smoke(child, tmp_path, dict(os.environ),
                               ready_timeout=ready_timeout, quit_timeout=quit_timeout)
    return result, received


@pytest.mark.skipif(sys.platform == "win32", reason="pty")
def test_title_before_prompt(tmp_path):
    result, received = run_child(tmp_path, "title_before_prompt")
    assert (tmp_path / "early").read_bytes() == b""
    assert received.read_bytes() == b"q\r"
    assert result["quit_exit"] == 0
    assert [p["name"] for p in result["phases"]] == ["READY", "TYPE", "ACK", "SUBMIT", "EXIT"]
    assert [p["bytes_written"] for p in result["phases"]] == [0, 0, 1, 1, 2]
    assert [p["seconds"] for p in result["phases"]] == sorted(p["seconds"] for p in result["phases"])


@pytest.mark.skipif(sys.platform == "win32", reason="pty")
def test_priority_enter_race(tmp_path):
    result, received = run_child(tmp_path, "reorder_child")
    assert result["quit_exit"] == 0
    assert received.read_bytes() == b"q\r"


@pytest.mark.skipif(sys.platform == "win32", reason="pty")
def test_post_write_redraw_no_accept(tmp_path):
    with pytest.raises(RuntimeError, match="q not echoed"):
        run_child(tmp_path, "post_write_redraw_no_accept", quit_timeout=2)
    assert (tmp_path / "received").read_bytes() == b"q"


@pytest.mark.skipif(sys.platform == "win32", reason="pty")
def test_echo_no_exit(tmp_path):
    with pytest.raises(RuntimeError, match="Terms quit timed out"):
        run_child(tmp_path, "echo_no_exit", quit_timeout=2)
    assert (tmp_path / "received").read_bytes() == b"q\r"


@pytest.mark.skipif(sys.platform == "win32", reason="pty")
def test_nonzero_exit(tmp_path):
    with pytest.raises(RuntimeError, match="exit=3"):
        run_child(tmp_path, "nonzero_exit")


@pytest.mark.skipif(sys.platform == "win32", reason="pty")
def test_no_prompt(tmp_path):
    with pytest.raises(RuntimeError, match="Terms prompt not ready"):
        run_child(tmp_path, "no_prompt", ready_timeout=2)
    assert (tmp_path / "received").read_bytes() == b""


@pytest.mark.skipif(sys.platform == "win32", reason="pty")
def test_exec_failure(tmp_path):
    binary = tmp_path / "bad-binary"
    binary.write_bytes(b"not executable")
    with pytest.raises(RuntimeError, match="Terms prompt not ready"):
        smoke.terms_smoke(binary, tmp_path, dict(os.environ),
                          ready_timeout=10, quit_timeout=10)
