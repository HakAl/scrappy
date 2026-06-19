"""Tests for deferred Textual app setup wiring."""

import json
from pathlib import Path
from unittest.mock import Mock, call, patch
import uuid

from scrappy.cli.protocols import ActivityState
from scrappy.cli.textual.app import ScrappyApp
from scrappy.cli.textual.tui_events import (
    ActivityChanged,
    CliReadyChanged,
    TranscriptAppendText,
    TuiEventMessage,
)
from scrappy.cli.widgets import SelectableLog


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
    clipboard = Mock()
    app = ScrappyApp(cli_factory=lambda: Mock(), clipboard=clipboard)

    with (
        patch("textual.app.App.copy_to_clipboard", autospec=True) as mock_super_copy,
    ):
        app.copy_to_clipboard("copied text")

    clipboard.copy_text.assert_called_once_with("copied text")
    mock_super_copy.assert_called_once_with(app, "copied text")


def test_handle_paste_shortcut_reads_system_clipboard():
    """Paste shortcut should populate the target TextArea from the OS clipboard."""
    clipboard = Mock()
    clipboard.paste_text.return_value = "clipboard text"
    app = ScrappyApp(cli_factory=lambda: Mock(), clipboard=clipboard)
    target = Mock()
    target.read_only = False

    with (
        patch.object(app, "_get_paste_target", return_value=target),
    ):
        assert app._handle_paste_shortcut() is True

    assert app._clipboard == "clipboard text"
    clipboard.paste_text.assert_called_once_with()
    target.focus.assert_called_once_with()
    target.action_paste.assert_called_once_with()


def test_get_paste_target_uses_active_chat_surface_input():
    """Paste fallback should use any active screen's shared composer."""
    app = ScrappyApp(cli_factory=lambda: Mock())
    target = Mock()
    mock_screen = Mock()
    mock_screen._surface = Mock(input=target)

    with patch.object(type(app), "screen", new_callable=lambda: property(lambda self: mock_screen)):
        assert app._get_paste_target() is target


class FakeSelectableLog(SelectableLog):
    """SelectableLog test double that avoids clipboard side effects."""

    def __init__(self) -> None:
        super().__init__()
        self.copied = False

    @property
    def selection_text(self) -> str:
        return "selected transcript"

    def action_copy_selection(self) -> None:
        self.copied = True


def test_handle_copy_shortcut_uses_active_chat_surface_transcript():
    """Copy fallback should use any active screen's shared transcript."""
    app = ScrappyApp(cli_factory=lambda: Mock())
    output = FakeSelectableLog()
    mock_screen = Mock()
    mock_screen._surface = Mock(output=output)

    with patch.object(type(app), "screen", new_callable=lambda: property(lambda self: mock_screen)):
        assert app._handle_copy_shortcut() is True

    assert output.copied is True


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
    """Mouse restore should route through the injected policy seam."""
    policy = Mock()
    app = ScrappyApp(cli_factory=lambda: Mock(), mouse_policy=policy)

    app.restore_mouse_support()

    policy.enable.assert_called_once_with()


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
        app.on_tui_event_message(TuiEventMessage(CliReadyChanged(cli=cli)))

    mock_banner_status.assert_called_once_with(cli.io)
    assert mock_call_after_refresh.call_args_list == [
        call(app.restore_mouse_support),
        call(app._signal_integration_ready),
    ]


def test_transcript_event_reasserts_mouse_support_after_refresh():
    """Live transcript output should repair mouse tracking during active work."""
    app = ScrappyApp(cli_factory=lambda: Mock())

    with (
        patch.object(app, "_route_transcript_event") as mock_route,
        patch.object(app, "call_after_refresh") as mock_call_after_refresh,
    ):
        app.on_tui_event_message(
            TuiEventMessage(TranscriptAppendText(content="streamed\n"))
        )

    mock_route.assert_called_once()
    mock_call_after_refresh.assert_called_once_with(app.restore_mouse_support)


def test_on_cliready_writes_ready_signal_when_integration_env_enabled(monkeypatch):
    """Deferred startup should emit a file-based readiness signal for live harnesses."""
    base_dir = Path(".tmp_test_app_setup_signals") / str(uuid.uuid4())
    base_dir.mkdir(parents=True, exist_ok=True)
    ready_path = base_dir / "ready.signal"
    log_path = base_dir / "integration.jsonl"
    monkeypatch.setenv("SCRAPPY_READY_FILE", str(ready_path))
    monkeypatch.setenv("SCRAPPY_INTEGRATION_LOG_PATH", str(log_path))

    app = ScrappyApp(cli_factory=lambda: Mock())
    cli = Mock()
    cli.io = Mock()

    with (
        patch.object(app, "_setup_interactive_mode"),
        patch.object(app, "call_after_refresh", side_effect=lambda callback: callback()),
        patch("scrappy.cli.interactive_banner.display_banner_status"),
    ):
        app.on_tui_event_message(TuiEventMessage(CliReadyChanged(cli=cli)))

    assert ready_path.read_text(encoding="utf-8") == "ready\n"
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert any(event["event"] == "cli_ready" for event in events)
    assert any(
        event["event"] == "ui_ready" and event["ready"] is True for event in events
    )


def test_activity_idle_emits_command_idle_integration_event(monkeypatch, tmp_path):
    """Transitioning to IDLE should emit a command_idle integration event after refresh."""
    log_path = tmp_path / "integration.jsonl"
    monkeypatch.setenv("SCRAPPY_INTEGRATION_LOG_PATH", str(log_path))

    app = ScrappyApp(cli_factory=lambda: Mock())
    mock_screen = Mock()

    with (
        patch.object(app, "call_after_refresh", side_effect=lambda callback: callback()),
        patch.object(type(app), "screen", new_callable=lambda: property(lambda self: mock_screen)),
    ):
        app.on_tui_event_message(TuiEventMessage(ActivityChanged(ActivityState.IDLE)))

    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert any(
        event["event"] == "command_idle" and event["rendered"] is True for event in events
    )


def test_activity_thinking_does_not_emit_command_idle(monkeypatch, tmp_path):
    """Transitioning to THINKING should not emit a command_idle event."""
    log_path = tmp_path / "integration.jsonl"
    monkeypatch.setenv("SCRAPPY_INTEGRATION_LOG_PATH", str(log_path))

    app = ScrappyApp(cli_factory=lambda: Mock())
    mock_screen = Mock()

    with (
        patch.object(app, "call_after_refresh", side_effect=lambda callback: callback()),
        patch.object(type(app), "screen", new_callable=lambda: property(lambda self: mock_screen)),
    ):
        app.on_tui_event_message(TuiEventMessage(ActivityChanged(ActivityState.THINKING)))

    if log_path.exists():
        events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
        assert not any(event["event"] == "command_idle" for event in events)
