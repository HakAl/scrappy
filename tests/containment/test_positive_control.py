"""Probe D as a permanent positive control (plan 3d, brief probe D).

A launcher that rejected everything would pass every negative probe and be worthless.
This test proves the legitimate operations still succeed INSIDE the disposable storage:
tempfile allocation lands in the contained scratch, a profile-shaped write succeeds, and
the contained caches directory is writable.

It runs only under scripts/contained-pytest.sh (skipped otherwise), because it asserts
facts about the launcher's assigned environment. It never touches the real profile.

scrappy-aggp: THE INSTRUMENT MUST NOT WRITE INSIDE THE REGION IT MEASURES. The original
version wrote its marker to ``Path.home()/.scrappy/probe_d_marker``, and under the
launcher ``Path.home()`` IS the measured region, so the instrument's own writes appeared
as escape entries in the first measured baseline. A baseline that permanently carries
instrument artifacts can NEVER shrink to empty, and T-4 earns retirement of this
instrument only by OBSERVING an empty baseline.

Every write goes through tests/containment/instrument.py, which guards the target
DIRECTORY BEFORE the first mkdir or allocation. The earlier version guarded after
allocating, which would have left an artifact behind in exactly the misrouting case the
guard exists to catch.
"""

import os
import tempfile
from pathlib import Path

import pytest

from tests.containment import instrument, manifest

CONTAINED = ".pytest_profile" in Path.home().parts
pytestmark = pytest.mark.skipif(
    not CONTAINED, reason="positive control runs only inside scripts/contained-pytest.sh"
)


def measured_root() -> Path:
    """The region the baseline measures: the launcher's contained HOME (plan 3d)."""
    return Path.home().resolve()


def test_tempfile_allocation_lands_in_contained_scratch():
    """Allocation succeeds, and the DIRECTORY is guarded before anything is allocated."""
    allocated = instrument.allocate_temp_file(
        temp_dir=tempfile.gettempdir(), measured_root=measured_root()
    )
    assert ".pytest_profile" in allocated.parts
    # tempfile's chosen directory is the contained scratch the launcher/conftest set.
    assert allocated.parent == Path(tempfile.gettempdir()).resolve()


def test_profile_shaped_write_succeeds_in_disposable_storage(tmp_path):
    """The disposable storage accepts an application-profile-shaped write.

    This is the over-rejection check the original contained-HOME write performed, moved
    outside the measured region (scrappy-aggp).
    """
    target = instrument.write_profile_shaped_marker(
        scratch_root=tmp_path, measured_root=measured_root()
    )
    assert target.read_text(encoding="utf-8") == instrument.PROFILE_MARKER_BYTES
    assert ".pytest_profile" in target.parts


def test_contained_home_is_writable_without_leaving_an_artifact():
    """The contained HOME is a real, writable directory.

    Checked with os.access rather than a write, because ANY write here would enter the
    measured region and the baseline (scrappy-aggp). This is a WEAKER signal than a write
    and is stated as such: it establishes that the launcher created a writable HOME, not
    that an arbitrary application write would land there.
    """
    home = measured_root()
    assert home.is_dir(), f"launcher must create the contained HOME {home}"
    assert os.access(home, os.W_OK), f"contained HOME {home} must be writable"


def test_contained_caches_directory_is_writable():
    hf_home = os.environ.get("HF_HOME")
    assert hf_home, "HF_HOME must be assigned by the launcher"
    probe = instrument.write_cache_marker(caches_root=hf_home, measured_root=measured_root())
    assert probe.read_text(encoding="utf-8") == instrument.CACHE_MARKER_BYTES
    # The caches sibling is deliberately OUTSIDE the measured home region.
    caches = Path(hf_home).resolve()
    assert "caches" in caches.parts
    assert ".pytest_profile" in caches.parts


def test_the_guard_refuses_before_it_mutates(tmp_path):
    """scrappy-aggp, ordering: a misrouted probe refuses with NOTHING written.

    The measured root is set to a directory the probe is then pointed inside. The guard
    must raise AND leave no directory or file behind; a guard that fires after its mkdir
    would leave the tree it was supposed to prevent.
    """
    measured = tmp_path / "home"
    measured.mkdir()
    inside = measured / "would-be-contamination"

    with pytest.raises(manifest.MeasuredRegionContaminationError):
        instrument.write_profile_shaped_marker(scratch_root=inside, measured_root=measured)
    with pytest.raises(manifest.MeasuredRegionContaminationError):
        instrument.write_cache_marker(caches_root=inside, measured_root=measured)
    with pytest.raises(manifest.MeasuredRegionContaminationError):
        instrument.allocate_temp_file(temp_dir=inside, measured_root=measured)

    assert not inside.exists(), "the guard must refuse BEFORE creating anything"
    assert list(measured.iterdir()) == [], "the measured region must be untouched"


def test_every_instrument_write_target_is_outside_the_measured_region(tmp_path):
    """scrappy-aggp regression, LIVE: no probe target resolves inside the measured region.

    A path-level assertion rather than a before/after diff of the live HOME, because a
    live diff taken mid-suite cannot distinguish an instrument artifact from a concurrent
    application escape. The deterministic empty-diff proof is in test_manifest.py.
    """
    home = measured_root()
    written = instrument.perform_probe_writes(
        temp_dir=tempfile.gettempdir(),
        scratch_root=tmp_path,
        caches_root=os.environ["HF_HOME"],
        measured_root=home,
    )
    assert set(written) == {"temp_allocation", "profile_marker", "cache_marker"}
    for name, target in written.items():
        assert home != target and home not in target.parents, (
            f"instrument target {name}={target} is inside the measured region {home}"
        )
