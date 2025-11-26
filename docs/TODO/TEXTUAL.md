[//]: # (GOAL)
 
Integrate textual 
- create an area at the bottom of terminal below user input to display status
  - phase 1 -- integrate textual and display our existing app (header, static, input, RichLog, etc) -- COMPLETE
  - phase 2 -- add the footer to serve as our status area.
  - phase 3 -- integrate status elements eg: progress into status area

[//]: # (START PLAN)

## Architecture: Proper Library Separation

**Click** - CLI argument parsing and commands ONLY (input layer)
**Rich** - All styled output (Panels, Tables, Text, Syntax highlighting, etc.)
**Textual** - Layout and organization (widgets, TUI structure, event handling)

### Current Architecture Understanding (Complete)

**Entry Flow:**
```
scrappy.py → CLI.interactive_mode() → TextualInteractiveMode.run()
    ↓
ScrappyApp (Textual event loop - async)
    ↓
on_input_submitted() → run_worker(_process_input_worker)
    ↓
asyncio.to_thread(InteractiveMode._process_input) [runs in thread pool]
    ↓
CommandRouter.route() OR Orchestrator.delegate() [blocking I/O]
    ↓
Output via TextualIO.echo/secho → RichLog widget
```

**Thread Safety Issue:**
- InteractiveMode runs in worker thread (via asyncio.to_thread)
- TextualIO writes to RichLog widget from worker thread
- Textual widgets are NOT thread-safe
- Widget updates from threads are lost → no visible output


---

### Phase 0: Pre-Implementation Async Audit


**0.2 Create Blocking Operations Matrix**

Document findings in a table:

| Operation | Location | Blocks UI? | Phase 1 Strategy | Phase 3 Solution |
|-----------|----------|------------|------------------|------------------|
| io.prompt() | interactive_mode.py:123 | YES | Raise NotImplementedError | Modal Screen |
| io.confirm() | tool_executor.py:45 | YES | Auto-confirm with warning | Modal Dialog |
| Path.read_text() | file_tools.py:67 | Maybe | Leave as-is (fast) | async file I/O |

**0.3 Enable Disabled Features**

Create list of features that will be temporarily unavailable:
- Commands requiring user input mid-execution
- Tools requiring confirmation of destructive operations
- Any workflow using interactive prompts

**Deliverable:** `docs/TODO/done/ASYNC_AUDIT.md` with complete matrix and disabled features list.

---

### Phase 2: UI Rendering & Component Architecture

**Objective:** Fix visual corruption, restore original UX, architect for extensible status components.

**2.1 Define Status Component Protocol (textual_app.py)**

```python
from typing import Protocol
from textual.widgets import Widget

class StatusComponentProtocol(Protocol):
    """Protocol for status bar components that can be dynamically added/removed"""

    @property
    def component_id(self) -> str:
        """Unique identifier for this component"""
        ...

    @property
    def is_visible(self) -> bool:
        """Whether this component should be displayed"""
        ...

    def render_widget(self) -> Widget:
        """Return the Textual widget to display"""
        ...
```

**Example implementations:**
```python
class ProgressIndicator:
    """Shows indexing/processing progress"""
    def __init__(self):
        self._progress = 0
        self._total = 0
        self._message = ""
        self._active = False

    @property
    def component_id(self) -> str:
        return "progress"

    @property
    def is_visible(self) -> bool:
        return self._active

    def render_widget(self) -> Widget:
        from textual.widgets import ProgressBar, Label
        from textual.containers import Horizontal

        bar = ProgressBar(total=self._total, id="progress_bar")
        bar.progress = self._progress
        label = Label(self._message)
        return Horizontal(label, bar, id="progress_indicator")

    def update(self, progress: int, total: int, message: str) -> None:
        self._progress = progress
        self._total = total
        self._message = message
        self._active = True

    def complete(self) -> None:
        """Mark complete - will auto-hide after brief delay"""
        self._active = False

class TokenCounter:
    """Shows token usage for current session"""
    def __init__(self):
        self._tokens = 0
        self._visible = False

    @property
    def component_id(self) -> str:
        return "tokens"

    @property
    def is_visible(self) -> bool:
        return self._visible and self._tokens > 0

    def render_widget(self) -> Widget:
        from textual.widgets import Label
        return Label(f"Tokens: {self._tokens:,}", id="token_counter")

    def update(self, tokens: int) -> None:
        self._tokens = tokens
        self._visible = True

    def hide(self) -> None:
        self._visible = False
```

**2.2 Implement Dynamic StatusBar Container (textual_app.py)**

```python
from textual.containers import Container, Vertical
from textual.reactive import reactive

class StatusBar(Container):
    """Dynamic status bar that shows/hides based on active components"""

    show_status = reactive(False)

    def __init__(self):
        super().__init__(id="status_bar")
        self.components: Dict[str, StatusComponentProtocol] = {}

    def compose(self) -> ComposeResult:
        """Dynamically compose based on active components"""
        yield Vertical(id="status_content")

    def register_component(self, component: StatusComponentProtocol) -> None:
        """Add a status component"""
        self.components[component.component_id] = component
        self.refresh_display()

    def unregister_component(self, component_id: str) -> None:
        """Remove a status component"""
        if component_id in self.components:
            del self.components[component_id]
            self.refresh_display()

    def refresh_display(self) -> None:
        """Update visible components"""
        visible_components = [c for c in self.components.values() if c.is_visible]

        # Hide entire status bar if no visible components
        self.show_status = len(visible_components) > 0

        # Update content
        content_container = self.query_one("#status_content", Vertical)
        content_container.remove_children()

        for component in visible_components:
            content_container.mount(component.render_widget())
```

**2.3 Update App Layout (textual_app.py)**

```python
def compose(self) -> ComposeResult:
    # Main scrollable content area (banner will be written here as content)
    yield RichLog(id="output", auto_scroll=True, highlight=True)

    # User input
    yield Input(placeholder="Type your message or command", id="input")

    # Dynamic status bar (shows/hides based on active components)
    yield StatusBar()

def on_mount(self) -> None:
    self.query_one(Input).focus()

    log_widget = self.query_one(RichLog)

    # CRITICAL: Write banner as first content in RichLog (scrolls with everything)
    banner_text = Text.from_ansi(self._render_banner())
    log_widget.write(banner_text)
    log_widget.write(Text(""))  # Blank line after banner

    # Display buffered startup output
    startup_items = self.output_adapter.flush_startup_buffer()
    if startup_items:
        log_widget.write(Text("--- Session Start ---", style="dim"))
        for item in startup_items:
            log_widget.write(item)
        log_widget.write(Text(""))  # Blank line for spacing

    # Initialize status components
    self.progress_indicator = ProgressIndicator()
    self.token_counter = TokenCounter()

    status_bar = self.query_one(StatusBar)
    status_bar.register_component(self.progress_indicator)
    status_bar.register_component(self.token_counter)
```

**2.4 Create Theme CSS with Component Support (scrappy.tcss)**

```css
/* Match original CLI colors */
Screen {
    background: $surface;
}

/* Main scrollable output (includes banner as content) */
RichLog {
    background: $surface;
    color: $text;
    border: none;
    padding: 1;
}

/* User input */
Input {
    border: heavy $accent;
}

/* Defensive !important for known Textual specificity issues */
Input > .input--placeholder {
    color: $text-muted !important;
}

Input > .input--cursor {
    color: $text !important;
}

/* Status bar - only visible when components active */
#status_bar {
    height: auto;
    max-height: 30%;  /* Don't let status take over screen */
    background: $panel;
    border-top: solid $accent;
    padding: 1;
    display: none;  /* Hidden by default */
}

#status_bar.show {
    display: block;  /* Show when active components */
}

#status_content {
    width: 100%;
    height: auto;
}

/* Progress indicator styling */
#progress_indicator {
    width: 100%;
    height: auto;
    margin: 0 0 1 0;
}

#progress_indicator Label {
    width: 30;
    content-align: left middle;
}

#progress_indicator ProgressBar {
    width: 1fr;  /* Fill remaining space */
}

/* Token counter styling */
#token_counter {
    width: 100%;
    content-align: right middle;
    color: $text-muted;
}

/* Color variables matching original CLI */
$surface: #1e1e1e;
$text: #d4d4d4;
$text-muted: #808080;
$accent: #00ff00;
$panel: #2d2d2d;
```

**2.5 CSS Visual Testing Checklist**

After applying CSS:
- [ ] Launch Textual DevTools (Ctrl+\\) and inspect computed styles
- [ ] Verify Input placeholder visible before focus
- [ ] Verify Input placeholder disappears on focus
- [ ] Check RichLog background matches original CLI
- [ ] Verify banner ANSI codes fully stripped (no [32m visible)
- [ ] Test color contrast ratios (accessibility)
- [ ] Status bar hidden on startup (no components active)
- [ ] Status bar appears when component registered and visible
- [ ] Status bar hides when all components become invisible
- [ ] Progress bar and label fit within status area
- [ ] Multiple components can coexist in status bar

**2.6 Usage Example: Indexing Progress**

How to use the status bar for lancedb indexing:

```python
# During initialization/indexing
def index_files(self, files: List[Path]) -> None:
    status_bar = self.query_one(StatusBar)
    progress = self.progress_indicator

    total = len(files)
    for i, file in enumerate(files):
        # Update progress
        progress.update(i + 1, total, f"Indexing: {file.name}")
        status_bar.refresh_display()  # Trigger UI update

        # Actual indexing work
        self.vector_store.index(file)

    # Mark complete - status bar will hide after brief delay
    progress.complete()
    status_bar.refresh_display()

    # Optional: Auto-hide after 2 seconds
    self.set_timer(2.0, lambda: status_bar.refresh_display())
```

---

### Phase 3: Async Completion

**PITFALLS**

### 1. The Deadlock Trap (Phase 3 Critical Safety Patch)

In `ThreadSafeAsyncBridge`, you are blocking the current thread with `event.wait()`.
*   **The Risk:** If a developer accidentally calls `io.prompt()` from the **Main Thread** (instead of a worker thread),
* `event.wait()` will pause the Main Thread. The Main Thread is responsible for processing messages. It will never see `ShowPromptModal`.
* The app will freeze forever (Deadlock).
*   **The Fix:** Add a runtime guard in the bridge.

**Update `ThreadSafeAsyncBridge` methods:**

```python
import threading

def blocking_prompt(self, message: str, default: str = "") -> str:
    # DEADLOCK GUARD
    if threading.current_thread() is threading.main_thread():
        raise RuntimeError(
            "CRITICAL ERROR: blocking_prompt() called from Main Thread! "
            "This will cause a deadlock. Ensure calls to input/prompt "
            "are running inside a @work thread."
        )

    # ... rest of your code ...
```

### 2. CSS Layout Tweak (Phase 3.2)

In `PromptScreen`, `Vertical` containers inside a modal sometimes collapse if they don't have explicit dimensions or if the parent container constraints aren't tight.

**Refined CSS for `PromptScreen`:**
```css
PromptScreen > Container {
    width: 60;
    height: auto;
    border: thick $accent;
    background: $panel;
    padding: 1;
    /* Fix: Ensure layout engine knows how to stack */
    layout: vertical; 
}

/* Fix: Center buttons nicely */
PromptScreen Vertical {
    height: auto;
    align-horizontal: center;
    margin-top: 1;
}
```
**END PITFALLS**

**Objective:** Remove Phase 1 limitations and enable full interactive workflows.

**CRITICAL ARCHITECTURAL INSIGHT:**
InteractiveMode._process_input() runs in a worker thread (via @work decorator). You CANNOT simply await in a thread.
You need a ThreadSafeAsyncBridge that allows the worker thread to block while the main thread (event loop) handles
the Modal, then resumes the thread with the result.

**3.1 Implement ThreadSafeAsyncBridge (textual_app.py)**

```python
import threading
import uuid
from typing import Dict, Any, Optional
from textual.message import Message

class ShowPromptModal(Message):
    """Message to show prompt modal in main thread"""
    def __init__(self, prompt_id: str, message: str, default: str = "") -> None:
        self.prompt_id = prompt_id
        self.message = message
        self.default = default
        super().__init__()

class ShowConfirmModal(Message):
    """Message to show confirmation modal in main thread"""
    def __init__(self, prompt_id: str, question: str) -> None:
        self.prompt_id = prompt_id
        self.question = question
        super().__init__()

class ThreadSafeAsyncBridge:
    """
    Allows worker thread to block while waiting for async result from main thread.

    Pattern:
    1. Worker thread calls blocking_prompt()
    2. Bridge posts message to main thread
    3. Worker thread blocks on threading.Event
    4. Main thread shows modal, gets result
    5. Main thread calls provide_result()
    6. Worker thread unblocks with result
    """

    def __init__(self, app: 'ScrappyApp'):
        self.app = app
        self._pending_prompts: Dict[str, threading.Event] = {}
        self._prompt_results: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def blocking_prompt(self, message: str, default: str = "") -> str:
        """Called from worker thread - blocks until main thread provides result"""
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
        """Called from worker thread - blocks until main thread provides result"""
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
        """Called from main thread after modal dismisses"""
        with self._lock:
            self._prompt_results[prompt_id] = result
            self._pending_prompts[prompt_id].set()  # Unblock worker thread
```

**3.2 Implement Modal Screens (textual_app.py)**

```python
from textual.screen import ModalScreen
from textual.containers import Container, Vertical
from textual.widgets import Label, Input, Button

class PromptScreen(ModalScreen[str]):
    """Modal dialog for user input"""

    DEFAULT_CSS = """
    PromptScreen {
        align: center middle;
    }

    PromptScreen > Container {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $panel;
        padding: 1;
    }

    PromptScreen Input {
        margin: 1 0;
    }

    PromptScreen Button {
        margin: 0 1;
    }
    """

    def __init__(self, prompt_message: str, default: str = ""):
        super().__init__()
        self.prompt_message = prompt_message
        self.default = default

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(self.prompt_message, id="prompt_label")
            yield Input(value=self.default, id="modal_input")
            with Vertical():
                yield Button("Submit", variant="primary", id="submit")
                yield Button("Cancel", variant="default", id="cancel")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit":
            value = self.query_one(Input).value
            self.dismiss(value)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Allow Enter key to submit"""
        self.dismiss(event.value)

class ConfirmScreen(ModalScreen[bool]):
    """Modal dialog for confirmation"""

    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
    }

    ConfirmScreen > Container {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $panel;
        padding: 1;
    }

    ConfirmScreen Button {
        margin: 0 1;
    }
    """

    def __init__(self, question: str):
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(self.question, id="question_label")
            with Vertical():
                yield Button("Yes", variant="success", id="yes")
                yield Button("No", variant="error", id="no")

    def on_mount(self) -> None:
        self.query_one("#yes", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")
```

**3.3 Update TextualIO to Use Bridge (textual_io.py)**

```python
class TextualIO:
    def __init__(self, output_adapter: OutputSink, bridge: Optional[ThreadSafeAsyncBridge] = None):
        self.output_adapter = output_adapter
        self.bridge = bridge  # None in Phase 1, set in Phase 3

    def prompt(self, message: str, default: str = "") -> str:
        """Blocks worker thread until user provides input"""
        if self.bridge is None:
            # Phase 1 fallback - show error
            error_panel = Panel(
                f"[bold red]OPERATION BLOCKED[/]\n\n"
                f"Attempted to call blocking prompt():\n{message}\n\n"
                f"This operation is not supported in Textual mode.\n"
                f"Use CLI mode for interactive workflows.",
                title="[blink]Async Safety Error[/]",
                border_style="red"
            )
            self.output_adapter.post_output(error_panel)
            raise NotImplementedError(
                "Blocking input not supported in Textual mode. "
                "Bridge not initialized."
            )

        # Phase 3 - use bridge to block thread while modal runs
        return self.bridge.blocking_prompt(message, default)

    def confirm(self, question: str, default: bool = False) -> bool:
        """Blocks worker thread until user confirms"""
        if self.bridge is None:
            # Phase 1 fallback - auto-confirm with warning
            warning_panel = Panel(
                f"[blink bold white on red] AUTO-CONFIRMED [/]\n\n"
                f"{question}\n\n"
                f"[yellow]This operation was automatically approved.[/]\n"
                f"[yellow]Switch to CLI mode for manual confirmation.[/]",
                title="[blink]SECURITY: Automatic Confirmation[/]",
                border_style="red",
                expand=False
            )
            self.output_adapter.post_output(warning_panel)
            return True

        # Phase 3 - use bridge to block thread while modal runs
        return self.bridge.blocking_confirm(question)
```

**3.4 Update ScrappyApp to Handle Modal Messages (textual_app.py)**

```python
class ScrappyApp(App):
    def __init__(self, interactive_mode: InteractiveMode):
        super().__init__()
        self.interactive_mode = interactive_mode
        self.output_adapter = interactive_mode.io.output_adapter

        # Phase 3: Initialize bridge and inject into TextualIO
        self.bridge = ThreadSafeAsyncBridge(self)
        self.interactive_mode.io.bridge = self.bridge

    # ... existing methods ...

    def on_show_prompt_modal(self, message: ShowPromptModal) -> None:
        """Handle prompt request from worker thread"""
        def handle_result(result: Optional[str]) -> None:
            final_result = result if result is not None else message.default
            self.bridge.provide_result(message.prompt_id, final_result)

        self.push_screen(
            PromptScreen(message.message, message.default),
            handle_result
        )

    def on_show_confirm_modal(self, message: ShowConfirmModal) -> None:
        """Handle confirmation request from worker thread"""
        def handle_result(result: bool) -> None:
            self.bridge.provide_result(message.prompt_id, result)

        self.push_screen(
            ConfirmScreen(message.question),
            handle_result
        )
```

**3.5 Update Initialization (textual_interactive.py)**

```python
def run(self):
    output_adapter = TextualOutputAdapter()
    textual_io = TextualIO(output_adapter, bridge=None)  # Bridge set later

    interactive_mode = InteractiveMode(
        io=textual_io,
        orchestrator=self.orchestrator,
        # ... other dependencies
    )

    app = ScrappyApp(interactive_mode)
    output_adapter.set_app(app)
    # Bridge is initialized in ScrappyApp.__init__ and injected back into textual_io
    app.run()
```

**Why This Works:**
1. Worker thread calls `io.prompt()`
2. TextualIO calls `bridge.blocking_prompt()`
3. Bridge posts `ShowPromptModal` message to main thread
4. Worker thread blocks on `threading.Event.wait()`
5. Main thread (event loop) receives message via `on_show_prompt_modal()`
6. Main thread shows modal, user inputs data
7. Modal callback fires, calls `bridge.provide_result()`
8. Bridge sets the event, unblocking worker thread
9. Worker thread retrieves result and continues execution

**This pattern allows synchronous code to interact with async UI without refactoring the entire execution path.**

---

### Testing Protocol

**Execute tests in order - later tests depend on earlier ones passing.**

#### Backend Tests (IO Flow)

**Test Group 1: Basic Output**
1. [ ] Launch app - startup output visible in RichLog
2. [ ] /help - displays formatted table
3. [ ] /status - shows system info panel
4. [ ] Chat message - receives response visible in log

**Test Group 2: Command Execution**
5. [ ] /agent simple_task - executes with output visible
6. [ ] /plan create_feature - creates and displays plan
7. [ ] Multiple commands in sequence - all output visible

**Test Group 3: Async Safety**
8. [ ] Command with prompt() call - shows red error panel, doesn't crash
9. [ ] Command with confirm() call - shows red warning panel, continues
10. [ ] Long-running command - UI remains responsive during execution

#### Frontend Tests (Rendering)

**Test Group 4: Visual Quality**
11. [ ] Banner displays cleanly (no ANSI escape codes like [32m)
12. [ ] Input auto-focused on startup (can type immediately)
13. [ ] User commands echoed to log with "> " prefix
14. [ ] Colors match original CLI (compare screenshots)
15. [ ] RichLog scrolls automatically on new output

**Test Group 5: Interaction**
16. [ ] Hold Shift + drag mouse - can select text
17. [ ] Shift+select then Ctrl+C - copies to clipboard
18. [ ] /exit - shuts down cleanly without errors
19. [ ] Resize window - layout adapts properly

#### Regression Tests

**Test Group 6: Ensure Non-Textual Mode Still Works**
20. [ ] Launch with --no-textual flag (if exists) - original CLI works
21. [ ] All interactive prompts work in CLI mode
22. [ ] Confirmations require user input in CLI mode

---
