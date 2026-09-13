"""Regression tests for the BASELINE PUBLICATION GATE (bead scrappy-jxh4).

The defect these exist to prevent: an architect-side runner applied the contained HOME
into the environment it handed the launcher, the launcher CORRECTLY refused before exec
(preflight FAIL home-not-real, rc=11), pytest NEVER RAN, and the runner nonetheless
diffed an unchanged profile and PUBLISHED a baseline reporting escape_count 0.

An empty baseline is exactly what the FINAL ACCEPTANCE GATE for the seven-PR sequence
looks for (plan T-4: retirement is earned when the baseline is OBSERVED empty). A path
that publishes an unearned empty baseline can forge the acceptance signal for the whole
sequence. A VACUOUS PASS LOOKS EXACTLY LIKE A PERFECT PASS.

Cross-family review then found the SECOND way to reach that same forged signal, which is
covered here too: an ALL-SKIPPED session. It exits 0, selects tests, fails nothing, and
runs no test body, so of course it touches nothing. Ordinary opt-in integration fixtures
skip exactly like that.

Every refusal test asserts BOTH that publication is refused AND that NO FILE WAS WRITTEN.
The second half matters: a refusal that still leaves a file behind has not refused.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from tests.containment import baseline


ARGV = ("-p", "no:randomly", "-q")


@pytest.fixture(autouse=True)
def disposable_baseline_dir(tmp_path, monkeypatch):
    """Point the writer at a disposable directory. NEVER the committed baselines dir."""
    target = tmp_path / "baselines"
    monkeypatch.setattr(baseline, "BASELINE_DIR", target)
    return target


def write_junit(path, *, tests, failures=0, errors=0, skipped=0, wrap=True):
    """Write a JUnit session report in the shape pytest emits."""
    suite = (
        f'<testsuite name="pytest" errors="{errors}" failures="{failures}" '
        f'skipped="{skipped}" tests="{tests}" time="1.0"></testsuite>'
    )
    body = f"<testsuites>{suite}</testsuites>" if wrap else suite
    path.write_text(f'<?xml version="1.0" encoding="utf-8"?>{body}', encoding="utf-8")
    return path


def session(tmp_path, name, *, returncode=0, selection="default", argv=ARGV, **counts):
    """Claim a report path, write the report pytest would have written, then parse it.

    begin_run comes FIRST and clears the path, exactly as a real measurement does; the
    report is then written as if by pytest_sessionfinish.
    """
    evidence = baseline.begin_run(tmp_path / name)
    write_junit(evidence.report_path, **counts)
    return baseline.parse_junit_report(
        evidence, selection=selection, returncode=returncode, argv=argv
    )


def clean_run(tmp_path, *, selection="default"):
    return session(tmp_path, "clean.xml", selection=selection, tests=5197, skipped=2)


def assert_refused(run, disposable_baseline_dir, *, fragment, selection="default", ops=None):
    with pytest.raises(baseline.BaselinePublicationRefused) as excinfo:
        baseline.publish_baseline(selection, ops if ops is not None else [], run)
    assert fragment in str(excinfo.value), str(excinfo.value)
    written = (
        list(disposable_baseline_dir.glob("*.json")) if disposable_baseline_dir.exists() else []
    )
    assert written == [], f"a refused run must leave NO baseline file, found {written}"


# ---------------------------------------------------------------------------
# 1. NO SESSION AT ALL: preflight refusal, crash, kill.
# ---------------------------------------------------------------------------


def test_preflight_refusal_leaves_no_session_report(tmp_path, disposable_baseline_dir):
    """The exact scrappy-jxh4 defect. pytest never ran, so pytest wrote no report."""
    evidence = baseline.begin_run(tmp_path / "never-written.xml")
    with pytest.raises(baseline.MissingRunEvidence) as excinfo:
        baseline.parse_junit_report(evidence, selection="default", returncode=11, argv=ARGV)
    assert "never completed" in str(excinfo.value)
    assert not disposable_baseline_dir.exists()


def test_a_truncated_session_report_is_not_evidence(tmp_path):
    """Killed mid-write: the file exists but is not a parseable session result."""
    evidence = baseline.begin_run(tmp_path / "partial.xml")
    evidence.report_path.write_text('<?xml version="1.0"?><testsuites><testsu', encoding="utf-8")
    with pytest.raises(baseline.MissingRunEvidence):
        baseline.parse_junit_report(evidence, selection="default", returncode=-9, argv=ARGV)


def test_a_report_without_a_testsuite_is_not_evidence(tmp_path):
    evidence = baseline.begin_run(tmp_path / "empty.xml")
    evidence.report_path.write_text(
        '<?xml version="1.0"?><testsuites></testsuites>', encoding="utf-8"
    )
    with pytest.raises(baseline.MissingRunEvidence):
        baseline.parse_junit_report(evidence, selection="default", returncode=0, argv=ARGV)


# ---------------------------------------------------------------------------
# 2. THE ALL-SKIPPED FORGERY. Found by cross-family review.
# ---------------------------------------------------------------------------


def test_an_all_skipped_session_does_not_publish(tmp_path, disposable_baseline_dir):
    """rc=0, tests selected, nothing failed, and NO TEST BODY RAN.

    This is not a contrived input: an opt-in fixture that skips its whole module produces
    exactly this. The session touches nothing, so its escape set is empty for a reason
    that has nothing to do with containment.
    """
    run = session(tmp_path, "skipped.xml", tests=6, skipped=6)

    assert run.tests == 6
    assert run.skipped == 6
    assert run.non_skipped == 0
    assert run.failures == 0 and run.errors == 0
    assert_refused(run, disposable_baseline_dir, fragment="NO NON-SKIPPED OUTCOME")


def test_a_mostly_skipped_session_with_real_execution_does_publish(tmp_path):
    """The gate refuses ZERO execution, not skipping as such. Skips are legitimate."""
    run = session(tmp_path, "mixed.xml", tests=6, skipped=5)

    assert run.non_skipped == 1
    assert baseline.publication_refusals(run, selection="default") == []


# ---------------------------------------------------------------------------
# 3. FAILED AND INTERRUPTED EXECUTION.
# ---------------------------------------------------------------------------


def test_failed_execution_does_not_publish(tmp_path, disposable_baseline_dir):
    run = session(tmp_path, "failed.xml", returncode=1, tests=5177, failures=7, skipped=2)

    assert run.failures == 7
    assert_refused(run, disposable_baseline_dir, fragment="7 test(s) failed")


def test_collection_errors_do_not_publish(tmp_path, disposable_baseline_dir):
    run = session(tmp_path, "errors.xml", returncode=2, tests=3, errors=3)

    assert run.errors == 3
    assert_refused(run, disposable_baseline_dir, fragment="3 collection/setup error(s)")


def test_an_interrupted_session_that_still_wrote_a_report_does_not_publish(
    tmp_path, disposable_baseline_dir
):
    """Worst case: a report IS present but the run was cut short, so rc != 0."""
    run = session(tmp_path, "interrupted.xml", returncode=2, tests=120)

    assert run.non_skipped == 120
    assert_refused(run, disposable_baseline_dir, fragment="returned 2, not 0")


# ---------------------------------------------------------------------------
# 4. EMPTY INTENDED SELECTION.
# ---------------------------------------------------------------------------


def test_empty_selection_does_not_publish(tmp_path, disposable_baseline_dir):
    run = session(tmp_path, "none.xml", returncode=5, tests=0)

    assert run.tests == 0
    assert_refused(run, disposable_baseline_dir, fragment="selection was EMPTY")


# ---------------------------------------------------------------------------
# 5. UNVALIDATED CALLER ASSERTIONS. Found by cross-family review.
# ---------------------------------------------------------------------------


def test_a_hand_built_success_claim_without_counts_does_not_publish(disposable_baseline_dir):
    """A result object that merely ASSERTS success is refused.

    The gate validates the counts against each other, so an internally inconsistent
    result is refused however it was constructed, not only when it came from a real run.
    """
    run = baseline.RunResult(
        selection="default", returncode=0, tests=1, non_skipped=1, passed=0,
        failures=0, errors=0, skipped=0,
    )
    reasons = " ".join(baseline.publication_refusals(run, selection="default"))
    assert "inconsistent" in reasons
    assert "no recorded pytest argv" in reasons
    assert "no JUnit session report path" in reasons
    assert_refused(run, disposable_baseline_dir, fragment="inconsistent")


def test_results_recorded_for_one_selection_cannot_publish_as_another(
    tmp_path, disposable_baseline_dir
):
    """Selection is BOUND to the evidence, not a free label on the file."""
    run = clean_run(tmp_path, selection="integration")

    assert_refused(
        run, disposable_baseline_dir, fragment="selection mismatch", selection="default"
    )


def test_a_run_whose_report_has_since_vanished_does_not_publish(tmp_path, disposable_baseline_dir):
    """The evidence must still be on disk at publication time."""
    run = clean_run(tmp_path)
    (tmp_path / "clean.xml").unlink()

    assert_refused(run, disposable_baseline_dir, fragment="no longer exists")


def test_inconsistent_outcome_split_does_not_publish(tmp_path, disposable_baseline_dir):
    """non_skipped must equal tests - skipped; a claim that it does not is refused."""
    run = clean_run(tmp_path)
    forged = baseline.RunResult(**{**run.as_dict(), "non_skipped": 5197, "argv": run.argv})

    assert_refused(
        forged, disposable_baseline_dir, fragment="recorded outcome split is inconsistent"
    )


# ---------------------------------------------------------------------------
# 5b. EVIDENCE MISASSOCIATION. Found by cross-family review round 2.
#     No malicious suite is required for any of these; they are accidents.
# ---------------------------------------------------------------------------


def test_a_retained_result_cannot_publish_after_the_report_is_overwritten(
    tmp_path, disposable_baseline_dir
):
    """THE ACCIDENT: a good result is kept while a second run reuses the same path.

    The retained object still validates arithmetically and still points at an existing
    file, so existence and consistency checks both pass. Only re-deriving from the bytes
    catches it. Here the second run is all-skipped, so publishing the retained result
    would file the second run's empty measured diff under the first run's evidence.
    """
    run = session(tmp_path, "report.xml", tests=5197, skipped=2)
    assert baseline.publication_refusals(run, selection="default") == []

    write_junit(Path(run.report_path), tests=6, skipped=6)  # a DIFFERENT run, same path

    assert_refused(run, disposable_baseline_dir, fragment="has CHANGED since these counts")


def test_a_result_citing_an_unrelated_existing_file_does_not_publish(
    tmp_path, disposable_baseline_dir
):
    """A hand-built result may not borrow any existing path as its evidence."""
    unrelated = tmp_path / "not-a-report.txt"
    unrelated.write_text("this is not a junit report\n", encoding="utf-8")
    run = baseline.RunResult(
        selection="default", returncode=0, tests=1, non_skipped=1, passed=1,
        failures=0, errors=0, skipped=0, report_path=str(unrelated),
        report_sha256="0" * 64, argv=ARGV,
    )

    assert_refused(run, disposable_baseline_dir, fragment="has CHANGED since these counts")


def test_a_result_whose_counts_disagree_with_its_report_does_not_publish(
    tmp_path, disposable_baseline_dir
):
    """Counts must be RE-DERIVABLE from the cited bytes, not merely self-consistent."""
    import hashlib

    report = write_junit(tmp_path / "real.xml", tests=6, skipped=6)
    digest = hashlib.sha256(report.read_bytes()).hexdigest()
    # Internally consistent, correctly hashed, and simply not what the report says.
    run = baseline.RunResult(
        selection="default", returncode=0, tests=5197, non_skipped=5195, passed=5195,
        failures=0, errors=0, skipped=2, report_path=str(report),
        report_sha256=digest, started_at=time.time() - 1, argv=ARGV,
    )

    assert_refused(run, disposable_baseline_dir, fragment="do not match the report they cite")


def test_a_result_with_no_content_hash_does_not_publish(tmp_path, disposable_baseline_dir):
    report = write_junit(tmp_path / "real.xml", tests=10)
    run = baseline.RunResult(
        selection="default", returncode=0, tests=10, non_skipped=10, passed=10,
        failures=0, errors=0, skipped=0, report_path=str(report), argv=ARGV,
    )

    assert_refused(run, disposable_baseline_dir, fragment="no content hash")


# ---------------------------------------------------------------------------
# 6. THE POSITIVE CASE, and the recorded evidence the gate requires.
# ---------------------------------------------------------------------------


def test_a_completed_clean_run_publishes_with_recorded_results(tmp_path, disposable_baseline_dir):
    ops = [{"op": "modified", "path": ".scrappy/command_history", "before": {}, "after": {}}]
    run = clean_run(tmp_path)
    assert baseline.publication_refusals(run, selection="default") == []

    path = baseline.publish_baseline("default", ops, run, platform="darwin")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["platform"] == "darwin"
    assert payload["selection"] == "default"
    assert payload["escapes"] == ops
    # CONDITION 3: the evidence travels WITH the baseline.
    recorded = payload["run"]
    assert recorded["selection"] == "default"
    assert recorded["returncode"] == 0
    assert recorded["tests"] == 5197
    assert recorded["non_skipped"] == 5195
    assert recorded["passed"] == 5195
    assert recorded["skipped"] == 2
    assert recorded["failures"] == 0
    assert recorded["errors"] == 0
    assert recorded["argv"] == list(ARGV)
    assert recorded["report_path"].endswith("clean.xml")


def test_an_empty_escape_set_publishes_only_when_the_run_earned_it(tmp_path):
    """The T-4 success condition is reachable, but ONLY behind a real, executing run.

    Paired deliberately with the all-skipped and preflight-refusal tests: identical empty
    escape sets, opposite outcomes, and the run evidence is the only difference.
    """
    path = baseline.publish_baseline("default", [], clean_run(tmp_path))

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["escapes"] == []
    assert payload["run"]["non_skipped"] == 5195


def test_a_bare_testsuite_root_is_parsed(tmp_path):
    """pytest emits a bare <testsuite> root in some versions; both shapes must parse."""
    run = session(tmp_path, "bare.xml", tests=10, skipped=1, wrap=False)
    assert run.tests == 10 and run.non_skipped == 9


def test_the_published_payload_carries_no_absolute_worktree_paths(tmp_path):
    """The baseline is committed and diffed by PR-2..PR-7; machine paths would churn.

    The binding evidence is report_sha256, which is machine-independent, so nothing is
    lost by making the recorded paths repo-relative.
    """
    report = tmp_path / "clean.xml"
    run = session(
        tmp_path, "clean.xml", tests=5197, skipped=2,
        argv=("-q", f"--junit-xml={report}"),
    )

    path = baseline.publish_baseline("default", [], run)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert str(baseline.REPO_ROOT) not in json.dumps(payload)
    assert payload["run"]["report_sha256"] == run.report_sha256


# ---------------------------------------------------------------------------
# 5c. STALE EVIDENCE. Found by cross-family review round 3.
#     Byte consistency proves the counts match the report. It does NOT prove the
#     report belongs to THIS measurement.
# ---------------------------------------------------------------------------


def test_begin_run_clears_a_previous_report(tmp_path):
    """The claim on the path is what makes a surviving report impossible to mistake."""
    stale = tmp_path / "junit.xml"
    write_junit(stale, tests=5197, skipped=2)

    evidence = baseline.begin_run(stale)

    assert not evidence.report_path.exists()
    assert evidence.started_at > 0


def test_an_invocation_that_never_ran_a_session_has_no_evidence(tmp_path):
    """THE STALE-REPORT ACCIDENT, end to end.

    A successful report is left in place. A new measurement starts against the same
    destination but the invocation never runs a session (pytest returns 0 for --help
    without one, and the JUnit report is written in pytest_sessionfinish, so none is
    produced). Because begin_run cleared the path, there is simply no evidence to parse:
    the surviving bytes from the earlier session cannot stand in for this one.
    """
    report = tmp_path / "junit.xml"
    write_junit(report, tests=5197, skipped=2)  # a real, successful earlier run

    evidence = baseline.begin_run(report)  # the new measurement claims the path
    # ... the suite never runs, so nothing writes a report ...

    with pytest.raises(baseline.MissingRunEvidence) as excinfo:
        baseline.parse_junit_report(evidence, selection="default", returncode=0, argv=ARGV)
    assert "never completed" in str(excinfo.value)


def test_a_report_predating_the_run_that_cites_it_does_not_publish(
    tmp_path, disposable_baseline_dir
):
    """Belt and braces: even a report that survived clearing is refused as too old."""
    run = clean_run(tmp_path)
    stale = baseline.RunResult(
        **{**run.as_dict(), "started_at": time.time() + 3600, "argv": run.argv}
    )

    assert_refused(stale, disposable_baseline_dir, fragment="predates the run that cites it")
