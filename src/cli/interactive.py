"""
Interactive mode module for CLI.

Handles the main interactive chat loop.
"""

import sys
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional

from .io_interface import CLIIOProtocol
from .state_manager import PlanStateManager
from .session_context import SessionContextProtocol
from .input_handler import InputHandler
from .command_router import CommandRouter
from .tool_detector import needs_tool_support
from .display import CLIDisplay
from .smart_query import CLISmartQuery
from .task_router_handler import CLITaskRouterHandler
from .tasks import CLITaskExecution
from .utils.session_utils import display_session_save_error
from .interactive_banner import render_welcome_banner
from .rich_output import RichIO

from .exceptions import (
    CLIError,
    ProviderError,
    UserInputError,
    SessionError,
)
from .error_recovery import error_recovery_context, graceful_degrade
from .logging import get_logger, CLILogger

if TYPE_CHECKING:
    from ..orchestrator.protocols import Orchestrator


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
        logger: CLILogger
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
        """
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

    def run(self) -> None:
        """
        Run the interactive chat loop.

        Displays the welcome banner and mode statuses, then enters the main
        input loop. Requires a TTY (terminal) environment to operate.

        Side Effects:
            - Checks if running in TTY mode, exits with error if not
            - Displays welcome banner with available commands
            - Shows multiline and auto-routing mode statuses
            - Enters _main_loop which processes user input until exit

        State Changes:
            - No direct state changes; delegates to _main_loop

        Returns:
            None
        """
        io = self.io

        # Check if running in interactive environment
        if not sys.stdin.isatty():
            io.secho("Error: Interactive mode requires a TTY (terminal).", fg="red", bold=True)
            io.echo("Cannot run interactive mode without stdin.")
            io.echo("Use one-shot commands instead (e.g., scrappy query 'your question')")
            return

        # Show welcome banner with Rich Panel
        # Use RichIO if available, otherwise fall back to basic io
        if isinstance(io, RichIO):
            render_welcome_banner(io, self.session_context.multiline_mode, self.session_context.auto_route_mode)
        else:
            # Fallback for non-Rich IO (e.g., testing)
            io.secho("=" * 60, fg="cyan")
            io.secho("Scrappy - Interactive Mode", fg="cyan", bold=True)
            io.secho("=" * 60, fg="cyan")
            io.echo("Commands:")
            io.echo(f"  {io.style('/help', fg='yellow')}          - Show all commands")
            io.echo(f"  {io.style('/auto', fg='yellow')}          - Toggle auto-routing")
            io.echo(f"  {io.style('/plan', fg='yellow')} <task>   - Create a task plan")
            io.echo(f"  {io.style('/agent', fg='yellow')} <task>  - Run code agent")
            io.echo(f"  {io.style('/smart', fg='yellow')} <q>     - Research-first query")
            io.echo(f"  {io.style('/status', fg='yellow')}        - Show system status")
            io.echo(f"  {io.style('/quit', fg='yellow')}          - Exit the CLI")
            io.secho("=" * 60, fg="cyan")

            if self.session_context.multiline_mode:
                io.secho("Multiline input: ON", fg="green")
            else:
                io.secho("Multiline input: OFF", fg="yellow")

            if self.session_context.auto_route_mode:
                io.secho("Auto-routing: ON", fg="green")
            else:
                io.secho("Auto-routing: OFF", fg="yellow")
            io.echo()

        # Run main loop
        self._main_loop()

    def _main_loop(self) -> None:
        """
        Run the main input loop.

        Continuously reads user input and processes it until exit is requested.
        Handles keyboard interrupts and EOF gracefully.

        Side Effects:
            - Reads input via input_handler.read_interactive_input()
            - Processes each input through _process_input()
            - Displays interrupt messages on KeyboardInterrupt
            - Logs user interrupts and errors

        State Changes:
            - Delegates state changes to _process_input()
            - Loop exits when _process_input returns False or EOF received

        Raises:
            Does not raise; all exceptions are handled internally.

        Returns:
            None
        """
        while True:
            try:
                # Read input
                user_input = self.input_handler.read_interactive_input(
                    multiline_mode=self.session_context.multiline_mode
                )

                # Process input
                if not self._process_input(user_input):
                    break

            except KeyboardInterrupt:
                self.io.echo("\n\nInterrupted. Type /quit to exit.")
                self.logger.info("User interrupted input", extra={"action": "keyboard_interrupt"})
                continue
            except EOFError:
                self._handle_eof()
                break
            except UserInputError as e:
                if e.interrupted:
                    self.io.echo("\n\nInterrupted. Type /quit to exit.")
                elif e.eof:
                    self._handle_eof()
                    break
                else:
                    self._handle_error(e)
            except CLIError as e:
                self._handle_error(e)
            except Exception as e:
                self._handle_error(e)

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
            cmd, args = self.input_handler.parse_command(user_input)
            return self.command_router.route(cmd, args)

        # Regular chat
        self.session_context.conversation_history.append({
            "role": "user",
            "content": user_input
        })

        # Use auto-routing if enabled
        if self.session_context.auto_route_mode:
            result = self.task_router.handle_auto_route(user_input)
            response_content = result.output if result.success else f"Error: {result.error}"
            response = type('Response', (), {'content': response_content})()
        # Use smart mode if enabled
        elif self.session_context.smart_mode:
            response = self.smart.smart_query(user_input)
        else:
            # Check if this looks like a research task that needs tools
            needs_tools = needs_tool_support(user_input)

            if needs_tools:
                # Use task router with tool support
                io.secho("Using tools for research...", fg="cyan")
                result = self.task_router.handle_auto_route(user_input)
                response_content = result.output if result.success else f"Error: {result.error}"
                response = type('Response', (), {'content': response_content})()

                # Show tool usage info if available
                if hasattr(result, 'metadata') and result.metadata:
                    tool_calls = result.metadata.get('tool_calls', [])
                    if tool_calls:
                        io.secho(f"  Tools used: {[tc['tool'] for tc in tool_calls]}", fg="cyan")

                io.secho("Assistant: ", fg="blue", bold=True)
                io.echo(response.content)

                # Show execution metadata
                provider_used = getattr(result, 'provider_used', None) or "unknown"
                tokens = getattr(result, 'tokens_used', None) or 0
                exec_time = getattr(result, 'execution_time', None) or 0
                # Ensure numeric values for formatting
                try:
                    tokens = int(tokens)
                    exec_time_ms = float(exec_time) * 1000
                except (TypeError, ValueError):
                    tokens = 0
                    exec_time_ms = 0
                io.secho(
                    f"[{provider_used} | {tokens} tokens | {exec_time_ms:.0f}ms]",
                    fg="cyan"
                )
            else:
                io.secho("Assistant: ", fg="blue", bold=True, nl=False)

                response = self.orchestrator.delegate(
                    self.orchestrator.brain,
                    user_input,
                    system_prompt="You are a helpful AI assistant. Be concise and informative."
                )

                io.echo(response.content)
                io.secho(
                    f"[{response.provider}/{response.model} | {response.tokens_used} tokens | {response.latency_ms:.0f}ms]",
                    fg="cyan"
                )
        io.echo()

        self.session_context.conversation_history.append({
            "role": "assistant",
            "content": response.content
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
        io.secho("EOF received. Exiting...", fg="yellow")
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
                io.secho(f"Session saved to: {result}", fg="green")
                self.logger.info("Session saved", extra={"session_file": str(result)})
            else:
                self.logger.warning("Session save failed during exit")

        self.display.show_usage()
        io.secho("Goodbye!", fg="cyan", bold=True)

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
                io.secho(f"\nError: {exception}", fg="red", bold=True)
            else:
                io.secho(f"\nError: {exception}", fg="red")

            # Show suggestion if available
            if exception.suggestion:
                io.echo(f"Suggestion: {exception.suggestion}")

            # Log with structured data
            self.logger.error(
                str(exception),
                extra=exception.logging_extra()
            )
        elif isinstance(exception, ProviderError):
            io.secho(f"\nProvider error: {exception}", fg="red")
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
            io.secho(f"\nError: {exception}", fg="red")
            self.logger.exception("Unhandled exception in interactive mode")

        io.echo("Type /help for available commands.\n")
