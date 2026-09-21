"""
Project-root threading: scan identity versus storage identity (scrappy-i2jo PR-5).

project_path selects the code to SCAN. The injected provider selects where
derived state is STORED. Neither substitutes for the other, and these tests
assert BOTH halves. A test that only proved containment would still pass while
scanning the wrong project, so every scan-role assertion here is bidirectional:
the intended project's planted file is FOUND, and a decoy project's file is NOT.

Four directories are kept distinct in every test: the scan project, the storage
root, the process working directory, and the disposable profile. Distinctness is
ASSERTED, not merely arranged by fixture, so a future fixture that collapses two
of them fails loudly here instead of silently weakening the proof.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock

import pytest

from scrappy.context.codebase_context import CodebaseContext
from scrappy.context.semantic.config import SemanticIndexConfig
from scrappy.context.semantic_manager import SemanticSearchManager, bind_storage_defaults
from scrappy.context.staleness import StalenessChecker
from scrappy.infrastructure.paths import TempPathProvider, create_default_path_provider
from scrappy.orchestrator.factory import OrchestratorFactory

SCAN_MARKER = "marker_intended.py"
DECOY_MARKER = "marker_decoy.py"


class _FalseyStalenessChecker(StalenessChecker):
    """A fully working checker that happens to be falsey."""

    def __len__(self) -> int:
        return 0


class _FalseySemanticIndexConfig(SemanticIndexConfig):
    """A fully working config that happens to be falsey."""

    def __bool__(self) -> bool:
        return False


class _FalseyPathProvider(TempPathProvider):
    """A fully working provider that happens to be falsey."""

    def __len__(self) -> int:
        return 0


@dataclass
class RoutingEnv:
    """Four distinct roles, deliberately never the same directory."""

    scan_project: Path
    decoy_project: Path
    storage_root: Path
    cwd_dir: Path
    provider: TempPathProvider


@pytest.fixture
def routing(tmp_path, monkeypatch) -> RoutingEnv:
    """Build the four-way distinct environment and prove it is distinct."""
    scan_project = tmp_path / "scan_project"
    decoy_project = tmp_path / "decoy_project"
    storage_root = tmp_path / "storage_root"
    cwd_dir = tmp_path / "process_cwd"
    for directory in (scan_project, decoy_project, storage_root, cwd_dir):
        directory.mkdir()

    (scan_project / SCAN_MARKER).write_text("INTENDED = 1\n")
    (decoy_project / DECOY_MARKER).write_text("DECOY = 1\n")

    monkeypatch.chdir(cwd_dir)
    provider = TempPathProvider(storage_root)

    roles = {
        "scan_project": scan_project.resolve(),
        "decoy_project": decoy_project.resolve(),
        "storage_root": storage_root.resolve(),
        "cwd_dir": cwd_dir.resolve(),
    }
    assert len(set(roles.values())) == 4, f"roles collapsed: {roles}"
    # The disposable profile is a fifth thing and storage must not be it.
    assert provider.data_dir().resolve() != (Path.home() / ".scrappy").resolve()
    assert Path.cwd().resolve() == cwd_dir.resolve()

    return RoutingEnv(
        scan_project=scan_project,
        decoy_project=decoy_project,
        storage_root=storage_root,
        cwd_dir=cwd_dir,
        provider=provider,
    )


def _context_via_factory(env: RoutingEnv, *, semantic: bool = False) -> CodebaseContext:
    """Compose a context the way production does, through the factory."""
    factory = OrchestratorFactory(
        project_path=str(env.scan_project),
        path_provider=env.provider,
        enable_semantic_search=semantic,
        api_key_service=Mock(),
    )
    return factory.create_codebase_context()


def _router_with_provider(provider):
    """Build a CommandRouter with only the provider wiring that matters here."""
    from scrappy.cli.command_router import CommandRouter

    return CommandRouter(
        io=Mock(),
        orchestrator=Mock(),
        session_context=Mock(),
        display=Mock(),
        session_mgr=Mock(),
        codebase=Mock(),
        tasks=Mock(),
        agent_mgr=Mock(),
        session_saver=Mock(),
        model_selection=Mock(),
        api_key_service=Mock(),
        path_provider=provider,
    )


def _stub_semantic_externals(monkeypatch) -> list:
    """Make every semantic-enabled route offline and deterministic.

    Exactly two external boundaries are replaced: embedding-model creation
    and lancedb.connect. Everything between them still runs for real -- the
    initializer worker, the search provider, config propagation and directory
    creation -- so these tests prove routing rather than restate it. No model
    is downloaded and no native database I/O happens.

    Returns:
        The list of directories actually handed to lancedb.connect.
    """
    from scrappy.context.semantic import provider as provider_module
    from scrappy.context.semantic import state as state_module

    class DeterministicEmbedding:
        def generate_embeddings(self, texts):
            return [[0.0] * 384 for _ in texts]

        def ndims(self):
            return 384

    monkeypatch.setattr(
        provider_module,
        "_create_embedding_func",
        lambda model_id=None: DeterministicEmbedding(),
    )

    connected: list = []

    class FakeDB:
        def table_names(self):
            return []

    def fake_connect(path):
        connected.append(Path(path))
        return FakeDB()

    monkeypatch.setattr(provider_module.lancedb, "connect", fake_connect)
    monkeypatch.setattr(state_module.lancedb, "connect", fake_connect)

    return connected


def _pin_embedding_model(monkeypatch, model_id: str = "bge-small") -> str:
    """Pin model selection so the model subdirectory is deterministic.

    Selection must travel through configuration, never through pre-setting
    _model_id: _resolve_model_and_paths returns immediately when that
    attribute is already set, which would skip path resolution entirely and
    hollow out the assertions that follow.
    """
    monkeypatch.setenv("SEMANTIC_INDEX_EMBEDDING_MODEL", model_id)
    return model_id


def _settle_background_init(context: CodebaseContext) -> None:
    """Drive started background initialization to completion, then stop it.

    Tests must not leave model-loading threads running. The wait also proves
    the offline stubs actually carried the work instead of the thread dying
    quietly and the assertions passing for the wrong reason.
    """
    initializer = context._semantic_manager._initializer
    assert initializer is not None, "semantic route did not create an initializer"
    assert initializer.wait_for_completion(timeout=30.0), (
        f"background initialization did not finish offline: {initializer.get_error()}"
    )

    # Real thread liveness, not just the completion flag: a shutdown that
    # left the worker alive would otherwise pass unnoticed.
    managed_thread = initializer._managed_thread
    context._semantic_manager.shutdown(timeout=30.0)
    assert managed_thread is None or not managed_thread.is_running(), (
        "background initializer thread outlived the test"
    )


def _assert_scanned_intended_project(context: CodebaseContext) -> None:
    """Bidirectional scan proof: intended file found, decoy file absent."""
    python_files = context.file_index.get("python", [])
    assert SCAN_MARKER in python_files, (
        f"scan did not reach the intended project; saw {python_files}"
    )
    assert DECOY_MARKER not in python_files, (
        f"scan reached the decoy project; saw {python_files}"
    )


class TestStorageFollowsProvider:
    """T13, T14: derived state lands under the injected storage root."""

    def test_t13_context_cache_lands_under_injected_storage_root(self, routing):
        """Context cache must be the provider's file, and must really be written."""
        context = _context_via_factory(routing)

        context.explore()

        expected = routing.provider.context_file()
        assert context.cache_file == expected
        assert expected.exists(), "cache file was not actually written"
        assert expected.is_relative_to(routing.storage_root)
        assert not expected.is_relative_to(routing.scan_project)
        assert not expected.is_relative_to(routing.cwd_dir)
        _assert_scanned_intended_project(context)

    def test_t14_fingerprints_store_at_provider_while_scan_stays_on_scan_root(
        self, routing
    ):
        """The two roles inside StalenessChecker must separate.

        This is the test that fails if only the provider is forwarded, and
        also fails if the scan root is re-pointed at storage.
        """
        context = _context_via_factory(routing)
        checker = context._staleness_checker

        # STORAGE role: fingerprints resolve under the provider.
        assert checker._fingerprint_path.is_relative_to(routing.storage_root)
        assert not checker._fingerprint_path.is_relative_to(routing.scan_project)

        # SCAN role: the checker still scans the scan project.
        assert Path(checker.root_path).resolve() == routing.scan_project.resolve()

        # And the write really happens at the storage destination.
        checker.update_fingerprints()
        assert checker._fingerprint_path.exists(), "fingerprints were not written"

        context.explore()
        _assert_scanned_intended_project(context)


