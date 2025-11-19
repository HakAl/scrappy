"""
Core CLI functionality.
Main entry point and command routing for the Scrappy CLI.
"""

import sys
from datetime import datetime
from typing import Optional

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
        io: Optional[CLIIOProtocol] = None
    ):
        """
        Initialize CLI with orchestrator and component handlers.

        Creates an AgentOrchestrator instance and initializes all CLI component
        handlers (display, session, codebase, tasks, etc.) using the factory.

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
            io: IO interface for input/output operations. Defaults to ClickIO.

        Side Effects:
            - Prints initialization messages to stdout via io interface
            - Creates and stores AgentOrchestrator instance
            - Initializes logger for structured logging
            - May prompt user to restore previous session if one exists
            - Displays brain/provider status to console

        State Changes:
            - Sets self.orchestrator to new AgentOrchestrator
            - Sets self.session_start to current datetime
            - Sets self.state_manager to new PlanStateManager
            - Initializes all component handlers (display, session_mgr, etc.)
            - Sets self.input_handler and self.logger

        Raises:
            No explicit exceptions, but underlying orchestrator/provider
            initialization may raise if no providers are available.
        """
        if io is None:
            io = RichIO()
        self.io = io

        io.secho("Initializing Scrappy...", fg="cyan")

        # Show verbose selection info if requested
        if verbose_selection:
            io.secho("Verbose provider selection enabled", fg="yellow")

        self.orchestrator = AgentOrchestrator(
            orchestrator_provider=brain,
            auto_explore=auto_explore,
            context_aware=context_aware,
            verbose_selection=verbose_selection,
            show_provider_status=show_provider_status
        )
        self.session_start = datetime.now()

        # Initialize state manager for plan tracking
        self.state_manager = PlanStateManager()

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
        self.input_handler = InputHandler(io)

        # Logger for structured logging
        self.logger = get_logger("cli.core", io=io)
        self.logger.info("CLI initialized", extra={
            "brain": self.orchestrator.brain,
            "auto_explore": auto_explore,
            "context_aware": context_aware,
        })

        # Display initialization info (unless show_provider_status already did)
        if not show_provider_status:
            brain_name = self.orchestrator.brain
            if brain_name:
                io.echo(f"Brain: {io.style(brain_name, fg='green', bold=True)}")
            else:
                io.secho("Brain: None (no providers available)", fg='yellow')
            providers_list = ', '.join(self.orchestrator.providers.list_available())
            if providers_list:
                io.echo(f"Available providers: {io.style(providers_list, fg='cyan')}")
            else:
                io.secho("No providers available - check API keys", fg='yellow')

        # Show context status
        if self.orchestrator.context.is_explored():
            io.secho(f"Context: {self.orchestrator.context.project_path.name} (cached)", fg="cyan")
        elif context_aware:
            io.secho("Context: Not explored (use /context to explore)", fg="yellow")

        # Auto-detect and offer to load previous session
        self._check_and_offer_session_restore(io=io)

        io.echo()

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
        # Create InteractiveMode with shared state manager
        interactive = InteractiveMode(
            io=self.io,
            orchestrator=self.orchestrator,
            state_manager=self.state_manager
        )

        # Run the interactive loop
        interactive.run()

    # Proxy properties for backward compatibility
    @property
    def active_plan(self):
        """Get active plan from state manager."""
        return self.state_manager.active_plan

    @active_plan.setter
    def active_plan(self, value):
        """Set active plan in state manager."""
        self.state_manager.active_plan = value

    @property
    def current_task_index(self):
        """Get current task index from state manager."""
        return self.state_manager.current_task_index

    @current_task_index.setter
    def current_task_index(self, value):
        """Set current task index in state manager."""
        self.state_manager.current_task_index = value

    @property
    def plan_active(self):
        """Get plan active state from state manager."""
        return self.state_manager.plan_active

    @plan_active.setter
    def plan_active(self, value):
        """Set plan active state in state manager."""
        self.state_manager.plan_active = value

    @property
    def auto_execute_tasks(self):
        """Get auto execute tasks setting from state manager."""
        return self.state_manager.auto_execute_tasks

    @auto_execute_tasks.setter
    def auto_execute_tasks(self, value):
        """Set auto execute tasks setting in state manager."""
        self.state_manager.auto_execute_tasks = value

    @property
    def multiline_mode(self):
        """Get multiline mode (default True)."""
        return getattr(self, '_multiline_mode', True)

    @multiline_mode.setter
    def multiline_mode(self, value):
        """Set multiline mode."""
        self._multiline_mode = value

    @property
    def auto_route_mode(self):
        """Get auto route mode (default True)."""
        return getattr(self, '_auto_route_mode', True)

    @auto_route_mode.setter
    def auto_route_mode(self, value):
        """Set auto route mode."""
        self._auto_route_mode = value

    @property
    def smart_mode(self):
        """Get smart mode (default False)."""
        return getattr(self, '_smart_mode', False)

    @smart_mode.setter
    def smart_mode(self, value):
        """Set smart mode."""
        self._smart_mode = value

    @property
    def conversation_history(self):
        """Get conversation history."""
        return getattr(self, '_conversation_history', [])

    @conversation_history.setter
    def conversation_history(self, value):
        """Set conversation history."""
        self._conversation_history = value

    @property
    def auto_save(self):
        """Get auto save setting (default True)."""
        return getattr(self, '_auto_save', True)

    @auto_save.setter
    def auto_save(self, value):
        """Set auto save setting."""
        self._auto_save = value

    # Proxy methods for backward compatibility
    def _read_multiline_input(self, prompt_text: str = "... ", io: Optional[CLIIOProtocol] = None) -> str:
        """Read multiline input (delegates to InputHandler)."""
        if io is not None:
            handler = InputHandler(io)
            return handler.read_multiline_input(prompt_text)
        return self.input_handler.read_multiline_input(prompt_text)

    def _needs_tool_support(self, user_input: str) -> bool:
        """Detect if query needs tool support (delegates to tool_detector)."""
        return needs_tool_support(user_input)

    def _show_current_task(self, io: Optional[CLIIOProtocol] = None):
        """Display current task (delegates to PlanStateManager)."""
        if io is None:
            io = self.io
        self.state_manager.show_current_task(io)

    def _show_plan_summary(self, io: Optional[CLIIOProtocol] = None):
        """Show plan summary (delegates to PlanStateManager)."""
        if io is None:
            io = self.io
        self.state_manager.show_plan_summary(io)

    def _prompt_task_progression(self, io: Optional[CLIIOProtocol] = None) -> bool:
        """Prompt for task progression (delegates to PlanStateManager)."""
        if io is None:
            io = self.io
        return self.state_manager.prompt_task_progression(io)

    def _handle_command(self, command: str, io: Optional[CLIIOProtocol] = None) -> bool:
        """
        Handle slash commands by delegating to CommandRouter.

        Parses the command string and routes it to the appropriate handler
        via a CommandRouter instance. State is synchronized back after routing.

        Args:
            command: Full command string including the slash prefix and any args.
            io: IO interface for input/output. Defaults to self.io.

        Returns:
            bool: True to continue the interactive loop, False to exit.

        Side Effects:
            - Creates a new CommandRouter instance for each command
            - Executes the command which may modify files, make API calls, etc.
            - Output is displayed to console via io interface

        State Changes:
            - Syncs back conversation_history from router
            - Syncs back multiline_mode from router
            - Syncs back auto_route_mode from router
            - Syncs back smart_mode from router
            - Syncs back auto_save from router
        """
        if io is None:
            io = self.io

        # Create a command router with current state
        router = CommandRouter(io, self.orchestrator, state_manager=self.state_manager)
        router.conversation_history = self.conversation_history
        router.multiline_mode = self.multiline_mode
        router.auto_route_mode = self.auto_route_mode
        router.smart_mode = self.smart_mode
        router.auto_save = self.auto_save

        # Use CLI's display instance for consistency
        router.display = self.display

        # Parse and route the command
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        result = router.route(cmd, args)

        # Sync state back
        self.conversation_history = router.conversation_history
        self.multiline_mode = router.multiline_mode
        self.auto_route_mode = router.auto_route_mode
        self.smart_mode = router.smart_mode
        self.auto_save = router.auto_save

        return result

    def _execute_current_task(self, io: Optional[CLIIOProtocol] = None):
        """
        Execute the current task using intelligent routing.

        Takes the current task from the active plan and routes it through
        the TaskRouter for execution. Falls back to agent_mgr if routing fails.

        Args:
            io: IO interface for input/output. Defaults to self.io.

        Side Effects:
            - Displays task execution status messages to console
            - Routes task through TaskRouter which may:
              - Execute shell commands directly
              - Make LLM API calls for research queries
              - Run full agent loop for code generation
            - Logs task execution outcome
            - Prompts user for next action after completion
            - Falls back to agent_mgr.run_agent() on routing failure

        State Changes:
            - Does not modify plan state directly (caller handles progression)
            - Task execution may modify project files if it's a code task
            - Updates orchestrator discoveries with task results

        Returns:
            None
        """
        if io is None:
            io = self.io

        if not self.plan_active or not self.active_plan:
            return

        task = self.active_plan[self.current_task_index]

        # Build task description
        if isinstance(task, dict):
            task_name = task.get('step', 'Task')
            task_desc = task.get('description', task_name)
            full_task = f"{task_name}: {task_desc}"
        else:
            full_task = str(task)

        io.secho(f"\nAuto-executing task...", fg="cyan", bold=True)
        self.logger.info("Auto-executing task", extra={"task": full_task})

        # Use TaskRouter to intelligently route the task
        try:
            result = self.task_router.router.route(full_task)

            if result.success:
                io.secho("[OK] Task executed successfully", fg="green")
                if result.output:
                    io.echo(result.output[:1000])  # Truncate long output
                self.logger.info("Task completed", extra={"task": full_task})
            else:
                io.secho(f"[FAIL] Task failed: {result.error}", fg="red")
                self.logger.warning("Task failed", extra={"task": full_task, "error": result.error})

            # Show execution metadata
            if "classification" in result.metadata:
                cls_info = result.metadata["classification"]
                io.secho(
                    f"  [Strategy: {cls_info.get('type', 'unknown')} | "
                    f"Provider: {cls_info.get('resolved_provider', 'none')}]",
                    fg="bright_black"
                )
        except CLIError as e:
            io.secho(f"Error executing task: {e}", fg="red")
            if e.suggestion:
                io.echo(f"Suggestion: {e.suggestion}")
            self.logger.error("Task execution error", extra=e.logging_extra())
            # Fallback to agent manager if TaskRouter fails
            io.secho("Falling back to agent manager...", fg="yellow")
            self.agent_mgr.run_agent(full_task, io=io)
        except Exception as e:
            io.secho(f"Error executing task: {e}", fg="red")
            self.logger.exception("Unexpected error during task execution")
            # Fallback to agent manager if TaskRouter fails
            io.secho("Falling back to agent manager...", fg="yellow")
            self.agent_mgr.run_agent(full_task, io=io)

        # After task completes, prompt for next action
        self._prompt_task_progression(io=io)
