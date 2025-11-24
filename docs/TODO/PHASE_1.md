Phase 1 Issue Fix Plan

  Fix Order (Dependency-Based)

  3. Issue #4 - Fix focus management (needed for usability)
  5. Issue #5 - Fix text copying (enable selection)
  7. Issue #6 - Fix HTTP/worker thread deadlock (CRITICAL - fixes app freezing)

  ---

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

  Issue #5: Can't Copy Text

`ALLOW_SELECT` is exactly the right strategy, but you generally cannot just pass it as an argument to the standard `RichLog`. You usually need to subclass it.

Here is why it happens and how to fix it properly.

### The Problem
By default, `RichLog` (and `Log`) captures your mouse clicks to handle **scrolling**. If you click and drag inside the log, Textual interprets that as "pan/scroll the view," not "select text."

### The Fix
You need to explicitly tell the widget to prioritize selection over scrolling interactions.

#### 1. The Subclass Method (Cleanest)
Create a custom log class that enables selection by default.

```python
from textual.widgets import RichLog

class CopyableLog(RichLog):
    # This class var enables the mouse selection behavior
    ALLOW_SELECT = True

# Usage in your app:
# yield CopyableLog()
```

#### 2. The Instance Method (Quickest)
If you don't want to make a new class, you can set the attribute on the instance in your `on_mount` or after querying it.

```python
def on_mount(self):
    log = self.query_one(RichLog)
    log.allow_select = True
```

### Important Trade-offs
1.  **Selection vs. Scrolling:** Once you enable `allow_select`, clicking and dragging inside the log will **select text**, which means you can no longer click and drag to **scroll**. Users will have to use the scrollbar or the mouse wheel to scroll.
2.  **Rich Objects:** `RichLog` renders complex objects (tables, trees, panels). When you select and copy them, you get the **plain text** representation. It usually looks fine, but it won't preserve the "Rich" structure (colors/styles) in the clipboard.

  ---
  



need more planning:

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