class TestLanceDBBoundary:
    """T15: the directory handed across the external boundary."""

    def test_t15_lancedb_receives_injected_storage_destination(
        self, routing, monkeypatch
    ):
        """Drive the REAL initializer offline and assert the actual connect args.

        The initializer and the state manager are both SUPPLIED BY the routed
        context's manager, never constructed here. That distinction is the
        whole point: hand-building either one would keep passing if the
        manager stopped forwarding its config to them, which is exactly the
        regression this test exists to catch.

        Expected destinations are derived from the PROVIDER, not from the
        config the manager happens to be holding, so the test cannot drift
        into agreeing with a broken manager.
        """
        connected = _stub_semantic_externals(monkeypatch)
        model_id = _pin_embedding_model(monkeypatch)

        context = _context_via_factory(routing)
        manager = context._semantic_manager

        # --- state-manager boundary, as the routed manager composed it ---
        state_manager = manager._state_manager
        state_manager._ensure_db()

        # --- search-provider boundary, through the initializer the manager builds ---
        initializer = manager._create_default_initializer()

        class StubThread:
            shutdown_requested = False

        initializer._initialize_worker(StubThread())

        assert initializer.is_complete(), (
            f"initialization did not succeed: {initializer.get_error()}"
        )

        routed = bind_storage_defaults(routing.provider)
        expected_state_dir = Path(routed.db_dir_name)
        expected_provider_dir = Path(routed.get_db_dir_for_model(model_id))

        assert expected_state_dir in connected, f"state dir not connected: {connected}"
        assert expected_provider_dir in connected, (
            f"provider dir not connected: {connected}"
        )

        # Model-specific subdirectory preserved, under the injected storage.
        assert expected_provider_dir.name == model_id
        assert expected_provider_dir.is_relative_to(routing.storage_root)
        assert not expected_provider_dir.is_relative_to(routing.scan_project)
        assert not expected_provider_dir.is_relative_to(routing.cwd_dir)

        # Directories were really created; mkdir was not stubbed.
        assert expected_state_dir.is_dir()
        assert expected_provider_dir.is_dir()


