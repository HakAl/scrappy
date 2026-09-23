"""PR-7: configuration routing from command entry, and bounded rules discovery.

Two things are proved here and they are deliberately separate.

ROUTING. Configuration is selected ONCE at the command entry against the
captured code root and threaded down. The hazard is not theoretical: the
factory caches on its first uncached call and its default-file scan reads the
AMBIENT process directory, so whichever call lands first fixes the object for
the process. A test that supplies an object below the entry boundary cannot
detect that, which is why the entry selection is exercised directly.

DISCOVERY. ``max_depth`` is a LIMIT, a count of directories examined, and depth
is ZERO-BASED ANCESTOR DISTANCE. Limit N examines distances 0 through N-1.
These cases are stated literally rather than as "the edge", because an earlier
revision of the brief specified them off by one and would have pressured a
regression into the traversal.

An empty containment measurement cannot substitute for any of this: discovery
is a READ path, so a correct implementation and a broken one both leave the
profile region untouched.
"""

import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from scrappy.cli.commands import capture_configuration_at_entry
from scrappy.cli.config_factory import CLIConfigFactory, get_config, set_config
from scrappy.context.agent_rules_loader import AgentRulesLoader


# ---------------------------------------------------------------------------
# Distinct roots. Code root and CWD must never be the same directory here, or
# "selected against the code root" and "scanned from ambient CWD" would be
# indistinguishable, which is the exact mistake PR-6 had to correct.
# ---------------------------------------------------------------------------


@pytest.fixture
def roots(tmp_path, monkeypatch):
    code_root = tmp_path / "code_root"
    other_cwd = tmp_path / "other_cwd"
    storage_root = tmp_path / "storage_root"
    profile = tmp_path / "profile"
    for d in (code_root, other_cwd, storage_root, profile):
        d.mkdir()
    resolved = [str(d.resolve()) for d in (code_root, other_cwd, storage_root, profile)]
    assert len(set(resolved)) == 4, f"roots must be distinct, got {resolved}"
    # The profile GOVERNS home resolution for these tests, so it has an
    # exercised role rather than being a fourth named directory.
    monkeypatch.setenv("HOME", str(profile))
    monkeypatch.setenv("USERPROFILE", str(profile))
    monkeypatch.chdir(code_root)
    return type("Roots", (), {
        "code_root": code_root,
        "other_cwd": other_cwd,
        "storage_root": storage_root,
        "profile": profile,
    })()


def write_config(directory: Path, temperature: float) -> Path:
    """A real config file the production parser can read."""
    path = directory / ".scrappy.json"
    path.write_text(json.dumps({"temperature_default": temperature}))
    return path


# ---------------------------------------------------------------------------
# The seed itself must be shown to govern, or every test below that relies on
# "a DIFFERENT seeded global" is resting on an assumption.
# ---------------------------------------------------------------------------


def test_contained_seed_actually_governs_the_fallback_consumers():
    """The autouse seed reaches a consumer that takes no configuration.

    Non-vacuous by construction: the seeded value is an arbitrary sentinel no
    real configuration would carry, so observing it proves the seed arrived
    rather than that some default happened to match.
    """
    from tests.conftest import CONTAINED_CONFIG_SEED

    config = get_config()

    assert config.temperature_default == CONTAINED_CONFIG_SEED["temperature_default"]
    assert config.max_tokens_query == CONTAINED_CONFIG_SEED["max_tokens_query"]


# ---------------------------------------------------------------------------
# Entry selection. This is the hop the reviewer identified as missing: below it
# an ambient read has already cached the wrong object.
# ---------------------------------------------------------------------------


@pytest.mark.no_contained_config_seed
def test_entry_selects_against_the_code_root_and_returns_an_absolute_path(roots, monkeypatch):
    """Selection happens against the captured code root, resolved absolute."""
    monkeypatch.delenv("CLI_CONFIG_PATH", raising=False)
    expected = write_config(roots.code_root, 0.11)

    config, selected = capture_configuration_at_entry()

    assert selected is not None, "a present config file must be selected"
    assert Path(selected).is_absolute(), "selection must be absolute, not CWD-relative"
    assert Path(selected).resolve() == expected.resolve()
    assert config is not None, "an explicit selection must yield an OBJECT, not just a path"


@pytest.mark.no_contained_config_seed
def test_entry_selection_survives_a_later_cwd_change(roots, monkeypatch):
    """The captured selection must not be retargeted by moving the process.

    Both directories contain a DIFFERENT valid config file, so a re-read after
    the move resolves to the other one and this test fails. With only one file
    present the assertion could pass against a re-reading implementation.
    """
    monkeypatch.delenv("CLI_CONFIG_PATH", raising=False)
    from_code_root = write_config(roots.code_root, 0.11)
    write_config(roots.other_cwd, 0.99)

    _, selected = capture_configuration_at_entry()
    os.chdir(roots.other_cwd)

    assert Path(selected).resolve() == from_code_root.resolve(), (
        "selection was retargeted by the later CWD change"
    )


