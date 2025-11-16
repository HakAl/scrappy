"""
CLI handler for task-type aware routing.
"""

import click
from pathlib import Path
from typing import Optional

from ..task_router import TaskRouter, ClassifiedTask
from ..orchestrator import AgentOrchestrator


class CLITaskRouterHandler:
    """
    Handler for task-type aware execution in the CLI.

    Provides automatic routing based on task classification.
    """

    def __init__(
        self,
        orchestrator: AgentOrchestrator,
        project_root: Optional[Path] = None,
        auto_confirm: bool = False
    ):
        self.orchestrator = orchestrator
        self.project_root = project_root or Path.cwd()
        self.auto_confirm = auto_confirm

        # Initialize router
        self.router = TaskRouter(
            orchestrator=orchestrator,
            project_root=self.project_root,
            auto_confirm_direct=auto_confirm,
            verbose=True
        )

        # Track routing history
        self.history = []

    def handle_auto_route(self, user_input: str):
        """
        Automatically route and execute user input.

        This is the main entry point for task-aware execution.
        """
        click.secho("\n🔄 Auto-routing task...", fg="cyan")

        result = self.router.route(user_input)

        # Display result
        self._display_result(result)

        # Track in history
        self.history.append({
            "input": user_input,
            "result": result,
            "classification": result.metadata.get("classification", {})
        })

        return result

    def handle_classify_only(self, user_input: str):
        """Classify task without executing (preview mode)."""
        click.secho("\n🔍 Task Classification Preview:", fg="cyan")

        classified = self.router.classify_only(user_input)
        self._display_classification(classified)

        return classified

    def handle_route_status(self):
        """Display router status and metrics."""
        metrics = self.router.get_metrics()

        click.secho("\n📊 Task Router Metrics:", fg="cyan", bold=True)
        click.echo(f"  Total tasks: {metrics.total_tasks}")

        if metrics.tasks_by_type:
            click.echo("  Tasks by type:")
            for task_type, count in metrics.tasks_by_type.items():
                click.echo(f"    - {task_type}: {count}")

        click.echo(f"  Avg execution time: {metrics.avg_execution_time:.2f}s")
        click.echo(f"  Total tokens used: {metrics.total_tokens_used}")
        click.echo(f"  Success rate: {metrics.success_rate:.1%}")

    def handle_route_history(self):
        """Display routing history."""
        if not self.history:
            click.secho("No routing history yet.", fg="yellow")
            return

        click.secho("\n📜 Routing History:", fg="cyan", bold=True)

        for i, entry in enumerate(self.history[-10:], 1):  # Last 10 entries
            classification = entry["classification"]
            result = entry["result"]

            click.echo(f"\n{i}. {entry['input'][:50]}...")
            click.echo(f"   Type: {classification.get('type', 'unknown')}")
            click.echo(f"   Success: {'✅' if result.success else '❌'}")
            click.echo(f"   Time: {result.execution_time:.2f}s")

    def _display_result(self, result):
        """Display execution result."""
        if result.success:
            click.secho("\n✅ Execution successful", fg="green", bold=True)
        else:
            click.secho("\n❌ Execution failed", fg="red", bold=True)
            if result.error:
                click.secho(f"Error: {result.error}", fg="red")

        # Show output
        if result.output:
            click.echo("\nOutput:")
            click.echo("-" * 40)
            # Truncate long output
            output = result.output
            if len(output) > 2000:
                output = output[:2000] + "\n... (truncated)"
            click.echo(output)
            click.echo("-" * 40)

        # Show metadata
        click.secho(f"\nExecution time: {result.execution_time:.2f}s", fg="cyan")
        if result.tokens_used:
            click.echo(f"Tokens used: {result.tokens_used}")
        if result.provider_used:
            click.echo(f"Provider: {result.provider_used}")

    def _display_classification(self, classified: ClassifiedTask):
        """Display classification details."""
        type_colors = {
            "direct_command": "green",
            "code_generation": "yellow",
            "research": "cyan",
            "conversation": "blue"
        }

        color = type_colors.get(classified.task_type.value, "white")

        click.echo(f"\n  Task Type: {click.style(classified.task_type.value, fg=color, bold=True)}")
        click.echo(f"  Confidence: {classified.confidence:.2f}")
        click.echo(f"  Complexity: {classified.complexity_score}/10")
        click.echo(f"  Reasoning: {classified.reasoning}")

        if classified.extracted_command:
            click.echo(f"  Extracted command: {classified.extracted_command}")

        if classified.suggested_provider:
            click.echo(f"  Suggested provider: {classified.suggested_provider}")

        click.echo(f"  Requires planning: {'Yes' if classified.requires_planning else 'No'}")
        click.echo(f"  Requires tools: {'Yes' if classified.requires_tools else 'No'}")

        if classified.matched_patterns:
            click.echo(f"  Matched patterns: {', '.join(classified.matched_patterns[:5])}")


def register_task_router_commands(cli_instance):
    """
    Register task router commands with CLI.

    Commands:
    - /auto <task> - Auto-route and execute
    - /classify <task> - Preview classification
    - /router-status - Show metrics
    - /router-history - Show history
    """

    # Create handler if not exists
    if not hasattr(cli_instance, 'task_router_handler'):
        cli_instance.task_router_handler = CLITaskRouterHandler(
            orchestrator=cli_instance.orchestrator,
            project_root=Path.cwd()
        )

    return cli_instance.task_router_handler