class TestWorkingDirectoryIsNotConsulted:
    """T16, T16b: CWD behaviour, proven by exercising routes rather than arranging one."""

    def test_t16_routed_objects_ignore_a_moved_cwd(self, routing, monkeypatch, tmp_path):
        """Construct real routed objects, move CWD, then exercise the routes."""
        from scrappy.cli import interactive_banner

        context = _context_via_factory(routing)

        # Move CWD again, after composition, to a fifth directory.
        moved_cwd = tmp_path / "moved_cwd"
        moved_cwd.mkdir()
        monkeypatch.chdir(moved_cwd)

        # --- scanning and storage still route correctly ---
        context.explore()
        _assert_scanned_intended_project(context)
        assert context.cache_file.is_relative_to(routing.storage_root)
        assert not context.cache_file.is_relative_to(moved_cwd)
        assert context._staleness_checker._fingerprint_path.is_relative_to(
            routing.storage_root
        )

        # --- banner output reflects the injected provider ---
        printed = []
        docker_roots = []
        io = Mock()
        io.echo = Mock()
        monkeypatch.setattr(
            interactive_banner,
            "_print_rich",
            lambda io_, text: printed.append(text),
        )
        monkeypatch.setattr(
            interactive_banner,
            "_get_docker_status",
            lambda root: docker_roots.append(root) or {"available": False},
        )
        api_key_service = Mock()
        api_key_service.get_configured_providers = Mock(return_value=[])

        interactive_banner.display_banner_status(
            io, api_key_service=api_key_service, path_provider=routing.provider
        )

        workspace_lines = [line for line in printed if "Workspace" in line]
        assert workspace_lines, f"no workspace line rendered: {printed}"
        assert str(moved_cwd) not in workspace_lines[0]

        # The docker root must be the provider's ACTUAL root. Reading
        # project_root without calling it yields a bound-method repr, which
        # is a string and so survives str() silently; assert the real value.
        assert docker_roots, "docker status was never consulted"
        assert "bound method" not in docker_roots[0], (
            f"banner stringified a method instead of calling it: {docker_roots[0]!r}"
        )
        assert docker_roots[0] == str(routing.provider.project_root())
        assert str(moved_cwd) not in docker_roots[0]

        # --- task handling reads the injected provider's todo file ---
        # Driven through CommandRouter, not by constructing storage directly:
        # constructing it here would assert the provider's path without ever
        # proving the router consults the injected provider.
        todo = routing.provider.todo_file()
        todo.parent.mkdir(parents=True, exist_ok=True)
        todo.write_text("- [ ] injected task\n")

        router = _router_with_provider(routing.provider)
        router_io = Mock()
        # clear_tasks=True takes the branch that clears without prompting, so
        # the assertion is on which file the router actually reached.
        router._handle_existing_tasks(router_io, clear_tasks=True)

        assert not todo.exists() or "injected task" not in todo.read_text(), (
            "router did not act on the injected provider's todo file"
        )

    def test_t16b_bare_construction_captures_cwd_once(self, routing, monkeypatch, tmp_path):
        """Omitted scan root snapshots CWD at composition and does not follow it."""
        monkeypatch.chdir(routing.scan_project)

        context = CodebaseContext()
        captured = context.project_path

        assert captured.resolve() == routing.scan_project.resolve()

        moved = tmp_path / "after_construction"
        moved.mkdir()
        monkeypatch.chdir(moved)

        assert context.project_path.resolve() == routing.scan_project.resolve(), (
            "scan root followed the working directory instead of being snapshotted"
        )
        context.explore()
        _assert_scanned_intended_project(context)


