"""Tests for shared Textual runtime wiring."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from scrappy.cli.textual.runtime_wiring import (
    create_textual_runtime_session,
    wire_textual_runtime,
)


def create_runtime(orchestrator):
    """Create lightweight mocks for runtime wiring tests."""
    app = Mock()
    app.bridge = Mock()
    output_adapter = Mock()
    io = Mock()
    interactive_mode = Mock()
    interactive_mode.command_router = Mock()
    cli = Mock()
    cli.agent_mgr = Mock()
    return app, interactive_mode, io, output_adapter, cli


@patch("scrappy.cli.output_bridge.OutputBridge")
@patch("scrappy.cli.interactive.InteractiveMode")
def test_create_textual_runtime_session_builds_interactive_mode(
    mock_interactive_cls,
    mock_output_bridge_cls,
):
    """Session factory should consistently build InteractiveMode for Textual."""
    orchestrator = Mock()
    io = Mock()
    session_context = Mock()
    state_manager = Mock()
    input_handler = Mock()
    command_router = Mock()
    display = Mock()
    tasks = Mock()
    logger = Mock()
    output_adapter = Mock()
    interactive_mode = Mock()
    mock_interactive_cls.return_value = interactive_mode
    output_bridge = Mock()
    mock_output_bridge_cls.return_value = output_bridge

    result = create_textual_runtime_session(
        io=io,
        orchestrator=orchestrator,
        session_context=session_context,
        state_manager=state_manager,
        input_handler=input_handler,
        command_router=command_router,
        display=display,
        tasks=tasks,
        logger=logger,
        output_adapter=output_adapter,
    )

    assert result is interactive_mode
    assert orchestrator.output is output_bridge
    mock_output_bridge_cls.assert_called_once_with(output_adapter)
    mock_interactive_cls.assert_called_once_with(
        io=io,
        orchestrator=orchestrator,
        session_context=session_context,
        state_manager=state_manager,
        input_handler=input_handler,
        command_router=command_router,
        display=display,
        tasks=tasks,
        logger=logger,
    )


def test_wire_textual_runtime_skips_langgraph_when_streaming_unavailable():
    """Bridge wiring should still complete without LangGraph support."""
    orchestrator = SimpleNamespace()
    app, interactive_mode, io, output_adapter, cli = create_runtime(orchestrator)
    callback = Mock()

    result = wire_textual_runtime(
        app=app,
        interactive_mode=interactive_mode,
        io=io,
        orchestrator=orchestrator,
        output_adapter=output_adapter,
        cli=cli,
        setup_wizard_callback=callback,
    )

    assert result is None
    io.set_bridge.assert_called_once_with(app.bridge)
    cli.reinitialize_handlers_with_bridge.assert_called_once_with(app.bridge, None)
    interactive_mode.set_langgraph_bridge.assert_not_called()
    assert interactive_mode.command_router.agent_mgr is cli.agent_mgr
    interactive_mode.command_router.set_setup_wizard_callback.assert_called_once_with(callback)


@patch("scrappy.cli.textual.langgraph_bridge.LangGraphBridge")
@patch("scrappy.graph.tools.ToolAdapter.create_default")
def test_wire_textual_runtime_wires_langgraph_when_streaming_available(
    mock_create_default,
    mock_langgraph_bridge_cls,
):
    """Streaming-capable orchestrators should get LangGraph bridge wiring."""
    orchestrator = SimpleNamespace(
        stream_completion_with_fallback=Mock(),
        context_manager=SimpleNamespace(context=Mock()),
    )
    app, interactive_mode, io, output_adapter, cli = create_runtime(orchestrator)
    callback = Mock()
    tool_adapter = Mock()
    mock_create_default.return_value = tool_adapter
    langgraph_bridge = Mock()
    mock_langgraph_bridge_cls.return_value = langgraph_bridge

    result = wire_textual_runtime(
        app=app,
        interactive_mode=interactive_mode,
        io=io,
        orchestrator=orchestrator,
        output_adapter=output_adapter,
        cli=cli,
        setup_wizard_callback=callback,
    )

    assert result is langgraph_bridge
    app.set_codebase_context.assert_called_once_with(orchestrator.context_manager.context)
    io.set_bridge.assert_called_once_with(app.bridge)
    cli.reinitialize_handlers_with_bridge.assert_called_once_with(app.bridge, langgraph_bridge)
    interactive_mode.set_langgraph_bridge.assert_called_once_with(langgraph_bridge)
    interactive_mode.command_router.set_setup_wizard_callback.assert_called_once_with(callback)
    assert app._tool_adapter is tool_adapter
