"""Main chat interface screen for Scrappy TUI."""

from typing import TYPE_CHECKING, Any, Optional, cast
import logging
import time

from textual.screen import Screen
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import TextArea
from textual import work

from .chat_layout import ChatLayout
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
    ActivityStateChange,
)

from scrappy.infrastructure.theme import ThemeProtocol
from ..protocols import ActivityState, ClipboardProtocol

if TYPE_CHECKING:
    from ..interactive import InteractiveMode
    from ..textual import (
        TextualOutputAdapter,
        ThreadSafeAsyncBridge,
        ScrappyApp,
        MetricsUpdate,
    )

logger = logging.getLogger(__name__)


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

        # Layout component (set on mount)
        self._layout: Optional[ChatLayout] = None

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
        """Create child widgets using ChatLayout."""
        yield ChatLayout(
            show_status_bar=True,
            input_placeholder="Type your message or command...",
            id="chat_layout"
        )

    def on_mount(self) -> None:
        """Called when screen is mounted."""
        # Get layout and focus input
        self._layout = self.query_one(ChatLayout)
        self._layout.focus_input()

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
        if self._layout is None:
            return

        # Right-click (button=3) pastes from clipboard
        if hasattr(event, 'button') and event.button == 3:
            try:
                text = self._clipboard.paste_text()
                if text:
                    self._layout.input.replace(
                        text,
                        self._layout.input.selection.start,
                        self._layout.input.selection.end,
                        maintain_selection_offset=True
                    )
            except Exception as e:
                logger.warning(f"Failed to paste from clipboard: {e}")
            return

        # Get the widget that was clicked
        clicked_widget = event.widget if hasattr(event, 'widget') else None

        # Refocus input if clicking anything except the input or log
        if clicked_widget is not None and not isinstance(clicked_widget, (TextArea, SelectableLog)):
            self._layout.focus_input()
            # Clear selection by moving to end
            def clear_selection():
                end_location = self._layout.input.document.end
                self._layout.input.cursor_location = end_location
            self.call_after_refresh(clear_selection)

    def on_key(self, event) -> None:
        """Handle screen-specific key events.

        Note: ctrl+q, ctrl+c, and escape are handled at app level (ScrappyApp.on_key).
        This handler only deals with screen-specific keys like up-arrow blocking.
        """
        if self._layout is None:
            return

        # Block up-arrow history during capture mode
        if self.capture_manager.is_capturing:
            if event.key == "up":
                event.stop()
                return

        # Already focused on input, let it handle naturally
        if self._layout.input.has_focus:
            return

        # Don't steal focus from other interactive widgets (except SelectableLog
        # which doesn't use keyboard input - it only uses mouse for selection)
        focused = self.focused
        if focused is not None and focused != self and not isinstance(focused, SelectableLog):
            return

        # Auto-focus on printable characters
        if event.is_printable:
            self._layout.focus_input()

    def action_submit_input(self) -> None:
        """Handle Enter to submit input."""
        if self._layout is None:
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
                self.write_output("Still initializing...\n")
                return

        # Preserve multiline input as-is (Textual TextArea buffers paste correctly)
        user_input = self._layout.input.text.strip()

        # Clear input immediately
        self._layout.input.clear()

        # Handle capture mode
        if self.capture_manager.is_capturing:
            self._handle_captured_input(user_input)
            return

        # Normal command processing
        if not user_input:
            return

        # Add to history and reset navigation position
        self._history.add_to_history(user_input)
        self._history_temp_input = ""

        # Process in worker thread
        self.process_command(user_input)

    def action_history_previous(self) -> None:
        """Handle Up arrow to navigate to previous history entry."""
        if self.capture_manager.is_capturing or self._layout is None:
            return

        current_text = self._layout.input.text
        if self._history_temp_input == "" and current_text:
            self._history_temp_input = current_text

        previous = self._history.get_previous()
        if previous is not None:
            # Use text setter instead of clear()+insert() to properly reset cursor state
            self._layout.input.text = previous

    def action_history_next(self) -> None:
        """Handle Down arrow to navigate to next history entry."""
        if self.capture_manager.is_capturing or self._layout is None:
            return

        next_entry = self._history.get_next()
        if next_entry is not None:
            # Use text setter instead of clear()+insert() to properly reset cursor state
            self._layout.input.text = next_entry
        else:
            # Restore saved input when navigating past history end
            restored = self._history_temp_input
            self._history_temp_input = ""
            self._layout.input.text = restored

    def _cancel_ui_cleanup(self) -> None:
        """Stop timer and hide activity indicator after cancellation."""
        self._stop_elapsed_timer()
        self._history.reset_position()
        try:
            indicator = self.query_one(ActivityIndicator)
            indicator.hide()
        except Exception:
            pass  # Indicator might not be mounted

    def _handle_captured_input(self, user_input: str) -> None:
        """Process input captured for prompt/confirm."""
        self.capture_manager.handle_captured_input(user_input)
        next_request = self.capture_manager.exit_capture_mode()

        if next_request:
            self.capture_manager.enter_capture_mode(
                next_request.prompt_id,
                next_request.message,
                next_request.input_type,
                next_request.default
            )
            self._update_capture_ui(next_request)
        else:
            self._exit_capture_ui()

    @work(exclusive=True, thread=True)
    def process_command(self, user_input: str) -> None:
        """Process command in worker thread."""
        logger.debug("process_command: starting for input: %s", user_input[:50])
        try:
            self.app.post_message(ActivityStateChange(ActivityState.THINKING))
            interactive_mode = self.interactive_mode
            if interactive_mode is None:
                interactive_mode = self.scrappy_app.interactive_mode
                if interactive_mode is not None:
                    self.interactive_mode = interactive_mode
            if interactive_mode is None:
                logger.warning("process_command called before interactive mode was ready")
                self.write_output("Still initializing...\n")
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

            self.output_adapter.post_renderable(error_text)
            logger.exception("Error processing command")
        finally:
            logger.debug("process_command: finally block, flushing output adapter")
            self.output_adapter.flush(timeout=5.0)
            logger.debug("process_command: flush complete, posting IDLE")
            self.app.post_message(ActivityStateChange(ActivityState.IDLE))
            restore_mouse_support = getattr(self.app, "restore_mouse_support", None)
            if callable(restore_mouse_support):
                call_from_thread = getattr(self.app, "call_from_thread", None)
                if callable(call_from_thread):
                    call_from_thread(restore_mouse_support)
                else:
                    restore_mouse_support()
            logger.debug("process_command: IDLE posted, exiting")

    def write_output(self, content: str) -> None:
        """Write plain text to output area."""
        if self._layout:
            self._layout.write(content)

    def write_renderable(self, renderable: Any) -> None:
        """Write Rich renderable to output area."""
        if self._layout:
            self._layout.write(renderable)

    def enter_capture_mode(
        self,
        prompt_id: str,
        message: str,
        input_type: str,
        default: str = ""
    ) -> None:
        """Enter capture mode for inline input."""
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
        if self._layout is None:
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

        if request.input_type == "confirm":
            self._layout.input.placeholder = "Type y or n..."
        elif request.input_type == "confirm_yna":
            self._layout.input.placeholder = "Type y, n, or a (allow all)..."
        elif request.input_type == "checkpoint":
            self._layout.input.placeholder = "Type c, g, a, or s..."
        else:
            hint = f" (default: {request.default})" if request.default else ""
            self._layout.input.placeholder = f"Enter value{hint}..."

        self._layout.focus_input()

    def _exit_capture_ui(self) -> None:
        """Clean up capture mode UI state."""
        if self._layout is None:
            return

        self._layout.input.placeholder = "Type your message or command..."

        self.prompt_display.hide_prompt()
        status_bar = self.query_one(StatusBar)
        status_bar.refresh_display()

        input_container = self.query_one("#input_container")
        input_container.remove_class("capture-mode")

        # Restore activity indicator - agent is continuing after the prompt.
        # _update_capture_ui hid it while waiting for input, now we resume.
        # The THINKING state will be replaced by IDLE when process_command ends.
        self.app.post_message(ActivityStateChange(ActivityState.THINKING))

    def update_activity(self, message: ActivityStateChange) -> None:
        """Update activity indicator based on state change message.

        Args:
            message: ActivityStateChange message with state, message, and elapsed_ms
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

    def update_metrics(self, message: "MetricsUpdate") -> None:
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


