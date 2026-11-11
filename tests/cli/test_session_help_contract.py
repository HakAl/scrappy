"""Behavioral contracts for supported session commands and exit guidance."""

from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

from rich.console import Console

from scrappy.cli.command_router import CommandRouter
from scrappy.cli.display_rich import show_help_table
from scrappy.cli.unified_io import UnifiedIO


def test_rendered_help_advertises_only_supported_session_commands():
    stream = StringIO()
    io = UnifiedIO(console=Console(file=stream, width=120, color_system=None))

    show_help_table(io)

    output = stream.getvalue()
    assert '/session save' not in output
    assert '/session load' not in output
    # Match a complete rendered first cell, including its adjacent description.
    assert any(
        line.split(chr(0x2502))[1].strip() == '/session'
        for line in output.splitlines()
        if chr(0x2502) in line
    )
    assert '/session clear' in output
    assert '/help' in output
    assert '/quit' in output


def test_quit_without_autosave_gives_supported_restart_advice():
    stream = StringIO()
    io = UnifiedIO(console=Console(file=stream, width=120, color_system=None))
    saver = Mock()
    router = CommandRouter(
        io=io,
        orchestrator=Mock(),
        session_context=SimpleNamespace(auto_save=False),
        display=Mock(),
        session_mgr=Mock(),
        codebase=Mock(),
        tasks=Mock(),
        agent_mgr=Mock(),
        session_saver=saver,
        model_selection=Mock(),
        api_key_service=Mock(),
    )

    result = router.route('/quit', '')

    output = stream.getvalue()
    assert '/session save' not in output
    assert 'Session not saved (auto-save disabled).' in output
    assert 'Start scrappy without --no-save to save the session when using /quit.' in output
    saver.save_session.assert_not_called()
    assert result is False
