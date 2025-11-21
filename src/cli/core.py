"""
Core CLI functionality.
Main entry point and command routing for the Scrappy CLI.
"""

import sys
from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..infrastructure.protocols import BackgroundInitializerProtocol

from ..orchestrator import AgentOrchestrator
from .display import CLIDisplay
from .session import CLISessionManager
from .codebase import CLICodebaseAnalysis
from .tasks import CLITaskExecution
from .multiprovider import CLIMultiProvider
from .smart_query import CLISmartQuery
from .agent_manager import CLIAgentManager
from .task_router_handler import CLITaskRouterHandler
from .io_interface import CLIIOProtocol
from .rich_output import RichIO
from .tool_detector import needs_tool_support
from .input_handler import InputHandler
from .state_manager import PlanStateManager
from .session_context import SessionContext
from .command_router import CommandRouter
from .interactive import InteractiveMode
from .utils.session_utils import display_previous_session_detected
from .utils.cli_factory import initialize_cli_handlers
from .exceptions import CLIError, SessionError, TaskExecutionError
from .error_recovery import graceful_degrade, error_recovery_context
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
        state_manager: Optional[PlanStateManager] = None,
        semantic_search_initializer: Optional['BackgroundInitializerProtocol'] = None
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
            semantic_search_initializer: Injectable background initializer for semantic search
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

        # Background initializer for semantic search (heavy dependencies)
        self.semantic_search_initializer = semantic_search_initializer or self._create_default_semantic_search_initializer()

        # Initialize component handlers using factory
        handlers = initialize_cli_handlers(self.orchestrator, self.session_start)
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

        # Start background initialization of semantic search (non-blocking)
        self.semantic_search_initializer.start()
        self.io.secho("Loading semantic search in background...", fg="cyan")

        # Log initialization
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

        # Auto-detect and offer to load previous session
        if offer_session_restore:
            self._check_and_offer_session_restore(io=self.io)

        self.io.echo()

        return self

    # Factory methods for default dependencies

    def _create_default_io(self) -> CLIIOProtocol:
        """Create default IO interface."""
        return RichIO()

    def _create_default_orchestrator(self) -> AgentOrchestrator:
        """Create default orchestrator."""
        orch = AgentOrchestrator(
            context_aware=self._context_aware,
            verbose_selection=self._verbose_selection,
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

    def _create_default_semantic_search_initializer(self) -> 'BackgroundInitializerProtocol':
        """Create default semantic search initializer."""
        from ..context.semantic import SemanticSearchInitializer
        project_path = self.orchestrator.context.project_path
        return SemanticSearchInitializer(project_path)

    def _create_command_router(self) -> CommandRouter:
        """Create CommandRouter with all dependencies."""
        return CommandRouter(
            io=self.io,
            orchestrator=self.orchestrator,
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

    def _create_interactive_mode(self) -> InteractiveMode:
        """Create InteractiveMode with all dependencies."""
        return InteractiveMode(
            io=self.io,
            orchestrator=self.orchestrator,
            session_context=self.session_context,
            state_manager=self.state_manager,
            input_handler=self.input_handler,
            command_router=self._create_command_router(),
            display=self.display,
            smart=self.smart,
            task_router=self.task_router,
            tasks=self.tasks,
            logger=self.logger
        )

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
                    io.echo(f"  Files: {result['files_restored']}")
                    io.echo(f"  Searches: {result['searches_restored']}")
                    io.echo(f"  Git ops: {result['git_ops_restored']}")
                    io.echo(f"  Discoveries: {result['discoveries_restored']}")
                    self.logger.info("Session restored", extra={
                        "files": result['files_restored'],
                        "searches": result['searches_restored'],
                    })
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