class TestProductionDefaultsPreserved:
    """T17: default composition still selects today's locations."""

    def test_t17_default_composition_reproduces_production_paths(self, tmp_path):
        """Absolute binding must not move any production path."""
        project_root = tmp_path / "proj"
        project_root.mkdir()
        provider = create_default_path_provider(project_root)
        config = bind_storage_defaults(provider)

        legacy_db = (project_root / SemanticIndexConfig().db_dir_name).resolve()
        legacy_fp = (project_root / SemanticIndexConfig().fingerprint_file).resolve()

        assert Path(config.db_dir_name) == legacy_db
        assert Path(config.fingerprint_file) == legacy_fp

        # Model-specific subdirectory preserved.
        assert Path(config.get_db_dir_for_model("bge-small")) == legacy_db / "bge-small"

        # No repeated .scrappy component anywhere.
        for value in (config.db_dir_name, config.fingerprint_file):
            assert ".scrappy/.scrappy" not in value
            assert value.count(f"{os.sep}.scrappy{os.sep}") <= 1

        # The provider holds an absolute root even when composed relatively.
        assert create_default_path_provider(Path(".")).project_root().is_absolute()

    def test_t17b_no_provider_keeps_global_defaults(self):
        """Without a provider the global defaults are untouched."""
        config = bind_storage_defaults(None)
        assert config.db_dir_name == SemanticIndexConfig().db_dir_name
        assert config.fingerprint_file == SemanticIndexConfig().fingerprint_file


