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
from textual.theme import Theme
from textual.widgets import Label, ProgressBar
from textual.containers import Container, Vertical, Horizontal
from textual.reactive import reactive
from textual import work

from src.infrastructure.output_mode import OutputModeContext
from src.infrastructure.theme import DEFAULT_THEME, ThemeProtocol
from .input_capture import InputCaptureManager, InputRequest


if TYPE_CHECKING:
    from .interactive import InteractiveMode
    from .protocols import StatusComponentProtocol
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

    def blocking_prompt(self, message: str, default: str = "") -> str:
        """Called from worker thread - blocks until main thread provides result."""
        if threading.current_thread() is threading.main_thread():
            raise RuntimeError(
                "CRITICAL ERROR: blocking_prompt() called from Main Thread! "
                "This will cause a deadlock."
            )

        prompt_id = str(uuid.uuid4())

        with self._lock:
            event = threading.Event()
            self._pending_prompts[prompt_id] = event

        self.app.post_message(RequestInlineInput(prompt_id, message, "prompt", default))
        event.wait()

        with self._lock:
            result = self._prompt_results.pop(prompt_id)
            del self._pending_prompts[prompt_id]

        return result

    def blocking_confirm(self, question: str) -> bool:
        """Called from worker thread - blocks until main thread provides result."""
        if threading.current_thread() is threading.main_thread():
            raise RuntimeError(
                "CRITICAL ERROR: blocking_confirm() called from Main Thread! "
                "This will cause a deadlock."
            )

        prompt_id = str(uuid.uuid4())

        with self._lock:
            event = threading.Event()
            self._pending_prompts[prompt_id] = event

        self.app.post_message(RequestInlineInput(prompt_id, question, "confirm"))
        event.wait()

        with self._lock:
            result = self._prompt_results.pop(prompt_id)
            del self._pending_prompts[prompt_id]

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

    def post_output(self, content: str) -> None:
        self._queue.put(('output', content))

    def post_renderable(self, obj: Any) -> None:
        self._queue.put(('renderable', obj))

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
        self._widget: Optional[Horizontal] = None
        self._label: Optional[Label] = None
        self._bar: Optional[ProgressBar] = None

    @property
    def component_id(self) -> str:
        return "progress_indicator"

    @property
    def is_visible(self) -> bool:
        return self._active

    @property
    def widget(self) -> Horizontal:
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
        if self._label is not None:
            self._label.update(self._message)
        if self._bar is not None:
            self._bar.total = self._total or 100
            self._bar.progress = self._progress

    def update(self, progress: int, total: int, message: str) -> None:
        self._progress = progress
        self._total = total
        self._message = message
        self._active = True
        self.update_widget()

    def complete(self) -> None:
        self._active = False


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


class StatusBar(Container):
    """Dynamic status bar that shows/hides based on active components."""

    show_status = reactive(False)

    def __init__(self) -> None:
        super().__init__(id="status_bar")
        self.components: Dict[str, "StatusComponentProtocol"] = {}
        self._mounted_ids: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Vertical(id="status_content")

    def register_component(self, component: "StatusComponentProtocol") -> None:
        self.components[component.component_id] = component
        self.refresh_display()

    def unregister_component(self, component_id: str) -> None:
        if component_id in self.components:
            del self.components[component_id]
            self._mounted_ids.discard(component_id)
            self.refresh_display()

    def _get_visible_components(self) -> List["StatusComponentProtocol"]:
        return [c for c in self.components.values() if c.is_visible]

    def _update_visibility(self, has_visible: bool) -> None:
        self.show_status = has_visible
        if has_visible:
            self.add_class("show")
        else:
            self.remove_class("show")

    def _mount_components(self, visible: List["StatusComponentProtocol"]) -> None:
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

    Responsibilities:
    - Screen navigation (push/pop/switch)
    - Theme registration
    - Output queue consumption
    - Message routing to active screen
    - Codebase context management
    """

    CSS_PATH = "scrappy.tcss"

    def __init__(
        self,
        interactive_mode: "InteractiveMode",
        output_adapter: TextualOutputAdapter,
        theme: Optional[ThemeProtocol] = None,
    ):
        """Initialize the Textual app controller.

        Args:
            interactive_mode: The InteractiveMode instance with UnifiedIO
            output_adapter: The TextualOutputAdapter to consume messages from
            theme: Optional theme for consistent styling
        """
        super().__init__()
        self.interactive_mode = interactive_mode
        self.output_adapter = output_adapter
        self._theme = theme or DEFAULT_THEME
        self._should_stop_consumer = False

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

        def progress_callback(message: str) -> None:
            if self.is_running and not self._should_stop_consumer:
                self.post_message(IndexingProgress(message=message))

        context.set_indexing_progress_callback(progress_callback)

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
        if not self._has_any_provider():
            self._show_wizard_screen(allow_cancel=False)
        else:
            self._show_main_screen()

    def on_unmount(self) -> None:
        """Called when app is about to close."""
        self._should_stop_consumer = True
        OutputModeContext.set_tui_mode(False)

        if self._codebase_context is not None:
            self._codebase_context.shutdown()

    def _has_any_provider(self) -> bool:
        """Check if any provider is configured."""
        from src.infrastructure.config.api_keys import create_api_key_service
        from src.orchestrator.provider_definitions import PROVIDERS

        config_service = create_api_key_service()
        env_vars = [info.env_var for info in PROVIDERS.values()]
        return config_service.has_any_key(env_vars)

    def _show_main_screen(self) -> None:
        """Switch to main chat screen."""
        from .screens import MainAppScreen

        screen = MainAppScreen(
            interactive_mode=self.interactive_mode,
            output_adapter=self.output_adapter,
            bridge=self.bridge,
            theme=self._theme,
        )
        self.push_screen(screen)

    def _show_wizard_screen(self, allow_cancel: bool = True) -> None:
        """Push wizard screen."""
        from .screens import SetupWizardScreen

        screen = SetupWizardScreen(
            io=self.interactive_mode.io,
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
            self.interactive_mode.orchestrator._auto_register_providers()
            # Show main screen after wizard
            self.call_later(self._show_main_screen)
        else:
            # No provider configured - exit the app
            self.call_later(self.exit)

    def launch_setup_wizard(self) -> None:
        """Launch setup wizard (called by /setup command)."""
        self._show_wizard_screen(allow_cancel=True)

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
