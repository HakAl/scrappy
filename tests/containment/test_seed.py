"""Tests for profile seeding (plan 3d, D-6)."""

import hashlib
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
    """The DEFAULT call must NOT seed rate_limits.json, and must stay two-file.

    A1. Extended for the opt-in parameter (scrappy-i2jo). This is the guard that the
    two-file DEFAULT CONTRACT did not shift: the rglob proves no rate-limits file
    appears anywhere under the measured home, and the key-set assertion proves the
    RETURNED manifest still carries exactly the two historical entries. Without the
    second half, an implementation that seeded the file outside the home, or that
    returned a third manifest entry, could still pass.
    """
    home = _contained_home(tmp_path, monkeypatch)
    seeded = seed.seed_profile(home)
    assert not (home / ".scrappy" / "rate_limits.json").exists()
    for path in home.rglob("rate_limits.json"):
        raise AssertionError(f"rate_limits.json must not be seeded, found {path}")

    # EXACT historical key set, not a count. A renamed or substituted key of the same
    # cardinality would pass a count check and fail here.
    expected_keys = {
        seed.command_history_file(home).relative_to(home).as_posix(),
        seed.platform_config_file().resolve().relative_to(home.resolve()).as_posix(),
    }
    assert set(seeded) == expected_keys, (
        f"default contract must be exactly {sorted(expected_keys)}, got {sorted(seeded)}"
    )


def test_seeded_manifest_matches_snapshot(tmp_path, monkeypatch):
    """A2. Extended to assert the DEFAULT manifest is unchanged by the new parameter."""
    home = _contained_home(tmp_path, monkeypatch)
    seeded = seed.seed_profile(home)

    observed = manifest.snapshot(home, hashed=set(seeded))
    for rel, expected in seeded.items():
        assert observed[rel]["size"] == expected["size"]
        assert observed[rel]["sha256"] == expected["sha256"]

    # The manifest the default call returns still describes the whole measured region:
    # no extra file appeared merely because the opt-in parameter now exists.
    assert set(observed) == set(seeded)


def test_opt_in_seeds_rate_limits_with_exact_bytes(tmp_path, monkeypatch):
    """A3. The opt-in writes the exact declared payload at the AMBIENT destination.

    The destination is derived the way production resolves it, and deliberately WITHOUT
    ensure_user_dir(), which would run both migration routines before the seed existed.
    """
    home = _contained_home(tmp_path, monkeypatch)
    seeded = seed.seed_profile(home, include_rate_limits=True)

    target = seed.rate_limits_file().resolve()
    assert target.is_file(), f"opt-in did not write {target}"
    assert home.resolve() in target.parents, "ambient target escaped the measured home"
    assert target.read_bytes() == seed.RATE_LIMITS_BYTES

    # 124 bytes and the declared digest, asserted on the payload itself.
    assert len(seed.RATE_LIMITS_BYTES) == 124
    assert (
        hashlib.sha256(seed.RATE_LIMITS_BYTES).hexdigest()
        == "e8a5b9bb73b62b20a61664958fae010bea8e26ffd1433d906acbb470cb951a9e"
    )

    rel = target.relative_to(home.resolve()).as_posix()
    assert seeded[rel]["size"] == 124
    assert seeded[rel]["sha256"] == hashlib.sha256(seed.RATE_LIMITS_BYTES).hexdigest()
    assert len(seeded) == 3, f"opt-in must add exactly one entry, got {sorted(seeded)}"


