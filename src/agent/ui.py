"""
Agent UI implementation.

Handles all user interaction and console output formatting for the agent.
Wraps CLIIOProtocol to provide agent-specific display operations.
"""

from typing import Optional, Dict, Any, TYPE_CHECKING
import json

if TYPE_CHECKING:
    from ..cli.io_interface import CLIIOProtocol

from .protocols import AgentUIProtocol


def safe_print(*args, **kwargs):
    """Safely handles Unicode encoding errors on Windows."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        text = ' '.join(str(arg) for arg in args)
        safe_text = text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        try:
            print(safe_text, **kwargs)
        except Exception:
            ascii_text = ''.join(c if ord(c) < 128 else '?' for c in text)
            print(ascii_text, **kwargs)
    except Exception:
        pass


class AgentUI:
    """
    Agent user interface implementation.

    Implements AgentUIProtocol by wrapping CLIIOProtocol and adding
    agent-specific formatting and Rich enhancements.

    Single Responsibility: Agent-specific UI operations
    Dependencies: CLIIOProtocol (injected)
    """

    def __init__(self, io: "CLIIOProtocol"):
        """
        Initialize agent UI.

        Args:
            io: CLI I/O interface (CLIIOProtocol)
        """
        self.io = io

    def show_thinking(self, text: str) -> None:
        """Display agent thinking/reasoning."""
        if not text or not text.strip():
            return

        # Use Rich panel if available
        if hasattr(self.io, 'panel'):
            self.io.panel(text, title="Thinking", border_style="blue")
        else:
            self.io.secho(f"\n[Thinking] {text}", fg="blue")

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
            self.io.secho(f"\nTool: {tool_name}", fg="cyan", bold=True)
            self.io.echo(f"Parameters: {json.dumps(params, indent=2)}")

    def show_command(self, command: str) -> None:
        """Display shell command being executed."""
        # Use Rich syntax highlighting if available
        if hasattr(self.io, 'syntax'):
            self.io.syntax(command, language="shell")
        else:
            self.io.secho(f"$ {command}", fg="yellow")

    def show_error(self, message: str) -> None:
        """Display error message."""
        if hasattr(self.io, 'panel'):
            self.io.panel(message, title="Error", border_style="red")
        else:
            self.io.secho(f"\nError: {message}", fg="red")

    def show_result(
        self,
        result: str,
        title: str = "Result",
        is_error: bool = False
    ) -> None:
        """Display action result."""
        # Truncate very long output for display
        display_result = result[:2000] + "... [truncated]" if len(result) > 2000 else result

        color = "red" if is_error else "green"

        if hasattr(self.io, 'panel'):
            self.io.panel(display_result, title=title, border_style=color)
        else:
            self.io.secho(f"\n{title}: {display_result}", fg=color)

    def show_warning(self, message: str) -> None:
        """Display warning message."""
        if hasattr(self.io, 'panel'):
            self.io.panel(message, title="Warning", border_style="yellow")
        else:
            self.io.secho(f"\nWarning: {message}", fg="yellow")

    def show_progress(self, message: str) -> None:
        """Display progress/status message."""
        self.io.secho(message, fg="cyan")

    def show_provider_status(
        self,
        provider: str,
        message: str,
        color: str = "cyan"
    ) -> None:
        """Display provider-specific status."""
        self.io.secho(f"[{provider}] {message}", fg=color)

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
