"""
Textual-based TUI application for Scrappy CLI.

Provides an interactive terminal UI using the Textual framework,
wrapping the existing InteractiveMode with a modern UI.
"""

from typing import TYPE_CHECKING, Any
import logging
from textual.app import App, ComposeResult
from textual.message import Message
from textual.widgets import Input, RichLog
from textual import work
from src.cli.protocols import OutputSink

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

    This adapter bridges the OutputSink protocol to Textual's message system,
    enabling thread-safe posting of output from worker threads to the UI.
    """

    def __init__(self, app: "ScrappyApp"):
        """Initialize adapter with reference to Textual app.

        Args:
            app: The ScrappyApp instance to post messages to
        """
        self.app = app

    def post_output(self, content: str) -> None:
        """Post plain text via message.

        Args:
            content: Plain text content to write
        """
        self.app.post_message(WriteOutput(content))

    def post_renderable(self, obj: Any) -> None:
        """Post Rich renderable via message.

        Args:
            obj: Rich renderable object (Panel, Table, Text, etc.)
        """
        self.app.post_message(WriteRenderable(obj))


class ScrappyApp(App):
    """Main Textual application for interactive mode.

    Provides a terminal UI with:
    - Scrollable output area for conversation history (RichLog)
    - Input field for user messages and commands
    - Native terminal copy/paste support (mouse disabled)
    - Thread-safe message-based output routing
    """

    # Disable mouse to restore native terminal copy/paste
    ENABLE_MOUSE = False

    CSS = """
    Screen {
        layout: vertical;
    }

    RichLog {
        height: 1fr;
        border: none;
        padding: 1;
        background: transparent;
    }

    Input {
        dock: bottom;
        height: 3;
        border: none;
        background: $surface;
    }
    """

    def __init__(self, orchestrator):
        """Initialize the Textual app with orchestrator.

        Args:
            orchestrator: The orchestrator instance for routing commands
        """
        super().__init__()
        self.orchestrator = orchestrator

        # Create output adapter and IO
        self.output_adapter = TextualOutputAdapter(self)

        # Import TextualIO here to avoid circular import issues
        from src.cli.textual_io import TextualIO
        self.io = TextualIO(self.output_adapter)

    def compose(self) -> ComposeResult:
        """Create child widgets.

        Yields:
            Widget instances for the app layout
        """
        yield RichLog(
            id="output",
            highlight=True,
            markup=True,
            auto_scroll=True,
            wrap=True
        )
        yield Input(
            id="input",
            placeholder="You> Type your message or command..."
        )

    def on_mount(self) -> None:
        """Called when app starts."""
        # Focus input immediately - fixes "click to type" issue
        self.query_one(Input).focus()

        # Display banner
        from src.cli.interactive_banner import display_banner
        display_banner(self.io)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input submission.

        Args:
            event: The input submission event containing user text
        """
        user_input = event.value.strip()

        if not user_input:
            return

        # Clear input immediately
        self.query_one(Input).value = ""

        # Echo user input
        self.io.secho(f"You> {user_input}", fg="cyan")

        # Process in worker thread
        self.process_command(user_input)

    @work(exclusive=True, thread=True)
    def process_command(self, user_input: str) -> None:
        """Process command in worker thread.

        Blocking I/O here won't freeze UI. The @work decorator handles
        threading automatically.

        Args:
            user_input: The user's input string
        """
        try:
            # Check for exit commands
            if user_input.lower() in ["/exit", "/quit", "exit", "quit"]:
                self.exit()
                return

            # Route to orchestrator (blocking I/O is ok here)
            result = self.orchestrator.delegate(user_input)

            # Post result back (thread-safe via message)
            if result:
                self.output_adapter.post_output(result)

        except Exception as e:
            # Post error (thread-safe via message)
            from rich.text import Text
            error_text = Text(f"Error: {str(e)}", style="red")
            self.output_adapter.post_renderable(error_text)

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
