"""Exit-save policy survives real context composition and initialization."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from scrappy.cli.core import CLI
from scrappy.cli.utils.cli_factory import create_cli_from_context
from scrappy.infrastructure.paths import TempPathProvider
from scrappy.infrastructure.theme import DEFAULT_THEME


@pytest.mark.parametrize("options, saves", [({"auto_save": False}, False), ({}, True)],
                         ids=["no-save", "default-saving"])
def test_exit_save_policy_after_initialize(tmp_path, monkeypatch, options, saves):
    profile = tmp_path / "profile"
    code = tmp_path / "code"
    storage = tmp_path / "storage"
    for root in (profile, code, storage):
        root.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: profile))
    monkeypatch.chdir(code)

    # Replace external resources, leaving constructor, initialization, handlers,
    # context extraction and public router dispatch real.
    orchestrator = MagicMock()
    orchestrator.context = SimpleNamespace(project_path=code)
    orchestrator.session_manager.get_session_info.return_value = {"exists": False}
    orchestrator.save_session.return_value = storage / "session.json"
    store = MagicMock()
    history = [{"role": "user", "content": "known exit-save payload"}]
    store.get_recent.return_value = history
    store.get_last_message_time.return_value = datetime.now(timezone.utc)
    io = MagicMock()
    io.theme = DEFAULT_THEME
    with (
        patch.object(CLI, "_create_default_orchestrator", return_value=orchestrator),
        patch("scrappy.cli.core.create_conversation_store", return_value=store),
    ):
        cli = create_cli_from_context(
            SimpleNamespace(obj=options), io=io,
            path_provider=TempPathProvider(storage), api_key_service=MagicMock(),
        )

    try:
        assert cli._create_command_router().route("/quit", "") is False
        if saves:
            orchestrator.save_session.assert_called_once_with(history)
        else:
            orchestrator.save_session.assert_not_called()
            io.secho.assert_any_call(
                "\nSession not saved (auto-save disabled).", fg=DEFAULT_THEME.warning,
            )
        # Supporting assertion follows the behavioral oracle so the negative
        # control fails specifically at the unexpected session-save call.
        assert cli.session_context.auto_save is saves
    finally:
        cli.session_context.close()
