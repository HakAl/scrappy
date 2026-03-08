"""Tests for CLITaskExecution output and discovery behavior."""

from unittest.mock import Mock

from scrappy.cli.io_interface import TestIO as CLIIOFixture
from scrappy.cli.tasks import CLITaskExecution


class MockTheme:
    """Minimal theme for TestIO assertions."""

    error = "red"
    warning = "yellow"
    success = "green"


def create_task_executor():
    """Create CLITaskExecution with lightweight test doubles."""
    io = CLIIOFixture()
    io.theme = MockTheme()

    orchestrator = Mock()
    orchestrator.working_memory = Mock()

    executor = CLITaskExecution(orchestrator, io)
    return executor, io, orchestrator


def test_plan_task_formats_steps_and_records_discovery():
    """Planning should print numbered steps and record a summary discovery."""
    executor, io, orchestrator = create_task_executor()
    orchestrator.plan.return_value = [
        {"step": "Inspect", "description": "Read the relevant files."},
    ]

    steps = executor.plan_task("clean up")

    assert steps == [{"step": "Inspect", "description": "Read the relevant files."}]
    assert "Planning: clean up" in io.get_output()
    assert "1. Inspect" in io.get_output()
    orchestrator.working_memory.add_discovery.assert_called_once_with(
        "Created plan for 'clean up' with 1 steps",
        "task_plan",
    )


def test_plan_task_reports_errors_and_returns_empty_list():
    """Planning failures should surface as output and not record discoveries."""
    executor, io, orchestrator = create_task_executor()
    orchestrator.plan.side_effect = RuntimeError("boom")

    steps = executor.plan_task("clean up")

    assert steps == []
    assert "Error during planning: boom" in io.get_output()
    orchestrator.working_memory.add_discovery.assert_not_called()


def test_reason_formats_response_and_records_discovery():
    """Reasoning should render structured output and save a short conclusion."""
    executor, io, orchestrator = create_task_executor()
    orchestrator.reason.return_value = {
        "question": "why",
        "analysis": "Because the flow is valid.",
        "conclusion": "It works.",
        "confidence": "high",
    }

    executor.reason("why")

    output = io.get_output()
    assert "Reasoning about: why" in output
    assert "Analysis:" in output
    assert "It works." in output
    orchestrator.working_memory.add_discovery.assert_called_once_with(
        "Reasoning on 'why...': It works....",
        "reasoning",
    )
