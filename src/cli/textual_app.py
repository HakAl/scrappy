"""
Textual-based TUI application for Scrappy CLI.

Provides an interactive terminal UI using the Textual framework,
wrapping the existing InteractiveMode with a modern UI.
"""

from typing import TYPE_CHECKING, Any, Optional, Dict, List
import logging
import threading
import uuid
from queue import Queue, Empty
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widgets import TextArea, RichLog, Label, ProgressBar
from textual.containers import Container, Vertical, Horizontal
from textual.reactive import reactive
from textual import work
import pyperclip

from src.infrastructure.output_mode import OutputModeContext
from .input_capture import InputCaptureManager, InputRequest


if TYPE_CHECKING:
    from .interactive import InteractiveMode
    from .protocols import StatusComponentProtocol

logger = logging.getLogger(__name__)


class WriteOutput(Message):
    """Message for thread-safe output to RichLog widget.

    This message can be posted from any thread and will be handled
    on the main thread by the Textual app.
    """

    def __init__(self, content: str) -> None:
        """Initialize output message.

        Args:
            content: The text content to write (with Rich markup if applicable)
        """
        super().__init__()
        self.content = content


class WriteRenderable(Message):
    """Message for posting Rich renderables to RichLog widget.

    This message handles Rich objects (Panel, Table, Text, etc.) that
    preserve formatting, colors, and structure. Thread-safe like WriteOutput.
    """

    def __init__(self, renderable: Any) -> None:
        """Initialize renderable message.

        Args:
            renderable: Rich renderable object (Panel, Table, Text, etc.)
        """
        super().__init__()
        self.renderable = renderable


class RequestInlineInput(Message):
    """Message to request inline input capture.

    Posted from worker thread via ThreadSafeAsyncBridge to request
    user input through inline capture (replaces modal dialogs).
    """

    def __init__(
        self,
        prompt_id: str,
        message: str,
        input_type: str,
        default: str = ""
    ) -> None:
        """Initialize inline input request message.

        Args:
            prompt_id: Unique ID to correlate request with response
            message: Prompt message to display
            input_type: Either "prompt" or "confirm"
            default: Default value for prompts
        """
        super().__init__()
        self.prompt_id = prompt_id
        self.message = message
        self.input_type = input_type
        self.default = default


class ThreadSafeAsyncBridge:
    """Allows worker thread to block while waiting for async result from main thread.

    This bridge solves the threading problem where InteractiveMode._process_input()
    runs in a worker thread (via @work decorator) but needs to show modal dialogs
    that run on the main thread's event loop.

    Pattern:
    1. Worker thread calls blocking_prompt() or blocking_confirm()
    2. Bridge posts message to main thread
    3. Worker thread blocks on threading.Event
    4. Main thread shows modal, gets result
    5. Main thread calls provide_result()
    6. Worker thread unblocks with result
    """

    def __init__(self, app: "ScrappyApp") -> None:
        """Initialize bridge with app reference.

        Args:
            app: The ScrappyApp instance to post messages to
        """
        self.app = app
        self._pending_prompts: Dict[str, threading.Event] = {}
        self._prompt_results: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def blocking_prompt(self, message: str, default: str = "") -> str:
        """Called from worker thread - blocks until main thread provides result.

        Args:
            message: Prompt message to display
            default: Default value if user cancels

        Returns:
            User input string

        Raises:
            RuntimeError: If called from main thread (would cause deadlock)
        """
        # DEADLOCK GUARD
        if threading.current_thread() is threading.main_thread():
            raise RuntimeError(
                "CRITICAL ERROR: blocking_prompt() called from Main Thread! "
                "This will cause a deadlock. Ensure calls to input/prompt "
                "are running inside a @work thread."
            )

        prompt_id = str(uuid.uuid4())

        with self._lock:
            event = threading.Event()
            self._pending_prompts[prompt_id] = event

        # Post message to main thread for inline input capture
        self.app.post_message(RequestInlineInput(prompt_id, message, "prompt", default))

        # BLOCK this worker thread until result ready
        event.wait()

        # Retrieve result and cleanup
        with self._lock:
            result = self._prompt_results.pop(prompt_id)
            del self._pending_prompts[prompt_id]

        return result

    def blocking_confirm(self, question: str) -> bool:
        """Called from worker thread - blocks until main thread provides result.

        Args:
            question: Confirmation question to display

        Returns:
            True if user confirmed, False otherwise

        Raises:
            RuntimeError: If called from main thread (would cause deadlock)
        """
        # DEADLOCK GUARD
        if threading.current_thread() is threading.main_thread():
            raise RuntimeError(
                "CRITICAL ERROR: blocking_confirm() called from Main Thread! "
                "This will cause a deadlock. Ensure calls to confirm "
                "are running inside a @work thread."
            )

        prompt_id = str(uuid.uuid4())

        with self._lock:
            event = threading.Event()
            self._pending_prompts[prompt_id] = event

        # Post message to main thread for inline input capture
        self.app.post_message(RequestInlineInput(prompt_id, question, "confirm"))

        # BLOCK this worker thread until result ready
        event.wait()

        # Retrieve result and cleanup
        with self._lock:
            result = self._prompt_results.pop(prompt_id)
            del self._pending_prompts[prompt_id]

        return result

    def provide_result(self, prompt_id: str, result: Any) -> None:
        """Called from main thread after modal dismisses.

        Args:
            prompt_id: ID of the prompt being answered
            result: The result value (str for prompt, bool for confirm)
        """
        with self._lock:
            if prompt_id not in self._pending_prompts:
                # Stale prompt - already cleaned up or never registered
                logger.warning(f"provide_result: unknown prompt_id {prompt_id}, ignoring")
                return
            self._prompt_results[prompt_id] = result
            self._pending_prompts[prompt_id].set()  # Unblock worker thread


