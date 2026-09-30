"""Seed a disposable profile with known contents at known sizes (plan 3d, D-6).

An overwrite of an EMPTY profile is indistinguishable from a create; an overwrite of a
SEEDED file is unambiguous. That is exactly how the R1 escape was found: a 23-byte
seeded command_history came back at 104 bytes with test commands appended.

PR-1 seeds command_history and the platform config file. BY DEFAULT IT STILL DOES NOT
seed rate_limits.json, and that two-file default contract is unchanged: every existing
caller gets exactly the same two entries it always did.

RATE-LIMITS SEEDING IS AVAILABLE ONLY AS AN EXPLICIT OPT-IN (scrappy-i2jo full-workload
evidence). `seed_profile(home, include_rate_limits=True)` adds ONE further seed. The
historical deferral reason was a KeyError 'last_reset' from a MALFORMED state; the
opt-in payload here is COMPLETE AND VALID, so it never reaches that missing-key defect.
Note validity does NOT imply no reset: RATE_LIMITS_BYTES is deliberately EXPIRED, so a
workload may legitimately attempt a reset. If the ambient file is rewritten, that is a
FINDING, never an allowed exception. scrappy-cktc remains a separate bug about genuinely
malformed state and is neither fixed nor worked around here.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import platformdirs

from .manifest import ensure_disposable


APP_NAME = "scrappy"

# Deterministic seed payloads. Their bytes and lengths are fixed so that any suite
# write is visible as a size or hash change against the manifest.
COMMAND_HISTORY_BYTES = b"seed-help\nseed-status\nseed-quit\n"
CONFIG_JSON_BYTES = b'{"_seed": "scrappy-i2jo-pr1", "providers": {}}\n'

# OPT-IN ONLY. Complete and VALID rate-limit state in the exact shape the tracker
# itself writes (orchestrator/rate_limiting/tracker.py _initialise_empty), so it never
# hits the missing-key defect. Deliberately EXPIRED (August), because a valid expired
# state is the honest way to exercise the reset branch: the mapping exists, so the
# direct last_reset indexing is safe. 124 bytes,
# sha256 e8a5b9bb73b62b20a61664958fae010bea8e26ffd1433d906acbb470cb951a9e.
RATE_LIMITS_BYTES = (
    b'{\n'
    b'  "providers": {},\n'
    b'  "last_reset": {"daily": "2026-08-01", "monthly": "2026-08"},\n'
    b'  "created_at": "2026-08-01T00:00:00"\n'
    b'}\n'
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def platform_config_file() -> Path:
    """Return the platform config file path derived from the ambient (contained) env.

    Uses the same platformdirs call the application uses (infrastructure/paths.py:25),
    so the seed lands exactly where U-1's USER_CONFIG_FILE resolves.
    """
    return Path(platformdirs.user_config_dir(APP_NAME)) / "config.json"


def command_history_file(home_dir: str | os.PathLike[str]) -> Path:
    """Return the command-history path under the contained home (cli/command_history.py:201)."""
    return Path(home_dir) / ".scrappy" / "command_history"


def rate_limits_file() -> Path:
    """Return the AMBIENT rate-limits path derived from the contained env.

    Mirrors the production resolution: ScrappyPathProvider.rate_limits_file() is
    ``user_data_dir / "rate_limits.json"`` (infrastructure/paths.py:115-117), and
    ``user_data_dir`` comes from the same platformdirs lookup used here. Deriving it
    this way means the seed lands exactly where the application resolves it.

    IT DELIBERATELY DOES NOT CALL ``ensure_user_dir()``. That method invokes BOTH
    migration routines (paths.py:160-167), so calling it to obtain a path would mutate
    state before the seed was written, which is precisely what this seeding must not do.
    """
    return Path(platformdirs.user_data_dir(APP_NAME)) / "rate_limits.json"


def _validated_target(home: Path, target: Path) -> Path:
    """Resolve ``target`` and refuse it unless it lands inside the measured home.

    ``ensure_disposable`` resolves the path, which FOLLOWS SYMLINKS, so a link whose
    referent escapes the marker region is rejected here rather than written through.
    The containment check is then made against the measured home itself.

    This performs NO mutation. All targets are validated before any directory is
    created or any byte is written, so a refusal leaves the profile untouched.
    """
    resolved = ensure_disposable(target)
    if home != resolved and home not in resolved.parents:
        raise ValueError(f"seed target {resolved} is not under the measured home {home}")
    return resolved


def seed_profile(
    home_dir: str | os.PathLike[str],
    *,
    include_rate_limits: bool = False,
) -> dict[str, dict[str, Any]]:
    """Seed the disposable profile and return a manifest of the seeded files.

    The returned mapping is keyed by path RELATIVE to ``home_dir`` (the measured
    region) and records the expected size and sha256 of each seed, suitable for
    passing straight into ``manifest.snapshot(..., hashed=...)`` and for comparison.

    Args:
        home_dir: the disposable measured home.
        include_rate_limits: OPT-IN, default OFF. When False the returned manifest and
            the files written are exactly the historical two, so no existing caller
            changes behaviour. Keyword-only and defaulted, so no positional call breaks.

    VALIDATION PRECEDES MUTATION. Every target is resolved and containment-checked
    BEFORE the first mkdir or write, so an out-of-home or symlink-escaping target is
    refused with nothing written. A write-then-check order would leave a partially
    seeded profile behind on refusal.
    """
    home = ensure_disposable(home_dir)

    seeds: list[tuple[Path, bytes]] = [
        (command_history_file(home), COMMAND_HISTORY_BYTES),
        (platform_config_file(), CONFIG_JSON_BYTES),
    ]
    if include_rate_limits:
        seeds.append((rate_limits_file(), RATE_LIMITS_BYTES))

    # Phase 1: validate everything. No mutation happens in this loop.
    validated: list[tuple[Path, bytes]] = [
        (_validated_target(home, target), payload) for target, payload in seeds
    ]

    # Phase 2: only now write.
    manifest: dict[str, dict[str, Any]] = {}
    for resolved, payload in validated:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_bytes(payload)
        rel = resolved.relative_to(home).as_posix()
        manifest[rel] = {"kind": "file", "size": len(payload), "sha256": _sha256(payload)}

    return manifest
