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

PUBLICATION GATE (bead scrappy-jxh4). A VACUOUS PASS LOOKS EXACTLY LIKE A PERFECT PASS.
The first attempt at a baseline was produced by a runner that applied the contained HOME
into the environment it handed the launcher. The launcher CORRECTLY refused (preflight
FAIL home-not-real, rc=11) and pytest never started; the runner diffed an unchanged
profile and published a baseline reporting escape_count 0. An empty baseline is exactly
the success condition the FINAL ACCEPTANCE GATE for the whole seven-PR sequence looks
for, so that path could forge the acceptance signal.

There is therefore NO UNGUARDED WRITER in this module. ``publish_baseline`` is the only
way to write a baseline and it requires ALL THREE of:

  1. SUCCESSFUL COMPLETION   pytest ran to completion and reported success.
  2. NONEMPTY SELECTION      tests were selected AND at least one produced a
                             NON-SKIPPED outcome (see the proxy note below).
  3. RECORDED RESULTS        the outcome counts are carried IN the baseline file.

EVIDENCE IS STRUCTURAL, NOT SCRAPED. The evidence is pytest's own JUnit XML session
report, not its console text. Two review findings drove this:

  - SKIPPED OUTCOMES CANNOT ESTABLISH A SELECTION RAN. Counting skipped tests toward the
    selection let an ALL-SKIPPED run publish an empty baseline: pytest exits 0, nothing
    is selected-empty, nothing fails, and the session touches almost nothing, so of
    course the escape set was empty. Ordinary opt-in integration fixtures skip exactly
    like this. ``non_skipped`` therefore counts outcomes that were NOT reported as
    skipped, and a run with zero of them is refused.

    ``non_skipped`` IS A CONSERVATIVE PROXY, NOT A COUNT OF TEST BODIES THAT RAN, and it
    is deliberately named for what it measures. It is NOT a count of test bodies that
    ran, in either direction:

      - It UNDERCOUNTS execution. A test body may do substantial work before calling
        pytest.skip and still be reported as skipped (tests/integration/
        test_bridge_data_flow.py and tests/integration/real_terminal_scenario.py both do
        exactly that). _pytest/junitxml.py also reports ordinary xfails as skipped.
      - It OVERCOUNTS execution. A test whose SETUP failed never reaches its body, but
        _pytest/junitxml.py calls append_error for a failed setup or teardown rather than
        recording a skip, so such a test counts as non-skipped here. That case cannot
        reach publication anyway, because errors are refused separately.

    The gate needs only the conservative direction: zero non-skipped outcomes means
    nothing in the session evidences that the selection ran, which is enough to refuse.
  - SCRAPED TEXT IS NOT A SESSION RESULT. A console-line parser accepts any line that
    happens to match, and a hand-built result object could assert success with no counts
    behind it. The JUnit report is written BY PYTEST at the end of a real session, and
    every published field is derived from it. ``publication_refusals`` additionally
    checks the counts against each other, so an internally inconsistent result is refused
    however it was constructed, and it binds the SELECTION LABEL to the evidence so a
    result from one selection cannot be published under another selection's name.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import xml.etree.ElementTree as ElementTree
from dataclasses import asdict, dataclass, field
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


class BaselinePublicationRefused(RuntimeError):
    """Raised when a run does not satisfy the publication gate (scrappy-jxh4).

    Carries every failed condition so a refusal names the mechanism, not just the fact.
    """

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = list(reasons)
        super().__init__(
            "refusing to publish a baseline: "
            + "; ".join(self.reasons)
            + ". An unearned empty baseline is indistinguishable from a perfect result "
            "and would forge the final acceptance signal (scrappy-jxh4)."
        )


class MissingRunEvidence(RuntimeError):
    """Raised when the JUnit session report is absent or unreadable.

    A separate error from a refusal: a refusal means "this run did not earn a baseline",
    this means "there is no run to judge at all". Both prevent publication.
    """


@dataclass(frozen=True)
class RunResult:
    """Evidence that a contained suite run actually happened, derived from JUnit XML.

    ``non_skipped`` is the load-bearing field. It is NOT ``tests``: a fully skipped
    session selects tests and exits 0, which would otherwise publish a perfectly empty
    baseline off a session that produced no non-skipped outcome at all.

    ``report_sha256`` binds these counts to the exact bytes they were derived from, so a
    result cannot be carried across to a different report (see publication_refusals).
    """

    selection: str
    returncode: int
    tests: int
    non_skipped: int
    passed: int
    failures: int
    errors: int
    skipped: int
    report_path: str = ""
    report_sha256: str = ""
    started_at: float = 0.0
    argv: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["argv"] = list(self.argv)
        return payload


# A report's mtime is compared against a wall-clock start, so allow for coarse
# filesystem timestamp granularity. This is a SECONDARY check: the primary guarantee is
# that begin_run REMOVES any existing report, so a report present afterwards is new.
MTIME_TOLERANCE_SECONDS = 2.0


