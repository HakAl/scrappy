"""Tests for InteractiveMode chat routing behavior."""

from types import SimpleNamespace
from unittest.mock import Mock

from scrappy.cli.interactive import InteractiveMode
from scrappy.cli.io_interface import TestIO as CLIIOFixture


class MockTheme:
    """Minimal theme for TestIO assertions."""

    text = "white"
    error = "red"
    warning = "yellow"


def create_mode() -> tuple[InteractiveMode, CLIIOFixture, Mock]:
    """Create InteractiveMode with lightweight test doubles."""
    io = CLIIOFixture()
    io.theme = MockTheme()
    session_context = Mock()
    session_context.conversation_history = []
    session_context.add_message = Mock()

    state_manager = Mock()
    state_manager.plan_active = False

    input_handler = Mock()
    input_handler.is_command.return_value = False

    mode = InteractiveMode(
        io=io,
        orchestrator=Mock(),
        session_context=session_context,
        state_manager=state_manager,
        input_handler=input_handler,
        command_router=Mock(),
        display=Mock(),
        tasks=Mock(),
        logger=Mock(),
        theme=MockTheme(),
    )
    return mode, io, session_context


def test_process_via_langgraph_returns_error_when_bridge_missing():
    """Direct LangGraph processing should degrade gracefully without a bridge."""
    mode, _, _ = create_mode()

    result = mode._process_via_langgraph("hello")

    assert result == "Error: Agent not initialized"


def test_process_input_reports_missing_langgraph_bridge():
    """Chat input should show a user-visible error instead of crashing."""
    mode, io, session_context = create_mode()

    should_continue = mode._process_input("hello")

    assert should_continue is True
    assert session_context.conversation_history == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "Error: Agent not initialized"},
    ]
    session_context.add_message.assert_any_call({"role": "user", "content": "hello"})
    session_context.add_message.assert_any_call(
        {"role": "assistant", "content": "Error: Agent not initialized"}
    )
    output = io.get_output()
    assert "> hello" in output
    assert "Error: LangGraph bridge not initialized" in output


def test_process_via_langgraph_returns_last_assistant_message():
    """LangGraph chat should return the most recent assistant response."""
    mode, _, _ = create_mode()
    bridge = Mock()
    bridge.run_agent.return_value = SimpleNamespace(
        cancelled=False,
        success=True,
        error=None,
        final_state=SimpleNamespace(
            messages=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "first"},
                {"role": "assistant", "content": "final"},
            ]
        ),
    )
    mode.set_langgraph_bridge(bridge)

    result = mode._process_via_langgraph("hello")

    assert result == "final"
    bridge.run_agent.assert_called_once()


def test_process_via_langgraph_failure_appends_suggestion_line():
    """PR-4 Option D: chat failures render the suggestion channel."""
    mode, _, _ = create_mode()
    bridge = Mock()
    bridge.run_agent.return_value = SimpleNamespace(
        cancelled=False,
        success=False,
        error="Rate limit exceeded for groq",
        suggestion="Wait 30.0 seconds before retrying.",
        final_state=None,
    )
    mode.set_langgraph_bridge(bridge)

    result = mode._process_via_langgraph("hello")

    assert result == (
        "Error: Rate limit exceeded for groq\n"
        "Suggestion: Wait 30.0 seconds before retrying."
    )


def test_process_via_langgraph_failure_without_suggestion_has_no_line():
    """No suggestion channel means no dangling Suggestion: line."""
    mode, _, _ = create_mode()
    bridge = Mock()
    bridge.run_agent.return_value = SimpleNamespace(
        cancelled=False,
        success=False,
        error="Tool execution failed",
        suggestion=None,
        final_state=None,
    )
    mode.set_langgraph_bridge(bridge)

    result = mode._process_via_langgraph("hello")

    assert result == "Error: Tool execution failed"
    assert "Suggestion:" not in result
