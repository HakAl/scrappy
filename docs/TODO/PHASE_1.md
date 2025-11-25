Issue: Input Unusable After Classification (CRITICAL)
Description: User enters query -> many sync async calls (tools, http, routing) -> app becomes unusable, output never returns to UI
We can see all background processes work, but no output.

Root Cause: unknown

Root Cause Analysis - Textual App Freeze

  I've identified multiple blocking input() calls that can cause the Textual app to freeze when running in worker
  threads. These are the root causes:

  Critical Issues Found

  1. TaskRouter Direct Command Confirmation (src/task_router/router.py:496)

  if action == "confirm":
      if self.verbose:
          self.output_handler.log_info(f"Command: {task.extracted_command}")
          response = input("  Execute? [y/N]: ").strip().lower()  # BLOCKS FOREVER

  When a task is classified as DIRECT_COMMAND and requires confirmation, this calls input() directly. In a Textual
  worker thread, this will block forever waiting for stdin that never comes.

  2. InteractiveClarifier (src/task_router/intent_clarifier.py:80)

  def clarify(self, task: ClassifiedTask) -> ClassifiedTask:
      # ...
      try:
          choice = self.input_fn("\nChoice [1/2/3]: ").strip()  # Default is input()

  The InteractiveClarifier is the default clarifier (line 92 of router.py). When a task has low confidence (< 0.65)
  and clarify_on_low_confidence is True, this will be called, blocking forever.

  The flow that triggers this:
  1. User types a query in Textual
  2. Worker thread processes via process_command()
  3. _process_input() calls task_router.handle_auto_route()
  4. router.route() classifies the task
  5. If confidence is low, _clarify_intent() is called
  6. InteractiveClarifier.clarify() calls input() - BLOCKED

  3. Why This Only Happens with Auto-Route (Not Direct Chat)

  Direct chat (orchestrator.delegate()) doesn't go through the TaskRouter at all - it goes straight to the
  DelegationManager. The TaskRouter is only used when:
  - auto_route_mode is enabled, OR
  - The query is detected as needing tools (needs_tool_support(user_input))

  This explains why "direct chat works but handle_auto_route doesn't".

  Solution

  The CLITaskRouterHandler._create_default_router() needs to inject a non-blocking clarifier and disable the direct
  input() confirmation:

  def _create_default_router(self) -> TaskRouter:
      """Create default task router with CLI IO integration."""
      from src.task_router import CLIIOOutputHandler, AutoClarifier  # Add AutoClarifier

      return TaskRouter(
          orchestrator=self.orchestrator,
          project_root=self.project_root,
          auto_confirm_direct=True,  # Skip the input() confirmation
          verbose=True,
          output_handler=CLIIOOutputHandler(self.io),
          intent_clarifier=AutoClarifier(default_action="escalate")  # Non-blocking
      )

  Or better yet, the Textual mode should detect when it's running and configure appropriately.

  Secondary Issue: RichOutputHandler._console Not Initialized

  In src/task_router/output_handler.py:400, the RichOutputHandler class references self._console but never
  initializes it:
  def log_classification(self, ...):
      # ...
      self._console.print(table)  # AttributeError: 'RichOutputHandler' has no attribute '_console'

  This would cause an error if RichOutputHandler is ever used.



---
  
https://textual.textualize.io/guide/workers/#thread-workers

Thread workers¶
In previous examples we used run_worker or the work decorator in conjunction with coroutines. This works well if you are using an async API like httpx, but if your API doesn't support async you may need to use threads.

What are threads?

Threads are a form of concurrency supplied by your Operating System. Threads allow your code to run more than a single function simultaneously.

You can create threads by setting thread=True on the run_worker method or the work decorator. The API for thread workers is identical to async workers, but there are a few differences you need to be aware of when writing code for thread workers.

The first difference is that you should avoid calling methods on your UI directly from a threaded worker, or setting reactive variables. You can work around this with the App.call_from_thread method which runs your function from the main thread.

The second difference is that you can't cancel threads in the same way as coroutines, but you can manually check if the worker was cancelled.

Let's demonstrate thread workers by replacing httpx with urllib.request (in the standard library). The urllib module is not async aware, so we will need to use threads:

weather05.py

from urllib.parse import quote
from urllib.request import Request, urlopen

from rich.text import Text

from textual import work
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Static
from textual.worker import Worker, get_current_worker


