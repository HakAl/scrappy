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
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Input, RichLog, Label, ProgressBar, Button
from textual.containers import Container, Vertical, Horizontal
from textual.reactive import reactive
from textual import work

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


class ShowPromptModal(Message):
    """Message to show prompt modal in main thread.

    Posted from worker thread via ThreadSafeAsyncBridge to request
    user input through a modal dialog.
    """

    def __init__(self, prompt_id: str, message: str, default: str = "") -> None:
        """Initialize prompt modal message.

        Args:
            prompt_id: Unique ID to correlate request with response
            message: Prompt message to display
            default: Default value for input
        """
        super().__init__()
        self.prompt_id = prompt_id
        self.message = message
        self.default = default


class ShowConfirmModal(Message):
    """Message to show confirmation modal in main thread.

    Posted from worker thread via ThreadSafeAsyncBridge to request
    yes/no confirmation through a modal dialog.
    """

    def __init__(self, prompt_id: str, question: str) -> None:
        """Initialize confirm modal message.

        Args:
            prompt_id: Unique ID to correlate request with response
            question: Question to display for confirmation
        """
        super().__init__()
        self.prompt_id = prompt_id
        self.question = question


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

        # Post message to main thread to show modal
        self.app.post_message(ShowPromptModal(prompt_id, message, default))

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

        # Post message to main thread to show modal
        self.app.post_message(ShowConfirmModal(prompt_id, question))

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
            self._prompt_results[prompt_id] = result
            self._pending_prompts[prompt_id].set()  # Unblock worker thread


class PromptScreen(ModalScreen[str]):
    """Modal dialog for user input.

    Displays a prompt message with an input field. User can submit
    with Enter or the Submit button, or cancel with the Cancel button.
    """

    DEFAULT_CSS = """
    PromptScreen {
        align: center middle;
    }

    PromptScreen > Container {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $panel-bg;
        padding: 1;
        layout: vertical;
    }

    PromptScreen Label {
        margin-bottom: 1;
    }

    PromptScreen Input {
        margin: 1 0;
    }

    PromptScreen #button_row {
        height: auto;
        align-horizontal: center;
        margin-top: 1;
    }

    PromptScreen Button {
        margin: 0 1;
    }
    """

    def __init__(self, prompt_message: str, default: str = "") -> None:
        """Initialize prompt screen.

        Args:
            prompt_message: Message to display to user
            default: Default input value
        """
        super().__init__()
        self.prompt_message = prompt_message
        self.default = default

    def compose(self) -> ComposeResult:
        """Compose the prompt dialog."""
        with Container():
            yield Label(self.prompt_message, id="prompt_label")
            yield Input(value=self.default, id="modal_input")
            with Horizontal(id="button_row"):
                yield Button("Submit", variant="primary", id="submit")
                yield Button("Cancel", variant="default", id="cancel")

    def on_mount(self) -> None:
        """Focus input on mount."""
        self.query_one(Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "submit":
            value = self.query_one(Input).value
            self.dismiss(value)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Allow Enter key to submit."""
        self.dismiss(event.value)


class ConfirmScreen(ModalScreen[bool]):
    """Modal dialog for confirmation.

    Displays a question with Yes/No buttons. Returns True for Yes,
    False for No or if dialog is dismissed.
    """

    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
    }

    ConfirmScreen > Container {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $panel-bg;
        padding: 1;
        layout: vertical;
    }

    ConfirmScreen Label {
        margin-bottom: 1;
    }

    ConfirmScreen #button_row {
        height: auto;
        align-horizontal: center;
        margin-top: 1;
    }

    ConfirmScreen Button {
        margin: 0 1;
    }
    """

    def __init__(self, question: str) -> None:
        """Initialize confirm screen.

        Args:
            question: Question to display for confirmation
        """
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        """Compose the confirm dialog."""
        with Container():
            yield Label(self.question, id="question_label")
            with Horizontal(id="button_row"):
                yield Button("Yes", variant="success", id="yes")
                yield Button("No", variant="error", id="no")

    def on_mount(self) -> None:
        """Focus Yes button on mount."""
        self.query_one("#yes", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        self.dismiss(event.button.id == "yes")


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
    - Native terminal copy/paste support (mouse disabled)
    - Thread-safe message-based output routing via worker thread
    """

    # Disable mouse to restore native terminal copy/paste
    ENABLE_MOUSE = False

    # Use external CSS file for styling
    CSS_PATH = "scrappy.tcss"

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

        # Phase 3: Initialize thread-safe async bridge for modal dialogs
        self.bridge = ThreadSafeAsyncBridge(self)

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
            yield Input(
                id="input",
                placeholder="Type your message or command...",
            )

        # Dynamic status bar (shows/hides based on active components)
        yield StatusBar()

    def on_mount(self) -> None:
        """Called when app starts."""
        # Cache input reference and focus immediately
        self._input = self.query_one(Input)
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

    def on_click(self, event) -> None:
        """Refocus input when clicking anywhere that's not the input field.

        This allows users to click anywhere in the terminal and immediately
        start typing without explicitly clicking the input field.

        Args:
            event: The click event
        """
        # Get the widget that was clicked
        clicked_widget = event.widget if hasattr(event, 'widget') else None

        # Refocus input if clicking anything except the input or log
        if clicked_widget is not None and not isinstance(clicked_widget, Input):
            self._input.focus()
            # Clear selection by setting cursor position after focus completes
            def clear_selection():
                self._input.cursor_position = len(self._input.value)
            self.call_after_refresh(clear_selection)

    def on_key(self, event) -> None:
        """Auto-focus input when user starts typing.

        This allows users to simply start typing from anywhere, and the
        input will automatically receive focus. Respects focus on other
        interactive widgets (like scrollable logs).

        Args:
            event: The key event
        """
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

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input submission.

        Args:
            event: The input submission event containing user text
        """
        user_input = event.value.strip()

        if not user_input:
            return

        # Clear input immediately
        self._input.value = ""

        # Process in worker thread
        self.process_command(user_input)

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

    def on_show_prompt_modal(self, message: ShowPromptModal) -> None:
        """Handle prompt request from worker thread.

        Shows PromptScreen modal and provides result to bridge when dismissed.

        Args:
            message: The ShowPromptModal message with prompt details
        """
        def handle_result(result: Optional[str]) -> None:
            # Use default if user cancelled (None result)
            final_result = result if result is not None else message.default
            self.bridge.provide_result(message.prompt_id, final_result)

        self.push_screen(
            PromptScreen(message.message, message.default),
            handle_result
        )

    def on_show_confirm_modal(self, message: ShowConfirmModal) -> None:
        """Handle confirmation request from worker thread.

        Shows ConfirmScreen modal and provides result to bridge when dismissed.
        Treats None (escape/cancel) as False.

        Args:
            message: The ShowConfirmModal message with confirmation details
        """
        def handle_result(result: Optional[bool]) -> None:
            # Treat None (escape/cancel) as False
            final_result = result if result is not None else False
            self.bridge.provide_result(message.prompt_id, final_result)

        self.push_screen(
            ConfirmScreen(message.question),
            handle_result
        )
