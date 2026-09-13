"""The instrument's OWN write operations, guarded BEFORE any mutation (scrappy-aggp).

Two review findings shaped this module, and both are about the difference between a
guard that is checked and a guard that is LOAD-BEARING:

  - GUARD ORDERING. The first fix asserted the target was outside the measured region
    AFTER allocating a temporary file and AFTER creating the cache directory. If the
    ambient environment ever misrouted those into the measured HOME, the instrument had
    ALREADY written there by the time it refused. A guard that fires after the mutation
    it exists to prevent is a report, not a defence. Every function below resolves and
    guards the DIRECTORY before the first mkdir, allocation or write.

  - ONE IMPLEMENTATION, NOT TWO. The regression proof originally re-modelled these
    writes rather than calling them, so moving a real probe back under the measured
    region would have left the proof green. The positive control and the deterministic
    empty-diff regression test now both call THESE functions, so there is a single
    implementation to move and any move fails both.

Nothing here is application code. It exists so the instrument cannot enter the escape
baseline it measures, which per plan T-4 must be able to reach empty for the seven-PR
sequence to be accepted at all.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .manifest import assert_outside_measured_region

PROBE_TEMP_PREFIX = "probe-d-"
PROFILE_MARKER_NAME = "probe_d_marker"
CACHE_MARKER_NAME = "probe_d_cache_marker"
PROFILE_MARKER_BYTES = "probe-d\n"
CACHE_MARKER_BYTES = "ok\n"


def guarded_dir(path: str | os.PathLike[str], *, measured_root: str | os.PathLike[str]) -> Path:
    """Resolve, GUARD, then create a directory the instrument is about to write into.

    The guard runs BEFORE mkdir, so a misrouted target is refused with the filesystem
    still untouched.
    """
    resolved = assert_outside_measured_region(path, measured_root=measured_root)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def guarded_file(path: str | os.PathLike[str], *, measured_root: str | os.PathLike[str]) -> Path:
    """Resolve and GUARD a file target, and its parent, before anything is written."""
    resolved = assert_outside_measured_region(path, measured_root=measured_root)
    guarded_dir(resolved.parent, measured_root=measured_root)
    return resolved


def allocate_temp_file(
    *, temp_dir: str | os.PathLike[str], measured_root: str | os.PathLike[str]
) -> Path:
    """Allocate and release a temporary file, guarding the DIRECTORY first.

    Returns the path that was allocated. The file itself is removed on exit; the point
    of the probe is that allocation SUCCEEDS in the disposable scratch, which is what
    proves the launcher is not simply rejecting everything.
    """
    directory = guarded_dir(temp_dir, measured_root=measured_root)
    with tempfile.NamedTemporaryFile(prefix=PROBE_TEMP_PREFIX, dir=directory, delete=True) as handle:
        return Path(handle.name).resolve()


def write_profile_shaped_marker(
    *, scratch_root: str | os.PathLike[str], measured_root: str | os.PathLike[str]
) -> Path:
    """Write an application-profile-shaped marker into disposable scratch.

    The ``.scrappy/<file>`` shape is retained deliberately: it is the shape the
    application actually writes, so the probe exercises the real operation rather than a
    convenient stand-in.
    """
    target = guarded_file(
        Path(scratch_root) / ".scrappy" / PROFILE_MARKER_NAME, measured_root=measured_root
    )
    target.write_text(PROFILE_MARKER_BYTES, encoding="utf-8")
    return target


def write_cache_marker(
    *, caches_root: str | os.PathLike[str], measured_root: str | os.PathLike[str]
) -> Path:
    """Write a marker into the third-party caches region, guarding it before mkdir."""
    target = guarded_file(Path(caches_root) / CACHE_MARKER_NAME, measured_root=measured_root)
    target.write_text(CACHE_MARKER_BYTES, encoding="utf-8")
    return target


def perform_probe_writes(
    *,
    temp_dir: str | os.PathLike[str],
    scratch_root: str | os.PathLike[str],
    caches_root: str | os.PathLike[str],
    measured_root: str | os.PathLike[str],
) -> dict[str, Path]:
    """Perform EVERY write the instrument makes for its own purposes.

    This is the single list. The positive control calls these operations individually
    and the deterministic regression test calls this function against a synthetic
    measured region; adding a probe write anywhere else, or moving one of these back
    under the measured region, breaks both.
    """
    return {
        "temp_allocation": allocate_temp_file(temp_dir=temp_dir, measured_root=measured_root),
        "profile_marker": write_profile_shaped_marker(
            scratch_root=scratch_root, measured_root=measured_root
        ),
        "cache_marker": write_cache_marker(caches_root=caches_root, measured_root=measured_root),
    }
