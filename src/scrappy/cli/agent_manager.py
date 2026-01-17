"""
Code agent management for the CLI.
Handles running and managing code execution agents with human approval.
"""

from typing import TYPE_CHECKING, Optional

from scrappy.undo import create_undo_point, UndoError
from scrappy.sandbox.git_isolation import GitIsolation, GitError, BranchInfo
from .io_interface import CLIIOProtocol
from .display_manager import DisplayManager
from .user_interaction import CLIUserInteraction
from .utils.error_handler import handle_error

if TYPE_CHECKING:
    from .protocols import UserInteractionProtocol
    from .textual.langgraph_bridge import LangGraphBridge


class CLIAgentManager:
    """Manages code agent execution with human-in-the-loop approval."""

    def __init__(
        self,
        orchestrator,
        io: CLIIOProtocol,
        user_interaction: Optional["UserInteractionProtocol"] = None,
        langgraph_bridge: Optional["LangGraphBridge"] = None,
    ):
        """Initialize agent manager.

        Args:
            orchestrator: The AgentOrchestrator instance
            io: I/O interface for output (stored directly for DI)
            user_interaction: Optional interaction handler for prompts/confirms.
                Defaults to CLIUserInteraction if not provided.
            langgraph_bridge: Optional LangGraph bridge for TUI mode.
                When provided, run_agent uses LangGraph instead of CodeAgent.
        """
        self.orchestrator = orchestrator
        self.io = io  # Store directly per CLAUDE.md DI principles
        self.display = DisplayManager(io=io, dashboard_enabled=False)
        # Inject user interaction - defaults to CLI mode
        self._interaction = user_interaction or CLIUserInteraction(io)
        # LangGraph bridge for TUI mode
        self._langgraph_bridge = langgraph_bridge

    def cancel(self) -> None:
        """Cancel the currently running agent if any."""
        if self._langgraph_bridge is not None and self._langgraph_bridge.is_running:
            self._langgraph_bridge.cancel()
            self.io.secho("Cancelling...", fg=self.io.theme.warning)

    def run_agent(
        self,
        task: str,
        dry_run: bool = False,
        verbose: bool = False,
    ):
        """
        Run the LangGraph agent on a task with human-in-the-loop approval.

        Args:
            task: Description of the task for the agent to perform.
            dry_run: If True, agent simulates actions without making changes.
            verbose: If True, show full output (thinking, params, results).
        """
        import os

        io = self.io
        dashboard = self.display.get_dashboard()

        if self._langgraph_bridge is None:
            io.secho("Error: Agent not initialized", fg=io.theme.error)
            return

        # Update dashboard if enabled
        if dashboard:
            dashboard.set_state("idle", "Awaiting user input")
            dashboard.update_thought_process(f"Task: {task}")

        # Git isolation - create working branch to keep main clean
        branch_info: Optional[BranchInfo] = None
        git_isolation: Optional[GitIsolation] = None
        try:
            git_isolation = GitIsolation(os.getcwd())
            branch_info = git_isolation.create_working_branch(task)
            io.secho(f"Working branch: {branch_info.name}", fg=io.theme.success)
        except GitError as e:
            io.secho(f"Could not create working branch: {e}", fg=io.theme.warning)
            io.echo("Continuing on current branch...")

        # Safety options - use injected interaction handler for mode-aware prompts
        create_undo = self._interaction.confirm(
            "Create undo point before running?", default=True
        )

        undo_state = None
        if create_undo:
            io.echo("Creating undo point...")
            try:
                undo_state = create_undo_point()
                io.secho(f"Undo point created: {undo_state.ref.split('/')[-1]}", fg=io.theme.success)
            except UndoError as e:
                io.secho(f"Could not create undo point: {e}", fg=io.theme.warning)

        self._run_langgraph_agent(task, undo_state, branch_info, dry_run, dashboard)

    def _run_langgraph_agent(
        self,
        task: str,
        undo_state,
        branch_info: Optional[BranchInfo],
        dry_run: bool,
        dashboard,
    ) -> None:
        """
        Run the LangGraph agent via the bridge.

        This method is called when a LangGraphBridge is available (TUI mode).
        It delegates execution to the bridge which runs the agent in a
        worker thread with proper HITL confirmation support.

        Tool confirmation is enabled by default - user will be prompted
        with y/n/a before destructive operations. Pressing 'a' allows
        all remaining operations for the run.

        Args:
            task: The task to run
            undo_state: Undo state if checkpoint was created
            branch_info: Branch info if working branch was created
            dry_run: Whether this is a dry run (currently ignored for LangGraph)
            dashboard: Dashboard instance if enabled
        """
        import os

        io = self.io

        # Minimal config output - task is shown by the bridge
        if dry_run:
            io.secho("Note: dry_run not yet implemented for LangGraph", fg=io.theme.warning)

        if dashboard:
            dashboard.set_state("executing", "Running LangGraph agent...")
            dashboard.update_thought_process(f"Executing task: {task}\n\nLangGraph agent processing...")

        try:
            import logging
            lgr = logging.getLogger(__name__)
            lgr.debug("_run_langgraph_agent: calling bridge.run_agent")

            # Run agent via bridge (synchronous call that runs in current thread)
            # The bridge handles all HITL confirmations via ThreadSafeAsyncBridge
            assert self._langgraph_bridge is not None  # Type guard for mypy
            result = self._langgraph_bridge.run_agent(
                task=task,
                working_dir=os.getcwd(),
            )

            lgr.debug("_run_langgraph_agent: bridge.run_agent returned, result.success=%s, result.cancelled=%s",
                     result.success, result.cancelled)

            if dashboard:
                dashboard.set_state("idle", "Task completed")

            # Completion summary is output by the bridge
            # Just record to working memory for context
            if result.cancelled:
                self.orchestrator.working_memory.add_discovery(
                    f"Agent task '{task[:50]}...' cancelled by user",
                    "agent_task"
                )
            elif result.success:
                iterations = result.final_state.iteration if result.final_state else 0
                self.orchestrator.working_memory.add_discovery(
                    f"Agent task '{task[:50]}...': completed in {iterations} iterations",
                    "agent_task"
                )
            else:
                self.orchestrator.working_memory.add_discovery(
                    f"Agent task '{task[:50]}...' failed: {result.error or 'unknown'}",
                    "agent_task"
                )

            # Inform user about rollback options (if files were changed)
            if not dry_run and result.final_state and result.final_state.files_changed:
                rollback_options = []
                if undo_state:
                    rollback_options.append("scrappy undo")
                if branch_info:
                    rollback_options.append(f"git checkout {branch_info.base_branch}")
                if rollback_options:
                    io.echo(f"To rollback: {' | '.join(rollback_options)}")

        except KeyboardInterrupt:
            lgr.debug("_run_langgraph_agent: KeyboardInterrupt")
            io.echo("\n\nAgent interrupted by user.")
            self.orchestrator.working_memory.add_discovery(
                f"Agent task '{task[:50]}...' interrupted by user",
                "agent_task"
            )
        except Exception as e:
            lgr.debug("_run_langgraph_agent: Exception: %s", e)
            io.echo()  # Newline before error
            handle_error(e, io, context="LangGraph agent execution")
            self.orchestrator.working_memory.add_discovery(
                f"Agent task '{task[:50]}...' failed: {str(e)[:50]}",
                "agent_task"
            )
        finally:
            lgr.debug("_run_langgraph_agent: finally block, cleaning up")
            # Clear task progress widget
            output_sink = getattr(io, "output_sink", None)
            if output_sink is not None and hasattr(output_sink, "post_tasks_updated"):
                output_sink.post_tasks_updated([])
            lgr.debug("_run_langgraph_agent: returning")
