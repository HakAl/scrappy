"""Probe D as a permanent positive control (plan 3d, brief probe D).

A launcher that rejected everything would pass every negative probe and be worthless.
This test proves the legitimate operations still succeed INSIDE the disposable storage:
tempfile allocation lands in the contained scratch, a write to the contained HOME
profile succeeds, and the contained caches directory is writable.

It runs only under scripts/contained-pytest.sh (skipped otherwise), because it asserts
facts about the launcher's assigned environment. It never touches the real profile.
"""

import os
import tempfile
from pathlib import Path

import pytest

CONTAINED = ".pytest_profile" in Path.home().parts
pytestmark = pytest.mark.skipif(
    not CONTAINED, reason="positive control runs only inside scripts/contained-pytest.sh"
)


def test_tempfile_allocation_lands_in_contained_scratch():
    with tempfile.NamedTemporaryFile(prefix="probe-d-", delete=True) as handle:
        allocated = Path(handle.name).resolve()
    assert ".pytest_profile" in allocated.parts
    # tempfile's chosen directory is the contained scratch the launcher/conftest set.
    assert allocated.parent == Path(tempfile.gettempdir()).resolve()


def test_write_to_contained_home_profile_succeeds():
    target = Path.home() / ".scrappy" / "probe_d_marker"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("probe-d\n", encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "probe-d\n"
    assert ".pytest_profile" in target.resolve().parts


def test_contained_caches_directory_is_writable():
    hf_home = os.environ.get("HF_HOME")
    assert hf_home, "HF_HOME must be assigned by the launcher"
    caches = Path(hf_home)
    caches.mkdir(parents=True, exist_ok=True)
    probe = caches / "probe_d_cache_marker"
    probe.write_text("ok\n", encoding="utf-8")
    assert probe.read_text(encoding="utf-8") == "ok\n"
    # The caches sibling is deliberately OUTSIDE the measured home region.
    assert "caches" in caches.resolve().parts
    assert ".pytest_profile" in caches.resolve().parts
