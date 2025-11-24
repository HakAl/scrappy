"""
Command router module for CLI.

Routes slash commands to appropriate handlers.
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from .io_interface import CLIIOProtocol
from .state_manager import PlanStateManager
from .session_context import SessionContextProtocol
from .display import CLIDisplay
from .session import CLISessionManager
from .codebase import CLICodebaseAnalysis
from .tasks import CLITaskExecution
from .multiprovider import CLIMultiProvider
from .smart_query import CLISmartQuery
from .agent_manager import CLIAgentManager
from .task_router_handler import CLITaskRouterHandler
from .validators import validate_command
from .utils.session_utils import (
    display_session_saved,
    display_session_save_error,
    display_session_not_saved_warning
)

if TYPE_CHECKING:
    from ..orchestrator.protocols import Orchestrator


class CommandRouter:
    """Routes slash commands to appropriate handlers."""

    def __init__(
        self,
        io: CLIIOProtocol,
        orchestrator: "Orchestrator",
        session_context: SessionContextProtocol,
        display: CLIDisplay,
        session_mgr: CLISessionManager,
        codebase: CLICodebaseAnalysis,
        tasks: CLITaskExecution,
        multiprovider: CLIMultiProvider,
        smart: CLISmartQuery,
        agent_mgr: CLIAgentManager,
        task_router: CLITaskRouterHandler,
        state_manager: Optional[PlanStateManager] = None
    ) -> None:
        """
        Initialize CommandRouter with all dependencies.

        Args:
            io: The IO interface for input/output.
            orchestrator: The agent orchestrator.
            session_context: Shared session context for state management.
            display: Display handler for showing information.
            session_mgr: Session manager for persistence.
            codebase: Codebase analysis handler.
            tasks: Task execution handler.
            multiprovider: Multi-provider handler.
            smart: Smart query handler.
            agent_mgr: Agent manager handler.
            task_router: Task router handler.
            state_manager: Optional plan state manager.
        """
        self.io = io
        self.orchestrator = orchestrator
        self.session_context = session_context
        self.display = display
        self.session_mgr = session_mgr
        self.codebase = codebase
        self.tasks = tasks
        self.multiprovider = multiprovider
        self.smart = smart
        self.agent_mgr = agent_mgr
        self.task_router = task_router
        self.state_manager = state_manager or PlanStateManager()

        # Build command registry for dispatch
        self._command_registry = {
            # Exit commands
            "/quit": self._handle_exit,
            "/exit": self._handle_exit,
            "/q": self._handle_exit,
            # Display commands
            "/help": self._handle_help,
            "/status": self._handle_status,
            "/providers": self._handle_providers,
            "/brain": self._handle_brain,
            "/usage": self._handle_usage,
            "/models": self._handle_models,
            # Session commands
            "/context": self._handle_context,
            "/cache": self._handle_cache,
            "/session": self._handle_session,
            "/limits": self._handle_limits,
            # Task commands
            "/plan": self._handle_plan,
            "/reason": self._handle_reason,
            "/agent": self._handle_agent,
            # Multi-provider commands
            "/synthesize": self._handle_synthesize,
            "/delegate": self._handle_delegate,
            # Smart query commands
            "/smart": self._handle_smart,
            # Codebase commands
            "/explore": self._handle_explore,
            # Task router commands
            "/classify": self._handle_classify,
            # State commands
            "/clear": self._handle_clear,
            "/autoexec": self._handle_autoexec,
            "/paste": self._handle_multiline,
            "/ml": self._handle_multiline,
            "/multiline": self._handle_multiline,
            "/auto": self._handle_auto,
            "/route": self._handle_auto,
            "/autoroute": self._handle_auto,
            # Tasks list command
            "/tasks": self._handle_tasks,
        }

    # =========================================================================
    # Command Handler Methods
    # =========================================================================

    def _handle_exit(self, args: str) -> bool:
        """Handle exit commands (/quit, /exit, /q)."""
        io = self.io
        if self.session_context.auto_save:
            try:
                session_file = self.orchestrator.save_session(self.session_context.conversation_history)
                display_session_saved(io, session_file, len(self.session_context.conversation_history), with_help=True)
            except Exception as e:
                display_session_save_error(io, e)
        else:
            display_session_not_saved_warning(io)

        self.display.show_usage()
        io.secho("\nGoodbye!", fg="cyan", bold=True)
        return False

    def _handle_help(self, args: str) -> bool:
        """Handle /help command."""
        # DEBUG: Prove this executes
        self.io.secho("[DEBUG] _handle_help called", fg="yellow")
        self.display.show_help()
        self.io.secho("[DEBUG] _handle_help done", fg="yellow")
        return True

    def _handle_status(self, args: str) -> bool:
        """Handle /status command."""
        self.display.show_status()
        return True

    def _handle_providers(self, args: str) -> bool:
        """Handle /providers command."""
        self.display.list_providers()
        return True

    def _handle_brain(self, args: str) -> bool:
        """Handle /brain command."""
        self.display.switch_brain(args)
        return True

    def _handle_usage(self, args: str) -> bool:
        """Handle /usage command."""
        self.display.show_usage()
        return True

    def _handle_models(self, args: str) -> bool:
        """Handle /models command."""
        self.display.list_models(args)
        return True

    def _handle_context(self, args: str) -> bool:
        """Handle /context command."""
        self.session_mgr.manage_context(args)
        return True

    def _handle_cache(self, args: str) -> bool:
        """Handle /cache command."""
        self.session_mgr.manage_cache(args)
        return True

    def _handle_session(self, args: str) -> bool:
        """Handle /session command."""
        result = self.session_mgr.manage_session(args, self.session_context.conversation_history, self.session_context.auto_save)
        if result.get('conversation_history') is not None:
            self.session_context.conversation_history = result['conversation_history']
        if result.get('auto_save') is not None:
            self.session_context.auto_save = result['auto_save']
        return True

    def _handle_limits(self, args: str) -> bool:
        """Handle /limits command."""
        self.session_mgr.show_rate_limits(args)
        return True

    def _handle_plan(self, args: str) -> bool:
        """Handle /plan command."""
        io = self.io
        if not args:
            io.echo("Usage: /plan <task description>")
        else:
            steps = self.tasks.plan_task(args)
            if steps and len(steps) > 0:
                if io.confirm("Start working on this plan?", default=True):
                    self.state_manager.start_plan(steps)
                    io.echo()
                    self.state_manager.show_current_task(io)
        return True

    def _handle_reason(self, args: str) -> bool:
        """Handle /reason command."""
        io = self.io
        if not args:
            io.echo("Usage: /reason <question>")
        else:
            self.tasks.reason(args)
        return True

    def _handle_agent(self, args: str) -> bool:
        """Handle /agent command."""
        io = self.io
        if not args:
            io.echo("Usage: /agent <task description>")
        else:
            self.agent_mgr.run_agent(args)
            if self.state_manager.plan_active:
                self.state_manager.prompt_task_progression(io)
        return True

    def _handle_synthesize(self, args: str) -> bool:
        """Handle /synthesize command."""
        self.multiprovider.synthesize_mode(io=self.io)
        return True

    def _handle_delegate(self, args: str) -> bool:
        """Handle /delegate command."""
        self.multiprovider.delegate_mode(args, io=self.io)
        return True

    def _handle_smart(self, args: str) -> bool:
        """Handle /smart command."""
        io = self.io
        if not args:
            status = io.style("ON", fg="green") if self.session_context.smart_mode else io.style("OFF", fg="yellow")
            io.echo(f"Smart query mode: {status}")
            io.echo("Usage: /smart <query> or /smart toggle")
        elif args.lower() == "toggle":
            self.session_context.smart_mode = not self.session_context.smart_mode
            status = "enabled" if self.session_context.smart_mode else "disabled"
            io.secho(f"Smart query mode {status}.", fg="green" if self.session_context.smart_mode else "yellow")
            if self.session_context.smart_mode:
                io.echo("All queries will now use tools for research (higher quota usage).")
        else:
            self.smart.smart_query(args)
        return True

    def _handle_explore(self, args: str) -> bool:
        """Handle /explore command."""
        self.codebase.explore_codebase(args, io=self.io)
        return True

    def _handle_classify(self, args: str) -> bool:
        """Handle /classify command."""
        io = self.io
        if not args:
            io.echo("Usage: /classify <task description>")
            io.echo("  Preview how a task would be classified without executing.")
        else:
            self.task_router.handle_classify_only(args)
        return True

    def _handle_clear(self, args: str) -> bool:
        """Handle /clear command."""
        self.session_context.conversation_history.clear()
        self.io.secho("Conversation history cleared.", fg="green")
        return True

    def _handle_autoexec(self, args: str) -> bool:
        """Handle /autoexec command."""
        io = self.io
        self.state_manager.auto_execute_tasks = not self.state_manager.auto_execute_tasks
        status = io.style("ENABLED", fg="green") if self.state_manager.auto_execute_tasks else io.style("DISABLED", fg="red")
        io.echo(f"Auto-execute tasks: {status}")
        if self.state_manager.auto_execute_tasks:
            io.echo("  Tasks in plans will be automatically executed using intelligent routing")
            io.echo("  (DIRECT_COMMAND -> immediate, RESEARCH -> fast LLM, CODE_GEN -> agent with approval)")
        else:
            io.echo("  Tasks in plans will wait for manual execution")
        return True

    def _handle_multiline(self, args: str) -> bool:
        """Handle multiline commands (/paste, /ml, /multiline)."""
        io = self.io
        self.session_context.multiline_mode = not self.session_context.multiline_mode
        if self.session_context.multiline_mode:
            io.secho("Multiline input mode: ON", fg="green", bold=True)
            io.echo("  - End a line with \\ to continue on next line")
            io.echo("  - Press Enter normally to send (no double-enter needed)")
            io.echo("  - Commands still work on the first line")
        else:
            io.secho("Multiline input mode: OFF", fg="yellow", bold=True)
            io.echo("  - Single line input (press Enter to send)")
            io.echo("  - Each line is processed separately")
        return True

    def _handle_auto(self, args: str) -> bool:
        """Handle auto-routing commands (/auto, /route, /autoroute)."""
        io = self.io
        if not args:
            self.session_context.auto_route_mode = not self.session_context.auto_route_mode
            if self.session_context.auto_route_mode:
                io.secho("Auto-routing mode: ON", fg="green", bold=True)
                io.echo("  Tasks are automatically classified and routed:")
                io.echo("  - Direct commands (pip, git) -> Shell execution")
                io.echo("  - Code generation -> Full agent loop with planning")
                io.echo("  - Research queries -> Fast provider (Cerebras)")
                io.echo("  - Simple chat -> Instant responses")
            else:
                io.secho("Auto-routing mode: OFF", fg="yellow", bold=True)
                io.echo("  All input goes to default chat mode.")
        elif args.lower() == "status":
            self.task_router.handle_route_status()
        elif args.lower() == "history":
            self.task_router.handle_route_history()
        else:
            io.echo("Usage: /auto [status|history]")
            io.echo("  /auto         - Toggle auto-routing mode")
            io.echo("  /auto status  - Show routing metrics")
            io.echo("  /auto history - Show routing history")
        return True

    def _handle_tasks(self, args: str) -> bool:
        """Handle /tasks command."""
        io = self.io
        if not self.state_manager.plan_active or not self.state_manager.active_plan:
            io.secho("No active plan. Use /plan <task> to create one.", fg="yellow")
        else:
            self.state_manager.show_all_tasks(io)
        return True

    def route(self, cmd: str, args: str) -> bool:
        """
        Route a command to its handler.

        Validates the command and dispatches it to the appropriate handler
        based on the command name using registry-based dispatch.

        Args:
            cmd: The command name (e.g., "/help", "/quit", "/plan").
            args: The command arguments as a single string.

        Returns:
            bool: True to continue the interactive loop, False to exit
                (returned by /quit, /exit, /q commands).
        """
        io = self.io

        # Validate command input
        full_command = f"{cmd} {args}".strip() if args else cmd
        validation_result = validate_command(full_command)

        if not validation_result.is_valid:
            io.secho(f"Invalid command: {validation_result.error}", fg="red")
            io.echo("Type /help for available commands.")
            io.echo()
            return True

        # Dispatch via registry
        import logging
        logger = logging.getLogger(__name__)
        handler = self._command_registry.get(cmd)
        logger.debug(f"[route] Looking up cmd='{cmd}', handler found: {handler is not None}")
        if handler:
            logger.debug(f"[route] Calling handler for '{cmd}'")
            result = handler(args)
            logger.debug(f"[route] Handler returned: {result}")
            io.echo()
            return result

        # Unknown command
        logger.debug(f"[route] Unknown command: '{cmd}'")
        io.secho(f"Unknown command: {cmd}", fg="yellow")
        io.echo("Type /help for available commands.")
        io.echo()
        return True
