"""Shared startup wiring for Textual runtime integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Callable

if TYPE_CHECKING:
    from scrappy.cli.command_router import CommandRouter
    from scrappy.cli.core import CLI
    from scrappy.cli.display import CLIDisplay
    from scrappy.cli.input_handler import InputHandler
    from scrappy.cli.interactive import InteractiveMode
    from scrappy.cli.logging import CLILogger
    from scrappy.cli.session_context import SessionContextProtocol
    from scrappy.cli.state_manager import PlanStateManager
    from scrappy.cli.tasks import CLITaskExecution
    from scrappy.cli.unified_io import UnifiedIO
    from scrappy.cli.textual.output_adapter import TextualOutputAdapter
    from scrappy.cli.textual.app import ScrappyApp
    from scrappy.orchestrator.protocols import Orchestrator


def create_textual_runtime_session(
    *,
    io: "UnifiedIO",
    orchestrator: "Orchestrator",
    session_context: "SessionContextProtocol",
    state_manager: "PlanStateManager",
    input_handler: "InputHandler",
    command_router: "CommandRouter",
    display: "CLIDisplay",
    tasks: "CLITaskExecution",
    logger: "CLILogger",
    output_adapter: "TextualOutputAdapter",
) -> "InteractiveMode":
    """Create InteractiveMode and route orchestrator output through Textual."""
    from ..interactive import InteractiveMode
    from ..output_bridge import OutputBridge

    orchestrator.output = OutputBridge(output_adapter)
    return InteractiveMode(
        io=io,
        orchestrator=orchestrator,
        session_context=session_context,
        state_manager=state_manager,
        input_handler=input_handler,
        command_router=command_router,
        display=display,
        tasks=tasks,
        logger=logger,
        session_saver=command_router.session_saver,
    )


def wire_textual_runtime(
    *,
    app: "ScrappyApp",
    interactive_mode: "InteractiveMode",
    io: "UnifiedIO",
    orchestrator: "Orchestrator",
    output_adapter: "TextualOutputAdapter",
    cli: Optional["CLI"] = None,
    setup_wizard_callback: Optional[Callable[[], None]] = None,
) -> Optional["Any"]:
    """Wire bridge, tool adapter, and handler state for Textual runtime."""
    # Pass codebase context for semantic search indexing.
    if hasattr(orchestrator, "context_manager"):
        context_manager = orchestrator.context_manager
        if hasattr(context_manager, "context"):
            app.set_codebase_context(context_manager.context)

    # Inject bridge into UnifiedIO for modal dialogs.
    io.set_bridge(app.bridge)

    langgraph_bridge = None
    if hasattr(orchestrator, "stream_completion_with_fallback"):
        from .langgraph_bridge import LangGraphBridge
        from scrappy.graph.tools import ToolAdapter

        # Owned by the app so cleanup happens in one place.
        app._tool_adapter = ToolAdapter.create_default()

        langgraph_bridge = LangGraphBridge(
            app=app,
            bridge=app.bridge,
            output_adapter=output_adapter,
            orchestrator=orchestrator,
            tool_adapter=app._tool_adapter,
        )

    if cli is not None:
        cli.reinitialize_handlers_with_bridge(app.bridge, langgraph_bridge)
        interactive_mode.command_router.agent_mgr = cli.agent_mgr

    if langgraph_bridge is not None:
        interactive_mode.set_langgraph_bridge(langgraph_bridge)

    if setup_wizard_callback is not None:
        interactive_mode.command_router.set_setup_wizard_callback(setup_wizard_callback)

    return langgraph_bridge
