"""
Test execution tool for the code agent.

Provides test command execution with smart output truncation
optimized for LLM consumption.
"""

import re
from typing import Optional

from .base import ToolBase, ToolParameter, ToolResult, ToolContext
from ..components import CommandSecurity, SubprocessRunner
from ..constants import DEFAULT_COMMAND_TIMEOUT
from scrappy.infrastructure.exceptions import CancelledException


# Output truncation settings
MAX_OUTPUT_CHARS = 4000
HEAD_CHARS = 1000
TAIL_CHARS = 3000


def truncate_test_output(output: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """
    Truncate test output keeping head and tail.

    Test output structure:
    - Head: test collection, setup info
    - Middle: individual test results (often noise for passing tests)
    - Tail: failure details, summary, exit status

    For LLMs, the tail (failures/summary) is most valuable.

    Args:
        output: Raw test output
        max_chars: Maximum output length

    Returns:
        Truncated output with middle removed if needed
    """
    if len(output) <= max_chars:
        return output

    head = output[:HEAD_CHARS]
    tail = output[-TAIL_CHARS:]

    truncated_chars = len(output) - max_chars
    separator = f"\n\n[... {truncated_chars} chars truncated ...]\n\n"

    return head + separator + tail


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape codes from text."""
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_pattern.sub('', text)


class RunTestsTool(ToolBase):
    """
    Tool for executing test commands with smart output handling.

    Provides:
    - Command security validation
    - Configurable timeout
    - Smart output truncation (head + tail for LLM consumption)
    - ANSI code stripping
    """

    def __init__(
        self,
        timeout: int = DEFAULT_COMMAND_TIMEOUT,
        security: Optional[CommandSecurity] = None,
        runner: Optional[SubprocessRunner] = None,
    ):
        """
        Initialize test runner tool.

        Args:
            timeout: Command execution timeout in seconds
            security: Command security validator (default: creates CommandSecurity)
            runner: Subprocess runner (for testing injection only)
        """
        self._timeout = timeout
        self._security = security or CommandSecurity()
        self._injected_runner = runner  # Only used for test injection

    @property
    def name(self) -> str:
        return "run_tests"

    @property
    def description(self) -> str:
        return (
            "Execute test command and return results. "
            "Output is truncated to show setup info and failure details. "
            "Default: 'pytest -v'"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                "command",
                str,
                "Test command to execute (e.g., 'pytest tests/ -v', 'python -m unittest')",
                required=False,
                default="pytest -v"
            ),
            ToolParameter(
                "timeout",
                int,
                "Timeout in seconds (default: 60)",
                required=False,
                default=60
            ),
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        """
        Execute test command.

        Args:
            context: ToolContext with project root and settings
            **kwargs: command (str), timeout (int)

        Returns:
            ToolResult with truncated test output
        """
        command = kwargs.get("command", "pytest -v")
        timeout = kwargs.get("timeout", self._timeout)

        if not command:
            command = "pytest -v"

        # Security validation
        try:
            self._security.validate(command)
        except ValueError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Command blocked: {str(e)}"
            )

        # Dry run check
        if context.dry_run:
            return ToolResult(
                success=True,
                output=f"[DRY RUN] Would execute: {command}",
                metadata={"dry_run": True, "command": command}
            )

        # Get runner - use injected for tests, otherwise create with cancellation token
        runner = self._injected_runner
        if runner is None:
            runner = SubprocessRunner(cancellation_token=context.cancellation_token)

        # Execute command
        try:
            result = runner.execute(
                command=command,
                cwd=str(context.project_root),
                timeout=timeout,
                stream_output=False,
            )

            # Process output
            output = result.stdout or ""
            if result.stderr:
                output += f"\n\nSTDERR:\n{result.stderr}"

            # Strip ANSI codes and truncate
            output = strip_ansi_codes(output)
            output = truncate_test_output(output)

            # Determine success based on exit code
            success = result.exit_code == 0

            return ToolResult(
                success=success,
                output=output,
                metadata={
                    "command": command,
                    "exit_code": result.exit_code,
                    "execution_time": result.execution_time,
                }
            )

        except CancelledException:
            # Re-raise cancellation to propagate up the call stack
            raise
        except TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error=f"Test command timed out after {timeout} seconds. "
                      f"Consider running a subset of tests or increasing timeout."
            )
        except FileNotFoundError:
            # pytest/python not found
            return ToolResult(
                success=False,
                output="",
                error=f"Command not found. Ensure the test framework is installed. "
                      f"Command was: {command}"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error running tests: {str(e)}"
            )
