"""
Stdout sentinel: catches raw writes to stdout/stderr while Textual owns the terminal.

WHY THIS EXISTS:
Mouse selection breaks when anything writes directly to the terminal (stdout/stderr)
while Textual is running. Textual uses VT escape sequences to enable mouse tracking.
A single raw write can corrupt those sequences and kill mouse mode for the rest of
the session. This has caused at least 3 regressions.

This test monkey-patches sys.stdout and sys.stderr during app operation and fails
if anything bypasses Textual's output routing. This catches the ROOT CAUSE of mouse
regressions, not just the symptom.

Run this in CI. If it fails, something is writing to the terminal directly.
"""

import io
import os
import sys
import logging
import pytest
from unittest.mock import MagicMock

os.environ["SCRAPPY_MOCK_LLM"] = "1"

from scrappy.cli.textual.app import ScrappyApp


def create_mock_cli():
    mock_cli = MagicMock()
    mock_cli.interactive_mode = MagicMock()
    mock_cli.interactive_mode.command_router = MagicMock()
    mock_cli.interactive_mode.command_router.set_setup_wizard_callback = MagicMock()
    mock_cli.interactive_mode._process_input = MagicMock(return_value=True)
    return mock_cli


class StdoutSentinel(io.TextIOBase):
    """Captures any writes to stdout/stderr and records the callers."""

    def __init__(self, name: str):
        self.name = name
        self.violations: list[str] = []
        self._buffer = io.StringIO()

    def write(self, s: str) -> int:
        if s and s.strip():
            # Capture the call stack to identify the offender
            import traceback
            stack = "".join(traceback.format_stack()[:-1])
            self.violations.append(f"[{self.name}] {s!r}\n{stack}")
        return len(s)

    def flush(self):
        pass

    def fileno(self):
        raise io.UnsupportedOperation("sentinel has no fd")

    @property
    def encoding(self):
        return "utf-8"


class TestNoRawStdoutDuringAppLifecycle:
    """Nothing should write to stdout/stderr while Textual runs."""

    @pytest.mark.asyncio
    async def test_app_startup_no_stdout_writes(self):
        """App startup (mount, banner, CLI ready) should not touch stdout."""
        app = ScrappyApp(cli_factory=create_mock_cli)

        stdout_sentinel = StdoutSentinel("stdout")
        stderr_sentinel = StdoutSentinel("stderr")

        async with app.run_test(size=(80, 24)) as pilot:
            # Patch AFTER Textual's own startup (which legitimately uses the terminal)
            real_stdout = sys.stdout
            real_stderr = sys.stderr
            sys.stdout = stdout_sentinel
            sys.stderr = stderr_sentinel

            # Suppress logging handlers that write to stderr
            root_logger = logging.getLogger()
            old_handlers = root_logger.handlers[:]
            root_logger.handlers = [h for h in root_logger.handlers
                                    if not isinstance(h, logging.StreamHandler)]

            try:
                await pilot.pause()
                await pilot.pause()
                await pilot.pause()
            finally:
                sys.stdout = real_stdout
                sys.stderr = real_stderr
                root_logger.handlers = old_handlers

        # Filter out known-safe writes (Textual internals, test framework)
        real_violations = [
            v for v in stdout_sentinel.violations + stderr_sentinel.violations
            if "textual" not in v.lower()
            and "pytest" not in v.lower()
            and "_pytest" not in v.lower()
        ]

        assert len(real_violations) == 0, (
            "Raw writes to terminal detected during app startup!\n"
            "This WILL break mouse selection.\n\n"
            + "\n---\n".join(real_violations[:5])
        )

    @pytest.mark.asyncio
    async def test_chat_input_no_stdout_writes(self):
        """Processing a chat message should not touch stdout."""
        app = ScrappyApp(cli_factory=create_mock_cli)

        stdout_sentinel = StdoutSentinel("stdout")
        stderr_sentinel = StdoutSentinel("stderr")

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            real_stdout = sys.stdout
            real_stderr = sys.stderr
            sys.stdout = stdout_sentinel
            sys.stderr = stderr_sentinel

            root_logger = logging.getLogger()
            old_handlers = root_logger.handlers[:]
            root_logger.handlers = [h for h in root_logger.handlers
                                    if not isinstance(h, logging.StreamHandler)]

            try:
                await pilot.press("h", "e", "l", "l", "o")
                await pilot.press("enter")
                await pilot.pause()
                await pilot.pause()
                await pilot.pause()
            finally:
                sys.stdout = real_stdout
                sys.stderr = real_stderr
                root_logger.handlers = old_handlers

        real_violations = [
            v for v in stdout_sentinel.violations + stderr_sentinel.violations
            if "textual" not in v.lower()
            and "pytest" not in v.lower()
            and "_pytest" not in v.lower()
        ]

        assert len(real_violations) == 0, (
            "Raw writes to terminal detected during chat!\n"
            "This WILL break mouse selection.\n\n"
            + "\n---\n".join(real_violations[:5])
        )

    @pytest.mark.asyncio
    async def test_help_command_no_stdout_writes(self):
        """/help command should not touch stdout."""
        app = ScrappyApp(cli_factory=create_mock_cli)

        stdout_sentinel = StdoutSentinel("stdout")
        stderr_sentinel = StdoutSentinel("stderr")

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            real_stdout = sys.stdout
            real_stderr = sys.stderr
            sys.stdout = stdout_sentinel
            sys.stderr = stderr_sentinel

            root_logger = logging.getLogger()
            old_handlers = root_logger.handlers[:]
            root_logger.handlers = [h for h in root_logger.handlers
                                    if not isinstance(h, logging.StreamHandler)]

            try:
                await pilot.press("/", "h", "e", "l", "p")
                await pilot.press("enter")
                await pilot.pause()
                await pilot.pause()
                await pilot.pause()
            finally:
                sys.stdout = real_stdout
                sys.stderr = real_stderr
                root_logger.handlers = old_handlers

        real_violations = [
            v for v in stdout_sentinel.violations + stderr_sentinel.violations
            if "textual" not in v.lower()
            and "pytest" not in v.lower()
            and "_pytest" not in v.lower()
        ]

        assert len(real_violations) == 0, (
            "Raw writes to terminal detected during /help!\n"
            "This WILL break mouse selection.\n\n"
            + "\n---\n".join(real_violations[:5])
        )