@pytest.mark.parametrize("escape", ["outside_home", "symlink_escape"])
def test_opt_in_refuses_a_target_outside_the_measured_home(tmp_path, monkeypatch, escape):
    """A4. Refusal happens BEFORE any mutation, for both escape shapes.

    The assertion is that NOTHING was written, not merely that an error was raised. A
    write-then-check implementation would raise and still leave a seeded file behind,
    and would fail this test.

    Two arrangement choices make that bite, and both are deliberate.

    THE MARKER ON ``outside`` IS CONTRIBUTED BY THIS TEST rather than inherited from
    ``tmp_path``. A sibling under the same marker root means the guard's marker test
    PASSES and the containment test is what refuses, which is the behavior under test.
    The earlier ``tmp_path / "outside_the_marker"`` construction made the OUTCOME depend
    on ambient inheritance. WITHOUT an inherited marker the guard's marker test refused
    first, raising ``RealProfileAccessError``; WITH one, the marker test passed and the
    call could go on to reach the home containment ``ValueError`` this test asserts.
    Because ``RealProfileAccessError`` is a ``RuntimeError`` and NOT a ``ValueError``,
    that construction satisfied this test only where ``tmp_path`` happened to sit under a
    marker region. The resolved-suffix assertions below fail on it either way.

    THE ORDINARY SEED DESTINATIONS ARE LEFT ABSENT. Pre-seeding them with their normal
    payloads would hide the exact regression this test exists to reject: validate-all-
    before-write degrading to validate-and-write-one-target-at-a-time rewrites history
    and config with IDENTICAL bytes before rejecting the rate target, so every recorded
    size and digest still matches and a snapshot comparison still passes. Requiring both
    to be STILL ABSENT afterwards catches it. A non-seed sentinel keeps the home
    non-empty so the "nothing changed" claim has real content to protect.
    """
    home = _contained_home(tmp_path, monkeypatch)
    marker_root = home.parent
    outside = marker_root / "outside_sibling"
    outside.mkdir()

    # An observable pre-write state: content the seeder never writes, so its survival is
    # evidence about the refusal rather than about the seeder's own output.
    sentinel = home / "prepared-sentinel.txt"
    sentinel.write_bytes(b"a4-prepared-sentinel\n")

    # The two ordinary destinations start ABSENT, which is what makes a premature write
    # detectable at all.
    history_dest = seed.command_history_file(home)
    config_dest = seed.platform_config_file()
    assert not history_dest.exists()
    assert not config_dest.exists()

    if escape == "outside_home":
        redirected = outside / "rate_limits.json"
    else:
        # A link that lives inside the home but resolves outside it. ensure_disposable
        # resolves before checking, so the referent is what gets judged.
        link_parent = home / ".local" / "share" / "scrappy"
        link_parent.mkdir(parents=True, exist_ok=True)
        link = link_parent / "escaped"
        link.symlink_to(outside, target_is_directory=True)
        redirected = link / "rate_limits.json"

    monkeypatch.setattr(seed, "rate_limits_file", lambda: redirected)

    # Bind the REAL RESOLVED target, not the lexical path. The guard resolves before it
    # checks, and in the symlink case the referent is what must be judged.
    r_tmp = tmp_path.resolve()
    r_home = home.resolve()
    r_outside = outside.resolve()
    r_redirected = redirected.resolve()

    # The marker must appear in each path's OWN suffix below tmp_path. A marker inherited
    # from an ancestor above tmp_path cannot satisfy this, so the premise is constructed
    # rather than ambient.
    assert manifest.CONTAINMENT_MARKER in r_home.relative_to(r_tmp).parts
    assert manifest.CONTAINMENT_MARKER in r_outside.relative_to(r_tmp).parts
    assert manifest.CONTAINMENT_MARKER in r_redirected.relative_to(r_tmp).parts
    # The redirection really points at the intended sibling file, and really escapes.
    assert r_redirected == r_outside / "rate_limits.json"
    assert r_home not in r_redirected.parents

    def snapshot(root: Path) -> dict[str, bytes | None]:
        out: dict[str, bytes | None] = {}
        for entry in sorted(root.rglob("*")):
            rel = entry.relative_to(root).as_posix()
            out[rel] = entry.read_bytes() if entry.is_file() else None
        return out

    # Recorded LAST, after every directory, parent, link and the sentinel already exist.
    # Snapshotting earlier would make the symlink case fail on entries this test itself
    # added after the snapshot, independently of the behavior under test.
    before_home = snapshot(home)
    before_outside = snapshot(outside)

    with pytest.raises(ValueError):
        seed.seed_profile(home, include_rate_limits=True)

    # NOTHING under either region changed.
    assert snapshot(home) == before_home, "the prepared home was mutated before refusal"
    assert snapshot(outside) == before_outside, "the outside region was mutated"

    # NOTHING was written anywhere: not the escaping target, and not the two ordinary
    # seeds either, because validation precedes the first write.
    assert sentinel.read_bytes() == b"a4-prepared-sentinel\n"
    assert not history_dest.exists(), "history was written before the rate target refused"
    assert not config_dest.exists(), "config was written before the rate target refused"
    assert not redirected.exists()
    assert list(outside.iterdir()) == []
    assert list(home.rglob("rate_limits.json")) == []


def test_hashed_manifest_detects_a_same_size_alteration(tmp_path, monkeypatch):
    """A5. A one-byte change at IDENTICAL length is detected.

    This proves the seeded entry is genuinely in the HASHED set rather than only
    size-compared. A size-only comparison would report this file as unchanged.
    """
    home = _contained_home(tmp_path, monkeypatch)
    seeded = seed.seed_profile(home, include_rate_limits=True)
    hashed = set(seeded)

    before = manifest.snapshot(home, hashed=hashed)

    target = seed.rate_limits_file().resolve()
    original = target.read_bytes()
    altered = original.replace(b'"2026-08-01"', b'"2026-08-02"', 1)
    assert len(altered) == len(original), "the alteration must not change the length"
    target.write_bytes(altered)

    after = manifest.snapshot(home, hashed=hashed)
    rel = target.relative_to(home.resolve()).as_posix()
    assert after[rel]["size"] == before[rel]["size"], "size is deliberately unchanged"
    assert after[rel]["sha256"] != before[rel]["sha256"], "hashed set failed to detect it"
    assert manifest.diff(before, after), "diff must report the same-size alteration"


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
