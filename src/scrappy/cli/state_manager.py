"""
State manager module for CLI.

Handles plan state, task tracking, and plan progression.
"""

import sys
from typing import Any, List, Optional, Tuple
from .io_interface import CLIIOProtocol


class PlanStateManager:
    """Manages plan state and task progression."""

    def __init__(self):
        """Initialize PlanStateManager with default state."""
        self.active_plan: List[Any] = []
        self.current_task_index: int = 0
        self.plan_active: bool = False
        self.auto_execute_tasks: bool = True

    def start_plan(self, steps: List[Any]) -> None:
        """
        Start a new plan with the given steps.

        Args:
            steps: List of plan steps (dicts or strings).
        """
        self.active_plan = steps
        self.current_task_index = 0
        self.plan_active = True

    def end_plan(self) -> None:
        """End the current plan while preserving data for summary."""
        self.plan_active = False

    def advance_task(self) -> bool:
        """
        Advance to the next task.

        Returns:
            True if more tasks remain, False if plan complete.
        """
        self.current_task_index += 1

        if self.current_task_index >= len(self.active_plan):
            self.plan_active = False
            return False

        return True

    def skip_task(self) -> None:
        """Skip the current task without marking it complete."""
        self.current_task_index += 1

        if self.current_task_index >= len(self.active_plan):
            self.plan_active = False

    def get_current_task(self) -> Optional[Any]:
        """
        Get the current task.

        Returns:
            Current task or None if no active plan.
        """
        if not self.plan_active or not self.active_plan:
            return None

        if self.current_task_index >= len(self.active_plan):
            return None

        return self.active_plan[self.current_task_index]

    def has_more_tasks(self) -> bool:
        """
        Check if there are more tasks remaining.

        Returns:
            True if more tasks exist, False otherwise.
        """
        if not self.active_plan:
            return False

        return self.current_task_index < len(self.active_plan)

    def get_progress(self) -> Tuple[int, int]:
        """
        Get progress counts.

        Returns:
            Tuple of (completed tasks, total tasks).
        """
        total = len(self.active_plan)
        completed = self.current_task_index

        return (completed, total)

    def get_progress_percentage(self) -> int:
        """
        Get progress as a percentage.

        Returns:
            Progress percentage (0-100).
        """
        if not self.active_plan:
            return 0

        total = len(self.active_plan)
        completed = self.current_task_index

        return int((completed / total) * 100)

    def show_current_task(self, io: CLIIOProtocol) -> None:
        """
        Display the current task being worked on.

        Args:
            io: The IO interface for output.
        """
        if not self.plan_active or not self.active_plan:
            return

        total = len(self.active_plan)
        current = self.current_task_index + 1

        io.secho("=" * 60, fg=io.theme.primary)
        io.secho(f"[{current}/{total}] ", fg=io.theme.primary, bold=True, nl=False)

        task = self.active_plan[self.current_task_index]
        if isinstance(task, dict):
            label = task.get('step') or task.get('description') or 'Task'
            io.secho(label, bold=True)
            if 'description' in task and 'step' in task:
                io.echo(f"    {task['description']}")
        else:
            io.secho(str(task), bold=True)

        io.secho("=" * 60, fg=io.theme.primary)
        io.echo()

    def show_plan_summary(self, io: CLIIOProtocol) -> None:
        """
        Show summary of plan progress.

        Args:
            io: The IO interface for output.
        """
        if not self.active_plan:
            return

        total = len(self.active_plan)
        completed = self.current_task_index

        io.echo()
        io.secho("Plan Summary:", fg=io.theme.primary, bold=True)
        io.echo(f"  Completed: {completed}/{total} tasks")

        # Progress bar
        progress = int((completed / total) * 20)
        bar = "#" * progress + "-" * (20 - progress)
        percentage = int((completed / total) * 100)
        io.echo(f"  Progress: [{bar}] {percentage}%")
        io.echo()

    def show_all_tasks(self, io: CLIIOProtocol) -> None:
        """
        Show all tasks with status markers.

        Args:
            io: The IO interface for output.
        """
        if not self.active_plan:
            return

        io.secho("\nCurrent Plan:", fg=io.theme.primary, bold=True)
        io.secho("-" * 50, fg=io.theme.primary)

        for i, task in enumerate(self.active_plan):
            if i < self.current_task_index:
                # Completed
                status = io.style("[x]", fg=io.theme.success)
            elif i == self.current_task_index:
                # Current
                status = io.style("->", fg=io.theme.warning, bold=True)
            else:
                # Pending
                status = io.style("o", fg="white")

            if isinstance(task, dict):
                task_name = task.get('step', task.get('description', 'Task'))
            else:
                task_name = str(task)

            io.echo(f"  {status} {i+1}. {task_name}")

        io.echo()
        self.show_plan_summary(io)

    def prompt_task_progression(self, io: CLIIOProtocol) -> bool:
        """
        Prompt user for next action after completing work.

        Args:
            io: The IO interface for input/output.

        Returns:
            True to continue loop, False if plan is finished.
        """
        if not self.plan_active:
            return True

        # Skip prompts if not in interactive mode
        if not sys.stdin.isatty():
            io.secho("Non-interactive mode: ending plan execution.", fg=io.theme.warning)
            self.plan_active = False
            return True

        io.echo()
        io.secho("What next?", fg=io.theme.primary, bold=True)
        io.echo("  1. Mark complete & continue")
        io.echo("  2. Stay on this task")
        io.echo("  3. Skip this task")
        io.echo("  4. Finish planning session")
        io.echo()

        try:
            choice = io.prompt("Choice", default="1", show_default=True).strip()
        except (EOFError, Exception):
            # Non-interactive or cancelled - end plan
            io.secho("\nEnding planning session...", fg=io.theme.warning)
            self.plan_active = False
            return True

        if choice == "1":
            # Mark complete and advance
            io.secho(f"[DONE] Task {self.current_task_index + 1} complete", fg=io.theme.success, bold=True)
            io.echo()

            self.current_task_index += 1
            if self.current_task_index >= len(self.active_plan):
                io.secho("All tasks complete!", fg=io.theme.success, bold=True)
                self.show_plan_summary(io)
                self.plan_active = False
                return True

            self.show_current_task(io)

        elif choice == "2":
            # Stay on current task
            io.secho("Continuing with current task...", fg=io.theme.warning)
            io.echo()

        elif choice == "3":
            # Skip task
            io.secho(f"Skipped task {self.current_task_index + 1}", fg=io.theme.warning)
            io.echo()

            self.current_task_index += 1
            if self.current_task_index >= len(self.active_plan):
                io.secho("Plan complete (some tasks skipped)", fg=io.theme.warning, bold=True)
                self.show_plan_summary(io)
                self.plan_active = False
                return True

            self.show_current_task(io)

        elif choice == "4":
            # End planning session
            io.secho("Ending planning session...", fg=io.theme.warning)
            self.show_plan_summary(io)
            self.plan_active = False

        return True

    def get_task_description(self) -> str:
        """
        Get description of current task for execution.

        Returns:
            Task description string or empty string if no plan.
        """
        if not self.plan_active or not self.active_plan:
            return ""

        if self.current_task_index >= len(self.active_plan):
            return ""

        task = self.active_plan[self.current_task_index]

        if isinstance(task, dict):
            task_name = task.get('step', 'Task')
            task_desc = task.get('description', task_name)
            return f"{task_name}: {task_desc}"
        else:
            return str(task)