class TestConfigObjectPrecedence:
    """T18: an explicitly supplied config object wins as a whole."""

    def test_t18_supplied_absolute_values_are_used_as_given(self, routing, tmp_path):
        """An absolute supplied config wins THROUGH the routed reconfiguration.

        The precedence contract has to hold where it actually operates: a
        provider-routed context being reconfigured. Exercising a bare
        StalenessChecker would only re-test an unchanged leaf that PR-5 does
        not touch, and would stay green even if reconfiguration ignored the
        supplied config entirely.
        """
        custom = tmp_path / "custom_store"
        supplied = SemanticIndexConfig(
            db_dir_name=str(custom / "db"),
            fingerprint_file=str(custom / "fp.json"),
        )

        context = _context_via_factory(routing)
        context.configure_semantic_search(
            config=supplied,
            state_manager=Mock(),
            decision_maker=Mock(),
        )

        checker = context._semantic_manager._staleness_checker
        assert checker is context._staleness_checker, (
            "reconfiguration forked the checker"
        )
        assert checker._fingerprint_path == custom / "fp.json"

        # The provider-bound default was displaced, not merged into.
        assert not checker._fingerprint_path.is_relative_to(routing.storage_root)

        # And the destination is real, not just computed.
        checker.update_fingerprints()
        assert (custom / "fp.json").exists(), (
            "fingerprints were not written where the caller asked"
        )

    def test_t18_supplied_relative_values_keep_todays_semantics(self, routing):
        """A relative value stays relative to the scan root and is NOT re-based.

        Also driven through the routed reconfiguration, so the relative case
        is proven at the same seam as the absolute one.
        """
        supplied = SemanticIndexConfig(fingerprint_file="custom_rel/fp.json")

        context = _context_via_factory(routing)
        context.configure_semantic_search(
            config=supplied,
            state_manager=Mock(),
            decision_maker=Mock(),
        )

        checker = context._semantic_manager._staleness_checker
        assert checker._fingerprint_path == routing.scan_project / "custom_rel/fp.json"
        assert not checker._fingerprint_path.is_relative_to(routing.storage_root)

        checker.update_fingerprints()
        assert checker._fingerprint_path.exists(), (
            "fingerprints were not written at the scan-relative destination"
        )

    def test_t18_default_valued_config_object_is_still_caller_supplied(self, routing):
        """The case that fails if anyone infers provenance by equality.

        This config's fields equal the class defaults, and it is supplied at
        the routed reconfiguration seam of a PROVIDER-BACKED context. That is
        the seam where equality-based rebinding would actually be written, so
        the proof is the destination reached, not the config's field values:
        rebinding on equality would move persistence under the storage root.
        """
        supplied = SemanticIndexConfig()
        assert supplied.fingerprint_file == SemanticIndexConfig().fingerprint_file

        context = _context_via_factory(routing)
        context.configure_semantic_search(
            config=supplied,
            state_manager=Mock(),
            decision_maker=Mock(),
        )

        checker = context._semantic_manager._staleness_checker
        assert checker is context._staleness_checker, (
            "reconfiguration forked the checker"
        )

        expected = routing.scan_project / SemanticIndexConfig().fingerprint_file
        assert checker._fingerprint_path == expected
        assert not checker._fingerprint_path.is_relative_to(routing.storage_root), (
            "a default-valued config was rebound to the provider by equality"
        )

        checker.update_fingerprints()
        assert expected.exists(), "fingerprints were not written as supplied"
        provider_default = Path(bind_storage_defaults(routing.provider).fingerprint_file)
        assert not provider_default.exists(), (
            "persistence landed at the provider destination anyway"
        )

    def test_t18_model_only_config_retains_its_own_storage_defaults(
        self, routing, monkeypatch
    ):
        """Setting only the model must not silently acquire provider binding.

        Driven to the real connection destination: the model subdirectory has
        to appear under the config's own default storage on the SCAN root,
        never under the provider, even though the context is provider-backed.
        """
        # Model selection must come from the supplied config, so no env override.
        monkeypatch.delenv("SEMANTIC_INDEX_EMBEDDING_MODEL", raising=False)
        connected = _stub_semantic_externals(monkeypatch)

        supplied = SemanticIndexConfig(embedding_model="bge-small")

        context = _context_via_factory(routing)
        context.configure_semantic_search(
            config=supplied,
            state_manager=Mock(),
            decision_maker=Mock(),
        )

        initializer = context._semantic_manager._create_default_initializer()

        class StubThread:
            shutdown_requested = False

        initializer._initialize_worker(StubThread())
        assert initializer.is_complete(), (
            f"initialization did not succeed: {initializer.get_error()}"
        )

        expected = routing.scan_project / SemanticIndexConfig().db_dir_name / "bge-small"
        assert expected in connected, f"model dir not connected: {connected}"
        assert not any(
            directory.is_relative_to(routing.storage_root) for directory in connected
        ), f"a model-only config acquired provider binding: {connected}"

    def test_t18_binder_never_mutates_and_covers_both_fields(self, routing):
        """The binder returns a new object and binds BOTH storage fields."""
        before_db = SemanticIndexConfig().db_dir_name
        before_fp = SemanticIndexConfig().fingerprint_file

        bound = bind_storage_defaults(routing.provider)

        assert SemanticIndexConfig().db_dir_name == before_db
        assert SemanticIndexConfig().fingerprint_file == before_fp
        assert Path(bound.db_dir_name).is_absolute()
        assert Path(bound.fingerprint_file).is_absolute()
        assert Path(bound.db_dir_name).is_relative_to(routing.storage_root)
        assert Path(bound.fingerprint_file).is_relative_to(routing.storage_root)

    def test_t18_binder_resolves_a_relative_provider_root(self, routing, monkeypatch):
        """A joined-but-relative value would never win the downstream join.

        Providers can hold a relative root, so binding must RESOLVE and not
        merely join. Without resolution the value stays relative, the
        absolute-wins seam never engages, and storage silently follows the
        scan root instead of the provider.
        """
        monkeypatch.chdir(routing.storage_root)
        relative_provider = TempPathProvider(Path("."))

        bound = bind_storage_defaults(relative_provider)

        assert Path(bound.db_dir_name).is_absolute(), (
            "binder produced a relative value; the absolute-wins seam cannot engage"
        )
        assert Path(bound.fingerprint_file).is_absolute()
        assert Path(bound.db_dir_name).is_relative_to(routing.storage_root)

        # And it actually wins the join a consumer performs.
        checker = StalenessChecker(root_path=routing.scan_project, config=bound)
        assert checker._fingerprint_path.is_relative_to(routing.storage_root)
        assert not checker._fingerprint_path.is_relative_to(routing.scan_project)

    def test_t18_injected_state_manager_keeps_its_destination(
        self, routing, tmp_path, monkeypatch
    ):
        """An injected storage dependency is never recomputed.

        The supplied state manager points somewhere the config does NOT: the
        config carries the provider-bound storage root, the state manager
        carries a separate custom directory. Dropping the explicit dependency
        would rebuild it from the config and open the provider directory
        instead, which the connection destination makes visible.
        """
        from scrappy.context.semantic import state as state_module

        connected = _stub_semantic_externals(monkeypatch)

        custom_db = tmp_path / "custom_state_store" / "db"
        supplied_state = state_module.LanceDBIndexStateManager(custom_db)
        routed_config = bind_storage_defaults(routing.provider)

        context = _context_via_factory(routing)
        context.configure_semantic_search(
            config=routed_config,
            state_manager=supplied_state,
            decision_maker=Mock(),
        )

        context._semantic_manager._state_manager._ensure_db()

        assert custom_db in connected, (
            f"the injected state manager's destination was not opened: {connected}"
        )
        assert Path(routed_config.db_dir_name) not in connected, (
            "the state manager was rebuilt from config instead of being honoured"
        )