@pytest.mark.no_contained_config_seed
def test_entry_selection_yields_to_an_explicit_environment_selector(roots, monkeypatch):
    """CLI_CONFIG_PATH keeps its precedence; entry selection must not override it.

    Returning None is the mechanism: it leaves the factory to honour branch 2
    exactly as before, rather than this code re-implementing precedence.
    """
    write_config(roots.code_root, 0.11)
    monkeypatch.setenv("CLI_CONFIG_PATH", str(roots.other_cwd / "hostile.json"))

    # The environment names a file that does not exist. Production does NOT fall
    # through to the code-root scan in that case (branch 3 is an `else`), so no
    # explicit selection is captured and ordinary precedence yields defaults.
    config, selected = capture_configuration_at_entry()
    assert config is None and selected is None


@pytest.mark.no_contained_config_seed
def test_entry_selection_preserves_missing_file_behaviour(roots, monkeypatch):
    """No candidate present must return None, not invent a path."""
    monkeypatch.delenv("CLI_CONFIG_PATH", raising=False)
    present = [n for n in CLIConfigFactory.DEFAULT_CONFIG_FILES
               if (roots.code_root / n).exists()]
    assert not present, f"fixture must start clean, found {present}"

    config, selected = capture_configuration_at_entry()
    assert config is None and selected is None


# ---------------------------------------------------------------------------
# The chain below the entry, through the REAL factory and the REAL context.
# ---------------------------------------------------------------------------


@pytest.mark.no_contained_config_seed
def test_selected_object_reaches_the_real_context_through_the_real_factory(roots, monkeypatch):
    """Hops 4 to 7, with a DIFFERENT global seeded, after a CWD change.

    Two mechanisms make this non-vacuous. The seeded global differs from the
    selected object, so any hop that drops the object falls back to a value
    this test can distinguish. The CWD moves before the assertion, so any hop
    that re-derives selection from ambient state also fails.
    """
    from unittest.mock import Mock

    from scrappy.orchestrator.factory import OrchestratorFactory

    monkeypatch.delenv("CLI_CONFIG_PATH", raising=False)

    selected_path = write_config(roots.code_root, 0.11)
    selected = CLIConfigFactory().create_from_file(str(selected_path))

    # A DIFFERENT global, so a dropped object is detectable rather than masked.
    other_path = write_config(roots.other_cwd, 0.99)
    set_config(CLIConfigFactory().create_from_file(str(other_path)))
    assert get_config().temperature_default == 0.99

    factory = OrchestratorFactory(
        project_path=str(roots.code_root),
        cli_config=selected,
        enable_semantic_search=False,
        api_key_service=Mock(),
    )
    os.chdir(roots.other_cwd)
    context = factory.create_codebase_context()

    assert context._cli_config is selected, (
        "the selected object did not survive the factory hop"
    )
    assert context._cli_config.temperature_default == 0.11, (
        "the context observed the seeded global instead of the selected object"
    )


@pytest.mark.no_contained_config_seed
def test_cli_config_parameter_is_distinct_from_orchestrator_config(roots):
    """cli_config must not collide with the existing OrchestratorConfig field."""
    from unittest.mock import Mock

    from scrappy.orchestrator.config import OrchestratorConfig
    from scrappy.orchestrator.factory import OrchestratorFactory

    selected = CLIConfigFactory().create_from_file(str(write_config(roots.code_root, 0.11)))
    orch_config = OrchestratorConfig()

    factory = OrchestratorFactory(
        project_path=str(roots.code_root),
        config=orch_config,
        cli_config=selected,
        enable_semantic_search=False,
        api_key_service=Mock(),
    )

    assert factory.config is orch_config, "OrchestratorConfig was displaced"
    assert factory._cli_config is selected, "CLIConfig was displaced"


# ---------------------------------------------------------------------------
# Bounded discovery. max_depth is a LIMIT; depth is zero-based ancestor
# distance. Limit N examines distances 0 through N-1 inclusive.
# ---------------------------------------------------------------------------


def build_chain(root: Path, depth: int) -> Path:
    """Return a directory `depth` ancestors below `root`."""
    current = root
    for i in range(depth):
        current = current / f"level{i}"
    current.mkdir(parents=True, exist_ok=True)
    return current


@pytest.mark.no_contained_config_seed
@pytest.mark.parametrize("method", ["load", "discover_file"])
def test_limit_zero_finds_nothing_even_in_the_starting_directory(tmp_path, method):
    """A limit of zero examines NO directory, not one."""
    (tmp_path / "AGENTS.md").write_text("# rules\n")
    loader = AgentRulesLoader(max_depth=0)

    assert getattr(loader, method)(tmp_path) is None


