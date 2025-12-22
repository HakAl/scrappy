"""
Agent UI implementation.

Handles all user interaction and console output formatting for the agent.
Wraps CLIIOProtocol to provide agent-specific display operations.
"""

from typing import Optional, Dict, Any, List, Tuple, Callable

import json

from ..protocols.io import CLIIOProtocol
from ..infrastructure.theme import ThemeProtocol, DEFAULT_THEME


class AgentUI:
    """
    Agent user interface implementation.

    Implements AgentUIProtocol by wrapping CLIIOProtocol and adding
    agent-specific formatting and Rich enhancements.

    Single Responsibility: Agent-specific UI operations
    Dependencies: CLIIOProtocol (injected), ThemeProtocol (optional)

    Supports two output modes:
    - Compact (default): One-line summaries for each action
    - Verbose: Full output with thinking, params, results
    """

    def __init__(
        self,
        io: CLIIOProtocol,
        theme: Optional[ThemeProtocol] = None,
        verbose: bool = False,
        on_tasks_updated: Optional[Callable[[list], None]] = None,
    ):
        """
        Initialize agent UI.

        Args:
            io: CLI I/O interface (CLIIOProtocol)
            theme: Optional theme for color styling. Defaults to DEFAULT_THEME.
            verbose: If True, show full output. If False, compact mode.
            on_tasks_updated: Optional callback when tasks are updated.
        """
        self.io = io
        self._theme = theme or DEFAULT_THEME
        self.verbose = verbose
        self.current_step = 0
        self._on_tasks_updated = on_tasks_updated

    def show_thinking(self, text: str) -> None:
        """Display agent thinking/reasoning."""
        if not text or not text.strip():
            return

        # Skip thinking in compact mode
        if not self.verbose:
            return

        # Use Rich panel if available
        if hasattr(self.io, 'panel'):
            self.io.panel(text, title="Thinking", border_style=self._theme.info)
        else:
            self.io.secho(f"\n[Thinking] {text}", fg=self._theme.info)

    def show_tool_request(self, tool_name: str, params: Dict[str, Any]) -> None:
        """Display tool invocation request."""
        self.current_step += 1

        # Compact mode: one-line summary
        if not self.verbose:
            # Special handling for task tool: show command + description
            if tool_name == 'task' and params.get('command') and params.get('description'):
                cmd = params['command']
                desc = params['description']
                if len(desc) > 45:
                    desc = desc[:42] + "..."
                target = f"{cmd} \"{desc}\""
            else:
                # Extract most relevant parameter for display
                target = (
                    params.get('file_path') or
                    params.get('path') or
                    params.get('description') or
                    params.get('command') or
                    params.get('query') or
                    params.get('pattern') or
                    (str(list(params.values())[0]) if params else '')
                )
                # Truncate long targets
                if len(target) > 50:
                    target = target[:47] + "..."
            self.io.secho(f"[Step {self.current_step}] {tool_name}: {target}", fg=self._theme.primary)
            return

        # Verbose mode: full table
        if hasattr(self.io, 'table'):
            headers = ["Property", "Value"]
            rows = [["Tool", tool_name]]
            for key, value in params.items():
                str_value = str(value)
                if len(str_value) > 100:
                    str_value = str_value[:100] + "..."
                rows.append([key, str_value])
            self.io.table(headers, rows, title="Tool Request")
        else:
            self.io.secho(f"\nTool: {tool_name}", fg=self._theme.primary, bold=True)
            self.io.echo(f"Parameters: {json.dumps(params, indent=2)}")

    def show_diff_preview(
        self,
        path: str,
        diff_lines: List[str],
        max_lines: int = 30
    ) -> None:
        """Display diff preview before file write.

        Shows unified diff with colored additions/deletions.
        Always shown (both compact and verbose modes) since it's critical
        for user to see what will change before approving.

        Args:
            path: File path being modified
            diff_lines: Lines from unified diff output
            max_lines: Maximum lines to show before truncating
        """
        if not diff_lines:
            self.io.secho(f"    [new file] {path}", fg=self._theme.info)
            return

        # Show header
        self.io.secho(f"    Changes to {path}:", fg=self._theme.info)

        # Colorize and display diff lines
        shown = 0
        for line in diff_lines:
            if shown >= max_lines:
                remaining = len(diff_lines) - shown
                self.io.secho(f"    ... ({remaining} more lines)", fg=self._theme.text_muted)
                break

            # Strip trailing newlines to avoid double-spacing
            line = line.rstrip('\n\r')

            # Skip diff headers (---, +++, @@) in compact display
            if line.startswith('---') or line.startswith('+++'):
                continue
            if line.startswith('@@'):
                # Show hunk header in muted color
                self.io.secho(f"    {line}", fg=self._theme.text_muted)
                shown += 1
                continue

            # Colorize based on diff type
            if line.startswith('+'):
                self.io.secho(f"    {line}", fg=self._theme.success)
            elif line.startswith('-'):
                self.io.secho(f"    {line}", fg=self._theme.error)
            else:
                # Context lines
                self.io.secho(f"    {line}", fg=self._theme.text_muted)
            shown += 1

    def show_command(self, command: str) -> None:
        """Display shell command being executed."""
        # Use Rich syntax highlighting if available
        if hasattr(self.io, 'syntax'):
            self.io.syntax(command, language="shell")
        else:
            self.io.secho(f"$ {command}", fg=self._theme.accent)

    def show_error(self, message: str) -> None:
        """Display error message."""
        if hasattr(self.io, 'panel'):
            self.io.panel(message, title="Error", border_style=self._theme.error)
        else:
            self.io.secho(f"\nError: {message}", fg=self._theme.error)

    def show_result(
        self,
        result: str,
        title: str = "Result",
        is_error: bool = False
    ) -> None:
        """Display action result."""
        color = self._theme.error if is_error else self._theme.success

        # Compact mode: one-line summary (always show errors)
        if not self.verbose and not is_error:
            # Count lines for summary
            lines = result.count('\n') + 1 if result else 0
            muted = getattr(self._theme, 'text_muted', 'dim')
            if lines > 1:
                self.io.secho(f"    ... done ({lines} lines)", fg=muted)
            else:
                # Short result - show inline
                short = result[:40] + "..." if len(result) > 40 else result
                self.io.secho(f"    ... {short}", fg=muted)
            return

        # Verbose mode or error: full output
        display_result = result[:2000] + "... [truncated]" if len(result) > 2000 else result

        if hasattr(self.io, 'panel'):
            self.io.panel(display_result, title=title, border_style=color)
        else:
            self.io.secho(f"\n{title}: {display_result}", fg=color)

    def show_warning(self, message: str) -> None:
        """Display warning message.

        In compact mode, shows one-line warning. In verbose mode, shows panel.
        """
        if not self.verbose:
            # Compact: one-line warning
            short = message[:70] + "..." if len(message) > 70 else message
            self.io.secho(f"    [!] {short}", fg=self._theme.warning)
            return

        # Verbose: full panel
        if hasattr(self.io, 'panel'):
            self.io.panel(message, title="Warning", border_style=self._theme.warning)
        else:
            self.io.secho(f"\nWarning: {message}", fg=self._theme.warning)

    def show_progress(self, message: str) -> None:
        """Display progress/status message.

        In compact mode, only shows significant progress messages.
        """
        # Skip noise messages in compact mode
        if not self.verbose:
            noise_phrases = ["Auto-approved", "safe operation", "Executing:"]
            if any(phrase in message for phrase in noise_phrases):
                return
        self.io.secho(message, fg=self._theme.primary)

    def show_provider_status(
        self,
        provider: str,
        message: str,
        color: Optional[str] = None
    ) -> None:
        """Display provider-specific status.

        In compact mode, skips repetitive status messages like "Thinking...".
        """
        # Skip verbose status messages in compact mode
        if not self.verbose:
            skip_phrases = [
                "Thinking...",
                "Analyzing task",
                "Response received",
            ]
            if any(phrase in message for phrase in skip_phrases):
                return
        fg_color = color if color else self._theme.primary
        self.io.secho(f"[{provider}] {message}", fg=fg_color)

    def show_rule(self, title: Optional[str] = None) -> None:
        """Display horizontal rule separator."""
        if hasattr(self.io, 'rule'):
            self.io.rule(title)
        else:
            self.io.echo(f"\n{'='*60}")
            if title:
                self.io.echo(f" {title} ")

    def prompt_confirm(
        self,
        message: str = "Allow?",
        default: bool = False
    ) -> bool:
        """Prompt user for confirmation."""
        return self.io.confirm(message, default=default)

    def confirm(self, message: str, default: bool = True) -> bool:
        """Prompt user for yes/no confirmation.

        Args:
            message: Question to ask user
            default: Default value if user just presses enter

        Returns:
            True if user confirms, False otherwise
        """
        return self.io.confirm(message, default=default)

    def show_info(self, message: str) -> None:
        """Display informational message.

        Args:
            message: Message to display
        """
        self.io.secho(f"  {message}", fg=self._theme.info)

    def reset_step_counter(self) -> None:
        """Reset step counter for new task."""
        self.current_step = 0

    def show_completion(self, result: str, success: bool = True) -> None:
        """Display task completion message.

        In compact mode, shows a one-line summary.
        In verbose mode, shows full result panel.

        Args:
            result: Completion message/result text
            success: Whether the task completed successfully
        """
        color = self._theme.success if success else self._theme.error
        status = "Done" if success else "Failed"

        if not self.verbose:
            # Compact: one line with truncated result (no step number - completion isn't a step)
            short = result[:70] + "..." if len(result) > 70 else result
            self.io.secho(f"{status}: {short}", fg=color)
            return

        # Verbose: full panel
        if hasattr(self.io, 'panel'):
            self.io.panel(result, title=status, border_style=color)
        else:
            self.io.secho(f"\n{status}: {result}", fg=color)

    def notify_tasks_updated(self, tasks: list) -> None:
        """Notify UI that agent tasks have been updated.

        Called when the task tool modifies tasks (add, update, delete, clear).
        Routes to TUI via output_sink if available, or invokes callback if set.

        Args:
            tasks: Current list of Task objects
        """
        # Try TUI output sink first
        output_sink = getattr(self.io, "output_sink", None)
        if output_sink is not None and hasattr(output_sink, "post_tasks_updated"):
            output_sink.post_tasks_updated(tasks)
            return

        # Fall back to callback if provided
        if self._on_tasks_updated:
            self._on_tasks_updated(tasks)

    def prompt_checkpoint(self, iteration: int, tools_count: int) -> str:
        """Prompt user at safety checkpoint with multiple options.

        Displays a checkpoint prompt with options to continue, create git
        checkpoint, enable allow-all mode, or stop.

        Args:
            iteration: Current iteration number
            tools_count: Number of tools executed so far

        Returns:
            User's choice: 'c' (continue), 'g' (git checkpoint),
            'a' (allow all), 's' (stop)
        """
        # Show checkpoint banner
        self.io.echo("")
        self.io.secho("=" * 60, fg=self._theme.warning)
        self.io.secho(
            f"  Safety Checkpoint - {iteration} iterations, {tools_count} actions",
            fg=self._theme.warning,
            bold=True
        )
        self.io.secho("=" * 60, fg=self._theme.warning)
        self.io.echo("")
        self.io.secho("  [c] Continue        - keep going", fg=self._theme.info)
        self.io.secho("  [g] Git checkpoint  - save restore point, then continue", fg=self._theme.info)
        self.io.secho("  [a] Allow all       - skip confirmations for remaining actions", fg=self._theme.info)
        self.io.secho("  [s] Stop            - end agent run", fg=self._theme.info)
        self.io.echo("")

        # Get user choice
        while True:
            choice = self.io.prompt("Choice [c/g/a/s]", default="c").lower().strip()
            if choice in ('c', 'g', 'a', 's'):
                return choice
            self.io.secho("Invalid choice. Please enter c, g, a, or s.", fg=self._theme.error)

    def confirm_batch(
        self,
        actions: List[Tuple[str, Dict[str, Any]]],
    ) -> bool:
        """Display batch of actions in activity bar and prompt for approval.

        Used when LLM returns multiple tool calls. Shows a compact summary
        of all actions and asks for batch approval.

        Args:
            actions: List of (tool_name, parameters) tuples

        Returns:
            True if user approves all actions, False if denied
        """
        # Build compact summaries for each action
        summaries = []
        for tool_name, params in actions:
            # Extract most relevant parameter (same logic as show_tool_request)
            target = (
                params.get('file_path') or
                params.get('path') or
                params.get('description') or
                params.get('command') or
                params.get('query') or
                params.get('pattern') or
                (str(list(params.values())[0]) if params else '')
            )
            # Truncate long targets
            if len(target) > 30:
                target = target[:27] + "..."
            summaries.append(f"{tool_name}: {target}")

        # Format prompt message with numbered actions
        actions_preview = " ".join(f"[{i}] {s}" for i, s in enumerate(summaries, 1))
        prompt_msg = f"Allow {len(actions)} actions? {actions_preview}"

        # Use io.confirm which routes to activity bar in TUI mode
        return self.io.confirm(prompt_msg, default=False)
