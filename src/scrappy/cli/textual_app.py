"""
Textual-based TUI application for Scrappy CLI.

Provides an interactive terminal UI using the Textual framework,
wrapping the existing InteractiveMode with a modern UI.
"""

from typing import TYPE_CHECKING, Any, Optional, Dict, List, Callable
import logging
import threading
import time
import uuid
from queue import Queue, Empty
from textual.app import App, ComposeResult
from textual.message import Message
from textual.theme import Theme
from textual.widgets import Label
from textual.containers import Container, Vertical, Horizontal
from textual.reactive import reactive
from textual import work

from scrappy.infrastructure.output_mode import OutputModeContext
from scrappy.infrastructure.theme import DEFAULT_THEME, ThemeProtocol
from scrappy.protocols.activity import ActivityState
from .protocols import StatusComponentProtocol

if TYPE_CHECKING:
    from .interactive import InteractiveMode
    from .core import CLI
    from ..context.codebase_context import CodebaseContext

logger = logging.getLogger(__name__)


# =============================================================================
# Messages (thread-safe communication)
# =============================================================================

class WriteOutput(Message):
    """Message for thread-safe output to RichLog widget."""

    def __init__(self, content: str) -> None:
        super().__init__()
        self.content = content


class WriteRenderable(Message):
    """Message for posting Rich renderables to RichLog widget."""

    def __init__(self, renderable: Any) -> None:
        super().__init__()
        self.renderable = renderable


class RequestInlineInput(Message):
    """Message to request inline input capture."""

    def __init__(
        self,
        prompt_id: str,
        message: str,
        input_type: str,
        default: str = ""
    ) -> None:
        super().__init__()
        self.prompt_id = prompt_id
        self.message = message
        self.input_type = input_type
        self.default = default


class IndexingProgress(Message):
    """Message for semantic search indexing progress updates."""

    def __init__(
        self,
        message: str,
        progress: int = 0,
        total: int = 0,
        complete: bool = False
    ) -> None:
        super().__init__()
        self.message = message
        self.progress = progress
        self.total = total
        self.complete = complete


class ActivityStateChange(Message):
    """Message for thread-safe activity indicator updates.

    Used to communicate activity state changes from worker threads to the main
    thread's ActivityIndicator widget. Supports elapsed time tracking for
    long-running operations like Q/A processing and codebase re-indexing.

    Args:
        state: Current activity state (IDLE, THINKING, SYNCING, TOOL_EXECUTION)
        message: Optional descriptive message for the activity
        elapsed_ms: Elapsed time in milliseconds (0 for new activities)
    """

    def __init__(
        self,
        state: ActivityState,
        message: str = "",
        elapsed_ms: int = 0
    ) -> None:
        super().__init__()
        self.state = state
        self.message = message
        self.elapsed_ms = elapsed_ms


class TasksUpdated(Message):
    """Message for updating the task progress widget.

    Posted when the agent's task list changes (add, update, delete, clear).
    The main thread handles this by updating the TaskProgressWidget.

    Args:
        tasks: Current list of tasks to display.
    """

    def __init__(self, tasks: list) -> None:
        super().__init__()
        self.tasks = tasks


class CLIReady(Message):
    """Message posted when CLI initialization completes in background thread.

    Used by deferred initialization to signal that CLI is ready for use.
    Posted via call_from_thread() to safely update state on main thread.

    Args:
        cli: The fully initialized CLI instance
        error: Error message if initialization failed, None on success
    """

    def __init__(self, cli: Optional["CLI"] = None, error: Optional[str] = None) -> None:
        super().__init__()
        self.cli = cli
        self.error = error


# =============================================================================
# Thread-Safe Bridge
# =============================================================================

