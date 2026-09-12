#!/usr/bin/env python3
"""Fail unless every positive control actually EXECUTED and passed.

WHY THIS EXISTS. The positive control is the only thing in this repository that
demonstrates the launcher contains anything, and it SKIPS ITSELF when it is not run
under scripts/contained-pytest.sh (its pytestmark keys on ``.pytest_profile`` appearing
in ``Path.home()``). A skipped test is green. So a CI job that merely runs pytest and
checks the exit code reports success in exactly the case where NOTHING WAS VERIFIED,
which is the failure mode this whole bead exists to eliminate: a vacuous pass looks
exactly like a perfect pass.

This gate therefore refuses three different kinds of silence:
  - the report is MISSING, so nothing can be established from it;
  - a test SKIPPED, so the launcher environment was not actually in force;
  - fewer cases ran than expected, so the selection quietly shrank.

ABSENCE PROVES NOTHING (L-4). Passing on an empty or partial report would make this job
worthless in precisely the situation it is meant to catch.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED_MODULE = "tests.containment.test_positive_control"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <junit-xml> <expected-count>", file=sys.stderr)
        return 2

    report = Path(argv[1])
    expected = int(argv[2])

    if not report.is_file():
        print(
            f"FAIL: no report at {report}. The positive control produced NO evidence, "
            f"so nothing about containment is established. An absent report must never "
            f"satisfy this gate.",
            file=sys.stderr,
        )
        return 1

    root = ET.parse(report).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    cases = [case for suite in suites for case in suite.iter("testcase")]

    skipped = [c for c in cases if c.find("skipped") is not None]
    failed = [c for c in cases if c.find("failure") is not None]
    errored = [c for c in cases if c.find("error") is not None]

    print(f"positive control cases reported: {len(cases)}")
    for case in cases:
        state = "PASS"
        if case.find("skipped") is not None:
            state = "SKIPPED"
        elif case.find("failure") is not None:
            state = "FAILED"
        elif case.find("error") is not None:
            state = "ERROR"
        print(f"  {state:8} {case.get('classname')}.{case.get('name')}")

    problems: list[str] = []
    if skipped:
        problems.append(
            f"{len(skipped)} positive control(s) SKIPPED. The launcher environment was "
            f"not in force, so this run verifies NOTHING about containment. A skipped "
            f"positive control must not satisfy this job."
        )
    if failed or errored:
        problems.append(f"{len(failed)} failed and {len(errored)} errored.")
    if len(cases) != expected:
        problems.append(
            f"expected exactly {expected} cases, got {len(cases)}. The selection "
            f"changed; this gate is pinned so it cannot silently shrink."
        )
    off_module = sorted(
        {c.get("classname", "") for c in cases if EXPECTED_MODULE not in (c.get("classname") or "")}
    )
    if off_module:
        problems.append(
            f"cases from outside {EXPECTED_MODULE} were counted: {off_module}. Other "
            f"tests must not be able to satisfy the positive control gate."
        )

    if problems:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1

    print(
        f"OK: all {expected} positive controls EXECUTED and passed under the launcher. "
        f"This is runtime containment evidence for this platform, and it is the only "
        f"kind of evidence that counts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
