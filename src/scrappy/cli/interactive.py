"""
Interactive mode module for CLI.

Handles input processing for the interactive chat.
"""

import os
from typing import TYPE_CHECKING, Optional

from .io_interface import CLIIOProtocol
from .state_manager import PlanStateManager
from .session_context import SessionContextProtocol
from .input_handler import InputHandler
from .command_router import CommandRouter
from .display import CLIDisplay
from .tasks import CLITaskExecution
from .error_recovery import graceful_degrade
from .logging import CLILogger
from ..orchestrator.protocols import Orchestrator
from scrappy.infrastructure.theme import ThemeProtocol

if TYPE_CHECKING:
    from .textual.langgraph_bridge import LangGraphBridge


class InteractiveMode:
    """Handles the main interactive chat loop."""

    def __init__(
        self,
        io: CLIIOProtocol,
        orchestrator: Orchestrator,
        session_context: SessionContextProtocol,
        state_manager: PlanStateManager,
        input_handler: InputHandler,
        command_router: CommandRouter,
        display: CLIDisplay,
        tasks: CLITaskExecution,
        logger: CLILogger,
        theme: Optional[ThemeProtocol] = None,
    ) -> None:
        """
        Initialize InteractiveMode.

        Args:
            io: The IO interface for input/output.
            orchestrator: The agent orchestrator.
            session_context: Shared session context for state management.
            state_manager: Plan state manager.
            input_handler: Input handler for reading user input.
            command_router: Command router for slash commands.
            display: Display handler for showing information.
            tasks: Task execution handler.
            logger: Logger for structured logging.
            theme: Optional theme for consistent styling.
        """
        from scrappy.infrastructure.theme import DEFAULT_THEME

        self.io = io
        self.orchestrator = orchestrator
        self.session_context = session_context
        self.state_manager = state_manager
        self.input_handler = input_handler
        self.command_router = command_router
        self.display = display
        self.tasks = tasks
        self.logger = logger
        self._theme = theme or DEFAULT_THEME
        # LangGraph bridge for unified chat (set later via set_langgraph_bridge)
        self._langgraph_bridge: Optional["LangGraphBridge"] = None

    def set_langgraph_bridge(self, bridge: "LangGraphBridge") -> None:
        """
        Set the LangGraph bridge for unified chat handling.

        When set, ALL non-command input routes through LangGraph instead of TaskRouter.
        The LLM decides whether to use tools based on the query.

        Args:
            bridge: The LangGraphBridge instance
        """
        self._langgraph_bridge = bridge

    def _process_via_langgraph(self, user_input: str) -> str:
        """
        Process input through LangGraph for unified chat.

        Routes ALL input through the LangGraph agent. The LLM decides whether
        to use tools based on the query:
        - Simple conversation: responds directly (no tools)
        - Code tasks: uses file tools
        - Research: uses search/read tools

        Args:
            user_input: The user's input string

        Returns:
            Response content string
        """
        import logging
        logger = logging.getLogger(__name__)

        bridge = self._langgraph_bridge
        if bridge is None:
            logger.warning("LangGraph bridge missing while processing chat input")
            return "Error: Agent not initialized"

        try:
            # Run through LangGraph - bridge handles streaming output
            # Chat mode uses "chat" tier (70B models)
            # Agent mode (/agent command) uses "instruct" tier
            logger.info("Chat mode: calling run_agent with tier=chat")
            result = bridge.run_agent(
                task=user_input,
                working_dir=os.getcwd(),
                tier="chat",
            )

            # Extract response from final state
            if result.cancelled:
                return "(cancelled by user)"
            elif result.success and result.final_state:
                # Get last assistant message content
                messages = result.final_state.messages
                for msg in reversed(messages):
                    if msg.get("role") == "assistant":
                        # Use `or ""` because .get() returns None if key exists with None value
                        content = msg.get("content") or ""
                        if content:
                            return content
                return "(no response)"
            else:
                error_text = f"Error: {result.error or 'unknown error'}"
                if result.suggestion:
                    error_text += f"\nSuggestion: {result.suggestion}"
                return error_text

        except Exception as e:
            logger.exception("LangGraph processing failed: %s", e)
            return f"Error: {e}"

    def _process_input(self, user_input: str) -> bool:
        """
        Process user input.

        Handles both slash commands and regular chat input. For commands,
        delegates to command_router. For chat, routes through LangGraph
        where the LLM decides tool usage.

        Args:
            user_input: The user's input string.

        Returns:
            bool: True to continue the loop, False to exit.

        Side Effects:
            - Commands are routed to command_router.route()
            - Chat input is processed through LangGraph bridge
            - LLM decides whether to use tools based on query
            - Prompts for task progression if plan is active

        State Changes:
            - Appends user message to conversation_history
            - Appends assistant response to conversation_history
            - Command routing may change various state attributes
        """
        io = self.io

        if not user_input:
            return True

        # Handle commands
        if self.input_handler.is_command(user_input):
            import logging
            logger = logging.getLogger(__name__)
            cmd, args = self.input_handler.parse_command(user_input)
            logger.debug(f"[_process_input] Routing command: {cmd}, args: {args}")
            result = self.command_router.route(cmd, args)
            logger.debug(f"[_process_input] Command result: {result}")
            return result

        # Regular chat
        self.session_context.conversation_history.append({
            "role": "user",
            "content": user_input
        })

        # Persist user message
        self.session_context.add_message({
            "role": "user",
            "content": user_input
        })

        # Echo user query
        io.secho(f"> {user_input}", fg=self._theme.text)

        # Route through LangGraph (required)
        if self._langgraph_bridge is None:
            io.secho("Error: LangGraph bridge not initialized", fg=io.theme.error)
            response_content = "Error: Agent not initialized"
        else:
            response_content = self._process_via_langgraph(user_input)
            # Chat mode streams response via callback - don't echo again
            # Only echo for errors/cancellations (which start with "(" or "Error:")
            if response_content and response_content.startswith(("(", "Error:")):
                io.echo()
                io.echo(response_content)

        io.echo()

        self.session_context.conversation_history.append({
            "role": "assistant",
            "content": response_content
        })

        # Persist assistant message
        self.session_context.add_message({
            "role": "assistant",
            "content": response_content
        })

        # Prompt for task progression if plan is active
        if self.state_manager.plan_active:
            self.state_manager.prompt_task_progression(io)

        return True

    def _handle_eof(self) -> None:
        """
        Handle EOF (end of input).

        Performs cleanup operations when EOF is received, including auto-saving
        the session if enabled and displaying usage statistics.

        Side Effects:
            - Displays EOF message to console
            - Logs EOF event
            - Auto-saves session via orchestrator.save_session() if enabled
            - Displays session save status
            - Shows usage statistics via display.show_usage()
            - Displays goodbye message

        State Changes:
            - Creates session file if auto_save is enabled

        Returns:
            None
        """
        io = self.io

        io.echo("\n")
        io.secho("EOF received. Exiting...", fg=self._theme.warning)
        self.logger.info("EOF received, exiting interactive mode")

        # Auto-save session on exit if enabled
        if self.session_context.auto_save:
            def save_session():
                return self.orchestrator.save_session(self.session_context.conversation_history)

            result = graceful_degrade(
                save_session,
                on_error=lambda e: None,
                io=io,
                degraded_message="Could not save session: will continue without saving"
            )

            if result:
                io.secho(f"Session saved to: {result}", fg=self._theme.success)
                self.logger.info("Session saved", extra={"session_file": str(result)})
            else:
                self.logger.warning("Session save failed during exit")

        self.display.show_usage()
        io.secho("Goodbye!", fg=self._theme.primary, bold=True)
