"""
Git operation tools for the code agent.

Provides git log, diff, blame, show, and recent changes operations.
"""

import subprocess
from typing import Optional

from .base import Tool, ToolParameter, ToolResult, ToolContext
from ..formatters import OutputFormatter, GitOutputFormatter, NullFormatter


class GitTool(Tool):
    """Base class for git tools with common functionality."""

    def __init__(self, formatter: Optional[OutputFormatter] = None):
        """
        Initialize git tool with optional formatter.

        Args:
            formatter: OutputFormatter for colorizing output (default: GitOutputFormatter)
        """
        self._formatter = formatter or GitOutputFormatter()

    def _run_git_command(
        self,
        context: ToolContext,
        args: list[str],
        timeout: Optional[int] = None
    ) -> tuple[bool, str]:
        """
        Run a git command and return result.

        Args:
            context: Tool execution context
            args: Git command arguments (e.g., ['log', '-10'])
            timeout: Command timeout in seconds

        Returns:
            Tuple of (success, output_or_error)
        """
        if timeout is None:
            timeout = context.config.git_timeout if context.config else 30

        try:
            result = subprocess.run(
                ['git'] + args,
                cwd=context.project_root,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            if result.returncode != 0:
                return False, result.stderr.strip()

            return True, result.stdout.strip()
        except subprocess.TimeoutExpired:
            return False, f"Command timed out ({timeout}s limit)"
        except Exception as e:
            return False, str(e)


class GitLogTool(GitTool):
    """View recent git commits."""

    @property
    def name(self) -> str:
        return "git_log"

    @property
    def description(self) -> str:
        return "View recent commits (optionally for specific file)"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("n", int, "Number of commits to show", required=False, default=10),
            ToolParameter("file", str, "Specific file to show history for", required=False, default=None)
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        n = kwargs.get("n", 10)
        file = kwargs.get("file", None)

        args = ['log', f'-{n}', '--oneline', '--decorate']

        if file:
            if not context.is_safe_path(file):
                return ToolResult(False, "", f"Path '{file}' is outside project directory")
            args.extend(['--', file])

        success, output = self._run_git_command(context, args)

        if not success:
            return ToolResult(False, "", f"Git error: {output}")

        if not output:
            return ToolResult(True, "No commits found")

        # Store in working memory
        op_desc = f"git log -{n}" + (f" {file}" if file else "")
        context.remember_git_operation(op_desc, output)

        # Format output
        formatted = self._formatter.format(output, "log")

        return ToolResult(
            True,
            formatted,
            metadata={"commits": n, "file": file}
        )


class GitDiffTool(GitTool):
    """Show git diff (unstaged changes, or vs a ref)."""

    @property
    def name(self) -> str:
        return "git_diff"

    @property
    def description(self) -> str:
        return "Show changes (unstaged, or vs ref like HEAD~1)"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("ref", str, "Git reference to diff against", required=False, default=None),
            ToolParameter("file", str, "Specific file to diff", required=False, default=None)
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        ref = kwargs.get("ref", None)
        file = kwargs.get("file", None)

        args = ['diff']
        if ref:
            args.append(ref)
        if file:
            if not context.is_safe_path(file):
                return ToolResult(False, "", f"Path '{file}' is outside project directory")
            args.extend(['--', file])

        success, output = self._run_git_command(context, args)

        if not success:
            return ToolResult(False, "", f"Git error: {output}")

        if not output:
            return ToolResult(True, "No changes found")

        # Truncate if too long
        max_size = context.config.max_git_diff_size if context.config else 20000
        truncated = len(output) > max_size
        if truncated:
            output = output[:max_size] + "\n... [truncated]"

        # Store in working memory
        op_desc = "git diff" + (f" {ref}" if ref else "") + (f" {file}" if file else "")
        context.remember_git_operation(op_desc, output[:500])

        # Format output
        formatted = self._formatter.format(output, "diff")

        return ToolResult(
            True,
            formatted,
            metadata={"ref": ref, "file": file, "truncated": truncated}
        )


class GitBlameTool(GitTool):
    """Show git blame for a file."""

    @property
    def name(self) -> str:
        return "git_blame"

    @property
    def description(self) -> str:
        return "Show who changed each line (e.g., lines='10,20')"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("file", str, "File to blame", required=True),
            ToolParameter("lines", str, "Line range (e.g., '10,20')", required=False, default=None)
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        file = kwargs["file"]
        lines = kwargs.get("lines", None)

        if not context.is_safe_path(file):
            return ToolResult(False, "", f"Path '{file}' is outside project directory")

        args = ['blame', '--date=short']

        if lines:
            args.extend(['-L', lines])

        args.append(file)

        success, output = self._run_git_command(context, args)

        if not success:
            return ToolResult(False, "", f"Git error: {output}")

        if not output:
            return ToolResult(True, "No blame information found")

        # Truncate if too long
        max_size = context.config.max_git_blame_size if context.config else 20000
        truncated = len(output) > max_size
        if truncated:
            output = output[:max_size] + "\n... [truncated]"

        # Format output
        formatted = self._formatter.format(output, "blame")

        return ToolResult(
            True,
            formatted,
            metadata={"file": file, "lines": lines, "truncated": truncated}
        )


class GitShowTool(GitTool):
    """Show details of a specific commit."""

    @property
    def name(self) -> str:
        return "git_show"

    @property
    def description(self) -> str:
        return "Show details of a specific commit"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("commit", str, "Commit hash or reference", required=True)
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        commit = kwargs["commit"]

        # Basic validation of commit reference
        if not commit.replace('-', '').replace('^', '').replace('~', '').replace('HEAD', '').isalnum():
            if commit not in ['HEAD', 'HEAD~1', 'HEAD~2', 'HEAD^']:
                return ToolResult(False, "", f"Invalid commit reference '{commit}'")

        args = ['show', '--stat', commit]

        success, output = self._run_git_command(context, args)

        if not success:
            return ToolResult(False, "", f"Git error: {output}")

        if not output:
            return ToolResult(True, "No commit information found")

        # Truncate if too long
        max_size = context.config.max_git_show_size if context.config else 20000
        truncated = len(output) > max_size
        if truncated:
            output = output[:max_size] + "\n... [truncated]"

        # Format output
        formatted = self._formatter.format(output, "show")

        return ToolResult(
            True,
            formatted,
            metadata={"commit": commit, "truncated": truncated}
        )


class GitRecentChangesTool(GitTool):
    """Show content of last N commits with full diffs."""

    @property
    def name(self) -> str:
        return "git_recent_changes"

    @property
    def description(self) -> str:
        return "Show content of last N commits with full diffs"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("n", int, "Number of commits to show", required=False, default=3)
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        n = kwargs.get("n", 3)

        # Limit to reasonable number
        max_commits = context.config.max_recent_commits if context.config else 10
        n = min(n, max_commits)

        args = [
            'log',
            f'-{n}',
            '--patch',
            '--stat',
            '--pretty=format:=== COMMIT %h ===\nAuthor: %an\nDate: %ad\nMessage: %s\n'
        ]

        # Use longer timeout for diffs
        timeout = context.config.git_diff_timeout if context.config else 60

        success, output = self._run_git_command(context, args, timeout=timeout)

        if not success:
            return ToolResult(False, "", f"Git error: {output}")

        if not output:
            return ToolResult(True, "No recent changes found")

        # Truncate if too long
        max_size = context.config.max_recent_changes_size if context.config else 50000
        truncated = len(output) > max_size
        if truncated:
            output = output[:max_size] + f"\n\n... [truncated - showing first {max_size} chars]"

        # Format output
        formatted = self._formatter.format(output, "show")

        return ToolResult(
            True,
            formatted,
            metadata={"commits": n, "truncated": truncated}
        )
