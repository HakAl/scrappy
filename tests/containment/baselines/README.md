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

It was RE-MEASURED at the PR-7 candidate `a6f1979`, which owns configuration selection at
command entry and composes the agent rules loader in the runtime: 5475 selected, 5467
passed, 8 skipped, 0 failures, 0 errors, 106 deselected. It records NO escapes. Six of the
eight skips are the differential scanner cases in `test_launcher_validation.py` that
argparse rejects outright; the other two pre-date the instrument.

THE MEASURED REVISION IS `a6f1979`, NOT the commit that installed this file. The
installation is a separate evidence-only commit that runs no suite; attributing the
measurement to it would misdate the evidence.

The PR-6 measurement it supersedes recorded 5437 selected, 5429 passed, 8 skipped, and
likewise NO escapes; the last committed figure before this installation was 5469 selected
and 5461 passed, taken mid-PR-7. Every node-count increase across PR-7 is added test
material, chiefly the configuration routing, discovery and rules-composition proofs. An
unchanged empty set across that delta is the expected result, not a new claim: see the
node-count note immediately below.

The node count moving does NOT change what an empty set means. Added tests can only widen
what was exercised; they cannot evidence that an unexercised path is contained. Re-read the
three limits below against every re-measurement, not just the first.

An EMPTY set here means exactly one thing: NO DETECTABLE NET FILE CHANGE between the before
and after snapshots of the measured profile region. It is NOT a completion certificate, and
it is not a claim that nothing happened during the run. Read it with three limits in mind:

- It does NOT complete `scrappy-i2jo` and does NOT retire the containment boundary. PR-6 has
  since LANDED, merged as PR #53 at `7992987`. PR-7 is the candidate being measured here and
  is NOT landed yet; it and the separate final acceptance gate both remain. That gate
  requires PR-2 through PR-7 all landed, so PR-7 landing is now its one unmet precondition.
- A before/after diff sees NET STATE, not events. A file created and removed inside the run
  is invisible, and so are a `mkdir` that leaves no file and any read. Tests that still
  construct CLI, ScrappyApp or AgentOrchestrator bare can still create the user directories
  and read the legacy directory; `tests/conftest.py` keeps disclosing that.
- It covers `darwin` at the default selection only, measured once. There is no `linux` and
  no `windows` contained measurement at all, so nothing here speaks to those platforms.
- LAUNCH PROVENANCE IS LIMITED FOR THIS MEASUREMENT, and that limit is recorded rather than
  omitted. The run's own artifacts are complete and were independently reconciled: the JUnit
  digest, the collection receipt, the before/after manifests, the seed hashes, the process
  queries and the Git pins all agree. What could NOT be independently verified is the exact
  OUTER invocation that started the approved wrapper: the original launch record was not
  retrievable, and the reviewer accepted the run as Darwin net-change and local test evidence
  WITH that limitation stated. Concretely unestablished: whether the invocation was detached
  rather than foreground, whether shell no-clobber was in force, and whether the initial
  directory change ran inside the output redirection. Measurement validity, control
  compliance and selection integrity are NOT among the unestablished items. Do not read this
  file as certifying how its measurement was launched.

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
| `e8933be`, `139d2c4`, `fb21307`, `4e07d07`, `e83259d`, `9903a0e` | 0 | 5429 | PR-6, merged at `7992987` |
| `9370342` | 0 | 5430 | PR-6 + 1 Windows regression node |
| `90ce85b` | 0 | 5444 | PR-7 candidate, seeding + routing/discovery proofs |
| `3d80ca3` | 0 | 5448 | PR-7 candidate, after the F3/F5 corrections |
| `c4ffa08` | 0 | 5461 | PR-7 candidate, after F1/F2/F4 |
| this file | 0 | 5467 | PR-7 candidate measured at `a6f1979`, NOT LANDED |

The last four rows are measurements of an UNLANDED branch. They are evidence about a
candidate, not about `main`.

The empty set was FIRST ACHIEVED at `1420986`, which landed with PR-4b, merged at `f33748a`
as PR #51. PR-4b, PR-5 and PR-6 have all since PRESERVED zero, and the PR-7 candidate
continues to preserve it. Do NOT attribute the removal to PR-5, PR-6 or PR-7; none of them
earned it, and each merely held it across a growing node count.

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

### One disclosed deviation in how THIS file was installed

This baseline was installed from a RETAINED run rather than from a live one, by design: the
measurement was reviewed and accepted before installation was authorized, and no rerun was
permitted. `publish_baseline` and its full refusal gate were used unchanged, and the counts
here were re-derived from the report bytes and content-hashed by that gate at publication
time, exactly as for any other baseline.

What was NOT used is `begin_run`. It cannot be: it DELETES the report it claims, so calling
it would have destroyed the accepted evidence. Its freshness guarantee was replaced by the
run's own recorded start time, and the binding rests instead on three facts that do not
depend on it: the report lives inside the run's exclusively reserved output directory, its
mtime falls after that recorded start, and its digest matches the value the run itself
recorded on completion and that review independently rechecked. This is a weaker claim than
`begin_run` provides and is recorded here so nobody has to infer it from the file's history.

## Lifecycle

The set SHRINKS as PR-2 through PR-7 route each escaping write to an injected path. It is
now empty for `darwin` at the default selection, which is a MEASUREMENT of that selection
on that platform, not the end of the sequence.

An observed-empty baseline does NOT retire `HOME`'s boundary role and does NOT complete
`scrappy-i2jo`. The file manifest cannot see directory creation or reads, no `linux` or
`integration` selection has ever been measured, and PR-7 plus the separate final acceptance
gate still have to land. Retirement is a decision taken against the whole sequence, never
against one empty file list.

Nothing here authorizes pointing an instrument at a real user profile. Disposable seeded
verification through `scripts/contained-pytest.sh` is the safety boundary for every
measurement in this sequence, including the final aggregate one.
