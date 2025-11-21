"""
Tests for CLI state manager module.

TDD: Tests written first for the state_manager.py module which handles
plan state, task tracking, and plan progression.
"""

import pytest
from unittest.mock import MagicMock, patch
from tests.helpers import MockIO, ConfigurableTestOrchestrator


class TestPlanStateManager:
    """Tests for PlanStateManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.state_manager import PlanStateManager
        self.PlanStateManager = PlanStateManager
        self.orchestrator = ConfigurableTestOrchestrator()

    # =========================================================================
    # Initialization Tests
    # =========================================================================

    def test_initializes_with_empty_plan(self):
        """Should initialize with empty plan."""
        manager = self.PlanStateManager()

        assert manager.active_plan == []
        assert manager.current_task_index == 0
        assert manager.plan_active is False

    def test_initializes_auto_execute_enabled(self):
        """Should initialize with auto_execute enabled."""
        manager = self.PlanStateManager()

        assert manager.auto_execute_tasks is True

    # =========================================================================
    # Plan Activation Tests
    # =========================================================================

    def test_start_plan_activates_plan(self):
        """Should activate plan when start_plan called."""
        manager = self.PlanStateManager()
        steps = [
            {'step': 'Task 1', 'description': 'First task'},
            {'step': 'Task 2', 'description': 'Second task'}
        ]

        manager.start_plan(steps)

        assert manager.plan_active is True
        assert manager.active_plan == steps
        assert manager.current_task_index == 0

    def test_start_plan_resets_index(self):
        """Should reset task index when starting new plan."""
        manager = self.PlanStateManager()
        manager.current_task_index = 5

        manager.start_plan([{'step': 'Task 1'}])

        assert manager.current_task_index == 0

    def test_end_plan_deactivates_plan(self):
        """Should deactivate plan when end_plan called."""
        manager = self.PlanStateManager()
        manager.start_plan([{'step': 'Task 1'}])

        manager.end_plan()

        assert manager.plan_active is False

    def test_end_plan_preserves_plan_data(self):
        """Should preserve plan data after ending for summary."""
        manager = self.PlanStateManager()
        steps = [{'step': 'Task 1'}]
        manager.start_plan(steps)

        manager.end_plan()

        assert manager.active_plan == steps

    # =========================================================================
    # Task Progression Tests
    # =========================================================================

    def test_advance_task_increments_index(self):
        """Should increment task index when advancing."""
        manager = self.PlanStateManager()
        manager.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'}
        ])

        manager.advance_task()

        assert manager.current_task_index == 1

    def test_advance_task_returns_true_when_more_tasks(self):
        """Should return True when more tasks remain."""
        manager = self.PlanStateManager()
        manager.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'}
        ])

        result = manager.advance_task()

        assert result is True

    def test_advance_task_returns_false_when_complete(self):
        """Should return False when all tasks complete."""
        manager = self.PlanStateManager()
        manager.start_plan([{'step': 'Task 1'}])

        result = manager.advance_task()

        assert result is False

    def test_advance_task_deactivates_plan_when_complete(self):
        """Should deactivate plan when last task advanced."""
        manager = self.PlanStateManager()
        manager.start_plan([{'step': 'Task 1'}])

        manager.advance_task()

        assert manager.plan_active is False

    def test_skip_task_advances_without_marking_complete(self):
        """Should advance to next task without completion."""
        manager = self.PlanStateManager()
        manager.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'}
        ])

        manager.skip_task()

        assert manager.current_task_index == 1

    def test_get_current_task_returns_task(self):
        """Should return current task."""
        manager = self.PlanStateManager()
        task = {'step': 'Task 1', 'description': 'First'}
        manager.start_plan([task])

        result = manager.get_current_task()

        assert result == task

    def test_get_current_task_returns_none_when_no_plan(self):
        """Should return None when no active plan."""
        manager = self.PlanStateManager()

        result = manager.get_current_task()

        assert result is None

    def test_has_more_tasks_true(self):
        """Should return True when more tasks exist."""
        manager = self.PlanStateManager()
        manager.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'}
        ])

        assert manager.has_more_tasks() is True

    def test_has_more_tasks_false(self):
        """Should return False when at last task."""
        manager = self.PlanStateManager()
        manager.start_plan([{'step': 'Task 1'}])
        manager.current_task_index = 0

        # After advancing past last task
        manager.advance_task()

        assert manager.has_more_tasks() is False

    # =========================================================================
    # Plan Progress Tests
    # =========================================================================

    def test_get_progress_returns_counts(self):
        """Should return completed and total counts."""
        manager = self.PlanStateManager()
        manager.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'},
            {'step': 'Task 3'}
        ])
        manager.current_task_index = 2

        completed, total = manager.get_progress()

        assert completed == 2
        assert total == 3

    def test_get_progress_percentage(self):
        """Should return progress percentage."""
        manager = self.PlanStateManager()
        manager.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'}
        ])
        manager.current_task_index = 1

        percentage = manager.get_progress_percentage()

        assert percentage == 50

    def test_get_progress_percentage_zero_when_empty(self):
        """Should return 0 when no tasks."""
        manager = self.PlanStateManager()

        percentage = manager.get_progress_percentage()

        assert percentage == 0


class TestPlanStateManagerDisplay:
    """Tests for PlanStateManager display methods."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.state_manager import PlanStateManager
        self.PlanStateManager = PlanStateManager

    def test_show_current_task_outputs_task(self):
        """Should output current task through io."""
        io = MockIO()
        manager = self.PlanStateManager()
        manager.start_plan([
            {'step': 'Task 1', 'description': 'First task'}
        ])

        manager.show_current_task(io)

        output = io.get_output()
        assert "1/1" in output
        assert "Task 1" in output

    def test_show_current_task_includes_description(self):
        """Should include task description in output."""
        io = MockIO()
        manager = self.PlanStateManager()
        manager.start_plan([
            {'step': 'Task 1', 'description': 'Do something important'}
        ])

        manager.show_current_task(io)

        output = io.get_output()
        assert "Do something important" in output

    def test_show_current_task_handles_string_tasks(self):
        """Should handle plain string tasks."""
        io = MockIO()
        manager = self.PlanStateManager()
        manager.start_plan(["Simple task string"])

        manager.show_current_task(io)

        output = io.get_output()
        assert "Simple task string" in output

    def test_show_current_task_no_output_when_inactive(self):
        """Should output nothing when plan inactive."""
        io = MockIO()
        manager = self.PlanStateManager()

        manager.show_current_task(io)

        output = io.get_output()
        assert output.strip() == ""

    def test_show_plan_summary_outputs_progress(self):
        """Should output plan progress summary."""
        io = MockIO()
        manager = self.PlanStateManager()
        manager.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'},
            {'step': 'Task 3'}
        ])
        manager.current_task_index = 2

        manager.show_plan_summary(io)

        output = io.get_output()
        assert "Plan Summary" in output
        assert "2/3" in output

    def test_show_plan_summary_shows_progress_bar(self):
        """Should show progress bar in summary."""
        io = MockIO()
        manager = self.PlanStateManager()
        manager.start_plan([{'step': 'Task 1'}] * 10)
        manager.current_task_index = 5

        manager.show_plan_summary(io)

        output = io.get_output()
        assert "%" in output
        assert "#" in output or "-" in output

    def test_show_plan_summary_no_output_when_empty(self):
        """Should output nothing when no plan."""
        io = MockIO()
        manager = self.PlanStateManager()

        manager.show_plan_summary(io)

        output = io.get_output()
        assert output.strip() == ""

    def test_show_all_tasks_outputs_task_list(self):
        """Should output all tasks with status markers."""
        io = MockIO()
        manager = self.PlanStateManager()
        manager.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'},
            {'step': 'Task 3'}
        ])
        manager.current_task_index = 1

        manager.show_all_tasks(io)

        output = io.get_output()
        assert "Task 1" in output
        assert "Task 2" in output
        assert "Task 3" in output


