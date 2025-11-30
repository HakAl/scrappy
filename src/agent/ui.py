"""
Agent UI implementation.

Handles all user interaction and console output formatting for the agent.
Wraps CLIIOProtocol to provide agent-specific display operations.
"""

from typing import Optional, Dict, Any, TYPE_CHECKING
import json

if TYPE_CHECKING:
    from ..protocols.io import CLIIOProtocol
    from ..infrastructure.theme import ThemeProtocol

from .protocols import AgentUIProtocol
from ..infrastructure.theme import DEFAULT_THEME


class AgentUI:
    """
    Agent user interface implementation.

    Implements AgentUIProtocol by wrapping CLIIOProtocol and adding
    agent-specific formatting and Rich enhancements.

    Single Responsibility: Agent-specific UI operations
    Dependencies: CLIIOProtocol (injected), ThemeProtocol (optional)
    """

    def __init__(
        self,
        io: "CLIIOProtocol",
        theme: Optional["ThemeProtocol"] = None,
    ):
        """
        Initialize agent UI.

        Args:
            io: CLI I/O interface (CLIIOProtocol)
            theme: Optional theme for color styling. Defaults to DEFAULT_THEME.
        """
        self.io = io
        self._theme = theme or DEFAULT_THEME

    def show_thinking(self, text: str) -> None:
        """Display agent thinking/reasoning."""
        if not text or not text.strip():
            return

        # Use Rich panel if available
        if hasattr(self.io, 'panel'):
            self.io.panel(text, title="Thinking", border_style=self._theme.info)
        else:
            self.io.secho(f"\n[Thinking] {text}", fg=self._theme.info)

    def show_tool_request(self, tool_name: str, params: Dict[str, Any]) -> None:
        """Display tool invocation request."""
        # Use Rich table if available
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
        # Truncate very long output for display
        display_result = result[:2000] + "... [truncated]" if len(result) > 2000 else result

        color = self._theme.error if is_error else self._theme.success

        if hasattr(self.io, 'panel'):
            self.io.panel(display_result, title=title, border_style=color)
        else:
            self.io.secho(f"\n{title}: {display_result}", fg=color)

    def show_warning(self, message: str) -> None:
        """Display warning message."""
        if hasattr(self.io, 'panel'):
            self.io.panel(message, title="Warning", border_style=self._theme.warning)
        else:
            self.io.secho(f"\nWarning: {message}", fg=self._theme.warning)

    def show_progress(self, message: str) -> None:
        """Display progress/status message."""
        self.io.secho(message, fg=self._theme.primary)

    def show_provider_status(
        self,
        provider: str,
        message: str,
        color: Optional[str] = None
    ) -> None:
        """Display provider-specific status."""
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
