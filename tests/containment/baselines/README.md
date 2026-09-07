# Escape baselines

Each file here is the EXPECTED escape set for one platform and one test selection: the
application-profile paths a contained run is known to still touch at the current point
in the scrappy-i2jo PR sequence.

## Naming

    escape-baseline.<platform>.<selection>.json

- `<platform>`: `sys.platform`, e.g. `darwin`, `linux`. Separate per platform because
  plan S-1 (path resolution) and S-5 (child forwarding) make them genuinely different.
- `<selection>`: `default` for the default suite, `integration` for the integration
  subset that exercises the iTerm2 and tmux child paths.

## These contents are a MEASUREMENT, never a prediction

A baseline is written by `baseline.publish_baseline(...)` from an actual contained run,
not hand-authored in advance (plan PR-1 EXPECTED DELTAS). The first baseline is produced
by the architect-owned first contained suite run (brief section 6).

`escape-baseline.darwin.default.json` is that first measurement, taken on this branch at
the TRUE DEFAULT SELECTION with the instrument included: 5332 selected, 5324 passed, 8
skipped, 0 failures, 0 errors, 106 deselected. Six of the eight skips are the differential
scanner cases in `test_launcher_validation.py` that argparse rejects outright; the other
two pre-date this branch. It records TWO escapes, both U-2 and both routed in PR-2:

- `.scrappy/command_history` MODIFIED, 32 -> 122 bytes with a changed hash. The growth on
  a SEEDED file is the R1 damage reproduced, and it is why seeding with known bytes
  rather than measuring an empty profile is load-bearing: an overwrite of an empty
  profile is indistinguishable from a create.
- `Library/Application Support/scrappy/command_history` CREATED at 101 bytes.

There is no `linux` baseline and no `integration` baseline. Neither has been measured, and
per L-4 an unmeasured baseline is not an empty one.

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

The set SHRINKS as PR-2 through PR-7 route each escaping write to an injected path, and
is empty when routing is complete. Per plan T-4, `HOME`'s boundary role ends when the
baseline is OBSERVED empty, not when any particular PR number lands.