class TestManagerReplacementSharesChecker:
    """T19: both replacement paths keep ONE checker and keep routing."""

    def _drive_and_read_persisted(self, context) -> Path:
        """Cause a real fingerprint update and return the file written."""
        checker = context._semantic_manager._staleness_checker
        checker.update_fingerprints()
        return checker._fingerprint_path

    def test_t19_configure_semantic_search_shares_checker_and_persists(self, routing):
        """Reconfiguration must not drop routing or fork the checker."""
        context = _context_via_factory(routing)
        config = bind_storage_defaults(routing.provider)

        context.configure_semantic_search(
            config=config,
            state_manager=Mock(),
            decision_maker=Mock(),
        )

        manager_checker = context._semantic_manager._staleness_checker
        assert manager_checker is context._staleness_checker, (
            "context and replacement manager hold different checkers"
        )

        persisted = self._drive_and_read_persisted(context)
        assert persisted.is_relative_to(routing.storage_root)
        assert persisted.exists(), "fingerprints were not persisted at the destination"

        # Behavioural, not attribute-only: a real refresh updates the file.
        first = persisted.read_text()
        (routing.scan_project / "added_after.py").write_text("ADDED = 1\n")
        context.explore(force=True)
        manager_checker.update_fingerprints()
        assert persisted.read_text() != first, "refresh did not update persisted state"

    def test_t19_factory_route_shares_checker_and_persists(self, routing, monkeypatch):
        """The factory route replaces the manager too, and must share as well.

        This is the only case here that starts real background work, so the
        external boundaries are stubbed offline BEFORE composition and the
        initializer is driven to completion and shut down before the test
        ends. Without that, this test would start an uncontrolled
        model-loading thread as a side effect of its own setup.
        """
        connected = _stub_semantic_externals(monkeypatch)
        _pin_embedding_model(monkeypatch)

        context = _context_via_factory(routing, semantic=True)
        try:
            manager_checker = context._semantic_manager._staleness_checker
            assert manager_checker is context._staleness_checker, (
                "factory route left the context and manager with different checkers"
            )

            persisted = self._drive_and_read_persisted(context)
            assert persisted.is_relative_to(routing.storage_root)
            assert persisted.exists()
        finally:
            _settle_background_init(context)

        # The stubs are load-bearing, not decoration: the background route
        # really did reach the intercepted boundary, so no real model load
        # or native database open happened on this path.
        assert connected, "background init never reached the stubbed boundary"
        assert all(
            directory.is_relative_to(routing.storage_root) for directory in connected
        ), f"background init opened a directory outside the injected storage: {connected}"

    def test_t19_user_injected_checker_survives_replacement(self, routing):
        """An originally injected checker is preserved, by explicit None handling."""
        injected = StalenessChecker(
            root_path=routing.scan_project,
            config=bind_storage_defaults(routing.provider),
        )
        context = CodebaseContext(
            str(routing.scan_project),
            path_provider=routing.provider,
            staleness_checker=injected,
        )

        context.configure_semantic_search(
            config=bind_storage_defaults(routing.provider),
            state_manager=Mock(),
            decision_maker=Mock(),
        )

        assert context._staleness_checker is injected, "user checker was discarded"
        assert context._semantic_manager._staleness_checker is injected


