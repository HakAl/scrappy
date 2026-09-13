"""Tests for profile seeding (plan 3d, D-6)."""

import sys
from pathlib import Path

import pytest

from tests.containment import manifest, seed


def _contained_home(tmp_path: Path, monkeypatch) -> Path:
    """A disposable home with HOME/XDG pointed at it so platformdirs resolves inside it.

    The ``.pytest_profile`` segment is LOAD-BEARING and must be built here rather than
    inherited from the launcher's basetemp. This helper points HOME at the region itself,
    so ensure_disposable()'s real-home test can never accept it: ``Path.home()`` resolves
    to exactly the path being guarded. The marker is the only route by which this region
    is disposable, which makes it independent of where the checkout lives.

    HOME and XDG contain the lookup on POSIX only; see the Windows branch below for why
    that platform needs the OS folder lookup itself mocked.
    """
    home = tmp_path / ".pytest_profile" / "sid" / "home"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))

    if sys.platform == "win32":
        # On Windows NONE of the assignments above reach platformdirs. It binds and
        # lru_cache-wraps its folder resolver at IMPORT time (platformdirs/windows.py:274)
        # and the implementation selected whenever ctypes.windll exists is
        # get_win_folder_via_ctypes, which asks the OS through SHGetFolderPathW.
        # LOCALAPPDATA is read only by get_win_folder_from_env_vars, the FALLBACK used when
        # neither ctypes.windll nor winreg can be imported, so setting that variable would
        # not contain anything on a real runner (scrappy-k5gy).
        #
        # Replacing the module-level callable is the seam that does contain it: the call
        # sites resolve the global at call time (windows.py:75), so substituting the cached
        # object sidesteps the lru_cache instead of fighting it, and every folder id is
        # answered from the disposable region rather than only the one under test.
        #
        # ONLY the OS lookup is mocked. The seeding, the filesystem writes, the hashes and
        # the manifest comparison all stay REAL, so Windows keeps genuine unit coverage.
        from platformdirs import windows as platformdirs_windows

        appdata = home / "AppData" / "Local"
        appdata.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            platformdirs_windows, "get_win_folder", lambda _csidl_name: str(appdata)
        )

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


def test_the_contained_home_carries_its_own_marker(tmp_path, monkeypatch):
    """CI regression: the seed home must CONTRIBUTE the marker, not inherit it.

    This helper points HOME at the region itself, so ensure_disposable()'s real-home branch
    matches it EXACTLY and can never accept it. The marker is therefore the only route by
    which the seed region is disposable, and without it these three tests fail on every
    platform once pytest runs outside the launcher, as CI showed.

    The assertion is on the path RELATIVE to ``tmp_path`` because under the launcher every
    absolute path already sits inside a ``.pytest_profile`` region; an absolute check would
    pass vacuously here and still fail in CI.
    """
    home = _contained_home(tmp_path, monkeypatch)
    relative = home.relative_to(tmp_path)
    assert manifest.CONTAINMENT_MARKER in relative.parts, (
        f"the helper must place the seed home under a {manifest.CONTAINMENT_MARKER} segment "
        f"of its own; got {relative}, which is disposable only by inheritance"
    )
    assert manifest.ensure_disposable(home) == home.resolve()


# A path that CANNOT exist and carries no marker, standing in for the developer's real
# home. Never created: the assertions below prove the guard refuses before any mkdir.
ORIGINAL_HOME = Path("/nonexistent-original-home-for-guard-test")


def test_the_guard_refuses_the_original_home_after_redirection(tmp_path, monkeypatch):
    """scrappy-641n: the ORIGINAL home stays refused once HOME has been redirected.

    The guard used to accept any path not nested under the CURRENT Path.home(). Under the
    launcher that inverts, and the launcher is the only place the guard matters: HOME is
    by then the DISPOSABLE home, so the original home is not nested under it and was
    ACCEPTED. The guard protected the disposable profile from the real one, exactly
    backwards, and seed_profile(original_home) would have overwritten the developer's own
    ~/.scrappy/command_history, which is the R1 damage this instrument exists to measure.

    The two homes are kept SEPARATE and SYNTHETIC, per the finding. Asserting the original
    is still absent afterwards is what proves the refusal landed BEFORE any creation
    rather than after it.
    """
    redirected = _contained_home(tmp_path, monkeypatch)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: redirected))

    # Not vacuous: the redirected home IS disposable and is still accepted.
    assert manifest.ensure_disposable(redirected) == redirected.resolve()

    # The original home is refused even though it lies nowhere near the redirected one,
    # which is precisely the case the old ambient rule let through.
    with pytest.raises(manifest.RealProfileAccessError):
        manifest.ensure_disposable(ORIGINAL_HOME)
    with pytest.raises(manifest.RealProfileAccessError):
        seed.seed_profile(ORIGINAL_HOME)

    assert not ORIGINAL_HOME.exists(), "the guard must refuse BEFORE creating anything"
