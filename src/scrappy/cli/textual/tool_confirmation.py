"""
Tool confirmation handler for destructive operations.

Displays tool info and diff preview before prompting for Y/N/A confirmation.
Extracted from the old agent/ui.py and agent/action_executor.py code.
"""

import difflib
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

# Callback types matching the existing bridge interface
OutputCallback = Callable[[str], None]
ConfirmYNACallback = Callable[[str], str]  # Returns "y", "n", or "a"


class ToolConfirmationUIProtocol(Protocol):
    """Protocol for tool confirmation UI operations."""

    def output(self, content: str) -> None:
        """Output content to the UI."""
        ...

    def confirm_yna(self, question: str) -> str:
        """Prompt for Y/N/A confirmation. Returns 'y', 'n', or 'a'."""
        ...


class ToolConfirmationHandler:
    """
    Handles tool confirmation with preview display.

    Shows tool info and diff preview before prompting for confirmation.
    Ported from agent/action_executor.py and agent/ui.py.
    """

    # Tools that modify files and should show diff preview
    FILE_WRITE_TOOLS = frozenset({
        "write_file",
        "edit_file",
        "create_file",
        "patch_file",
    })

    def __init__(
        self,
        output_callback: OutputCallback,
        confirm_callback: ConfirmYNACallback,
        working_dir: str,
    ) -> None:
        """
        Initialize the confirmation handler.

        Args:
            output_callback: Function to output content to UI
            confirm_callback: Function to prompt Y/N/A confirmation
            working_dir: Working directory for resolving file paths
        """
        self._output = output_callback
        self._confirm = confirm_callback
        self._working_dir = working_dir
        self._allow_all = False

    def reset(self) -> None:
        """Reset allow_all state for a new run."""
        self._allow_all = False

    def confirm_tool(
        self,
        tool_name: str,
        description: str,
        args: dict[str, Any],
    ) -> bool:
        """
        Confirm a tool execution with preview.

        Shows tool info and diff preview (for file writes), then prompts
        for Y/N/A confirmation.

        Args:
            tool_name: Name of the tool
            description: Human-readable description (e.g., "Write to file.py")
            args: Tool arguments dict

        Returns:
            True if confirmed (y or a), False if denied (n)
        """
        # Skip if user already pressed 'a' (allow all) this run
        if self._allow_all:
            return True

        # Display tool info
        self._show_tool_info(tool_name, args)

        # Show diff preview for file-modifying tools
        if tool_name in self.FILE_WRITE_TOOLS:
            diff_lines = self._generate_diff_preview(args)
            path = self._get_file_path(args)
            self._show_diff_preview(path or "", diff_lines)

        # Prompt for confirmation
        response = self._confirm(f"{description}?")

        if response == "a":
            self._allow_all = True
            return True
        elif response == "y":
            return True
        else:
            return False

    def _show_tool_info(self, tool_name: str, args: dict[str, Any]) -> None:
        """Display tool call header."""
        key_param = self._extract_key_param(tool_name, args)

        if tool_name == "run_command":
            self._output(f"[dim]>[/dim] [yellow]{tool_name}[/yellow]: {key_param or '(no command)'}\n")
        elif key_param:
            self._output(f"[dim]>[/dim] [bold]{tool_name}[/bold]: {key_param}\n")
        else:
            self._output(f"[dim]>[/dim] [bold]{tool_name}[/bold]\n")

    def _generate_diff_preview(self, args: dict[str, Any]) -> list[str]:
        """
        Generate unified diff for write_file action.

        Ported from agent/action_executor.py._generate_diff_preview()

        Args:
            args: Tool arguments with path and content

        Returns:
            List of diff lines (empty for new files)
        """
        path = self._get_file_path(args)
        new_content = args.get("content", "")

        if not path:
            return []

        # Build full path
        if Path(path).is_absolute():
            file_path = Path(path)
        else:
            file_path = Path(self._working_dir) / path

        if not file_path.exists():
            # New file - no diff to show
            return []

        try:
            existing_content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Can't read existing file
            return []

        # Generate unified diff
        existing_lines = existing_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            existing_lines,
            new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm=""
        )

        return list(diff)

    def _show_diff_preview(
        self,
        path: str,
        diff_lines: list[str],
        max_lines: int = 30
    ) -> None:
        """
        Display diff preview before file write.

        Shows unified diff with colored additions/deletions.
        Always shown since it's critical for user to see what will change
        before approving.

        Ported from agent/ui.py.show_diff_preview()

        Args:
            path: File path being modified
            diff_lines: Lines from unified diff output
            max_lines: Maximum lines to show before truncating
        """
        if not diff_lines:
            self._output(f"  [green](new file)[/green]\n")
            return

        # Build diff output as single string to avoid extra spacing
        output_lines = []
        shown = 0
        for line in diff_lines:
            if shown >= max_lines:
                remaining = len(diff_lines) - shown
                output_lines.append(f"  [dim]... ({remaining} more lines)[/dim]")
                break

            # Strip trailing newlines
            line = line.rstrip("\n\r")

            # Skip diff headers (---, +++)
            if line.startswith("---") or line.startswith("+++"):
                continue
            if line.startswith("@@"):
                output_lines.append(f"  [cyan]{line}[/cyan]")
                shown += 1
                continue

            # Colorize based on diff type
            if line.startswith("+"):
                output_lines.append(f"  [green]{line}[/green]")
            elif line.startswith("-"):
                output_lines.append(f"  [red]{line}[/red]")
            else:
                output_lines.append(f"  [dim]{line}[/dim]")
            shown += 1

        # Output all at once
        if output_lines:
            self._output("\n".join(output_lines) + "\n")

    def _get_file_path(self, args: dict[str, Any]) -> Optional[str]:
        """Extract file path from tool arguments."""
        file_path = (
            args.get("file_path")
            or args.get("path")
            or args.get("filepath")
            or args.get("file")
        )
        return str(file_path) if file_path else None

    def _extract_key_param(self, tool_name: str, args: dict[str, Any]) -> str:
        """Extract the key parameter for display."""
        key_param_map = {
            "write_file": "path",
            "read_file": "path",
            "edit_file": "path",
            "create_file": "path",
            "patch_file": "path",
            "delete_file": "path",
            "run_command": "command",
        }

        param_name = key_param_map.get(tool_name)
        if not param_name or param_name not in args:
            return ""

        value = str(args[param_name])

        # Truncate long values
        if len(value) > 50:
            return value[:47] + "..."

        return value
