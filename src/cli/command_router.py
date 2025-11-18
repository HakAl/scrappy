"""
Command router module for CLI.

Routes slash commands to appropriate handlers.
"""

from datetime import datetime
from typing import Any, List, Optional
from .io_interface import CLIIOProtocol
from .state_manager import PlanStateManager
from .display import CLIDisplay
from .session import CLISessionManager
from .codebase import CLICodebaseAnalysis
from .tasks import CLITaskExecution
from .multiprovider import CLIMultiProvider
from .smart_query import CLISmartQuery
from .agent_manager import CLIAgentManager
from .task_router_handler import CLITaskRouterHandler


class CommandRouter:
    """Routes slash commands to appropriate handlers."""

    def __init__(
        self,
        io: CLIIOProtocol,
        orchestrator: Any,
        state_manager: Optional[PlanStateManager] = None
    ):
        """
        Initialize CommandRouter with IO interface and orchestrator.

        Args:
            io: The IO interface for input/output.
            orchestrator: The agent orchestrator.
            state_manager: Optional plan state manager.
        """
        self.io = io
        self.orchestrator = orchestrator
        self.state_manager = state_manager or PlanStateManager()

        # State attributes
        self.conversation_history: List[dict] = []
        self.multiline_mode: bool = True
        self.auto_route_mode: bool = True
        self.smart_mode: bool = False
        self.auto_save: bool = True

        # Initialize component handlers
        self.session_start = datetime.now()
        self.display = CLIDisplay(orchestrator, self.session_start)
        self.session_mgr = CLISessionManager(orchestrator)
        self.codebase = CLICodebaseAnalysis(orchestrator)
        self.tasks = CLITaskExecution(orchestrator)
        self.multiprovider = CLIMultiProvider(orchestrator)
        self.smart = CLISmartQuery(orchestrator)
        self.agent_mgr = CLIAgentManager(orchestrator)
        self.task_router = CLITaskRouterHandler(orchestrator)

    def route(self, cmd: str, args: str) -> bool:
        """
        Route a command to its handler.

        Args:
            cmd: The command name (e.g., "/help").
            args: The command arguments.

        Returns:
            True to continue the loop, False to exit.
        """
        io = self.io

        # Exit commands
        if cmd in ["/quit", "/exit", "/q"]:
            # Auto-save session on exit if enabled
            if self.auto_save:
                try:
                    session_file = self.orchestrator.save_session(self.conversation_history)
                    io.secho(f"\nSession saved to: {session_file}", fg="green")
                    io.echo(f"  Conversation: {len(self.conversation_history)} messages")
                    io.echo("Use 'llm-team --resume' to continue later.")
                except Exception as e:
                    io.secho(f"Warning: Could not save session: {e}", fg="yellow")
            else:
                io.secho("\nSession not saved (auto-save disabled).", fg="yellow")
                io.echo("Use '/session save' to manually save before quitting.")

            self.display.show_usage()
            io.secho("\nGoodbye!", fg="cyan", bold=True)
            return False

        # Display commands
        elif cmd == "/help":
            self.display.show_help()

        elif cmd == "/status":
            self.display.show_status()

        elif cmd == "/providers":
            self.display.list_providers()

        elif cmd == "/brain":
            self.display.switch_brain(args)

        elif cmd == "/usage":
            self.display.show_usage()

        elif cmd == "/models":
            self.display.list_models(args)

        # Session commands
        elif cmd == "/context":
            self.session_mgr.manage_context(args, io=io)

        elif cmd == "/cache":
            self.session_mgr.manage_cache(args, io=io)

        elif cmd == "/session":
            result = self.session_mgr.manage_session(args, self.conversation_history, self.auto_save, io=io)
            # Update state if changed
            if result.get('conversation_history') is not None:
                self.conversation_history = result['conversation_history']
            if result.get('auto_save') is not None:
                self.auto_save = result['auto_save']

        elif cmd == "/limits":
            self.session_mgr.show_rate_limits(args, io=io)

        # Task commands
        elif cmd == "/plan":
            if not args:
                io.echo("Usage: /plan <task description>")
            else:
                steps = self.tasks.plan_task(args)
                if steps and len(steps) > 0:
                    # Prompt to start tracking
                    if io.confirm("Start working on this plan?", default=True):
                        self.state_manager.start_plan(steps)
                        io.echo()
                        self.state_manager.show_current_task(io)

        elif cmd == "/reason":
            if not args:
                io.echo("Usage: /reason <question>")
            else:
                self.tasks.reason(args)

        elif cmd == "/agent":
            if not args:
                io.echo("Usage: /agent <task description>")
            else:
                self.agent_mgr.run_agent(args, io=io)
                # Prompt for task progression if plan is active
                if self.state_manager.plan_active:
                    self.state_manager.prompt_task_progression(io)

        # Multi-provider commands
        elif cmd == "/synthesize":
            self.multiprovider.synthesize_mode(io=io)

        elif cmd == "/delegate":
            self.multiprovider.delegate_mode(args, io=io)

        # Smart query commands
        elif cmd == "/smart":
            if not args:
                # Show smart mode status
                status = io.style("ON", fg="green") if self.smart_mode else io.style("OFF", fg="yellow")
                io.echo(f"Smart query mode: {status}")
                io.echo("Usage: /smart <query> or /smart toggle")
            elif args.lower() == "toggle":
                self.smart_mode = not self.smart_mode
                status = "enabled" if self.smart_mode else "disabled"
                io.secho(f"Smart query mode {status}.", fg="green" if self.smart_mode else "yellow")
                if self.smart_mode:
                    io.echo("All queries will now use tools for research (higher quota usage).")
            else:
                self.smart.smart_query(args)

        # Codebase commands
        elif cmd == "/explore":
            self.codebase.explore_codebase(args, io=io)

        # Task router commands
        elif cmd == "/classify":
            if not args:
                io.echo("Usage: /classify <task description>")
                io.echo("  Preview how a task would be classified without executing.")
            else:
                self.task_router.handle_classify_only(args)

        # State commands
        elif cmd == "/clear":
            self.conversation_history.clear()
            io.secho("Conversation history cleared.", fg="green")

        elif cmd == "/autoexec":
            # Toggle auto-execute for plan tasks
            self.state_manager.auto_execute_tasks = not self.state_manager.auto_execute_tasks
            status = io.style("ENABLED", fg="green") if self.state_manager.auto_execute_tasks else io.style("DISABLED", fg="red")
            io.echo(f"Auto-execute tasks: {status}")
            if self.state_manager.auto_execute_tasks:
                io.echo("  Tasks in plans will be automatically executed using intelligent routing")
                io.echo("  (DIRECT_COMMAND -> immediate, RESEARCH -> fast LLM, CODE_GEN -> agent with approval)")
            else:
                io.echo("  Tasks in plans will wait for manual execution")

        elif cmd in ["/paste", "/ml", "/multiline"]:
            # Toggle multiline input mode
            self.multiline_mode = not self.multiline_mode
            if self.multiline_mode:
                io.secho("Multiline input mode: ON", fg="green", bold=True)
                io.echo("  - End a line with \\ to continue on next line")
                io.echo("  - Press Enter normally to send (no double-enter needed)")
                io.echo("  - Commands still work on the first line")
            else:
                io.secho("Multiline input mode: OFF", fg="yellow", bold=True)
                io.echo("  - Single line input (press Enter to send)")
                io.echo("  - Each line is processed separately")

        elif cmd in ["/auto", "/route", "/autoroute"]:
            if not args:
                # Toggle auto-routing mode
                self.auto_route_mode = not self.auto_route_mode
                if self.auto_route_mode:
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

        # Tasks list command
        elif cmd == "/tasks":
            if not self.state_manager.plan_active or not self.state_manager.active_plan:
                io.secho("No active plan. Use /plan <task> to create one.", fg="yellow")
            else:
                self.state_manager.show_all_tasks(io)

        # Unknown command
        else:
            io.secho(f"Unknown command: {cmd}", fg="yellow")
            io.echo("Type /help for available commands.")

        io.echo()
        return True