@pytest.mark.no_contained_config_seed
@pytest.mark.parametrize("method", ["load", "discover_file"])
def test_limit_one_finds_the_starting_directory_and_excludes_its_parent(tmp_path, method):
    """A limit of one examines distance 0 only."""
    start = build_chain(tmp_path, 1)

    (start / "AGENTS.md").write_text("# start\n")
    loader = AgentRulesLoader(max_depth=1)
    assert getattr(loader, method)(start) is not None, "distance 0 must be examined"

    (start / "AGENTS.md").unlink()
    (tmp_path / "AGENTS.md").write_text("# parent\n")
    assert getattr(loader, method)(start) is None, "distance 1 is outside limit 1"


@pytest.mark.no_contained_config_seed
@pytest.mark.parametrize("method", ["load", "discover_file"])
def test_limit_n_finds_at_distance_n_minus_one_and_not_at_distance_n(tmp_path, method):
    """The general boundary, asserted in BOTH directions against one limit."""
    limit = 4
    start = build_chain(tmp_path, limit)

    inside = start
    for _ in range(limit - 1):
        inside = inside.parent
    (inside / "AGENTS.md").write_text("# inside\n")
    loader = AgentRulesLoader(max_depth=limit)
    assert getattr(loader, method)(start) is not None, (
        f"distance {limit - 1} is the last in-bounds ancestor and must be found"
    )

    (inside / "AGENTS.md").unlink()
    outside = inside.parent
    (outside / "AGENTS.md").write_text("# outside\n")
    assert getattr(loader, method)(start) is None, (
        f"distance {limit} is outside limit {limit} and must NOT be found"
    )


@pytest.mark.no_contained_config_seed
def test_nearest_directory_wins_over_an_ancestor(tmp_path):
    """Precedence between directories is unchanged by this work."""
    start = build_chain(tmp_path, 2)
    (tmp_path / "AGENTS.md").write_text("# far\n")
    (start / "AGENTS.md").write_text("# near\n")

    found = AgentRulesLoader(max_depth=10).discover_file(start)

    assert found is not None
    assert found.resolve() == (start / "AGENTS.md").resolve()


# ---------------------------------------------------------------------------
# F3: positional API compatibility. Adding an optional parameter in the wrong
# position silently REBINDS existing positional callers, and keyword-only tests
# cannot see it. These bind old-style calls and assert where each argument
# lands.
# ---------------------------------------------------------------------------


@pytest.mark.no_contained_config_seed
def test_factory_positional_semantic_search_flag_is_not_captured_by_cli_config():
    """An old positional enable_semantic_search=False must stay False.

    Behavioural, not just signature shape: the factory is really constructed
    with the flag in its historical positional slot.
    """
    import inspect
    from unittest.mock import Mock

    from scrappy.orchestrator.factory import OrchestratorFactory

    sig = inspect.signature(OrchestratorFactory.__init__)
    assert sig.parameters["cli_config"].kind is inspect.Parameter.KEYWORD_ONLY, (
        "cli_config must be keyword-only so it cannot absorb a positional flag"
    )

    factory = OrchestratorFactory(
        None,          # project_path
        24,            # cache_ttl_hours
        True,          # context_aware
        None,          # created_at
        None,          # path_provider
        None,          # config
        False,         # enable_semantic_search, the historical positional slot
        api_key_service=Mock(),
    )

    assert factory.enable_semantic_search is False, (
        "positional False was captured by the new parameter"
    )
    assert factory._cli_config is None




# ---------------------------------------------------------------------------
# F3: a REAL old-style positional construction, not signature inspection.
# All components are supplied so the injected-component branch runs and no
# factory work is performed.
# ---------------------------------------------------------------------------


@pytest.mark.no_contained_config_seed
def test_orchestrator_old_positional_call_still_binds_the_api_key_service():
    """An old positional api_key_service must reach the service, not cli_config.

    This CONSTRUCTS the orchestrator with arguments in their historical
    positional slots. If cli_config were reinserted before api_key_service the
    service would land on configuration and _api_key_service would default,
    which is a behaviour change no keyword-only test can see.
    """
    from unittest.mock import Mock

    from scrappy.orchestrator.core import AgentOrchestrator

    service = Mock(name="api_key_service")
    components = [Mock(name=f"component{i}") for i in range(16)]  # output..model_selector

    orchestrator = AgentOrchestrator(
        None,     # project_path
        True,     # context_aware
        True,     # enable_cache
        24,       # cache_ttl_hours
        False,    # enable_semantic_search
        None,     # quality_mode
        *components,
        None,     # path_provider
        service,  # api_key_service, historically the final positional slot
    )

    assert orchestrator._api_key_service is service, (
        "the positional service was captured by a later-inserted parameter"
    )


# ---------------------------------------------------------------------------
# F5: controlled configuration inputs, and restoration observed IMMEDIATELY.
# These drive tests/conftest.py's contained_cli_config_scope directly, so no
# assertion depends on test ordering and no later fixture setup can mask a
# restoration failure.
# ---------------------------------------------------------------------------


