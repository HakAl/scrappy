"""Output suppression utilities for chatty libraries.

CONTEXT: Libraries like LiteLLM and Langfuse write debug output during import
and initialization. In TUI apps using Textual, this corrupts terminal escape
sequences used for mouse tracking, causing mouse events to stop working.

SYMPTOMS:
- Mouse selection/scrolling works during loading but stops when app is "ready"
- Mouse events stop ~3-5 seconds into initialization (when LLM service created)
- No errors, just silent failure of mouse tracking

ROOT CAUSE:
Terminal escape sequences like ESC[?1000h enable mouse tracking. When a library
writes to stdout/stderr during import, it can corrupt these sequences, causing
the terminal to disable mouse reporting.

SOLUTION:
Suppress output BEFORE importing chatty libraries. This module provides utilities
for that purpose.

See also: src/scrappy/orchestrator/litellm_config.py for the actual fix.
"""

import os
import sys
from contextlib import contextmanager
from typing import Generator


@contextmanager
def suppress_output(
    suppress_stdout: bool = True,
    suppress_stderr: bool = True
) -> Generator[None, None, None]:
    """Redirect stdout and/or stderr to devnull.

    Use this when importing libraries that write debug output during import.
    Critical for TUI apps where stray output corrupts terminal state.

    Args:
        suppress_stdout: Redirect stdout to /dev/null
        suppress_stderr: Redirect stderr to /dev/null

    Example:
        with suppress_output():
            import litellm
            import langfuse
    """
    devnull = os.open(os.devnull, os.O_RDWR)
    old_stdout, old_stderr = None, None

    try:
        if suppress_stdout:
            old_stdout = os.dup(sys.stdout.fileno())
            os.dup2(devnull, sys.stdout.fileno())

        if suppress_stderr:
            old_stderr = os.dup(sys.stderr.fileno())
            os.dup2(devnull, sys.stderr.fileno())

        yield

    finally:
        if old_stdout is not None:
            os.dup2(old_stdout, sys.stdout.fileno())
            os.close(old_stdout)

        if old_stderr is not None:
            os.dup2(old_stderr, sys.stderr.fileno())
            os.close(old_stderr)

        os.close(devnull)