@dataclass(frozen=True)
class RunEvidence:
    """A claim on one report path for the duration of ONE measurement (scrappy-lfa7).

    WITHOUT THIS, A STALE REPORT EARNS A FRESH MEASUREMENT. Hashing and re-parsing a
    report proves the counts match those bytes; it does NOT prove the bytes belong to the
    run whose escape set is being published. Concretely: leave a successful report in
    place, start a "measurement" that never runs a session (an accidental --help returns
    rc=0 without one, and _pytest/junitxml.py writes the report in pytest_sessionfinish,
    so none is produced), then parse the surviving report with the new invocation's rc and
    argv. Every byte-level check passes and the new, empty diff gets published.

    begin_run therefore REMOVES any existing report before the suite starts. A report
    present afterwards was written by this session or there is no evidence at all.
    """

    report_path: Path
    started_at: float


def begin_run(report_path: str | os.PathLike[str]) -> RunEvidence:
    """Claim a report path for one measurement, clearing any previous report.

    Call this BEFORE launching the suite, and pass the result to parse_junit_report. The
    lifecycle lives here, in committed and tested code, rather than in whatever script
    happens to be driving the measurement.
    """
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    return RunEvidence(report_path=path, started_at=time.time())


def _iter_testsuites(root: ElementTree.Element) -> list[ElementTree.Element]:
    """Return the testsuite elements, whether the root is testsuites or a testsuite."""
    if root.tag == "testsuite":
        return [root]
    return list(root.iter("testsuite"))


def parse_junit_report(
    evidence: RunEvidence,
    *,
    selection: str,
    returncode: int,
    argv: tuple[str, ...] = (),
) -> RunResult:
    """Build a RunResult from pytest's OWN JUnit XML session report.

    Takes the RunEvidence returned by begin_run, so the report can only be one this
    measurement produced. Raises MissingRunEvidence when the report does not exist, is
    not parseable, or predates the run: that is what a launcher refusal, a crash, a kill
    before session end, and an invocation that never started a session all look like.
    """
    path = evidence.report_path
    if not path.exists():
        raise MissingRunEvidence(
            f"no JUnit session report at {path}. pytest writes it at the end of a real "
            f"session, so its absence means the suite never completed (rc={returncode})."
        )
    mtime = path.stat().st_mtime
    if mtime < evidence.started_at - MTIME_TOLERANCE_SECONDS:
        raise MissingRunEvidence(
            f"the JUnit session report at {path} predates this run (written {mtime}, run "
            f"started {evidence.started_at}). It belongs to an earlier session."
        )
    try:
        root = ElementTree.parse(path).getroot()
    except ElementTree.ParseError as exc:
        raise MissingRunEvidence(f"JUnit session report at {path} is not parseable: {exc}") from exc

    suites = _iter_testsuites(root)
    if not suites:
        raise MissingRunEvidence(f"JUnit session report at {path} contains no testsuite element")

    def total(attr: str) -> int:
        return sum(int(suite.get(attr, "0") or 0) for suite in suites)

    tests = total("tests")
    failures = total("failures")
    errors = total("errors")
    skipped = total("skipped")
    # Conservative proxy: outcomes pytest did NOT report as skipped. See the module
    # docstring for exactly what this does and does not establish.
    non_skipped = tests - skipped
    passed = tests - failures - errors - skipped
    return RunResult(
        selection=selection,
        returncode=returncode,
        tests=tests,
        non_skipped=non_skipped,
        passed=passed,
        failures=failures,
        errors=errors,
        skipped=skipped,
        report_path=str(path),
        report_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        started_at=evidence.started_at,
        argv=argv,
    )


_EVIDENCE_FIELDS = ("tests", "non_skipped", "passed", "failures", "errors", "skipped")


def _evidence_refusals(run: RunResult) -> list[str]:
    """Re-derive the counts FROM THE REPORT BYTES and refuse any disagreement.

    Validating arithmetic and file existence is not enough (review R2 finding 1). Two
    ACCIDENTAL routes reach a wrong publication without any malicious suite:

      - A RunResult from a good run is retained while a second run overwrites the SAME
        report path. The retained object still validates, still points at an existing
        file, and publishes the second run's measured diff under the first run's
        evidence.
      - A hand-built result names any existing file, or a directory, as its report.

    So the report is re-hashed against the hash captured when the counts were derived,
    and re-parsed and compared field by field. Evidence that cannot be re-derived from
    the bytes on disk is not evidence.
    """
    if not run.report_path:
        return ["the run carries no JUnit session report path, so its counts are unevidenced"]
    path = Path(run.report_path)
    if not path.exists():
        return [f"the recorded JUnit session report {path} no longer exists"]
    if not run.report_sha256:
        return [f"the run carries no content hash for {path}, so its counts are unbound to it"]
    try:
        current_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        return [f"the recorded JUnit session report {path} could not be read: {exc}"]
    if current_digest != run.report_sha256:
        return [
            f"the JUnit session report {path} has CHANGED since these counts were "
            f"derived (recorded {run.report_sha256[:16]}..., now {current_digest[:16]}...); "
            "the results belong to a different run"
        ]
    if run.started_at <= 0:
        return [f"the run carries no start time, so {path} cannot be shown to belong to it"]
    if path.stat().st_mtime < run.started_at - MTIME_TOLERANCE_SECONDS:
        return [
            f"the JUnit session report {path} predates the run that cites it; the "
            "results belong to an earlier session"
        ]
    try:
        rederived = parse_junit_report(
            RunEvidence(report_path=path, started_at=run.started_at),
            selection=run.selection,
            returncode=run.returncode,
            argv=run.argv,
        )
    except MissingRunEvidence as exc:
        return [f"the recorded report is not a usable session result: {exc}"]
    mismatched = [
        f"{name} recorded {getattr(run, name)} but report says {getattr(rederived, name)}"
        for name in _EVIDENCE_FIELDS
        if getattr(run, name) != getattr(rederived, name)
    ]
    if mismatched:
        return ["recorded counts do not match the report they cite: " + "; ".join(mismatched)]
    return []


