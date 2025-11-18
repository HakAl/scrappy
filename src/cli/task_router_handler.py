"""
CLI handler for task-type aware routing.
"""

import click
from pathlib import Path
from typing import Optional

from ..task_router import TaskRouter, ClassifiedTask
from ..orchestrator import AgentOrchestrator


class CLITaskRouterHandler:
    """Handler for task-type aware execution in the CLI.

    This class provides automatic task routing based on classification, allowing
    tasks to be directed to the most appropriate execution path (direct command,
    code generation, research, or conversation). It maintains execution history
    and provides metrics tracking.

    Attributes:
        orchestrator: The AgentOrchestrator instance for task execution.
        project_root: Root directory of the project for context.
        auto_confirm: Whether to auto-confirm direct commands without prompting.
        router: The TaskRouter instance that performs classification and routing.
        history: List of routing history entries with input, result, and classification.
    """

    def __init__(
        self,
        orchestrator: AgentOrchestrator,
        project_root: Optional[Path] = None,
        auto_confirm: bool = False
    ) -> None:
        """Initialize CLI task router handler.

        Args:
            orchestrator: The AgentOrchestrator instance that will execute tasks.
            project_root: Root directory of the project. Defaults to current
                working directory if not provided.
            auto_confirm: If True, direct commands will execute without user
                confirmation. Defaults to False for safety.

        State Changes:
            - Sets instance attributes for orchestrator, project_root, auto_confirm
            - Creates a new TaskRouter instance with verbose=True
            - Initializes empty history list for tracking routing decisions
        """
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
        self.history: list = []

    def handle_auto_route(self, user_input: str):
        """Automatically route and execute user input.

        This is the main entry point for task-aware execution. It classifies
        the input, routes it to the appropriate handler, executes it, and
        displays the result.

        Args:
            user_input: The user's task description or command to execute.

        Returns:
            TaskResult object containing:
                - success: Whether execution succeeded
                - output: The result output text
                - error: Error message if failed
                - execution_time: Time taken in seconds
                - tokens_used: Number of tokens consumed
                - provider_used: Which provider handled the task
                - metadata: Additional info including classification

        Side Effects:
            - Executes the task via router.route() which may call external APIs,
              run shell commands, or perform other operations
            - Displays result to terminal via click
            - Appends entry to self.history with input, result, and classification
        """
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
        """Classify task without executing (preview mode).

        Analyzes and classifies the user input to show what routing decision
        would be made, without actually executing the task. Useful for
        understanding how the router interprets different inputs.

        Args:
            user_input: The user's task description to classify.

        Returns:
            ClassifiedTask object containing:
                - task_type: The classification (direct_command, code_generation,
                  research, conversation)
                - confidence: Classification confidence score (0-1)
                - complexity_score: Estimated task complexity (0-10)
                - reasoning: Explanation of classification decision
                - extracted_command: For direct commands, the extracted command
                - suggested_provider: Recommended provider for this task type
                - requires_planning: Whether task needs planning phase
                - requires_tools: Whether task needs tool access
                - matched_patterns: Patterns that influenced classification

        Side Effects:
            - Displays classification details to terminal via click
            - No state changes or task execution
        """
        click.secho("\nTask Classification Preview:", fg="cyan")

        classified = self.router.classify_only(user_input)
        self._display_classification(classified)

        return classified

    def handle_route_status(self) -> None:
        """Display router status and metrics.

        Shows aggregate statistics about task routing including total tasks,
        breakdown by type, average execution time, token usage, and success rate.

        Returns:
            None. Results are displayed via click.

        Side Effects:
            - Displays formatted metrics to terminal via click
            - No state changes
        """
        metrics = self.router.get_metrics()

        click.secho("\nTask Router Metrics:", fg="cyan", bold=True)
        click.echo(f"  Total tasks: {metrics.total_tasks}")

        if metrics.tasks_by_type:
            click.echo("  Tasks by type:")
            for task_type, count in metrics.tasks_by_type.items():
                click.echo(f"    - {task_type}: {count}")

        click.echo(f"  Avg execution time: {metrics.avg_execution_time:.2f}s")
        click.echo(f"  Total tokens used: {metrics.total_tokens_used}")
        click.echo(f"  Success rate: {metrics.success_rate:.1%}")

    def handle_route_history(self) -> None:
        """Display routing history.

        Shows the last 10 routing decisions with input preview, task type,
        success status, and execution time for each.

        Returns:
            None. Results are displayed via click.

        Side Effects:
            - Displays formatted history to terminal via click
            - No state changes
        """
        if not self.history:
            click.secho("No routing history yet.", fg="yellow")
            return

        click.secho("\nRouting History:", fg="cyan", bold=True)

        for i, entry in enumerate(self.history[-10:], 1):  # Last 10 entries
            classification = entry["classification"]
            result = entry["result"]

            click.echo(f"\n{i}. {entry['input'][:50]}...")
            click.echo(f"   Type: {classification.get('type', 'unknown')}")
            click.echo(f"   Success: {'Yes' if result.success else 'No'}")
            click.echo(f"   Time: {result.execution_time:.2f}s")

    def _display_result(self, result) -> None:
        """Display execution result to terminal.

        Formats and displays the task execution result including success/failure
        status, output content (truncated if long), execution time, token usage,
        and provider information.

        Args:
            result: TaskResult object containing execution results with attributes:
                - success: bool indicating if execution succeeded
                - error: Optional error message
                - output: Optional output text
                - execution_time: Time in seconds
                - tokens_used: Optional token count
                - provider_used: Optional provider name

        Returns:
            None. Output is displayed via click.

        Side Effects:
            - Displays formatted output to terminal via click
            - No state changes
        """
        if result.success:
            click.secho("\nExecution successful", fg="green", bold=True)
        else:
            click.secho("\nExecution failed", fg="red", bold=True)
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

    def _display_classification(self, classified: ClassifiedTask) -> None:
        """Display classification details to terminal.

        Formats and displays task classification information with color-coded
        task type and all relevant classification attributes.

        Args:
            classified: ClassifiedTask object containing:
                - task_type: TaskType enum value
                - confidence: float (0-1)
                - complexity_score: int (0-10)
                - reasoning: str explanation
                - extracted_command: Optional extracted command
                - suggested_provider: Optional provider suggestion
                - requires_planning: bool
                - requires_tools: bool
                - matched_patterns: List of pattern strings

        Returns:
            None. Output is displayed via click.

        Side Effects:
            - Displays formatted classification to terminal via click
            - No state changes
        """
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


