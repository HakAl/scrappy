"""Tests for the profile manifest helpers (plan 3d).

The load-bearing test is the R1 proof: the manifest catches a file whose contents
changed while its PARENT DIRECTORY MTIME did not, which is precisely the escape a
directory-mtime guard would have missed.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.containment import instrument, manifest


def _disposable_root(tmp_path: Path) -> Path:
    """A tmp subtree that carries the ``.pytest_profile`` marker segment.

    ensure_disposable() accepts a path only when a ``.pytest_profile`` segment appears in
    it. A bare ``tmp_path`` does not carry one, which matters when
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


def test_ensure_disposable_refuses_the_real_profile_whatever_home_says(monkeypatch):
    """The guard blocks the real profile, and does so WITHOUT consulting Path.home().

    Renamed from ..._refuses_a_path_under_the_real_home: the guard no longer has a
    real-home branch to exercise (scrappy-641n), so the old name described a mechanism
    that had been deleted. What is asserted now is stronger, and the monkeypatched home
    is what makes it so. Path.home() is pointed AT the real profile's own parent, the
    single arrangement under which an ambient rule would be most tempted to allow it,
    and the refusal still lands purely because the path carries no marker.

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


# ---------------------------------------------------------------------------
# scrappy-sqqc: an incomplete scan must never become clean baseline evidence.
# ---------------------------------------------------------------------------

_IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX permission bits do not restrict directory traversal on Windows",
)
@pytest.mark.skipif(
    _IS_ROOT,
    reason="root traverses unreadable directories, so the read failure cannot be provoked",
)
def test_an_unreadable_subtree_voids_the_measurement(tmp_path):
    """A scan that cannot read everything must raise, not return a subset.

    os.walk() SWALLOWS traversal errors by default and snapshot() used to swallow stat
    errors on top of that, so an unreadable subtree vanished from the BEFORE and AFTER
    manifests alike. diff() then had nothing to report for it and the publication gate
    accepted the remaining diff as evidence of a clean run: an empty baseline forged out
    of SILENCE and indistinguishable from a genuinely empty one. T-4 retires this
    instrument on OBSERVING an empty baseline, so that distinction is the whole point.
    """
    region = _measured_region(tmp_path)
    (region / ".scrappy" / "visible").write_bytes(b"seen")
    blocked = region / ".scrappy" / "blocked"
    blocked.mkdir()
    (blocked / "hidden").write_bytes(b"written-but-unreadable")
    blocked.chmod(0o000)
    try:
        with pytest.raises(manifest.IncompleteScanError) as excinfo:
            manifest.snapshot(region)
        assert "blocked" in str(excinfo.value), str(excinfo.value)
    finally:
        # Restore before pytest's own cleanup, which cannot remove an unreadable dir.
        blocked.chmod(0o700)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="creating symlinks on Windows needs a privilege the runner does not hold",
)
def test_a_broken_symlink_stays_visible_rather_than_vanishing(tmp_path):
    """A broken link is a real state of the region, so it is recorded, not dropped.

    Skipping it would reintroduce exactly the silent disappearance scrappy-sqqc is about.
    It is now recorded like any other link, from lstat and readlink, WITHOUT the target
    being probed at all: the manifest says "this path is a link to X" and claims nothing
    about whether X resolves (scrappy-ni4w).
    """
    region = _measured_region(tmp_path)
    link = region / ".scrappy" / "dangling"
    link.symlink_to(region / ".scrappy" / "no-such-target")

    entries = manifest.snapshot(region)

    assert ".scrappy/dangling" in entries, entries
    assert entries[".scrappy/dangling"]["kind"] == "symlink"
    assert entries[".scrappy/dangling"]["target"].endswith("no-such-target")


_NO_SYMLINKS_ON_WINDOWS = pytest.mark.skipif(
    sys.platform == "win32",
    reason="creating symlinks on Windows needs a privilege the runner does not hold",
)


@_NO_SYMLINKS_ON_WINDOWS
def test_snapshot_never_follows_a_symlink_out_of_the_measured_region(tmp_path):
    """A link out of the region must not be followed, sized, or hashed (scrappy-f2uw).

    snapshot() used to stat() and open() through the link, so a seeded path replaced by
    a link into the ORIGINAL profile made the manifest record that external file's size
    and sha256 as though they belonged to the region. Two failures in one: the
    measurement describes a file that is not in the region, and the instrument reads a
    profile it must never touch. Validating the root says nothing about its descendants.

    The outside file here is SYNTHETIC. The real profile is never involved.
    """
    region = _measured_region(tmp_path)
    outside = tmp_path / "outside_the_region"
    outside.mkdir()
    external = outside / "original_command_history"
    external.write_bytes(b"OUTSIDE-CONTENT-" * 8)  # 128 bytes, unlike any seed

    rel = ".scrappy/command_history"
    link = region / rel
    link.symlink_to(external)

    entries = manifest.snapshot(region, hashed={rel})

    assert entries[rel]["kind"] == "symlink"
    assert entries[rel]["target"] == str(external)
    # The recorded size is the length of the link text, NOT the external file's size.
    assert entries[rel]["size"] != external.stat().st_size
    assert entries[rel]["size"] == len(str(external))
    # The seeded path was requested as hashed, and STILL nothing outside was read.
    assert entries[rel]["sha256"] is None


@_NO_SYMLINKS_ON_WINDOWS
@pytest.mark.skipif(
    _IS_ROOT,
    reason="root traverses unreadable directories, so the read failure cannot be provoked",
)
def test_a_link_whose_target_is_unreadable_is_not_reported_as_broken(tmp_path):
    """An unreadable target is not a missing one, and must not be recorded as such.

    The old branch caught EVERY OSError from stat() and, on finding the path was a
    symlink, declared it dangling. is_symlink() proves only that the path IS a link; it
    never proved the target was absent. A permission error, an I/O error or a link loop
    therefore became a clean accepted entry, which is the scrappy-sqqc class of defect:
    a read failure turning into evidence (scrappy-ni4w).

    Referent metadata does not determine the recorded symlink entry, so there is no
    failure left to misclassify.
    """
    region = _measured_region(tmp_path)
    locked = tmp_path / "locked_parent"
    locked.mkdir()
    target = locked / "present_and_readable_but_for_the_parent"
    target.write_bytes(b"this target EXISTS")
    link = region / ".scrappy" / "link_into_locked"
    link.symlink_to(target)
    locked.chmod(0o000)
    try:
        entries = manifest.snapshot(region)

        assert entries[".scrappy/link_into_locked"]["kind"] == "symlink"
        assert entries[".scrappy/link_into_locked"]["target"] == str(target)
    finally:
        # Restore before pytest's own cleanup, which cannot remove an unreadable dir.
        locked.chmod(0o700)


@_NO_SYMLINKS_ON_WINDOWS
def test_a_seed_replaced_by_a_same_size_link_is_still_an_operation(tmp_path):
    """Destroying a seed must produce a diff even when the size is unchanged.

    diff() compared size and hashes only, and hash_changed required BOTH hashes to
    exist. Replacing the 32-byte seeded command_history with a dangling link whose
    target string is ALSO 32 bytes left the size equal and the new hash None, so the
    destroyed seed generated NO operation at all (scrappy-st0h). That seed's growth is
    this instrument's entire measured signal.
    """
    region = _measured_region(tmp_path)
    rel = ".scrappy/command_history"
    seed = region / rel
    seed.write_bytes(b"A" * 32)

    before = manifest.snapshot(region, hashed={rel})
    assert before[rel]["size"] == 32

    target_of_equal_length = "B" * 32
    seed.unlink()
    seed.symlink_to(target_of_equal_length)

    after = manifest.snapshot(region, hashed={rel})
    assert after[rel]["size"] == before[rel]["size"], "the size must be UNCHANGED"
    assert after[rel]["sha256"] is None

    ops = manifest.diff(before, after)

    assert [op["path"] for op in ops] == [rel], ops
    assert ops[0]["op"] == "modified"
    assert ops[0]["before"]["kind"] == "file"
    assert ops[0]["after"]["kind"] == "symlink"


@_NO_SYMLINKS_ON_WINDOWS
def test_a_retargeted_link_of_equal_length_is_an_operation(tmp_path):
    """Same kind, same size, different referent. Only the target tells them apart."""
    region = _measured_region(tmp_path)
    rel = ".scrappy/link"
    link = region / rel
    link.symlink_to("aaaa")

    before = manifest.snapshot(region)

    link.unlink()
    link.symlink_to("bbbb")

    after = manifest.snapshot(region)
    assert before[rel]["size"] == after[rel]["size"]

    ops = manifest.diff(before, after)

    assert [op["path"] for op in ops] == [rel], ops
    assert ops[0]["after"]["target"] == "bbbb"


@_NO_SYMLINKS_ON_WINDOWS
def test_a_symlinked_directory_is_recorded_and_never_traversed(tmp_path):
    """A directory link out of the region used to leave NO trace whatsoever.

    os.walk() does not follow directory links by default, and a linked directory never
    appears in ``filenames``, so it was absent from every manifest AND raised no error.
    The link and everything behind it simply did not exist as far as the instrument was
    concerned: another route to a baseline forged out of silence.

    The link is now recorded as an object. It is still not traversed, so nothing behind
    it is read.
    """
    region = _measured_region(tmp_path)
    outside = tmp_path / "outside_the_region"
    outside.mkdir()
    (outside / "leaked").write_bytes(b"content behind the link")

    (region / ".scrappy" / "linked_dir").symlink_to(outside, target_is_directory=True)

    entries = manifest.snapshot(region)

    assert entries[".scrappy/linked_dir"]["kind"] == "symlink"
    assert entries[".scrappy/linked_dir"]["target"] == str(outside)
    # Recorded, but NOT descended into: nothing behind the link was read.
    assert not [rel for rel in entries if rel.startswith(".scrappy/linked_dir/")], entries


_FIFO_CHILD = """
import json, sys
from tests.containment import manifest
region, rel = sys.argv[1], sys.argv[2]
entries = manifest.snapshot(region, hashed={rel})
print(json.dumps(entries[rel]))
"""


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="os.mkfifo is not available on Windows",
)
def test_a_fifo_is_recorded_without_being_opened(tmp_path):
    """A non-regular file is recorded by kind and never read.

    Only a REGULAR file is opened. Classifying a fifo as an ordinary file would hide the
    substitution from diff(), and HASHING one blocks forever: open() on a fifo waits for
    a writer that never comes.

    THE SNAPSHOT RUNS IN A BOUNDED CHILD PROCESS, and that is the whole point of the test
    (scrappy-gdqg). Restoring the defect does not make an in-process version of this test
    fail, it makes it HANG, taking the run with it: the first falsification run of this
    fix hung for over seven minutes here before it was killed. A regression must produce
    a FAILURE, not a stall, so the bound cannot live in the assertion. It lives in the
    process boundary, which holds even if the blocked call ignores signals.
    """
    region = _measured_region(tmp_path)
    rel = ".scrappy/command_history"
    os.mkfifo(region / rel)

    repo_root = Path(__file__).resolve().parents[2]
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _FIFO_CHILD, str(region), rel],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            "snapshot() BLOCKED on a fifo and had to be killed. A non-regular file was "
            "opened for hashing, and open() on a fifo waits forever for a writer, so "
            "the whole measurement stalls instead of failing (scrappy-gdqg)."
        )

    assert completed.returncode == 0, completed.stderr
    entry = json.loads(completed.stdout)
    assert entry["kind"] == "special"
    assert entry["sha256"] is None


@_NO_SYMLINKS_ON_WINDOWS
@pytest.mark.skipif(
    not hasattr(os, "O_NOFOLLOW"),
    reason="O_NOFOLLOW is a POSIX flag; without it the final-component race is not closed",
)
def test_hash_file_refuses_to_follow_a_link_at_the_final_component(tmp_path):
    """The lstat and the open are two operations; the open must not follow (scrappy-tban).

    snapshot() only calls hash_file after lstat reported a REGULAR file, so reaching
    hash_file with a symlink requires the path to have been replaced in between. This
    test performs that substitution directly rather than racing it, which is the only
    deterministic way to exercise the window. O_NOFOLLOW must make it an OSError, which
    snapshot() collects into IncompleteScanError: the measurement is VOIDED rather than
    quietly reporting bytes from outside the region.
    """
    region = _measured_region(tmp_path)
    outside = tmp_path / "outside_the_region"
    outside.mkdir()
    external = outside / "original_command_history"
    external.write_bytes(b"OUTSIDE-CONTENT-" * 8)

    link = region / ".scrappy" / "command_history"
    link.symlink_to(external)

    with pytest.raises(OSError) as excinfo:
        manifest.hash_file(link)

    # Whatever the platform's errno, the point is that it did NOT return a digest of the
    # external file.
    assert not isinstance(excinfo.value, StopIteration)