@pytest.mark.no_contained_config_seed
def test_hostile_selector_under_a_synthetic_home_is_rejected_and_not_consumed(
    tmp_path, monkeypatch, request
):
    """An inherited session label plus an ordinary HOME is NOT provenance.

    This reproduces the case the previous predicate accepted: a NONEMPTY
    inherited SCRAPPY_TEST_SESSION_ID (the launcher itself adopts inherited
    labels, contained-pytest.sh:72-78), a synthetic stand-in for an
    uncontrolled real home, and a VALID conflicting configuration file inside
    it. None of that is the repository-owned disposable profile.

    Rejection alone is not enough, so this also proves the file is NOT
    CONSUMED: it drives the real get_config reload path and asserts the hostile
    marker never appears. theme_config is used deliberately because it SURVIVES
    current merge semantics, unlike a scalar such as temperature_default which
    the environment merge overwrites regardless (scrappy-bj58).
    """
    from scrappy.cli.config_factory import get_config
    from tests.conftest import contained_cli_config_scope

    fake_home = tmp_path / "synthetic_real_home"
    fake_home.mkdir()
    hostile = fake_home / ".scrappy.json"
    hostile.write_text(json.dumps({"theme_config": {"preset": "hostile-marker"}}))

    # A SYNTHETIC disposable repository root. Under the contained launcher the
    # real tmp_path already lives inside <repo>/.pytest_profile, so anchoring on
    # the live root would make this "outside" directory genuinely inside it and
    # the test would assert nothing.
    synthetic_repo = tmp_path / "synthetic_repo"
    (synthetic_repo / ".pytest_profile").mkdir(parents=True)

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("SCRAPPY_TEST_SESSION_ID", "inherited-label")
    monkeypatch.setenv("CLI_CONFIG_PATH", str(hostile))

    with contained_cli_config_scope(
        tmp_path / "disposable", seed=False, repo_root=synthetic_repo
    ):
        assert Path(os.environ["CLI_CONFIG_PATH"]) != hostile, (
            "an inherited label plus HOME membership was accepted as provenance"
        )
        reloaded = get_config(reload=True)
        assert reloaded.theme_config.get("preset") != "hostile-marker", (
            "the hostile configuration was actually CONSUMED through reload"
        )

    assert os.environ["CLI_CONFIG_PATH"] == str(hostile), "original selector not restored"


@pytest.mark.no_contained_config_seed
def test_repository_owned_launcher_selector_is_preserved_and_consumed(tmp_path, monkeypatch, request):
    """POSITIVE case: a genuine launcher assignment is kept and remains usable.

    Anchored to the real layout, REPO_ROOT/.pytest_profile/<session>/home/...,
    rather than to HOME membership. Disposable throughout: the file lives under
    the repository-owned profile directory and is removed with it.
    """
    from scrappy.cli.config_factory import get_config
    from tests.conftest import contained_cli_config_scope

    # Synthetic disposable repository root, mirroring the launcher's real
    # layout REPO_ROOT/.pytest_profile/<session>/home/. Nothing is written into
    # the live .pytest_profile, which the containment baseline measures.
    synthetic_repo = tmp_path / "synthetic_repo"
    legit_dir = synthetic_repo / ".pytest_profile" / "session" / "home" / ".config" / "scrappy"
    legit_dir.mkdir(parents=True)
    legit = legit_dir / "contained-cli-config.json"
    legit.write_text(json.dumps({"theme_config": {"preset": "launcher-marker"}}))

    monkeypatch.setenv("CLI_CONFIG_PATH", str(legit))

    with contained_cli_config_scope(
        tmp_path / "disposable", seed=False, repo_root=synthetic_repo
    ):
            assert os.environ["CLI_CONFIG_PATH"] == str(legit), (
                "a repository-owned launcher assignment must be preserved"
            )
            reloaded = get_config(reload=True)
            assert reloaded.theme_config.get("preset") == "launcher-marker", (
                "the legitimate launcher selection was not usable"
            )


@pytest.mark.no_contained_config_seed
def test_symlink_escape_out_of_the_profile_is_rejected(tmp_path, monkeypatch, request):
    """A selector INSIDE the profile that symlinks OUT of it must be rejected.

    Membership by unresolved path is not containment: both sides are resolved
    before comparison, so the escape is caught.
    """
    from tests.conftest import contained_cli_config_scope

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "escaped.json").write_text(json.dumps({"theme_config": {"preset": "escaped"}}))

    synthetic_repo = tmp_path / "synthetic_repo"
    profile = synthetic_repo / ".pytest_profile"
    profile.mkdir(parents=True)
    link = profile / "link-to-outside"
    link.symlink_to(outside, target_is_directory=True)

    monkeypatch.setenv("CLI_CONFIG_PATH", str(link / "escaped.json"))

    with contained_cli_config_scope(
        tmp_path / "disposable", seed=False, repo_root=synthetic_repo
    ):
            inside = Path(os.environ["CLI_CONFIG_PATH"]).resolve()
            assert not inside.is_relative_to(outside.resolve()), (
                "a symlink escape out of the profile was accepted"
            )


