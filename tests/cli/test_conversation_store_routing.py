"""Conversation-store destination ownership (scrappy-su47, contract B).

WHY THIS SUITE EXISTS. Every pre-existing test of this route PATCHES
``scrappy.cli.core.create_conversation_store`` (nine call sites across five
modules, including the two provider/API routing suites). In those tests the
helper never runs, so none of them can establish where the SQLite database
actually lands. Replacing the helper cannot prove what the helper does.

HELPER PATCHING, STATED ACCURATELY. Every POSITIVE test runs the REAL helper,
the real ``ConversationStore`` and real SQLite. Exactly one place patches the
helper: the wrong-root negative control, which needs a deliberate mutation seam
to misroute the destination. That seam is marked as such at its use site. An
earlier version of this header claimed nothing here patches the helper; that was
inaccurate and is corrected.

CONTRACT B, in precedence order, one test per rule:

1. An explicitly supplied STORE wins unchanged, including a falsey one.
2. Otherwise an explicitly supplied PROVIDER owns the destination:
   ``provider.data_dir()`` holds ``conversations.db`` and its companion
   ``config.json`` project identity.
3. Without an explicit provider the LEGACY destination is preserved:
   ``orchestrator.context.project_path / ".scrappy"``, including when an
   injected orchestrator's project differs from the CWD.

FOUR DISTINCT ROOTS, deliberately never the same directory: the CODE root the
orchestrator reports, the STORAGE root of the injected provider, the disposable
PROFILE root, and the ambient CWD. The CWD is MOVED between composition and
``initialize()`` so an accidental CWD dependence is caught rather than masked by
two roots coinciding.

EXPECTED DESTINATIONS ARE DECLARED BEFORE EXECUTION. Searching all roots and
accepting wherever the database landed would not be a regression test, because
under contract B the old code-root helper would still pass it.

THE NEGATIVE CONTROLS RUN THE REAL ORACLE. ``_assert_persistence_cycle`` is the
single success assertion. The positive test calls it and expects success; each
fault control calls THE SAME function under its injected fault and expects it to
be rejected at the real destination or restore assertion. The oracle is never
inverted, nothing raises unconditionally, and no intentionally failing test is
shipped. Ordinary graceful-degradation coverage is retained separately.
"""

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import scrappy.cli.core as cli_core
from scrappy.cli.core import CLI
from scrappy.cli.utils.cli_factory import create_conversation_store
from scrappy.infrastructure.paths import TempPathProvider

DB_NAME = "conversations.db"
ID_NAME = "config.json"


class _FalseyPathProvider(TempPathProvider):
    """A fully working provider that happens to be falsey.

    Pins the ``is None`` rule: truthiness selection would silently discard this
    provider and route to the legacy destination.
    """

    def __len__(self) -> int:
        return 0


class _FalseyStore:
    """A working store that is falsey, to pin explicit-store precedence.

    ``messages`` is a real capture, used to assert the session actually consumed
    the injected store rather than merely holding a reference to it.
    """

    def __init__(self):
        self.messages = []

    def __bool__(self) -> bool:
        return False

    def get_recent(self, token_budget=None):
        return []

    def get_last_message_time(self):
        return None

    def add_message(self, message):
        self.messages.append(message)

    def close(self):
        return None


def _orchestrator_at(code_root: Path) -> MagicMock:
    """A controlled orchestrator whose context reports CODE_ROOT as its project."""
    orch = MagicMock()
    orch.context = SimpleNamespace(project_path=code_root)
    return orch


def _isolated_cli(**kwargs) -> CLI:
    """Build a real CLI with unrelated collaborators controlled.

    The conversation-store helper is NOT patched here: it is the code under test.
    IO and handlers are doubles because they are unrelated to destination
    ownership and would otherwise touch a terminal.

    ``api_key_service`` is supplied through the CLI's EXISTING injection seam so
    the production ``create_api_key_service()`` is never constructed. That
    factory captures the module-bound ``paths.USER_CONFIG_FILE`` at import, which
    a ``Path.home`` patch does not replace. The real service is lazy and is not
    consumed on this route, so this closes a fixture-declaration gap rather than
    an observed escape.

    Callers that are testing the LEGACY no-provider rule must not pass
    ``path_provider``: supplying one would change the very contract under test.
    """
    handlers = {
        "display": MagicMock(),
        "session_mgr": MagicMock(),
        "codebase": MagicMock(),
        "tasks": MagicMock(),
        "agent_mgr": MagicMock(),
    }
    kwargs.setdefault("api_key_service", MagicMock())
    with (
        patch.object(CLI, "_create_default_io", return_value=MagicMock()),
        patch("scrappy.cli.core.initialize_cli_handlers", return_value=handlers),
    ):
        return CLI(**kwargs)


