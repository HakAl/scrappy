"""
Textual-based interactive mode for Scrappy CLI.

Provides a clean TUI interface using Textual framework.
"""

from typing import TYPE_CHECKING

from .textual.app import ScrappyApp
from .unified_io import UnifiedIO
from .output_bridge import OutputBridge
from .config_factory import get_config
from .textual.runtime_wiring import create_textual_runtime_session, wire_textual_runtime
from ..orchestrator.protocols import Orchestrator

# Re-export for backward compatibility
OrchestratorOutputAdapter = OutputBridge

if TYPE_CHECKING:
    from .state_manager import PlanStateManager
    from .session_context import SessionContextProtocol
    from .input_handler import InputHandler
    from .command_router import CommandRouter
    from .display import CLIDisplay
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

        interactive_mode = create_textual_runtime_session(
            io=self.io,
            orchestrator=self.orchestrator,
            session_context=self.session_context,
            state_manager=self.state_manager,
            input_handler=self.input_handler,
            command_router=self.command_router,
            display=self.display,
            tasks=self.tasks,
            logger=self.logger,
            output_adapter=output_adapter,
        )

        # Create ScrappyApp with InteractiveMode, output adapter, and user theme
        app = ScrappyApp(interactive_mode, output_adapter, theme=self._config.theme)

        wire_textual_runtime(
            app=app,
            interactive_mode=interactive_mode,
            io=self.io,
            orchestrator=self.orchestrator,
            output_adapter=output_adapter,
            cli=self._cli,
            setup_wizard_callback=app.launch_setup_wizard,
        )

        # Launch the TUI
        app.run()
