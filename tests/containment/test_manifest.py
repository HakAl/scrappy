"""Tests for the profile manifest helpers (plan 3d).

The load-bearing test is the R1 proof: the manifest catches a file whose contents
changed while its PARENT DIRECTORY MTIME did not, which is precisely the escape a
directory-mtime guard would have missed.
"""

import os
from pathlib import Path

import pytest

from tests.containment import manifest


def _measured_region(tmp_path: Path) -> Path:
    region = tmp_path / "home"
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
