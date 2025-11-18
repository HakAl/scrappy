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
        """
        Create a task plan.

        Generates a structured plan with steps for the given task using the
        orchestrator's planning capability. Returns the steps for tracking.

        Args:
            task: Description of the task to plan.

        Returns:
            list: List of plan steps (dicts with 'step', 'description', etc.)
                or empty list on error. Each step may contain:
                - step: Step name/title
                - description: Detailed description
                - provider_type: Recommended provider for execution

        Side Effects:
            - Displays "Planning: {task}" header to console
            - Shows progress bar during plan generation
            - Displays formatted plan with numbered steps to console
            - Displays recommended provider for each step if available
            - Adds discovery to orchestrator's working memory

        State Changes:
            - Updates orchestrator.discoveries with plan summary

        Raises:
            Does not raise; catches exceptions internally and displays error.
        """
        click.secho(f"\nPlanning: {task}", bold=True)
        click.echo("-" * 50)

        with click.progressbar(length=1, label="Generating plan") as bar:
            try:
                steps = self.orchestrator.plan(task)
                bar.update(1)
            except Exception as e:
                bar.update(1)
                click.secho(f"Error during planning: {e}", fg="red")
                return []

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
            steps = [steps]  # Convert to list for tracking

        # Save plan to working memory
        self.orchestrator.add_discovery(
            f"Created plan for '{task}' with {len(steps) if isinstance(steps, list) else 1} steps",
            "task_plan"
        )

        return steps if isinstance(steps, list) else []

    def reason(self, question: str):
        """
        Perform reasoning on a question.

        Uses the orchestrator's reasoning capability to analyze a question
        and provide a structured response with analysis, conclusion, and
        confidence level.

        Args:
            question: The question to reason about.

        Returns:
            None (displays results to console).

        Side Effects:
            - Displays "Reasoning about: {question}" header to console
            - Shows progress bar during analysis
            - Displays structured response with:
              - Question
              - Analysis
              - Conclusion
              - Confidence level
            - Adds discovery to orchestrator's working memory with
              truncated question and conclusion

        State Changes:
            - Updates orchestrator.discoveries with reasoning result

        Raises:
            Does not raise; catches exceptions internally and displays error.
        """
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
