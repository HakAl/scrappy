"""Tests for deferred Textual app setup wiring."""

from unittest.mock import Mock, patch

from scrappy.cli.textual.app import CLIReady, ScrappyApp


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


def test_on_unmount_closes_session_context():
    """App shutdown should close session-scoped persistence."""
    app = ScrappyApp(cli_factory=lambda: Mock())
    session_context = Mock()
    orchestrator = Mock()
    orchestrator.cancel_all_background_tasks.return_value = 0
    orchestrator.llm_service = Mock()
    interactive_mode = Mock()
    interactive_mode.session_context = session_context
    interactive_mode.orchestrator = orchestrator
    app.interactive_mode = interactive_mode

    app.on_unmount()

    session_context.close.assert_called_once_with()
    orchestrator.cancel_all_background_tasks.assert_called_once_with()
    orchestrator.llm_service.close.assert_called_once_with()


def test_exit_runs_runtime_cleanup_once():
    """App.exit should run cleanup before delegating to Textual."""
    app = ScrappyApp(cli_factory=lambda: Mock())

    with (
        patch.object(app, "_cleanup_runtime_resources") as mock_cleanup,
        patch("textual.app.App.exit") as mock_super_exit,
    ):
        app.exit()

    mock_cleanup.assert_called_once_with()
    mock_super_exit.assert_called_once_with(None, 0, None)


def test_copy_to_clipboard_uses_system_clipboard_when_available():
    """Clipboard copy should sync Textual's clipboard to the OS clipboard too."""
    app = ScrappyApp(cli_factory=lambda: Mock())
    pyperclip = Mock()

    with (
        patch.dict("sys.modules", {"pyperclip": pyperclip}),
        patch("textual.app.App.copy_to_clipboard", autospec=True) as mock_super_copy,
    ):
        app.copy_to_clipboard("copied text")

    pyperclip.copy.assert_called_once_with("copied text")
    mock_super_copy.assert_called_once_with(app, "copied text")


def test_handle_paste_shortcut_reads_system_clipboard():
    """Paste shortcut should populate the target TextArea from the OS clipboard."""
    app = ScrappyApp(cli_factory=lambda: Mock())
    target = Mock()
    target.read_only = False
    pyperclip = Mock()
    pyperclip.paste.return_value = "clipboard text"

    with (
        patch.object(app, "_get_paste_target", return_value=target),
        patch.dict("sys.modules", {"pyperclip": pyperclip}),
    ):
        assert app._handle_paste_shortcut() is True

    assert app._clipboard == "clipboard text"
    target.focus.assert_called_once_with()
    target.action_paste.assert_called_once_with()


def test_handle_ctrl_c_prefers_copy_over_exit_and_cancel():
    """Copying selected text should not arm Ctrl+C exit behavior."""
    app = ScrappyApp(cli_factory=lambda: Mock())

    with (
        patch.object(app, "_handle_copy_shortcut", return_value=True) as mock_copy,
        patch.object(app, "_cancel_operation") as mock_cancel,
        patch.object(app, "notify") as mock_notify,
        patch.object(app, "exit") as mock_exit,
    ):
        assert app._handle_ctrl_c() is True

    mock_copy.assert_called_once_with()
    mock_cancel.assert_not_called()
    mock_notify.assert_not_called()
    mock_exit.assert_not_called()


def test_restore_mouse_support_uses_driver_hook_when_available():
    """Mouse restore should call the driver's enable hook when present."""
    app = ScrappyApp(cli_factory=lambda: Mock())
    driver = Mock()
    app._driver = driver

    app.restore_mouse_support()

    driver._enable_mouse_support.assert_called_once_with()


def test_on_cliready_reasserts_mouse_support_after_banner_status():
    """Completing deferred startup should schedule mouse support restoration."""
    app = ScrappyApp(cli_factory=lambda: Mock())
    cli = Mock()
    cli.io = Mock()

    with (
        patch.object(app, "_setup_interactive_mode"),
        patch.object(app, "call_after_refresh") as mock_call_after_refresh,
        patch("scrappy.cli.interactive_banner.display_banner_status") as mock_banner_status,
    ):
        app.on_cliready(CLIReady(cli=cli))

    mock_banner_status.assert_called_once_with(cli.io)
    mock_call_after_refresh.assert_called_once_with(app.restore_mouse_support)
