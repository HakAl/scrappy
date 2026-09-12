"""Tests for the profile manifest helpers (plan 3d).

The load-bearing test is the R1 proof: the manifest catches a file whose contents
changed while its PARENT DIRECTORY MTIME did not, which is precisely the escape a
directory-mtime guard would have missed.
"""

import os
from pathlib import Path

import pytest

from tests.containment import instrument, manifest


def _disposable_root(tmp_path: Path) -> Path:
    """A tmp subtree that carries the ``.pytest_profile`` marker segment.

    ensure_disposable() accepts a path only when a ``.pytest_profile`` segment appears in
    it OR it is not nested under the real home. A bare ``tmp_path`` satisfies NEITHER when
    the repository is checked out under the developer's home directory, which is the case
    on every CI runner (the checkout sits under the runner's own home). Under the launcher
    these regions inherited the marker from the contained basetemp, so they passed for a
    reason they never stated; run directly, the guard refused every one of them.

    Constructing the marker here makes the disposability EXPLICIT and independent of the
    ambient HOME and basetemp. Disposability is not inheritable state.
    """
    root = tmp_path / ".pytest_profile" / "sid"
    root.mkdir(parents=True)
    return root


def _measured_region(tmp_path: Path) -> Path:
    region = _disposable_root(tmp_path) / "home"
    (region / ".scrappy").mkdir(parents=True)
    return region


def test_snapshot_reports_created_deleted_and_modified(tmp_path):
    region = _measured_region(tmp_path)
    kept = region / ".scrappy" / "kept"
    removed = region / ".scrappy" / "removed"
    kept.write_bytes(b"one")
    removed.write_bytes(b"gone-soon")

    before = manifest.snapshot(region)

    kept.write_bytes(b"one-plus-more")  # size change -> modified
    removed.unlink()  # -> deleted
    (region / ".scrappy" / "fresh").write_bytes(b"new")  # -> created

    after = manifest.snapshot(region)
    ops = {op["op"]: op["path"] for op in manifest.diff(before, after)}

    assert ops == {
        "modified": ".scrappy/kept",
        "deleted": ".scrappy/removed",
        "created": ".scrappy/fresh",
    }


def test_manifest_catches_content_change_when_parent_dir_mtime_unchanged(tmp_path):
    """R1 proof: a seeded file's bytes change, the parent dir mtime does not, and the
    per-path manifest still reports the modification. A directory-mtime guard would miss it."""
    region = _measured_region(tmp_path)
    seeded = region / ".scrappy" / "command_history"
    seeded.write_bytes(b"seed-aaaaaaaaaaaaaaaaa")  # 22 bytes
    rel = ".scrappy/command_history"

    before = manifest.snapshot(region, hashed={rel})
    parent_mtime_before = os.stat(seeded.parent).st_mtime_ns

    # Same-size, different bytes: only a content hash can see this.
    seeded.write_bytes(b"seed-bbbbbbbbbbbbbbbbb")
    assert seeded.stat().st_size == before[rel]["size"]

    parent_mtime_after = os.stat(seeded.parent).st_mtime_ns
    # The escape this instrument exists to catch: parent dir mtime did NOT move.
    assert parent_mtime_after == parent_mtime_before

    after = manifest.snapshot(region, hashed={rel})
    ops = manifest.diff(before, after)
    assert [op["op"] for op in ops] == ["modified"]
    assert ops[0]["path"] == rel
    assert ops[0]["before"]["sha256"] != ops[0]["after"]["sha256"]


def test_escape_paths_reduces_ops_to_sorted_paths(tmp_path):
    region = _measured_region(tmp_path)
    (region / ".scrappy" / "b").write_bytes(b"b")
    before = manifest.snapshot(region)
    (region / ".scrappy" / "a").write_bytes(b"a")
    (region / ".scrappy" / "b").write_bytes(b"bb")
    after = manifest.snapshot(region)
    assert manifest.escape_paths(manifest.diff(before, after)) == [".scrappy/a", ".scrappy/b"]


def test_ensure_disposable_refuses_a_path_under_the_real_home(monkeypatch):
    """The guard blocks the real profile: a path under home without a .pytest_profile
    segment is refused, so the instrument can never read or hash the real profile.

    A marker-free absolute home is used deliberately: under the launcher, ``tmp_path``
    itself lives beneath ``.pytest_profile``, which would short-circuit the guard's
    marker branch and defeat the test. The guard only inspects path structure, so the
    directories need not exist.
    """
    fake_real_home = Path("/nonexistent-real-home-for-guard-test")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_real_home))

    real_profile = fake_real_home / "Library" / "Application Support" / "scrappy"
    with pytest.raises(manifest.RealProfileAccessError):
        manifest.ensure_disposable(real_profile)


