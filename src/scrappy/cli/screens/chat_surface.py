"""Shared chat surface widget and submit controller contracts."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Protocol, TypeAlias

from rich.console import RenderableType
from textual.app import ComposeResult
from textual.containers import Container
from textual.widget import Widget
from textual.widgets import Label, TextArea

from ..input_capture import InputRequest
from ..textual import ActivityIndicator, StatusBar
from ..textual.tui_events import TuiEventTarget
from ..widgets import SelectableLog, TaskProgressWidget

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatSurfaceConfig:
    """Feature configuration for the shared chat surface."""

    show_status_bar: bool = True
    input_placeholder: str = ""


@dataclass(frozen=True)
class ClearTranscript:
    """Clear the local transcript surface."""

    target: TuiEventTarget = TuiEventTarget.MAIN_TRANSCRIPT


@dataclass(frozen=True)
class AppendTranscript:
    """Append ordered renderables to the local transcript surface."""

    entries: tuple[RenderableType, ...]
    target: TuiEventTarget = TuiEventTarget.MAIN_TRANSCRIPT


@dataclass(frozen=True)
class RefocusInput:
    """Refocus the shared composer."""


@dataclass(frozen=True)
class RestartCapture:
    """Restart inline capture with the next queued request."""

    request: InputRequest


@dataclass(frozen=True)
class ExitApp:
    """Request application exit after submit handling."""


@dataclass(frozen=True)
class UpdatePlaceholder:
    """Update the shared composer placeholder."""

    text: str


FollowUpAction: TypeAlias = (
    ClearTranscript
    | AppendTranscript
    | RefocusInput
    | RestartCapture
    | ExitApp
    | UpdatePlaceholder
)


@dataclass(frozen=True)
class SubmitResult:
    """Result of a command submit action."""

    accepted: bool
    follow_up_actions: tuple[FollowUpAction, ...] = ()


class ChatCommandHandlerProtocol(Protocol):
    """Screen-specific command handling behind a shared submit path."""

    def handle_submit(self, user_input: str) -> SubmitResult:
        """Handle an already-trimmed user input string."""
        ...


class ChatSurface(Widget):
    """Shared transcript, status, and composer surface."""

    def __init__(
        self,
        config: ChatSurfaceConfig | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._config = config or ChatSurfaceConfig()
        self._output: SelectableLog | None = None
        self._input: TextArea | None = None

    def compose(self) -> ComposeResult:
        """Create the shared chat widgets."""
        yield SelectableLog(id="output", auto_scroll=True)
        yield ActivityIndicator()
        yield TaskProgressWidget()

        with Container(id="input_container"):
            yield Label(">", id="input_prompt")
            yield TextArea(
                id="input",
                language=None,
                show_line_numbers=False,
                soft_wrap=True,
            )

        if self._config.show_status_bar:
            yield StatusBar()

    def on_mount(self) -> None:
        """Cache widget references after mounting."""
        self._output = self.query_one("#output", SelectableLog)
        self._input = self.query_one("#input", TextArea)
        if self._config.input_placeholder:
            self._input.placeholder = self._config.input_placeholder

    @property
    def output(self) -> SelectableLog:
        """Return the transcript widget."""
        if self._output is None:
            self._output = self.query_one("#output", SelectableLog)
        return self._output

    @property
    def input(self) -> TextArea:
        """Return the composer widget."""
        if self._input is None:
            self._input = self.query_one("#input", TextArea)
        return self._input

    def write(self, content: RenderableType) -> None:
        """Write text or a Rich renderable to the transcript."""
        self.output.write(content)

    def clear_output(self) -> None:
        """Clear the transcript."""
        self.output.clear()

    def clear_input(self) -> str:
        """Clear the composer and return its previous text."""
        text = self.input.text
        self.input.clear()
        return text

    def focus_input(self) -> None:
        """Focus the composer."""
        self.input.focus()

    def submit(self, handler: ChatCommandHandlerProtocol) -> SubmitResult:
        """Submit the current composer text through the handler protocol."""
        user_input = self.clear_input().strip()
        return handler.handle_submit(user_input)

    def handle_click(self, event: Any, clipboard: Any) -> None:
        """Apply shared click, focus, and right-click paste policy."""
        clicked_widget = event.widget if hasattr(event, "widget") else None

        if isinstance(clicked_widget, SelectableLog):
            return

        if hasattr(event, "button") and event.button == 3:
            self.paste_from_clipboard(clipboard)
            return

        if clicked_widget is not None and not isinstance(clicked_widget, TextArea):
            self.focus_input()

            def clear_selection() -> None:
                end_location = self.input.document.end
                self.input.cursor_location = end_location

            self.call_after_refresh(clear_selection)

    def paste_from_clipboard(self, clipboard: Any) -> bool:
        """Paste clipboard text into the composer."""
        try:
            text = clipboard.paste_text()
        except Exception as exc:
            logger.warning("Failed to paste from clipboard: %s", exc)
            return False

        if not text:
            return False

        self.input.replace(
            text,
            self.input.selection.start,
            self.input.selection.end,
            maintain_selection_offset=True,
        )
        return True

    def apply_follow_up_actions(
        self,
        actions: tuple[FollowUpAction, ...],
    ) -> tuple[FollowUpAction, ...]:
        """Apply local surface actions and return screen-owned actions."""
        unhandled: list[FollowUpAction] = []
        for action in actions:
            if isinstance(action, ClearTranscript):
                self.clear_output()
            elif isinstance(action, AppendTranscript):
                for entry in action.entries:
                    self.write(entry)
            elif isinstance(action, RefocusInput):
                self.focus_input()
            elif isinstance(action, UpdatePlaceholder):
                self.input.placeholder = action.text
            else:
                unhandled.append(action)
        return tuple(unhandled)
