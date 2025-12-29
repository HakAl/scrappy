"""
Textual-based TUI application for Scrappy CLI.

Provides an interactive terminal UI using the Textual framework,
wrapping the existing InteractiveMode with a modern UI.
"""

from typing import TYPE_CHECKING, Optional, Callable
import logging
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

        screen = self.screen
        if isinstance(screen, MainAppScreen):
            screen.update_activity(message)

    def on_tasks_updated(self, message: TasksUpdated) -> None:
        """Route task updates to active screen."""
        from ..screens import MainAppScreen

        screen = self.screen
        if isinstance(screen, MainAppScreen):
            screen.update_tasks(message.tasks)