def test_ensure_disposable_allows_a_pytest_profile_region(tmp_path):
    region = tmp_path / ".pytest_profile" / "sid" / "home"
    region.mkdir(parents=True)
    assert manifest.ensure_disposable(region) == region.resolve()


def test_the_measured_region_carries_its_own_marker(tmp_path):
    """CI regression: the helper must CONTRIBUTE the marker, not inherit it from basetemp.

    Under the launcher ``tmp_path`` already sits inside a ``.pytest_profile`` region, so a
    region built as ``tmp_path / "home"`` is accepted for a reason the helper never supplied
    and the dependency is invisible. Run directly, pytest's basetemp is repo-local, the
    checkout on a CI runner is nested under the runner's home, and ensure_disposable()
    refused every such region. Seven tests failed in CI while passing here.

    Asserting on the path RELATIVE to ``tmp_path`` is what makes this test ambient-
    independent: every absolute path available to a contained test inherits the launcher's
    marker, so an absolute assertion, or a monkeypatched ``Path.home()``, passes vacuously.
    The relative segment can only come from the helper itself.
    """
    region = _measured_region(tmp_path)
    relative = region.relative_to(tmp_path)
    assert manifest.CONTAINMENT_MARKER in relative.parts, (
        f"the helper must place its region under a {manifest.CONTAINMENT_MARKER} segment "
        f"of its own; got {relative}, which is disposable only by inheritance"
    )
    assert manifest.ensure_disposable(region) == region.resolve()


# ---------------------------------------------------------------------------
# scrappy-aggp: the instrument must not be able to enter its own baseline.
# ---------------------------------------------------------------------------


def test_measured_region_guard_refuses_a_target_inside_the_measured_region(tmp_path):
    """The guard is not vacuous: a profile-shaped path under the measured root is refused."""
    measured = tmp_path / "home"
    (measured / ".scrappy").mkdir(parents=True)
    with pytest.raises(manifest.MeasuredRegionContaminationError):
        manifest.assert_outside_measured_region(
            measured / ".scrappy" / "probe_d_marker", measured_root=measured
        )
    # The measured root itself is refused too, not only paths beneath it.
    with pytest.raises(manifest.MeasuredRegionContaminationError):
        manifest.assert_outside_measured_region(measured, measured_root=measured)


def test_measured_region_guard_allows_a_sibling_disposable_region(tmp_path):
    measured = tmp_path / "home"
    measured.mkdir()
    sibling = tmp_path / "caches" / "probe_marker"
    assert manifest.assert_outside_measured_region(
        sibling, measured_root=measured
    ) == sibling.resolve()


def test_the_real_instrument_writes_produce_an_empty_measured_diff(tmp_path):
    """scrappy-aggp regression: instrument artifacts CANNOT enter the application baseline.

    Calls the ACTUAL instrument implementation (tests/containment/instrument.py, the same
    functions the positive control uses) against a SYNTHETIC measured region, rather than
    re-modelling the writes here. That coupling is the point: an earlier version of this
    test reconstructed the writes, so moving a real probe back under the measured region
    would have left it green. Now there is one implementation and moving it fails here.
    """
    measured = _measured_region(tmp_path)
    root = measured.parent
    seeded = measured / ".scrappy" / "command_history"
    seeded.write_bytes(b"seed-help\n")
    rel = ".scrappy/command_history"

    before = manifest.snapshot(measured, hashed={rel})

    written = instrument.perform_probe_writes(
        temp_dir=root / "scratch" / "system",
        scratch_root=root / "scratch",
        caches_root=root / "caches",
        measured_root=measured,
    )

    after = manifest.snapshot(measured, hashed={rel})
    assert manifest.diff(before, after) == []
    assert manifest.escape_paths(manifest.diff(before, after)) == []
    # The writes really happened; the empty diff is not vacuous.
    assert written["profile_marker"].exists()
    assert written["cache_marker"].exists()
    assert ".scrappy" in written["profile_marker"].parts


def test_the_real_instrument_refuses_when_pointed_at_the_measured_region(tmp_path):
    """The coupling above only proves something if the guard can actually fail."""
    measured = tmp_path / "home"
    measured.mkdir()
    with pytest.raises(manifest.MeasuredRegionContaminationError):
        instrument.perform_probe_writes(
            temp_dir=measured / "scratch",
            scratch_root=measured / "scratch",
            caches_root=measured / "caches",
            measured_root=measured,
        )
    assert list(measured.iterdir()) == [], "refusal must leave the measured region untouched"