def register_task_router_commands(cli_instance) -> CLITaskRouterHandler:
    """Register task router commands with CLI instance.

    Creates and attaches a CLITaskRouterHandler to the CLI instance if one
    doesn't already exist. This handler provides task-aware routing commands
    for automatic task classification and execution.

    Args:
        cli_instance: The CLI instance to register commands with. Must have
            an 'orchestrator' attribute.

    Returns:
        The CLITaskRouterHandler instance (newly created or existing).

    Side Effects:
        - If cli_instance doesn't have a task_router_handler attribute, creates
          a new CLITaskRouterHandler and attaches it as cli_instance.task_router_handler
        - Uses Path.cwd() as project_root for the handler

    Available Commands After Registration:
        - /auto <task>: Auto-route and execute task based on classification
        - /classify <task>: Preview classification without executing
        - /router-status: Show routing metrics and statistics
        - /router-history: Show recent routing history

    Example:
        >>> handler = register_task_router_commands(cli)
        >>> handler.handle_auto_route("list all Python files")
    """
    # Create handler if not exists
    if not hasattr(cli_instance, 'task_router_handler'):
        cli_instance.task_router_handler = CLITaskRouterHandler(
            orchestrator=cli_instance.orchestrator,
            project_root=Path.cwd()
        )

    return cli_instance.task_router_handler
