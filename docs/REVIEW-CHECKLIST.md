# Review Checklist: design and test quality

Audience: the reviewing agent (different model family from the author, per AGENTS.md).
Apply at plan review and PR review. These are judgment criteria, not mechanical gates.
Items marked GATE CANDIDATE are one small check away from mechanical enforcement;
promote them when a slot opens, then delete them from this file.

Finding discipline: reference the checklist item number, quote the offending code or
plan line, state what would fix it. Verdicts: approve / approve-with-tweaks / blocking.
Never approve on prose claims alone; re-run claimed checks or read their raw output.

## Design

1. Single responsibility: each new or touched class has one reason to change.
   God-class smell: a constructor that builds or holds unrelated subsystems.
2. Open/closed: new behavior arrives by extension (strategy, registry), not by
   widening if/elif chains in existing functions.
3. Liskov: implementations honor the full protocol contract. No partial
   implementations that raise NotImplementedError on contract members.
   GATE CANDIDATE: mypy catches signature drift; behavior contracts need tests.
4. Interface segregation: no fat protocols forcing unused members; split by
   capability (chat vs stream vs embed). Protocols mirror real usage in both
   directions; trim fictional members (grep-prove they are dead first).
5. Dependency inversion: constructors take protocols, not concretions. No direct
   stdlib/network/file instantiation inside business classes.
   GATE CANDIDATE: greppable patterns (sqlite3.connect, requests., Path(...).write_text
   in class bodies outside factory methods).
6. Protocol-first boundary respected: new infrastructure classes ship with their
   protocol; exempt categories are listed in AGENTS.md.

## Tests

7. Behavior over structure: every new test would fail if the feature broke.
   Reject: isinstance-only asserts, "obj is not None", bare hasattr checks.
   GATE CANDIDATE: these have detectable AST signatures.
8. Mock budget: mocks only at external boundaries. A test that only asserts
   mocks were called proves the mocks exist, not that the feature works.
9. Edge cases present for the changed behavior: empty, boundary, error, invalid.
10. No real API calls, ever.
    GATE CANDIDATE: network-guard fixture in conftest that fails any socket use.
11. Isolation: no order dependence, no shared mutable state across tests,
    subprocess use is hermetic. A test must pass alone and in the full suite.

## Plans

12. Right layer: the plan fixes the root cause at the layer that owns it, not the
    layer where the symptom surfaced.
13. Scope: the plan delivers the asked X. Adjacent discoveries become beads, not scope.
14. Declared expectations: expected error-count deltas, test-count deltas, and the
    touched-file list are pre-declared, so post-merge verification is a set-diff
    against declarations, not a judgment call.

## Provenance

Extracted from AGENTS.md 2026-07-04 so implementers carry law and reviewers carry
judgment. Each criterion either graduates to a mechanical gate or stays here as a
named review lens; if nobody would ever cite an item in a finding, delete it.
