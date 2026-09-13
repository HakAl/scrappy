"""Profile manifest: snapshot, diff and disposable-region guard (plan 3d).

MANIFEST CONTRACT:
  - MEASURED REGION is the application-profile root (the launcher's ``home/``) ONLY.
    The third-party caches sibling is never passed to these helpers.
  - ENTRY GRANULARITY is per path, with an operation class: created, modified, deleted.
    Every entry carries a KIND (file, symlink, special), and kind is COMPARED: a seed
    replaced by a same-size link is a change, not a match (scrappy-st0h).
  - NO SYMLINK REFERENT IS EVER READ, AND NO LINKED DIRECTORY IS EVER ENTERED, FOR A
    TREE THAT IS STABLE DURING THE SCAN. Entries are classified from lstat and only a
    REGULAR file is opened, so the instrument cannot be led outside the region by a link
    it finds inside it (scrappy-f2uw), and a symlink is recorded as an object rather
    than probed for whether its target resolves (scrappy-ni4w).
    TWO QUALIFICATIONS, because the unqualified sentence would be false (scrappy-tban).
    FIRST: os.walk() classifies each entry with DirEntry.is_dir(), which stats the
    target, so referent METADATA is consulted even though it never determines a recorded
    field. SECOND: this module walks by PATHNAME, so lstat and the later open are
    separate operations. WHERE O_NOFOLLOW IS AVAILABLE, a final component swapped for a
    link between them is refused by hash_file and voids the measurement; ON A PLATFORM
    WITHOUT IT the flag degrades to zero and THAT RACE REMAINS OPEN, so such a swap would
    be followed and the referent hashed. An ANCESTOR DIRECTORY swapped for a link
    mid-scan is NOT covered on any platform, and covering it would require
    descriptor-relative traversal. CONCURRENT MUTATION OF THE MEASURED REGION IS OUT OF
    SCOPE, which is consistent with the instrument being single-measurement by design,
    though single-measurement does NOT by itself establish that the tree is quiescent:
    the caller must actually keep it stable for the duration of each scan.
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
import stat
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
    """Return the sha256 of a file's contents (streamed, so large files are fine).

    OPENED WITH ``O_NOFOLLOW`` where the platform has it. snapshot() only calls this
    after ``lstat`` reported a REGULAR file, but the lstat and the open are two separate
    pathname operations, so a path replaced by a symlink BETWEEN them would otherwise be
    followed by the open and its referent hashed. With O_NOFOLLOW that race raises
    OSError instead, which snapshot() collects into IncompleteScanError: the measurement
    is voided rather than quietly describing a file outside the region.

    This closes the FINAL component only. An ancestor directory swapped for a link during
    the scan is still resolved at open time; covering that needs descriptor-relative
    traversal, which is not implemented here. See the module docstring.
    """
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _symlink_entry(link_path: Path, info: os.stat_result) -> dict[str, Any]:
    """Describe a symlink as an OBJECT, without ever resolving or reading its target.

    ``size`` is the length of the stored target string (from lstat), not the size of
    whatever the link points at, and ``target`` is the raw link text. Nothing here
    touches the referent, so a link out of the measured region cannot draw the
    instrument outside it (scrappy-f2uw) and an unreadable referent cannot be
    misreported as a missing one (scrappy-ni4w).
    """
    return {
        "kind": "symlink",
        "size": info.st_size,
        "sha256": None,
        "target": os.readlink(link_path),
    }


def snapshot(root: str | os.PathLike[str], *, hashed: set[str] | None = None) -> dict[str, dict[str, Any]]:
    """Manifest every path under ``root`` (the measured application-profile region).

    Records size for every path and a content hash for the relative paths named in
    ``hashed`` (the seeded files). Directories are represented only by the entries they
    contain; no directory mtime is ever recorded.

    NO REFERENT IS EVER READ (scrappy-f2uw). Every entry is classified from ``lstat``,
    and only a REGULAR file is ever opened. ``stat`` used to be the primary call, so a
    seeded path replaced by a link into the original profile was followed: the manifest
    then recorded the EXTERNAL file's size and sha256 as though they were the region's
    own, and the instrument read a profile it must never touch. Validating the root says
    nothing about its descendants, which is the same lesson scrappy-31k9 taught about
    the launcher's creation destinations.

    THE EXACT BOUNDARY, because the looser claim would be false (scrappy-tban).
    ``os.walk()`` classifies each entry with ``DirEntry.is_dir()``, which STATS THE
    REFERENT: that is why a link to a directory arrives in ``dirnames`` and a broken one
    arrives in ``filenames``. So referent METADATA is consulted, by os.walk, to sort
    entries. What is guaranteed here is narrower and is what the defect needed: no
    referent's CONTENT is ever read, no linked directory is ever descended into, and no
    recorded field is ever taken from a referent. Both classifications converge on the
    same ``symlink`` entry built from lstat and readlink, so the sorting cannot change
    what is measured.

    AND IT HOLDS FOR A TREE THAT IS STABLE DURING THE SCAN. Traversal is by PATHNAME, so
    the lstat here and the open inside hash_file are separate operations on the same
    name. WHERE O_NOFOLLOW IS AVAILABLE, a final component swapped for a symlink between
    them is refused and becomes a scan error, so the measurement is VOIDED rather than
    silently taken from outside the region. WHERE IT IS NOT AVAILABLE the flag degrades
    to zero and that race is NOT closed. An ancestor directory swapped for a link
    mid-scan is not covered on any platform. This instrument is single-measurement by
    design and is not claimed to be correct under concurrent mutation of the region it
    measures.
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

    for dirpath, dirnames, filenames in os.walk(base, onerror=_record_walk_error):
        # A SYMLINKED DIRECTORY is never descended into (os.walk does not follow links
        # by default) and never appears in ``filenames``, so it used to leave NO TRACE
        # AT ALL: the link and everything behind it were absent from both manifests and
        # no error was raised. That is another route to a baseline forged out of
        # silence, so the link itself is recorded here. It is still not traversed.
        for name in dirnames:
            dir_path = Path(dirpath) / name
            rel = dir_path.relative_to(base).as_posix()
            try:
                info = dir_path.lstat()
                if stat.S_ISLNK(info.st_mode):
                    entries[rel] = _symlink_entry(dir_path, info)
            except OSError as error:
                scan_errors.append(f"lstat {dir_path}: {error}")

        for name in filenames:
            file_path = Path(dirpath) / name
            rel = file_path.relative_to(base).as_posix()
            try:
                info = file_path.lstat()
            except OSError as error:
                scan_errors.append(f"lstat {file_path}: {error}")
                continue

            if stat.S_ISLNK(info.st_mode):
                # Recorded whether or not the target resolves. A broken link is a real
                # observable state of the region and stays VISIBLE; a link whose target
                # merely cannot be read is no longer mistaken for one (scrappy-ni4w).
                try:
                    entries[rel] = _symlink_entry(file_path, info)
                except OSError as error:
                    scan_errors.append(f"readlink {file_path}: {error}")
                continue

            if not stat.S_ISREG(info.st_mode):
                # A fifo, socket or device node. Recorded, never opened: reading a fifo
                # would block the measurement forever.
                entries[rel] = {"kind": "special", "size": info.st_size, "sha256": None}
                continue

            entry: dict[str, Any] = {"kind": "file", "size": info.st_size, "sha256": None}
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

    A path is ``modified`` when its size changes, when its KIND changes, when a symlink
    retargets, or when a recorded seed hash changes or is LOST. Directory mtimes are
    never consulted.

    KIND AND TARGET ARE LOAD-BEARING, not decoration (scrappy-st0h). Comparing size and
    hash alone let a destroyed seed pass as unchanged: replacing the 32-byte seeded
    command_history with a DANGLING LINK whose target string is also 32 bytes left the
    size equal and the hash None, and ``hash_changed`` requires BOTH hashes to exist, so
    the diff was empty. The seeded file whose growth is this instrument's entire
    measured signal could be destroyed without generating a single operation.
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
        kind_changed = prior.get("kind") != current.get("kind")
        target_changed = prior.get("target") != current.get("target")
        hash_changed = (
            prior.get("sha256") is not None
            and current.get("sha256") is not None
            and prior["sha256"] != current["sha256"]
        )
        # Losing a hash that was recorded before is LOSS OF EVIDENCE, not an absence of
        # change, and absence proves nothing (L-4).
        hash_lost = prior.get("sha256") is not None and current.get("sha256") is None
        if size_changed or kind_changed or target_changed or hash_changed or hash_lost:
            ops.append({"op": "modified", "path": rel, "before": prior, "after": current})
    return ops


def escape_paths(ops: list[dict[str, Any]]) -> list[str]:
    """Reduce a diff to the sorted set of profile paths that escaped (any operation)."""
    return sorted({op["path"] for op in ops})
