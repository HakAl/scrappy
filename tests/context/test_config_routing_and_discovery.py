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

import pytest

from scrappy.cli.commands import _select_config_at_entry
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
    for d in (code_root, other_cwd):
        d.mkdir()
    assert code_root.resolve() != other_cwd.resolve()
    monkeypatch.chdir(code_root)
    return type("Roots", (), {"code_root": code_root, "other_cwd": other_cwd})()


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

    selected = _select_config_at_entry()

    assert selected is not None, "a present config file must be selected"
    assert Path(selected).is_absolute(), "selection must be absolute, not CWD-relative"
    assert Path(selected).resolve() == expected.resolve()


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

    selected = _select_config_at_entry()
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

    assert _select_config_at_entry() is None


@pytest.mark.no_contained_config_seed
def test_entry_selection_preserves_missing_file_behaviour(roots, monkeypatch):
    """No candidate present must return None, not invent a path."""
    monkeypatch.delenv("CLI_CONFIG_PATH", raising=False)
    present = [n for n in CLIConfigFactory.DEFAULT_CONFIG_FILES
               if (roots.code_root / n).exists()]
    assert not present, f"fixture must start clean, found {present}"

    assert _select_config_at_entry() is None


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