class TextualOutputAdapter:
    """Adapter that implements OutputSink for Textual App.

    This adapter bridges the OutputSink protocol to a thread-safe queue.
    The Textual app consumes from this queue using a worker thread.

    No circular dependency - adapter has no knowledge of the app.
    """

    def __init__(self):
        """Initialize adapter with message queue."""
        self._queue: Queue[tuple[str, Any]] = Queue()

    def post_output(self, content: str) -> None:
        """Post plain text to queue.

        Args:
            content: Plain text content to write
        """
        self._queue.put(('output', content))

    def post_renderable(self, obj: Any) -> None:
        """Post Rich renderable to queue.

        Args:
            obj: Rich renderable object (Panel, Table, Text, etc.)
        """
        self._queue.put(('renderable', obj))

    def get_message(self, block: bool = True, timeout: Optional[float] = None) -> Optional[tuple[str, Any]]:
        """Get next message from queue.

        Args:
            block: Whether to block waiting for message
            timeout: Optional timeout in seconds

        Returns:
            Tuple of (type, content) where type is 'output' or 'renderable',
            or None if queue is empty and not blocking
        """
        try:
            return self._queue.get(block=block, timeout=timeout)
        except Empty:
            return None


class ProgressIndicator:
    """Shows indexing/processing progress in the status bar.

    Caches widget instance to prevent flickering on updates.
    Implements StatusComponentProtocol.
    """

    def __init__(self) -> None:
        """Initialize progress indicator with default values."""
        self._progress: int = 0
        self._total: int = 0
        self._message: str = ""
        self._active: bool = False
        self._widget: Optional[Horizontal] = None
        self._label: Optional[Label] = None
        self._bar: Optional[ProgressBar] = None

    @property
    def component_id(self) -> str:
        """Unique identifier for this component."""
        return "progress_indicator"

    @property
    def is_visible(self) -> bool:
        """Whether this component should be displayed."""
        return self._active

    @property
    def widget(self) -> Horizontal:
        """Return cached widget, creating if needed."""
        if self._widget is None:
            self._label = Label(self._message, id="progress_label")
            self._bar = ProgressBar(total=self._total or 100, id="progress_bar")
            self._widget = Horizontal(
                self._label,
                self._bar,
                id=self.component_id
            )
        return self._widget

    def update_widget(self) -> None:
        """Update widget state in place."""
        if self._label is not None:
            self._label.update(self._message)
        if self._bar is not None:
            self._bar.total = self._total or 100
            self._bar.progress = self._progress

    def update(self, progress: int, total: int, message: str) -> None:
        """Update progress state.

        Args:
            progress: Current progress value
            total: Total value for progress
            message: Message to display alongside progress
        """
        self._progress = progress
        self._total = total
        self._message = message
        self._active = True
        self.update_widget()

    def complete(self) -> None:
        """Mark progress as complete - will hide the indicator."""
        self._active = False


