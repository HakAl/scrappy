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

A baseline is written by `baseline.save_baseline(...)` from an actual contained run,
not hand-authored in advance (plan PR-1 EXPECTED DELTAS). The first baseline is produced
by the architect-owned first contained suite run (brief section 6); PR-1 ships the
instrument that produces and compares baselines, and this directory intentionally starts
without any baseline JSON.

## Lifecycle

The set SHRINKS as PR-2 through PR-7 route each escaping write to an injected path, and
is empty when routing is complete. Per plan T-4, `HOME`'s boundary role ends when the
baseline is OBSERVED empty, not when any particular PR number lands.
