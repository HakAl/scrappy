"""
Status bar components for the Textual TUI.

These components are displayed in the status bar area of the TUI,
providing real-time information like progress indicators, metrics,
activity states, and semantic search status.
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional
import time

from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Label
from textual.app import ComposeResult

from ..protocols import ActivityState

if TYPE_CHECKING:
    from ..protocols import StatusComponentProtocol


class ProgressIndicator:
    """Shows indexing/processing progress in the status bar."""

    def __init__(self) -> None:
        self._progress: int = 0
        self._total: int = 0
        self._message: str = ""
        self._active: bool = False
        self._start_time: Optional[float] = None
        self._widget: Optional[Label] = None

    @property
    def component_id(self) -> str:
        return "progress_indicator"

    @property
    def is_visible(self) -> bool:
        return self._active

    @property
    def widget(self) -> Label:
        if self._widget is None:
            self._widget = Label(self._message, id=self.component_id)
        return self._widget

    def start(self, message: str = "", total: int = 0) -> None:
        """Start progress tracking with timing."""
        self._start_time = time.time()
        self._message = message
        self._total = total
        self._progress = 0
        self._active = True
        self.update_widget()

    def get_elapsed(self) -> float:
        """Get elapsed time in seconds since start()."""
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def update_widget(self) -> None:
        if self._widget is not None:
            elapsed = self.get_elapsed()
            if elapsed > 0.0:
                self._widget.update(f"{self._message} ({elapsed:.1f}s)")
            else:
                self._widget.update(self._message)

    def update(self, progress: int, total: int, message: str) -> None:
        if self._start_time is None:
            self._start_time = time.time()
        self._progress = progress
        self._total = total
        self._message = message
        self._active = True
        self.update_widget()

    def complete(self) -> None:
        self._active = False
        self._start_time = None


class TokenCounter:
    """Shows token usage for current session in the status bar."""

    def __init__(self) -> None:
        self._tokens: int = 0
        self._visible: bool = False
        self._widget: Optional[Label] = None

    @property
    def component_id(self) -> str:
        return "token_counter"

    @property
    def is_visible(self) -> bool:
        return self._visible and self._tokens > 0

    @property
    def widget(self) -> Label:
        if self._widget is None:
            self._widget = Label(f"Tokens: {self._tokens:,}", id=self.component_id)
        return self._widget

    def update_widget(self) -> None:
        if self._widget is not None:
            self._widget.update(f"Tokens: {self._tokens:,}")

    def update(self, tokens: int) -> None:
        self._tokens = tokens
        self._visible = True
        self.update_widget()

    def hide(self) -> None:
        self._visible = False


class ProviderStatus:
    """Shows current provider/model during agent runs in the status bar."""

    def __init__(self) -> None:
        self._display: str = ""
        self._visible: bool = False
        self._widget: Optional[Label] = None

    @property
    def component_id(self) -> str:
        return "provider_status"

    @property
    def is_visible(self) -> bool:
        return self._visible and bool(self._display)

    @property
    def widget(self) -> Label:
        if self._widget is None:
            self._widget = Label(self._display, id=self.component_id)
        return self._widget

    def update_widget(self) -> None:
        if self._widget is not None:
            self._widget.update(self._display)

    def show(self, display: str) -> None:
        """Show the provider status with given display string (e.g., 'cerebras: llama-3.3-70b')."""
        self._display = display
        self._visible = True
        self.update_widget()

    def hide(self) -> None:
        """Hide the provider status."""
        self._display = ""
        self._visible = False
        self.update_widget()


class MetricsStatus:
    """Shows provider/model and token metrics in the status bar."""

    def __init__(self) -> None:
        self._provider_display: Optional[str] = None
        self._input_tokens: Optional[int] = None
        self._output_tokens: Optional[int] = None
        self._session_total: Optional[int] = None
        self._context_percent: Optional[int] = None
        self._widget: Optional[Label] = None

    @property
    def component_id(self) -> str:
        return "metrics_status"

    @property
    def is_visible(self) -> bool:
        return True

    @property
    def widget(self) -> Label:
        if self._widget is None:
            self._widget = Label(self._format_metrics(), id=self.component_id)
        return self._widget

    def update_widget(self) -> None:
        if self._widget is not None:
            self._widget.update(self._format_metrics())

    def update(
        self,
        provider_display: Optional[str],
        input_tokens: Optional[int],
        output_tokens: Optional[int],
        session_total: Optional[int],
        context_percent: Optional[int] = None,
    ) -> None:
        self._provider_display = provider_display
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._session_total = session_total
        self._context_percent = context_percent
        self.update_widget()

    def _format_metrics(self) -> str:
        provider = (self._provider_display or "").strip() or "provider: --"
        input_tokens = self._format_tokens(self._input_tokens)
        output_tokens = self._format_tokens(self._output_tokens)
        total = self._format_tokens(self._session_total)
        percent = self._format_percent(self._context_percent)
        # Format: provider | in:X out:Y | session:Z | ctx:N%
        # - in/out: tokens for last request
        # - session: cumulative tokens this session
        # - ctx: context window utilization %
        return f"{provider} | in:{input_tokens} out:{output_tokens} | session:{total} | ctx:{percent}"

    @staticmethod
    def _format_tokens(value: Optional[int]) -> str:
        if value is None:
            return "--"
        return f"{value:,}"

    @staticmethod
    def _format_percent(value: Optional[int]) -> str:
        if value is None:
            return "--%"
        if value >= 90:
            return f"[red]{value}%[/red]"
        if value >= 80:
            return f"[yellow]{value}%[/yellow]"
        return f"{value}%"


class PromptDisplay:
    """Shows prompt/question near the input in the status bar."""

    def __init__(self) -> None:
        self._message: str = ""
        self._input_type: str = ""
        self._default: str = ""
        self._visible: bool = False
        self._widget: Optional[Label] = None

    @property
    def component_id(self) -> str:
        return "prompt_display"

    @property
    def is_visible(self) -> bool:
        return self._visible and bool(self._message)

    @property
    def widget(self) -> Label:
        if self._widget is None:
            self._widget = Label(self._format_prompt(), id=self.component_id)
        return self._widget

    def _format_prompt(self) -> str:
        if not self._message:
            return ""
        hint = " [y/n]" if self._input_type == "confirm" else ""
        default_hint = f" (default: {self._default})" if self._default else ""
        return f"{self._message}{hint}{default_hint}"

    def update_widget(self) -> None:
        if self._widget is not None:
            self._widget.update(self._format_prompt())

    def show_prompt(self, message: str, input_type: str = "text", default: str = "") -> None:
        self._message = message
        self._input_type = input_type
        self._default = default
        self._visible = True
        self.update_widget()

    def hide_prompt(self) -> None:
        self._message = ""
        self._input_type = ""
        self._default = ""
        self._visible = False
        self.update_widget()


class SemanticStatusComponent:
    """Shows semantic search status in the status bar (always visible)."""

    def __init__(self) -> None:
        self._state: str = "initializing"  # initializing, indexing, ready, error
        self._chunks: int = 0
        self._files: int = 0
        self._progress_info: str = ""  # Right-aligned progress details
        self._start_time: Optional[float] = None
        self._widget: Optional[Horizontal] = None
        self._left_label: Optional[Label] = None
        self._right_label: Optional[Label] = None

    @property
    def component_id(self) -> str:
        return "semantic_status"

    @property
    def is_visible(self) -> bool:
        return True  # Always visible unlike ProgressIndicator

    @property
    def widget(self) -> Horizontal:
        if self._widget is None:
            self._left_label = Label(self._format_left(), id="semantic_status_left")
            self._right_label = Label(self._format_right(), id="semantic_status_right")
            self._widget = Horizontal(
                self._left_label,
                self._right_label,
                id=self.component_id
            )
        return self._widget

    def _format_left(self) -> str:
        if self._state == "ready":
            return "Search: ready"
        elif self._state == "indexing":
            return "Search: indexing"
        elif self._state == "error":
            return "Search: unavailable"
        else:
            return "Search: initializing..."

    def _format_right(self) -> str:
        if self._state == "indexing" and self._progress_info:
            elapsed = ""
            if self._start_time is not None:
                elapsed_secs = time.time() - self._start_time
                # Fixed-width format to prevent layout shift (handles 0.0 to 999.9)
                elapsed = f" ({elapsed_secs:>5.1f}s)"
            return f"{self._progress_info}{elapsed}"
        return ""

    def update_widget(self) -> None:
        if self._left_label is not None:
            self._left_label.update(self._format_left())
        if self._right_label is not None:
            self._right_label.update(self._format_right())

    def set_indexing(self, progress_info: str = "") -> None:
        if self._state != "indexing":
            self._start_time = time.time()
        self._state = "indexing"
        self._progress_info = progress_info
        if self._widget is not None:
            self._widget.remove_class("ready")
            self._widget.add_class("indexing")
        self.update_widget()

    def set_ready(self, chunks: int = 0, files: int = 0) -> None:
        self._state = "ready"
        self._chunks = chunks
        self._files = files
        self._progress_info = ""
        self._start_time = None
        if self._widget is not None:
            self._widget.remove_class("indexing")
            self._widget.add_class("ready")
        self.update_widget()

    def set_error(self) -> None:
        self._state = "error"
        self._progress_info = ""
        self._start_time = None
        self.update_widget()


class ActivityIndicator(Label):
    """Activity indicator widget for showing activity state.

    Displays current activity state (THINKING, SYNCING, TOOL_EXECUTION) with
    elapsed time. Flicker prevention via 500ms timer delay - if operation
    completes before delay, the indicator never becomes visible.

    Thread-safe: Updates via ActivityChanged events from worker threads.
    """

    # Delay before showing indicator (flicker prevention)
    SHOW_DELAY_SECONDS = 0.5

    def __init__(self) -> None:
        super().__init__("", id="activity_indicator")
        self._state: Optional[ActivityState] = None
        self._message: str = ""
        self._elapsed_ms: int = 0
        self._show_timer: Optional[Any] = None

    @property
    def is_visible(self) -> bool:
        """Whether indicator is currently active (has 'active' class)."""
        return self._state is not None

    def show(self, state: ActivityState, message: str = "") -> None:
        """Schedule showing the activity indicator after delay.

        Uses timer-based delay for flicker prevention - if hide() is called
        before the timer fires, the indicator never becomes visible.

        Args:
            state: Current activity state
            message: Optional descriptive message
        """
        # Cancel any pending show timer
        if self._show_timer is not None:
            self._show_timer.stop()
            self._show_timer = None

        self._state = state
        self._message = message
        self._elapsed_ms = 0
        self._update_display()

        # Schedule showing after delay (flicker prevention)
        self._show_timer = self.set_timer(
            self.SHOW_DELAY_SECONDS,
            self._reveal
        )

    def _reveal(self) -> None:
        """Actually show the indicator (called after delay)."""
        self._show_timer = None
        if self._state is not None:
            self.add_class("active")

    def update_elapsed(self, elapsed_ms: int) -> None:
        """Update elapsed time display.

        Args:
            elapsed_ms: Elapsed time in milliseconds
        """
        self._elapsed_ms = elapsed_ms
        if self.is_visible:
            self._update_display()

    def hide(self) -> None:
        """Hide the activity indicator immediately."""
        # Cancel pending show timer (prevents flicker)
        if self._show_timer is not None:
            self._show_timer.stop()
            self._show_timer = None

        self._state = None
        self._message = ""
        self._elapsed_ms = 0
        self.remove_class("active")
        self.update("")

    def _update_display(self) -> None:
        """Update display text based on current state."""
        if self._state is None:
            return

        state_text = {
            ActivityState.THINKING: "thinking",
            ActivityState.SYNCING: "syncing",
            ActivityState.TOOL_EXECUTION: "executing",
            ActivityState.IDLE: ""
        }.get(self._state, "")

        if not state_text:
            return

        elapsed_sec = self._elapsed_ms / 1000.0
        text = f"{state_text}... ({elapsed_sec:.1f}s)"

        if self._message:
            text = f"{state_text}: {self._message} ({elapsed_sec:.1f}s)"

        self.update(text)


class StatusBar(Container):
    """Dynamic status bar that shows/hides based on active components."""

    show_status = reactive(False)

    def __init__(self) -> None:
        super().__init__(id="status_bar")
        self.components: Dict[str, "StatusComponentProtocol"] = {}
        self._mounted_ids: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Vertical(id="status_content")

    def register_component(self, component: "StatusComponentProtocol") -> None:
        self.components[component.component_id] = component
        self.refresh_display()

    def unregister_component(self, component_id: str) -> None:
        if component_id in self.components:
            del self.components[component_id]
            self._mounted_ids.discard(component_id)
            self.refresh_display()

    def _get_visible_components(self) -> List["StatusComponentProtocol"]:
        return [c for c in self.components.values() if c.is_visible]

    def _update_visibility(self, has_visible: bool) -> None:
        self.show_status = has_visible
        if has_visible:
            self.add_class("show")
        else:
            self.remove_class("show")

    def _mount_components(self, visible: List["StatusComponentProtocol"]) -> None:
        try:
            content = self.query_one("#status_content", Vertical)
        except Exception:
            return

        visible_ids = {c.component_id for c in visible}

        for comp_id in self._mounted_ids - visible_ids:
            try:
                widget = content.query_one(f"#{comp_id}")
                widget.remove()
            except Exception:
                pass

        for component in visible:
            if component.component_id not in self._mounted_ids:
                content.mount(component.widget)

        for component in visible:
            component.update_widget()

        self._mounted_ids = visible_ids

    def refresh_display(self) -> None:
        visible = self._get_visible_components()
        self._update_visibility(len(visible) > 0)
        self._mount_components(visible)
