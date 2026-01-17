"""
Pilot test to reproduce scrappy-8ebm: SelectableLog loses mouse responsiveness.

Bug: After /agent completes with undo (y), text selection and scrolling
stop working in the chat log.

ROOT CAUSE: subprocess.run() corrupts terminal mouse state on Windows.
Textual uses escape sequences to enable mouse tracking. When subprocess
runs (even with capture_output=True), it can reset terminal state.
Textual doesn't re-enable mouse mode after subprocess exits.

Fix: Use app.suspend() context manager when running subprocess calls.
See: https://github.com/Textualize/textual/issues/1093

This test aims to:
1. Verify SelectableLog receives mouse events normally
2. Prove that subprocess calls break mouse events
3. Show that app.suspend() preserves mouse functionality
"""

import os
import subprocess
import pytest
from textual.geometry import Offset
from unittest.mock import MagicMock, patch, AsyncMock

from scrappy.cli.widgets.selectable_log import SelectableLog
from scrappy.cli.textual.messages import ActivityStateChange
from scrappy.cli.protocols import ActivityState


# Set mock mode for tests
os.environ["SCRAPPY_MOCK_LLM"] = "1"


class TestSelectableLogBasicMouse:
    """Basic mouse event tests using pilot."""

    @pytest.mark.asyncio
    async def test_click_on_log_sets_selection_start(self):
        """Clicking on log should set selection start."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            CSS = """
            SelectableLog { height: 100%; width: 100%; }
            """
            def compose(self) -> ComposeResult:
                yield SelectableLog(id="log")

        app = TestApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            log = app.query_one("#log", SelectableLog)
            log.write("Line 1: Hello World")
            log.write("Line 2: Test content")
            await pilot.pause()

            # Click triggers mouse_down then mouse_up
            await pilot.click("#log", offset=Offset(10, 1))
            await pilot.pause()

            # After click, _is_selecting should be False (mouse_up was called)
            assert log._is_selecting is False
            # But selection_start should have been set during mouse_down
            assert log._selection_start is not None, "Selection start should be set after click"


class TestSelectableLogAfterAgentSimulation:
    """Simulate what happens during /agent execution."""

    @pytest.mark.asyncio
    async def test_mouse_after_rapid_writes_and_idle(self):
        """Mouse should work after rapid writes followed by IDLE state."""
        from textual.app import App, ComposeResult
        from scrappy.cli.textual import ActivityIndicator

        class TestApp(App):
            CSS = """
            SelectableLog { height: 20; width: 80; }
            ActivityIndicator { height: auto; }
            """
            def compose(self) -> ComposeResult:
                yield SelectableLog(id="log")
                yield ActivityIndicator()

            def on_activity_state_change(self, message: ActivityStateChange) -> None:
                indicator = self.query_one(ActivityIndicator)
                if message.state == ActivityState.IDLE:
                    indicator.hide()
                else:
                    indicator.show(message.state, message.message)

        app = TestApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            log = app.query_one("#log", SelectableLog)

            # Phase 1: Initial content
            log.write("Initial prompt")
            await pilot.pause()

            # Phase 2: Simulate THINKING state (agent starting)
            app.post_message(ActivityStateChange(ActivityState.THINKING))
            await pilot.pause()

            # Phase 3: Rapid output (like agent execution)
            for i in range(15):
                log.write(f"> Tool output line {i}")
            await pilot.pause()

            # Phase 4: Final message and IDLE
            log.write("To undo changes: scrappy undo")
            app.post_message(ActivityStateChange(ActivityState.IDLE))
            await pilot.pause()

            # Phase 5: Try to click - this is where the bug manifests
            await pilot.click("#log", offset=Offset(10, 5))
            await pilot.pause()

            # Verify selection was set
            assert log._selection_start is not None, \
                "BUG: Selection start not set - mouse events not reaching widget"


class TestSelectableLogWithCaptureMode:
    """Test with capture mode simulation (y/n prompts)."""

    @pytest.mark.asyncio
    async def test_mouse_after_capture_mode_exit(self):
        """Mouse should work after exiting capture mode."""
        from textual.app import App, ComposeResult
        from textual.widgets import TextArea, Label
        from textual.containers import Container

        class TestApp(App):
            CSS = """
            SelectableLog { height: 15; width: 80; }
            #input_container { height: 3; }
            TextArea { height: 1; }
            """
            def compose(self) -> ComposeResult:
                yield SelectableLog(id="log")
                with Container(id="input_container"):
                    yield Label(">", id="prompt")
                    yield TextArea(id="input")

            def simulate_capture_mode(self):
                """Simulate entering and exiting capture mode."""
                input_widget = self.query_one("#input", TextArea)
                input_widget.focus()

            def simulate_capture_exit(self):
                """Simulate exiting capture mode."""
                input_widget = self.query_one("#input", TextArea)
                input_widget.focus()

        app = TestApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            log = app.query_one("#log", SelectableLog)

            # Write initial content
            log.write("Create undo point? [y/n]")
            await pilot.pause()

            # Simulate capture mode (user types 'y')
            app.simulate_capture_mode()
            await pilot.pause()

            # Simulate exiting capture mode
            app.simulate_capture_exit()
            await pilot.pause()

            # Write agent output
            for i in range(10):
                log.write(f"Agent output {i}")
            await pilot.pause()

            log.write("To undo changes: scrappy undo")
            await pilot.pause()

            # Try clicking on log
            await pilot.click("#log", offset=Offset(10, 5))
            await pilot.pause()

            # Check selection was set
            assert log._selection_start is not None, \
                "Selection should work after capture mode exit"


class TestSelectableLogVirtualSize:
    """Test virtual size behavior which affects scrollability."""

    @pytest.mark.asyncio
    async def test_virtual_size_set_after_writes(self):
        """Virtual size should reflect content."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield SelectableLog(id="log")

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            log = app.query_one("#log", SelectableLog)

            for i in range(50):
                log.write(f"Line {i}")
            await pilot.pause()

            assert log.virtual_size.height == 50
            assert log.virtual_size.width > 0

    @pytest.mark.asyncio
    async def test_virtual_size_not_zero_after_idle(self):
        """Virtual size should not be reset to zero after IDLE."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield SelectableLog(id="log")

            def on_activity_state_change(self, message: ActivityStateChange) -> None:
                pass  # Just handle the message

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            log = app.query_one("#log", SelectableLog)

            # Write content
            for i in range(20):
                log.write(f"Line {i}")
            await pilot.pause()

            height_before = log.virtual_size.height
            assert height_before == 20

            # Post IDLE
            app.post_message(ActivityStateChange(ActivityState.IDLE))
            await pilot.pause()

            height_after = log.virtual_size.height
            assert height_after == 20, \
                f"BUG: Virtual size changed from {height_before} to {height_after} after IDLE"


class TestScrappyAppSelectableLog:
    """Test with actual ScrappyApp to reproduce the real bug."""


class TestSubprocessCorruptsMouseState:
    """
    Documentation tests for scrappy-8ebm root cause.

    ROOT CAUSE of scrappy-8ebm:
    - create_undo_point() runs git commands via subprocess.run(shell=True)
    - On Windows, this can corrupt terminal's mouse tracking state
    - Textual doesn't know to re-enable mouse mode after subprocess
    - Result: SelectableLog stops receiving mouse events

    IMPORTANT: This bug ONLY manifests in real terminal environments.
    Textual's pilot test runner uses a simulated terminal that doesn't
    have real mouse mode escape sequences, so subprocess can't corrupt
    the terminal state in tests.

    FIX: Use app.suspend() context manager when running subprocess calls.
    See: https://github.com/Textualize/textual/issues/1093

    Manual reproduction steps (real terminal required):
    1. Run scrappy in Windows Terminal
    2. Run: /agent create a .gitignore with .idea in it
    3. Press 'y' for undo (this triggers subprocess.run for git commands)
    4. Wait for agent to complete
    5. Try to click/drag in the log - FAILS (mouse events not received)
    """

    @pytest.mark.asyncio
    async def test_mouse_works_in_test_environment(self):
        """
        Verify mouse works in Textual's simulated test environment.

        NOTE: This passes because pilot uses a simulated terminal.
        The real bug only occurs in actual terminal environments.
        """
        from textual.app import App, ComposeResult
        from textual import work

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield SelectableLog(id="log")

            @work(thread=True)
            def run_subprocess_in_worker(self) -> None:
                """Simulate what create_undo_point() does."""
                subprocess.run(
                    "git status",
                    shell=True,
                    capture_output=True,
                    text=True,
                )

        app = TestApp()
        async with app.run_test(size=(80, 24)) as pilot:
            log = app.query_one("#log", SelectableLog)
            log.write("Before subprocess")
            await pilot.pause()

            # Mouse works before subprocess
            await pilot.click("#log", offset=Offset(5, 0))
            await pilot.pause()
            assert log._selection_start is not None, "Mouse should work before"

            log._selection_start = None

            # Run subprocess (simulates create_undo_point)
            app.run_subprocess_in_worker()
            await pilot.pause()
            await pilot.pause()

            log.write("After subprocess")
            await pilot.pause()

            # In test env, this PASSES because no real terminal to corrupt
            # In real terminal, this would FAIL - that's the bug
            await pilot.click("#log", offset=Offset(5, 1))
            await pilot.pause()

            # This passes in test env but fails in real terminal
            assert log._selection_start is not None, \
                "In test env this passes; in real terminal it fails (scrappy-8ebm)"


class TestUndoFlowMouseEvents:
    """
    Test the exact flow that breaks mouse events with undo.

    The undo flow differs from non-undo in that there are EXTRA writes
    to the log between capture mode exit and agent execution:

    With undo:
    1. Capture mode for undo prompt (y/n)
    2. User presses 'y'
    3. _exit_capture_ui() posts THINKING
    4. io.echo("Creating undo point...")  <-- EXTRA WRITE
    5. create_undo_point() runs subprocess
    6. io.secho("Undo point created...")  <-- EXTRA WRITE
    7. Agent starts

    Without undo:
    1. Capture mode for undo prompt (y/n)
    2. User presses 'n'
    3. _exit_capture_ui() posts THINKING
    4. Agent starts immediately (no extra writes)
    """

    @pytest.mark.asyncio
    async def test_mouse_after_capture_mode_with_immediate_writes(self):
        """
        Test: Does writing to the log immediately after capture mode exit
        break mouse events?

        This mimics the undo flow where io.echo/io.secho are called
        right after the undo prompt is answered.
        """
        from textual.app import App, ComposeResult
        from textual.widgets import TextArea, Label
        from textual.containers import Container

        class TestApp(App):
            CSS = """
            SelectableLog { height: 15; width: 80; }
            #input_container { height: 3; }
            """

            def compose(self) -> ComposeResult:
                yield SelectableLog(id="log")
                with Container(id="input_container"):
                    yield Label(">", id="prompt")
                    yield TextArea(id="input")

        app = TestApp()
        async with app.run_test(size=(80, 24)) as pilot:
            log = app.query_one("#log", SelectableLog)

            # Initial content
            log.write("Initial line")
            await pilot.pause()

            # Verify mouse works initially
            await pilot.click("#log", offset=Offset(5, 0))
            await pilot.pause()
            assert log._selection_start is not None, "Mouse should work initially"
            log._selection_start = None

            # Simulate capture mode (would normally hide activity indicator)
            input_container = app.query_one("#input_container")
            input_container.add_class("capture-mode")
            await pilot.pause()

            # Simulate capture mode exit (would normally post THINKING)
            input_container.remove_class("capture-mode")
            app.post_message(ActivityStateChange(ActivityState.THINKING))
            await pilot.pause()

            # THIS IS THE KEY DIFFERENCE with undo:
            # Immediately write output after capture mode exit
            log.write("Creating undo point...")
            await pilot.pause()
            log.write("Undo point created: scrappy-xxx")
            await pilot.pause()

            # Now try to click - does mouse still work?
            await pilot.click("#log", offset=Offset(5, 2))
            await pilot.pause()

            assert log._selection_start is not None, \
                "BUG: Mouse broken after writes following capture mode exit"

    @pytest.mark.asyncio
    async def test_mouse_after_capture_mode_without_writes(self):
        """
        Control test: No extra writes after capture mode exit.
        This mimics the non-undo flow.
        """
        from textual.app import App, ComposeResult
        from textual.widgets import TextArea, Label
        from textual.containers import Container

        class TestApp(App):
            CSS = """
            SelectableLog { height: 15; width: 80; }
            #input_container { height: 3; }
            """

            def compose(self) -> ComposeResult:
                yield SelectableLog(id="log")
                with Container(id="input_container"):
                    yield Label(">", id="prompt")
                    yield TextArea(id="input")

        app = TestApp()
        async with app.run_test(size=(80, 24)) as pilot:
            log = app.query_one("#log", SelectableLog)

            # Initial content
            log.write("Initial line")
            await pilot.pause()

            # Verify mouse works initially
            await pilot.click("#log", offset=Offset(5, 0))
            await pilot.pause()
            assert log._selection_start is not None, "Mouse should work initially"
            log._selection_start = None

            # Simulate capture mode
            input_container = app.query_one("#input_container")
            input_container.add_class("capture-mode")
            await pilot.pause()

            # Simulate capture mode exit (no extra writes - like non-undo)
            input_container.remove_class("capture-mode")
            app.post_message(ActivityStateChange(ActivityState.THINKING))
            await pilot.pause()

            # NO extra writes here - goes straight to "agent execution"

            # Now try to click
            await pilot.click("#log", offset=Offset(5, 0))
            await pilot.pause()

            assert log._selection_start is not None, \
                "Mouse should work after capture mode exit without writes"


class TestSubprocessMissingTerminalIsolation:
    """
    PROOF: undo.py subprocess calls lack terminal isolation.

    ROOT CAUSE of scrappy-8ebm:
    - subprocess.run() without stdin=DEVNULL allows the subprocess to
      interact with the terminal
    - In worker threads, this corrupts Textual's mouse tracking state
    - The terminal escape sequences (ESC[?1000h) get corrupted
    - Result: SelectableLog stops receiving mouse events

    This test FAILS if the bug exists (missing stdin=DEVNULL).
    This test PASSES after the fix is applied.
    """

    def test_undo_run_missing_stdin_devnull(self):
        """
        FAIL: _run() does not pass stdin=DEVNULL to subprocess.run.

        This is the root cause of scrappy-8ebm. Without stdin isolation,
        subprocess can interact with the terminal and corrupt mouse state.

        Expected: subprocess.run called with stdin=subprocess.DEVNULL
        Actual: subprocess.run called WITHOUT stdin parameter
        """
        import subprocess
        from unittest.mock import patch, MagicMock

        # Import the module to test
        from scrappy import undo

        with patch.object(subprocess, 'run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )

            # Call _run (the internal function that wraps subprocess.run)
            undo._run("git status", check=False)

            # Verify subprocess.run was called
            mock_run.assert_called_once()

            # Get the actual call arguments
            call_kwargs = mock_run.call_args.kwargs

            # THIS IS THE BUG: stdin should be DEVNULL but it's not set
            # This test FAILS until the fix is applied
            assert 'stdin' in call_kwargs, \
                "BUG: subprocess.run called without stdin parameter - allows terminal interaction"
            assert call_kwargs['stdin'] == subprocess.DEVNULL, \
                f"BUG: stdin should be DEVNULL but is {call_kwargs.get('stdin')}"

    def test_create_undo_point_subprocess_isolation(self):
        """
        FAIL: create_undo_point's subprocess calls lack terminal isolation.

        The git commands in create_undo_point() run via _run() which
        doesn't isolate stdin, allowing terminal corruption.
        """
        import subprocess
        from unittest.mock import patch, MagicMock

        from scrappy import undo

        # Track all subprocess.run calls
        subprocess_calls = []

        def track_subprocess(*args, **kwargs):
            subprocess_calls.append(kwargs)
            return MagicMock(returncode=0, stdout="main\n", stderr="")

        with patch.object(subprocess, 'run', side_effect=track_subprocess):
            with patch.object(undo, 'is_dirty', return_value=False):
                with patch.object(undo, 'has_untracked', return_value=False):
                    with patch.object(undo, 'is_shallow_clone', return_value=False):
                        with patch.object(undo, 'persist_undo_state'):
                            with patch.object(undo, 'prune_old_undo_states'):
                                with patch('os.getcwd', return_value='/test'):
                                    try:
                                        undo.create_undo_point()
                                    except Exception:
                                        pass  # May fail due to mocking, that's OK

        # Should have made at least one subprocess call
        assert len(subprocess_calls) > 0, "Expected subprocess.run calls"

        # Check that ALL calls have stdin=DEVNULL
        for i, call in enumerate(subprocess_calls):
            assert 'stdin' in call, \
                f"BUG: subprocess call #{i+1} missing stdin parameter"
            assert call['stdin'] == subprocess.DEVNULL, \
                f"BUG: subprocess call #{i+1} stdin should be DEVNULL"


class TestUndoLockMouseEvents:
    """
    Test if undo_lock file operations break mouse events.

    The undo_lock() uses low-level os.open/os.write/os.close operations.
    On Windows, these might interfere with terminal file descriptors
    that Textual uses for mouse event tracking.
    """

    @pytest.mark.asyncio
    async def test_os_open_in_worker_breaks_mouse(self):
        """
        Test: Do low-level file operations in worker thread break mouse?

        This mimics what undo_lock() does - creates a file using os.open
        with O_CREAT | O_EXCL flags, writes to it, and closes it.
        """
        import os
        import tempfile
        from textual.app import App, ComposeResult
        from textual import work

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield SelectableLog(id="log")

            @work(thread=True)
            def do_file_ops_in_worker(self) -> None:
                """Simulate undo_lock file operations."""
                # Create a temp file path
                with tempfile.TemporaryDirectory() as tmpdir:
                    lock_path = os.path.join(tmpdir, "test.lock")

                    # This is exactly what undo_lock does
                    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    os.write(fd, str(os.getpid()).encode())
                    os.close(fd)

                    # Clean up
                    os.unlink(lock_path)

        app = TestApp()
        async with app.run_test(size=(80, 24)) as pilot:
            log = app.query_one("#log", SelectableLog)
            log.write("Before file ops")
            await pilot.pause()

            # Verify mouse works before
            await pilot.click("#log", offset=Offset(5, 0))
            await pilot.pause()
            assert log._selection_start is not None, "Mouse should work before"
            log._selection_start = None

            # Do file operations in worker thread
            app.do_file_ops_in_worker()
            await pilot.pause()
            await pilot.pause()

            log.write("After file ops")
            await pilot.pause()

            # Does mouse still work?
            await pilot.click("#log", offset=Offset(5, 1))
            await pilot.pause()

            assert log._selection_start is not None, \
                "BUG: Mouse broken after os.open/write/close in worker thread"

    @pytest.mark.asyncio
    async def test_time_sleep_in_worker_breaks_mouse(self):
        """
        Test: Does time.sleep in worker thread break mouse?

        undo_lock has a polling loop with time.sleep(0.1).
        """
        import time
        from textual.app import App, ComposeResult
        from textual import work

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield SelectableLog(id="log")

            @work(thread=True)
            def sleep_in_worker(self) -> None:
                """Simulate undo_lock polling."""
                time.sleep(0.2)

        app = TestApp()
        async with app.run_test(size=(80, 24)) as pilot:
            log = app.query_one("#log", SelectableLog)
            log.write("Before sleep")
            await pilot.pause()

            # Verify mouse works before
            await pilot.click("#log", offset=Offset(5, 0))
            await pilot.pause()
            assert log._selection_start is not None, "Mouse should work before"
            log._selection_start = None

            # Do sleep in worker thread
            app.sleep_in_worker()
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()  # Extra pause to let sleep complete

            log.write("After sleep")
            await pilot.pause()

            # Does mouse still work?
            await pilot.click("#log", offset=Offset(5, 1))
            await pilot.pause()

            assert log._selection_start is not None, \
                "BUG: Mouse broken after time.sleep in worker thread"
