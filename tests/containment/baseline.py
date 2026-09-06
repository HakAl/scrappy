"""Per-platform, per-selection escape baselines (plan 3d, T-4).

A baseline is the EXPECTED escape set: the profile paths that a contained run is known
to still touch at a given point in the PR sequence. It SHRINKS as PR-2..PR-7 land and is
empty when routing is complete (T-4: retirement is earned by the empty baseline being
OBSERVED, not by a PR number).

CRITICAL: a baseline's contents are a MEASUREMENT produced by a contained run, never a
prediction written in advance (plan PR-1 EXPECTED DELTAS). This module provides the
writer, the loader and the comparison; it does not ship fabricated baseline contents.

Baselines are separated per platform AND per selection because plan S-1 (platform) and
S-5 (child forwarding) make them genuinely different. The filename makes both visible:

    escape-baseline.<platform>.<selection>.json      (platform e.g. darwin, linux)
                                                      (selection e.g. default, integration)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


BASELINE_DIR = Path(__file__).resolve().parent / "baselines"


def current_platform() -> str:
    """Return the platform tag used in baseline filenames (sys.platform)."""
    return sys.platform


def baseline_filename(selection: str, platform: str | None = None) -> str:
    """Return the baseline filename for a platform and selection."""
    return f"escape-baseline.{platform or current_platform()}.{selection}.json"


def baseline_path(selection: str, platform: str | None = None) -> Path:
    """Return the full baseline path for a platform and selection."""
    return BASELINE_DIR / baseline_filename(selection, platform)


def save_baseline(selection: str, ops: list[dict[str, Any]], *, platform: str | None = None) -> Path:
    """Write a measured escape set as the baseline for a platform/selection.

    Intended for the architect-owned first contained run. Sorted and pretty-printed so
    the file diffs cleanly as it shrinks.
    """
    path = baseline_path(selection, platform)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "platform": platform or current_platform(),
        "selection": selection,
        "escapes": sorted(ops, key=lambda op: (op["path"], op["op"])),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_baseline(selection: str, *, platform: str | None = None) -> dict[str, Any] | None:
    """Load a baseline, or return None if it has not been measured yet."""
    path = baseline_path(selection, platform)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def compare_to_baseline(
    observed_ops: list[dict[str, Any]],
    baseline: dict[str, Any],
) -> dict[str, list[str]]:
    """Compare an observed escape set against a baseline.

    Returns the path-level differences as {"new": [...], "cleared": [...]}. ``new`` is a
    regression (a path escaping that the baseline did not expect); ``cleared`` is
    progress (a baseline path that no longer escapes) and is expected to grow as PRs land.
    """
    observed = {op["path"] for op in observed_ops}
    expected = {op["path"] for op in baseline.get("escapes", [])}
    return {
        "new": sorted(observed - expected),
        "cleared": sorted(expected - observed),
    }