class WeatherApp(App):
    """App to display the current weather."""

    CSS_PATH = "weather.tcss"

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Enter a City")
        with VerticalScroll(id="weather-container"):
            yield Static(id="weather")

    async def on_input_changed(self, message: Input.Changed) -> None:
        """Called when the input changes"""
        self.update_weather(message.value)

    @work(exclusive=True, thread=True)
    def update_weather(self, city: str) -> None:
        """Update the weather for the given city."""
        weather_widget = self.query_one("#weather", Static)
        worker = get_current_worker()
        if city:
            # Query the network API
            url = f"https://wttr.in/{quote(city)}"
            request = Request(url)
            request.add_header("User-agent", "CURL")
            response_text = urlopen(request).read().decode("utf-8")
            weather = Text.from_ansi(response_text)
            if not worker.is_cancelled:
                self.call_from_thread(weather_widget.update, weather)
        else:
            # No city, so just blank out the weather
            if not worker.is_cancelled:
                self.call_from_thread(weather_widget.update, "")

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Called when the worker state changes."""
        self.log(event)


if __name__ == "__main__":
    app = WeatherApp()
    app.run()
In this example, the update_weather is not asynchronous (i.e. a regular function). The @work decorator has thread=True which makes it a thread worker. Note the use of get_current_worker which the function uses to check if it has been cancelled or not.

Important

Textual will raise an exception if you add the work decorator to a regular function without thread=True.

Posting messages¶
Most Textual functions are not thread-safe which means you will need to use call_from_thread to run them from a thread worker. An exception would be post_message which is thread-safe. If your worker needs to make multiple updates to the UI, it is a good idea to send custom messages and let the message handler update the state of the UI.


---
App Code

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

interactive_mode.process_input:

    def _process_input(self, user_input: str) -> bool:
        """
        Process user input.

        Handles both slash commands and regular chat input. For commands,
        delegates to command_router. For chat, uses auto-routing, smart mode,
        or direct LLM delegation based on current settings.

        Args:
            user_input: The user's input string.

        Returns:
            bool: True to continue the loop, False to exit.

        Side Effects:
            - Commands are routed to command_router.route()
            - Chat input is:
              - Routed through task_router if auto_route_mode is enabled
              - Processed by smart_query if smart_mode is enabled
              - Sent to orchestrator.delegate() otherwise
            - Displays response to console with metadata
            - May use tools for research if query requires it
            - Prompts for task progression if plan is active

        State Changes:
            - Appends user message to conversation_history
            - Appends assistant response to conversation_history
            - Command routing may change various state attributes
        """
        io = self.io

        if not user_input:
            return True

        # Handle commands
        if self.input_handler.is_command(user_input):
            import logging
            logger = logging.getLogger(__name__)
            cmd, args = self.input_handler.parse_command(user_input)
            logger.debug(f"[_process_input] Routing command: {cmd}, args: {args}")
            result = self.command_router.route(cmd, args)
            logger.debug(f"[_process_input] Command result: {result}")
            return result

        # Regular chat
        self.session_context.conversation_history.append({
            "role": "user",
            "content": user_input
        })

        # Use auto-routing if enabled
        if self.session_context.auto_route_mode:
            result = self.task_router.handle_auto_route(user_input)
            response_content = result.output if result.success else f"Error: {result.error}"
            response = type('Response', (), {'content': response_content})()
        # Use smart mode if enabled
        elif self.session_context.smart_mode:
            response = self.smart.smart_query(user_input)
        else:
            # Check if this looks like a research task that needs tools
            needs_tools = needs_tool_support(user_input)

            if needs_tools:
                # Use task router with tool support
                io.secho("Using tools for research...", fg="cyan")
                result = self.task_router.handle_auto_route(user_input)
                response_content = result.output if result.success else f"Error: {result.error}"
                response = type('Response', (), {'content': response_content})()

                # Show tool usage info if available
                if hasattr(result, 'metadata') and result.metadata:
                    tool_calls = result.metadata.get('tool_calls', [])
                    if tool_calls:
                        io.secho(f"  Tools used: {[tc['tool'] for tc in tool_calls]}", fg="cyan")

                io.secho("Assistant: ", fg="blue", bold=True)
                io.echo(response.content)

                # Show execution metadata
                provider_used = getattr(result, 'provider_used', None) or "unknown"
                tokens = getattr(result, 'tokens_used', None) or 0
                exec_time = getattr(result, 'execution_time', None) or 0
                # Ensure numeric values for formatting
                try:
                    tokens = int(tokens)
                    exec_time_ms = float(exec_time) * 1000
                except (TypeError, ValueError):
                    tokens = 0
                    exec_time_ms = 0
                io.secho(
                    f"[{provider_used} | {tokens} tokens | {exec_time_ms:.0f}ms]",
                    fg="cyan"
                )
            else:
                io.secho("Assistant: ", fg="blue", bold=True, nl=False)

                response = self.orchestrator.delegate(
                    self.orchestrator.brain,
                    user_input,
                    system_prompt="You are a helpful AI assistant. Be concise and informative."
                )

                io.echo(response.content)
                io.secho(
                    f"[{response.provider}/{response.model} | {response.tokens_used} tokens | {response.latency_ms:.0f}ms]",
                    fg="cyan"
                )
        io.echo()

        self.session_context.conversation_history.append({
            "role": "assistant",
            "content": response.content
        })

        # Prompt for task progression if plan is active
        if self.state_manager.plan_active:
            self.state_manager.prompt_task_progression(io)

        return True