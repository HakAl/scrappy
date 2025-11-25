"""
Textual-based interactive mode for Scrappy CLI.

Provides a clean TUI interface using Textual framework.
"""

from typing import TYPE_CHECKING

from .textual_app import ScrappyApp, TextualOutputAdapter
from .unified_io import UnifiedIO
from .interactive import InteractiveMode
from .protocols import OutputSink

if TYPE_CHECKING:
    from ..orchestrator.protocols import Orchestrator
    from .state_manager import PlanStateManager
    from .session_context import SessionContextProtocol
    from .input_handler import InputHandler
    from .command_router import CommandRouter
    from .display import CLIDisplay
    from .smart_query import CLISmartQuery
    from .task_router_handler import CLITaskRouterHandler
    from .tasks import CLITaskExecution
    from .logging import CLILogger


class OrchestratorOutputAdapter:
    """Adapter that bridges orchestrator OperationalOutputProtocol to Textual OutputSink.

    This fixes the "split-brain" issue by routing ALL orchestrator output
    (including from delegate(), registration messages, etc.) through the
    Textual message queue.

    Implements the OperationalOutputProtocol interface (info, warn, error, success).
    """

    def __init__(self, output_sink: OutputSink):
        """Initialize with OutputSink (TextualOutputAdapter).

        Args:
            output_sink: OutputSink protocol implementation (TextualOutputAdapter)
        """
        self.output_sink = output_sink

    def info(self, message: str) -> None:
        """Output informational message."""
        self.output_sink.post_output(message + "\n")

    def warn(self, message: str) -> None:
        """Output warning message."""
        from rich.text import Text
        warning_text = Text(message, style="yellow")
        self.output_sink.post_renderable(warning_text)

    def error(self, message: str) -> None:
        """Output error message."""
        from rich.text import Text
        error_text = Text(message, style="red bold")
        self.output_sink.post_renderable(error_text)

    def success(self, message: str) -> None:
        """Output success message."""
        from rich.text import Text
        success_text = Text(message, style="green")
        self.output_sink.post_renderable(success_text)


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
        orchestrator: "Orchestrator",
        session_context: "SessionContextProtocol",
        state_manager: "PlanStateManager",
        input_handler: "InputHandler",
        command_router: "CommandRouter",
        display: "CLIDisplay",
        smart: "CLISmartQuery",
        task_router: "CLITaskRouterHandler",
        tasks: "CLITaskExecution",
        logger: "CLILogger",
        io: UnifiedIO
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

        # Inject orchestrator output adapter
        # This routes ALL orchestrator output (delegate(), registration, etc.)
        # through the Textual message queue
        orchestrator_output = OrchestratorOutputAdapter(output_adapter)
        self.orchestrator.output = orchestrator_output

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

        # Create ScrappyApp with InteractiveMode and output adapter
        app = ScrappyApp(interactive_mode, output_adapter)

        # Launch the TUI
        app.run()
