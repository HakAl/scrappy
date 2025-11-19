"""
Task execution functionality for the CLI.
Handles planning and reasoning operations.
"""

from typing import Optional

from .io_interface import CLIIOProtocol
from .rich_output import RichIO


class CLITaskExecution:
    """Handles task planning and reasoning operations."""

    def __init__(self, orchestrator):
        """Initialize task executor.

        Args:
            orchestrator: The AgentOrchestrator instance
        """
        self.orchestrator = orchestrator

    def plan_task(self, task: str, io: Optional[CLIIOProtocol] = None):
        """
        Create a task plan.

        Generates a structured plan with steps for the given task using the
        orchestrator's planning capability. Returns the steps for tracking.

        Args:
            task: Description of the task to plan.
            io: I/O interface for output. If None, uses ClickIO.

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
        if io is None:
            io = RichIO()

        io.secho(f"\nPlanning: {task}", bold=True)
        io.echo("-" * 50)

        with io.progress(total=1, description="Generating plan") as progress:
            try:
                steps = self.orchestrator.plan(task)
                progress.advance(1)
            except Exception as e:
                progress.advance(1)
                io.secho(f"Error during planning: {e}", fg="red")
                return []

        io.echo()
        plan_summary = ""
        if isinstance(steps, list):
            for i, step in enumerate(steps, 1):
                if isinstance(step, dict):
                    io.secho(f"{i}. {step.get('step', 'Step')}", bold=True)
                    io.echo(f"   {step.get('description', '')}")
                    if 'provider_type' in step:
                        io.secho(f"   [Recommended: {step['provider_type']}]", fg="cyan")
                    plan_summary += f"{i}. {step.get('step', 'Step')}\n"
                else:
                    io.echo(f"{i}. {step}")
                    plan_summary += f"{i}. {step}\n"
                io.echo()
        else:
            io.echo(steps)
            plan_summary = str(steps)
            steps = [steps]  # Convert to list for tracking

        # Save plan to working memory
        self.orchestrator.working_memory.add_discovery(
            f"Created plan for '{task}' with {len(steps) if isinstance(steps, list) else 1} steps",
            "task_plan"
        )

        return steps if isinstance(steps, list) else []

    def reason(self, question: str, io: Optional[CLIIOProtocol] = None):
        """
        Perform reasoning on a question.

        Uses the orchestrator's reasoning capability to analyze a question
        and provide a structured response with analysis, conclusion, and
        confidence level.

        Args:
            question: The question to reason about.
            io: I/O interface for output. If None, uses ClickIO.

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
        if io is None:
            io = RichIO()

        io.secho(f"\nReasoning about: {question}", bold=True)
        io.echo("-" * 50)

        with io.progress(total=1, description="Analyzing") as progress:
            try:
                response = self.orchestrator.reason(question)
                progress.advance(1)
            except Exception as e:
                progress.advance(1)
                io.secho(f"Error during reasoning: {e}", fg="red")
                return

        io.echo()
        conclusion = ""
        if isinstance(response, dict):
            io.echo(f"Question: {response.get('question', question)}")
            io.secho(f"\nAnalysis:", bold=True)
            io.echo(response.get('analysis', ''))
            io.secho(f"\nConclusion: ", bold=True, nl=False)
            conclusion = response.get('conclusion', '')
            io.echo(conclusion)
            io.echo(f"Confidence: {response.get('confidence', 'N/A')}")
        else:
            io.echo(response)
            conclusion = str(response)[:200]

        # Save reasoning result to working memory
        self.orchestrator.working_memory.add_discovery(
            f"Reasoning on '{question[:50]}...': {conclusion[:100]}...",
            "reasoning"
        )
