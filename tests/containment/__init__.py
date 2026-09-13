"""Containment instrument for scrappy-i2jo PR-1.

This package is the MEASUREMENT half of the contained verification harness. The
BOUNDARY is the launcher environment assigned by scripts/contained-pytest.sh; the
helpers here seed a disposable profile, manifest it before and after a run, and
compare the delta against a checked-in per-platform/per-selection baseline that
shrinks as later PRs land (plan rules R-D, R-F).

Two invariants the review paid for:
  - A manifest is a MEASUREMENT, never the protection mechanism (R-F).
  - Full manifests are compared per path; directory mtimes are NEVER used, because
    the R1 reproduction changed a file while its parent directory mtime did not.

Every helper only ever touches directories the instrument itself created. None of
them read, write, list or hash the real user profile, not even to compare.
"""
