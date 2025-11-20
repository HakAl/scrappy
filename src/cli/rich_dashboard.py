"""Rich dashboard component for live CLI display.

Provides a dynamic dashboard layout with panels for:
- Agent state (Scanning, Thinking, Executing)
- Thought process (LLM reasoning)
- Terminal output (command output)
- Context info (active files, tokens)

This module implements DashboardProtocol for live agent visualization.
"""

from typing import List, Optional
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from io import StringIO


class RichDashboard:
    """Live dashboard for displaying agent activity.

    Implements DashboardProtocol for protocol-based dependency injection
    and testing. Provides real-time visualization of agent operations
    across four panels: agent state, thought process, terminal output,
    and context tracking.

    The dashboard is designed for use with Rich.Live for dynamic updates
    during long-running agent operations.
    """

    VALID_STATES = {"idle", "thinking", "executing", "scanning"}
    MAX_TERMINAL_LINES = 100

    def __init__(self, console: Optional[Console] = None):
        """Initialize dashboard with optional custom console.

        Args:
            console: Rich Console instance. Creates default if not provided.
        """
        self.console = console if console is not None else Console()
        self._state = "idle"
        self._state_message = ""

        # Panel content storage
        self._agent_state_content = ""
        self._thought_process_content = ""
        self._terminal_content = ""
        self._context_files: List[str] = []
        self._context_tokens = 0

        # Panel titles
        self._panel_titles = {
            "agent_state": "Agent State",
            "thought_process": "Thought Process",
            "terminal": "Terminal",
            "context": "Context",
        }

        # Panel styles based on state
        self._state_styles = {
            "idle": "dim",
            "thinking": "yellow",
            "executing": "green",
            "scanning": "cyan",
        }

        # Create the layout
        self._layout = self._create_layout()

    def _create_layout(self) -> Layout:
        """Create the dashboard layout structure."""
        layout = Layout(name="root")

        # Split into upper and lower sections
        layout.split_column(
            Layout(name="upper", ratio=2),
            Layout(name="lower", ratio=1),
        )

        # Upper section: agent state and thought process
        layout["upper"].split_row(
            Layout(name="agent_state", ratio=1),
            Layout(name="thought_process", ratio=2),
        )

        # Lower section: terminal and context
        layout["lower"].split_row(
            Layout(name="terminal", ratio=2),
            Layout(name="context", ratio=1),
        )

        return layout

    def get_layout(self) -> Layout:
        """Get the dashboard layout."""
        return self._layout

    def get_panel_names(self) -> List[str]:
        """Get list of all panel names."""
        return list(self._panel_titles.keys())

    def get_state(self) -> str:
        """Get current dashboard state."""
        return self._state

    def set_state(self, state: str, message: str = "") -> None:
        """Set dashboard state with optional message.

        Args:
            state: One of VALID_STATES
            message: Optional custom message to display

        Raises:
            ValueError: If state is not valid
        """
        if state not in self.VALID_STATES:
            raise ValueError(f"Invalid state: {state}. Must be one of {self.VALID_STATES}")

        self._state = state
        self._state_message = message

        # Auto-update agent state panel
        if message:
            self._agent_state_content = message
        else:
            self._agent_state_content = state.capitalize()

    def get_panel_title(self, panel_name: str) -> str:
        """Get title for a specific panel."""
        return self._panel_titles.get(panel_name, "")

    def get_panel_content(self, panel_name: str) -> str:
        """Get current content of a panel."""
        if panel_name == "agent_state":
            return self._agent_state_content
        elif panel_name == "thought_process":
            return self._thought_process_content
        elif panel_name == "terminal":
            return self._terminal_content
        elif panel_name == "context":
            return self._format_context_content()
        return ""

    def get_panel_style(self, panel_name: str) -> str:
        """Get current style for a panel based on state."""
        if panel_name == "agent_state":
            return self._state_styles.get(self._state, "dim")
        return "dim"

    def _format_context_content(self) -> str:
        """Format context panel content."""
        lines = []

        if self._context_files:
            lines.append("Active Files:")
            for f in self._context_files:
                lines.append(f"  {f}")

        lines.append(f"\nTokens: {self._context_tokens:,}")

        return "\n".join(lines)

    def update_agent_state(self, content: str) -> None:
        """Update agent state panel content."""
        self._agent_state_content = content

    def update_thought_process(self, content: str) -> None:
        """Update thought process panel content (replaces existing)."""
        self._thought_process_content = content

    def update_terminal(self, content: str) -> None:
        """Update terminal panel content (replaces existing)."""
        self._terminal_content = content
        self._enforce_terminal_limit()

    def update_context(self, active_files: List[str], tokens_used: int) -> None:
        """Update context panel with files and token count."""
        self._context_files = active_files
        self._context_tokens = tokens_used

    def append_terminal(self, content: str) -> None:
        """Append content to terminal, preserving history."""
        if self._terminal_content:
            self._terminal_content += "\n" + content
        else:
            self._terminal_content = content
        self._enforce_terminal_limit()

    def _enforce_terminal_limit(self) -> None:
        """Ensure terminal content doesn't exceed max lines."""
        lines = self._terminal_content.split('\n')
        if len(lines) > self.MAX_TERMINAL_LINES:
            # Keep only the most recent lines
            lines = lines[-self.MAX_TERMINAL_LINES:]
            self._terminal_content = '\n'.join(lines)

    def append_thought(self, content: str) -> None:
        """Append content to thought process panel."""
        if self._thought_process_content:
            self._thought_process_content += "\n" + content
        else:
            self._thought_process_content = content

    def clear_terminal(self) -> None:
        """Clear terminal output."""
        self._terminal_content = ""

    def clear_thought_process(self) -> None:
        """Clear thought process content."""
        self._thought_process_content = ""

    def capture_output(self, content: str, stream: str = "stdout") -> None:
        """Capture output from stdout or stderr.

        Args:
            content: Output content to capture
            stream: 'stdout' or 'stderr'
        """
        if stream == "stderr":
            content = f"[stderr] {content}"
        self.append_terminal(content)

    def capture_command(self, command: str, output: str) -> None:
        """Capture a command and its output.

        Args:
            command: The command that was run
            output: The command's output
        """
        self.append_terminal(f"$ {command}")
        if output:
            self.append_terminal(output)

    def update_active_files(self, files: List[str]) -> None:
        """Update only the active files list, preserving tokens."""
        self._context_files = files

    def update_tokens(self, tokens: int) -> None:
        """Update only the token count, preserving files."""
        self._context_tokens = tokens

    def render_to_string(self) -> str:
        """Render the dashboard to a string for testing."""
        # Create panels for each section
        self._update_layout_panels()

        # Render to string using a string buffer
        string_io = StringIO()
        temp_console = Console(file=string_io, force_terminal=True, width=120)
        temp_console.print(self._layout)

        return string_io.getvalue()

    def _update_layout_panels(self) -> None:
        """Update layout with current panel contents."""
        self._layout["agent_state"].update(
            Panel(
                self._agent_state_content or "Idle",
                title=self._panel_titles["agent_state"],
                border_style=self.get_panel_style("agent_state"),
            )
        )

        self._layout["thought_process"].update(
            Panel(
                self._thought_process_content or "",
                title=self._panel_titles["thought_process"],
                border_style="blue",
            )
        )

        self._layout["terminal"].update(
            Panel(
                self._terminal_content or "",
                title=self._panel_titles["terminal"],
                border_style="white",
            )
        )

        self._layout["context"].update(
            Panel(
                self._format_context_content(),
                title=self._panel_titles["context"],
                border_style="magenta",
            )
        )

    def get_renderable(self) -> Layout:
        """Get renderable for use with Rich Live display."""
        self._update_layout_panels()
        return self._layout

    def reset(self) -> None:
        """Reset dashboard to initial state."""
        self._state = "idle"
        self._state_message = ""
        self._agent_state_content = ""
        self._thought_process_content = ""
        self._terminal_content = ""
        self._context_files = []
        self._context_tokens = 0
