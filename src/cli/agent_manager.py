"""
Code agent management for the CLI.
Handles running and managing code execution agents with human approval.
"""

from ..agent import CodeAgent, create_git_checkpoint, rollback_to_checkpoint
from .io_interface import CLIIOProtocol
from .display_manager import DisplayManager


class CLIAgentManager:
    """Manages code agent execution with human-in-the-loop approval."""

    def __init__(self, orchestrator, io: CLIIOProtocol):
        """Initialize agent manager.

        Args:
            orchestrator: The AgentOrchestrator instance
            io: I/O interface for output
        """
        self.orchestrator = orchestrator
        self.display = DisplayManager(io=io, dashboard_enabled=False)

    def run_agent(self, task: str):
        """
        Run the code agent on a task with human-in-the-loop approval.

        Creates and executes a CodeAgent for the given task, with interactive
        prompts for safety options like dry-run mode and git checkpoints.

        Args:
            task: Description of the task for the agent to perform.

        Side Effects:
            - Prompts user for dry-run mode and checkpoint creation
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
        io = self.display.get_io()
        dashboard = self.display.get_dashboard()

        io.secho(f"\nCode Agent - Task: {task}", bold=True)
        io.echo("-" * 60)

        # Update dashboard if enabled
        if dashboard:
            dashboard.set_state("idle", "Awaiting user input")
            dashboard.update_thought_process(f"Task: {task}")

        # Safety options
        dry_run = io.confirm("Run in dry-run mode? (no actual changes)", default=False)
        create_checkpoint = io.confirm("Create git checkpoint before running?", default=True)

        checkpoint_hash = None
        if create_checkpoint:
            io.echo("Creating git checkpoint...")
            checkpoint_hash = create_git_checkpoint(str(self.orchestrator.context.project_path))
            if checkpoint_hash:
                io.secho(f"Checkpoint created: {checkpoint_hash[:8]}", fg="green")
            else:
                io.secho("Could not create checkpoint (not a git repo?)", fg="yellow")

        # Create agent
        agent = CodeAgent(self.orchestrator)
        agent.dry_run = dry_run

        # Show agent configuration
        io.echo(f"\nAgent Configuration:")
        io.echo(f"  Planner (smart tasks): {agent.planner}")
        io.echo(f"  Executor (fast tasks): {agent.executor}")
        io.echo(f"  Project root: {agent.project_root}")
        if dry_run:
            io.secho("  Mode: DRY RUN (no actual changes)", fg="yellow")
        io.echo()

        if not io.confirm("Start agent?", default=True):
            io.echo("Agent cancelled.")
            return

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
                io.secho("Task Completed Successfully!", fg="green", bold=True)
            else:
                io.secho("Task Did Not Complete", fg="yellow", bold=True)

            io.echo(f"Result: {result['result']}")
            io.echo(f"Iterations: {result['iterations']}")

            # Show audit log summary
            if result['audit_log']:
                io.secho("\nAudit Log:", bold=True)
                for entry in result['audit_log']:
                    approved = io.style("Approved", fg="green") if entry['approved'] else io.style("Denied", fg="red")
                    io.echo(f"  [{entry['timestamp'][:19]}] {entry['action']} - {approved}")

            # Offer to save audit log
            if io.confirm("\nSave audit log to file?", default=False):
                log_path = agent.save_audit_log()
                io.secho(f"Saved to: {log_path}", fg="green")

            # Offer rollback if checkpoint was created
            if checkpoint_hash and not dry_run:
                if io.confirm("\nRollback to checkpoint?", default=False):
                    if rollback_to_checkpoint(checkpoint_hash, str(agent.project_root)):
                        io.secho(f"Rolled back to {checkpoint_hash[:8]}", fg="green")
                    else:
                        io.secho("Rollback failed", fg="red")

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
            io.secho(f"\nAgent error: {e}", fg="red")
            self.orchestrator.working_memory.add_discovery(
                f"Agent task '{task[:50]}...' failed: {str(e)[:50]}",
                "agent_task"
            )
