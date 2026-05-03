"""Tests for CLIAgentManager fallback behavior."""

from types import SimpleNamespace
from unittest.mock import Mock

from scrappy.cli.agent_manager import CLIAgentManager
from scrappy.cli.io_interface import TestIO as CLIIOFixture


class MockTheme:
    """Minimal theme for TestIO assertions."""

    error = "red"
    warning = "yellow"
    success = "green"


def create_agent_manager(langgraph_bridge=None):
    """Create CLIAgentManager with lightweight test doubles."""
    io = CLIIOFixture()
    io.theme = MockTheme()

    orchestrator = Mock()
    orchestrator.working_memory = Mock()

    interaction = Mock()
    interaction.confirm.return_value = False

    manager = CLIAgentManager(
        orchestrator=orchestrator,
        io=io,
        user_interaction=interaction,
        langgraph_bridge=langgraph_bridge,
    )
    return manager, io, orchestrator, interaction


def test_run_agent_reports_missing_langgraph_bridge():
    """Public agent execution should fail cleanly when bridge is unavailable."""
    manager, io, orchestrator, interaction = create_agent_manager()

    manager.run_agent("ship it")

    assert "Error: Agent not initialized" in io.get_output()
    interaction.confirm.assert_not_called()
    orchestrator.working_memory.add_discovery.assert_not_called()


def test_run_langgraph_agent_reports_missing_bridge_and_records_discovery():
    """Internal LangGraph execution should avoid assertion crashes."""
    manager, io, orchestrator, _ = create_agent_manager()
    dashboard = Mock()

    manager._run_langgraph_agent("ship it", undo_state=None, dry_run=False, dashboard=dashboard)

    assert "Error: Agent not initialized" in io.get_output()
    dashboard.set_state.assert_any_call("idle", "Agent unavailable")
    orchestrator.working_memory.add_discovery.assert_called_once_with(
        "Agent task 'ship it...' could not start: agent not initialized",
        "agent_task",
    )


def test_run_langgraph_agent_records_successful_completion():
    """Successful LangGraph runs should still record completion details."""
    bridge = Mock()
    bridge.run_agent.return_value = SimpleNamespace(
        cancelled=False,
        success=True,
        error=None,
        final_state=SimpleNamespace(iteration=3, files_changed=["a.py"]),
    )
    manager, io, orchestrator, _ = create_agent_manager(langgraph_bridge=bridge)
    dashboard = Mock()
    undo_state = SimpleNamespace(ref="refs/undo/test")

    manager._run_langgraph_agent("ship it", undo_state=undo_state, dry_run=False, dashboard=dashboard)

    bridge.run_agent.assert_called_once()
    dashboard.set_state.assert_any_call("idle", "Task completed")
    orchestrator.working_memory.add_discovery.assert_called_once_with(
        "Agent task 'ship it...': completed in 3 iterations",
        "agent_task",
    )
    assert "To undo changes: scrappy undo" in io.get_output()
