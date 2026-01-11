"""
Subprocess execution component.

Implements SubprocessRunnerProtocol to handle low-level process
execution, streaming, timeout handling, and signal management.

Supports cancellation via CancellationToken for responsive user interrupts.
"""

import os
import subprocess
import threading
import time
from typing import TYPE_CHECKING, Optional, List

from ..protocols import ExecutionResult
from .output_collector import ThreadSafeOutputCollector
from scrappy.cli.protocols import CLIIOProtocol
from scrappy.infrastructure.exceptions import CancelledException

if TYPE_CHECKING:
    from scrappy.infrastructure.threading.protocols import CancellationTokenProtocol


class SubprocessRunner:
    """
    Executes commands in subprocesses with streaming and timeout support.

    This class implements a single responsibility: subprocess execution.
    It does NOT handle security validation, output parsing, or platform fixes.

    Following dependency injection principles, accepts optional IO interface
    for progress output. If not provided, progress messages are suppressed.

    Supports cancellation via CancellationToken - uses Event.wait() for
    efficient cancellation instead of polling sleep loops.
    """

    def __init__(
        self,
        io: Optional[CLIIOProtocol] = None,
        cancellation_token: Optional["CancellationTokenProtocol"] = None,
    ):
        """Initialize subprocess runner.

        Args:
            io: Optional IO interface for progress output. If None,
                progress messages are suppressed.
            cancellation_token: Optional token for user cancellation support.
                If provided, allows responsive interrupt during execution.
        """
        self._io = io
        self._cancellation_token = cancellation_token

    def execute(
        self,
        command: str,
        cwd: str,
        timeout: Optional[float] = None,
        stream_output: bool = False,
    ) -> ExecutionResult:
        """
        Execute command in subprocess.

        Args:
            command: Command to execute
            cwd: Working directory
            timeout: Optional timeout in seconds
            stream_output: Whether to stream output in real-time

        Returns:
            ExecutionResult with stdout, stderr, and exit code

        Raises:
            TimeoutError: If execution exceeds timeout
        """
        timeout = timeout or 120  # Default 2 minutes

        collector = ThreadSafeOutputCollector()
        process = None
        start_time = time.time()

        try:
            # Set environment for unbuffered output
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['NODE_ENV'] = 'development'
            env['CI'] = 'true'
            env['npm_config_yes'] = 'true'

            process = subprocess.Popen(
                command,
                shell=True,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=env,
                encoding='utf-8',
                errors='replace',
            )

            def read_output():
                try:
                    for line in iter(process.stdout.readline, ''):
                        if line:
                            collector.append(line.rstrip())
                            if stream_output and collector.line_count() % 10 == 0 and self._io:
                                self._io.echo(f"   ... {collector.line_count()} lines processed")
                except Exception:
                    pass

            reader_thread = threading.Thread(target=read_output)
            reader_thread.daemon = True
            reader_thread.start()

            stall_warning_shown = False
            while process.poll() is None:
                elapsed = time.time() - start_time
                stall_time = time.time() - collector.get_last_output_time()

                if elapsed > timeout:
                    process.kill()
                    raise TimeoutError(f"Command timed out after {timeout}s")

                # Check cancellation using Event.wait() instead of sleep+poll
                # This wakes immediately on cancellation instead of waiting the interval
                if self._cancellation_token is not None:
                    was_cancelled = self._cancellation_token.wait(timeout=0.5)
                    if was_cancelled:
                        if self._cancellation_token.is_force_cancelled:
                            # Force cancel - SIGKILL immediately
                            process.kill()
                            process.wait(timeout=2)
                            raise CancelledException("Force cancelled by user", force=True)
                        else:
                            # Graceful cancel - SIGTERM, allow cleanup
                            process.terminate()
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                # Force kill if won't die gracefully
                                process.kill()
                                process.wait(timeout=2)
                            raise CancelledException("Cancelled by user", force=False)
                else:
                    # No token - use regular sleep
                    time.sleep(0.5)

                if stall_time > 30 and not stall_warning_shown and stream_output and self._io:
                    self._io.echo("   No output for 30s - command may be waiting for input")
                    stall_warning_shown = True

            reader_thread.join(timeout=5)

            execution_time = time.time() - start_time
            stdout = "\n".join(collector.get_lines())
            exit_code = process.returncode

            if stream_output and self._io:
                self._io.echo(f"   Command completed ({collector.line_count()} lines)")

            return ExecutionResult(
                stdout=stdout if stdout else "(no output)",
                stderr="",
                exit_code=exit_code,
                execution_time=execution_time
            )

        except KeyboardInterrupt:
            if process:
                process.kill()
            raise TimeoutError("Command interrupted by user (Ctrl+C)")
        except CancelledException:
            # Re-raise cancellation exceptions directly - don't wrap them
            raise
        except Exception as e:
            if process:
                process.kill()
            raise RuntimeError(f"Error running command: {str(e)}")

    def execute_list(
        self,
        command: List[str],
        cwd: str,
        timeout: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Execute command as list (no shell interpolation).

        Safer than execute() - no shell injection risk.
        Supports cancellation via CancellationToken.

        Args:
            command: Command as list of arguments
            cwd: Working directory
            timeout: Optional timeout in seconds

        Returns:
            ExecutionResult with stdout, stderr, and exit code

        Raises:
            TimeoutError: If execution exceeds timeout
            CancelledException: If cancelled via token
        """
        timeout = timeout or 120  # Default 2 minutes

        start_time = time.time()
        process = None
        stdout_lines: List[str] = []
        stderr_lines: List[str] = []

        try:
            # Run subprocess without shell=True for security
            process = subprocess.Popen(
                command,
                shell=False,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
            )

            # Read stdout/stderr in background threads
            def read_stdout():
                try:
                    for line in iter(process.stdout.readline, ''):
                        if line:
                            stdout_lines.append(line.rstrip())
                except Exception:
                    pass

            def read_stderr():
                try:
                    for line in iter(process.stderr.readline, ''):
                        if line:
                            stderr_lines.append(line.rstrip())
                except Exception:
                    pass

            stdout_thread = threading.Thread(target=read_stdout)
            stderr_thread = threading.Thread(target=read_stderr)
            stdout_thread.daemon = True
            stderr_thread.daemon = True
            stdout_thread.start()
            stderr_thread.start()

            # Poll for completion with cancellation support
            while process.poll() is None:
                elapsed = time.time() - start_time

                if elapsed > timeout:
                    process.kill()
                    raise TimeoutError(f"Command timed out after {timeout}s")

                # Check cancellation using Event.wait() for efficiency
                if self._cancellation_token is not None:
                    was_cancelled = self._cancellation_token.wait(timeout=0.5)
                    if was_cancelled:
                        if self._cancellation_token.is_force_cancelled:
                            process.kill()
                            process.wait(timeout=2)
                            raise CancelledException("Force cancelled by user", force=True)
                        else:
                            process.terminate()
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait(timeout=2)
                            raise CancelledException("Cancelled by user", force=False)
                else:
                    time.sleep(0.5)

            # Wait for reader threads to finish
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)

            execution_time = time.time() - start_time

            return ExecutionResult(
                stdout="\n".join(stdout_lines) if stdout_lines else "",
                stderr="\n".join(stderr_lines) if stderr_lines else "",
                exit_code=process.returncode,
                execution_time=execution_time
            )

        except KeyboardInterrupt:
            if process:
                process.kill()
            raise TimeoutError("Command interrupted by user (Ctrl+C)")
        except CancelledException:
            raise
        except subprocess.SubprocessError as e:
            if process:
                process.kill()
            raise RuntimeError(f"Error running command: {str(e)}")
