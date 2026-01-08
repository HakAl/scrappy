"""
Command router module for CLI.

Routes slash commands to appropriate handlers.
"""

from pathlib import Path
from typing import Callable, Optional
from .io_interface import CLIIOProtocol
from .state_manager import PlanStateManager
from .session_context import SessionContextProtocol
from .display import CLIDisplay
from .session import CLISessionManager
from .codebase import CLICodebaseAnalysis
from .tasks import CLITaskExecution
from .smart_query import CLISmartQuery
from .agent_manager import CLIAgentManager
from .task_router_handler import CLITaskRouterHandler
from .validators import validate_command
from .utils.dependency_check import check_agent_dependencies, check_optional_dependencies
from .utils.session_utils import (
    display_session_saved,
    display_session_save_error,
    display_session_not_saved_warning
)
from ..orchestrator.protocols import Orchestrator
from ..orchestrator.model_selection import ModelSelectionType


class CommandRouter:
    """Routes slash commands to appropriate handlers."""

    def __init__(
        self,
        io: CLIIOProtocol,
        orchestrator: Orchestrator,
        session_context: SessionContextProtocol,
        display: CLIDisplay,
        session_mgr: CLISessionManager,
        codebase: CLICodebaseAnalysis,
        tasks: CLITaskExecution,
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
        self.smart = smart
        self.agent_mgr = agent_mgr
        self.task_router = task_router
        self.state_manager = state_manager or PlanStateManager()

        # Optional callback for TUI mode to launch wizard screen
        self._setup_wizard_callback: Optional[Callable[[], None]] = None

        # Build command registry for dispatch
        self._command_registry = {
            # Exit commands
            "/quit": self._handle_exit,
            "/exit": self._handle_exit,
            "/q": self._handle_exit,
            # Display commands
            "/help": self._handle_help,
            "/status": self._handle_status,
            "/usage": self._handle_usage,
            "/models": self._handle_models,
            "/model": self._handle_model,
            # Session commands
            "/context": self._handle_context,
            "/cache": self._handle_cache,
            "/session": self._handle_session,
            "/limits": self._handle_limits,
            # Task commands
            "/plan": self._handle_plan,
            "/reason": self._handle_reason,
            "/agent": self._handle_agent,
            # Smart query commands
            "/smart": self._handle_smart,
            # Codebase commands
            "/explore": self._handle_explore,
            # Task router commands
            "/classify": self._handle_classify,
            # State commands
            "/clear": self._handle_clear,
            "/history": self._handle_history,
            "/autoexec": self._handle_autoexec,
            "/verbose": self._handle_verbose,
            "/v": self._handle_verbose,
            # Tasks list command
            "/tasks": self._handle_tasks,
            # Setup command
            "/setup": self._handle_setup,
        }

    # =========================================================================
    # Command Handler Methods
    # =========================================================================

    def _handle_exit(self, args: str) -> bool:
        """Handle exit commands (/quit, /exit, /q)."""
        io = self.io
        if self.session_context.auto_save:
            try:
                session_file = self.orchestrator.save_session()
                display_session_saved(io, session_file, len(self.session_context.conversation_history), with_help=True)
            except Exception as e:
                display_session_save_error(io, e)
        else:
            display_session_not_saved_warning(io)

        self.display.show_usage()
        io.secho("\nGoodbye!", fg=io.theme.primary, bold=True)
        return False

    def _handle_help(self, args: str) -> bool:
        """Handle /help command."""
        self.display.show_help()
        return True

    def _handle_status(self, args: str) -> bool:
        """Handle /status command."""
        self.display.show_status()
        return True

    def _handle_usage(self, args: str) -> bool:
        """Handle /usage command."""
        self.display.show_usage()
        return True

    def _handle_models(self, args: str) -> bool:
        """Handle /models command."""
        self.display.list_models(args)
        return True

    def _handle_model(self, args: str) -> bool:
        """Handle /model command to set model tier.

        Model Tiers:
        - fast: 8B models, speed priority
        - chat: 70B models, conversation (maps to quality_mode=True for backwards compat)
        - instruct: Instruction-tuned models for agent/tools (maps to quality_mode=True)
        """
        io = self.io
        arg = args.strip().lower()

        # Map tier names to selection types and quality_mode
        tier_map = {
            "fast": (ModelSelectionType.FAST, False),
            "chat": (ModelSelectionType.CHAT, True),
            "instruct": (ModelSelectionType.INSTRUCT, True),
            # Backwards compatibility
            "quality": (ModelSelectionType.CHAT, True),
        }

        tier_descriptions = {
            "fast": "8B models, high throughput",
            "chat": "70B models, conversation",
            "instruct": "Instruction-tuned models (agent/tools)",
        }

        if arg in tier_map:
            selection_type, quality_mode = tier_map[arg]
            self.orchestrator.quality_mode = quality_mode
            # Get actual model being used for feedback
            try:
                provider, model = self.orchestrator.provider_selector.get_model(selection_type)
                io.secho(f"Switched to {arg.upper()} tier", fg=io.theme.success, bold=True)
                io.echo(f"  Using: {provider}/{model}")
                io.echo(f"  {tier_descriptions.get(arg, '')}")
            except Exception as e:
                io.secho(f"Switched to {arg.upper()} tier", fg=io.theme.success)
                io.secho(f"  Warning: Could not determine model - {e}", fg=io.theme.warning)
        else:
            # Show current mode
            mode = "CHAT" if self.orchestrator.quality_mode else "FAST"
            selection_type = ModelSelectionType.CHAT if self.orchestrator.quality_mode else ModelSelectionType.FAST
            try:
                provider, model = self.orchestrator.provider_selector.get_model(selection_type)
                io.echo(f"Current tier: {io.style(mode, fg=io.theme.success, bold=True)}")
                io.echo(f"  Using: {provider}/{model}")
            except Exception as e:
                io.echo(f"Current tier: {io.style(mode, fg=io.theme.success, bold=True)}")
                io.secho(f"  Warning: Could not determine model - {e}", fg=io.theme.warning)
            io.echo()
            io.echo("Usage: /model fast | /model chat | /model instruct")
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
        self.session_mgr.manage_session(args)
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

        # Parse flags
        dry_run = False
        verbose = False
        clear_tasks = False
        if "--dry-run" in args:
            dry_run = True
            args = args.replace("--dry-run", "").strip()
        if "--verbose" in args or "-v" in args:
            verbose = True
            args = args.replace("--verbose", "").replace(" -v ", " ").strip()
            if args.startswith("-v "):
                args = args[3:]
            if args.endswith(" -v"):
                args = args[:-3]
        if "--clear" in args:
            clear_tasks = True
            args = args.replace("--clear", "").strip()

        if not args:
            io.echo("Usage: /agent <task description>")
            io.echo("  --dry-run  Simulate actions without making changes")
            io.echo("  --verbose  Show full output (thinking, params, results)")
            io.echo("  --clear    Clear previous task list before starting")
            io.echo("")
            io.echo("Tool confirmation is enabled by default. Respond with:")
            io.echo("  y - allow this operation")
            io.echo("  n - deny this operation")
            io.echo("  a - allow all remaining operations")
            return True

        # Check dependencies before running agent
        deps_ok, errors = check_agent_dependencies()
        if not deps_ok:
            io.secho("Agent requires missing dependencies:", fg=io.theme.error)
            for err in errors:
                io.echo(f"  - {err}")
            return True

        # Check optional dependencies and warn
        warnings = check_optional_dependencies()
        for warning in warnings:
            io.secho(f"Warning: {warning}", fg=io.theme.warning)

        # Handle existing tasks
        if not self._handle_existing_tasks(io, clear_tasks):
            return True  # User cancelled

        import logging
        logger = logging.getLogger(__name__)
        logger.debug("[_handle_agent] Calling agent_mgr.run_agent")
        self.agent_mgr.run_agent(args, dry_run=dry_run, verbose=verbose)
        logger.debug("[_handle_agent] agent_mgr.run_agent returned")
        if self.state_manager.plan_active:
            self.state_manager.prompt_task_progression(io)
        logger.debug("[_handle_agent] returning True")
        return True

    def _handle_existing_tasks(self, io: CLIIOProtocol, clear_tasks: bool) -> bool:
        """Check for existing tasks and handle appropriately.

        Args:
            io: IO interface for prompts and output.
            clear_tasks: If True, clear tasks without prompting.

        Returns:
            True to continue with agent, False if user cancelled.
        """
        from ..agent_tools.tools.task_tools import MarkdownTaskStorage
        from ..protocols.tasks import TaskStatus
        from ..infrastructure.paths import ScrappyPathProvider

        # Use ScrappyPathProvider for consistent path handling
        path_provider = ScrappyPathProvider(Path.cwd())
        storage = MarkdownTaskStorage(path_provider.todo_file())

        if not storage.exists():
            return True  # No tasks, continue

        tasks = storage.read_tasks()
        pending = [t for t in tasks if t.status != TaskStatus.DONE]

        if not pending:
            return True  # No pending tasks, continue

        # Clear flag bypasses prompt
        if clear_tasks:
            storage.clear()
            io.secho("Cleared previous task list.", fg=io.theme.info)
            return True

        # Show existing tasks and prompt
        io.echo("\nFound tasks from previous session:")
        for task in pending:
            if task.status == TaskStatus.IN_PROGRESS:
                checkbox = "[>]"
            else:
                checkbox = "[ ]"
            priority = f"[{task.priority.value}] " if task.priority else ""
            io.echo(f"  {checkbox} {priority}{task.description}")
        io.echo()

        # Prompt user
        continue_tasks = io.confirm("Continue these tasks?", default=True)

        if not continue_tasks:
            storage.clear()
            io.secho("Cleared task list. Starting fresh.", fg=io.theme.info)

        return True  # Always continue (user chose continue or clear)

    def _handle_smart(self, args: str) -> bool:
        """Handle /smart command."""
        io = self.io
        if not args:
            status = io.style("ON", fg=io.theme.success) if self.session_context.smart_mode else io.style("OFF", fg=io.theme.warning)
            io.echo(f"Smart query mode: {status}")
            io.echo("Usage: /smart <query> or /smart toggle")
        elif args.lower() == "toggle":
            self.session_context.smart_mode = not self.session_context.smart_mode
            status = "enabled" if self.session_context.smart_mode else "disabled"
            io.secho(f"Smart query mode {status}.", fg=io.theme.success if self.session_context.smart_mode else io.theme.warning)
            if self.session_context.smart_mode:
                io.echo("All queries will now use tools for research (higher quota usage).")
        else:
            self.smart.smart_query(args)
        return True

    def _handle_explore(self, args: str) -> bool:
        """Handle /explore command."""
        self.codebase.explore_codebase(args)
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
        self.io.secho("Conversation history cleared.", fg=self.io.theme.success)
        return True

    def _handle_history(self, args: str) -> bool:
        """Handle /history command to show conversation history."""
        io = self.io
        history = self.session_context.conversation_history

        if not history:
            io.secho("No conversation history.", fg=io.theme.warning)
            return True

        # Parse optional count argument
        count = 10  # Default to last 10 messages
        if args.strip():
            try:
                count = int(args.strip())
                if count <= 0:
                    io.secho("Count must be a positive number.", fg=io.theme.error)
                    return True
            except ValueError:
                io.secho(f"Invalid count: {args}. Usage: /history [n]", fg=io.theme.error)
                return True

        # Get the last n messages
        messages_to_show = history[-count:] if count < len(history) else history
        total = len(history)
        showing = len(messages_to_show)

        io.secho(f"\nConversation History ({showing} of {total} messages):", fg=io.theme.accent, bold=True)
        io.secho("-" * 50, fg=io.theme.accent)

        for i, msg in enumerate(messages_to_show):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            # Truncate long messages for display
            max_len = 200
            if len(content) > max_len:
                content = content[:max_len] + "..."

            # Style based on role
            if role == "user":
                role_style = io.style("You:", fg=io.theme.primary, bold=True)
            elif role == "assistant":
                role_style = io.style("Assistant:", fg=io.theme.success, bold=True)
            else:
                role_style = io.style(f"{role}:", fg=io.theme.warning)

            io.echo(f"{role_style} {content}")

        io.echo()
        io.echo("Use /history [n] to show last n messages (default: 10)")
        return True

    def _handle_autoexec(self, args: str) -> bool:
        """Handle /autoexec command."""
        io = self.io
        self.state_manager.auto_execute_tasks = not self.state_manager.auto_execute_tasks
        status = io.style("ENABLED", fg=io.theme.success) if self.state_manager.auto_execute_tasks else io.style("DISABLED", fg=io.theme.error)
        io.echo(f"Auto-execute tasks: {status}")
        if self.state_manager.auto_execute_tasks:
            io.echo("  Tasks in plans will be automatically executed using intelligent routing")
            io.echo("  (DIRECT_COMMAND -> immediate, RESEARCH -> fast LLM, CODE_GEN -> agent with approval)")
        else:
            io.echo("  Tasks in plans will wait for manual execution")
        return True

    def _handle_tasks(self, args: str) -> bool:
        """Handle /tasks command."""
        io = self.io
        if not self.state_manager.plan_active or not self.state_manager.active_plan:
            io.secho("No active plan. Use /plan <task> to create one.", fg=io.theme.warning)
        else:
            self.state_manager.show_all_tasks(io)
        return True

    def _handle_verbose(self, args: str) -> bool:
        """Handle /verbose command to toggle verbose output mode."""
        io = self.io
        self.session_context.verbose_mode = not self.session_context.verbose_mode
        if self.session_context.verbose_mode:
            io.secho("Verbose mode: ON", fg=io.theme.success, bold=True)
            io.echo("  Metadata (provider, tokens, time) will be shown for responses.")
        else:
            io.secho("Verbose mode: OFF", fg=io.theme.warning, bold=True)
            io.echo("  Clean output without metadata.")
        return True

    def set_setup_wizard_callback(self, callback: Callable[[], None]) -> None:
        """Set callback for launching setup wizard in TUI mode.

        Args:
            callback: Function to call to launch the wizard screen
        """
        self._setup_wizard_callback = callback

    def _handle_setup(self, args: str) -> bool:
        """Handle /setup command - launch provider setup wizard."""
        # In TUI mode, use the dedicated wizard screen
        if self._setup_wizard_callback is not None:
            self._setup_wizard_callback()
            return True

        # CLI mode - use blocking wizard
        from .setup_wizard import SetupWizard
        from scrappy.orchestrator.key_validator import create_key_validator

        io = self.io

        io.echo("Launching provider setup wizard...")
        wizard = SetupWizard(io, create_key_validator())
        wizard.run(allow_cancel=True)
        # Reconfigure llm_service after wizard saves new keys
        self.orchestrator.llm_service.configure()
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
            io.secho(f"Invalid command: {validation_result.error}", fg=io.theme.error)
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
        io.secho(f"Unknown command: {cmd}", fg=io.theme.warning)
        io.echo("Type /help for available commands.")
        io.echo()
        return True