@pytest.mark.no_contained_config_seed
def test_scope_restores_non_none_global_and_factory_cache_immediately(tmp_path):
    """Restoration observed the instant the scope exits.

    Both saved values are deliberately NON-None, so a teardown that merely
    clears rather than restores is detected. The ordered-pair form this
    replaces could not do that: the next test's own setup reseeded before it
    could look.
    """
    from scrappy.cli import config_factory as cf
    from tests.conftest import contained_cli_config_scope

    prior = cf.CLIConfigFactory().create_from_file(str(write_config(tmp_path, 0.31)))
    cf.set_config(prior)
    cf._factory._cached_config = prior

    with contained_cli_config_scope(tmp_path / "disposable", seed=True):
        assert cf._global_config is not prior, "scope did not take over the global"

    assert cf._global_config is prior, "global was cleared instead of restored"
    assert cf._factory._cached_config is prior, "factory cache was cleared instead of restored"


@pytest.mark.no_contained_config_seed
def test_scope_restores_even_when_setup_fails(tmp_path, monkeypatch):
    """A failure during seeding must still restore everything.

    Failure is injected at the external boundary the scope calls during setup,
    so the exception arrives before the body would run.
    """
    from scrappy.cli import config_factory as cf
    from tests.conftest import contained_cli_config_scope

    prior = cf.CLIConfigFactory().create_from_file(str(write_config(tmp_path, 0.31)))
    cf.set_config(prior)
    cf._factory._cached_config = prior
    saved_env = os.environ.get("CLI_CONFIG_PATH")

    def boom(*a, **k):
        raise RuntimeError("injected setup failure")

    monkeypatch.setattr(cf.CLIConfigFactory, "create_from_file", boom)

    with pytest.raises(RuntimeError, match="injected setup failure"):
        with contained_cli_config_scope(tmp_path / "disposable", seed=True):
            pytest.fail("body must not run when setup fails")

    assert cf._global_config is prior, "global not restored after setup failure"
    assert cf._factory._cached_config is prior, "factory cache not restored after setup failure"
    assert os.environ.get("CLI_CONFIG_PATH") == saved_env, "selector not restored"


# ---------------------------------------------------------------------------
# F2/F4: the capture must survive a DIFFERENT CACHED GLOBAL, and must reach a
# real consumer through the real entry. These drive the actual Click group and
# the real CLI composition rather than asserting below the entry boundary.
#
# The marker rides on theme_config deliberately: it SURVIVES current merge
# semantics, while scalars are overwritten by the environment merge regardless
# (scrappy-bj58, out of scope here). A scalar marker would prove nothing.
# ---------------------------------------------------------------------------


# Distinct primary colours per marker, so resolving config.theme is a real
# OPERATION with observable output rather than a field read.
MARKER_COLOURS = {
    "from-code-root": "magenta",
    "from-elsewhere": "green",
    "rewritten-after-main-captured": "yellow",
    "from-environment": "blue",
}


def write_marked_config(directory: Path, marker: str) -> Path:
    path = directory / ".scrappy.json"
    theme = {"preset": marker}
    if marker in MARKER_COLOURS:
        theme["primary"] = MARKER_COLOURS[marker]
    path.write_text(json.dumps({"theme_config": theme}))
    return path


@pytest.mark.no_contained_config_seed
def test_capture_wins_over_a_different_already_cached_global(roots, monkeypatch):
    """THE F2 CACHE CONFLICT, proven.

    get_config(config_path=...) does NOT replace an already-cached global, so a
    path-based selection loses to whatever was cached earlier. The capture
    returns an OBJECT, so it wins. Both a conflicting cached global AND a valid
    conflicting file elsewhere are present, so a dropped capture is detectable.
    """
    monkeypatch.delenv("CLI_CONFIG_PATH", raising=False)
    write_marked_config(roots.code_root, "from-code-root")
    other = write_marked_config(roots.other_cwd, "from-elsewhere")

    set_config(CLIConfigFactory().create_from_file(str(other)))
    assert get_config().theme_config["preset"] == "from-elsewhere"

    captured, _ = capture_configuration_at_entry()

    assert captured is not None, "no explicit selection was captured"
    assert captured.theme_config["preset"] == "from-code-root", (
        "the capture lost to the already-cached global"
    )
    # get_config cache/reload semantics are deliberately NOT changed by this.
    assert get_config().theme_config["preset"] == "from-elsewhere", (
        "capturing must not mutate the cached global"
    )


