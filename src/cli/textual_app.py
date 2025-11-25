"""
Textual-based TUI application for Scrappy CLI.

Provides an interactive terminal UI using the Textual framework,
wrapping the existing InteractiveMode with a modern UI.
"""

from typing import TYPE_CHECKING, Any, Optional
import logging
from queue import Queue, Empty
from textual.app import App, ComposeResult
from textual.message import Message
from textual.widgets import Input, RichLog, Label
from textual import work

if TYPE_CHECKING:
    from .interactive import InteractiveMode

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


class ScrappyApp(App):
    """Main Textual application for interactive mode.

    Provides a terminal UI with:
    - Scrollable output area for conversation history (RichLog)
    - Input field for user messages and commands
    - Native terminal copy/paste support (mouse disabled)
    - Thread-safe message-based output routing via worker thread
    """

    # Disable mouse to restore native terminal copy/paste
    ENABLE_MOUSE = False

    CSS = """
    Screen {
        layout: vertical;
    }

    #output_container {
        height: 1fr;
        overflow-y: auto;
    }

    RichLog {
        height: 100%;
        border: none;
        padding: 0 1 1 1;
        background: transparent;
        scrollbar-size-vertical: 0;
    }

    #input_container {
        layout: horizontal;
        height: auto;
        background: $surface;
        padding: 1;
    }

    #input_prompt {
        width: 2;
        content-align: center middle;
        color: $accent;
    }

    Input {
        width: 1fr;
        height: 1;
        border: none;
        background: transparent;
    }

    """

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

    def compose(self) -> ComposeResult:
        """Create child widgets.

        Yields:
            Widget instances for the app layout
        """
        from textual.containers import Container

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

    def on_mount(self) -> None:
        """Called when app starts."""
        # Cache input reference and focus immediately
        self._input = self.query_one(Input)
        self._input.focus()

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