class TokenCounter:
    """Shows token usage for current session in the status bar.

    Caches widget instance to prevent flickering on updates.
    Implements StatusComponentProtocol.
    """

    def __init__(self) -> None:
        """Initialize token counter with default values."""
        self._tokens: int = 0
        self._visible: bool = False
        self._widget: Optional[Label] = None

    @property
    def component_id(self) -> str:
        """Unique identifier for this component."""
        return "token_counter"

    @property
    def is_visible(self) -> bool:
        """Whether this component should be displayed."""
        return self._visible and self._tokens > 0

    @property
    def widget(self) -> Label:
        """Return cached widget, creating if needed."""
        if self._widget is None:
            self._widget = Label(f"Tokens: {self._tokens:,}", id=self.component_id)
        return self._widget

    def update_widget(self) -> None:
        """Update widget state in place."""
        if self._widget is not None:
            self._widget.update(f"Tokens: {self._tokens:,}")

    def update(self, tokens: int) -> None:
        """Update token count.

        Args:
            tokens: Current token count to display
        """
        self._tokens = tokens
        self._visible = True
        self.update_widget()

    def hide(self) -> None:
        """Hide the token counter."""
        self._visible = False


class StatusBar(Container):
    """Dynamic status bar that shows/hides based on active components.

    Single Responsibility: Each method has one job:
    - _get_visible_components(): Filter logic
    - _update_visibility(): CSS class toggling
    - _mount_components(): Widget mounting
    - refresh_display(): Orchestrates the above
    """

    show_status = reactive(False)

    def __init__(self) -> None:
        """Initialize status bar with empty components dict."""
        super().__init__(id="status_bar")
        self.components: Dict[str, "StatusComponentProtocol"] = {}
        self._mounted_ids: set[str] = set()

    def compose(self) -> ComposeResult:
        """Compose the status bar layout."""
        yield Vertical(id="status_content")

    def register_component(self, component: "StatusComponentProtocol") -> None:
        """Add a status component.

        Args:
            component: Component implementing StatusComponentProtocol
        """
        self.components[component.component_id] = component
        self.refresh_display()

    def unregister_component(self, component_id: str) -> None:
        """Remove a status component.

        Args:
            component_id: ID of the component to remove
        """
        if component_id in self.components:
            del self.components[component_id]
            self._mounted_ids.discard(component_id)
            self.refresh_display()

    def _get_visible_components(self) -> List["StatusComponentProtocol"]:
        """Return list of components that should be visible."""
        return [c for c in self.components.values() if c.is_visible]

    def _update_visibility(self, has_visible: bool) -> None:
        """Toggle CSS class based on whether any components are visible.

        Args:
            has_visible: True if at least one component is visible
        """
        self.show_status = has_visible
        if has_visible:
            self.add_class("show")
        else:
            self.remove_class("show")

    def _mount_components(self, visible: List["StatusComponentProtocol"]) -> None:
        """Mount/unmount components as needed.

        Only mounts components that aren't already mounted.
        Only unmounts components that are no longer visible.
        Uses cached widgets from components (no recreation).

        Args:
            visible: List of visible components to mount
        """
        try:
            content = self.query_one("#status_content", Vertical)
        except Exception:
            return  # Status content not ready yet

        visible_ids = {c.component_id for c in visible}

        # Unmount components no longer visible
        for comp_id in self._mounted_ids - visible_ids:
            try:
                widget = content.query_one(f"#{comp_id}")
                widget.remove()
            except Exception:
                pass  # Widget already removed

        # Mount newly visible components (using cached widgets)
        for component in visible:
            if component.component_id not in self._mounted_ids:
                content.mount(component.widget)

        # Update all visible component widgets
        for component in visible:
            component.update_widget()

        self._mounted_ids = visible_ids

    def refresh_display(self) -> None:
        """Update visible components - orchestrates visibility and mounting."""
        visible = self._get_visible_components()
        self._update_visibility(len(visible) > 0)
        self._mount_components(visible)


