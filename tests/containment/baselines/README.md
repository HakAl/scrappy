# Escape baselines

Each file here is the EXPECTED escape set for one platform and one test selection: the
application-profile paths a contained run is known to still touch at the current point
in the scrappy-i2jo PR sequence.

## Naming

    escape-baseline.<platform>.<selection>.json

- `<platform>`: `sys.platform`, e.g. `darwin`, `linux`. Separate per platform because
  profile path resolution and child-process forwarding differ per platform, so the
  escape sets are genuinely different.
- `<selection>`: `default` for the default suite, `integration` for the integration
  subset that exercises the iTerm2 and tmux child paths.

## These contents are a MEASUREMENT, never a prediction

A baseline is written by `baseline.publish_baseline(...)` from a completed contained run
of the selection it names, never hand-authored in advance.

`escape-baseline.darwin.default.json` is the CURRENT measurement, taken at the TRUE
DEFAULT SELECTION. The instrument was included after the last production helper that took
no provider, `create_orchestrator()` in `orchestrator/core.py`, was given an optional one
and the tests that reached its default were routed to disposable providers.

It was RE-MEASURED at the PR-6 candidate, which threads selected task storage through the
existing graph execution context and captures the CLI code root at composition: 5437
selected, 5429 passed, 8 skipped, 0 failures, 0 errors, 106 deselected. It records NO
escapes. Six of the eight skips are the differential scanner cases in
`test_launcher_validation.py` that argparse rejects outright; the other two pre-date the
instrument.

The PR-5 measurement it supersedes recorded 5419 selected, 5411 passed, 8 skipped, and
likewise NO escapes. The +18 node delta is SOLELY the new routing tests in
`tests/graph/test_task_storage_routing.py`; the PR-6 maintenance edits changed assertions in
existing tests and added NO nodes, and PR-6 removed no tests. An unchanged empty set across
that delta is the expected result, not a new claim: see the node-count note immediately below.

The node count moving does NOT change what an empty set means. Added tests can only widen
what was exercised; they cannot evidence that an unexercised path is contained. Re-read the
three limits below against every re-measurement, not just the first.

An EMPTY set here means exactly one thing: NO DETECTABLE NET FILE CHANGE between the before
and after snapshots of the measured profile region. It is NOT a completion certificate, and
it is not a claim that nothing happened during the run. Read it with three limits in mind:

- It does NOT complete `scrappy-i2jo` and does NOT retire the containment boundary. PR-6 is
  the candidate being measured here and is NOT landed yet; it, PR-7 and final acceptance all
  remain.
- A before/after diff sees NET STATE, not events. A file created and removed inside the run
  is invisible, and so are a `mkdir` that leaves no file and any read. Tests that still
  construct CLI, ScrappyApp or AgentOrchestrator bare can still create the user directories
  and read the legacy directory; `tests/conftest.py` keeps disclosing that.
- It covers `darwin` at the default selection only, measured once.

The measurement that produced it used the EXTENDED hash selection: the two seeded paths plus
the migration destination `Library/Application Support/scrappy/command_history`. That
selection is load-bearing for comparability. A run that hashes only the seeds records
`sha256: null` for any surviving copy, which looks like a content change against a baseline
that hashed it and is not one. Keep the extension when re-measuring.

MEASUREMENT HISTORY, read from this file's own git history, in order:

| published at | escapes | passed | slice |
|---|---|---|---|
| `747bb64`, `4aff5ff`, `032ab5e` | 1 | 5354, 5356, 5356 | before PR-4b |
| `1420986`, `df6d263` | 0 | 5390 | PR-4b, merged at `f33748a` |
| `c7bbfe4`, `d5baf28` | 0 | 5411 | PR-5, merged at `c5c9be0` |
| `e8933be`, `139d2c4`, `fb21307`, `4e07d07` | 0 | 5429 | PR-6 |

The empty set was FIRST ACHIEVED at `1420986`, which landed with PR-4b. PR-4b, PR-5 and PR-6
have all since PRESERVED zero. Do NOT attribute the removal to PR-5 or to PR-6; neither
earned it, and both merely held it across a growing node count.

The last NON-EMPTY measurement, at `032ab5e` and earlier, recorded ONE escape:
`Library/Application Support/scrappy/command_history`
CREATED at 32 bytes, the legacy migration copying the seed into the platform data directory,
triggered by the mock-mode selection tests through the then-providerless `create_orchestrator()`.
Its disappearance was the acceptance delta of THAT earlier provider-routing work, and the
delta was falsified rather than assumed: pointing ONE mock-mode test back at the default
provider and re-measuring brings the same 32-byte copy back, so the instrument is sensitive to
precisely the routing that removed it. PR-5 and PR-6 change nothing about that routing and so
inherit the result rather than re-earning it.
The measurement BEFORE that one recorded TWO escapes, the same copy at 101 bytes and
`.scrappy/command_history` MODIFIED from 32 to 122 bytes with a changed hash. That modification
was the reproduced command-history damage, and it is why seeding with known bytes rather than
measuring an empty profile is load-bearing: an overwrite of an empty profile is
indistinguishable from a create. No `model_cooldowns.json` ever appeared in the measured
region: the persisted cooldown tracker, which reads and can rewrite its store on construction
alone, is bound to the injected provider at every construction that reaches it.

There is no `linux` baseline and no `integration` baseline. Neither has been measured, and
an unmeasured baseline is not an empty one.

## The publication gate (bead scrappy-jxh4)

`publish_baseline` is the ONLY writer, and it refuses unless all three hold:

1. **Successful completion.** pytest ran to the end and reported success. A return code
   alone is not enough: a launcher refusal before `exec` also exits without crashing, and
   the profile it did not touch diffs to an EMPTY escape set, which is indistinguishable
   from the perfect result this whole sequence is trying to earn.
2. **Nonempty intended selection.** Tests were selected AND at least one produced a
   non-skipped outcome. Deselections are not a selection, and an all-skipped session
   evidences nothing about containment: it exits 0 having touched almost nothing.
   `non_skipped` is a deliberately conservative proxy and is NOT a count of test bodies
   that ran; see the note in `baseline.py` for what it over- and under-counts.
3. **Recorded results, bound to one run.** The outcome counts and the pytest argv are
   written INTO the baseline file under `"run"`, so a baseline can never be read without
   the evidence behind it. The counts are re-derived from the report bytes at publication
   and the report is content-hashed, so a result cannot be carried to a different report.
   `begin_run` claims the report path and removes any previous report before the suite
   starts, so a surviving report from an earlier session cannot be mistaken for this one.

Refusal and failed/interrupted execution are covered by `tests/containment/test_baseline.py`.

## Lifecycle

The set SHRINKS as PR-2 through PR-7 route each escaping write to an injected path. It is
now empty for `darwin` at the default selection, which is a MEASUREMENT of that selection
on that platform, not the end of the sequence.

An observed-empty baseline does NOT retire `HOME`'s boundary role and does NOT complete
`scrappy-i2jo`. The file manifest cannot see directory creation or reads, no `linux` or
`integration` selection has ever been measured, and the remaining PRs in the sequence plus
final acceptance still have to land. Retirement is a decision taken against the whole
sequence, never against one empty file list.
