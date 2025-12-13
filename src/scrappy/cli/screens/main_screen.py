"""Main chat interface screen for Scrappy TUI."""

from typing import TYPE_CHECKING, Any, Optional
import logging
import re
import time

from textual.screen import Screen
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import TextArea
from textual import work

from .chat_layout import ChatLayout
from ..input_capture import InputCaptureManager, InputRequest
from ..command_history import CommandHistory, get_default_history_path

if TYPE_CHECKING:
    from ..interactive import InteractiveMode
    from ..textual_app import (
        TextualOutputAdapter,
        ThreadSafeAsyncBridge,
        StatusBar,
        SemanticStatusComponent,
        ActivityStateChange,
        ScrappyApp,
    )
    from scrappy.infrastructure.theme import ThemeProtocol

logger = logging.getLogger(__name__)


class MainAppScreen(Screen):
    """Main chat interface screen.

    Provides:
    - Scrollable output area for conversation history (RichLog)
    - Input field for user messages and commands
    - Dynamic status bar for progress indicators and token counters
    - Command history navigation with up/down arrows
    - Inline capture mode for prompts/confirms
    """

    BINDINGS = [
        Binding("enter", "submit_input", "Submit", priority=True),
        Binding("up", "history_previous", "Previous", priority=True),
        Binding("down", "history_next", "Next", priority=True),
    ]

    def __init__(
        self,
        interactive_mode: "InteractiveMode",
        output_adapter: "TextualOutputAdapter",
        bridge: "ThreadSafeAsyncBridge",
        theme: "ThemeProtocol",
    ):
        """Initialize main screen with dependencies.

        Args:
            interactive_mode: The InteractiveMode instance for command processing
            output_adapter: Adapter for thread-safe output routing
            bridge: Bridge for blocking prompts/confirms from worker threads
            theme: Theme for consistent styling
        """
        super().__init__()
        self.interactive_mode = interactive_mode
        self.output_adapter = output_adapter
        self.bridge = bridge
        self._theme = theme

        # Import here to avoid circular imports
        from ..textual_app import ProgressIndicator, TokenCounter, PromptDisplay

        # Status bar components
        self.progress_indicator = ProgressIndicator()
        self.token_counter = TokenCounter()
        self.prompt_display = PromptDisplay()

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
    def semantic_status(self) -> "SemanticStatusComponent":
        """Lazy-load semantic status component."""
        if not hasattr(self, '_semantic_status'):
            from ..textual_app import SemanticStatusComponent
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
        from ..textual_app import StatusBar

        # Get layout and focus input
        self._layout = self.query_one(ChatLayout)
        self._layout.focus_input()

        # Register status components with the status bar
        status_bar = self.query_one(StatusBar)
        status_bar.register_component(self.progress_indicator)
        status_bar.register_component(self.token_counter)
        status_bar.register_component(self.prompt_display)
        status_bar.register_component(self.semantic_status)

        # Display welcome banner
        from scrappy.cli.interactive_banner import display_banner
        display_banner(self.interactive_mode.io)

    def on_click(self, event) -> None:
        """Refocus input when clicking anywhere except input field."""
        import pyperclip

        if self._layout is None:
            return

        # Right-click (button=3) pastes from clipboard
        if hasattr(event, 'button') and event.button == 3:
            try:
                text = pyperclip.paste()
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
        if clicked_widget is not None and not isinstance(clicked_widget, TextArea):
            self._layout.focus_input()
            # Clear selection by moving to end
            def clear_selection():
                end_location = self._layout.input.document.end
                self._layout.input.cursor_location = end_location
            self.call_after_refresh(clear_selection)

    def on_key(self, event) -> None:
        """Handle key events."""
        if self._layout is None:
            return

        # Handle Escape or Ctrl+C in capture mode
        if self.capture_manager.is_capturing:
            if event.key == "escape" or event.key == "ctrl+c":
                self.capture_manager.cancel()
                self._exit_capture_ui()
                event.stop()
                return

            # Block up-arrow history during capture mode
            if event.key == "up":
                event.stop()
                return

        # Already focused on input, let it handle naturally
        if self._layout.input.has_focus:
            return

        # Don't steal focus from other interactive widgets
        focused = self.focused
        if focused is not None and focused != self:
            return

        # Auto-focus on printable characters
        if event.is_printable:
            self._layout.focus_input()

    def action_submit_input(self) -> None:
        """Handle Enter to submit input."""
        if self._layout is None:
            return

        # Sanitize newlines before processing
        raw_input = self._layout.input.text
        user_input = raw_input.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ').strip()
        user_input = re.sub(r'\s+', ' ', user_input)

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
            self._layout.input.clear()
            self._layout.input.insert(previous)

    def action_history_next(self) -> None:
        """Handle Down arrow to navigate to next history entry."""
        if self.capture_manager.is_capturing or self._layout is None:
            return

        next_entry = self._history.get_next()
        if next_entry is not None:
            self._layout.input.clear()
            self._layout.input.insert(next_entry)
        else:
            self._layout.input.clear()
            if self._history_temp_input:
                self._layout.input.insert(self._history_temp_input)
                self._history_temp_input = ""

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
        from ..textual_app import ActivityStateChange
        from ..protocols import ActivityState

        try:
            self.app.post_message(ActivityStateChange(ActivityState.THINKING))
            should_continue = self.interactive_mode._process_input(user_input)
            if not should_continue:
                self.app.exit()
        except Exception as e:
            from rich.text import Text
            error_text = Text(f"Error: {str(e)}", style=self._theme.error)
            self.output_adapter.post_renderable(error_text)
            logger.exception("Error processing command")
        finally:
            self.app.post_message(ActivityStateChange(ActivityState.IDLE))

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
        from ..textual_app import StatusBar

        # Detect completion from message content
        is_complete = (
            complete
            or message.startswith("Indexing complete")
            or message == "Semantic search ready"
            or message == "Index up to date - no changes detected"
        )

        if is_complete:
            self.progress_indicator.complete()
            # Update semantic status to ready
            if hasattr(self, '_semantic_status'):
                # Extract chunk count from message if present
                chunks = total
                if "Indexing complete" in message:
                    # Try to extract number from "Indexing complete (N files)"
                    import re
                    match = re.search(r'\((\d+)\s+files?\)', message)
                    if match:
                        chunks = int(match.group(1))
                self._semantic_status.set_ready(chunks=chunks)
        else:
            effective_total = total if total > 0 else 100
            self.progress_indicator.update(
                progress=progress,
                total=effective_total,
                message=message
            )
            # Update semantic status to indexing
            if hasattr(self, '_semantic_status'):
                self._semantic_status.set_indexing()

        status_bar = self.query_one(StatusBar)
        status_bar.refresh_display()

    def _update_capture_ui(self, request: "InputRequest") -> None:
        """Update UI for capture mode."""
        from ..textual_app import StatusBar

        if self._layout is None:
            return

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
        else:
            hint = f" (default: {request.default})" if request.default else ""
            self._layout.input.placeholder = f"Enter value{hint}..."

        self._layout.focus_input()

    def _exit_capture_ui(self) -> None:
        """Clean up capture mode UI state."""
        from ..textual_app import StatusBar

        if self._layout is None:
            return

        self._layout.input.placeholder = "Type your message or command..."

        self.prompt_display.hide_prompt()
        status_bar = self.query_one(StatusBar)
        status_bar.refresh_display()

        input_container = self.query_one("#input_container")
        input_container.remove_class("capture-mode")

    def update_activity(self, message: "ActivityStateChange") -> None:
        """Update activity indicator based on state change message.

        Args:
            message: ActivityStateChange message with state, message, and elapsed_ms
        """
        from ..textual_app import ActivityIndicator
        from ..protocols import ActivityState

        try:
            indicator = self.query_one(ActivityIndicator)
        except Exception:
            return

        if message.state == ActivityState.IDLE:
            indicator.hide()
            self._stop_elapsed_timer()
        else:
            if message.elapsed_ms > 0:
                indicator.update_elapsed(message.elapsed_ms)
            else:
                indicator.show(message.state, message.message)
                self._start_elapsed_timer()

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
        from ..textual_app import ActivityIndicator, ActivityStateChange
        from ..protocols import ActivityState

        if self._elapsed_start_time == 0.0:
            return

        elapsed_ms = int((time.time() - self._elapsed_start_time) * 1000)

        try:
            indicator = self.query_one(ActivityIndicator)
            if indicator.is_visible:
                indicator.update_elapsed(elapsed_ms)
        except Exception:
            pass


