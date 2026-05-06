"""
Textual-based TUI application for Scrappy CLI.

Provides an interactive terminal UI using the Textual framework,
wrapping the existing InteractiveMode with a modern UI.
"""

from typing import TYPE_CHECKING, Optional, Callable, Any, cast
import asyncio
import json
import logging
import os
import time
from pathlib import Path

from textual.app import App
from textual.theme import Theme
from textual.reactive import reactive
from textual import work
from textual.widgets import TextArea

from scrappy.cli.protocols import ActivityState, ClipboardProtocol
from scrappy.infrastructure.output_mode import OutputModeContext
from scrappy.infrastructure.theme import DEFAULT_THEME, ThemeProtocol

from .runtime_wiring import create_textual_runtime_session, wire_textual_runtime
from .bridge import ThreadSafeAsyncBridge
from .event_sink import TextualTuiEventSink
from .output_adapter import TextualOutputAdapter
from .tui_events import (
    ActivityChanged,
    CliReadyChanged,
    FlushRequested,
    IndexingProgressChanged,
    MetricsUpdated,
    PromptRequested,
    ShutdownRequested,
    TranscriptClear,
    TasksUpdated,
    TranscriptAppendRenderable,
    TranscriptAppendText,
    TuiEventTarget,
    TuiEventMessage,
)