class TestPlanStateManagerProgression:
    """Tests for task progression prompting."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.state_manager import PlanStateManager
        self.PlanStateManager = PlanStateManager

    def test_prompt_task_progression_shows_options(self):
        """Should show progression options."""
        io = MockIO(inputs=["4"])  # Finish planning
        manager = self.PlanStateManager()
        manager.start_plan([{'step': 'Task 1'}])

        with patch('sys.stdin.isatty', return_value=True):
            manager.prompt_task_progression(io)

        output = io.get_output()
        assert "What next?" in output
        assert "Mark complete" in output
        assert "Stay on this task" in output
        assert "Skip" in output
        assert "Finish" in output

    def test_prompt_task_progression_mark_complete(self):
        """Should advance task on choice 1."""
        io = MockIO(inputs=["1"])
        manager = self.PlanStateManager()
        manager.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'}
        ])
        manager.auto_execute_tasks = False

        with patch('sys.stdin.isatty', return_value=True):
            manager.prompt_task_progression(io)

        assert manager.current_task_index == 1
        output = io.get_output()
        assert "DONE" in output or "complete" in output.lower()

    def test_prompt_task_progression_stay_on_task(self):
        """Should stay on current task on choice 2."""
        io = MockIO(inputs=["2"])
        manager = self.PlanStateManager()
        manager.start_plan([{'step': 'Task 1'}])

        with patch('sys.stdin.isatty', return_value=True):
            manager.prompt_task_progression(io)

        assert manager.current_task_index == 0
        assert manager.plan_active is True

    def test_prompt_task_progression_skip_task(self):
        """Should skip to next task on choice 3."""
        io = MockIO(inputs=["3"])
        manager = self.PlanStateManager()
        manager.start_plan([
            {'step': 'Task 1'},
            {'step': 'Task 2'}
        ])
        manager.auto_execute_tasks = False

        with patch('sys.stdin.isatty', return_value=True):
            manager.prompt_task_progression(io)

        assert manager.current_task_index == 1
        output = io.get_output()
        assert "Skipped" in output

    def test_prompt_task_progression_finish_planning(self):
        """Should end plan on choice 4."""
        io = MockIO(inputs=["4"])
        manager = self.PlanStateManager()
        manager.start_plan([{'step': 'Task 1'}])

        with patch('sys.stdin.isatty', return_value=True):
            manager.prompt_task_progression(io)

        assert manager.plan_active is False
        output = io.get_output()
        assert "Ending" in output

    def test_prompt_task_progression_returns_true_to_continue(self):
        """Should return True to continue main loop."""
        io = MockIO(inputs=["2"])  # Stay on task
        manager = self.PlanStateManager()
        manager.start_plan([{'step': 'Task 1'}])

        with patch('sys.stdin.isatty', return_value=True):
            result = manager.prompt_task_progression(io)

        assert result is True

    def test_prompt_task_progression_all_complete_message(self):
        """Should show completion message when all tasks done."""
        io = MockIO(inputs=["1"])
        manager = self.PlanStateManager()
        manager.start_plan([{'step': 'Task 1'}])
        manager.auto_execute_tasks = False

        with patch('sys.stdin.isatty', return_value=True):
            manager.prompt_task_progression(io)

        output = io.get_output()
        assert "All tasks complete" in output or "complete" in output.lower()

    def test_prompt_task_progression_non_interactive_ends_plan(self):
        """Should end plan in non-interactive mode."""
        io = MockIO()
        manager = self.PlanStateManager()
        manager.start_plan([{'step': 'Task 1'}])

        with patch('sys.stdin.isatty', return_value=False):
            manager.prompt_task_progression(io)

        assert manager.plan_active is False

    def test_prompt_task_progression_handles_eof(self):
        """Should handle EOF gracefully."""
        io = MockIO(inputs=[])  # No inputs will cause exception
        io.prompt = lambda *args, **kwargs: (_ for _ in ()).throw(EOFError())
        manager = self.PlanStateManager()
        manager.start_plan([{'step': 'Task 1'}])

        with patch('sys.stdin.isatty', return_value=True):
            manager.prompt_task_progression(io)

        assert manager.plan_active is False


class TestPlanStateManagerTaskExecution:
    """Tests for task execution functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        from src.cli.state_manager import PlanStateManager
        self.PlanStateManager = PlanStateManager

    def test_get_task_description_from_dict(self):
        """Should extract description from dict task."""
        manager = self.PlanStateManager()
        manager.start_plan([
            {'step': 'Task Name', 'description': 'Task details'}
        ])

        desc = manager.get_task_description()

        assert "Task Name" in desc
        assert "Task details" in desc

    def test_get_task_description_from_string(self):
        """Should return string task as description."""
        manager = self.PlanStateManager()
        manager.start_plan(["Simple string task"])

        desc = manager.get_task_description()

        assert desc == "Simple string task"

    def test_get_task_description_empty_when_no_plan(self):
        """Should return empty string when no plan."""
        manager = self.PlanStateManager()

        desc = manager.get_task_description()

        assert desc == ""

