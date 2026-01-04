"""
Git diff utilities for displaying file changes.

Simple, focused module for getting and formatting git diffs.
Used by both AgentUI and LangGraphBridge.
"""

import subprocess
from pathlib import Path
from typing import Optional

from scrappy.infrastructure.theme import GIT_COLORS


def get_file_diff(file_path: str, working_dir: str) -> Optional[str]:
    """
    Get git diff for a file.

    Tries unstaged changes first, then staged changes, then shows
    new file content as pseudo-diff for untracked files.

    Args:
        file_path: Path to the file (relative or absolute)
        working_dir: Working directory for git commands

    Returns:
        Diff string, or None if no diff available
    """
    try:
        # Try unstaged changes
        result = subprocess.run(
            ["git", "diff", "--no-color", "--", file_path],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()

        # Try staged changes
        result = subprocess.run(
            ["git", "diff", "HEAD", "--no-color", "--", file_path],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()

        # Check for untracked file
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", file_path],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip().startswith("??"):
            return _format_new_file(file_path, working_dir)

        return None

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _format_new_file(file_path: str, working_dir: str) -> Optional[str]:
    """Format new file content as additions."""
    try:
        full_path = Path(working_dir) / file_path
        if not full_path.exists():
            return None
        content = full_path.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")
        return "\n".join(f"+{line}" for line in lines)
    except (OSError, IOError):
        return None


def format_diff_lines(diff: str, max_lines: int = 20, colorize: bool = True) -> list[str]:
    """
    Extract and format diff content lines.

    Filters out headers, keeps +/- lines and context.
    Optionally adds Rich markup for colors using theme GitColors.

    Args:
        diff: Raw diff string
        max_lines: Maximum lines to return
        colorize: Add Rich color markup (default True)

    Returns:
        List of formatted diff lines
    """
    if not diff:
        return []

    content_lines = []
    for line in diff.split("\n"):
        # Skip headers
        if line.startswith(("diff --git", "index ", "--- ", "+++ ")):
            continue
        # Keep hunk headers, +/- lines, and context
        if line.startswith("@@"):
            formatted = f"[{GIT_COLORS.header}]{line}[/{GIT_COLORS.header}]" if colorize else line
            content_lines.append(formatted)
        elif line.startswith("+"):
            formatted = f"[{GIT_COLORS.add}]{line}[/{GIT_COLORS.add}]" if colorize else line
            content_lines.append(formatted)
        elif line.startswith("-"):
            formatted = f"[{GIT_COLORS.remove}]{line}[/{GIT_COLORS.remove}]" if colorize else line
            content_lines.append(formatted)
        elif line.startswith(" "):
            content_lines.append(line)

    # Truncate if needed
    if len(content_lines) > max_lines:
        remaining = len(content_lines) - max_lines
        truncation_msg = f"[dim]... ({remaining} more lines)[/dim]" if colorize else f"... ({remaining} more lines)"
        return content_lines[:max_lines] + [truncation_msg]

    return content_lines
