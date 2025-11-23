"""
Subprocess execution component.

Implements SubprocessRunnerProtocol to handle low-level process
execution, streaming, timeout handling, and signal management.
"""

import os
import subprocess
import threading
import time
from typing import Optional, TYPE_CHECKING

from ..protocols import ExecutionResult

if TYPE_CHECKING:
    from src.cli.io_interface import CLIIOProtocol


class SubprocessRunner:
    """
    Executes commands in subprocesses with streaming and timeout support.

    This class implements a single responsibility: subprocess execution.
    It does NOT handle security validation, output parsing, or platform fixes.

    Following dependency injection principles, accepts optional IO interface
    for progress output. If not provided, progress messages are suppressed.
    """

    def __init__(self, io: Optional["CLIIOProtocol"] = None):
        """Initialize subprocess runner.

        Args:
            io: Optional IO interface for progress output. If None,
                progress messages are suppressed.
        """
        self._io = io

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

        output_lines = []
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

            last_output_time = start_time

            def read_output():
                nonlocal last_output_time
                try:
                    for line in iter(process.stdout.readline, ''):
                        if line:
                            output_lines.append(line.rstrip())
                            last_output_time = time.time()
                            if stream_output and len(output_lines) % 10 == 0 and self._io:
                                self._io.echo(f"   ... {len(output_lines)} lines processed")
                except Exception:
                    pass

            reader_thread = threading.Thread(target=read_output)
            reader_thread.daemon = True
            reader_thread.start()

            stall_warning_shown = False
            while process.poll() is None:
                elapsed = time.time() - start_time
                stall_time = time.time() - last_output_time

                if elapsed > timeout:
                    process.kill()
                    raise TimeoutError(f"Command timed out after {timeout}s")

                if stall_time > 30 and not stall_warning_shown and stream_output and self._io:
                    self._io.echo(f"   No output for 30s - command may be waiting for input")
                    stall_warning_shown = True

                time.sleep(0.5)

            reader_thread.join(timeout=5)

            execution_time = time.time() - start_time
            stdout = "\n".join(output_lines)
            exit_code = process.returncode

            if stream_output and self._io:
                self._io.echo(f"   Command completed ({len(output_lines)} lines)")

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
        except Exception as e:
            if process:
                process.kill()
            raise RuntimeError(f"Error running command: {str(e)}")
