"""
Textual-based TUI application for Scrappy CLI.

Provides an interactive terminal UI using the Textual framework,
wrapping the existing InteractiveMode with a modern UI.
"""

from typing import TYPE_CHECKING, Optional, Callable
import logging
import os
import time
from pathlib import Path

from textual.app import App
from textual.theme import Theme
from textual.reactive import reactive
from textual import work

from scrappy.infrastructure.output_mode import OutputModeContext
from scrappy.infrastructure.theme import DEFAULT_THEME, ThemeProtocol

from .messages import (
    WriteOutput,
    WriteRenderable,
    RequestInlineInput,
    IndexingProgress,
    ActivityStateChange,
    TasksUpdated,
    CLIReady,
)
from .bridge import ThreadSafeAsyncBridge
from .output_adapter import TextualOutputAdapter

if TYPE_CHECKING:
    from ..interactive import InteractiveMode
    from ..core import CLI
    from ...context.codebase_context import CodebaseContext

logger = logging.getLogger(__name__)


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

    # Point to scrappy.tcss in parent directory (cli/)
    CSS_PATH = Path(__file__).parent.parent / "scrappy.tcss"

    # Double-tap threshold for Ctrl+C exit (seconds)
    _CTRL_C_DOUBLE_TAP_THRESHOLD = 0.5

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

        # Track last Ctrl+C time for double-tap exit
        self._last_ctrl_c_time: float = 0.0

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
        from ..interactive import InteractiveMode
        from ..output_bridge import OutputBridge

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

        # Create LangGraphBridge for new agent architecture
        # This bridges LangGraph async execution to Textual worker pattern
        langgraph_bridge = None
        llm_service = getattr(self._cli.orchestrator, 'llm_service', None)
        if llm_service is not None:
            from .langgraph_bridge import LangGraphBridge
            from scrappy.graph.tools import ToolAdapter

            # Create tool adapter - owned by app, passed to bridge
            # This ensures proper cleanup and reuse across agent runs
            self._tool_adapter = ToolAdapter.create_default()

            langgraph_bridge = LangGraphBridge(
                app=self,
                bridge=self.bridge,
                output_adapter=self.output_adapter,
                llm_service=llm_service,
                tool_adapter=self._tool_adapter,
            )

        # Reinitialize handlers with bridge for TUI-aware user interaction
        self._cli.reinitialize_handlers_with_bridge(self.bridge, langgraph_bridge)

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

        # Clean up tool adapter (stops Docker containers)
        if hasattr(self, '_tool_adapter') and self._tool_adapter is not None:
            try:
                self._tool_adapter.cleanup()
            except Exception as e:
                logger.debug("Error cleaning up tool adapter: %s", e)

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
        from ..screens import MainAppScreen

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
        from ..screens import SetupWizardScreen
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
                elif msg_type == 'activity':
                    # Unpack activity tuple: (state, message, elapsed_ms)
                    state, msg, elapsed_ms = content
                    self.post_message(ActivityStateChange(state, msg, elapsed_ms))
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
        from ..screens import MainAppScreen

        screen = self.screen
        if isinstance(screen, MainAppScreen):
            screen.write_output(message.content)

    def on_write_renderable(self, message: WriteRenderable) -> None:
        """Route Rich renderable to active screen."""
        from ..screens import MainAppScreen

        screen = self.screen
        if isinstance(screen, MainAppScreen):
            screen.write_renderable(message.renderable)

    def on_request_inline_input(self, message: RequestInlineInput) -> None:
        """Route inline input request to active screen."""
        from ..screens import MainAppScreen

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
        from ..screens import MainAppScreen

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
        from ..screens import MainAppScreen

        logger.debug("on_activity_state_change: state=%s, screen=%s", message.state, type(self.screen).__name__)
        screen = self.screen
        if isinstance(screen, MainAppScreen):
            screen.update_activity(message)
        else:
            logger.warning("on_activity_state_change: screen is not MainAppScreen, ignoring")

    def on_tasks_updated(self, message: TasksUpdated) -> None:
        """Route task updates to active screen."""
        from ..screens import MainAppScreen

        screen = self.screen
        if isinstance(screen, MainAppScreen):
            screen.update_tasks(message.tasks)

    # =========================================================================
    # Global Key Handlers
    # =========================================================================

    def on_key(self, event) -> None:
        """Global key handler for app-wide shortcuts.

        Handles keys that should work consistently across all screens:
        - ctrl+q: Hard exit (immediate, no cleanup - emergency only)
        - ctrl+c: Copy selection, cancel operations, or double-tap for clean exit
        - escape: Cancel running operations (agent, capture mode)
        """
        if event.key == "ctrl+q":
            os._exit(0)

        # Handle Ctrl+C
        if event.key == "ctrl+c":
            if self._handle_ctrl_c():
                event.stop()
                event.prevent_default()

        if event.key == "escape":
            self._handle_escape()
            event.stop()

    def _cancel_operation(self) -> bool:
        """Cancel any running operation and clean up UI.

        Returns True if something was cancelled, False if nothing was running.

        Cancellation cascade:
        1. Cancel capture mode if active (prompts/confirms)
        2. Cancel running agent if any
        3. Clean up UI directly (stop timer, hide indicators)
        """
        from ..screens import MainAppScreen

        screen = self.screen
        did_cancel = False

        # 1. Cancel capture mode if active (but don't call _exit_capture_ui
        # which restarts the timer - we'll clean up UI below)
        if isinstance(screen, MainAppScreen):
            if screen.capture_manager.is_capturing:
                screen.capture_manager.cancel()
                # Full UI cleanup without restarting timer
                if screen._layout:
                    screen._layout.input.placeholder = "Type your message or command..."
                screen.prompt_display.hide_prompt()
                try:
                    from ..textual import StatusBar
                    status_bar = screen.query_one(StatusBar)
                    status_bar.refresh_display()
                    input_container = screen.query_one("#input_container")
                    input_container.remove_class("capture-mode")
                except Exception:
                    pass  # UI elements might not be mounted
                did_cancel = True

        # 2. Cancel running agent (always try, let agent_mgr handle state)
        if self.interactive_mode:
            agent_mgr = self.interactive_mode.command_router.agent_mgr
            if agent_mgr:
                # Check if agent has active work
                if agent_mgr._cancellation_token is not None:
                    did_cancel = True
                agent_mgr.cancel()

        # 3. Clean up UI directly (synchronous, not via message)
        if isinstance(screen, MainAppScreen):
            screen._cancel_ui_cleanup()

        return did_cancel

    def _handle_escape(self) -> None:
        """Handle ESC key: cancel whatever is running."""
        self._cancel_operation()

    def _handle_ctrl_c(self) -> bool:
        """Handle Ctrl+C with context-aware behavior.

        Priority:
        1. Double-tap always exits (escape hatch when stuck)
        2. Copy selection if text is selected
        3. Cancel operations and clean up UI
        4. Single tap shows hint

        Returns:
            True to stop event propagation, False to let it bubble.
        """
        from ..screens import MainAppScreen
        from ..widgets.selectable_log import SelectableLog

        screen = self.screen
        now = time.time()

        # 1. Double-tap ALWAYS exits (escape hatch when agent is stuck)
        if now - self._last_ctrl_c_time < self._CTRL_C_DOUBLE_TAP_THRESHOLD:
            self.exit()
            return True

        # Update timestamp for double-tap detection
        self._last_ctrl_c_time = now

        # 2. Copy selection if available (only action that doesn't show hint)
        if isinstance(screen, MainAppScreen) and screen._layout is not None:
            output = screen._layout.output
            if isinstance(output, SelectableLog) and output._has_selection():
                output.action_copy_selection()
                return True

        # 3. Cancel any running operations
        did_cancel = self._cancel_operation()

        # 4. Show hint if nothing was cancelled
        if not did_cancel:
            self.notify("Press Ctrl+C again to exit", timeout=2)

        return True