@pytest.mark.no_contained_config_seed
def test_environment_selection_is_resolved_and_retained_by_the_capture(roots, monkeypatch):
    """CLI_CONFIG_PATH keeps precedence AND is resolved into the capture.

    Previously the helper returned None whenever the variable was set, which
    ceded control to ambient discovery and left the two entry points deriving
    their own answers.
    """
    env_file = write_marked_config(roots.other_cwd, "from-environment")
    write_marked_config(roots.code_root, "from-code-root")
    monkeypatch.setenv("CLI_CONFIG_PATH", str(env_file))

    captured, selected = capture_configuration_at_entry()

    assert selected is not None and Path(selected).is_absolute()
    assert Path(selected).resolve() == env_file.resolve(), (
        "the environment selection was not resolved and retained"
    )
    assert captured.theme_config["preset"] == "from-environment", (
        "environment precedence over the code-root scan was not preserved"
    )


@pytest.mark.no_contained_config_seed
def test_real_click_entry_forwards_one_capture_to_the_deferred_helper(roots, monkeypatch):
    """ENTRY PROOF: the REAL Click group runs and hands on the SAME capture.

    Invoked through click.testing.CliRunner, so the production group callback
    executes. start_tui_deferred is recorded rather than run, because it would
    launch a TUI; everything up to that handoff is real.
    """
    from click.testing import CliRunner

    from scrappy.cli import commands as commands_module

    monkeypatch.delenv("CLI_CONFIG_PATH", raising=False)
    write_marked_config(roots.code_root, "from-code-root")
    other = write_marked_config(roots.other_cwd, "from-elsewhere")
    set_config(CLIConfigFactory().create_from_file(str(other)))

    seen = {}

    def recording_start(ctx, theme, resume=False, cli_config=None):
        seen["cli_config"] = cli_config

    monkeypatch.setattr(commands_module, "start_tui_deferred", recording_start)

    result = CliRunner().invoke(commands_module.cli, [], obj={})

    assert result.exit_code == 0, f"Click entry failed: {result.output}"
    assert seen.get("cli_config") is not None, (
        "the real Click entry forwarded no captured configuration"
    )
    assert seen["cli_config"].theme_config["preset"] == "from-code-root", (
        "the entry forwarded the cached global instead of its own capture"
    )


@pytest.mark.no_contained_config_seed
def test_captured_config_reaches_the_real_interactive_consumer(roots, monkeypatch):
    """CONSUMER PROOF: the captured object reaches the real interactive mode.

    Builds a REAL CLI through the production composition and drives the real
    _create_interactive_mode, so the object is observed where a consumer
    actually receives it. A conflicting global is cached and the CWD moves
    afterwards, so a dropped capture or an ambient re-read both fail.
    """
    from scrappy.cli.core import CLI
    from scrappy.infrastructure.paths import TempPathProvider
    from tests.cli.helpers import MockApiKeyConfigService

    monkeypatch.delenv("CLI_CONFIG_PATH", raising=False)
    write_marked_config(roots.code_root, "from-code-root")
    other = write_marked_config(roots.other_cwd, "from-elsewhere")
    set_config(CLIConfigFactory().create_from_file(str(other)))

    os.chdir(roots.code_root)
    captured, _ = capture_configuration_at_entry()
    assert captured is not None

    cli = CLI(
        orchestrator=Mock(),
        io=Mock(),
        api_key_service=MockApiKeyConfigService(),
        path_provider=TempPathProvider(roots.other_cwd),
        cli_config=captured,
    )
    os.chdir(roots.other_cwd)

    interactive = cli._create_interactive_mode()

    assert interactive._config is captured, (
        "the interactive consumer did not receive the captured object"
    )
    assert interactive._config.theme_config["preset"] == "from-code-root", (
        "the consumer observed the cached global instead of the selection"
    )


# ---------------------------------------------------------------------------
# F4 continuation: the COMPOSED route, end to end.
#
# Runs main(), the real Click callback, the real deferred closure, the real
# create_cli_from_context and a real consumer. Only genuinely external
# boundaries are replaced: the TUI app, provider probing, the API key service
# and the path provider. Dropping cli_config anywhere along that chain fails
# here, which the earlier tests could not detect because they stopped before
# the closure or bypassed it.
# ---------------------------------------------------------------------------


def run_main_capturing_the_deferred_factory(monkeypatch, roots):
    """Drive the REAL main() -> Click -> start_tui_deferred chain.

    Returns the cli_factory closure that production built, without launching a
    TUI. The app itself is the external boundary being replaced; every step up
    to and including the closure's construction is production code.
    """
    import sys

    from scrappy.cli import commands as commands_module
    from scrappy.infrastructure.paths import TempPathProvider
    from tests.cli.helpers import MockApiKeyConfigService

    captured = {}

    class RecordingApp:
        def __init__(self, cli_factory=None, **kwargs):
            captured["factory"] = cli_factory

        def run(self):
            captured["ran"] = True

    monkeypatch.setattr("scrappy.cli.textual.app.ScrappyApp", RecordingApp)
    monkeypatch.setattr(
        "scrappy.orchestrator.api_key_composition.create_api_key_service",
        lambda *a, **k: MockApiKeyConfigService(),
    )
    # The disposable PROFILE governs the user-path route here; storage_root
    # stays the storage role, so the two are not conflated.
    monkeypatch.setattr(
        "scrappy.infrastructure.paths.create_default_path_provider",
        lambda *a, **k: TempPathProvider(roots.profile),
    )
    # NARROWED. Only provider probing is replaced, which is the genuinely
    # external operation. initialize() itself still runs, so conversation and
    # command-history loading execute for real against the injected provider.
    # Replacing initialize wholesale would have skipped application
    # orchestration and been wrong to describe as external I/O only.
    monkeypatch.setattr("scrappy.cli.core.CLI._initialize_orchestrator", lambda self: None)
    monkeypatch.setattr(sys, "argv", ["scrappy"])

    try:
        commands_module.main()
    except SystemExit as exc:
        assert exc.code in (0, None), f"main() exited with {exc.code}"

    assert captured.get("factory") is not None, "main() never reached the deferred factory"
    return captured["factory"]


