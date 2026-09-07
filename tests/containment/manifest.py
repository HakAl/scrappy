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
disposable region. A path is disposable when a ``.pytest_profile`` segment appears in
it, OR it is not nested under the real home directory. That blocks the real profile
(``~/Library/Application Support/scrappy``, ``~/.scrappy``, ...) while allowing the
launcher's contained ``home/`` and an ordinary pytest ``tmp_path``.
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


def ensure_disposable(path: str | os.PathLike[str]) -> Path:
    """Return ``path`` resolved, or raise if it is not a disposable region.

    This is the single guard that keeps the instrument off the real profile.
    """
    resolved = Path(path).resolve()
    if CONTAINMENT_MARKER in resolved.parts:
        return resolved
    home = Path.home().resolve()
    if resolved == home or home in resolved.parents:
        raise RealProfileAccessError(
            f"refusing to touch {resolved}: it is under the real home {home} and is not "
            f"a {CONTAINMENT_MARKER} disposable region"
        )
    return resolved


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
    for dirpath, _dirnames, filenames in os.walk(base):
        for name in filenames:
            file_path = Path(dirpath) / name
            rel = file_path.relative_to(base).as_posix()
            try:
                size = file_path.stat().st_size
            except OSError:
                continue
            entries[rel] = {
                "kind": "file",
                "size": size,
                "sha256": hash_file(file_path) if rel in hashed else None,
            }
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
