"""
Output formatting for agent tool results.

Provides injectable formatters to colorize and style output.
"""

from abc import ABC, abstractmethod
from typing import Protocol

try:
    import click
    HAS_CLICK = True
except ImportError:
    HAS_CLICK = False


class OutputFormatter(Protocol):
    """Protocol for output formatters."""

    def format(self, output: str, output_type: str = "default") -> str:
        """Format the output string."""
        ...


class NullFormatter:
    """Formatter that returns output unchanged."""

    def format(self, output: str, output_type: str = "default") -> str:
        """Return output unchanged."""
        return output


class GitOutputFormatter:
    """
    Colorizes git command output for better readability.

    Supports output types: log, diff, blame, show
    """

    def format(self, output: str, output_type: str = "log") -> str:
        """
        Add colors to git output for better readability.

        Args:
            output: Raw git command output
            output_type: Type of git output (log, diff, blame, show)

        Returns:
            Colorized output string (or unchanged if click not available)
        """
        if not HAS_CLICK:
            return output

        lines = output.split('\n')
        colored_lines = []

        for line in lines:
            colored_line = self._colorize_line(line, output_type)
            colored_lines.append(colored_line)

        return '\n'.join(colored_lines)

    def _colorize_line(self, line: str, output_type: str) -> str:
        """Colorize a single line based on output type."""
        if output_type == "log":
            return self._colorize_log_line(line)
        elif output_type == "diff":
            return self._colorize_diff_line(line)
        elif output_type == "blame":
            return self._colorize_blame_line(line)
        elif output_type == "show":
            return self._colorize_show_line(line)
        else:
            return line

    def _colorize_log_line(self, line: str) -> str:
        """Colorize git log output."""
        # Color commit hashes and decorations
        if line and len(line) > 7 and line[:7].replace(' ', '').isalnum():
            parts = line.split(' ', 1)
            if len(parts) >= 1:
                # Commit hash in yellow
                colored = click.style(parts[0], fg='yellow')
                if len(parts) > 1:
                    colored += ' ' + parts[1]
                return colored
        return line

    def _colorize_diff_line(self, line: str) -> str:
        """Colorize git diff output."""
        if line.startswith('+++') or line.startswith('---'):
            return click.style(line, fg='cyan', bold=True)
        elif line.startswith('+'):
            return click.style(line, fg='green')
        elif line.startswith('-'):
            return click.style(line, fg='red')
        elif line.startswith('@@'):
            return click.style(line, fg='cyan')
        elif line.startswith('diff --git'):
            return click.style(line, fg='bright_white', bold=True)
        return line

    def _colorize_blame_line(self, line: str) -> str:
        """Colorize git blame output."""
        if line and '^' in line or (len(line) > 8 and line[:8].replace(' ', '').isalnum()):
            parts = line.split(' ', 1)
            if len(parts) >= 1:
                colored = click.style(parts[0], fg='yellow')
                if len(parts) > 1:
                    colored += ' ' + parts[1]
                return colored
        return line

    def _colorize_show_line(self, line: str) -> str:
        """Colorize git show output."""
        if line.startswith('commit '):
            return click.style(line, fg='yellow', bold=True)
        elif line.startswith('Author:'):
            return click.style(line, fg='cyan')
        elif line.startswith('Date:'):
            return click.style(line, fg='cyan')
        elif line.startswith('=== COMMIT'):
            return click.style(line, fg='yellow', bold=True)
        elif line.startswith('Message:'):
            return click.style(line, fg='bright_white', bold=True)
        elif '|' in line and ('+' in line or '-' in line):
            # File stat lines
            return click.style(line, fg='cyan')
        elif line.startswith('+'):
            return click.style(line, fg='green')
        elif line.startswith('-'):
            return click.style(line, fg='red')
        return line
