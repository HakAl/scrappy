"""Tests for TextualInteractiveMode startup behavior."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from scrappy.cli.textual_interactive import TextualInteractiveMode


def create_mode(orchestrator, cli=None):
    """Create a TextualInteractiveMode with lightweight mocked dependencies."""
    io = Mock()
    io.output_sink = Mock()
    io.set_bridge = Mock()
    config = SimpleNamespace(theme=Mock())

    return TextualInteractiveMode(
        orchestrator=orchestrator,
        session_context=Mock(),
        state_manager=Mock(),
        input_handler=Mock(),
        command_router=Mock(),
        display=Mock(),
        tasks=Mock(),
        logger=Mock(),
        io=io,
        cli=cli,
        config=config,
    )


@patch("scrappy.cli.textual_interactive.OutputBridge")
@patch("scrappy.cli.textual_interactive.InteractiveMode")
@patch("scrappy.cli.textual_interactive.ScrappyApp")
@patch("scrappy.cli.textual_interactive.wire_textual_runtime")
def test_run_skips_langgraph_when_orchestrator_lacks_streaming(
    mock_wire_runtime,
    mock_app_cls,
    mock_interactive_cls,
    mock_output_bridge_cls,
):
    """Textual mode should still run when LangGraph bridge cannot be created."""
    orchestrator = SimpleNamespace()
    cli = Mock()
    mode = create_mode(orchestrator, cli=cli)

    app = Mock()
    app.bridge = Mock()
    mock_app_cls.return_value = app
    interactive_mode = Mock()
    mock_interactive_cls.return_value = interactive_mode
    mock_output_bridge_cls.return_value = Mock()
    mock_wire_runtime.return_value = None

    mode.run()

    mock_wire_runtime.assert_called_once_with(
        app=app,
        interactive_mode=interactive_mode,
        io=mode.io,
        orchestrator=orchestrator,
        output_adapter=mode.io.output_sink,
        cli=cli,
        setup_wizard_callback=app.launch_setup_wizard,
    )
    app.run.assert_called_once()


@patch("scrappy.cli.textual_interactive.OutputBridge")
@patch("scrappy.cli.textual_interactive.InteractiveMode")
@patch("scrappy.cli.textual_interactive.ScrappyApp")
@patch("scrappy.cli.textual_interactive.wire_textual_runtime")
def test_run_wires_langgraph_when_streaming_is_available(
    mock_wire_runtime,
    mock_app_cls,
    mock_interactive_cls,
    mock_output_bridge_cls,
):
    """Textual mode should still wire LangGraph in the happy path."""
    orchestrator = SimpleNamespace(stream_completion_with_fallback=Mock())
    cli = Mock()
    mode = create_mode(orchestrator, cli=cli)

    app = Mock()
    app.bridge = Mock()
    mock_app_cls.return_value = app
    interactive_mode = Mock()
    mock_interactive_cls.return_value = interactive_mode
    mock_output_bridge_cls.return_value = Mock()
    langgraph_bridge = Mock()
    mock_wire_runtime.return_value = langgraph_bridge

    mode.run()

    mock_wire_runtime.assert_called_once_with(
        app=app,
        interactive_mode=interactive_mode,
        io=mode.io,
        orchestrator=orchestrator,
        output_adapter=mode.io.output_sink,
        cli=cli,
        setup_wizard_callback=app.launch_setup_wizard,
    )
    app.run.assert_called_once()
