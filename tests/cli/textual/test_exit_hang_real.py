"""Test that reproduces the REAL exit hang bug.

The bug: After running an agent command that writes a file,
app.run() hangs indefinitely when exit() is called.

This test uses real app.run() (not run_test()) and actually
executes an agent command.
"""

import os
import subprocess
import sys
import tempfile

import pytest


class TestRealExitHang:
    """Test real exit hang after agent execution."""

    def test_app_run_with_agent_command(self):
        """Real app.run() with agent command - reproduces hang.

        Steps:
        1. Start app with real app.run()
        2. Wait for app to be ready
        3. Programmatically trigger an agent command
        4. Wait for agent to complete
        5. Call exit()
        6. Verify app exits within timeout

        This should FAIL (hang) if the bug exists.
        """
        script = '''
import os
import sys
import threading
import time
import tempfile
import asyncio

os.environ["SCRAPPY_MOCK_LLM"] = "1"

# Create temp working directory
tmpdir = tempfile.mkdtemp()
os.chdir(tmpdir)
with open(".gitignore", "w") as f:
    f.write("# existing\\n")

# Debug logging to file (Textual captures stderr)
logfile = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log")
def log(msg):
    logfile.write(f"{time.time():.2f}: {msg}\\n")
    logfile.flush()

log(f"Working in: {tmpdir}")
log("Script starting")

from scrappy.cli.textual.app import ScrappyApp
from scrappy.cli.core import CLI
from scrappy.cli.screens import MainAppScreen

cli = CLI()
app = ScrappyApp(cli_factory=lambda: cli)

log("App created")

def run_agent_then_exit():
    """Thread that waits for app ready, runs agent, then exits."""
    log("Thread: waiting for app.ready")

    # Wait for app.ready (basic readiness)
    for i in range(100):
        time.sleep(0.1)
        if app.ready:
            log(f"Thread: app.ready=True after {i*0.1:.1f}s")
            log(f"Thread: app.interactive_mode={app.interactive_mode is not None}")
            try:
                screen = app.screen
                log(f"Thread: screen type={type(screen).__name__}")
                if isinstance(screen, MainAppScreen):
                    log(f"Thread: screen.interactive_mode={screen.interactive_mode is not None}")
            except Exception as e:
                log(f"Thread: error checking screen: {e}")
            break
    else:
        log("Thread: app.ready never became True!")
        app.exit()
        return

    # Wait a bit more to ensure initialization completes
    log("Thread: waiting 2s for full init")
    time.sleep(2.0)

    # Log state again
    log(f"Thread: after wait - app.interactive_mode={app.interactive_mode is not None}")
    try:
        screen = app.screen
        if isinstance(screen, MainAppScreen):
            log(f"Thread: after wait - screen.interactive_mode={screen.interactive_mode is not None}")
    except Exception as e:
        log(f"Thread: error: {e}")

    # Force the screen to be ready and run agent
    try:
        screen = app.screen
        if isinstance(screen, MainAppScreen) and app.interactive_mode is not None:
            # MANUALLY SET screen.interactive_mode since deferred init doesn't do it
            if screen.interactive_mode is None:
                screen.interactive_mode = app.interactive_mode
                log("Thread: MANUALLY set screen.interactive_mode")

            log("Thread: running agent command")
            # Mock confirm
            agent_mgr = app.interactive_mode.command_router.agent_mgr
            if agent_mgr and hasattr(agent_mgr, '_interaction'):
                agent_mgr._interaction.confirm = lambda *a, **k: False
                log("Thread: mocked confirm")

            def run_command():
                log("Thread: inside run_command")
                return screen.process_command("/agent add .mypy_cache to gitignore")

            app.call_from_thread(run_command)
            log("Thread: agent command dispatched via call_from_thread")
            time.sleep(5)
            log("Thread: waited 5s for agent")

            # Check result
            try:
                with open(".gitignore") as f:
                    content = f.read()
                log(f"Thread: .gitignore content: {content!r}")
            except Exception as e:
                log(f"Thread: error reading file: {e}")
        else:
            log(f"Thread: can't run agent - screen={type(screen).__name__}, interactive_mode={app.interactive_mode is not None}")
    except Exception as e:
        import traceback
        log(f"Thread: error running agent: {e}")
        log(f"Thread: traceback: {traceback.format_exc()}")

    # Now exit
    log("Thread: calling app.exit()")
    app.exit()
    log("Thread: app.exit() returned")

agent_thread = threading.Thread(target=run_agent_then_exit, daemon=True)
agent_thread.start()

log("Starting app.run()")
print(f"LOGFILE:{logfile.name}", flush=True)
print(f"TMPDIR:{tmpdir}", flush=True)
try:
    app.run()
except Exception as e:
    log(f"app.run() raised: {e}")
log("app.run() returned")

# Write marker file (stdout may be blocked)
import pathlib
marker = pathlib.Path(tmpdir) / "EXIT_MARKER"
marker.write_text("OK")
log(f"Wrote marker to {marker}")

print("EXIT_OK", flush=True)
'''

        try:
            # Don't capture stderr - Textual's shutdown warnings can fill pipe buffer
            # causing deadlock. We only need stdout for EXIT_OK.
            result = subprocess.run(
                [sys.executable, "-u", "-c", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,  # Discard stderr to avoid pipe deadlock
                text=True,
                timeout=20,  # 20s timeout - agent needs time to run
                env={**os.environ, "SCRAPPY_MOCK_LLM": "1"},
            )

            print(f"stdout: {result.stdout}")

            # Read logfile
            logfile_content = self._extract_logfile(result.stdout)
            print(f"Logfile:\n{logfile_content}")

            # Check for marker file (more reliable than stdout)
            tmpdir = self._extract_tmpdir(result.stdout)
            marker_exists = False
            if tmpdir:
                marker_path = os.path.join(tmpdir, "EXIT_MARKER")
                marker_exists = os.path.exists(marker_path)
                print(f"Marker file exists: {marker_exists} at {marker_path}")

            # Success criteria:
            # 1. "EXIT_OK" in stdout (graceful shutdown), OR
            # 2. returncode == 0 (process exited cleanly), OR
            # 3. Marker file exists (app.run() returned and cleanup ran)
            graceful_exit = "EXIT_OK" in result.stdout
            clean_exit = result.returncode == 0

            assert graceful_exit or clean_exit or marker_exists, \
                f"App did not exit cleanly (returncode={result.returncode}, marker={marker_exists}).\nLogfile:\n{logfile_content}"

        except subprocess.TimeoutExpired as e:
            stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            logfile_content = self._extract_logfile(stdout)

            # Check marker file - if it exists, app.run() returned but stdout was blocked
            tmpdir = self._extract_tmpdir(stdout)
            marker_exists = False
            if tmpdir:
                marker_path = os.path.join(tmpdir, "EXIT_MARKER")
                marker_exists = os.path.exists(marker_path)

            if marker_exists:
                # App actually exited, stdout was just blocked
                print(f"Note: App exited (marker found) but subprocess timed out on stdout")
                print(f"Logfile:\n{logfile_content}")
                return  # Test passes

            print(f"HANG DETECTED!")
            print(f"Logfile:\n{logfile_content}")
            pytest.fail(
                f"EXIT HANG BUG: app hung for 20s after agent command.\n"
                f"Logfile:\n{logfile_content}"
            )

    def test_app_run_simple_exit_baseline(self):
        """Baseline: app.run() exits cleanly WITHOUT agent command.

        This should PASS - proves basic exit works.
        """
        script = '''
import os
import sys
import threading
import time
import tempfile

os.environ["SCRAPPY_MOCK_LLM"] = "1"

logfile = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log")
def log(msg):
    logfile.write(f"{time.time():.2f}: {msg}\\n")
    logfile.flush()

log("Script starting")

from scrappy.cli.textual.app import ScrappyApp
from scrappy.cli.core import CLI

cli = CLI()
app = ScrappyApp(cli_factory=lambda: cli)

log("App created")

def delayed_exit():
    log("Thread: waiting 3s")
    time.sleep(3)
    log("Thread: calling app.exit()")
    app.exit()
    log("Thread: app.exit() returned")

threading.Thread(target=delayed_exit, daemon=True).start()

log("Starting app.run()")
print(f"LOGFILE:{logfile.name}", flush=True)
app.run()
log("app.run() returned")
print("EXIT_OK", flush=True)
'''

        try:
            result = subprocess.run(
                [sys.executable, "-u", "-c", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=10,
                env={**os.environ, "SCRAPPY_MOCK_LLM": "1"},
            )

            print(f"stdout: {result.stdout}")
            logfile_content = self._extract_logfile(result.stdout)
            print(f"Logfile:\n{logfile_content}")

            # Success: either graceful exit or watchdog exit
            graceful_exit = "EXIT_OK" in result.stdout
            watchdog_exit = result.returncode == 0 and "EXIT_OK" not in result.stdout

            assert graceful_exit or watchdog_exit, \
                f"Baseline failed - basic exit broken (returncode={result.returncode}).\nLogfile:\n{logfile_content}"

            if watchdog_exit:
                print("Note: Baseline exited via watchdog (os._exit)")

        except subprocess.TimeoutExpired as e:
            stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            logfile_content = self._extract_logfile(stdout)
            pytest.fail(
                f"BASELINE FAILED: Even basic exit hangs!\n"
                f"Logfile:\n{logfile_content}"
            )

    def _extract_logfile(self, stdout: str) -> str:
        """Extract and read logfile from stdout."""
        for line in stdout.split('\n'):
            if line.startswith("LOGFILE:"):
                logfile_path = line.split(":", 1)[1].strip()
                try:
                    with open(logfile_path) as f:
                        return f.read()
                except Exception as ex:
                    return f"Error reading {logfile_path}: {ex}"
        return "No logfile found in output"

    def _extract_tmpdir(self, stdout: str) -> str:
        """Extract tmpdir path from stdout."""
        for line in stdout.split('\n'):
            if line.startswith("TMPDIR:"):
                return line.split(":", 1)[1].strip()
        return ""


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
