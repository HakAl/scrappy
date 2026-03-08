"""Tests for shared Textual runtime wiring."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from scrappy.cli.textual.runtime_wiring import wire_textual_runtime


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
