"""Tests for deferred Textual app setup wiring."""

from unittest.mock import Mock, patch

from scrappy.cli.textual.app import ScrappyApp


def test_setup_interactive_mode_uses_shared_helpers():
    """Deferred app setup should reuse the shared session and wiring helpers."""
    app = ScrappyApp(cli_factory=lambda: Mock())
    cli = Mock()
    cli.io = Mock()
    cli.orchestrator = Mock()
    cli.session_context = Mock()
    cli.state_manager = Mock()
    cli.input_handler = Mock()
    cli._create_command_router.return_value = Mock()
    cli.display = Mock()
    cli.tasks = Mock()
    cli.logger = Mock()
    app._cli = cli

    interactive_mode = Mock()

    with (
        patch("scrappy.cli.textual.app.create_textual_runtime_session", return_value=interactive_mode) as mock_create,
        patch("scrappy.cli.textual.app.wire_textual_runtime") as mock_wire,
    ):
        app._setup_interactive_mode()

    assert app.interactive_mode is interactive_mode
    mock_create.assert_called_once_with(
        io=cli.io,
        orchestrator=cli.orchestrator,
        session_context=cli.session_context,
        state_manager=cli.state_manager,
        input_handler=cli.input_handler,
        command_router=cli._create_command_router.return_value,
        display=cli.display,
        tasks=cli.tasks,
        logger=cli.logger,
        output_adapter=app.output_adapter,
    )
    mock_wire.assert_called_once_with(
        app=app,
        interactive_mode=interactive_mode,
        io=cli.io,
        orchestrator=cli.orchestrator,
        output_adapter=app.output_adapter,
        cli=cli,
        setup_wizard_callback=app.launch_setup_wizard,
    )