class TestFalseyInjectionsAreHonoured:
    """T20: a VALID but falsey injected dependency is still the caller's.

    `dependency or default` silently discards a working injected object
    whenever it is falsey, while the recorded `is not None` flag keeps
    claiming it was preserved. Every case here injects a falsey-but-working
    object and proves through BEHAVIOUR -- the destination actually reached --
    that the caller's object was used, never that an attribute points at it.

    These cover exactly the four branches this change promises to honour.
    """

    def test_t20_context_honours_a_falsey_injected_checker(self, routing, tmp_path):
        """CodebaseContext: the injected checker does the context's real work."""
        custom = tmp_path / "falsey_context_checker"
        injected = _FalseyStalenessChecker(
            root_path=routing.scan_project,
            config=SemanticIndexConfig(fingerprint_file=str(custom / "fp.json")),
        )
        assert not injected, "fixture is not falsey; this test would prove nothing"

        context = CodebaseContext(
            str(routing.scan_project),
            path_provider=routing.provider,
            staleness_checker=injected,
        )

        # Real production path: ensure_file_index() is what drives the
        # context's checker, establishing the fingerprint baseline.
        context.ensure_file_index()

        assert (custom / "fp.json").exists(), (
            "a falsey injected checker was replaced by a default"
        )
        provider_default = Path(bind_storage_defaults(routing.provider).fingerprint_file)
        assert not provider_default.exists(), (
            "the context fell back to the provider-bound default checker"
        )

    def test_t20_manager_honours_a_falsey_injected_config(
        self, routing, tmp_path, monkeypatch
    ):
        """SemanticSearchManager: the injected config still selects storage."""
        connected = _stub_semantic_externals(monkeypatch)

        custom = tmp_path / "falsey_config_store"
        supplied = _FalseySemanticIndexConfig(db_dir_name=str(custom / "db"))
        assert not supplied, "fixture is not falsey; this test would prove nothing"

        manager = SemanticSearchManager(
            project_path=routing.scan_project,
            config=supplied,
        )

        # Behaviour at the external boundary: the directory actually opened.
        manager._state_manager._ensure_db()

        assert custom / "db" in connected, (
            f"falsey config was replaced; connected to {connected}"
        )

    def test_t20_manager_honours_a_falsey_injected_checker(self, routing, tmp_path):
        """SemanticSearchManager: the injected checker persists where it says."""
        custom = tmp_path / "falsey_manager_checker"
        injected = _FalseyStalenessChecker(
            root_path=routing.scan_project,
            config=SemanticIndexConfig(fingerprint_file=str(custom / "fp.json")),
        )
        assert not injected, "fixture is not falsey; this test would prove nothing"

        manager = SemanticSearchManager(
            project_path=routing.scan_project,
            config=bind_storage_defaults(routing.provider),
            staleness_checker=injected,
        )

        manager._staleness_checker.update_fingerprints()

        assert (custom / "fp.json").exists(), (
            "a falsey injected checker was replaced by a default"
        )
        provider_default = Path(bind_storage_defaults(routing.provider).fingerprint_file)
        assert not provider_default.exists(), (
            "the manager built its own default checker instead"
        )

    def test_t20_router_honours_a_falsey_injected_path_provider(
        self, routing, tmp_path
    ):
        """CommandRouter: task handling reaches the injected provider's file.

        Falling back to the CWD-composed default would find no todo file at
        all, leave the injected one untouched, and return early.
        """
        store = tmp_path / "falsey_provider_store"
        store.mkdir()
        provider = _FalseyPathProvider(store)
        assert not provider, "fixture is not falsey; this test would prove nothing"

        todo = provider.todo_file()
        todo.parent.mkdir(parents=True, exist_ok=True)
        todo.write_text("- [ ] injected task\n")

        router = _router_with_provider(provider)
        router._handle_existing_tasks(Mock(), clear_tasks=True)

        assert not todo.exists() or "injected task" not in todo.read_text(), (
            "router fell back to a default provider instead of the injected one"
        )
