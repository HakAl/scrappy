"""
Textual-based TUI application for Scrappy CLI.

Provides an interactive terminal UI using the Textual framework,
wrapping the existing InteractiveMode with a modern UI.
"""

from typing import TYPE_CHECKING, Optional
import asyncio
import logging
import threading
from textual.app import App, ComposeResult
from textual.message import Message
from textual.widgets import Header, Static, Input, RichLog
from textual.containers import ScrollableContainer
from textual.worker import Worker, WorkerState

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


class ScrappyApp(App):
    """Main Textual application for interactive mode.

    Provides a terminal UI with:
    - Scrollable output area for conversation history
    - Input field for user messages and commands
    - Status bar for progress and system messages
    - Keyboard shortcuts for common actions
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+d", "quit", "Quit"),
        ("ctrl+l", "clear", "Clear output"),
    ]

    CSS = """
    Screen {
        background: $surface;
    }

    #output-container {
        height: 1fr;
        background: $surface;
    }

    #output {
        width: 100%;
        padding: 1 2;
        color: $text;
    }

    #status {
        dock: bottom;
        height: 3;
        background: $primary;
        color: $text;
        padding: 0 2;
        content-align: center middle;
    }

    Input {
        dock: bottom;
        border: tall $accent;
    }

    Header {
        background: $primary;
    }
    """

    def __init__(self, interactive_mode: "InteractiveMode"):
        """Initialize the Textual app with InteractiveMode.

        Args:
            interactive_mode: The existing InteractiveMode instance
        """
        super().__init__()
        self.interactive_mode = interactive_mode

    def compose(self) -> ComposeResult:
        """Create the UI layout.

        Yields:
            Widget instances for the app layout
        """
        yield Header(show_clock=False)
        with ScrollableContainer(id="output-container"):
            yield RichLog(id="output", highlight=True, markup=True)
        yield Static("Ready", id="status")
        yield Input(placeholder="Type your message or /command...")

    def on_mount(self) -> None:
        """Handle app startup."""
        import logging
        logger = logging.getLogger(__name__)

        try:
            logger.debug("[ScrappyApp.on_mount] Starting mount")

            # Focus the input field
            input_widget = self.query_one(Input)
            input_widget.focus()
            logger.debug("[ScrappyApp.on_mount] Input focused")

            # Show welcome banner (Rich Panel via console)
            from .interactive_banner import render_welcome_banner

            logger.debug("[ScrappyApp.on_mount] Rendering welcome banner")
            render_welcome_banner(
                self.interactive_mode.io,
                self.interactive_mode.session_context.multiline_mode,
                self.interactive_mode.session_context.auto_route_mode
            )
            logger.debug("[ScrappyApp.on_mount] Banner rendered (no flush needed)")
            logger.debug("[ScrappyApp.on_mount] Mount complete")

        except Exception as e:
            logger.error(f"[ScrappyApp.on_mount] Mount failed: {e}", exc_info=True)
            # Write error directly to output for debugging
            try:
                output = self.query_one("#output", RichLog)
                output.write(f"[red]Error during startup: {e}[/red]\n")
            except:
                pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input submission.

        Args:
            event: The input submission event containing user text
        """
        user_input = event.value.strip()

        # Clear input field
        event.input.value = ""

        # Ignore empty input
        if not user_input:
            return

        # Echo user input
        self.interactive_mode.io.secho(f"> {user_input}", fg="green")

        # Update status to show processing
        self._update_status("Processing...")

        # Run processing in background worker to avoid blocking UI
        self.run_worker(self._process_input_worker(user_input), exclusive=True)

    async def _process_input_worker(self, user_input: str) -> bool:
        """Process input in background worker.

        Args:
            user_input: The user's input string

        Returns:
            bool: True to continue, False to exit
        """
        # DEBUG: Prove worker starts
        logger.debug(f"[Worker] Starting to process: {user_input}")

        # Run the blocking InteractiveMode._process_input in a thread
        should_continue = await asyncio.to_thread(
            self.interactive_mode._process_input,
            user_input
        )

        # DEBUG: Prove worker completes
        logger.debug(f"[Worker] Completed, should_continue={should_continue}")

        # Update status back to Ready
        self._update_status("Ready")

        # Handle quit
        if not should_continue:
            self.exit()

        return should_continue

    def _update_status(self, content: str) -> None:
        """Update the status bar.

        Args:
            content: The status message to display
        """
        status_widget = self.query_one("#status", Static)
        status_widget.update(content)

    def action_quit(self) -> None:
        """Handle quit action (Ctrl+C or Ctrl+D)."""
        # Delegate to InteractiveMode's EOF handler for proper cleanup
        self.interactive_mode._handle_eof()
        self.exit()

    def action_clear(self) -> None:
        """Clear output area (Ctrl+L)."""
        output = self.query_one("#output", RichLog)
        output.clear()

        self._update_status("Output cleared")

    def on_write_output(self, message: WriteOutput) -> None:
        """Handle WriteOutput message - thread-safe output to RichLog.

        This message handler runs on the main thread, making it safe
        to update widgets even when the message was posted from a worker thread.

        Args:
            message: The WriteOutput message containing content to display
        """
        logger.debug(
            f"[WriteOutput Handler] Received message on thread: {threading.current_thread().name}"
        )
        output = self.query_one("#output", RichLog)
        output.write(message.content)
        logger.debug(f"[WriteOutput Handler] Wrote {len(message.content)} chars to RichLog")
