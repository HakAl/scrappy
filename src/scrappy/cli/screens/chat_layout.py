"""Reusable chat layout widget for Scrappy TUI screens."""

from typing import Any, Optional
import logging

from textual.widget import Widget
from textual.app import ComposeResult
from textual.widgets import TextArea, Label
from textual.containers import Container

from ..widgets import SelectableLog, TaskProgressWidget
from ..textual import StatusBar, ActivityIndicator

logger = logging.getLogger(__name__)


class ChatLayout(Widget):
    """Reusable chat layout with output area, input field, and optional status bar.

    Provides:
    - Scrollable output area (SelectableLog - supports text selection)
    - Fixed input area at bottom (TextArea with prompt)
    - Optional status bar

    Both MainAppScreen and SetupWizardScreen can use this component,
    ensuring consistent layout and enabling direct output writing.
    """

    def __init__(
        self,
        show_status_bar: bool = True,
        input_placeholder: str = "",
        **kwargs
    ):
        """Initialize chat layout.

        Args:
            show_status_bar: Whether to include the status bar
            input_placeholder: Initial placeholder text for input
        """
        super().__init__(**kwargs)
        self._show_status_bar = show_status_bar
        self._input_placeholder = input_placeholder

        # Cached widget references (set after mount)
        self._output: Optional[SelectableLog] = None
        self._input: Optional[TextArea] = None

    def compose(self) -> ComposeResult:
        """Create the chat layout widgets."""
        # Scrollable output area (with text selection support)
        with Container(id="output_container"):
            yield SelectableLog(id="output", auto_scroll=True)

        # Activity indicator
        yield ActivityIndicator()

        # Task progress display
        yield TaskProgressWidget()

        # Fixed input area at bottom
        with Container(id="input_container"):
            yield Label(">", id="input_prompt")
            yield TextArea(
                id="input",
                language=None,
                show_line_numbers=False,
                soft_wrap=True,
            )

        # Dynamic status bar (optional)
        if self._show_status_bar:
            yield StatusBar()

    def on_mount(self) -> None:
        """Cache widget references after mounting."""
        self._output = self.query_one("#output", SelectableLog)
        self._input = self.query_one("#input", TextArea)
        if self._input_placeholder:
            self._input.placeholder = self._input_placeholder

    @property
    def output(self) -> SelectableLog:
        """Get the output widget (SelectableLog)."""
        if self._output is None:
            self._output = self.query_one("#output", SelectableLog)
        return self._output

    @property
    def input(self) -> TextArea:
        """Get the TextArea input widget."""
        if self._input is None:
            self._input = self.query_one("#input", TextArea)
        return self._input

    def write(self, content: Any) -> None:
        """Write content to the output area.

        Args:
            content: Text string or Rich renderable
        """
        self.output.write(content)

    def clear_output(self) -> None:
        """Clear the output area."""
        self.output.clear()

    def clear_input(self) -> str:
        """Clear input and return the text that was there.

        Returns:
            The input text before clearing
        """
        text = self._input.text
        self._input.clear()
        return text

    def focus_input(self) -> None:
        """Focus the input field."""
        self._input.focus()
