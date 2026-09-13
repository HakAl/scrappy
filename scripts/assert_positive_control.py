#!/usr/bin/env python3
"""Fail unless EXACTLY the required positive controls executed and passed.

WHY THIS EXISTS. The positive control is the only thing in this repository that
demonstrates the launcher contains anything, and it SKIPS ITSELF when it is not run
under scripts/contained-pytest.sh (its pytestmark keys on ``.pytest_profile`` appearing
in ``Path.home()``). A skipped test is green. So a CI job that merely runs pytest and
checks the exit code reports success in exactly the case where NOTHING WAS VERIFIED,
which is the failure mode this whole bead exists to eliminate: a vacuous pass looks
exactly like a perfect pass.

THE GATE KEYS ON IDENTITY, NOT ON A COUNT (reviewer finding B1). The first version
compared a case COUNT and a classname SUBSTRING, and three different reports defeated it,
all confirmed by execution:
  - a FOREIGN module named ``...test_positive_control_foreign`` passed, because the
    required module name is a PREFIX of it and substring matching cannot tell them apart;
  - SIX COPIES of a single control passed while five required controls were absent,
    because nothing checked uniqueness;
  - a NESTED <testsuite> made three cases count as six, because the walk collected the
    outer and inner suites and then visited the inner cases through both.
A count plus a substring is not a selection. Only an exact set of identities is.

ABSENCE PROVES NOTHING (L-4). A missing, partial or foreign report must never satisfy
this gate, because passing on one would make the job worthless in precisely the situation
it exists to catch.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MODULE = "tests.containment.test_positive_control"

# The EXACT selection this gate requires. tests/containment/test_positive_control_gate.py
# holds this list in step with the test functions that actually exist, because the whole
# defect class here is two lists that can drift apart silently. Adding a seventh control
# must update BOTH, and failing closed until it does is deliberate.
REQUIRED_CONTROLS = frozenset(
    (MODULE, name)
    for name in (
        "test_tempfile_allocation_lands_in_contained_scratch",
        "test_profile_shaped_write_succeeds_in_disposable_storage",
        "test_contained_home_is_writable_without_leaving_an_artifact",
        "test_contained_caches_directory_is_writable",
        "test_the_guard_refuses_before_it_mutates",
        "test_every_instrument_write_target_is_outside_the_measured_region",
    )
)


def outcome(case: ET.Element) -> str:
    for tag, label in (("skipped", "SKIPPED"), ("failure", "FAILED"), ("error", "ERROR")):
        if case.find(tag) is not None:
            return label
    return "PASS"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <junit-xml>", file=sys.stderr)
        return 2

    report = Path(argv[1])
    if not report.is_file():
        print(
            f"FAIL: no report at {report}. The positive control produced NO evidence, so "
            f"nothing about containment is established. An absent report must never "
            f"satisfy this gate.",
            file=sys.stderr,
        )
        return 1

    try:
        root = ET.parse(report).getroot()
    except ET.ParseError as error:
        print(f"FAIL: {report} is not parseable XML: {error}", file=sys.stderr)
        return 1

    # Walk from the DOCUMENT ROOT so every <testcase> is visited EXACTLY ONCE however the
    # suites are nested. Collecting suites first and then walking each one visits a nested
    # suite's cases through both its own element and its ancestor's.
    cases = list(root.iter("testcase"))

    seen: list[tuple[str, str]] = []
    print(f"testcase elements in report: {len(cases)}")
    for case in cases:
        identity = (case.get("classname") or "", case.get("name") or "")
        seen.append(identity)
        required = "required" if identity in REQUIRED_CONTROLS else "NOT REQUIRED"
        print(f"  {outcome(case):8} {identity[0]}.{identity[1]}  [{required}]")

    problems: list[str] = []

    not_passing = [c for c in cases if outcome(c) != "PASS"]
    skipped = [c for c in not_passing if outcome(c) == "SKIPPED"]
    if skipped:
        problems.append(
            f"{len(skipped)} positive control(s) SKIPPED. The launcher environment was "
            f"not in force, so this run verifies NOTHING about containment. A skipped "
            f"positive control must not satisfy this job."
        )
    if len(not_passing) != len(skipped):
        problems.append(f"{len(not_passing) - len(skipped)} case(s) failed or errored.")

    duplicates = sorted({identity for identity in seen if seen.count(identity) > 1})
    if duplicates:
        problems.append(
            f"duplicate case identities: {duplicates}. Repeating one control cannot "
            f"stand in for the controls that are absent."
        )

    observed = set(seen)
    missing = sorted(REQUIRED_CONTROLS - observed)
    extra = sorted(observed - REQUIRED_CONTROLS)
    if missing:
        problems.append(f"required control(s) ABSENT from the report: {missing}")
    if extra:
        problems.append(
            f"case(s) present that are NOT required controls: {extra}. Other tests must "
            f"not be able to satisfy the positive control gate."
        )

    if problems:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1

    print(
        f"OK: exactly the {len(REQUIRED_CONTROLS)} required positive controls EXECUTED "
        f"and passed under the launcher, each once. This is runtime containment evidence "
        f"for this platform, and it is the only kind of evidence that counts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
