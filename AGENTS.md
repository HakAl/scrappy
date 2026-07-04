# Coding Agent Guidelines

CRITICAL: Never use emojis or special characters. Plain ASCII only.

This project uses br (beads rust) for issue tracking. Run `br info` or `br --help` to get started.

## Quick Reference

```bash
br info               # Show active .beads workspace and issue count
br ready              # Find available work
br show <id>          # View issue details
br update <id> --status in_progress  # Claim work
br close <id>         # Complete work
br sync               # Sync with git
```

## Documentation Locations

Two trees, different purposes:

- `docs/` : versioned, ships with the repo. User-facing docs, architecture overviews, behavior of existing systems. If it describes what we have, it goes here.
- `.docs/` : gitignored, local-only working space. Plans, drafts, scratchpads, baselines. If it describes what we want to build, it goes here.

NEVER commit anything under `.docs/`.

## Stay In Scope

When the user asks for X, deliver X. Do not build X plus adjacent infrastructure that might be useful later.

- Asked to plan an epic? Write the plan. Do not start building it.
- Asked to fix bug Y? Fix bug Y. Do not refactor surrounding code unless the fix requires it.
- Untracked artifacts in the worktree are suspicious. Do not ship them unless they are clearly part of the task.
- When in doubt about scope, ask before building.

## Plan Before Building

For any work bigger than a focused bug fix, write a plan first in `.docs/plans/`: what exists, what is missing, the design decisions, the proposed PR sequence. Plans are reviewed before implementation begins. If a plan keeps making the same wrong-layer mistake across revisions, name the rule explicitly and pin it at the top of the plan.

## Cross-Agent Review

Independent review is required for architectural decisions, plan revisions, and choices with multiple defensible answers. The author of an artifact has confirmation bias on their own work.

- The reviewer must be a DIFFERENT MODEL FAMILY from the author of the artifact. Same-family review shares the author's blind spots and does not count as independent.
- Address findings at the root in the artifact. Do not just patch the wording that was criticized.
- Verify claimed checks by re-running them or reading their output. Verify by OUTPUT, never by prose.
- Design and test-quality review criteria live in `.docs/REVIEW-CHECKLIST.md`. The reviewer applies them; implementers do not recite them, they survive them.

## Quality Gate (Before Claiming Done)

A change is not done until:

- `ruff check` passes on the changed surface. Focused path first; broaden when the change touches shared behavior.
- `mypy` passes on touched source files or packages when source code changed.
- The relevant test surface passes, including edge cases for the behavior changed.
- Any skipped or impossible checks are called out explicitly with the reason.
- For user-facing or environment-dependent behavior: do not claim it works in the user's environment until the user confirms. Say exactly what was verified locally and what remains unconfirmed.

## Engineering Rules

- Protocol-first infrastructure: never write a concrete infrastructure class without defining its protocol first. Applies to classes that do I/O, wrap external systems, coordinate services, hold external resources, or are injected as dependencies. Does not apply to dataclasses, enums, exceptions, typed value objects, or local helpers with no reasonable alternate implementation.
- Dependency injection everywhere: no direct instantiation of infrastructure in class bodies. Constructors assign dependencies only: no side effects, no business logic, no I/O. Defaults come from factory methods, not inline construction.
- Delete more than you add when cleanup is safe and in scope.
- Leave touched code better than you found it without expanding the task.
- Fix root causes. Do not defend a workaround when the underlying design is wrong.
- Prefer the smallest change that proves the behavior and preserves existing contracts.
- If pre-existing debt blocks the right fix, document it with `br create` instead of silently working around it.

## Tests

- NEVER make real API calls in tests. Mock only at external boundaries (APIs, file system, network); use real objects for business logic.
- Write behavior tests and edge-case tests. Before writing a test, ask: would this fail if the feature broke? If no, do not write it.
- Structure-only tests, initialization tests, and over-mocked tests do not get written. Definitions and examples are in `.docs/REVIEW-CHECKLIST.md`; the reviewer rejects violations.

## Issue Discovery (Mandatory)

Document issues you encounter with `br create` as you observe them: bugs and unexpected behavior, design violations (god classes, missing protocols, hard-coded dependencies), weak or missing tests, TODO/FIXME debt, documentation gaps. Keep the backlog honest; do not silently absorb problems.

## Command Reference

Use the narrowest command that proves the changed behavior first, then broaden when the change touches shared contracts.

```bash
# Lint source and tests
ruff check src/ tests/

# Type check source
mypy src/

# Default test suite (excludes integration, slow, benchmark by pytest config)
python -m pytest tests/ -v

# Specific test file
python -m pytest tests/test_<module>.py -v

# Full test tree (when validating test infrastructure changes)
python -m pytest tests/ -v --tb=short --strict-markers -o addopts=""

# Integration tests (when touching integration behavior)
python -m pytest tests/integration/ -v --tb=short --strict-markers -o addopts=""
```

If a command cannot run or is blocked by known pre-existing debt, say so explicitly.