class ScrappyApp(App):
    """Main Textual application for interactive mode.

    Provides a terminal UI with:
    - Scrollable output area for conversation history (RichLog)
    - Input field for user messages and commands
    - Dynamic status bar for progress indicators and token counters
    - Right-click paste support via pyperclip
    - Thread-safe message-based output routing via worker thread
    """

    # Use external CSS file for styling
    CSS_PATH = "scrappy.tcss"

    # Priority binding intercepts Enter before TextArea gets it
    BINDINGS = [
        Binding("enter", "submit_input", "Submit", priority=True),
    ]

    def __init__(self, interactive_mode: "InteractiveMode", output_adapter: TextualOutputAdapter):
        """Initialize the Textual app with InteractiveMode.

        Args:
            interactive_mode: The InteractiveMode instance with UnifiedIO
            output_adapter: The TextualOutputAdapter to consume messages from
        """
        super().__init__()
        self.interactive_mode = interactive_mode
        self.output_adapter = output_adapter
        self._should_stop_consumer = False

        # Status bar components (created here, registered in on_mount)
        self.progress_indicator = ProgressIndicator()
        self.token_counter = TokenCounter()

        # Thread-safe async bridge for prompts/confirms
        self.bridge = ThreadSafeAsyncBridge(self)

        # Input capture manager for inline prompts/confirms (replaces modals)
        self.capture_manager = InputCaptureManager(self.bridge)

    def compose(self) -> ComposeResult:
        """Create child widgets.

        Yields:
            Widget instances for the app layout
        """
        # Scrollable output area
        with Container(id="output_container"):
            yield RichLog(
                id="output",
                highlight=True,
                markup=True,
                auto_scroll=True,
                wrap=True
            )

        # Fixed input area at bottom
        with Container(id="input_container"):
            yield Label(">", id="input_prompt")
            yield TextArea(
                id="input",
                language=None,  # Plain text, no syntax highlighting
                show_line_numbers=False,
                soft_wrap=True,
            )

        # Dynamic status bar (shows/hides based on active components)
        yield StatusBar()

    def on_mount(self) -> None:
        """Called when app starts."""
        # Set TUI mode context so all components know to route through Textual
        OutputModeContext.set_tui_mode(True, self.output_adapter)

        # Cache input reference and focus
        self._input = self.query_one(TextArea)
        self._input.focus()

        # Register status components with the status bar
        status_bar = self.query_one(StatusBar)
        status_bar.register_component(self.progress_indicator)
        status_bar.register_component(self.token_counter)

        # Start worker thread to consume output queue
        self.consume_output_queue()

        # Display welcome banner
        from src.cli.interactive_banner import display_banner
        display_banner(self.interactive_mode.io)

    def on_unmount(self) -> None:
        """Called when app is about to close."""
        # Clear TUI mode context
        OutputModeContext.set_tui_mode(False)
        self._should_stop_consumer = True

    def on_click(self, event) -> None:
        """Refocus input when clicking anywhere that's not the input field.

        This allows users to click anywhere in the terminal and immediately
        start typing without explicitly clicking the input field.

        Args:
            event: The click event
        """
        # Right-click (button=3) pastes from clipboard
        if hasattr(event, 'button') and event.button == 3:
            try:
                text = pyperclip.paste()
                if text:
                    self._input.replace(
                        text,
                        self._input.selection.start,
                        self._input.selection.end,
                        maintain_selection_offset=True
                    )
            except Exception as e:
                logger.warning(f"Failed to paste from clipboard: {e}")
            return

        # Get the widget that was clicked
        clicked_widget = event.widget if hasattr(event, 'widget') else None

        # Refocus input if clicking anything except the input or log
        if clicked_widget is not None and not isinstance(clicked_widget, TextArea):
            self._input.focus()
            # Clear selection by setting cursor position after focus completes
            def clear_selection():
                # TextArea uses (row, col) tuple for cursor_location
                # Move to end of document
                end_location = self._input.document.end
                self._input.cursor_location = end_location
            self.call_after_refresh(clear_selection)

    def on_key(self, event) -> None:
        """Handle key events.

        - Escape/Ctrl+C during capture mode cancels and returns default
        - Up-arrow is blocked during capture mode (no history navigation)
        - Auto-focus input when user starts typing from anywhere

        Args:
            event: The key event
        """
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
        if self._input.has_focus:
            return

        # Don't steal focus from other interactive widgets
        focused = self.screen.focused
        if focused is not None and focused != self.screen:
            return

        # Auto-focus on printable characters
        if event.is_printable:
            self._input.focus()

    @work(exclusive=False, thread=True)
    def consume_output_queue(self) -> None:
        """Worker thread that consumes output queue and posts to UI.

        Runs continuously, blocking on queue.get() until messages are available.
        Posts Textual messages to update the UI thread-safely.
        """
        while not self._should_stop_consumer and self.is_running:
            try:
                # Block waiting for next message (with timeout to check stop flag)
                message = self.output_adapter.get_message(block=True, timeout=0.1)

                if message is None:
                    continue

                msg_type, content = message

                # Post to Textual message queue for UI thread
                if msg_type == 'output':
                    self.post_message(WriteOutput(content))
                elif msg_type == 'renderable':
                    self.post_message(WriteRenderable(content))

            except Exception as e:
                logger.exception(f"Error consuming output queue: {e}")

    def action_submit_input(self) -> None:
        """Handle Enter to submit input.

        Handles both normal command input and capture mode input.
        Uses TextArea API (.text and .clear()) instead of Input API.
        """
        user_input = self._input.text.strip()

        # Clear input immediately
        self._input.clear()

        # Handle capture mode
        if self.capture_manager.is_capturing:
            self._handle_captured_input(user_input)
            return

        # Normal command processing
        if not user_input:
            return

        # Process in worker thread
        self.process_command(user_input)

    def _handle_captured_input(self, user_input: str) -> None:
        """Process input captured for prompt/confirm.

        Args:
            user_input: The user's input string
        """
        # Delegate to capture manager
        self.capture_manager.handle_captured_input(user_input)

        # Exit capture mode and check for queued requests
        next_request = self.capture_manager.exit_capture_mode()

        if next_request:
            # Process next queued request
            self.capture_manager.enter_capture_mode(
                next_request.prompt_id,
                next_request.message,
                next_request.input_type,
                next_request.default
            )
            self._update_capture_ui(next_request)
        else:
            # Fully exit capture mode
            self._exit_capture_ui()

    @work(exclusive=True, thread=True)
    def process_command(self, user_input: str) -> None:
        """Process command in worker thread.

        Blocking I/O here won't freeze UI. The @work decorator handles
        threading automatically. Calls InteractiveMode._process_input()
        which handles all command routing and output.

        Args:
            user_input: The user's input string
        """
        try:
            # Call InteractiveMode to process input (handles commands, routing, and output)
            should_continue = self.interactive_mode._process_input(user_input)

            # Exit if requested
            if not should_continue:
                self.exit()

        except Exception as e:
            # Post error (thread-safe via message)
            from rich.text import Text
            error_text = Text(f"Error: {str(e)}", style="red")
            self.output_adapter.post_renderable(error_text)
            logger.exception("Error processing command")

    def on_write_output(self, message: WriteOutput) -> None:
        """Handle plain text output.

        This message handler runs on the main thread, making it safe
        to update widgets even when the message was posted from a worker thread.

        Args:
            message: The WriteOutput message containing content to display
        """
        output = self.query_one("#output", RichLog)
        output.write(message.content)

    def on_write_renderable(self, message: WriteRenderable) -> None:
        """Handle Rich renderable output.

        This message handler runs on the main thread, making it safe
        to update widgets even when the message was posted from a worker thread.

        Args:
            message: The WriteRenderable message containing renderable to display
        """
        output = self.query_one("#output", RichLog)
        output.write(message.renderable)

    def on_request_inline_input(self, message: RequestInlineInput) -> None:
        """Handle inline input request from worker thread.

        Enters capture mode and updates UI for inline input collection.

        Args:
            message: The RequestInlineInput message with input details
        """
        # Delegate to capture manager (handles queuing if already capturing)
        self.capture_manager.enter_capture_mode(
            message.prompt_id,
            message.message,
            message.input_type,
            message.default
        )

        # Only update UI if this is the active capture (not queued)
        if self.capture_manager.is_capturing:
            self._update_capture_ui(message)

    def _update_capture_ui(self, request: "RequestInlineInput | InputRequest") -> None:
        """Update UI for capture mode.

        Args:
            request: The input request with message and type info
        """
        output = self.query_one("#output", RichLog)

        # Display prompt in output area
        if request.input_type == "confirm":
            output.write(f"{request.message} [y/n]")
        else:
            output.write(request.message)

        # Visual feedback - add capture mode class
        input_container = self.query_one("#input_container")
        input_container.add_class("capture-mode")

        # Update placeholder
        if request.input_type == "confirm":
            self._input.placeholder = "Type y or n..."
        else:
            hint = f" (default: {request.default})" if request.default else ""
            self._input.placeholder = f"Enter value{hint}..."

        self._input.focus()

    def _exit_capture_ui(self) -> None:
        """Clean up capture mode UI state."""
        self._input.placeholder = "Type your message or command..."

        # Remove visual feedback
        input_container = self.query_one("#input_container")
        input_container.remove_class("capture-mode")