@pytest.mark.no_contained_config_seed
def test_main_capture_reaches_the_real_deferred_cli_and_consumer(roots, monkeypatch):
    """COMPOSED PROOF: main's selection survives to a real consumer.

    Hostile inputs are present throughout: a DIFFERENT valid config elsewhere, a
    DIFFERENT object already cached in the global, and a CWD change after main
    has run but before the deferred factory executes. Dropping cli_config at any
    hop, or re-selecting later, yields the wrong marker here.
    """
    monkeypatch.delenv("CLI_CONFIG_PATH", raising=False)
    write_marked_config(roots.code_root, "from-code-root")
    other = write_marked_config(roots.other_cwd, "from-elsewhere")
    set_config(CLIConfigFactory().create_from_file(str(other)))

    # CHANGE A CONTROLLED INPUT BETWEEN main's CAPTURE AND THE CLICK CALLBACK.
    # Without this the callback would re-select from the same directory and
    # reach the same answer, so a discarded capture would be undetectable.
    #
    # The seam is the Click invocation itself: main() resolves `cli` from module
    # globals at call time, so wrapping it fires AFTER main has captured and
    # validated, and BEFORE the callback could select again. An earlier attempt
    # hooked CLIConfig.validate, which is wrong: validate fires eight times
    # during a single capture, the first before the file is even read, so it
    # rewrote the input too early and the capture itself saw the new value.
    from scrappy.cli import commands as commands_module

    real_cli = commands_module.cli
    rewritten = {"done": False}

    def cli_after_inputs_change(*args, **kwargs):
        rewritten["done"] = True
        write_marked_config(roots.code_root, "rewritten-after-main-captured")
        return real_cli(*args, **kwargs)

    monkeypatch.setattr(commands_module, "cli", cli_after_inputs_change)

    os.chdir(roots.code_root)
    factory = run_main_capturing_the_deferred_factory(monkeypatch, roots)
    assert rewritten["done"], "the input-change seam never fired"

    # The deferred factory runs LATER, from a different directory.
    os.chdir(roots.other_cwd)
    cli = factory()

    assert cli._cli_config is not None, "the capture never reached the deferred CLI"
    assert cli._cli_config.theme_config["preset"] == "from-code-root", (
        "the deferred CLI used a re-selection or the cached global, not main's "
        "capture: seeing 'rewritten-after-main-captured' means the capture was "
        "discarded and Click selected again"
    )

    # A REAL consumer, composed by the CLI itself, exercised through a real
    # OPERATION rather than a field read: resolving .theme runs
    # load_theme_from_config and yields a theme whose primary colour differs per
    # selection. A consumer that ignored _config and read the ambient global
    # would resolve the global's colour instead.
    interactive = cli._create_interactive_mode()
    resolved_theme = interactive._config.theme
    assert resolved_theme.primary == MARKER_COLOURS["from-code-root"], (
        "the interactive consumer resolved a theme from the wrong configuration"
    )
    assert resolved_theme.primary != MARKER_COLOURS["from-elsewhere"], (
        "the consumer resolved the cached global's theme"
    )
    assert resolved_theme.primary != MARKER_COLOURS["rewritten-after-main-captured"], (
        "the consumer resolved a re-selection made after main captured"
    )

    # The disposable PROFILE genuinely governs the user-path route, so it is an
    # exercised role rather than a fourth named directory.
    user_path = Path(cli._path_provider.command_history_file())
    assert user_path.is_relative_to(roots.profile), (
        f"user paths did not resolve under the disposable profile: {user_path}"
    )


