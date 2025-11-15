"""
Code agent management for the CLI.
Handles running and managing code execution agents with human approval.
"""

import click

try:
    from ..agent import CodeAgent, create_git_checkpoint, rollback_to_checkpoint
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agent import CodeAgent, create_git_checkpoint, rollback_to_checkpoint


class CLIAgentManager:
    """Manages code agent execution with human-in-the-loop approval."""

    def __init__(self, orchestrator):
        """Initialize agent manager.

        Args:
            orchestrator: The AgentOrchestrator instance
        """
        self.orchestrator = orchestrator

    def run_agent(self, task: str):
        """Run the code agent on a task with human-in-the-loop approval."""
        click.secho(f"\nCode Agent - Task: {task}", bold=True)
        click.echo("-" * 60)

        # Safety options
        dry_run = click.confirm("Run in dry-run mode? (no actual changes)", default=False)
        create_checkpoint = click.confirm("Create git checkpoint before running?", default=True)

        checkpoint_hash = None
        if create_checkpoint:
            click.echo("Creating git checkpoint...")
            checkpoint_hash = create_git_checkpoint(str(self.orchestrator.context.project_path))
            if checkpoint_hash:
                click.secho(f"Checkpoint created: {checkpoint_hash[:8]}", fg="green")
            else:
                click.secho("Could not create checkpoint (not a git repo?)", fg="yellow")

        # Create agent
        agent = CodeAgent(self.orchestrator)
        agent.dry_run = dry_run

        # Show agent configuration
        click.echo(f"\nAgent Configuration:")
        click.echo(f"  Planner (smart tasks): {agent.planner}")
        click.echo(f"  Executor (fast tasks): {agent.executor}")
        click.echo(f"  Project root: {agent.project_root}")
        if dry_run:
            click.secho("  Mode: DRY RUN (no actual changes)", fg="yellow")
        click.echo()

        if not click.confirm("Start agent?", default=True):
            click.echo("Agent cancelled.")
            return

        # Run agent
        try:
            result = agent.run(task)

            click.echo("\n" + "=" * 60)
            if result['success']:
                click.secho("Task Completed Successfully!", fg="green", bold=True)
            else:
                click.secho("Task Did Not Complete", fg="yellow", bold=True)

            click.echo(f"Result: {result['result']}")
            click.echo(f"Iterations: {result['iterations']}")

            # Show audit log summary
            if result['audit_log']:
                click.secho("\nAudit Log:", bold=True)
                for entry in result['audit_log']:
                    approved = click.style("Approved", fg="green") if entry['approved'] else click.style("Denied", fg="red")
                    click.echo(f"  [{entry['timestamp'][:19]}] {entry['action']} - {approved}")

            # Offer to save audit log
            if click.confirm("\nSave audit log to file?", default=False):
                log_path = agent.save_audit_log()
                click.secho(f"Saved to: {log_path}", fg="green")

            # Offer rollback if checkpoint was created
            if checkpoint_hash and not dry_run:
                if click.confirm("\nRollback to checkpoint?", default=False):
                    if rollback_to_checkpoint(checkpoint_hash, str(agent.project_root)):
                        click.secho(f"Rolled back to {checkpoint_hash[:8]}", fg="green")
                    else:
                        click.secho("Rollback failed", fg="red")

            # Save agent task result to working memory
            self.orchestrator.add_discovery(
                f"Agent task '{task[:50]}...': {'completed' if result['success'] else 'incomplete'} in {result['iterations']} iterations",
                "agent_task"
            )

        except KeyboardInterrupt:
            click.echo("\n\nAgent interrupted by user.")
            self.orchestrator.add_discovery(
                f"Agent task '{task[:50]}...' interrupted by user",
                "agent_task"
            )
        except Exception as e:
            click.secho(f"\nAgent error: {e}", fg="red")
            self.orchestrator.add_discovery(
                f"Agent task '{task[:50]}...' failed: {str(e)[:50]}",
                "agent_task"
            )
