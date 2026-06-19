"""Main chat interface screen for Scrappy TUI."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Optional, Protocol, cast
import logging
import time

from textual.screen import Screen
from textual.app import ComposeResult
from textual.binding import Binding
from textual import work

from .chat_surface import (
    ChatSurface,
    ChatSurfaceConfig,
    ExitApp,
    RestartCapture,
    SubmitResult,
)
from ..widgets import SelectableLog
from ..input_capture import InputCaptureManager, InputRequest
from ..command_history import CommandHistory, get_default_history_path
from ..textual import (
    ProgressIndicator,
    MetricsStatus,
    PromptDisplay,
    SemanticStatusComponent,
    StatusBar,
    ActivityIndicator,
)
from ..textual.tui_events import ActivityChanged, MetricsUpdated
from ..textual.tui_events import TranscriptAppendRenderable, TranscriptAppendText

from scrappy.infrastructure.theme import ThemeProtocol
from ..protocols import ActivityState, ClipboardProtocol

if TYPE_CHECKING:
    from ..interactive import InteractiveMode
    from ..textual import (
        TextualOutputAdapter,
        ThreadSafeAsyncBridge,
        ScrappyApp,
    )

logger = logging.getLogger(__name__)


class MouseRestoreHostProtocol(Protocol):
    """App surface for restoring mouse capture after a worker command.

    Consumer-side boundary co-located with the screen so mypy verifies these
    calls, replacing the getattr lookups that previously erased them to Any.
    """

    def call_from_thread(
        self, callback: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """Run a callback on the app's main thread."""
        ...

    def restore_mouse_support(self) -> None:
        """Re-enable mouse capture after a command completes."""
        ...


