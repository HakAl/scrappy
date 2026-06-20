"""Behavior tests for the CLI constructor I/O-deferral contract.

scrappy-cli-init-side-effects PR-A: CLI.__init__ must not perform conversation
persistence or command-history filesystem I/O. The default conversation store,
token-budgeted history load, staleness check, and the file-backed command history
are created in initialize() instead. These tests pin both halves of that contract:
__init__ stays I/O-free, and initialize() actually performs the deferred work.

The orchestrator and io are mocked because the default orchestrator still does its
own provider I/O in __init__ (deferring that is PR-B); these tests isolate the
persistence/history seam this PR owns.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

from scrappy.cli.command_history import get_default_history_path
from scrappy.cli.core import CLI
from scrappy.infrastructure.persistence import ConversationStoreProtocol


def _mock_handlers() -> dict:
    return {
        "display": MagicMock(),
        "session_mgr": MagicMock(),
        "codebase": MagicMock(),
        "tasks": MagicMock(),
        "multiprovider": MagicMock(),
        "smart": MagicMock(),
        "agent_mgr": MagicMock(),
    }


def _loaded_store() -> MagicMock:
    """A store double that reports one prior message at a fresh (non-stale) time."""
    store = MagicMock(spec=ConversationStoreProtocol)
    store.get_recent.return_value = [{"role": "user", "content": "hi"}]
    store.get_last_message_time.return_value = datetime.now()
    return store


def test_init_performs_no_persistence_or_file_history_io():
    """Constructing the CLI with no injected store must not create the default store,
    read history, or open the file-backed command history."""
    with patch.object(CLI, "_create_default_orchestrator", return_value=MagicMock()):
        with patch.object(CLI, "_create_default_io", return_value=MagicMock()):
            with patch("scrappy.cli.core.initialize_cli_handlers", return_value=_mock_handlers()):
                with patch("scrappy.cli.core.create_conversation_store") as mock_create:
                    with patch("scrappy.cli.core.CommandHistory") as mock_cmd_history:
                        cli = CLI()

                        # No default store creation and no history read in __init__.
                        mock_create.assert_not_called()
                        # Command history built in-memory only (history_file=None).
                        mock_cmd_history.assert_called_once_with(history_file=None)
                        # Session context exists but carries no loaded history yet.
                        assert cli.session_context.conversation_history == []


def test_initialize_creates_default_store_and_loads_history():
    """initialize() must create the default store, load token-budgeted history into
    the session context, and switch command history to the file-backed path."""
    store = _loaded_store()
    with patch.object(CLI, "_create_default_orchestrator", return_value=MagicMock()):
        with patch.object(CLI, "_create_default_io", return_value=MagicMock()):
            with patch("scrappy.cli.core.initialize_cli_handlers", return_value=_mock_handlers()):
                with patch("scrappy.cli.core.create_conversation_store", return_value=store) as mock_create:
                    with patch("scrappy.cli.core.CommandHistory") as mock_cmd_history:
                        # Staleness is unrelated to the deferral contract under test
                        # (and exercised elsewhere); pin it off so the loaded history
                        # is asserted without a prepended stale-context message.
                        with patch(
                            "scrappy.infrastructure.persistence.check_session_staleness",
                            return_value=False,
                        ):
                            cli = CLI()
                            assert cli.session_context.conversation_history == []

                            cli.initialize(offer_session_restore=False)

                        # Default store created exactly once, during initialize().
                        mock_create.assert_called_once()
                        store.get_recent.assert_called_once_with(token_budget=8000)
                        # Loaded history is now visible on the session context.
                        assert cli.session_context.conversation_history == [
                            {"role": "user", "content": "hi"}
                        ]
                        # Command history rebuilt against the real default path.
                        mock_cmd_history.assert_any_call(history_file=get_default_history_path())


def test_injected_store_is_never_replaced_by_default():
    """An injected store is honored in both __init__ and initialize(); the default
    factory is never consulted (guards the Protocol-typed is-None contract)."""
    injected = MagicMock(spec=ConversationStoreProtocol)
    injected.get_recent.return_value = []
    with patch.object(CLI, "_create_default_orchestrator", return_value=MagicMock()):
        with patch.object(CLI, "_create_default_io", return_value=MagicMock()):
            with patch("scrappy.cli.core.initialize_cli_handlers", return_value=_mock_handlers()):
                with patch("scrappy.cli.core.create_conversation_store") as mock_create:
                    with patch("scrappy.cli.core.CommandHistory"):
                        cli = CLI(conversation_store=injected)
                        cli.initialize(offer_session_restore=False)

                        mock_create.assert_not_called()
                        injected.get_recent.assert_called_once_with(token_budget=8000)
