"""
Interactive mode module for CLI.

Handles input processing for the interactive chat.
"""

from typing import TYPE_CHECKING, Optional

from .io_interface import CLIIOProtocol
from .state_manager import PlanStateManager
from .session_context import SessionContextProtocol
from .input_handler import InputHandler
from .command_router import CommandRouter
from .display import CLIDisplay
from .smart_query import CLISmartQuery
from .task_router_handler import CLITaskRouterHandler
from .tasks import CLITaskExecution
from .exceptions import CLIError, ProviderError
from .error_recovery import graceful_degrade
from .logging import CLILogger

if TYPE_CHECKING:
    from ..orchestrator.protocols import Orchestrator
    from src.infrastructure.theme import ThemeProtocol


class InteractiveMode:
    """Handles the main interactive chat loop."""

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
        logger: CLILogger,
        theme: Optional["ThemeProtocol"] = None,
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
            smart: Smart query handler for tool-assisted queries.
            task_router: Task router handler for auto-routing.
            tasks: Task execution handler.
            logger: Logger for structured logging.
            theme: Optional theme for consistent styling.
        """
        from src.infrastructure.theme import DEFAULT_THEME

        self.io = io
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
        self._theme = theme or DEFAULT_THEME

    def _process_input(self, user_input: str) -> bool:
        """
        Process user input.

        Handles both slash commands and regular chat input. For commands,
        delegates to command_router. For chat, uses auto-routing, smart mode,
        or direct LLM delegation based on current settings.

        Args:
            user_input: The user's input string.

        Returns:
            bool: True to continue the loop, False to exit.

        Side Effects:
            - Commands are routed to command_router.route()
            - Chat input is:
              - Routed through task_router if auto_route_mode is enabled
              - Processed by smart_query if smart_mode is enabled
              - Sent to orchestrator.delegate() otherwise
            - Displays response to console with metadata
            - May use tools for research if query requires it
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

        # Echo user query
        io.secho(f"> {user_input}", fg=self._theme.text)

        # Always use auto-routing (task router handles classification and execution)
        result = self.task_router.handle_auto_route(user_input)
        response_content = result.output if result.success else f"Error: {result.error}"

        # Display response
        io.echo()
        io.echo(f"| {response_content}")

        # Verbose mode: show metadata
        if self.session_context.verbose_mode:
            classification = result.metadata.get('classification', {})
            provider = classification.get('resolved_provider') or result.provider_used or 'local'
            model = classification.get('resolved_model', '')
            tokens = result.tokens_used
            time_ms = result.execution_time * 1000
            if model:
                provider_str = provider + " (" + model + ")"
            else:
                provider_str = provider
            time_str = f"{time_ms:.1f}"
            io.echo(f"  {provider_str} | {tokens} tokens | {time_str}ms")

        io.echo()

        self.session_context.conversation_history.append({
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
                degraded_message=f"Could not save session: will continue without saving"
            )

            if result:
                io.secho(f"Session saved to: {result}", fg=self._theme.success)
                self.logger.info("Session saved", extra={"session_file": str(result)})
            else:
                self.logger.warning("Session save failed during exit")

        self.display.show_usage()
        io.secho("Goodbye!", fg=self._theme.primary, bold=True)

    def _handle_error(self, exception: Exception) -> None:
        """
        Handle general exceptions.

        Displays error messages with appropriate styling based on severity
        and exception type. Logs errors with structured data.

        Args:
            exception: The exception that occurred.

        Side Effects:
            - Displays error message to console with severity-based styling
            - Shows suggestion if available in exception
            - Logs error with structured data (CLIError) or full traceback
            - Displays help reminder

        State Changes:
            - None; purely handles display and logging

        Returns:
            None
        """
        io = self.io

        if isinstance(exception, CLIError):
            # Use severity-appropriate styling
            if exception.severity.value >= 4:  # CRITICAL
                io.secho(f"\nError: {exception}", fg=self._theme.error, bold=True)
            else:
                io.secho(f"\nError: {exception}", fg=self._theme.error)

            # Show suggestion if available
            if exception.suggestion:
                io.echo(f"Suggestion: {exception.suggestion}")

            # Log with structured data
            self.logger.error(
                str(exception),
                extra=exception.logging_extra()
            )
        elif isinstance(exception, ProviderError):
            io.secho(f"\nProvider error: {exception}", fg=self._theme.error)
            if exception.suggestion:
                io.echo(f"Suggestion: {exception.suggestion}")
            self.logger.error(
                str(exception),
                extra={
                    "provider": exception.provider,
                    "rate_limited": exception.rate_limited,
                    "is_timeout": exception.is_timeout,
                }
            )
        else:
            io.secho(f"\nError: {exception}", fg=self._theme.error)
            self.logger.exception("Unhandled exception in interactive mode")

        io.echo("Type /help for available commands.\n")