def _roots(tmp_path: Path, monkeypatch) -> SimpleNamespace:
    """Four distinct disposable roots plus a starting CWD."""
    code = tmp_path / "code_root"
    storage = tmp_path / "storage_root"
    profile = tmp_path / "profile_root"
    cwd_a = tmp_path / "ambient_cwd_a"
    cwd_b = tmp_path / "ambient_cwd_b"
    for p in (code, storage, profile, cwd_a, cwd_b):
        p.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: profile))
    monkeypatch.chdir(cwd_a)
    return SimpleNamespace(code=code, storage=storage, profile=profile,
                           cwd_a=cwd_a, cwd_b=cwd_b)


def _assert_store_artifacts_absent(root: Path, label: str) -> None:
    """No database, identity config or SQLite companion anywhere under `root`."""
    found = [
        p for p in root.rglob("*")
        if p.name == DB_NAME
        or p.name.startswith(f"{DB_NAME}-")   # WAL and SHM companions
        or (p.name == ID_NAME and p.parent.name == ".scrappy")
    ]
    assert not found, f"conversation artifacts unexpectedly present under {label}: {found}"


def _assert_persistence_cycle(roots, provider, unique: str) -> None:
    """THE SUCCESS ORACLE, shared unchanged by the positive test and both controls.

    Drives the real route twice: a real CLI writes a message through the real
    ``session_context.add_message``, closes, and a genuinely NEW CLI performs its
    own real ``initialize()`` and must restore it with a stable project identity.

    Raises AssertionError at the real destination or restore assertion when the
    routing or the store is wrong. Nothing here is conditional on a fault flag,
    so the controls exercise exactly the assertions the positive test does.
    """
    expected_db = provider.data_dir() / DB_NAME
    expected_id = provider.data_dir() / ID_NAME

    first = _isolated_cli(orchestrator=_orchestrator_at(roots.code), path_provider=provider)
    try:
        first.initialize(offer_session_restore=False)
        first.session_context.add_message({"role": "user", "content": unique})
    finally:
        # F2: close the first SQLite session even when an assertion above fails,
        # so DB/WAL handles are not left open for the next case (Windows).
        first.session_context.close()

    # DESTINATION assertion.
    assert expected_db.is_file(), f"no database at the declared destination {expected_db}"
    assert expected_id.is_file(), f"no project identity at {expected_id}"
    identity_after_first = expected_id.read_text(encoding="utf-8")

    second = _isolated_cli(
        orchestrator=_orchestrator_at(roots.code),
        path_provider=TempPathProvider(roots.storage),
    )
    try:
        second.initialize(offer_session_restore=False)
        restored = second.session_context.conversation_history
        # RESTORE assertion.
        assert any(unique in str(m.get("content", "")) for m in restored), (
            f"the persisted message was not restored; history={restored}"
        )
        assert expected_id.read_text(encoding="utf-8") == identity_after_first, (
            "project identity changed across reopen"
        )
    finally:
        second.session_context.close()


class TestExplicitStorePrecedence:
    """Rule 1: an explicitly supplied store wins, and is never replaced."""

    def test_injected_store_is_used_consumed_and_no_database_is_created(
        self, tmp_path, monkeypatch
    ):
        roots = _roots(tmp_path, monkeypatch)
        provider = TempPathProvider(roots.storage)
        store = _FalseyStore()

        cli = _isolated_cli(
            orchestrator=_orchestrator_at(roots.code),
            path_provider=provider,
            conversation_store=store,
        )
        monkeypatch.chdir(roots.cwd_b)
        cli.initialize(offer_session_restore=False)

        # The injected store survives even though it is FALSEY. Truthiness
        # selection here would have discarded it and built a database.
        assert cli._conversation_store is store

        # And it is actually CONSUMED by the session, not merely held. This
        # distinguishes a store retained on the CLI but lost when SessionContext
        # is rebuilt during initialize().
        cli.session_context.add_message({"role": "user", "content": "consumed marker"})
        assert any(
            m.get("content") == "consumed marker" for m in store.messages
        ), f"session did not consume the injected store; captured={store.messages}"

        _assert_store_artifacts_absent(roots.storage, "STORAGE root")
        _assert_store_artifacts_absent(roots.code, "CODE root")
        _assert_store_artifacts_absent(roots.profile, "PROFILE root")