def publication_refusals(run: RunResult, *, selection: str | None = None) -> list[str]:
    """Return every reason ``run`` may not back a baseline. Empty means publishable.

    Reported as a LIST so a refusal names every unmet condition at once. The consistency
    checks are applied to whatever object is handed in, so a hand-built RunResult that
    merely asserts success is refused just as a real failing run would be.
    """
    reasons: list[str] = []

    # CONDITION 1: successful completion.
    if run.returncode != 0:
        reasons.append(f"pytest returned {run.returncode}, not 0")
    if run.failures:
        reasons.append(f"{run.failures} test(s) failed; a baseline measured under failures is not trusted")
    if run.errors:
        reasons.append(f"{run.errors} collection/setup error(s) occurred")

    # CONDITION 2: nonempty selection AND real execution.
    if run.tests <= 0:
        reasons.append(
            "the intended selection was EMPTY (0 tests selected); a run that selects "
            "nothing touches nothing and its empty escape set means nothing"
        )
    if run.non_skipped <= 0:
        reasons.append(
            f"NO NON-SKIPPED OUTCOME ({run.tests} selected, {run.skipped} skipped). An "
            "all-skipped session exits 0, so nothing in it evidences that the selection "
            "ran and its empty escape set measures the skips, not containment"
        )

    # CONDITION 3: recorded results that are internally consistent and bound to evidence.
    if not run.selection:
        reasons.append("the run carries no selection label, so its results are unbound")
    if selection is not None and run.selection != selection:
        reasons.append(
            f"selection mismatch: results were recorded for {run.selection!r} but are "
            f"being published as {selection!r}; evidence must be bound to its selection"
        )
    if not run.argv:
        reasons.append("the run carries no recorded pytest argv, so the selection it measured is unverifiable")
    reasons.extend(_evidence_refusals(run))
    if any(value < 0 for value in (run.tests, run.non_skipped, run.passed, run.failures, run.errors, run.skipped)):
        reasons.append("the recorded counts contain a negative value")
    if run.passed + run.failures + run.errors + run.skipped != run.tests:
        reasons.append(
            f"recorded counts are inconsistent: passed {run.passed} + failures "
            f"{run.failures} + errors {run.errors} + skipped {run.skipped} != tests {run.tests}"
        )
    if run.non_skipped != run.tests - run.skipped:
        reasons.append(
            f"recorded outcome split is inconsistent: non_skipped {run.non_skipped} != "
            f"tests {run.tests} - skipped {run.skipped}"
        )
    return reasons


REPO_ROOT = Path(__file__).resolve().parents[2]


def _portable_run_payload(run: RunResult) -> dict[str, Any]:
    """Return the recorded results with absolute machine paths made repo-relative.

    The baseline is a COMMITTED artifact that PR-2 through PR-7 shrink and diff. Absolute
    worktree paths would make it churn on every machine and would leak one developer's
    filesystem layout into the repository, while adding nothing: the evidence that binds
    these counts to a real session is ``report_sha256``, which is machine-independent.
    """
    payload = run.as_dict()
    prefix = str(REPO_ROOT)

    def relative(value: str) -> str:
        return value.replace(prefix + "/", "").replace(prefix, ".")

    payload["report_path"] = relative(payload["report_path"])
    payload["argv"] = [relative(token) for token in payload["argv"]]
    return payload


def publish_baseline(
    selection: str,
    ops: list[dict[str, Any]],
    run: RunResult,
    *,
    platform: str | None = None,
) -> Path:
    """Write a measured escape set as the baseline, ONLY if ``run`` earns it.

    This is the module's ONLY writer. It raises BaselinePublicationRefused and writes
    NOTHING when the gate is not satisfied. The recorded run results are carried in the
    file, so no baseline can later be read without its evidence.
    """
    reasons = publication_refusals(run, selection=selection)
    if reasons:
        raise BaselinePublicationRefused(reasons)

    path = baseline_path(selection, platform)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "platform": platform or current_platform(),
        "selection": selection,
        "run": _portable_run_payload(run),
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
