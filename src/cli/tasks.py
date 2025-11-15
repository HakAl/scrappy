"""
Task execution functionality for the CLI.
Handles planning and reasoning operations.
"""

import click


class CLITaskExecution:
    """Handles task planning and reasoning operations."""

    def __init__(self, orchestrator):
        """Initialize task executor.

        Args:
            orchestrator: The AgentOrchestrator instance
        """
        self.orchestrator = orchestrator

    def plan_task(self, task: str):
        """Create a task plan."""
        click.secho(f"\nPlanning: {task}", bold=True)
        click.echo("-" * 50)

        with click.progressbar(length=1, label="Generating plan") as bar:
            try:
                steps = self.orchestrator.plan(task)
                bar.update(1)
            except Exception as e:
                bar.update(1)
                click.secho(f"Error during planning: {e}", fg="red")
                return

        click.echo()
        plan_summary = ""
        if isinstance(steps, list):
            for i, step in enumerate(steps, 1):
                if isinstance(step, dict):
                    click.secho(f"{i}. {step.get('step', 'Step')}", bold=True)
                    click.echo(f"   {step.get('description', '')}")
                    if 'provider_type' in step:
                        click.secho(f"   [Recommended: {step['provider_type']}]", fg="cyan")
                    plan_summary += f"{i}. {step.get('step', 'Step')}\n"
                else:
                    click.echo(f"{i}. {step}")
                    plan_summary += f"{i}. {step}\n"
                click.echo()
        else:
            click.echo(steps)
            plan_summary = str(steps)

        # Save plan to working memory
        self.orchestrator.add_discovery(
            f"Created plan for '{task}' with {len(steps) if isinstance(steps, list) else 1} steps",
            "task_plan"
        )

    def reason(self, question: str):
        """Perform reasoning on a question."""
        click.secho(f"\nReasoning about: {question}", bold=True)
        click.echo("-" * 50)

        with click.progressbar(length=1, label="Analyzing") as bar:
            try:
                response = self.orchestrator.reason(question)
                bar.update(1)
            except Exception as e:
                bar.update(1)
                click.secho(f"Error during reasoning: {e}", fg="red")
                return

        click.echo()
        conclusion = ""
        if isinstance(response, dict):
            click.echo(f"Question: {response.get('question', question)}")
            click.secho(f"\nAnalysis:", bold=True)
            click.echo(response.get('analysis', ''))
            click.secho(f"\nConclusion: ", bold=True, nl=False)
            conclusion = response.get('conclusion', '')
            click.echo(conclusion)
            click.echo(f"Confidence: {response.get('confidence', 'N/A')}")
        else:
            click.echo(response)
            conclusion = str(response)[:200]

        # Save reasoning result to working memory
        self.orchestrator.add_discovery(
            f"Reasoning on '{question[:50]}...': {conclusion[:100]}...",
            "reasoning"
        )