class TestExplicitProviderOwnsDestination:
    """Rule 2: an explicitly supplied provider selects the destination."""

    def test_database_and_identity_land_under_the_provider_data_dir(self, tmp_path, monkeypatch):
        roots = _roots(tmp_path, monkeypatch)
        provider = TempPathProvider(roots.storage)

        # DECLARED BEFORE EXECUTION.
        expected_db = provider.data_dir() / DB_NAME
        expected_id = provider.data_dir() / ID_NAME
        assert not expected_db.exists()

        cli = _isolated_cli(
            orchestrator=_orchestrator_at(roots.code),
            path_provider=provider,
        )
        monkeypatch.chdir(roots.cwd_b)
        try:
            cli.initialize(offer_session_restore=False)

            assert expected_db.is_file(), f"no database at the declared destination {expected_db}"
            assert expected_id.is_file(), f"no project identity at {expected_id}"
            _assert_store_artifacts_absent(roots.code, "CODE root")
            _assert_store_artifacts_absent(roots.profile, "PROFILE root")
            _assert_store_artifacts_absent(roots.cwd_b, "ambient CWD")
        finally:
            cli.session_context.close()

    def test_a_falsey_provider_still_owns_the_destination(self, tmp_path, monkeypatch):
        """`is None`, not truthiness. A falsey provider must not be discarded."""
        roots = _roots(tmp_path, monkeypatch)
        provider = _FalseyPathProvider(roots.storage)
        assert not provider, "fixture must actually be falsey for this to bite"

        expected_db = provider.data_dir() / DB_NAME

        cli = _isolated_cli(
            orchestrator=_orchestrator_at(roots.code),
            path_provider=provider,
        )
        try:
            cli.initialize(offer_session_restore=False)
            assert expected_db.is_file(), "a falsey provider was silently discarded"
            _assert_store_artifacts_absent(roots.code, "CODE root")
        finally:
            cli.session_context.close()


class TestLegacyDestinationPreserved:
    """Rule 3: no explicit provider preserves the orchestrator-derived location.

    These deliberately pass NO path_provider. Absent explicit provenance IS the
    contract under test, so supplying one to simplify setup would test something
    else entirely.
    """

    def test_without_a_provider_the_database_stays_at_the_orchestrator_project(
        self, tmp_path, monkeypatch
    ):
        roots = _roots(tmp_path, monkeypatch)

        # DECLARED BEFORE EXECUTION: the CODE root, not the CWD.
        expected_db = roots.code / ".scrappy" / DB_NAME

        cli = _isolated_cli(orchestrator=_orchestrator_at(roots.code))
        monkeypatch.chdir(roots.cwd_b)
        try:
            cli.initialize(offer_session_restore=False)
            assert expected_db.is_file(), f"legacy destination not preserved: {expected_db}"
            _assert_store_artifacts_absent(roots.profile, "PROFILE root")
            _assert_store_artifacts_absent(roots.cwd_b, "ambient CWD")
        finally:
            cli.session_context.close()

    def test_injected_orchestrator_beats_the_cwd_derived_default_provider(
        self, tmp_path, monkeypatch
    ):
        """THE COMPATIBILITY CASE.

        With no explicit provider the CLI builds its own default from the CWD.
        Forwarding THAT would move the database for every configuration where an
        injected orchestrator points elsewhere. The orchestrator must win.
        """
        roots = _roots(tmp_path, monkeypatch)

        expected_db = roots.code / ".scrappy" / DB_NAME
        forbidden_cwd = roots.cwd_b

        cli = _isolated_cli(orchestrator=_orchestrator_at(roots.code))
        # The CLI's default provider was resolved at composition under cwd_a;
        # the run then happens somewhere else entirely.
        monkeypatch.chdir(forbidden_cwd)
        try:
            cli.initialize(offer_session_restore=False)
            assert expected_db.is_file()
            _assert_store_artifacts_absent(forbidden_cwd, "ambient CWD at run time")
            _assert_store_artifacts_absent(roots.cwd_a, "ambient CWD at composition time")
        finally:
            cli.session_context.close()


class TestRealPersistenceAcrossReopen:
    """The positive run of the shared oracle."""

    def test_message_written_then_recovered_by_a_new_cli_with_stable_identity(
        self, tmp_path, monkeypatch
    ):
        roots = _roots(tmp_path, monkeypatch)
        provider = TempPathProvider(roots.storage)
        _assert_persistence_cycle(roots, provider, "su47 unique marker 0f3a9c")