class ThreadSafeAsyncBridge:
    """Allows worker thread to block while waiting for async result from main thread.

    This bridge solves the threading problem where InteractiveMode._process_input()
    runs in a worker thread (via @work decorator) but needs to show modal dialogs
    that run on the main thread's event loop.
    """

    def __init__(self, app: "ScrappyApp") -> None:
        self.app = app
        self._pending_prompts: Dict[str, threading.Event] = {}
        self._prompt_results: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._shutting_down = False

    def shutdown(self) -> None:
        """Signal all pending prompts to unblock - call when app is closing."""
        self._shutting_down = True
        with self._lock:
            for event in self._pending_prompts.values():
                event.set()

    def blocking_prompt(self, message: str, default: str = "") -> str:
        """Called from worker thread - blocks until main thread provides result."""
        if threading.current_thread() is threading.main_thread():
            raise RuntimeError(
                "CRITICAL ERROR: blocking_prompt() called from Main Thread! "
                "This will cause a deadlock."
            )

        if self._shutting_down:
            return default

        prompt_id = str(uuid.uuid4())

        with self._lock:
            event = threading.Event()
            self._pending_prompts[prompt_id] = event

        self.app.post_message(RequestInlineInput(prompt_id, message, "prompt", default))

        # Wait with timeout to allow for shutdown
        while not event.wait(timeout=0.5):
            if self._shutting_down:
                return default

        with self._lock:
            result = self._prompt_results.pop(prompt_id, default)
            self._pending_prompts.pop(prompt_id, None)

        return result

    def blocking_confirm(self, question: str) -> bool:
        """Called from worker thread - blocks until main thread provides result."""
        if threading.current_thread() is threading.main_thread():
            raise RuntimeError(
                "CRITICAL ERROR: blocking_confirm() called from Main Thread! "
                "This will cause a deadlock."
            )

        if self._shutting_down:
            return False

        prompt_id = str(uuid.uuid4())

        with self._lock:
            event = threading.Event()
            self._pending_prompts[prompt_id] = event

        self.app.post_message(RequestInlineInput(prompt_id, question, "confirm"))

        # Wait with timeout to allow for shutdown
        while not event.wait(timeout=0.5):
            if self._shutting_down:
                return False

        with self._lock:
            result = self._prompt_results.pop(prompt_id, False)
            self._pending_prompts.pop(prompt_id, None)

        return result

    def blocking_checkpoint(self, message: str, default: str = "c") -> str:
        """Called from worker thread for checkpoint prompts.

        Similar to blocking_prompt but uses input_type="checkpoint" which
        displays ONLY in activity bar (not in chat log).
        """
        if threading.current_thread() is threading.main_thread():
            raise RuntimeError(
                "CRITICAL ERROR: blocking_checkpoint() called from Main Thread! "
                "This will cause a deadlock."
            )

        if self._shutting_down:
            return default

        prompt_id = str(uuid.uuid4())

        with self._lock:
            event = threading.Event()
            self._pending_prompts[prompt_id] = event

        # Use "checkpoint" input_type to skip log output
        self.app.post_message(RequestInlineInput(prompt_id, message, "checkpoint", default))

        # Wait with timeout to allow for shutdown
        while not event.wait(timeout=0.5):
            if self._shutting_down:
                return default

        with self._lock:
            result = self._prompt_results.pop(prompt_id, default)
            self._pending_prompts.pop(prompt_id, None)

        return result

    def provide_result(self, prompt_id: str, result: Any) -> None:
        """Called from main thread after input is captured."""
        with self._lock:
            if prompt_id not in self._pending_prompts:
                logger.warning(f"provide_result: unknown prompt_id {prompt_id}, ignoring")
                return
            self._prompt_results[prompt_id] = result
            self._pending_prompts[prompt_id].set()


# =============================================================================
# Output Adapter
# =============================================================================

