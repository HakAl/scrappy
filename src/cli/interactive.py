"""
Interactive mode module for CLI.

Handles the main interactive chat loop.
"""

import sys
from datetime import datetime
from typing import Any, List, Optional

from .io_interface import CLIIOProtocol
from .state_manager import PlanStateManager
from .input_handler import InputHandler
from .command_router import CommandRouter
from .tool_detector import needs_tool_support
from .display import CLIDisplay
from .smart_query import CLISmartQuery
from .task_router_handler import CLITaskRouterHandler
from .tasks import CLITaskExecution


class InteractiveMode:
    """Handles the main interactive chat loop."""

    def __init__(
        self,
        io: CLIIOProtocol,
        orchestrator: Any,
        state_manager: Optional[PlanStateManager] = None
    ):
        """
        Initialize InteractiveMode.

        Args:
            io: The IO interface for input/output.
            orchestrator: The agent orchestrator.
            state_manager: Optional plan state manager.
        """
        self.io = io
        self.orchestrator = orchestrator

        # Initialize state manager
        self.state_manager = state_manager or PlanStateManager()

        # Initialize component handlers
        self.input_handler = InputHandler(io)
        self.command_router = CommandRouter(io, orchestrator, state_manager=self.state_manager)

        # State attributes (sync from command_router for convenience)
        self.conversation_history: List[dict] = self.command_router.conversation_history
        self.multiline_mode: bool = self.command_router.multiline_mode
        self.auto_route_mode: bool = self.command_router.auto_route_mode
        self.smart_mode: bool = self.command_router.smart_mode
        self.auto_save: bool = self.command_router.auto_save

        # Component handlers
        self.session_start = datetime.now()
        self.display = CLIDisplay(orchestrator, self.session_start)
        self.smart = CLISmartQuery(orchestrator)
        self.task_router = CLITaskRouterHandler(orchestrator)
        self.tasks = CLITaskExecution(orchestrator)

    def run(self) -> None:
        """Run the interactive chat loop."""
        io = self.io

        # Check if running in interactive environment
        if not sys.stdin.isatty():
            io.secho("Error: Interactive mode requires a TTY (terminal).", fg="red", bold=True)
            io.echo("Cannot run interactive mode without stdin.")
            io.echo("Use one-shot commands instead (e.g., llm-team query 'your question')")
            return

        # Show welcome banner
        io.secho("=" * 60, fg="cyan")
        io.secho("LLM Agent Team - Interactive Mode", fg="cyan", bold=True)
        io.secho("=" * 60, fg="cyan")
        io.echo("Commands:")
        io.echo(f"  {io.style('/help', fg='yellow')}          - Show all commands")
        io.echo(f"  {io.style('/auto', fg='yellow')}          - Toggle auto-routing (task-aware execution)")
        io.echo(f"  {io.style('/plan', fg='yellow')} <task>   - Create a task plan")
        io.echo(f"  {io.style('/reason', fg='yellow')} <q>    - Reason about a question")
        io.echo(f"  {io.style('/agent', fg='yellow')} <task>  - Run code agent (with human approval)")
        io.echo(f"  {io.style('/smart', fg='yellow')} <q>     - Research-first query (uses tools)")
        io.echo(f"  {io.style('/context', fg='yellow')}       - Manage codebase context")
        io.echo(f"  {io.style('/autoexec', fg='yellow')}      - Toggle auto-execute for plan tasks")
        io.echo(f"  {io.style('/status', fg='yellow')}        - Show system status")
        io.echo(f"  {io.style('/quit', fg='yellow')}          - Exit the CLI")
        io.echo(f"  {io.style('(any text)', fg='bright_white')}     - Chat with current brain")
        io.secho("=" * 60, fg="cyan")

        # Show mode statuses
        if self.multiline_mode:
            io.secho("Multiline input: ON (end line with \\ to continue, /ml to toggle)", fg="green")
        else:
            io.secho("Multiline input: OFF (/ml to toggle)", fg="yellow")

        if self.auto_route_mode:
            io.secho("Auto-routing: ON (task-aware execution)", fg="green")
        else:
            io.secho("Auto-routing: OFF (/auto to enable)", fg="yellow")
        io.echo()

        # Run main loop
        self._main_loop()

    def _main_loop(self) -> None:
        """Run the main input loop."""
        while True:
            try:
                # Read input
                user_input = self.input_handler.read_interactive_input(
                    multiline_mode=self.multiline_mode
                )

                # Process input
                if not self._process_input(user_input):
                    break

            except KeyboardInterrupt:
                self.io.echo("\n\nInterrupted. Type /quit to exit.")
                continue
            except EOFError:
                self._handle_eof()
                break
            except Exception as e:
                self._handle_error(e)

    def _process_input(self, user_input: str) -> bool:
        """
        Process user input.

        Args:
            user_input: The user's input string.

        Returns:
            True to continue loop, False to exit.
        """
        io = self.io

        if not user_input:
            return True

        # Handle commands
        if self.input_handler.is_command(user_input):
            cmd, args = self.input_handler.parse_command(user_input)
            return self.command_router.route(cmd, args)

        # Regular chat
        self.conversation_history.append({
            "role": "user",
            "content": user_input
        })

        # Use auto-routing if enabled
        if self.auto_route_mode:
            result = self.task_router.handle_auto_route(user_input)
            response_content = result.output if result.success else f"Error: {result.error}"
            response = type('Response', (), {'content': response_content})()
        # Use smart mode if enabled
        elif self.smart_mode:
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

        self.conversation_history.append({
            "role": "assistant",
            "content": response.content
        })

        # Prompt for task progression if plan is active
        if self.state_manager.plan_active:
            self.state_manager.prompt_task_progression(io)

        return True

    def _handle_eof(self) -> None:
        """Handle EOF (end of input)."""
        io = self.io

        io.echo("\n")
        io.secho("EOF received. Exiting...", fg="yellow")

        # Auto-save session on exit if enabled
        if self.auto_save:
            try:
                session_file = self.orchestrator.save_session(self.conversation_history)
                io.secho(f"Session saved to: {session_file}", fg="green")
            except Exception as save_error:
                io.secho(f"Warning: Could not save session: {save_error}", fg="yellow")

        self.display.show_usage()
        io.secho("Goodbye!", fg="cyan", bold=True)

    def _handle_error(self, exception: Exception) -> None:
        """
        Handle general exceptions.

        Args:
            exception: The exception that occurred.
        """
        self.io.secho(f"\nError: {exception}", fg="red")
        self.io.echo("Type /help for available commands.\n")