class TestNegativeControls:
    """Each runs THE SAME success oracle under a fault and requires its rejection.

    No oracle inversion, no unconditional raise, no shipped failing test. The
    ordinary graceful-degradation behaviour keeps its own separate test.
    """

    def test_wrong_root_routing_is_rejected_by_the_success_oracle(self, tmp_path, monkeypatch):
        """WRONG-ROOT CONTROL. Discriminates the routing fix specifically.

        Rejecting a None store would not discriminate it: a wrong destination
        still produces a perfectly working store.
        """
        roots = _roots(tmp_path, monkeypatch)
        provider = TempPathProvider(roots.storage)
        wrong = TempPathProvider(roots.code)
        real_helper = cli_core.create_conversation_store

        # INTENTIONAL MUTATION SEAM, and the only helper patch in this module:
        # it reproduces the pre-fix behaviour of consulting the wrong root.
        expected_db = provider.data_dir() / DB_NAME
        with patch(
            "scrappy.cli.core.create_conversation_store",
            side_effect=lambda orch, path_provider=None: create_conversation_store(
                orch, path_provider=wrong
            ),
        ):
            # Rejection must occur AT THE REAL DESTINATION ASSERTION, not
            # incidentally somewhere earlier. The match pins where it happened.
            with pytest.raises(
                AssertionError, match=r"no database at the declared destination"
            ) as excinfo:
                _assert_persistence_cycle(roots, provider, "wrong-root marker")
        assert str(expected_db) in str(excinfo.value)

        # The mutation is confined to the with-block.
        assert cli_core.create_conversation_store is real_helper
        # And the misrouted database really was produced elsewhere.
        assert (wrong.data_dir() / DB_NAME).is_file()

    def test_disabled_store_is_rejected_by_the_success_oracle(self, tmp_path, monkeypatch):
        """DISABLED-STORE CONTROL, via a PORTABLE injected failure.

        A targeted sqlite3.connect failure, not a chmod assumption, which is
        neither portable nor a reliable boundary.
        """
        roots = _roots(tmp_path, monkeypatch)
        provider = TempPathProvider(roots.storage)

        expected_db = provider.data_dir() / DB_NAME
        with patch(
            "scrappy.infrastructure.persistence.conversation_store.sqlite3.connect",
            side_effect=sqlite3.OperationalError("injected: store disabled"),
        ):
            with pytest.raises(
                AssertionError, match=r"no database at the declared destination"
            ) as excinfo:
                _assert_persistence_cycle(roots, provider, "disabled-store marker")
        assert str(expected_db) in str(excinfo.value)
        # Nothing was written anywhere, so the whole cycle is genuinely unprovable.
        assert not expected_db.exists()

    def test_graceful_degradation_is_preserved_when_the_store_cannot_be_created(
        self, tmp_path, monkeypatch
    ):
        """ORDINARY degradation coverage, retained separately from the control.

        Production's documented None-on-failure contract is unchanged.
        """
        roots = _roots(tmp_path, monkeypatch)
        provider = TempPathProvider(roots.storage)

        cli = _isolated_cli(
            orchestrator=_orchestrator_at(roots.code),
            path_provider=provider,
        )
        with patch(
            "scrappy.infrastructure.persistence.conversation_store.sqlite3.connect",
            side_effect=sqlite3.OperationalError("injected: store disabled"),
        ):
            cli.initialize(offer_session_restore=False)

        assert cli._conversation_store is None
        assert not (provider.data_dir() / DB_NAME).exists()
        assert cli.session_context.conversation_history == []


class TestStandaloneHelperCompatibility:
    """The helper keeps working for existing positional callers."""

    def test_positional_call_without_a_provider_uses_the_legacy_destination(
        self, tmp_path, monkeypatch
    ):
        roots = _roots(tmp_path, monkeypatch)
        orch = _orchestrator_at(roots.code)

        store = create_conversation_store(orch)   # exactly the old call shape
        try:
            assert store is not None
            assert (roots.code / ".scrappy" / DB_NAME).is_file()
            _assert_store_artifacts_absent(roots.storage, "STORAGE root")
        finally:
            if store is not None:
                store.close()

    def test_keyword_provider_is_honoured_by_the_standalone_helper(self, tmp_path, monkeypatch):
        roots = _roots(tmp_path, monkeypatch)
        provider = TempPathProvider(roots.storage)
        orch = _orchestrator_at(roots.code)

        store = create_conversation_store(orch, path_provider=provider)
        try:
            assert store is not None
            assert (provider.data_dir() / DB_NAME).is_file()
            _assert_store_artifacts_absent(roots.code, "CODE root")
        finally:
            if store is not None:
                store.close()
