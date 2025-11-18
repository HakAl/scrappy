"""
Core CLI functionality.
Main entry point and command routing for the LLM Agent Team CLI.
"""

import sys
from datetime import datetime
from typing import Optional

try:
    from ..orchestrator import AgentOrchestrator
    from .display import CLIDisplay
    from .session import CLISessionManager
    from .codebase import CLICodebaseAnalysis
    from .tasks import CLITaskExecution
    from .multiprovider import CLIMultiProvider
    from .smart_query import CLISmartQuery
    from .agent_manager import CLIAgentManager
    from .task_router_handler import CLITaskRouterHandler
    from .io_interface import CLIIOProtocol, ClickIO
    from .tool_detector import needs_tool_support
    from .input_handler import InputHandler
    from .state_manager import PlanStateManager
    from .command_router import CommandRouter
    from .interactive import InteractiveMode
    from .utils.session_utils import display_previous_session_detected
    from .utils.cli_factory import initialize_cli_handlers
except ImportError:
    # Allow running as script
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from orchestrator import AgentOrchestrator
    from cli.display import CLIDisplay
    from cli.session import CLISessionManager
    from cli.codebase import CLICodebaseAnalysis
    from cli.tasks import CLITaskExecution
    from cli.multiprovider import CLIMultiProvider
    from cli.smart_query import CLISmartQuery
    from cli.agent_manager import CLIAgentManager
    from cli.task_router_handler import CLITaskRouterHandler
    from cli.io_interface import CLIIOProtocol, ClickIO
    from cli.tool_detector import needs_tool_support
    from cli.input_handler import InputHandler
    from cli.state_manager import PlanStateManager
    from cli.command_router import CommandRouter
    from cli.interactive import InteractiveMode
    from cli.utils.session_utils import display_previous_session_detected
    from cli.utils.cli_factory import initialize_cli_handlers


class CLI:
    """Interactive CLI for the LLM Agent Team."""

    def __init__(
        self,
        brain: Optional[str] = None,
        auto_explore: bool = False,
        context_aware: bool = True,
        verbose_selection: bool = False,
        show_provider_status: bool = False,
        io: Optional[CLIIOProtocol] = None
    ):
        """Initialize CLI with orchestrator and component handlers."""
        if io is None:
            io = ClickIO()
        self.io = io

        io.secho("Initializing LLM Agent Team...", fg="cyan")

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

        # Display initialization info (unless show_provider_status already did)
        if not show_provider_status:
            io.echo(f"Brain: {io.style(self.orchestrator.brain, fg='green', bold=True)}")
            providers_list = ', '.join(self.orchestrator.providers.list_available())
            io.echo(f"Available providers: {io.style(providers_list, fg='cyan')}")

        # Show context status
        if self.orchestrator.context.is_explored():
            io.secho(f"Context: {self.orchestrator.context.project_path.name} (cached)", fg="cyan")
        elif context_aware:
            io.secho("Context: Not explored (use /context to explore)", fg="yellow")

        # Auto-detect and offer to load previous session
        self._check_and_offer_session_restore(io=io)

        io.echo()

    def _check_and_offer_session_restore(self, io: Optional[CLIIOProtocol] = None):
        """Check for existing session and offer to restore it automatically."""
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
                result = self.orchestrator.load_session()
                if result['status'] == 'loaded':
                    io.secho("Session restored successfully!", fg="green")
                    io.echo(f"  Files: {result['files_restored']}")
                    io.echo(f"  Searches: {result['searches_restored']}")
                    io.echo(f"  Git ops: {result['git_ops_restored']}")
                    io.echo(f"  Discoveries: {result['discoveries_restored']}")
                else:
                    io.secho(f"Could not restore session: {result.get('message', 'unknown error')}", fg="red")
            else:
                io.secho("Starting fresh session.", fg="yellow")
        except (EOFError, Exception):
            # Non-interactive environment or user cancelled
            io.secho("Starting fresh session.", fg="yellow")

    def interactive_mode(self):
        """Run interactive chat mode."""
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
        """Handle slash commands (delegates to CommandRouter)."""
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
        """Execute the current task using intelligent routing."""
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

        # Use TaskRouter to intelligently route the task
        try:
            result = self.task_router.router.route(full_task)

            if result.success:
                io.secho("[OK] Task executed successfully", fg="green")
                if result.output:
                    io.echo(result.output[:1000])  # Truncate long output
            else:
                io.secho(f"[FAIL] Task failed: {result.error}", fg="red")

            # Show execution metadata
            if "classification" in result.metadata:
                cls_info = result.metadata["classification"]
                io.secho(
                    f"  [Strategy: {cls_info.get('type', 'unknown')} | "
                    f"Provider: {cls_info.get('resolved_provider', 'none')}]",
                    fg="bright_black"
                )
        except Exception as e:
            io.secho(f"Error executing task: {e}", fg="red")
            # Fallback to agent manager if TaskRouter fails
            io.secho("Falling back to agent manager...", fg="yellow")
            self.agent_mgr.run_agent(full_task, io=io)

        # After task completes, prompt for next action
        self._prompt_task_progression(io=io)
