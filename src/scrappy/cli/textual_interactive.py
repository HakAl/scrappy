"""
Textual-based interactive mode for Scrappy CLI.

Provides a clean TUI interface using Textual framework.
"""

from typing import TYPE_CHECKING

from .textual import ScrappyApp
from .unified_io import UnifiedIO
from .interactive import InteractiveMode
from .output_bridge import OutputBridge
from .config_factory import get_config
from ..orchestrator.protocols import Orchestrator

# Re-export for backward compatibility
OrchestratorOutputAdapter = OutputBridge

if TYPE_CHECKING:
    from .state_manager import PlanStateManager
    from .session_context import SessionContextProtocol
    from .input_handler import InputHandler
    from .command_router import CommandRouter
    from .display import CLIDisplay
    from .smart_query import CLISmartQuery
    from .task_router_handler import CLITaskRouterHandler
    from .tasks import CLITaskExecution
    from .logging import CLILogger
    from .core import CLI
    from .cli_config import CLIConfig


class TextualInteractiveMode:
    """Interactive mode using Textual TUI.

    Provides a modern terminal UI with:
    - Thread-safe output routing via message queue
    - Native copy/paste support
    - Responsive UI during blocking operations
    - Clean separation of concerns via protocols

    Phase 1A: Properly injects UnifiedIO into InteractiveMode to fix the
    "split-brain" issue where output was going to the wrong IO implementation.
    """

    def __init__(
        self,
        orchestrator: Orchestrator,
        session_context: "SessionContextProtocol",
        state_manager: "PlanStateManager",
        input_handler: "InputHandler",
        command_router: "CommandRouter",
        display: "CLIDisplay",
        smart: "CLISmartQuery",
        task_router: "CLITaskRouterHandler",
        tasks: "CLITaskExecution",
        logger: "CLILogger",
        io: UnifiedIO,
        cli: "CLI" = None,
        config: "CLIConfig" = None
    ):
        """Initialize TextualInteractiveMode with all dependencies.

        Args:
            orchestrator: The orchestrator instance for routing commands
            session_context: Shared session context for state management
            state_manager: Plan state manager
            input_handler: Input handler for parsing commands
            command_router: Command router for slash commands
            display: Display handler for showing information
            smart: Smart query handler for tool-assisted queries
            task_router: Task router handler for auto-routing
            tasks: Task execution handler
            logger: Logger for structured logging
            io: UnifiedIO instance (created before CLI.initialize() ran)
            cli: Optional CLI instance for handler reinitialization with bridge
            config: Optional CLI config (loads from default locations if not provided)
        """
        self.orchestrator = orchestrator
        self.session_context = session_context
        self.state_manager = state_manager
        self.input_handler = input_handler
        self.command_router = command_router
        self.display = display
        self.smart = smart
        self.task_router = task_router
        self.tasks = tasks
        self.logger = logger
        self.io = io
        self._cli = cli
        # Load config from parameter or default locations
        self._config = config or get_config()

    def run(self) -> None:
        """Launch the Textual TUI application.

        Uses the existing UnifiedIO with OutputSink created by CLI factory.
        All output (including startup messages) will be routed through Textual.
        """
        # Get output_adapter from existing UnifiedIO (created by CLI factory)
        output_adapter = self.io.output_sink
        if output_adapter is None:
            raise RuntimeError(
                "CLI must be initialized with Textual IO (UnifiedIO with OutputSink). "
                "This is a programming error - CLI should always use Textual."
            )

        # Inject output bridge to route orchestrator output through Textual
        # OutputBridge implements BaseOutputProtocol (info/warn/error/success)
        # and routes all messages through the Textual OutputSink
        orchestrator_output = OutputBridge(output_adapter)
        self.orchestrator.output = orchestrator_output

        # Pass session_context to task_router for verbose_mode access
        self.task_router.session_context = self.session_context

        # Create InteractiveMode with existing Textual IO
        interactive_mode = InteractiveMode(
            io=self.io,  # Use existing Textual IO, not creating new one
            orchestrator=self.orchestrator,
            session_context=self.session_context,
            state_manager=self.state_manager,
            input_handler=self.input_handler,
            command_router=self.command_router,
            display=self.display,
            smart=self.smart,
            task_router=self.task_router,
            tasks=self.tasks,
            logger=self.logger
        )

        # Create ScrappyApp with InteractiveMode, output adapter, and user theme
        app = ScrappyApp(interactive_mode, output_adapter, theme=self._config.theme)

        # Pass codebase context for semantic search indexing
        # The orchestrator's context_manager holds the CodebaseContext
        if hasattr(self.orchestrator, 'context_manager'):
            context_manager = self.orchestrator.context_manager
            if hasattr(context_manager, 'context'):
                app.set_codebase_context(context_manager.context)

        # Phase 3: Inject bridge into UnifiedIO for modal dialogs
        # This enables prompt() and confirm() to show modals instead of auto-approving
        self.io.set_bridge(app.bridge)

        # Phase 3.3: Create LangGraphBridge for new agent architecture
        # This bridges LangGraph async execution to Textual worker pattern
        langgraph_bridge = None
        llm_service = getattr(self.orchestrator, 'llm_service', None)
        if self._cli is not None and llm_service is not None:
            from .textual.langgraph_bridge import LangGraphBridge
            from scrappy.graph.tools import ToolAdapter

            # Create tool adapter - owned by app, passed to bridge
            # This ensures proper cleanup and reuse across agent runs
            app._tool_adapter = ToolAdapter.create_default()

            langgraph_bridge = LangGraphBridge(
                app=app,
                bridge=app.bridge,
                output_adapter=output_adapter,
                llm_service=llm_service,
                tool_adapter=app._tool_adapter,
            )
        # Temporary assertion to catch wiring issues
        assert langgraph_bridge is not None, (
            f"LangGraphBridge not created: _cli={self._cli is not None}, "
            f"llm_service={llm_service is not None}"
        )

        # Phase 2: Reinitialize handlers with bridge for TUI-aware user interaction
        # This allows CLIAgentManager to use modal dialogs and LangGraph agent
        if self._cli is not None:
            self._cli.reinitialize_handlers_with_bridge(app.bridge, langgraph_bridge)
            # Update command router's references to the new handlers
            self.command_router.agent_mgr = self._cli.agent_mgr

        # Launch the TUI
        app.run()