if TYPE_CHECKING:
    from ..interactive import InteractiveMode
    from ..core import CLI
    from ..unified_io import UnifiedIO
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
        clipboard: Optional[ClipboardProtocol] = None,
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
            clipboard: Clipboard service for OS clipboard integration
        """
        super().__init__()
        self._theme = theme or DEFAULT_THEME
        self._shutdown_requested = False
        self._clipboard_service = clipboard or self._create_default_clipboard()
        self.tui_event_sink = TextualTuiEventSink(self)
        if output_adapter is not None:
            output_adapter.bind_event_sink(self.tui_event_sink)

        # Deferred initialization mode
        self._cli_factory = cli_factory
        self._cli: Optional["CLI"] = None

        # In deferred mode, create output adapter now (needed for skeleton screen)
        if cli_factory is not None:
            self.output_adapter = output_adapter or TextualOutputAdapter(self.tui_event_sink)
            self.interactive_mode: Optional["InteractiveMode"] = None
            self.ready = False  # Will be set True when CLI is ready
        else:
            # Immediate mode (legacy)
            if interactive_mode is None:
                raise ValueError("Must provide either interactive_mode or cli_factory")
            self.interactive_mode = interactive_mode
            self.output_adapter = output_adapter or TextualOutputAdapter(self.tui_event_sink)
            self.ready = True

        # Thread-safe async bridge for prompts/confirms
        self.bridge = ThreadSafeAsyncBridge(self)

        # Track last Ctrl+C time for double-tap exit
        self._last_ctrl_c_time: float = 0.0

        # Codebase context for semantic search indexing
        self._codebase_context: Optional["CodebaseContext"] = None
        self._buffered_main_transcript_events: list[
            TranscriptAppendText | TranscriptAppendRenderable | TranscriptClear
        ] = []
        self._buffered_main_transcript_omissions = 0
        self._main_transcript_buffer_draining = False

        self._runtime_cleanup_done = False
        self._integration_log_path = os.getenv("SCRAPPY_INTEGRATION_LOG_PATH")
        self._integration_ready_file = os.getenv("SCRAPPY_READY_FILE")
        self._integration_ready_signaled = False

    def _create_default_clipboard(self) -> ClipboardProtocol:
        """Create the default clipboard service."""
        from .clipboard import PyperclipClipboard

        return PyperclipClipboard()

    def copy_to_clipboard(self, text: str) -> None:
        """Copy text to both Textual's local clipboard and the system clipboard."""
        try:
            self._clipboard_service.copy_text(text)
        except Exception as e:
            logger.debug("Failed to copy to system clipboard: %s", e)

        super().copy_to_clipboard(text)

    def restore_mouse_support(self) -> None:
        """Re-enable terminal mouse reporting when the driver supports it.

        Real Windows terminals can lose Textual mouse mode after subprocess-heavy
        flows or noisy startup output. Reasserting mouse support is safe and helps
        keep text selection working in the chat log.
        """
        driver = getattr(self, "_driver", None)
        enable_mouse = getattr(driver, "_enable_mouse_support", None)
        if not callable(enable_mouse):
            return

        try:
            enable_mouse()
        except Exception as e:
            logger.debug("Failed to restore mouse support: %s", e)

    def _write_integration_event(self, event: str, **fields: object) -> None:
        """Append a structured integration event when the harness enables it."""
        if not self._integration_log_path:
            return

        payload: dict[str, object] = {
            "ts": round(time.time(), 3),
            "source": "app",
            "event": event,
        }
        payload.update(fields)

        try:
            log_path = Path(self._integration_log_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
        except Exception as e:
            logger.debug("Failed to write integration event: %s", e)

    def _signal_integration_ready(self) -> None:
        """Emit a ready marker after the app has refreshed into an interactive state."""
        if self._integration_ready_signaled:
            return

        self._integration_ready_signaled = True
        try:
            screen_name = type(self.screen).__name__
        except Exception:
            screen_name = None

        try:
            focused = type(self.focused).__name__ if self.focused is not None else None
        except Exception:
            focused = None

        self._write_integration_event(
            "ui_ready",
            ready=self.ready,
            screen=screen_name,
            focused=focused,
            interactive_mode=self.interactive_mode is not None,
        )

        if not self._integration_ready_file:
            return

        try:
            ready_path = Path(self._integration_ready_file)
            ready_path.parent.mkdir(parents=True, exist_ok=True)
            ready_path.write_text("ready\n", encoding="utf-8")
        except Exception as e:
            logger.debug("Failed to write integration ready file: %s", e)

    def _signal_command_idle(self) -> None:
        """Emit an integration event after a command completes and the frame is painted."""
        self._write_integration_event("command_idle", rendered=True)

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
            if not self._shutdown_requested:
                logger.debug(f"Posting indexing progress: {message}")
                self.tui_event_sink.post_event(
                    IndexingProgressChanged(
                        message=message,
                        progress=progress,
                        total=total,
                    )
                )

        context.set_indexing_progress_callback(progress_callback)

        # Check if semantic search is already ready (init completed before callback was set)
        # If so, send a ready message to update the UI directly (bypass is_running check)
        if hasattr(context, 'is_semantic_search_ready') and context.is_semantic_search_ready():
            logger.info("Semantic search already ready when callback registered, posting ready message")
            self.tui_event_sink.post_event(
                IndexingProgressChanged(message="Semantic search ready")
            )

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
        self._write_integration_event(
            "app_mount",
            deferred=self._cli_factory is not None,
            ready=self.ready,
        )

        # Navigate to appropriate screen
        has_provider, env_key_count = self._check_and_migrate_providers()

        # Check if disclaimer has been acknowledged
        from scrappy.infrastructure.config.api_keys import create_api_key_service
        config_service = create_api_key_service()
        disclaimer_acknowledged = config_service.is_disclaimer_acknowledged()

        # Mock mode bypasses wizard (for e2e testing)
        from scrappy.orchestrator.mock_llm_service import is_mock_mode_enabled
        mock_mode = is_mock_mode_enabled()

        if not mock_mode and (not has_provider or not disclaimer_acknowledged):
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

        Posts a typed CLI-ready event through the shared sink.
        """
        if self._cli_factory is None:
            return

        try:
            # This is the slow part - runs in thread pool
            cli = self._cli_factory()

            self.tui_event_sink.post_event(CliReadyChanged(cli=cli))
        except Exception as e:
            error_msg = str(e)
            logger.exception("Failed to initialize CLI: %s", e)
            self.tui_event_sink.post_event(CliReadyChanged(error=error_msg))

    def _handle_cli_ready(self, message: CliReadyChanged) -> None:
        """Handle CLI initialization completion.

        Called on main thread after background worker finishes.
        Wires up InteractiveMode and sets ready=True.
        """
        if message.error:
            # Show error in status bar - user can /setup to fix
            self.output_adapter.post_output(
                f"Startup error: {message.error}\nUse /setup to configure providers.\n"
            )
            self._write_integration_event("cli_ready_error", error=message.error)
            # Still mark as ready so user can interact
            self.ready = True
            return

        if message.cli is None:
            return

        self._cli = message.cli
        self._setup_interactive_mode()
        self.ready = True
        self._write_integration_event("cli_ready", ready=self.ready)

        # Display status lines now that CLI is ready (header already shown on mount)
        from scrappy.cli.interactive_banner import display_banner_status
        display_banner_status(self._cli.io)
        self.call_after_refresh(self.restore_mouse_support)
        self.call_after_refresh(self._signal_integration_ready)

    def _setup_interactive_mode(self) -> None:
        """Wire up InteractiveMode from CLI.

        Called after CLI is created (either sync or async).
        Sets up the interactive_mode and related callbacks.
        """
        if self._cli is None:
            return

        self.interactive_mode = create_textual_runtime_session(
            io=self._cli.io,
            orchestrator=self._cli.orchestrator,
            session_context=self._cli.session_context,
            state_manager=self._cli.state_manager,
            input_handler=self._cli.input_handler,
            command_router=self._cli._create_command_router(),
            display=self._cli.display,
            tasks=self._cli.tasks,
            logger=self._cli.logger,
            output_adapter=self.output_adapter,
        )

        wire_textual_runtime(
            app=self,
            interactive_mode=self.interactive_mode,
            io=self._cli.io,
            orchestrator=self._cli.orchestrator,
            output_adapter=self.output_adapter,
            cli=self._cli,
            setup_wizard_callback=self.launch_setup_wizard,
        )

    def exit(  # type: ignore[override]
        self,
        result: object = None,
        return_code: int = 0,
        message: object = None,
    ) -> None:
        """Override exit to ensure clean shutdown of all resources.

        Signal app-owned runtime resources before Textual waits for workers.
        """
        self._file_log("exit(): starting")

        # Signal event sinks and runtime resources before cancelling workers.
        self._shutdown_requested = True
        self.tui_event_sink.request_shutdown()
        self.output_adapter.request_shutdown()
        self._file_log("exit(): event sinks signaled")

        # Unblock any bridge operations (prompts/confirms)
        self.bridge.shutdown()
        self._file_log("exit(): bridge shutdown")

        # Cancel any running agent
        if hasattr(self, 'interactive_mode') and self.interactive_mode:
            agent_mgr = self.interactive_mode.command_router.agent_mgr
            if agent_mgr:
                agent_mgr.cancel()
                self._file_log("exit(): agent cancelled")

        # Cancel all Textual workers before calling exit
        # This prevents Textual's shutdown from waiting indefinitely for workers
        try:
            self._file_log(f"exit(): workers._workers={list(self.workers._workers)}")
            for w in list(self.workers._workers):
                self._file_log(f"exit(): worker name={w.name}, state={w.state}, is_finished={w.is_finished}")
            self.workers.cancel_all()
            self._file_log("exit(): cancel_all called, waiting briefly for workers...")
            # Give workers a moment to actually cancel
            import asyncio
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                # Can't use run_until_complete here, just sleep briefly.
                time.sleep(0.1)
            for w in list(self.workers._workers):
                self._file_log(f"exit(): after cancel - worker name={w.name}, state={w.state}, is_finished={w.is_finished}")
        except Exception as e:
            import traceback
            self._file_log(f"exit(): error cancelling workers: {e}")
            self._file_log(f"exit(): traceback: {traceback.format_exc()}")

        self._cleanup_runtime_resources()
        self._file_log("exit(): calling super().exit()")
        super().exit(result, return_code, str(message) if message else None)
        self._file_log("exit(): super().exit() returned")

    def _cleanup_runtime_resources(self) -> None:
        """Release app-owned runtime resources once during shutdown."""
        if self._runtime_cleanup_done:
            return

        self._runtime_cleanup_done = True
        self._shutdown_requested = True
        self.tui_event_sink.request_shutdown()
        self.output_adapter.request_shutdown()
        OutputModeContext.set_tui_mode(False)

        # Signal bridge to release any blocked worker threads (redundant but safe)
        self.bridge.shutdown()

        if hasattr(self, 'interactive_mode') and self.interactive_mode:
            try:
                self.interactive_mode.session_context.close()
            except Exception as e:
                logger.debug("Error closing session context: %s", e)

        if self._codebase_context is not None:
            # Short timeout since daemon threads will be killed on process exit anyway
            self._codebase_context.shutdown(timeout=0.5)

        # Clean up tool adapter (stops Docker containers)
        if hasattr(self, '_tool_adapter') and self._tool_adapter is not None:
            try:
                self._tool_adapter.cleanup()
            except Exception as e:
                logger.debug("Error cleaning up tool adapter: %s", e)

        # Cancel background tasks and close LLM service
        if hasattr(self, 'interactive_mode') and self.interactive_mode:
            orchestrator = cast(Any, self.interactive_mode.orchestrator)
            # Cancel any pending background tasks first
            try:
                cancelled = orchestrator.cancel_all_background_tasks()
                if cancelled > 0:
                    logger.debug("Cancelled %d background tasks on shutdown", cancelled)
            except Exception as e:
                logger.debug("Error cancelling background tasks: %s", e)

            # Flush and shutdown tracing (langfuse) before closing HTTP sessions
            try:
                from scrappy.graph.tracing import shutdown_tracing
                shutdown_tracing()
            except Exception as e:
                logger.debug("Error shutting down tracing: %s", e)

            # Close LLM service HTTP sessions
            try:
                orchestrator.llm_service.close()
            except Exception as e:
                logger.debug("Error closing LLM service: %s", e)

    def on_unmount(self) -> None:
        """Called when app is about to close."""
        self._cleanup_runtime_resources()

    async def _shutdown(self) -> None:  # type: ignore[override]
        """Run Textual shutdown.

        After Textual cleanup, we must shut down the default executor ourselves
        to prevent asyncio.run() from hanging. The issue: Textual's _win_sleep.py
        creates non-daemon threads via run_in_executor(None, func). These threads
        block asyncio.run() from returning unless we explicitly shut down the
        executor without waiting.

        Additionally, Textual's _shutdown() can hang indefinitely after running
        agent commands. We cancel pending asyncio tasks first to help it complete.
        """
        self._file_log("_shutdown: starting")

        # Cancel all pending asyncio tasks except the current one.
        # This helps Textual's shutdown complete when there are lingering tasks.
        loop = asyncio.get_running_loop()
        current_task = asyncio.current_task()
        pending_tasks = [t for t in asyncio.all_tasks(loop) if t is not current_task and not t.done()]
        self._file_log(f"_shutdown: cancelling {len(pending_tasks)} pending tasks")
        for task in pending_tasks:
            task.cancel()

        # Give cancelled tasks a moment to process their cancellation
        if pending_tasks:
            try:
                await asyncio.wait(pending_tasks, timeout=0.5)
            except Exception:
                pass
            self._file_log("_shutdown: pending tasks cancelled")

        try:
            await super()._shutdown()
            self._file_log("_shutdown: super()._shutdown() completed")
        except Exception as e:
            self._file_log(f"_shutdown: super()._shutdown() error: {e}")

        # Shut down the default executor to prevent asyncio.run() from hanging.
        # asyncio.run() calls loop.shutdown_default_executor() after our code
        # completes, but that hangs waiting for Textual's non-daemon threads.
        # By shutting it down here with wait=False and clearing the reference,
        # we prevent the hang.
        try:
            loop = asyncio.get_running_loop()
            executor = getattr(loop, '_default_executor', None)
            if executor is not None:
                self._file_log("_shutdown: shutting down default executor (wait=False)")
                executor.shutdown(wait=False, cancel_futures=True)
                # Clear the reference so asyncio.run() doesn't try to shut it down again
                loop._default_executor = None  # type: ignore[attr-defined]
                self._file_log("_shutdown: default executor cleared")
        except Exception as e:
            self._file_log(f"_shutdown: executor shutdown error: {e}")

        self._file_log("_shutdown: complete")

    def _file_log(self, msg: str) -> None:
        """Debug log to file (bypasses Textual's stderr capture)."""
        import tempfile
        logpath = os.path.join(tempfile.gettempdir(), "scrappy_shutdown_debug.log")
        try:
            with open(logpath, "a") as f:
                f.write(f"{time.time():.2f}: {msg}\n")
        except Exception:
            pass

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
            clipboard=self._clipboard_service,
        )
        self.push_screen(screen)
        self.call_later(self._drain_main_transcript_buffer)

        # Display banner header immediately (doesn't need CLI)
        from scrappy.cli.interactive_banner import display_banner_header_tui

        display_banner_header_tui(self.output_adapter)
        self.call_after_refresh(self.restore_mouse_support)
        self._write_integration_event(
            "main_screen_shown",
            ready=self.ready,
            interactive_mode=self.interactive_mode is not None,
        )

        # Show welcome message if keys were found in environment
        if env_key_count > 0:
            key_word = "key" if env_key_count == 1 else "keys"
            self.output_adapter.post_output(
                f"Found {env_key_count} API {key_word} in environment. Use /setup to add more.\n"
            )

        if self.ready and self.interactive_mode is not None:
            self.call_after_refresh(self._signal_integration_ready)

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
            io=cast("UnifiedIO", self.interactive_mode.io),
            key_validator=create_key_validator(),
            clipboard=self._clipboard_service,
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
                orchestrator = cast(Any, self.interactive_mode.orchestrator)
                orchestrator._auto_register_providers()
                # Refresh provider state now that API keys are saved.
                orchestrator.refresh_provider_configuration()
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

    # =========================================================================
    # Message Handlers - Route to Active Screen
    # =========================================================================

    def on_tui_event_message(self, message: TuiEventMessage) -> None:
        """Dispatch typed TUI events from the single boundary message."""
        event = message.event
        if isinstance(event, (TranscriptAppendText, TranscriptAppendRenderable, TranscriptClear)):
            self._route_transcript_event(event)
        elif isinstance(event, ActivityChanged):
            self._route_activity_changed(event)
        elif isinstance(event, TasksUpdated):
            self._route_tasks_updated(event)
        elif isinstance(event, MetricsUpdated):
            self._route_metrics_updated(event)
        elif isinstance(event, IndexingProgressChanged):
            self._route_indexing_progress_changed(event)
        elif isinstance(event, PromptRequested):
            self._route_prompt_requested(event)
        elif isinstance(event, CliReadyChanged):
            self._handle_cli_ready(event)
        elif isinstance(event, FlushRequested):
            self.tui_event_sink.acknowledge_flush(event.flush_id)
        elif isinstance(event, ShutdownRequested):
            self.exit()
        else:
            logger.debug(
                "on_tui_event_message: unhandled event %s",
                type(event).__name__,
            )

    def _active_main_screen(self):
        """Return the active main screen, if any."""
        from ..screens import MainAppScreen

        screen = self.screen
        return screen if isinstance(screen, MainAppScreen) else None

    def _active_wizard_screen(self):
        """Return the active wizard screen, if any."""
        from ..screens import SetupWizardScreen

        screen = self.screen
        return screen if isinstance(screen, SetupWizardScreen) else None

    def _route_transcript_event(
        self,
        event: TranscriptAppendText | TranscriptAppendRenderable | TranscriptClear,
    ) -> None:
        """Route transcript events to the intended surface."""
        if event.target == TuiEventTarget.WIZARD_TRANSCRIPT:
            wizard_screen = self._active_wizard_screen()
            if wizard_screen is not None:
                self._render_transcript_event(wizard_screen, event)
            return

        main_screen = self._active_main_screen()
        if main_screen is None or getattr(main_screen, "_layout", None) is None:
            self._buffer_main_transcript_event(event)
            return

        self._render_transcript_event(main_screen, event)

    def _render_transcript_event(
        self,
        screen: Any,
        event: TranscriptAppendText | TranscriptAppendRenderable | TranscriptClear,
    ) -> None:
        """Render a transcript event to a screen surface."""
        if isinstance(event, TranscriptAppendText):
            screen.write_output(event.content)
        elif isinstance(event, TranscriptAppendRenderable):
            screen.write_renderable(event.renderable)
        else:
            screen.clear_output()

    def _buffer_main_transcript_event(
        self,
        event: TranscriptAppendText | TranscriptAppendRenderable | TranscriptClear,
    ) -> None:
        """Buffer main transcript events while another screen is active."""
        if isinstance(event, TranscriptClear):
            self._buffered_main_transcript_events.clear()
            self._buffered_main_transcript_omissions = 0
            self._buffered_main_transcript_events.append(event)
            return

        if len(self._buffered_main_transcript_events) >= 2000:
            self._buffered_main_transcript_events.pop(0)
            self._buffered_main_transcript_omissions += 1

        self._buffered_main_transcript_events.append(event)

    def _drain_main_transcript_buffer(self) -> None:
        """Replay buffered main transcript events in UI-sized batches."""
        if self._main_transcript_buffer_draining:
            return
        self._main_transcript_buffer_draining = True
        self._drain_main_transcript_buffer_batch()

    def _drain_main_transcript_buffer_batch(self) -> None:
        """Drain one buffered transcript batch."""
        main_screen = self._active_main_screen()
        if main_screen is None:
            self._main_transcript_buffer_draining = False
            return
        if getattr(main_screen, "_layout", None) is None:
            self.call_later(self._drain_main_transcript_buffer_batch)
            return

        if self._buffered_main_transcript_omissions:
            count = self._buffered_main_transcript_omissions
            self._buffered_main_transcript_omissions = 0
            main_screen.write_output(
                f"{count} transcript events truncated while wizard was active\n"
            )

        batch = self._buffered_main_transcript_events[:100]
        del self._buffered_main_transcript_events[:100]

        for event in batch:
            self._render_transcript_event(main_screen, event)

        if self._buffered_main_transcript_events:
            self.call_later(self._drain_main_transcript_buffer_batch)
        else:
            self._main_transcript_buffer_draining = False

    def _route_prompt_requested(self, event: PromptRequested) -> None:
        """Route inline input request to active screen."""
        screen = self._active_main_screen()
        if screen is not None:
            screen.enter_capture_mode(
                event.prompt_id,
                event.message,
                event.input_type,
                event.default,
            )

    def _route_indexing_progress_changed(
        self,
        event: IndexingProgressChanged,
    ) -> None:
        """Route indexing progress to active screen."""
        screen = self._active_main_screen()
        if screen is not None:
            screen.update_indexing_progress(
                message=event.message,
                progress=event.progress,
                total=event.total,
                complete=event.complete,
            )

    def _route_activity_changed(self, event: ActivityChanged) -> None:
        """Route activity state changes to active screen."""
        logger.debug(
            "on_tui_event_message: activity state=%s, screen=%s",
            event.state,
            type(self.screen).__name__,
        )
        screen = self._active_main_screen()
        if screen is not None:
            screen.update_activity(event)
        else:
            logger.warning("ActivityChanged received while main screen is not active")

        if event.state == ActivityState.IDLE:
            self.call_after_refresh(self._signal_command_idle)

    def _route_tasks_updated(self, event: TasksUpdated) -> None:
        """Route task updates to active screen."""
        screen = self._active_main_screen()
        if screen is not None:
            screen.update_tasks(event.tasks)

    def _route_metrics_updated(self, event: MetricsUpdated) -> None:
        """Route metrics updates to active screen."""
        screen = self._active_main_screen()
        if screen is not None:
            screen.update_metrics(event)

    # =========================================================================
    # Global Key Handlers
    # =========================================================================

    def on_key(self, event) -> None:
        """Global key handler for app-wide shortcuts.

        Handles keys that should work consistently across all screens:
        - ctrl+q: Hard exit (immediate, no cleanup - emergency only)
        - ctrl+c: Copy selection, cancel operations, or double-tap for clean exit
        - ctrl+shift+c: Copy selection without triggering exit/cancel behavior
        - ctrl+v / ctrl+shift+v / shift+insert: Paste from OS clipboard
        - escape: Cancel running operations (agent, capture mode)
        """
        if event.key == "ctrl+q":
            os._exit(0)

        if event.key == "ctrl+shift+c":
            if self._handle_copy_shortcut():
                event.stop()
                event.prevent_default()
            return

        if event.key in {"ctrl+v", "ctrl+shift+v", "shift+insert"}:
            if self._handle_paste_shortcut():
                event.stop()
                event.prevent_default()
            return

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
                # Check if agent has active work via the bridge
                bridge = getattr(agent_mgr, '_langgraph_bridge', None)
                if bridge is not None and bridge.is_running:
                    did_cancel = True
                agent_mgr.cancel()

        # 3. Clean up UI directly (synchronous, not via message)
        if isinstance(screen, MainAppScreen):
            screen._cancel_ui_cleanup()

        return did_cancel

    def _handle_escape(self) -> None:
        """Handle ESC key: cancel whatever is running."""
        self._cancel_operation()

    def _get_paste_target(self) -> Optional[TextArea]:
        """Return the focused TextArea, or the main input as a fallback."""
        focused = self.focused
        if isinstance(focused, TextArea):
            return focused

        from ..screens import MainAppScreen

        screen = self.screen
        if isinstance(screen, MainAppScreen) and screen._layout is not None:
            return screen._layout.input

        try:
            return self.screen.query_one(TextArea)
        except Exception:
            return None

    def _handle_copy_shortcut(self) -> bool:
        """Copy selected text from the focused input or output log."""
        from ..screens import MainAppScreen
        from ..widgets.selectable_log import SelectableLog

        focused = self.focused
        if isinstance(focused, TextArea) and focused.selected_text:
            focused.action_copy()
            return True

        screen = self.screen
        if isinstance(screen, MainAppScreen) and screen._layout is not None:
            output = screen._layout.output
            if isinstance(output, SelectableLog) and output._has_selection():
                output.action_copy_selection()
                return True

        return False

    def _handle_paste_shortcut(self) -> bool:
        """Paste the OS clipboard into the active TextArea."""
        target = self._get_paste_target()
        if target is None or target.read_only:
            return False

        try:
            clipboard_text = self._clipboard_service.paste_text()
        except Exception as e:
            logger.debug("Failed to read system clipboard: %s", e)
            return False

        self._clipboard = clipboard_text or ""
        target.focus()
        target.action_paste()
        return True

    def _handle_ctrl_c(self) -> bool:
        """Handle Ctrl+C with context-aware behavior.

        Priority:
        1. Copy selected text from input/output
        2. Double-tap exits (escape hatch when stuck)
        3. Cancel operations and clean up UI
        4. Single tap shows hint

        Returns:
            True to stop event propagation, False to let it bubble.
        """
        now = time.time()

        # 1. Copy selection if available. Do this before exit-tap tracking so
        # normal clipboard use doesn't look like an exit request.
        if self._handle_copy_shortcut():
            return True

        # 2. Double-tap exits (escape hatch when agent is stuck)
        if now - self._last_ctrl_c_time < self._CTRL_C_DOUBLE_TAP_THRESHOLD:
            self.exit()
            return True

        # Update timestamp for double-tap detection
        self._last_ctrl_c_time = now

        # 3. Cancel any running operations
        did_cancel = self._cancel_operation()

        # 4. Show hint if nothing was cancelled
        if not did_cancel:
            self.notify("Press Ctrl+C again to exit", timeout=2)

        return True
