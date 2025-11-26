"""
Core CLI functionality.
Main entry point and command routing for the Scrappy CLI.
"""

import sys
from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..infrastructure.protocols import BackgroundInitializerProtocol
    from .textual_app import ThreadSafeAsyncBridge

from ..orchestrator import AgentOrchestrator
from .io_interface import CLIIOProtocol
from .unified_io import UnifiedIO
from .input_handler import InputHandler
from .state_manager import PlanStateManager
from .session_context import SessionContext
from .command_router import CommandRouter
from .textual_interactive import TextualInteractiveMode
from .utils.session_utils import display_previous_session_detected
from .utils.cli_factory import initialize_cli_handlers
from .error_recovery import graceful_degrade
from .logging import get_logger


class CLI:
    """Interactive CLI for the Scrappy."""

    def __init__(
        self,
        brain: Optional[str] = None,
        auto_explore: bool = False,
        context_aware: bool = True,
        verbose_selection: bool = False,
        show_provider_status: bool = False,
        io: Optional[CLIIOProtocol] = None,
        orchestrator: Optional[AgentOrchestrator] = None,
        state_manager: Optional[PlanStateManager] = None
    ):
        """
        Initialize CLI with orchestrator and component handlers (dependencies only - NO side effects).

        Call initialize() after construction to perform setup and display initialization messages.

        Args:
            brain: Provider name to use as the orchestrator brain. If None, uses
                the first available provider.
            auto_explore: If True, automatically explore the codebase on startup.
            context_aware: If True, enable context-aware features that consider
                project structure in responses.
            verbose_selection: If True, display detailed provider selection info
                during initialization.
            show_provider_status: If True, display provider availability status
                instead of default initialization messages.
            io: IO interface for input/output operations. Defaults to RichIO.
            orchestrator: Injectable orchestrator instance (default: creates new AgentOrchestrator)
            state_manager: Injectable state manager (default: creates new PlanStateManager)
        """
        # Store config for factory methods and initialization
        self._brain = brain
        self._auto_explore = auto_explore
        self._context_aware = context_aware
        self._verbose_selection = verbose_selection
        self._show_provider_status = show_provider_status

        # Initialize dependencies using factory methods
        self.io = io or self._create_default_io()
        self.orchestrator = orchestrator or self._create_default_orchestrator()
        self.session_start = datetime.now()

        # Initialize state manager for plan tracking
        self.state_manager = state_manager or self._create_default_state_manager()

        # Create session context for shared state management
        self.session_context = SessionContext()

        # Initialize component handlers using factory
        handlers = initialize_cli_handlers(self.orchestrator, self.session_start, self.io)
        self.display = handlers['display']
        self.session_mgr = handlers['session_mgr']
        self.codebase = handlers['codebase']
        self.tasks = handlers['tasks']
        self.multiprovider = handlers['multiprovider']
        self.smart = handlers['smart']
        self.agent_mgr = handlers['agent_mgr']
        self.task_router = handlers['task_router']
        self.input_handler = InputHandler(self.io)

        # Logger for structured logging
        self.logger = get_logger("cli.core", io=self.io)

    def initialize(self, offer_session_restore: bool = True):
        """
        Initialize CLI with display messages and optional session restore.

        Call this after construction to perform I/O operations.

        Args:
            offer_session_restore: If True, check for and offer to restore previous session

        Returns:
            self (for method chaining)
        """
        self.io.secho("Initializing Scrappy...", fg="cyan")

        # Show verbose selection info if requested
        if self._verbose_selection:
            self.io.secho("Verbose provider selection enabled", fg="yellow")

        # Log initialization (outputs to IO)
        self.logger.info("CLI initialized", extra={
            "brain": self.orchestrator.brain,
            "auto_explore": self._auto_explore,
            "context_aware": self._context_aware,
        })

        # Display initialization info (unless show_provider_status already did)
        if not self._show_provider_status:
            brain_name = self.orchestrator.brain
            if brain_name:
                self.io.echo(f"Brain: {self.io.style(brain_name, fg='green', bold=True)}")
            else:
                self.io.secho("Brain: None (no providers available)", fg='yellow')
            providers_list = ', '.join(self.orchestrator.providers.list_available())
            if providers_list:
                self.io.echo(f"Available providers: {self.io.style(providers_list, fg='cyan')}")
            else:
                self.io.secho("No providers available - check API keys", fg='yellow')

        # Show context status
        if self.orchestrator.context.is_explored():
            self.io.secho(f"Context: {self.orchestrator.context.project_path.name} (cached)", fg="cyan")
        elif self._context_aware:
            self.io.secho("Context: Not explored (use /context to explore)", fg="yellow")

        # Show semantic search initialization progress if in progress
        self._show_semantic_search_progress()

        # Auto-detect and offer to load previous session
        if offer_session_restore:
            self._check_and_offer_session_restore(io=self.io)

        self.io.echo()

        return self

    # Factory methods for default dependencies

    # todo wrong type
    # todo wrong type
    # todo wrong type
    # todo wrong type
    def _create_default_io(self) -> CLIIOProtocol:
        """Create default IO interface for CLI (Textual).

        CLI always uses Textual, so this creates UnifiedIO with OutputSink.
        """
        from .textual_app import TextualOutputAdapter
        output_adapter = TextualOutputAdapter()
        return UnifiedIO(output_sink=output_adapter)

    def _create_default_orchestrator(self) -> AgentOrchestrator:
        """Create default orchestrator."""
        orch = AgentOrchestrator(
            context_aware=self._context_aware,
            verbose_selection=self._verbose_selection,
            enable_semantic_search=True,  # Enable for CLI usage
        )
        orch.initialize(
            auto_register=True,
            orchestrator_provider=self._brain,
            auto_explore=self._auto_explore,
            show_provider_status=self._show_provider_status
        )
        return orch

    def _create_default_state_manager(self) -> PlanStateManager:
        """Create default state manager."""
        return PlanStateManager()

    def _create_command_router(self) -> CommandRouter:
        """Create CommandRouter with all dependencies."""
        return CommandRouter(
            io=self.io,
            orchestrator=self.orchestrator,
            # todo wrong type
            # todo wrong type
            # todo wrong type
            # todo wrong type
            session_context=self.session_context,
            display=self.display,
            session_mgr=self.session_mgr,
            codebase=self.codebase,
            tasks=self.tasks,
            multiprovider=self.multiprovider,
            smart=self.smart,
            agent_mgr=self.agent_mgr,
            task_router=self.task_router,
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
            # todo wrong type
            # todo wrong type
            # todo wrong type
            # todo wrong type
            session_context=self.session_context,
            state_manager=self.state_manager,
            input_handler=self.input_handler,
            command_router=command_router,
            display=self.display,
            smart=self.smart,
            task_router=self.task_router,
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
                self.io.secho("Semantic search loading in background...", fg="yellow")

        except Exception as e:
            # Gracefully handle any errors
            if not self.orchestrator.context.is_semantic_search_ready():
                status = self.orchestrator.context.get_semantic_initialization_status()
                if status:
                    self.io.secho(f"Semantic search: {status}", fg="cyan")

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
                    io.secho("Session restored successfully!", fg="green")
                else:
                    error_msg = result.get('message', 'unknown error')
                    io.secho(f"Could not restore session: {error_msg}", fg="red")
                    self.logger.warning("Session restore failed", extra={"error": error_msg})
            else:
                io.secho("Starting fresh session.", fg="yellow")
                self.logger.info("User declined session restore")
        except (EOFError, KeyboardInterrupt):
            # Non-interactive environment or user cancelled
            io.secho("Starting fresh session.", fg="yellow")
            self.logger.info("Session restore skipped (non-interactive)")

    def reinitialize_handlers_with_bridge(self, bridge: "ThreadSafeAsyncBridge") -> None:
        """
        Re-initialize handlers that need the TUI bridge for modal dialogs.

        Called by TextualInteractiveMode.run() after the ScrappyApp creates
        the ThreadSafeAsyncBridge. This allows handlers like CLIAgentManager
        and CLIMultiProvider to use modal dialogs instead of blocking prompts.

        Args:
            bridge: The ThreadSafeAsyncBridge from ScrappyApp

        Side Effects:
            - Recreates agent_mgr and multiprovider with TUI-aware interaction
            - Updates command_router reference if it exists
        """
        from .user_interaction import get_user_interaction

        # Get TUI-aware interaction handler
        interaction = get_user_interaction(self.io, bridge)

        # Re-create handlers that use user interaction
        from .agent_manager import CLIAgentManager
        from .multiprovider import CLIMultiProvider

        self.agent_mgr = CLIAgentManager(self.orchestrator, self.io, interaction)
        self.multiprovider = CLIMultiProvider(self.orchestrator, self.io, interaction)

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
            - Conversation history, multiline_mode, auto_route_mode, etc.
              are managed by the InteractiveMode instance

        Returns:
            None
        """
        # Create InteractiveMode with all dependencies
        interactive = self._create_interactive_mode()

        # Run the interactive loop
        interactive.run()