class TextualOutputAdapter:
    """Adapter that bridges OutputSink protocol to thread-safe queue."""

    def __init__(self):
        self._queue: Queue[tuple[str, Any]] = Queue()
        self._flush_events: Dict[str, threading.Event] = {}
        self._flush_lock = threading.Lock()

    def post_output(self, content: str) -> None:
        self._queue.put(('output', content))

    def post_renderable(self, obj: Any) -> None:
        self._queue.put(('renderable', obj))

    def post_tasks_updated(self, tasks: list) -> None:
        """Post task list update to UI.

        Args:
            tasks: List of Task objects to display.
        """
        self._queue.put(('tasks', tasks))

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait for all pending output to be processed.

        Posts a flush sentinel and waits for consumer to acknowledge it.
        Returns True if flushed successfully, False on timeout.
        """
        flush_id = str(uuid.uuid4())
        event = threading.Event()

        with self._flush_lock:
            self._flush_events[flush_id] = event

        self._queue.put(('flush', flush_id))

        success = event.wait(timeout=timeout)

        with self._flush_lock:
            self._flush_events.pop(flush_id, None)

        return success

    def acknowledge_flush(self, flush_id: str) -> None:
        """Called by consumer when flush sentinel is processed."""
        with self._flush_lock:
            event = self._flush_events.get(flush_id)
            if event:
                event.set()

    def get_message(self, block: bool = True, timeout: Optional[float] = None) -> Optional[tuple[str, Any]]:
        try:
            return self._queue.get(block=block, timeout=timeout)
        except Empty:
            return None


# =============================================================================
# Status Bar Components
# =============================================================================

class ProgressIndicator:
    """Shows indexing/processing progress in the status bar."""

    def __init__(self) -> None:
        self._progress: int = 0
        self._total: int = 0
        self._message: str = ""
        self._active: bool = False
        self._start_time: Optional[float] = None
        self._widget: Optional[Label] = None

    @property
    def component_id(self) -> str:
        return "progress_indicator"

    @property
    def is_visible(self) -> bool:
        return self._active

    @property
    def widget(self) -> Label:
        if self._widget is None:
            self._widget = Label(self._message, id=self.component_id)
        return self._widget

    def start(self, message: str = "", total: int = 0) -> None:
        """Start progress tracking with timing."""
        self._start_time = time.time()
        self._message = message
        self._total = total
        self._progress = 0
        self._active = True
        self.update_widget()

    def get_elapsed(self) -> float:
        """Get elapsed time in seconds since start()."""
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def update_widget(self) -> None:
        if self._widget is not None:
            elapsed = self.get_elapsed()
            if elapsed > 0.0:
                self._widget.update(f"{self._message} ({elapsed:.1f}s)")
            else:
                self._widget.update(self._message)

    def update(self, progress: int, total: int, message: str) -> None:
        if self._start_time is None:
            self._start_time = time.time()
        self._progress = progress
        self._total = total
        self._message = message
        self._active = True
        self.update_widget()

    def complete(self) -> None:
        self._active = False
        self._start_time = None


class TokenCounter:
    """Shows token usage for current session in the status bar."""

    def __init__(self) -> None:
        self._tokens: int = 0
        self._visible: bool = False
        self._widget: Optional[Label] = None

    @property
    def component_id(self) -> str:
        return "token_counter"

    @property
    def is_visible(self) -> bool:
        return self._visible and self._tokens > 0

    @property
    def widget(self) -> Label:
        if self._widget is None:
            self._widget = Label(f"Tokens: {self._tokens:,}", id=self.component_id)
        return self._widget

    def update_widget(self) -> None:
        if self._widget is not None:
            self._widget.update(f"Tokens: {self._tokens:,}")

    def update(self, tokens: int) -> None:
        self._tokens = tokens
        self._visible = True
        self.update_widget()

    def hide(self) -> None:
        self._visible = False


class PromptDisplay:
    """Shows prompt/question near the input in the status bar."""

    def __init__(self) -> None:
        self._message: str = ""
        self._input_type: str = ""
        self._default: str = ""
        self._visible: bool = False
        self._widget: Optional[Label] = None

    @property
    def component_id(self) -> str:
        return "prompt_display"

    @property
    def is_visible(self) -> bool:
        return self._visible and bool(self._message)

    @property
    def widget(self) -> Label:
        if self._widget is None:
            self._widget = Label(self._format_prompt(), id=self.component_id)
        return self._widget

    def _format_prompt(self) -> str:
        if not self._message:
            return ""
        hint = " [y/n]" if self._input_type == "confirm" else ""
        default_hint = f" (default: {self._default})" if self._default else ""
        return f"{self._message}{hint}{default_hint}"

    def update_widget(self) -> None:
        if self._widget is not None:
            self._widget.update(self._format_prompt())

    def show_prompt(self, message: str, input_type: str = "text", default: str = "") -> None:
        self._message = message
        self._input_type = input_type
        self._default = default
        self._visible = True
        self.update_widget()

    def hide_prompt(self) -> None:
        self._message = ""
        self._input_type = ""
        self._default = ""
        self._visible = False
        self.update_widget()


class SemanticStatusComponent:
    """Shows semantic search status in the status bar (always visible)."""

    def __init__(self) -> None:
        self._state: str = "initializing"  # initializing, indexing, ready, error
        self._chunks: int = 0
        self._files: int = 0
        self._progress_info: str = ""  # Right-aligned progress details
        self._start_time: Optional[float] = None
        self._widget: Optional[Horizontal] = None
        self._left_label: Optional[Label] = None
        self._right_label: Optional[Label] = None

    @property
    def component_id(self) -> str:
        return "semantic_status"

    @property
    def is_visible(self) -> bool:
        return True  # Always visible unlike ProgressIndicator

    @property
    def widget(self) -> Horizontal:
        if self._widget is None:
            self._left_label = Label(self._format_left(), id="semantic_status_left")
            self._right_label = Label(self._format_right(), id="semantic_status_right")
            self._widget = Horizontal(
                self._left_label,
                self._right_label,
                id=self.component_id
            )
        return self._widget

    def _format_left(self) -> str:
        if self._state == "ready":
            return "Search: ready"
        elif self._state == "indexing":
            return "Search: indexing"
        elif self._state == "error":
            return "Search: unavailable"
        else:
            return "Search: initializing..."

    def _format_right(self) -> str:
        if self._state == "indexing" and self._progress_info:
            elapsed = ""
            if self._start_time is not None:
                elapsed_secs = time.time() - self._start_time
                # Fixed-width format to prevent layout shift (handles 0.0 to 999.9)
                elapsed = f" ({elapsed_secs:>5.1f}s)"
            return f"{self._progress_info}{elapsed}"
        return ""

    def update_widget(self) -> None:
        if self._left_label is not None:
            self._left_label.update(self._format_left())
        if self._right_label is not None:
            self._right_label.update(self._format_right())

    def set_indexing(self, progress_info: str = "") -> None:
        if self._state != "indexing":
            self._start_time = time.time()
        self._state = "indexing"
        self._progress_info = progress_info
        if self._widget is not None:
            self._widget.remove_class("ready")
            self._widget.add_class("indexing")
        self.update_widget()

    def set_ready(self, chunks: int = 0, files: int = 0) -> None:
        self._state = "ready"
        self._chunks = chunks
        self._files = files
        self._progress_info = ""
        self._start_time = None
        if self._widget is not None:
            self._widget.remove_class("indexing")
            self._widget.add_class("ready")
        self.update_widget()

    def set_error(self) -> None:
        self._state = "error"
        self._progress_info = ""
        self._start_time = None
        self.update_widget()


class ActivityIndicator(Label):
    """Activity indicator widget for showing activity state.

    Displays current activity state (THINKING, SYNCING, TOOL_EXECUTION) with
    elapsed time. Flicker prevention via 500ms timer delay - if operation
    completes before delay, the indicator never becomes visible.

    Thread-safe: Updates via ActivityStateChange messages from worker threads.
    """

    # Delay before showing indicator (flicker prevention)
    SHOW_DELAY_SECONDS = 0.5

    def __init__(self) -> None:
        super().__init__("", id="activity_indicator")
        self._state: Optional[ActivityState] = None
        self._message: str = ""
        self._elapsed_ms: int = 0
        self._show_timer: Optional[Any] = None

    @property
    def is_visible(self) -> bool:
        """Whether indicator is currently active (has 'active' class)."""
        return self._state is not None

    def show(self, state: ActivityState, message: str = "") -> None:
        """Schedule showing the activity indicator after delay.

        Uses timer-based delay for flicker prevention - if hide() is called
        before the timer fires, the indicator never becomes visible.

        Args:
            state: Current activity state
            message: Optional descriptive message
        """
        # Cancel any pending show timer
        if self._show_timer is not None:
            self._show_timer.stop()
            self._show_timer = None

        self._state = state
        self._message = message
        self._elapsed_ms = 0
        self._update_display()

        # Schedule showing after delay (flicker prevention)
        self._show_timer = self.set_timer(
            self.SHOW_DELAY_SECONDS,
            self._reveal
        )

    def _reveal(self) -> None:
        """Actually show the indicator (called after delay)."""
        self._show_timer = None
        if self._state is not None:
            self.add_class("active")

    def update_elapsed(self, elapsed_ms: int) -> None:
        """Update elapsed time display.

        Args:
            elapsed_ms: Elapsed time in milliseconds
        """
        self._elapsed_ms = elapsed_ms
        if self.is_visible:
            self._update_display()

    def hide(self) -> None:
        """Hide the activity indicator immediately."""
        # Cancel pending show timer (prevents flicker)
        if self._show_timer is not None:
            self._show_timer.stop()
            self._show_timer = None

        self._state = None
        self._message = ""
        self._elapsed_ms = 0
        self.remove_class("active")
        self.update("")

    def _update_display(self) -> None:
        """Update display text based on current state."""
        if self._state is None:
            return

        state_text = {
            ActivityState.THINKING: "thinking",
            ActivityState.SYNCING: "syncing",
            ActivityState.TOOL_EXECUTION: "executing",
            ActivityState.IDLE: ""
        }.get(self._state, "")

        if not state_text:
            return

        elapsed_sec = self._elapsed_ms / 1000.0
        text = f"{state_text}... ({elapsed_sec:.1f}s)"

        if self._message:
            text = f"{state_text}: {self._message} ({elapsed_sec:.1f}s)"

        self.update(text)


class StatusBar(Container):
    """Dynamic status bar that shows/hides based on active components."""

    show_status = reactive(False)

    def __init__(self) -> None:
        super().__init__(id="status_bar")
        self.components: Dict[str, StatusComponentProtocol] = {}
        self._mounted_ids: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Vertical(id="status_content")

    def register_component(self, component: StatusComponentProtocol) -> None:
        self.components[component.component_id] = component
        self.refresh_display()

    def unregister_component(self, component_id: str) -> None:
        if component_id in self.components:
            del self.components[component_id]
            self._mounted_ids.discard(component_id)
            self.refresh_display()

    def _get_visible_components(self) -> List[StatusComponentProtocol]:
        return [c for c in self.components.values() if c.is_visible]

    def _update_visibility(self, has_visible: bool) -> None:
        self.show_status = has_visible
        if has_visible:
            self.add_class("show")
        else:
            self.remove_class("show")

    def _mount_components(self, visible: List[StatusComponentProtocol]) -> None:
        try:
            content = self.query_one("#status_content", Vertical)
        except Exception:
            return

        visible_ids = {c.component_id for c in visible}

        for comp_id in self._mounted_ids - visible_ids:
            try:
                widget = content.query_one(f"#{comp_id}")
                widget.remove()
            except Exception:
                pass

        for component in visible:
            if component.component_id not in self._mounted_ids:
                content.mount(component.widget)

        for component in visible:
            component.update_widget()

        self._mounted_ids = visible_ids

    def refresh_display(self) -> None:
        visible = self._get_visible_components()
        self._update_visibility(len(visible) > 0)
        self._mount_components(visible)


# =============================================================================
# Main Application (Controller)
# =============================================================================

class ScrappyApp(App):
    """Main Textual application controller.

    Manages screen navigation and shared state. Delegates UI to screens:
    - MainAppScreen: Chat interface
    - SetupWizardScreen: Provider configuration

    Supports two initialization modes:
    - Immediate: Pass interactive_mode directly (legacy, used by tests)
    - Deferred: Pass cli_factory for background initialization (fast startup)

    Responsibilities:
    - Screen navigation (push/pop/switch)
    - Theme registration
    - Output queue consumption
    - Message routing to active screen
    - Codebase context management
    """

    CSS_PATH = "scrappy.tcss"

    # Ready state for deferred initialization
    # When using cli_factory, this is False until CLI is ready
    ready = reactive(True)

    def __init__(
        self,
        interactive_mode: Optional["InteractiveMode"] = None,
        output_adapter: Optional[TextualOutputAdapter] = None,
        theme: Optional[ThemeProtocol] = None,
        cli_factory: Optional[Callable[[], "CLI"]] = None,
    ):
        """Initialize the Textual app controller.

        Two modes of operation:
        1. Immediate mode (legacy): Pass interactive_mode directly
        2. Deferred mode: Pass cli_factory for background initialization

        Args:
            interactive_mode: The InteractiveMode instance (immediate mode)
            output_adapter: The TextualOutputAdapter to consume messages from
            theme: Optional theme for consistent styling
            cli_factory: Factory function to create CLI (deferred mode)
        """
        super().__init__()
        self._theme = theme or DEFAULT_THEME
        self._should_stop_consumer = False

        # Deferred initialization mode
        self._cli_factory = cli_factory
        self._cli: Optional["CLI"] = None

        # In deferred mode, create output adapter now (needed for skeleton screen)
        if cli_factory is not None:
            self.output_adapter = output_adapter or TextualOutputAdapter()
            self.interactive_mode: Optional["InteractiveMode"] = None
            self.ready = False  # Will be set True when CLI is ready
        else:
            # Immediate mode (legacy)
            if interactive_mode is None:
                raise ValueError("Must provide either interactive_mode or cli_factory")
            self.interactive_mode = interactive_mode
            self.output_adapter = output_adapter or TextualOutputAdapter()
            self.ready = True

        # Thread-safe async bridge for prompts/confirms
        self.bridge = ThreadSafeAsyncBridge(self)

        # Codebase context for semantic search indexing
        self._codebase_context: Optional["CodebaseContext"] = None

    def set_codebase_context(self, context: "CodebaseContext") -> None:
        """Set codebase context for semantic search indexing.

        Args:
            context: The CodebaseContext instance with semantic search manager
        """
        self._codebase_context = context

        def progress_callback(
            message: str, progress: int = 0, total: int = 0
        ) -> None:
            # Always try to post the message - post_message is thread-safe in Textual
            # Remove is_running check as it may reject valid messages during startup race
            if not self._should_stop_consumer:
                logger.debug(f"Posting indexing progress: {message}")
                self.post_message(IndexingProgress(
                    message=message, progress=progress, total=total
                ))

        context.set_indexing_progress_callback(progress_callback)

        # Check if semantic search is already ready (init completed before callback was set)
        # If so, send a ready message to update the UI directly (bypass is_running check)
        if hasattr(context, 'is_semantic_search_ready') and context.is_semantic_search_ready():
            logger.info("Semantic search already ready when callback registered, posting ready message")
            self.post_message(IndexingProgress(message="Semantic search ready", progress=0, total=0))

    def _register_user_theme(self) -> None:
        """Register theme from ThemeProtocol with Textual."""
        logger.info(f"Registering theme - preset={self._theme.preset}")

        self.dark = (self._theme.preset == "dark")

        textual_theme = Theme(
            name="scrappy_user",
            primary=self._theme.primary,
            secondary=self._theme.info,
            accent=self._theme.accent,
            foreground=self._theme.text,
            background=self._theme.surface,
            surface=self._theme.surface_alt,
            warning=self._theme.warning,
            error=self._theme.error,
            success=self._theme.success,
        )

        self.register_theme(textual_theme)
        self.theme = "scrappy_user"

    def on_mount(self) -> None:
        """Called when app starts."""
        self._register_user_theme()
        OutputModeContext.set_tui_mode(True, self.output_adapter)

        # Start worker thread to consume output queue
        self.consume_output_queue()

        # Navigate to appropriate screen
        has_provider, env_key_count = self._check_and_migrate_providers()

        # Check if disclaimer has been acknowledged
        from scrappy.infrastructure.config.api_keys import create_api_key_service
        config_service = create_api_key_service()
        disclaimer_acknowledged = config_service.is_disclaimer_acknowledged()

        if not has_provider or not disclaimer_acknowledged:
            # Show wizard if no provider OR disclaimer not acknowledged
            # In deferred mode, wizard needs CLI - create it synchronously
            # (user needs to configure before using anyway, no benefit to defer)
            if self._cli_factory is not None:
                self._create_cli_sync_for_wizard()
            self._show_wizard_screen(allow_cancel=has_provider)
        else:
            # Show main screen immediately (skeleton in deferred mode)
            self._show_main_screen(env_key_count=env_key_count)

            # In deferred mode, start background CLI initialization
            if self._cli_factory is not None:
                self.initialize_cli()

        # Set up callback for /setup command (only if interactive_mode exists)
        if self.interactive_mode is not None:
            self.interactive_mode.command_router.set_setup_wizard_callback(
                self.launch_setup_wizard
            )

    def _create_cli_sync_for_wizard(self) -> None:
        """Create CLI synchronously for wizard screen.

        When no provider is configured, we need CLI for the wizard.
        No benefit to defer since user must configure before using.
        """
        if self._cli_factory is None:
            return

        try:
            self._cli = self._cli_factory()
            self._setup_interactive_mode()
            self.ready = True
        except Exception as e:
            logger.exception("Failed to create CLI for wizard: %s", e)

    @work(thread=True)
    def initialize_cli(self) -> None:
        """Initialize CLI in background thread.

        CRITICAL: Uses thread=True to run in ThreadPoolExecutor.
        CLI creation is CPU-bound (imports) and blocking I/O (disk reads),
        which would freeze the UI if run on the main event loop.

        Posts CLIReady message directly (Textual handles thread safety for @work).
        """
        if self._cli_factory is None:
            return

        try:
            # This is the slow part - runs in thread pool
            cli = self._cli_factory()

            # Post message directly - Textual's @work handles thread safety
            self.post_message(CLIReady(cli=cli))
        except Exception as e:
            error_msg = str(e)
            logger.exception("Failed to initialize CLI: %s", e)
            self.post_message(CLIReady(error=error_msg))

    def on_cliready(self, message: CLIReady) -> None:
        """Handle CLI initialization completion.

        Called on main thread after background worker finishes.
        Wires up InteractiveMode and sets ready=True.

        Note: Handler name is 'on_cliready' (not 'on_cli_ready') because
        Textual converts 'CLIReady' to 'cliready' (all lowercase, no underscores).
        """
        if message.error:
            # Show error in status bar - user can /setup to fix
            self.output_adapter.post_output(
                f"Startup error: {message.error}\nUse /setup to configure providers.\n"
            )
            # Still mark as ready so user can interact
            self.ready = True
            return

        if message.cli is None:
            return

        self._cli = message.cli
        self._setup_interactive_mode()
        self.ready = True

        # Display status lines now that CLI is ready (header already shown on mount)
        from scrappy.cli.interactive_banner import display_banner_status

        display_banner_status(self._cli.io)

    def _setup_interactive_mode(self) -> None:
        """Wire up InteractiveMode from CLI.

        Called after CLI is created (either sync or async).
        Sets up the interactive_mode and related callbacks.
        """
        if self._cli is None:
            return

        # Create InteractiveMode from CLI
        # This mirrors what TextualInteractiveMode.run() does
        from .interactive import InteractiveMode
        from .output_bridge import OutputBridge

        # Inject output bridge to route orchestrator output through Textual
        orchestrator_output = OutputBridge(self.output_adapter)
        self._cli.orchestrator.output = orchestrator_output

        # Create InteractiveMode with CLI's dependencies
        self.interactive_mode = InteractiveMode(
            io=self._cli.io,
            orchestrator=self._cli.orchestrator,
            session_context=self._cli.session_context,
            state_manager=self._cli.state_manager,
            input_handler=self._cli.input_handler,
            command_router=self._cli._create_command_router(),
            display=self._cli.display,
            smart=self._cli.smart,
            task_router=self._cli.task_router,
            tasks=self._cli.tasks,
            logger=self._cli.logger
        )

        # Pass session_context to task_router for verbose_mode access
        self.interactive_mode.task_router.session_context = self.interactive_mode.session_context

        # Set up codebase context for semantic search
        if hasattr(self._cli.orchestrator, 'context_manager'):
            context_manager = self._cli.orchestrator.context_manager
            if hasattr(context_manager, 'context'):
                self.set_codebase_context(context_manager.context)

        # Inject bridge into UnifiedIO for modal dialogs
        self._cli.io.set_bridge(self.bridge)

        # Reinitialize handlers with bridge for TUI-aware user interaction
        self._cli.reinitialize_handlers_with_bridge(self.bridge)

        # Update command router's references to the new handlers
        self.interactive_mode.command_router.agent_mgr = self._cli.agent_mgr

        # Set up callback for /setup command
        self.interactive_mode.command_router.set_setup_wizard_callback(
            self.launch_setup_wizard
        )

    def exit(  # type: ignore[override]
        self,
        result: object = None,
        return_code: int = 0,
        message: object = None,
    ) -> None:
        """Override exit to ensure bridge shutdown before worker wait.

        Textual waits for workers to complete before on_unmount is called.
        If a worker is blocked on bridge.blocking_confirm(), this creates
        a deadlock. Signal shutdown early to unblock workers.
        """
        self._should_stop_consumer = True
        self.bridge.shutdown()

        # Cancel any running agent to unblock its worker thread
        if hasattr(self, 'interactive_mode') and self.interactive_mode:
            agent_mgr = self.interactive_mode.command_router.agent_mgr
            if agent_mgr:
                agent_mgr.cancel()

        # Cast message to satisfy type checker (parent expects RenderableType | None)
        super().exit(result, return_code, str(message) if message else None)

    def on_unmount(self) -> None:
        """Called when app is about to close."""
        self._should_stop_consumer = True
        OutputModeContext.set_tui_mode(False)

        # Signal bridge to release any blocked worker threads (redundant but safe)
        self.bridge.shutdown()

        if self._codebase_context is not None:
            self._codebase_context.shutdown()

        # Close LLM service HTTP sessions
        if hasattr(self, 'interactive_mode') and self.interactive_mode:
            try:
                self.interactive_mode.orchestrator.llm_service.close()
            except Exception as e:
                logger.debug("Error closing LLM service: %s", e)

    def update_status(self, content: str) -> None:
        """Update the status bar widget.

        Implements StatusBarUpdaterProtocol to allow infrastructure components
        to update the status without depending on the concrete ScrappyApp class.

        Args:
            content: The status message with Rich markup
        """
        from textual.widgets import Static

        try:
            status_widget = self.query_one("#status", Static)
            status_widget.update(content)
        except Exception:
            # If we can't update the status (e.g., app not fully initialized),
            # fail silently to avoid breaking the operation
            pass

    def _check_and_migrate_providers(self) -> tuple[bool, int]:
        """Check if any provider is configured.

        Migration from environment variables to config now happens automatically
        in ApiKeyConfigService.load(), so we just need to check for providers.

        Returns:
            Tuple of (has_any_provider, 0)
            Note: Second value kept for API compatibility but always 0
        """
        from scrappy.infrastructure.config.api_keys import create_api_key_service
        from scrappy.orchestrator.provider_definitions import PROVIDERS

        # Migration happens automatically in load() via _migrate_from_env()
        config_service = create_api_key_service()
        env_vars = [info.env_var for info in PROVIDERS.values()]

        return config_service.has_any_key(env_vars), 0

    def _show_main_screen(self, env_key_count: int = 0) -> None:
        """Switch to main chat screen.

        In deferred mode, interactive_mode may be None. MainAppScreen handles
        this by showing a skeleton UI and checking app.ready before processing.

        Args:
            env_key_count: Number of API keys found in environment (for welcome message)
        """
        from .screens import MainAppScreen

        screen = MainAppScreen(
            interactive_mode=self.interactive_mode,  # May be None in deferred mode
            output_adapter=self.output_adapter,
            bridge=self.bridge,
            theme=self._theme,
        )
        self.push_screen(screen)

        # Display banner header immediately (doesn't need CLI)
        from scrappy.cli.interactive_banner import display_banner_header_tui

        display_banner_header_tui(self.output_adapter)

        # Show welcome message if keys were found in environment
        if env_key_count > 0:
            key_word = "key" if env_key_count == 1 else "keys"
            self.output_adapter.post_output(
                f"Found {env_key_count} API {key_word} in environment. Use /setup to add more.\n"
            )

    def _show_wizard_screen(self, allow_cancel: bool = True) -> None:
        """Push wizard screen.

        Uses lightweight KeyValidator for instant startup - doesn't require CLI.
        interactive_mode may be None in deferred mode.
        """
        from .screens import SetupWizardScreen
        from scrappy.orchestrator.key_validator import create_key_validator

        if self.interactive_mode is None:
            logger.error("Cannot show wizard: interactive_mode not initialized")
            return

        screen = SetupWizardScreen(
            io=self.interactive_mode.io,
            key_validator=create_key_validator(),
            allow_cancel=allow_cancel,
            on_complete=self._on_wizard_complete,
        )
        self.push_screen(screen)

    def _on_wizard_complete(self, has_provider: bool) -> None:
        """Called when wizard screen completes.

        Args:
            has_provider: True if at least one provider is configured
        """
        if has_provider:
            if self.interactive_mode is not None:
                self.interactive_mode.orchestrator._auto_register_providers()
                # Configure LLM service now that API keys are saved
                self.interactive_mode.orchestrator.llm_service.configure()
            # Show main screen after wizard
            self.call_later(self._show_main_screen)
        else:
            # No provider configured - exit the app
            self.call_later(self.exit)

    def launch_setup_wizard(self) -> None:
        """Launch setup wizard (called by /setup command).

        Uses call_later() to ensure screen push happens on main thread,
        since commands are processed in worker threads.
        """
        self.call_later(lambda: self._show_wizard_screen(allow_cancel=True))

    @work(exclusive=False, thread=True)
    def consume_output_queue(self) -> None:
        """Worker thread that consumes output queue and posts to UI."""
        while not self._should_stop_consumer and self.is_running:
            try:
                message = self.output_adapter.get_message(block=True, timeout=0.1)

                if message is None:
                    continue

                msg_type, content = message

                if msg_type == 'output':
                    self.post_message(WriteOutput(content))
                elif msg_type == 'renderable':
                    self.post_message(WriteRenderable(content))
                elif msg_type == 'tasks':
                    self.post_message(TasksUpdated(content))
                elif msg_type == 'flush':
                    # Acknowledge flush - all prior items processed
                    self.output_adapter.acknowledge_flush(content)

            except Exception as e:
                logger.exception(f"Error consuming output queue: {e}")

    # =========================================================================
    # Message Handlers - Route to Active Screen
    # =========================================================================

    def on_write_output(self, message: WriteOutput) -> None:
        """Route plain text output to active screen."""
        from .screens import MainAppScreen

        screen = self.screen
        if isinstance(screen, MainAppScreen):
            screen.write_output(message.content)

    def on_write_renderable(self, message: WriteRenderable) -> None:
        """Route Rich renderable to active screen."""
        from .screens import MainAppScreen

        screen = self.screen
        if isinstance(screen, MainAppScreen):
            screen.write_renderable(message.renderable)

    def on_request_inline_input(self, message: RequestInlineInput) -> None:
        """Route inline input request to active screen."""
        from .screens import MainAppScreen

        screen = self.screen
        if isinstance(screen, MainAppScreen):
            screen.enter_capture_mode(
                message.prompt_id,
                message.message,
                message.input_type,
                message.default
            )

    def on_indexing_progress(self, message: IndexingProgress) -> None:
        """Route indexing progress to active screen."""
        from .screens import MainAppScreen

        screen = self.screen
        if isinstance(screen, MainAppScreen):
            screen.update_indexing_progress(
                message=message.message,
                progress=message.progress,
                total=message.total,
                complete=message.complete
            )

    def on_activity_state_change(self, message: ActivityStateChange) -> None:
        """Route activity state changes to active screen."""
        from .screens import MainAppScreen

        screen = self.screen
        if isinstance(screen, MainAppScreen):
            screen.update_activity(message)

    def on_tasks_updated(self, message: TasksUpdated) -> None:
        """Route task updates to active screen."""
        from .screens import MainAppScreen

        screen = self.screen
        if isinstance(screen, MainAppScreen):
            screen.update_tasks(message.tasks)
