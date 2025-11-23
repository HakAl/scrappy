"""
Textual-based interactive mode for Scrappy CLI.

Wraps the existing InteractiveMode with a Textual TUI display.
"""

from typing import TYPE_CHECKING

from .textual_app import ScrappyApp
from .textual_io import TextualIO
from .interactive import InteractiveMode
from .io_interface import CLIIOProtocol
from .state_manager import PlanStateManager
from .session_context import SessionContextProtocol
from .input_handler import InputHandler
from .command_router import CommandRouter
from .display import CLIDisplay
from .smart_query import CLISmartQuery
from .task_router_handler import CLITaskRouterHandler
from .tasks import CLITaskExecution
from .logging import CLILogger

if TYPE_CHECKING:
    from ..orchestrator.protocols import Orchestrator


class TextualInteractiveMode:
    """Interactive mode using Textual TUI.

    Wraps the existing working InteractiveMode with Textual UI.
    """

    def __init__(
        self,
        io: CLIIOProtocol,
        orchestrator: "Orchestrator",
        session_context: SessionContextProtocol,
        state_manager: PlanStateManager,
        input_handler: InputHandler,
        command_router: CommandRouter,
        display: CLIDisplay,
        smart: CLISmartQuery,
        task_router: CLITaskRouterHandler,
        tasks: CLITaskExecution,
        logger: CLILogger
    ) -> None:
        """Initialize TextualInteractiveMode."""
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

    def run(self) -> None:
        """Launch the Textual TUI application."""
        # Create the app (needed for TextualIO)
        app = ScrappyApp.__new__(ScrappyApp)

        # Create TextualIO
        textual_io = TextualIO(app)

        # Create InteractiveMode with TextualIO (your working code!)
        interactive_mode = InteractiveMode(
            io=textual_io,
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

        # Initialize app with InteractiveMode
        app.__init__(interactive_mode)
        app.run()
