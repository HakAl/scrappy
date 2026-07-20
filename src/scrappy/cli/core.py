"""
Core CLI functionality.
Main entry point and command routing for the Scrappy CLI.
"""

import sys
from datetime import datetime
from typing import Optional, TYPE_CHECKING


if TYPE_CHECKING:
    from .textual import ThreadSafeAsyncBridge
    from .textual.langgraph_bridge import LangGraphBridge

from ..orchestrator import AgentOrchestrator
from .io_interface import CLIIOProtocol
from .unified_io import UnifiedIO
from .input_handler import InputHandler
from .state_manager import PlanStateManager
from .session_context import SessionContext
from .command_router import CommandRouter
from .textual_interactive import TextualInteractiveMode
from .command_history import CommandHistory, get_default_history_path
from .utils.session_utils import display_previous_session_detected
from .utils.cli_factory import initialize_cli_handlers, create_conversation_store
from .error_recovery import graceful_degrade
from .logging import get_logger
from scrappy.infrastructure.persistence import ConversationStoreProtocol
from scrappy.infrastructure.theme import ThemeProtocol, DEFAULT_THEME


class CLI:
    """Interactive CLI for the Scrappy."""

    def __init__(
        self,
        brain: Optional[str] = None,
        auto_explore: bool = False,
        context_aware: bool = True,
        show_provider_status: bool = False,
        io: Optional[CLIIOProtocol] = None,
        orchestrator: Optional[AgentOrchestrator] = None,
        state_manager: Optional[PlanStateManager] = None,
        theme: Optional[ThemeProtocol] = None,
        conversation_store: Optional[ConversationStoreProtocol] = None
    ):
        """
        Initialize CLI with orchestrator and component handlers.

        Construction is side effect free: it assigns dependencies and builds bare
        objects only. All I/O is deferred to initialize() -- the default
        orchestrator's provider/brain setup and exploration (orch.initialize), the
        default conversation store, history loading, staleness checks, and the
        file-backed command history are all created there, not here. The default
        orchestrator is built as a bare object in __init__ but not initialized until
        initialize() runs.

        Call initialize() after construction to perform setup and display initialization messages.

        Args:
            brain: Provider name to use as the orchestrator brain. If None, uses
                the first available provider.
            auto_explore: If True, automatically explore the codebase on startup.
            context_aware: If True, enable context-aware features that consider
                project structure in responses.
            show_provider_status: If True, display provider availability status
                instead of default initialization messages.
            io: IO interface for input/output operations. Defaults to RichIO.
            orchestrator: Injectable orchestrator instance (default: creates new AgentOrchestrator)
            state_manager: Injectable state manager (default: creates new PlanStateManager)
            theme: Theme for styling. Defaults to DEFAULT_THEME.
            conversation_store: Injectable persistence store (default: creates one
                via create_conversation_store, which performs filesystem I/O).
                Inject a store (or fake) to keep construction side effect free.
        """
        # Store config for factory methods and initialization
        self._brain = brain
        self._auto_explore = auto_explore
        self._context_aware = context_aware
        self._show_provider_status = show_provider_status
        self._theme = theme or DEFAULT_THEME

        # Initialize dependencies using factory methods
        self.io = io or self._create_default_io()
        # The default orchestrator is built as a bare object here; its provider
        # probing / brain setup / exploration (orch.initialize) is deferred to
        # CLI.initialize() so construction performs no I/O. An injected orchestrator
        # is the caller's responsibility and is never initialized by the CLI.
        self._orchestrator_is_default = orchestrator is None
        self.orchestrator = orchestrator or self._create_default_orchestrator()
        self.session_start = datetime.now()

        # Initialize state manager for plan tracking
        self.state_manager = state_manager or self._create_default_state_manager()

        # Conversation persistence is injectable. Default-store creation, history
        # loading, and staleness checks all perform filesystem I/O, so they are
        # deferred to initialize() (see _load_persisted_conversation). __init__ only
        # holds the injected store (or None) and builds an empty session context so
        # the attribute exists right after construction; initialize() rebuilds it
        # with the loaded history. An injected store is held as-is and never
        # replaced -- it is Protocol-typed, so a falsy __bool__/__len__ must not
        # trigger a silent default.
        self._conversation_store = conversation_store
        self._session_is_stale = False

        # Create session context for shared state management (history loaded later)
        self.session_context = SessionContext(
            conversation_history=[],
            conversation_store=conversation_store,
            was_stale_at_load=False,
        )

        # Initialize component handlers using factory (pass theme)
        handlers = initialize_cli_handlers(
            self.orchestrator, self.session_start, self.io, theme=self._theme
        )
        self.display = handlers['display']
        self.session_mgr = handlers['session_mgr']
        self.codebase = handlers['codebase']
        self.tasks = handlers['tasks']
        self.agent_mgr = handlers['agent_mgr']

        # Command history for CLI mode (enables up/down arrow navigation). Starts
        # in-memory (no I/O); initialize() loads the file-backed history via
        # _load_command_history. TUI mode uses Textual's TextArea history.
        self.command_history = CommandHistory(history_file=None)
        self.input_handler = InputHandler(self.io, history=self.command_history)

        # Logger for structured logging
        self.logger = get_logger("cli.core", io=self.io)

    def initialize(self, offer_session_restore: bool = True):
        """
        Initialize CLI with minimal display messages.

        Call this after construction to perform I/O operations.

        Args:
            offer_session_restore: If True, silently restore previous session if available

        Returns:
            self (for method chaining)
        """

        # Perform the setup/I/O deferred out of __init__. Orchestrator setup runs
        # first so providers/brain are ready before conversation state loads.
        self._initialize_orchestrator()
        self._load_persisted_conversation()
        self._load_command_history()

        # Silently restore previous session (working memory: files, searches, etc.)
        if offer_session_restore:
            self._silent_session_restore()

        self.io.echo()

        return self

    def _load_persisted_conversation(self) -> None:
        """Load previously persisted conversation history into the session context.

        Deferred out of __init__ because it performs filesystem I/O: it creates the
        default conversation store when none was injected, reads token-budgeted
        recent history, and checks staleness. Rebuilds self.session_context with the
        loaded history; safe because session_context consumers run after initialize().
        """
        store = self._conversation_store
        if store is None:
            store = create_conversation_store(self.orchestrator)
            self._conversation_store = store

        loaded_history: list = []
        if store is not None:
            loaded_history = store.get_recent(token_budget=8000)

            # Staleness informs the LLM that restored context may be outdated.
            if loaded_history:
                from scrappy.infrastructure.persistence import (
                    check_session_staleness,
                    get_stale_context_message,
                )
                last_time = store.get_last_message_time()
                if check_session_staleness(last_time):
                    self._session_is_stale = True
                    loaded_history = [get_stale_context_message()] + loaded_history

        self.session_context = SessionContext(
            conversation_history=loaded_history,
            conversation_store=store,
            was_stale_at_load=self._session_is_stale,
        )

    def _load_command_history(self) -> None:
        """Load the file-backed command history (creates ~/.scrappy and reads it).

        Deferred out of __init__; until called, an in-memory history is used.
        """
        self.command_history = CommandHistory(history_file=get_default_history_path())
        self.input_handler = InputHandler(self.io, history=self.command_history)

    # Factory methods for default dependencies

    def _create_default_io(self) -> CLIIOProtocol:
        """Create default IO interface for CLI (Textual).

        CLI always uses Textual, so this creates UnifiedIO with OutputSink.
        Uses the configured theme for styling.
        """
        from .textual.output_adapter import TextualOutputAdapter
        output_adapter = TextualOutputAdapter()
        return UnifiedIO(output_sink=output_adapter, theme=self._theme)

    def _create_default_orchestrator(self) -> AgentOrchestrator:
        """Build the default orchestrator object (no provider setup / I/O).

        Provider probing, brain setup, and exploration are deferred to
        _initialize_orchestrator(), called from initialize(), so construction
        stays side effect free. AgentOrchestrator.__init__ itself assigns
        dependencies only.
        """
        return AgentOrchestrator(
            project_path=".",
            context_aware=self._context_aware,
            enable_semantic_search=True,  # Enable for CLI usage
        )

    def _initialize_orchestrator(self) -> None:
        """Set up the default orchestrator's providers/brain/exploration.

        Deferred out of __init__ because it performs I/O (provider probing,
        optional codebase exploration). Only the CLI-created default orchestrator
        is initialized; an injected orchestrator is the caller's responsibility and
        is left untouched (mirrors the injected conversation-store contract).
        """
        if not self._orchestrator_is_default:
            return
        self.orchestrator.initialize(
            auto_register=True,
            orchestrator_provider=self._brain,
            auto_explore=self._auto_explore,
            show_provider_status=self._show_provider_status,
        )

    def _create_default_state_manager(self) -> PlanStateManager:
        """Create default state manager."""
        return PlanStateManager()

    def _create_command_router(self) -> CommandRouter:
        """Create CommandRouter with all dependencies.

        The concrete orchestrator satisfies SessionSaverProtocol structurally
        and carries the model selection service the router displays tiers
        through.
        """
        model_selection = self.orchestrator.model_selector
        if model_selection is None:
            raise RuntimeError(
                "Orchestrator has no model selection service configured"
            )
        return CommandRouter(
            io=self.io,
            orchestrator=self.orchestrator,
            session_context=self.session_context,
            display=self.display,
            session_mgr=self.session_mgr,
            codebase=self.codebase,
            tasks=self.tasks,
            agent_mgr=self.agent_mgr,
            session_saver=self.orchestrator,
            model_selection=model_selection,
            state_manager=self.state_manager
        )

    def _create_interactive_mode(self) -> TextualInteractiveMode:
        """Create TextualInteractiveMode with all dependencies.

        Phase 1A: TextualInteractiveMode reuses the TextualIO created before
        CLI.initialize() ran, ensuring startup messages are buffered properly.

        Returns:
            TextualInteractiveMode instance ready to launch TUI
        """
        # Create command router for this interactive session
        command_router = self._create_command_router()

        return TextualInteractiveMode(
            orchestrator=self.orchestrator,
            session_context=self.session_context,
            state_manager=self.state_manager,
            input_handler=self.input_handler,
            command_router=command_router,
            display=self.display,
            tasks=self.tasks,
            logger=self.logger,
            io=self.io,  # Pass existing TextualIO created before initialize()
            cli=self  # Pass CLI reference for handler reinitialization with bridge
        )

    def _show_semantic_search_progress(self):
        """
        Display semantic search initialization progress.

        Uses IO abstraction for progress display to work with Textual.
        """
        import time

        # Check if initialization in progress
        status = self.orchestrator.context.get_semantic_initialization_status()
        if not status:
            return

        # If already complete, don't show progress
        if self.orchestrator.context.is_semantic_search_ready():
            return

        try:
            # Use IO spinner context manager - simpler than Live display
            with self.io.spinner("Loading semantic search..."):
                max_wait_seconds = 2.0
                start_time = time.time()

                while not self.orchestrator.context.is_semantic_search_ready():
                    # Check timeout
                    if time.time() - start_time > max_wait_seconds:
                        break

                    time.sleep(0.1)

            # Show completion message if ready
            if self.orchestrator.context.is_semantic_search_ready():
                self.io.secho("Semantic search ready", fg="green")
            else:
                self.io.secho("Semantic search loading in background...", fg=self.io.theme.warning)

        except Exception:
            # Gracefully handle any errors
            if not self.orchestrator.context.is_semantic_search_ready():
                status = self.orchestrator.context.get_semantic_initialization_status()
                if status:
                    self.io.secho(f"Semantic search: {status}", fg="cyan")

    def _silent_session_restore(self):
        """
        Silently restore previous session without user prompts.

        Loads session working memory (files, searches, git ops, discoveries)
        automatically if a previous session exists.
        """
        session_info = self.orchestrator.session_manager.get_session_info()

        if not session_info.get('exists', False):
            return

        if 'error' in session_info:
            return

        # Silently load session
        try:
            result = self.orchestrator.load_session()
            if result.get('status') != 'loaded':
                self.logger.warning("Session restore failed", extra={
                    "error": result.get('message', 'unknown')
                })
        except Exception as e:
            self.logger.warning("Session restore error", extra={"error": str(e)})

    def _check_and_offer_session_restore(self, io: Optional[CLIIOProtocol] = None):
        """
        Check for existing session and offer to restore it automatically.

        Looks for a previous session file and prompts the user to restore it.
        Only operates in interactive (TTY) mode.

        Args:
            io: IO interface for input/output. Defaults to self.io.

        Side Effects:
            - Displays session information to console if session exists
            - Prompts user for confirmation to restore
            - Calls orchestrator.load_session() if user confirms
            - Logs session restore outcome

        State Changes:
            - If restored, updates orchestrator's working memory with previous
              session data (files, searches, git ops, discoveries)
            - No state change if user declines or not in interactive mode

        Returns:
            None
        """
        if io is None:
            io = self.io

        # Skip session restore if not in interactive mode
        if not sys.stdin.isatty():
            return

        session_info = self.orchestrator.session_manager.get_session_info()

        if not session_info.get('exists', False):
            return

        if 'error' in session_info:
            return

        # Show session info
        display_previous_session_detected(io, session_info)

        # Offer to restore
        try:
            if io.confirm("Restore previous session?", default=True):
                def load_session():
                    return self.orchestrator.load_session()

                result = graceful_degrade(
                    load_session,
                    on_error=lambda e: {'status': 'error', 'message': str(e)},
                    io=io
                )

                if result.get('status') == 'loaded':
                    io.secho("Session restored successfully!", fg=io.theme.success)
                else:
                    error_msg = result.get('message', 'unknown error')
                    io.secho(f"Could not restore session: {error_msg}", fg=io.theme.error)
                    self.logger.warning("Session restore failed", extra={"error": error_msg})
            else:
                io.secho("Starting fresh session.", fg=io.theme.warning)
                self.logger.info("User declined session restore")
        except (EOFError, KeyboardInterrupt):
            # Non-interactive environment or user cancelled
            io.secho("Starting fresh session.", fg=io.theme.warning)
            self.logger.info("Session restore skipped (non-interactive)")

    def reinitialize_handlers_with_bridge(
        self,
        bridge: "ThreadSafeAsyncBridge",
        langgraph_bridge: "Optional[LangGraphBridge]" = None,
    ) -> None:
        """
        Re-initialize handlers that need the TUI bridge for modal dialogs.

        Called by TextualInteractiveMode.run() after the ScrappyApp creates
        the ThreadSafeAsyncBridge. This allows handlers like CLIAgentManager
        to use modal dialogs instead of blocking prompts.

        Args:
            bridge: The ThreadSafeAsyncBridge from ScrappyApp
            langgraph_bridge: Optional LangGraphBridge for new agent architecture

        Side Effects:
            - Recreates agent_mgr with TUI-aware interaction and LangGraph bridge
        """
        from .user_interaction import get_user_interaction

        # Get TUI-aware interaction handler
        interaction = get_user_interaction(self.io, bridge)

        # Re-create handlers that use user interaction
        from .agent_manager import CLIAgentManager

        self.agent_mgr = CLIAgentManager(
            self.orchestrator,
            self.io,
            interaction,
            langgraph_bridge=langgraph_bridge,
        )

    def interactive_mode(self):
        """
        Run interactive chat mode.

        Creates an InteractiveMode instance and delegates control to it for
        the main chat loop. This is the primary entry point for user interaction.

        Side Effects:
            - Displays welcome banner and command help to console
            - Runs continuous input loop until user exits
            - All user interactions are processed through InteractiveMode
            - Session may be auto-saved on exit depending on settings

        State Changes:
            - Creates InteractiveMode with shared state_manager
            - Conversation history, auto_route_mode, etc.
              are managed by the InteractiveMode instance

        Returns:
            None
        """
        # Create InteractiveMode with all dependencies
        interactive = self._create_interactive_mode()

        # Run the interactive loop
        interactive.run()
