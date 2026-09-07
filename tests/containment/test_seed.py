"""Tests for profile seeding (plan 3d, D-6)."""

from pathlib import Path

from tests.containment import manifest, seed


def _contained_home(tmp_path: Path, monkeypatch) -> Path:
    """A disposable home with HOME/XDG pointed at it so platformdirs resolves inside it."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    return home


def test_seed_writes_known_content_and_size(tmp_path, monkeypatch):
    home = _contained_home(tmp_path, monkeypatch)
    seeded = seed.seed_profile(home)

    history = seed.command_history_file(home)
    assert history.read_bytes() == seed.COMMAND_HISTORY_BYTES
    rel_history = history.relative_to(home).as_posix()
    assert seeded[rel_history]["size"] == len(seed.COMMAND_HISTORY_BYTES)

    config = seed.platform_config_file()
    assert config.read_bytes() == seed.CONFIG_JSON_BYTES
    # The seed must land INSIDE the measured region, otherwise the manifest never sees it
    # and an application overwrite of the real config would go unnoticed.
    assert home.resolve() in config.resolve().parents
    rel_config = config.resolve().relative_to(home.resolve()).as_posix()
    assert seeded[rel_config]["size"] == len(seed.CONFIG_JSON_BYTES)


def test_seed_does_not_write_rate_limits(tmp_path, monkeypatch):
    """PR-1 must NOT seed rate_limits.json (scrappy-cktc, turns on in PR-4)."""
    home = _contained_home(tmp_path, monkeypatch)
    seed.seed_profile(home)
    assert not (home / ".scrappy" / "rate_limits.json").exists()
    for path in home.rglob("rate_limits.json"):
        raise AssertionError(f"rate_limits.json must not be seeded, found {path}")


def test_seeded_manifest_matches_snapshot(tmp_path, monkeypatch):
    home = _contained_home(tmp_path, monkeypatch)
    seeded = seed.seed_profile(home)

    observed = manifest.snapshot(home, hashed=set(seeded))
    for rel, expected in seeded.items():
        assert observed[rel]["size"] == expected["size"]
        assert observed[rel]["sha256"] == expected["sha256"]