class MainAppScreen(Screen):
    """Main chat interface screen.

    Provides:
    - Scrollable output area for conversation history (SelectableLog)
    - Input field for user messages and commands
    - Dynamic status bar for progress indicators and metrics
    - Command history navigation with up/down arrows
    - Inline capture mode for prompts/confirms
    """

    BINDINGS = [
        Binding("enter", "submit_input", "Submit", priority=True),
        Binding("up", "history_previous", "Previous", priority=True),
        Binding("down", "history_next", "Next", priority=True),
        Binding("ctrl+home", "transcript_home", "Transcript Start", priority=True),
        Binding(
            "ctrl+end",
            "transcript_follow_latest",
            "Transcript End",
            priority=True,
        ),
        # Plain PageUp/PageDown stay with the focused widget: the composer pages
        # its own text, and a focused transcript scrolls itself (SelectableLog is
        # a focusable ScrollView). The Ctrl chord is the focus-independent path
        # so keyboard users can review older output without leaving the input.
        Binding("ctrl+pageup", "transcript_page_up", "Scroll Up", priority=True),
        Binding(
            "ctrl+pagedown",
            "transcript_page_down",
            "Scroll Down",
            priority=True,
        ),
        # Note: escape is handled at app level (ScrappyApp.on_key)
    ]

    def __init__(
        self,
        interactive_mode: Optional["InteractiveMode"],
        output_adapter: "TextualOutputAdapter",
        bridge: "ThreadSafeAsyncBridge",
        theme: ThemeProtocol,
        clipboard: ClipboardProtocol,
    ):
        """Initialize main screen with dependencies.

        Args:
            interactive_mode: The InteractiveMode instance for command processing.
                Can be None in deferred initialization mode - commands are blocked
                until app.ready becomes True.
            output_adapter: Adapter for thread-safe output routing
            bridge: Bridge for blocking prompts/confirms from worker threads
            theme: Theme for consistent styling
            clipboard: Clipboard service for OS clipboard integration
        """
        super().__init__()
        self.interactive_mode = interactive_mode
        self.output_adapter = output_adapter
        self.bridge = bridge
        self._theme = theme
        self._clipboard = clipboard

        # Status bar components
        self.progress_indicator = ProgressIndicator()
        self.prompt_display = PromptDisplay()
        self.metrics_status = MetricsStatus()

        # Input capture manager for inline prompts/confirms
        self.capture_manager = InputCaptureManager(self.bridge)

        # Command history for up/down arrow navigation
        self._history = CommandHistory(history_file=get_default_history_path())
        self._history_temp_input: str = ""

        # Shared chat surface (set on mount)
        self._surface: Optional[ChatSurface] = None

        # Elapsed timer for activity indicator
        self._elapsed_timer: Optional[Any] = None
        self._elapsed_start_time: float = 0.0

    @property
    def scrappy_app(self) -> "ScrappyApp":
        """Get the typed ScrappyApp instance."""
        from ..textual import ScrappyApp
        return cast(ScrappyApp, self.app)

    @property
    def semantic_status(self) -> SemanticStatusComponent:
        """Lazy-load semantic status component."""
        if not hasattr(self, '_semantic_status'):
            self._semantic_status = SemanticStatusComponent()
        return self._semantic_status

    def compose(self) -> ComposeResult:
        """Create child widgets using the shared chat surface."""
        yield ChatSurface(
            config=ChatSurfaceConfig(
                show_activity=True,
                show_tasks=True,
                show_status_bar=True,
                history_enabled=True,
                capture_enabled=True,
                input_placeholder="Type your message or command...",
            ),
            id="chat_surface"
        )

    def on_mount(self) -> None:
        """Called when screen is mounted."""
        # Get surface and focus input
        self._surface = self.query_one(ChatSurface)
        self._surface.focus_input()

        # Register status components with the status bar
        status_bar = self.query_one(StatusBar)
        status_bar.register_component(self.progress_indicator)
        status_bar.register_component(self.prompt_display)
        status_bar.register_component(self.metrics_status)
        status_bar.register_component(self.semantic_status)

        # NOTE: Banner is now displayed immediately in app._show_main_screen()
        # using display_banner_header_tui(). Status lines are shown when CLI is ready.
        # No "Starting up..." message needed since user sees banner immediately.

    def on_unmount(self) -> None:
        """Called when screen is unmounted - clean up resources."""
        self._stop_elapsed_timer()

    def on_click(self, event) -> None:
        """Refocus input when clicking anywhere except input field."""
        if self._surface is None:
            return
        self._surface.handle_click(event, self._clipboard)

    def on_key(self, event) -> None:
        """Handle screen-specific key events.

        Note: ctrl+q, ctrl+c, and escape are handled at app level (ScrappyApp.on_key).
        This handler only deals with screen-specific keys like up-arrow blocking.
        """
        if self._surface is None:
            return

        # Already focused on input, let it handle naturally
        if self._surface.input_has_focus():
            return

        # Don't steal focus from other interactive widgets (except SelectableLog
        # which doesn't use keyboard input - it only uses mouse for selection)
        focused = self.focused
        if focused is not None and focused != self and not isinstance(focused, SelectableLog):
            return

        # Auto-focus on printable characters
        if event.is_printable:
            self._surface.focus_input()

    def action_submit_input(self) -> None:
        """Handle Enter to submit input."""
        if self._surface is None:
            return

        # Gate: Block input until CLI is ready (deferred initialization)
        # Silently ignore - user sees banner header immediately, status lines when ready
        if not self.scrappy_app.ready:
            return

        # Gate: Block input if interactive_mode not wired up yet
        # (This shouldn't happen if app.ready is True, but defensive check)
        if self.interactive_mode is None:
            # Try to get updated reference from app
            self.interactive_mode = self.scrappy_app.interactive_mode
            if self.interactive_mode is None:
                self.scrappy_app.tui_event_sink.post_event(
                    TranscriptAppendText(content="Still initializing...\n")
                )
                return

        result = self._surface.submit(self)
        self._apply_submit_follow_up_actions(result)

    def handle_submit(self, user_input: str) -> SubmitResult:
        """Handle submitted composer text behind the shared surface protocol."""
        if self.capture_manager.is_capturing:
            return self._handle_captured_input(user_input)

        if not user_input:
            return SubmitResult(accepted=False)

        # Add to history and reset navigation position
        self._history.add_to_history(user_input)
        self._history_temp_input = ""

        # Process in worker thread
        self.process_command(user_input)
        return SubmitResult(accepted=True)

    def action_history_previous(self) -> None:
        """Handle Up arrow to navigate to previous history entry."""
        if self._surface is None:
            return

        if not self._surface.history_enabled:
            return

        if not self._surface.input_has_focus():
            self._surface.output.action_scroll_up()
            return

        if self._surface.move_composer_up_before_history():
            return

        if self.capture_manager.is_capturing:
            return

        current_text = self._surface.input_text
        if self._history_temp_input == "" and current_text:
            self._history_temp_input = current_text

        previous = self._history.get_previous()
        if previous is not None:
            # Use text setter instead of clear()+insert() to properly reset cursor state
            self._surface.input_text = previous

    def action_history_next(self) -> None:
        """Handle Down arrow to navigate to next history entry."""
        if self._surface is None:
            return

        if not self._surface.history_enabled:
            return

        if not self._surface.input_has_focus():
            self._surface.output.action_scroll_down()
            return

        if self._surface.move_composer_down_before_history():
            return

        if self.capture_manager.is_capturing:
            return

        next_entry = self._history.get_next()
        if next_entry is not None:
            # Use text setter instead of clear()+insert() to properly reset cursor state
            self._surface.input_text = next_entry
        else:
            # Restore saved input when navigating past history end
            restored = self._history_temp_input
            self._history_temp_input = ""
            self._surface.input_text = restored

    def action_transcript_page_up(self) -> None:
        """Page the transcript toward older output, regardless of input focus."""
        if self._surface is not None:
            self._surface.output.action_page_up()

    def action_transcript_page_down(self) -> None:
        """Page the transcript toward newer output, regardless of input focus."""
        if self._surface is not None:
            self._surface.output.action_page_down()

    def action_transcript_home(self) -> None:
        """Move the transcript to the oldest visible output."""
        if self._surface is not None:
            self._surface.output.action_scroll_home()

    def action_transcript_follow_latest(self) -> None:
        """Move the transcript to live output."""
        if self._surface is not None:
            self._surface.follow_latest()

    def _cancel_ui_cleanup(self) -> None:
        """Stop timer and hide activity indicator after cancellation."""
        self._stop_elapsed_timer()
        self._history.reset_position()
        try:
            indicator = self.query_one(ActivityIndicator)
            indicator.hide()
        except Exception:
            pass  # Indicator might not be mounted

    def _handle_captured_input(self, user_input: str) -> SubmitResult:
        """Process input captured for prompt/confirm."""
        self.capture_manager.handle_captured_input(user_input)
        next_request = self.capture_manager.exit_capture_mode()

        if next_request:
            return SubmitResult(
                accepted=True,
                follow_up_actions=(RestartCapture(next_request),),
            )
        else:
            self._exit_capture_ui()
            return SubmitResult(accepted=True)

    def _apply_submit_follow_up_actions(self, result: SubmitResult) -> None:
        """Apply screen-owned submit follow-up actions."""
        if self._surface is None:
            return

        for action in self._surface.apply_follow_up_actions(result.follow_up_actions):
            if isinstance(action, RestartCapture):
                request = action.request
                self.capture_manager.enter_capture_mode(
                    request.prompt_id,
                    request.message,
                    request.input_type,
                    request.default,
                )
                self._update_capture_ui(request)
            elif isinstance(action, ExitApp):
                self.app.exit()

    @work(exclusive=True, thread=True)
    def process_command(self, user_input: str) -> None:
        """Process command in worker thread."""
        logger.debug("process_command: starting for input: %s", user_input[:50])
        try:
            self.scrappy_app.tui_event_sink.post_event(
                ActivityChanged(ActivityState.THINKING)
            )
            interactive_mode = self.interactive_mode
            if interactive_mode is None:
                interactive_mode = self.scrappy_app.interactive_mode
                if interactive_mode is not None:
                    self.interactive_mode = interactive_mode
            if interactive_mode is None:
                logger.warning("process_command called before interactive mode was ready")
                self.scrappy_app.tui_event_sink.post_event(
                    TranscriptAppendText(content="Still initializing...\n")
                )
                return

            logger.debug("process_command: posted THINKING, calling _process_input")
            should_continue = interactive_mode._process_input(user_input)
            logger.debug("process_command: _process_input returned %s", should_continue)
            if not should_continue:
                self.app.exit()
        except Exception as e:
            from rich.text import Text
            from ..utils.error_handler import format_error, get_error_suggestion

            error_msg = format_error(e)
            suggestion = get_error_suggestion(e)

            error_text = Text(f"Error: {error_msg}", style=self._theme.error)
            if suggestion:
                error_text.append(f"\nSuggestion: {suggestion}", style="dim")

            self.scrappy_app.tui_event_sink.post_event(
                TranscriptAppendRenderable(renderable=error_text)
            )
            logger.exception("Error processing command")
        finally:
            logger.debug("process_command: finally block, flushing TUI event sink")
            self.scrappy_app.tui_event_sink.flush(timeout=5.0)
            logger.debug("process_command: flush complete, posting IDLE")
            self.scrappy_app.tui_event_sink.post_event(ActivityChanged(ActivityState.IDLE))
            mouse_host: MouseRestoreHostProtocol = self.scrappy_app
            mouse_host.call_from_thread(mouse_host.restore_mouse_support)
            logger.debug("process_command: IDLE posted, exiting")

    def write_output(self, content: str) -> None:
        """Write plain text to output area."""
        if self._surface:
            self._surface.write(content)

    def write_renderable(self, renderable: Any) -> None:
        """Write Rich renderable to output area."""
        if self._surface:
            self._surface.write(renderable)

    def enter_capture_mode(
        self,
        prompt_id: str,
        message: str,
        input_type: str,
        default: str = ""
    ) -> None:
        """Enter capture mode for inline input."""
        if self._surface is not None and not self._surface.capture_enabled:
            return
        self.capture_manager.enter_capture_mode(
            prompt_id, message, input_type, default
        )
        if self.capture_manager.is_capturing:
            request = InputRequest(prompt_id, message, input_type, default)
            self._update_capture_ui(request)

    def update_indexing_progress(
        self,
        message: str,
        progress: int = 0,
        total: int = 0,
        complete: bool = False
    ) -> None:
        """Update indexing progress in status bar.

        Args:
            message: Status message to display
            progress: Current progress value (number of items processed)
            total: Total number of items to process
            complete: Whether the operation is complete
        """
        # Detect completion from message content
        is_complete = (
            complete
            or message.startswith("Indexing complete")
            or message.startswith("Indexing failed")
            or message == "Semantic search ready"
            or message == "Index up to date - no changes detected"
            or message == "Incremental update complete"
            or message == "No files to index"
            or message == "Indexing cancelled"
            or message == "No file collector available"
        )

        if is_complete:
            # Update semantic status to ready
            if hasattr(self, '_semantic_status'):
                # Use numeric total directly (no more regex parsing)
                self._semantic_status.set_ready(chunks=total if total > 0 else progress)
        else:
            # Update semantic status with progress info
            if hasattr(self, '_semantic_status'):
                # Use numeric progress directly (no more regex parsing)
                if progress > 0:
                    progress_info = f"{progress} files"
                else:
                    progress_info = ""
                self._semantic_status.set_indexing(progress_info)

        status_bar = self.query_one(StatusBar)
        status_bar.refresh_display()

    def _update_capture_ui(self, request: "InputRequest") -> None:
        """Update UI for capture mode."""
        if self._surface is None:
            return

        # Hide activity indicator during prompts - we're waiting for user input,
        # not "thinking". This prevents the timer from showing with the prompt.
        self._stop_elapsed_timer()
        try:
            indicator = self.query_one(ActivityIndicator)
            indicator.hide()
        except Exception:
            pass  # Indicator might not be mounted

        self.prompt_display.show_prompt(
            message=request.message,
            input_type=request.input_type,
            default=getattr(request, 'default', '') or ''
        )

        status_bar = self.query_one(StatusBar)
        status_bar.refresh_display()

        input_container = self.query_one("#input_container")
        input_container.add_class("capture-mode")

        self._surface.prepare_capture_input(request)
        self._surface.focus_input()

    def _exit_capture_ui(self) -> None:
        """Clean up capture mode UI state."""
        if self._surface is None:
            return

        self._surface.restore_input_placeholder()

        self.prompt_display.hide_prompt()
        status_bar = self.query_one(StatusBar)
        status_bar.refresh_display()

        input_container = self.query_one("#input_container")
        input_container.remove_class("capture-mode")

        # Restore activity indicator - agent is continuing after the prompt.
        # _update_capture_ui hid it while waiting for input, now we resume.
        # The THINKING state will be replaced by IDLE when process_command ends.
        self.scrappy_app.tui_event_sink.post_event(
            ActivityChanged(ActivityState.THINKING)
        )

    def update_activity(self, message: ActivityChanged) -> None:
        """Update activity indicator based on activity event.

        Args:
            message: Activity event with state, message, and elapsed_ms
        """
        logger.debug("update_activity: state=%s, elapsed_ms=%d", message.state, message.elapsed_ms)
        try:
            indicator = self.query_one(ActivityIndicator)
        except Exception as e:
            logger.warning("update_activity: ActivityIndicator not found: %s", e)
            return

        if message.state == ActivityState.IDLE:
            logger.debug("update_activity: hiding indicator")
            indicator.hide()
            self._stop_elapsed_timer()
        else:
            if message.elapsed_ms > 0:
                indicator.update_elapsed(message.elapsed_ms)
            else:
                indicator.show(message.state, message.message)
                self._start_elapsed_timer()
        logger.debug("update_activity: done")

    def update_tasks(self, tasks: list) -> None:
        """Update task progress widget with new tasks.

        Args:
            tasks: List of Task objects to display.
        """
        from ..widgets import TaskProgressWidget

        try:
            widget = self.query_one(TaskProgressWidget)
            widget.update_tasks(tasks)
        except Exception:
            pass  # Widget not mounted yet

    def update_metrics(self, message: MetricsUpdated) -> None:
        """Update metrics status bar line."""
        self.metrics_status.update(
            provider_display=message.provider_display,
            input_tokens=message.input_tokens,
            output_tokens=message.output_tokens,
            session_total=message.session_total,
            context_percent=message.context_percent,
        )
        status_bar = self.query_one(StatusBar)
        status_bar.refresh_display()

    def _start_elapsed_timer(self) -> None:
        """Start the elapsed time timer for activity indicator updates."""
        self._stop_elapsed_timer()
        self._elapsed_start_time = time.time()
        self._elapsed_timer = self.set_interval(0.5, self._update_elapsed)

    def _stop_elapsed_timer(self) -> None:
        """Stop the elapsed time timer."""
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
            self._elapsed_timer = None
        self._elapsed_start_time = 0.0

    def _update_elapsed(self) -> None:
        """Update elapsed time in the activity indicator."""
        if self._elapsed_start_time == 0.0:
            return

        elapsed_ms = int((time.time() - self._elapsed_start_time) * 1000)

        try:
            indicator = self.query_one(ActivityIndicator)
            if indicator.is_visible:
                indicator.update_elapsed(elapsed_ms)
        except Exception:
            pass


