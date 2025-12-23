"""
Code agent management for the CLI.
Handles running and managing code execution agents with human approval.
"""

from typing import TYPE_CHECKING, Optional

from ..agent import CodeAgent, CancellationToken, create_git_checkpoint, rollback_to_checkpoint
from ..agent_config import AgentConfig
from .io_interface import CLIIOProtocol
from .display_manager import DisplayManager
from .user_interaction import CLIUserInteraction
from .utils.error_handler import handle_error

if TYPE_CHECKING:
    from .protocols import UserInteractionProtocol


class CLIAgentManager:
    """Manages code agent execution with human-in-the-loop approval."""

    def __init__(
        self,
        orchestrator,
        io: CLIIOProtocol,
        user_interaction: Optional["UserInteractionProtocol"] = None,
    ):
        """Initialize agent manager.

        Args:
            orchestrator: The AgentOrchestrator instance
            io: I/O interface for output (stored directly for DI)
            user_interaction: Optional interaction handler for prompts/confirms.
                Defaults to CLIUserInteraction if not provided.
        """
        self.orchestrator = orchestrator
        self.io = io  # Store directly per CLAUDE.md DI principles
        self.display = DisplayManager(io=io, dashboard_enabled=False)
        # Inject user interaction - defaults to CLI mode
        self._interaction = user_interaction or CLIUserInteraction(io)
        # Cancellation token for current agent run (None when no agent running)
        self._cancellation_token: Optional[CancellationToken] = None

    def cancel(self) -> None:
        """Cancel the currently running agent if any.

        First cancel: graceful (waits for current step)
        Second cancel: force (marks for immediate termination)
        """
        if self._cancellation_token:
            was_force_cancelled = self._cancellation_token.is_force_cancelled()
            self._cancellation_token.cancel()

            if self._cancellation_token.is_force_cancelled() and not was_force_cancelled:
                self.io.secho("Force cancelling...", fg=self.io.theme.error)
            elif not self._cancellation_token.is_force_cancelled():
                self.io.secho("Cancelling... waiting for current step to finish (press again to force)", fg=self.io.theme.warning)

    def is_force_cancelled(self) -> bool:
        """Check if force cancel was requested."""
        return self._cancellation_token and self._cancellation_token.is_force_cancelled()

    def reset_cancel_state(self) -> None:
        """Reset cancellation state for a new agent run."""
        if self._cancellation_token:
            self._cancellation_token.reset()

    def run_agent(self, task: str, dry_run: bool = False, verbose: bool = False):
        """
        Run the code agent on a task with human-in-the-loop approval.

        Creates and executes a CodeAgent for the given task, with interactive
        prompts for git checkpoints.

        Args:
            task: Description of the task for the agent to perform.
            dry_run: If True, agent simulates actions without making changes.
            verbose: If True, show full output (thinking, params, results).

        Side Effects:
            - Prompts user for checkpoint creation
            - May create a git checkpoint before execution
            - Displays agent configuration and progress to console via self.display
            - Agent may modify project files if not in dry-run mode
            - Displays audit log summary after execution
            - May save audit log to file if user requests
            - May rollback to checkpoint if user requests
            - Adds discovery to orchestrator's working memory
            - Updates dashboard if dashboard mode is enabled

        State Changes:
            - Creates temporary CodeAgent instance (not stored)
            - Updates orchestrator.discoveries with task result
            - May create new git commits (for checkpoint/rollback)
            - May modify project files via agent execution

        Raises:
            KeyboardInterrupt: If user interrupts agent execution.
            Exception: Any unhandled errors from agent execution are caught
                and displayed, then recorded as discoveries.

        Returns:
            None
        """
        io = self.io  # Use stored reference directly
        dashboard = self.display.get_dashboard()

        io.secho(f"\nCode Agent - Task: {task}", bold=True)
        io.echo("-" * 60)

        # Create cancellation token FIRST so Escape works during any prompt
        self.reset_cancel_state()
        self._cancellation_token = CancellationToken()

        # Update dashboard if enabled
        if dashboard:
            dashboard.set_state("idle", "Awaiting user input")
            dashboard.update_thought_process(f"Task: {task}")

        # Safety options - use injected interaction handler for mode-aware prompts
        create_checkpoint = self._interaction.confirm(
            "Create git checkpoint before running?", default=True
        )

        # Check if user cancelled during checkpoint prompt
        if self._cancellation_token.is_cancelled():
            io.secho("Agent cancelled.", fg=io.theme.warning)
            self._cancellation_token = None
            return

        checkpoint_hash = None
        if create_checkpoint:
            io.echo("Creating git checkpoint...")
            checkpoint_hash = create_git_checkpoint(str(self.orchestrator.context.project_path))
            if checkpoint_hash:
                io.secho(f"Checkpoint created: {checkpoint_hash[:8]}", fg=io.theme.success)
            else:
                io.secho("Could not create checkpoint (not a git repo?)", fg=io.theme.warning)

        # Create config with verbose setting
        config = AgentConfig()
        config.verbose = verbose

        # Create agent with bridged io instance and cancellation token
        agent = CodeAgent(
            self.orchestrator,
            io=io,
            config=config,
            cancellation_token=self._cancellation_token
        )
        agent.dry_run = dry_run

        # Show agent configuration
        io.echo("\nAgent Configuration:")
        io.echo(f"  Planner (smart tasks): {agent.planner}")
        io.echo(f"  Executor (fast tasks): {agent.executor}")
        io.echo(f"  Project root: {agent.project_root}")
        if dry_run:
            io.secho("  Mode: DRY RUN (no actual changes)", fg=io.theme.warning)
        io.echo()

        # Run agent
        if dashboard:
            dashboard.set_state("executing", "Running code agent...")
            dashboard.update_thought_process(f"Executing task: {task}\n\nAgent analyzing requirements...")

        try:
            result = agent.run(task)

            if dashboard:
                dashboard.set_state("idle", "Task completed")

            io.echo("\n" + "=" * 60)
            if result['success']:
                io.secho("Task Completed Successfully!", fg=io.theme.success, bold=True)
            else:
                io.secho("Task Did Not Complete", fg=io.theme.warning, bold=True)

            # Audit log is auto-saved to .scrappy/audit.json
            audit_path = agent.project_root / ".scrappy" / "audit.json"
            if audit_path.exists():
                io.secho(f"Audit log: {audit_path}", fg=io.theme.primary)

            # Offer rollback if checkpoint was created
            if checkpoint_hash and not dry_run:
                if self._interaction.confirm("Rollback to checkpoint?", default=False):
                    if rollback_to_checkpoint(checkpoint_hash, str(agent.project_root)):
                        io.secho(f"Rolled back to {checkpoint_hash[:8]}", fg=io.theme.success)
                    else:
                        io.secho("Rollback failed", fg=io.theme.error)

            # Save agent task result to working memory
            self.orchestrator.working_memory.add_discovery(
                f"Agent task '{task[:50]}...': {'completed' if result['success'] else 'incomplete'} in {result['iterations']} iterations",
                "agent_task"
            )

        except KeyboardInterrupt:
            io.echo("\n\nAgent interrupted by user.")
            self.orchestrator.working_memory.add_discovery(
                f"Agent task '{task[:50]}...' interrupted by user",
                "agent_task"
            )
        except Exception as e:
            io.echo()  # Newline before error
            handle_error(e, io, context="agent execution")
            self.orchestrator.working_memory.add_discovery(
                f"Agent task '{task[:50]}...' failed: {str(e)[:50]}",
                "agent_task"
            )
        finally:
            # Clear cancellation token after run completes
            self._cancellation_token = None
            # Clear task progress widget
            output_sink = getattr(io, "output_sink", None)
            if output_sink is not None and hasattr(output_sink, "post_tasks_updated"):
                output_sink.post_tasks_updated([])
