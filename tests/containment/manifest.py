"""Profile manifest: snapshot, diff and disposable-region guard (plan 3d).

MANIFEST CONTRACT:
  - MEASURED REGION is the application-profile root (the launcher's ``home/``) ONLY.
    The third-party caches sibling is never passed to these helpers.
  - ENTRY GRANULARITY is per path, with an operation class: created, modified, deleted.
  - CONTENT HASHES are recorded for SEEDED files only, where a stable expected value
    exists. Non-seeded output (cooldown JSON, logs) is matched at PATH granularity.
  - Full manifests are compared per path. Directory mtimes are NEVER consulted: the R1
    reproduction changed a file while its parent directory mtime did not.

MEASURED-REGION GUARD (scrappy-aggp): assert_outside_measured_region() refuses a write
the INSTRUMENT performs for its own purposes when that write would land inside the region
being measured. Instrument artifacts in the escape set make the baseline permanently
non-empty, and T-4 retires this instrument only when an EMPTY baseline is OBSERVED.

DISPOSABLE-REGION GUARD: every function refuses a target that is not demonstrably a
disposable region. A path is disposable when, and ONLY when, a ``.pytest_profile``
segment appears in it. That region is established EXPLICITLY by the launcher, is the
region ``.gitignore`` covers, and is the one the preflight validates, so it is the only
thing here that can honestly stand for "disposable". It blocks the real profile
(``~/Library/Application Support/scrappy``, ``~/.scrappy``, ...) and the original home.

The guard used to accept a second class of path: anything NOT nested under the real
home. That rule INVERTS under the launcher, which is the only place it matters. See
ensure_disposable() for why it was removed (scrappy-641n).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any


CONTAINMENT_MARKER = ".pytest_profile"


class RealProfileAccessError(RuntimeError):
    """Raised when a helper is pointed at anything that could be the real profile."""


class MeasuredRegionContaminationError(RuntimeError):
    """Raised when the INSTRUMENT itself would write inside the measured region.

    See bead scrappy-aggp. The positive control originally wrote its marker into
    ``Path.home()/.scrappy``, which under the launcher IS the measured region, so two
    of the first run's four escape entries were the instrument's own writes. A baseline
    that permanently contains instrument artifacts can never shrink to empty, and T-4
    earns retirement only by OBSERVING an empty baseline. The instrument must therefore
    be structurally incapable of entering the set it measures.
    """


class IncompleteScanError(RuntimeError):
    """Raised when the measured region could not be read in full.

    See bead scrappy-sqqc. ``os.walk()`` SWALLOWS traversal errors by default, and this
    module used to swallow stat errors on top of that, so an unreadable subtree vanished
    from the BEFORE and AFTER manifests alike. diff() then had nothing to report for it
    and the publication gate accepted the remaining diff as evidence of a clean run.

    That is a forged empty baseline assembled out of SILENCE rather than out of
    measurement, and it is indistinguishable from a genuinely clean region, which is the
    property that makes it dangerous: T-4 retires this instrument on OBSERVING an empty
    baseline. A scan that could not read everything is not a measurement at all, so it
    fails closed rather than reporting a subset.
    """


def ensure_disposable(path: str | os.PathLike[str]) -> Path:
    """Return ``path`` resolved, or raise unless it is inside the marker region.

    This is the single guard that keeps the instrument off the real profile, and it keys
    ONLY on the ``.pytest_profile`` marker, never on ambient state.

    IT DELIBERATELY DOES NOT CONSULT ``Path.home()`` (scrappy-641n). The rule used to be
    "marker, OR not nested under the real home", and that second clause INVERTS in exactly
    the situation the guard exists for. Under the launcher, HOME has already been
    reassigned to the DISPOSABLE home, so ``Path.home()`` returns that; the ORIGINAL home
    is then not nested under it and was ACCEPTED. The guard protected the disposable
    profile from the real one, precisely backwards. ``seed_profile(original_home)`` would
    have overwritten the developer's own ``~/.scrappy/command_history``, which is the R1
    damage this instrument was built to measure.

    A guard that reads ambient state protects whatever that state happens to name, and
    after a redirection that is the wrong thing. The marker cannot move underneath it.
    """
    resolved = Path(path).resolve()
    if CONTAINMENT_MARKER in resolved.parts:
        return resolved
    raise RealProfileAccessError(
        f"refusing to touch {resolved}: it is not inside a {CONTAINMENT_MARKER} "
        f"disposable region. The instrument writes ONLY inside the launcher's marker "
        f"region; the real profile and the pre-redirection home are both outside it."
    )


def assert_outside_measured_region(
    path: str | os.PathLike[str],
    *,
    measured_root: str | os.PathLike[str],
) -> Path:
    """Return ``path`` resolved, or raise if it lies inside the measured region.

    This is the scrappy-aggp guard. Every write the INSTRUMENT performs for its own
    purposes (probe markers, positive-control artifacts) must pass through here, so an
    instrument artifact cannot become an escape entry in the application baseline.

    It is deliberately separate from ``ensure_disposable``: that guard answers "is this
    safe to touch at all", this one answers "is this outside the thing being measured".
    A path can be perfectly disposable and still contaminate the measurement.
    """
    resolved = Path(path).resolve()
    root = Path(measured_root).resolve()
    if resolved == root or root in resolved.parents:
        raise MeasuredRegionContaminationError(
            f"refusing to let the instrument write {resolved}: it is inside the measured "
            f"region {root}. Instrument artifacts would enter the application escape "
            f"baseline, which could then never shrink to empty (scrappy-aggp, T-4)."
        )
    return resolved


def hash_file(path: Path) -> str:
    """Return the sha256 of a file's contents (streamed, so large files are fine)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(root: str | os.PathLike[str], *, hashed: set[str] | None = None) -> dict[str, dict[str, Any]]:
    """Manifest every file under ``root`` (the measured application-profile region).

    Records file size for every path and a content hash for the relative paths named
    in ``hashed`` (the seeded files). Directories are represented only by the files
    they contain; no directory mtime is ever recorded.
    """
    base = ensure_disposable(root)
    hashed = hashed or set()
    entries: dict[str, dict[str, Any]] = {}
    if not base.exists():
        return entries

    # EVERY read failure is collected and made fatal below. Nothing may be skipped
    # quietly: a path that disappears from both manifests hides whatever was written to
    # it (scrappy-sqqc).
    scan_errors: list[str] = []

    def _record_walk_error(error: OSError) -> None:
        scan_errors.append(f"walk {getattr(error, 'filename', base)}: {error}")

    for dirpath, _dirnames, filenames in os.walk(base, onerror=_record_walk_error):
        for name in filenames:
            file_path = Path(dirpath) / name
            rel = file_path.relative_to(base).as_posix()
            try:
                size = file_path.stat().st_size
            except OSError as error:
                # A DANGLING SYMLINK is a real, observable state of the region, not a
                # failure to read it. Record it from lstat so it stays VISIBLE in the
                # manifest: neither vanishing silently nor aborting a legitimate run.
                if file_path.is_symlink():
                    entries[rel] = {
                        "kind": "dangling_symlink",
                        "size": file_path.lstat().st_size,
                        "sha256": None,
                    }
                    continue
                scan_errors.append(f"stat {file_path}: {error}")
                continue
            entry: dict[str, Any] = {"kind": "file", "size": size, "sha256": None}
            if rel in hashed:
                try:
                    entry["sha256"] = hash_file(file_path)
                except OSError as error:
                    scan_errors.append(f"hash {file_path}: {error}")
                    continue
            entries[rel] = entry

    if scan_errors:
        raise IncompleteScanError(
            f"the measured region {base} could not be scanned in full, so this "
            f"measurement is void and must not back a baseline. "
            f"{len(scan_errors)} failure(s): " + "; ".join(sorted(scan_errors))
        )
    return entries


def diff(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return per-path operations between two manifests, sorted by path.

    A path is ``modified`` when its size changes, or when a recorded seed hash changes.
    Directory mtimes are never consulted.
    """
    ops: list[dict[str, Any]] = []
    before_paths = set(before)
    after_paths = set(after)

    for rel in sorted(after_paths - before_paths):
        ops.append({"op": "created", "path": rel, "after": after[rel]})
    for rel in sorted(before_paths - after_paths):
        ops.append({"op": "deleted", "path": rel, "before": before[rel]})
    for rel in sorted(before_paths & after_paths):
        prior, current = before[rel], after[rel]
        size_changed = prior["size"] != current["size"]
        hash_changed = (
            prior.get("sha256") is not None
            and current.get("sha256") is not None
            and prior["sha256"] != current["sha256"]
        )
        if size_changed or hash_changed:
            ops.append({"op": "modified", "path": rel, "before": prior, "after": current})
    return ops


def escape_paths(ops: list[dict[str, Any]]) -> list[str]:
    """Reduce a diff to the sorted set of profile paths that escaped (any operation)."""
    return sorted({op["path"] for op in ops})
