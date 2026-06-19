"""Headless real-terminal UX guards for the scrappy TUI (tmux-driven).

These encode the corrected failure-matrix findings as regression guards for
APP-LEVEL terminal behavior. Native selection + macOS Cmd+C are out of scope here
(see tmux_terminal_harness docstring) and stay with the GUI harnesses.

Opt in with SCRAPPY_RUN_TMUX_TUI=1; requires tmux on PATH. The clipboard guard
additionally requires macOS (pbcopy/pbpaste).
"""

from __future__ import annotations

import os
import sys
import time

import pytest

from .tmux_terminal_harness import TmuxTerminal, tmux_available

pytestmark = pytest.mark.integration

OPT_IN = "SCRAPPY_RUN_TMUX_TUI"


def _require_opt_in() -> None:
    if os.getenv(OPT_IN) != "1":
        pytest.skip(f"Set {OPT_IN}=1 to run the tmux real-terminal UX guards")
    if not tmux_available():
        pytest.skip("tmux is not available on PATH")


def _top_line(term: TmuxTerminal) -> str:
    for line in term.capture().splitlines():
        if line.strip():
            return line.strip()[:50]
    return ""


def _populate_help(term: TmuxTerminal) -> int:
    term.send_text("/help")
    time.sleep(0.4)
    term.send_keys("Enter")
    time.sleep(2.0)

    rows = term.capture().splitlines()
    target = next(
        (i for i, line in enumerate(rows, 1) if "Exit the CLI" in line or "/quit" in line),
        None,
    )
    assert target is not None, "expected a /help row to select"
    return target


# Escape sequences the app decodes (xterm)
PAGE_UP = "\x1b[5~"
CTRL_PAGE_UP = "\x1b[5;5~"
CTRL_END = "\x1b[1;5F"


def test_ctrl_pageup_scrolls_transcript_and_plain_pageup_does_not() -> None:
    """Contract: Ctrl+PageUp scrolls the transcript; plain PageUp stays in the composer.

    Regression guard against conflating the two (the composer owns plain PageUp for
    multiline navigation; transcript scroll is focus-independent on Ctrl+PageUp).
    Uses a short window so /help overflows and scrolling is observable.
    """
    _require_opt_in()
    term = TmuxTerminal(session="scrappy_tui_scroll", width=90, height=12)
    try:
        term.start()
        assert term.wait_for("Type your message", timeout=25), "app did not become ready"
        term.send_text("/help")
        time.sleep(0.4)
        term.send_keys("Enter")
        time.sleep(2.0)

        term.key_seq(CTRL_END)
        time.sleep(0.4)
        bottom = _top_line(term)
        assert bottom, "no visible content at live bottom"

        term.key_seq(PAGE_UP, n=3)
        time.sleep(0.4)
        assert _top_line(term) == bottom, "plain PageUp must not scroll the transcript"

        term.key_seq(CTRL_END)
        time.sleep(0.4)
        base = _top_line(term)
        term.key_seq(CTRL_PAGE_UP, n=3)
        time.sleep(0.4)
        assert _top_line(term) != base, "Ctrl+PageUp must scroll the transcript up"
    finally:
        term.kill()


@pytest.mark.skipif(sys.platform != "darwin", reason="clipboard guard uses macOS pbcopy/pbpaste")
def test_drag_select_then_ctrl_c_copies_app_selection() -> None:
    """App-level drag selection + Ctrl+C copies the selected text to the clipboard."""
    _require_opt_in()
    term = TmuxTerminal(session="scrappy_tui_copy", width=90, height=24)
    try:
        term.start()
        assert term.wait_for("Type your message", timeout=25), "app did not become ready"
        # /help fills the transcript with ample selectable content at any window size.
        term.send_text("/help")
        time.sleep(0.4)
        term.send_keys("Enter")
        time.sleep(2.0)

        term.clear_clipboard()
        rows = term.capture().splitlines()
        target = next(
            (i for i, line in enumerate(rows, 1) if "Exit the CLI" in line or "/quit" in line),
            None,
        )
        assert target is not None, "expected a /help row to select"
        text = rows[target - 1].strip()

        end_col = min(55, len(rows[target - 1].rstrip()))
        term.mouse_drag(col1=4, row1=target, col2=end_col, row2=target)
        time.sleep(0.6)
        term.send_keys("C-c")
        time.sleep(0.8)

        clip = term.clipboard().strip()
        assert clip, "Ctrl+C produced an empty clipboard"
        assert clip in text or text.startswith(clip[:10]), (
            f"clipboard {clip!r} is not part of the selected row {text!r}"
        )
    finally:
        term.kill()


def test_ctrl_t_toggles_terminal_mouse_reporting() -> None:
    """Ctrl+T suspends terminal mouse reporting so the terminal regains native
    drag-select + Cmd+C, and a second Ctrl+T restores it.

    Reads tmux's own pane mouse flags (the authoritative signal that the
    disable/enable escape sequences actually reached the terminal), not a styled
    capture -- the right-edge scrollbar also renders reverse-video, so a styled
    scrape cannot distinguish a drag selection from the scrollbar. Genuinely
    fail-when-broken: if the disable path is a no-op (flag flipped but no escape
    sequence emitted), reporting stays enabled after Ctrl+T and the middle
    assertion trips.
    """
    _require_opt_in()

    term = TmuxTerminal(session="scrappy_tui_mouse_toggle", width=90, height=24)
    try:
        term.start()
        assert term.wait_for("Type your message", timeout=25), "app did not become ready"
        _populate_help(term)
        assert term.mouse_reporting_enabled(), (
            "app did not request terminal mouse reporting at startup"
        )

        term.send_keys("C-t")
        time.sleep(0.8)
        assert "Selection mode" in term.capture(), "Ctrl+T did not enter selection mode"
        assert not term.mouse_reporting_enabled(), (
            "Ctrl+T selection mode did not suspend terminal mouse reporting"
        )

        term.send_keys("C-t")
        time.sleep(0.8)
        assert term.mouse_reporting_enabled(), (
            "second Ctrl+T did not restore terminal mouse reporting"
        )
    finally:
        term.kill()
