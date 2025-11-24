Phase 1 Issue Fix Plan

  Issue Severity Classification

  CRITICAL (Blocks Usage):
  - Issue #6: Input becomes unusable after classification questions (HTTP + worker thread deadlock)

  HIGH (Major UX Problems):
  - Issue #2: Output covered by input (layout overlap)
  - Issue #4: Must click input to focus (broken focus management)

  MEDIUM (Usability Issues):
  - Issue #3: Session restoration markup artifacts + duplicates
  - Issue #5: Can't copy text from Textual components

  LOW (Cosmetic):
  - Issue #1: No '>' cursor before input placeholder

  ---
  Fix Order (Dependency-Based)

  2. Issue #2 - Fix layout overlap (needed for visibility)
  3. Issue #4 - Fix focus management (needed for usability)
  4. Issue #3 - Fix session restoration messages (cleanup)
  5. Issue #5 - Fix text copying (enable selection)
  6. Issue #1 - Add input cursor prefix (polish)
  7. Issue #6 - Fix HTTP/worker thread deadlock (CRITICAL - fixes app freezing)

  ---
  Issue #2: Output Covered By Input (Layout Overlap)

  Root Cause

  The Input widget with dock: bottom may not be properly reserving space, causing RichLog to extend behind it.

  Fix: Add Explicit Layout Container

  # In textual_app.py, update CSS:
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
      padding: 0 1 1 1;  /* Add bottom padding to prevent overlap */
      background: transparent;
      scrollbar-size-vertical: 1;
  }

  #input_container {
      height: auto;
      background: $surface;
      padding: 1;
      border-top: solid $primary;
  }

  Input {
      height: 1;
      border: none;
      background: transparent;
  }
  """

  # Update compose() method:
  def compose(self) -> ComposeResult:
      from textual.containers import VerticalScroll, Container

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
          yield Input(
              id="input",
              placeholder="Type your message or command...",
          )

  ---
  Issue #4: Must Click Input To Focus

  Root Cause

  Focus is set in on_mount() but may be lost after banner display or output writes.

    Psuedo code rough strategy:

from textual.app import App, ComposeResult
from textual.widgets import Input, Header, Footer, Static
from textual.containers import Container

class ScrappyApp(App):
    BINDINGS = [("ctrl+c", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        # A container to hold text output/banners
        yield Container(id="output_area")
        yield Input(placeholder="Type command here...")
        yield Footer()

    def on_mount(self) -> None:
        """Focus immediately on startup."""
        self.query_one(Input).focus()

    def on_click(self, event) -> None:
        """If user clicks the blank background, refocus input."""
        # Using 'self.screen' ensures we catch clicks on the root background
        if event.target == self.screen:
            self.query_one(Input).focus()

    def on_key(self, event) -> None:
        """Auto-focus input if user starts typing."""
        # If we are focused on the Input, let it handle the key naturally
        if self.query_one(Input).has_focus:
            return

        # If we are scrolling a log or looking at a list, don't steal focus!
        # Only steal focus if the current focus is 'None' or the 'Screen' itself.
        if self.screen.focused is None or self.screen.focused == self.screen:
            if event.is_printable:
                self.query_one(Input).focus()
                # The key event continues to propagate to the newly focused widget

  ---
  Issue #3: Session Restoration Markup Artifacts

  Root Cause

  The input_confirm() method in OutputSinkAdapter (unified_io.py:693) creates a Text object with Rich markup, but
  the markup tags like [dim] are being displayed literally instead of being rendered.

  Fix: Properly Render Markup

  # In unified_io.py, update input_confirm() method (line 684):
  def input_confirm(self, text: str, default: bool = False) -> bool:
      """Auto-approve confirmation with warning (Phase 1 limitation)."""
      is_routine = (
          "restore" in text.lower() and "session" in text.lower()
      ) or default is True

      if is_routine:
          # FIX: Use Text.from_markup() to properly render markup
          message = Text.from_markup(f"{text} [dim](auto-confirmed)[/dim]")
          self._sink.post_renderable(message)
          return True

      # ... rest of method ...

  Also Fix: Duplicate Session Messages

  The "Session restored" message appears multiple times. This suggests session restoration is being called multiple
  times. Need to trace where this is happening:

  # Search for session restoration code
  grep -r "Session restored" src/
  grep -r "restore.*session" src/ -i

  Once identified, add a flag to prevent duplicate restoration:
  # In session_context.py or wherever restoration happens:
  class SessionContext:
      def __init__(self):
          self._restoration_attempted = False

      def restore_session(self):
          if self._restoration_attempted:
              return
          self._restoration_attempted = True
          # ... actual restoration logic ...

  ---
  Issue #5: Can't Copy Text

  Root Cause

  Despite ENABLE_MOUSE = False in textual_app.py:114, text selection may not be working due to Textual's default
  behavior or terminal limitations.

  Fix A: Verify Terminal Mode

  # In textual_app.py, add:
  class ScrappyApp(App):
      ENABLE_MOUSE = False

      def on_mount(self) -> None:
          # Explicitly disable mouse capture
          from textual import log
          log(f"Mouse enabled: {self.mouse_over}")

          # Force terminal into selection mode
          import sys
          if hasattr(sys.stdout, 'fileno'):
              try:
                  # Ensure raw mode isn't interfering
                  import termios
                  import tty
                  fd = sys.stdout.fileno()
                  old_settings = termios.tcgetattr(fd)
                  log(f"Terminal settings: {old_settings}")
              except Exception as e:
                  log(f"Could not check terminal settings: {e}")

          # ... rest of on_mount ...

  Fix B: Add Copy Command

  If native terminal copy doesn't work, add explicit copy command:
  # In textual_app.py:
  from textual.reactive import var

  class ScrappyApp(App):
      BINDINGS = [
          ("ctrl+shift+c", "copy_output", "Copy Last Output"),
      ]

      show_selection_mode = var(False)

      def action_copy_output(self) -> None:
          """Copy last output to clipboard."""
          import pyperclip
          output_widget = self.query_one(RichLog)

          # Get plain text from last N lines
          lines = output_widget.lines[-20:]  # Last 20 lines
          text = "\n".join(str(line.text) for line in lines)

          pyperclip.copy(text)
          self.notify("Copied last 20 lines to clipboard", severity="information")

  ---
  Issue #1: No '>' Cursor Before Input

  Fix: Add Prompt Prefix via CSS Pseudo-Element

  # In textual_app.py CSS, update Input styling:
  CSS = """
  # ... other styles ...

  Input {
      height: 1;
      border: none;
      background: transparent;
  }

  /* Add '>' prefix before input */
  Input:focus {
      border: none;
  }

  /* Use padding to make room for '>' */
  Input {
      padding-left: 3;  /* Make room for "> " */
  }
  """

  # Alternative: Use a Label widget next to Input
  def compose(self) -> ComposeResult:
      # ... other widgets ...

      with Container(id="input_container"):
          yield Label(">", id="input_prompt")  # Add prompt indicator
          yield Input(
              id="input",
              placeholder="Type your message or command...",
          )

  # Update CSS for side-by-side layout:
  CSS = """
  # ... other styles ...

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
      border: none;
      background: transparent;
  }
  """

  ---
  Issue #6: Input Unusable After Classification (CRITICAL)

  Root Cause

  Worker thread with @work(exclusive=True, thread=True) makes blocking HTTP calls during classification. Textual's
  worker thread pool may be exhausting, causing new input events to queue indefinitely.

  Diagnosis Steps

  # Add logging to identify the bottleneck
  # In textual_app.py:225
  @work(exclusive=True, thread=True)
  def process_command(self, user_input: str) -> None:
      import threading
      logger.debug(f"Worker thread started: {threading.current_thread().name}")
      logger.debug(f"Active workers: {len(self.workers)}")

      try:
          should_continue = self.interactive_mode._process_input(user_input)
          if not should_continue:
              self.exit()
      except Exception as e:
          logger.exception("Error processing command")
      finally:
          logger.debug(f"Worker thread ending: {threading.current_thread().name}")


 Use Dedicated Thread Pool
  # In textual_app.py, add at class level:
  from concurrent.futures import ThreadPoolExecutor

  class ScrappyApp(App):
      def __init__(self, interactive_mode, output_adapter):
          super().__init__()
          # ... existing init ...
          self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="scrappy-worker")

      def on_input_submitted(self, event: Input.Submitted) -> None:
          user_input = event.value.strip()
          if not user_input:
              return

          self.query_one(Input).value = ""

          # Use dedicated executor instead of @work decorator
          future = self._executor.submit(self._process_input_sync, user_input)
          self.call_later(lambda: self._check_result(future))

      def _process_input_sync(self, user_input: str) -> bool:
          """Runs in dedicated thread pool."""
          try:
              return self.interactive_mode._process_input(user_input)
          except Exception as e:
              logger.exception("Error processing command")
              from rich.text import Text
              error_text = Text(f"Error: {str(e)}", style="red")
              self.output_adapter.post_renderable(error_text)
              return True

      def _check_result(self, future) -> None:
          """Check if processing complete and handle exit."""
          if future.done():
              try:
                  should_continue = future.result()
                  if not should_continue:
                      self.exit()
              except Exception as e:
                  logger.exception("Future failed")