@pytest.mark.no_contained_config_seed
def test_empty_environment_selector_preserves_production_precedence(roots, monkeypatch):
    """An EMPTY CLI_CONFIG_PATH must behave as production does.

    The factory tests PRESENCE (config_factory.py:151-152), so an empty value
    selects Path(''), fails to load and retains defaults plus environment
    merging. It must NOT fall through to the code-root scan. Testing truthiness
    here would have loaded the code-root file and silently changed precedence.
    """
    write_marked_config(roots.code_root, "from-code-root")
    monkeypatch.setenv("CLI_CONFIG_PATH", "")

    captured, _ = capture_configuration_at_entry()

    # Path('') resolves to a DIRECTORY that exists, so neither production nor the
    # capture returns None here: both attempt it, fail to parse and retain
    # defaults plus environment merging. What must NOT happen is falling through
    # to the code-root scan and loading that file.
    captured_preset = None if captured is None else captured.theme_config.get("preset")
    assert captured_preset != "from-code-root", (
        "an empty environment selector fell through to the code-root scan"
    )

    # Production comparison, asserted rather than assumed.
    produced = CLIConfigFactory().create()
    assert produced.theme_config.get("preset") != "from-code-root"
    assert captured_preset == produced.theme_config.get("preset"), (
        "the capture and production disagree on the empty-selector edge case"
    )


@pytest.mark.no_contained_config_seed
def test_real_scanner_honours_an_explicitly_parsed_config_under_hostile_inputs(
    roots, monkeypatch
):
    """REAL SCANNER OUTCOME from a directly parsed configuration.

    Covers two obligations at once: direct create_from_file under HOSTILE
    controlled environment inputs, and real context/scanner behaviour driven by
    the resulting object rather than by the ambient global.

    create_from_file is used deliberately: it bypasses the environment merge, so
    the file's extension LISTS survive. Through create() they would be
    overwritten by environment defaults (scrappy-bj58), which stays out of scope
    and is not modified here.

    The outcome is observable rather than inspected: a file whose suffix only
    the injected configuration treats as Python is indexed, and a genuine .py
    file is not.
    """
    from scrappy.context.codebase_context import CodebaseContext
    from scrappy.infrastructure.paths import TempPathProvider

    selected_file = roots.code_root / "selected.json"
    selected_file.write_text(json.dumps({
        "python_extensions": [".xyz"],
        "theme_config": {"preset": "from-code-root", "primary": "magenta"},
    }))

    # HOSTILE ambient inputs: a conflicting environment selector pointing at a
    # valid file, and a conflicting object already cached in the global.
    hostile = write_marked_config(roots.other_cwd, "from-elsewhere")
    monkeypatch.setenv("CLI_CONFIG_PATH", str(hostile))
    set_config(CLIConfigFactory().create_from_file(str(hostile)))

    parsed = CLIConfigFactory().create_from_file(str(selected_file))
    assert parsed.python_extensions == [".xyz"], (
        "direct parsing did not retain the file's extension list"
    )

    (roots.code_root / "probe.xyz").write_text("# indexed only under the selection\n")
    (roots.code_root / "probe.py").write_text("# indexed only under the default\n")

    context = CodebaseContext(
        str(roots.code_root),
        path_provider=TempPathProvider(roots.profile),
        cli_config=parsed,
    )
    context.explore()
    indexed = context.file_index.get("python", [])

    assert "probe.xyz" in indexed, (
        f"the scanner ignored the injected configuration; indexed {indexed}"
    )
    assert "probe.py" not in indexed, (
        f"the scanner fell back to ambient defaults; indexed {indexed}"
    )


@pytest.mark.no_contained_config_seed
def test_direct_click_fallback_reaches_the_same_consumer_boundary(roots, monkeypatch):
    """Direct Click entry, with NO main above it, through the same consumer.

    The callback must select for itself and the selection must reach the same
    real interactive consumer, resolved as a theme operation. A conflicting
    global is cached and a hostile environment selector is absent here so the
    code-root scan is the path under test.
    """
    from click.testing import CliRunner

    from scrappy.cli import commands as commands_module
    from scrappy.cli.core import CLI
    from scrappy.infrastructure.paths import TempPathProvider
    from tests.cli.helpers import MockApiKeyConfigService

    monkeypatch.delenv("CLI_CONFIG_PATH", raising=False)
    write_marked_config(roots.code_root, "from-code-root")
    other = write_marked_config(roots.other_cwd, "from-elsewhere")
    set_config(CLIConfigFactory().create_from_file(str(other)))

    seen = {}

    def recording_start(ctx, theme, resume=False, cli_config=None):
        seen["cli_config"] = cli_config

    monkeypatch.setattr(commands_module, "start_tui_deferred", recording_start)

    os.chdir(roots.code_root)
    result = CliRunner().invoke(commands_module.cli, [], obj={})
    assert result.exit_code == 0, f"direct Click entry failed: {result.output}"

    captured = seen.get("cli_config")
    assert captured is not None, "direct Click entry captured nothing"

    # Same consumer boundary as the main() route.
    cli = CLI(
        orchestrator=Mock(),
        io=Mock(),
        api_key_service=MockApiKeyConfigService(),
        path_provider=TempPathProvider(roots.profile),
        cli_config=captured,
    )
    os.chdir(roots.other_cwd)

    resolved_theme = cli._create_interactive_mode()._config.theme
    assert resolved_theme.primary == MARKER_COLOURS["from-code-root"], (
        "the direct Click selection did not reach the consumer's theme resolution"
    )
