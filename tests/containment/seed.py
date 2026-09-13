"""Seed a disposable profile with known contents at known sizes (plan 3d, D-6).

An overwrite of an EMPTY profile is indistinguishable from a create; an overwrite of a
SEEDED file is unambiguous. That is exactly how the R1 escape was found: a 23-byte
seeded command_history came back at 104 bytes with test commands appended.

PR-1 seeds command_history and the platform config file. It DOES NOT seed
rate_limits.json: a seeded rate-limits file currently trips KeyError 'last_reset' from
rate_limiting/factory.py:180 during AgentOrchestrator.__init__ (bead scrappy-cktc, a
behaviour bug). Rate-limits seeding turns on in PR-4, after that bug is fixed with a
failing test first. It must not be typed, configured, or worked around here.
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


def seed_profile(home_dir: str | os.PathLike[str]) -> dict[str, dict[str, Any]]:
    """Seed the disposable profile and return a manifest of the seeded files.

    The returned mapping is keyed by path RELATIVE to ``home_dir`` (the measured
    region) and records the expected size and sha256 of each seed, suitable for
    passing straight into ``manifest.snapshot(..., hashed=...)`` and for comparison.
    """
    home = ensure_disposable(home_dir)

    seeds: list[tuple[Path, bytes]] = [
        (command_history_file(home), COMMAND_HISTORY_BYTES),
        (platform_config_file(), CONFIG_JSON_BYTES),
    ]

    manifest: dict[str, dict[str, Any]] = {}
    for target, payload in seeds:
        resolved = ensure_disposable(target)
        # The platform config file must fall inside the measured region to be seen.
        if home != resolved and home not in resolved.parents:
            raise ValueError(f"seed target {resolved} is not under the measured home {home}")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_bytes(payload)
        rel = resolved.relative_to(home).as_posix()
        manifest[rel] = {"kind": "file", "size": len(payload), "sha256": _sha256(payload)}

    return manifest
