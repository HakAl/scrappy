#!/usr/bin/env python3
"""
Autonomous workflow runner using claude CLI.

Each step runs in a fresh claude session (no context pollution).
State persists in beads between steps.

Usage:
Run it with a TODO file path:

  python scripts/auto.py docs/TODO/PLAN_SOMETHING_UX.md
  or you can use:
  /auto docs/TODO/PLAN_SEMANTIC_SEARCH_UX.md

  It will:
  1. Create a bead to track the work
  2. PLAN (5 fresh Claude sessions) - create and refine the plan, saving to bead
  3. IMPLEMENT - sanity check, implement each step, audit loop
  4. TEST - run tests, fix loop, generate final report
  5. Close the bead

  Each step runs in a fresh claude -p session (no context pollution). State persists in the bead between steps.

  Output streams to console so you can watch progress. The bead tracks everything via comments.
"""

import subprocess
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
BD_EXE = PROJECT_ROOT / ".beads" / "bd.exe"
TEMP_PLAN = PROJECT_ROOT / ".beads" / "tmp_plan.md"
TEMP_NOTES = PROJECT_ROOT / ".beads" / "tmp_notes.md"


def run_claude(prompt: str, timeout: int = 300) -> str:
    """Run claude CLI in print mode with fresh context."""
    try:
        result = subprocess.run(
            ["claude", "-p", "--dangerously-skip-permissions", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=PROJECT_ROOT,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            print(f"Claude error: {result.stderr}", file=sys.stderr)
        return result.stdout
    except subprocess.TimeoutExpired:
        print(f"Timeout after {timeout}s", file=sys.stderr)
        return ""


def run_bd(args: list[str]) -> str:
    """Run beads command."""
    result = subprocess.run(
        [str(BD_EXE)] + args,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def create_bead(title: str, description: str) -> str:
    """Create a bead and return its ID."""
    result = subprocess.run(
        [str(BD_EXE), "create", title, "-t", "task", "-p", "2", "-d", description, "--json"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        encoding="utf-8",
        errors="replace",
    )
    data = json.loads(result.stdout)
    return data["id"]


def update_bead(bead_id: str, design: str = None, notes: str = None) -> None:
    """Update bead with plan or notes."""
    args = [str(BD_EXE), "update", bead_id]
    if design:
        args.extend(["--design", design])
    if notes:
        args.extend(["--notes", notes])
    subprocess.run(args, cwd=PROJECT_ROOT, encoding="utf-8", errors="replace")


def update_bead_from_temp(bead_id: str, field: str = "design") -> bool:
    """Read temp file and update bead. Returns True if file existed."""
    temp_file = TEMP_PLAN if field == "design" else TEMP_NOTES
    if temp_file.exists():
        content = temp_file.read_text(encoding="utf-8")
        if content.strip():
            args = [str(BD_EXE), "update", bead_id, f"--{field}", content]
            subprocess.run(args, cwd=PROJECT_ROOT, encoding="utf-8", errors="replace")
            temp_file.unlink()  # Clean up
            return True
    return False


def add_comment(bead_id: str, comment: str) -> None:
    """Add comment to bead."""
    subprocess.run([str(BD_EXE), "comment", bead_id, comment], cwd=PROJECT_ROOT, encoding="utf-8", errors="replace")


def get_bead(bead_id: str) -> dict:
    """Get bead data."""
    result = subprocess.run(
        [str(BD_EXE), "show", bead_id, "--json"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        encoding="utf-8",
        errors="replace",
    )
    data = json.loads(result.stdout)
    return data[0] if isinstance(data, list) else data


def close_bead(bead_id: str) -> None:
    """Close bead."""
    subprocess.run([str(BD_EXE), "close", bead_id], cwd=PROJECT_ROOT, encoding="utf-8", errors="replace")


# =============================================================================
# PLAN PHASE
# =============================================================================

def run_with_retry(step_func, bead_id: str, max_retries: int = 3, **kwargs) -> bool:
    """Run step 1 with retry logic - checks if design field was populated."""
    for attempt in range(max_retries):
        step_func(bead_id, **kwargs)
        bead = get_bead(bead_id)
        if bead.get("design"):
            return True
        print(f"  Retry {attempt + 1}/{max_retries}: design not populated")
    return False


def plan_step_1_create(bead_id: str, todo_file: str) -> None:
    """Step 1: Review TODO and create initial integration plan."""
    print("\n[PLAN 1/5] Creating initial integration plan...")

    prompt = f"""TASK: Create integration plan for {todo_file}

REQUIRED ACTIONS:
1. Read {todo_file} to understand the goal
2. Read CLAUDE.md for architectural principles
3. Create a step-by-step integration plan with numbered steps
4. Each step must specify exact files and concrete actions

MANDATORY - Write your plan to this file:
.beads/tmp_plan.md

Write the complete plan to that file. Use the Write tool, not echo/cat.
The plan will be saved to the bead from this file.
"""

    output = run_claude(prompt)
    print(output)
    update_bead_from_temp(bead_id, "design")
    add_comment(bead_id, "[PLAN 1/5] Complete")


def plan_step_2_architecture(bead_id: str) -> None:
    """Step 2: Refine plan for architectural goals."""
    print("\n[PLAN 2/5] Refining for architectural goals...")

    bead = get_bead(bead_id)
    current_plan = bead.get("design", "")

    prompt = f"""TASK: Refine integration plan for architectural quality

CURRENT PLAN:
{current_plan}

REQUIRED ACTIONS:
1. Read CLAUDE.md for architectural principles
2. Refine the plan to ensure it follows:
   - SOLID principles
   - Protocol-first design
   - Dependency injection
   - No god classes

MANDATORY - Write the refined plan to this file:
.beads/tmp_plan.md

Write the complete refined plan to that file. Use the Write tool.
"""

    output = run_claude(prompt)
    print(output)
    update_bead_from_temp(bead_id, "design")
    add_comment(bead_id, "[PLAN 2/5] Complete")


def plan_step_3_outcome(bead_id: str, todo_file: str) -> None:
    """Step 3: Verify plan achieves desired outcome."""
    print("\n[PLAN 3/5] Verifying plan achieves desired outcome...")

    bead = get_bead(bead_id)
    current_plan = bead.get("design", "")

    prompt = f"""TASK: Verify plan achieves the desired outcome

REQUIRED ACTIONS:
1. Read {todo_file} to understand the original goal
2. Compare the current plan against that goal
3. If the plan does NOT achieve the goal, fix it
4. If the plan DOES achieve the goal, save it unchanged

CURRENT PLAN:
{current_plan}

MANDATORY - Write the verified plan to this file:
.beads/tmp_plan.md

Write the complete plan (fixed or unchanged) to that file. Use the Write tool.
"""

    output = run_claude(prompt)
    print(output)
    update_bead_from_temp(bead_id, "design")
    add_comment(bead_id, "[PLAN 3/5] Complete")


def plan_step_4_tests(bead_id: str) -> None:
    """Step 4: Verify new behavior is tested."""
    print("\n[PLAN 4/5] Verifying tests are covered...")

    bead = get_bead(bead_id)
    current_plan = bead.get("design", "")

    prompt = f"""TASK: Ensure plan includes adequate testing

REQUIRED ACTIONS:
1. Read CLAUDE.md for testing principles
2. Review the current plan for test coverage
3. Verify it includes:
   - Tests that prove features work (behavior tests)
   - Edge case coverage
   - No over-mocking
4. If testing is inadequate, add specific testing steps

CURRENT PLAN:
{current_plan}

MANDATORY - Write the plan with tests to this file:
.beads/tmp_plan.md

Write the complete plan (with testing steps added if needed) to that file. Use the Write tool.
"""

    output = run_claude(prompt)
    print(output)
    update_bead_from_temp(bead_id, "design")
    add_comment(bead_id, "[PLAN 4/5] Complete")


def plan_step_5_concrete(bead_id: str) -> None:
    """Step 5: Verify all steps are concrete."""
    print("\n[PLAN 5/5] Verifying all steps are concrete...")

    bead = get_bead(bead_id)
    current_plan = bead.get("design", "")

    prompt = f"""TASK: Make all plan steps concrete and actionable

REQUIRED ACTIONS:
1. Review each step in the current plan
2. Ensure each step specifies:
   - Exactly what file(s) to create/modify
   - Exactly what code to write
   - A single focused action (achievable in one session)
   - No ambiguity
3. Replace vague steps like "implement the feature" with specific actions

CURRENT PLAN:
{current_plan}

MANDATORY - Write the final concrete plan to this file:
.beads/tmp_plan.md

Write the complete final plan to that file. Use the Write tool.
This is the FINAL plan step - make it perfect.
"""

    output = run_claude(prompt)
    print(output)
    update_bead_from_temp(bead_id, "design")
    add_comment(bead_id, "[PLAN 5/5] Complete - PLAN PHASE DONE")


# =============================================================================
# IMPLEMENT PHASE
# =============================================================================

def implement_sanity_check(bead_id: str) -> bool:
    """Sanity check before implementation."""
    print("\n[IMPLEMENT] Sanity check...")

    bead = get_bead(bead_id)
    plan = bead.get("design", "")

    prompt = f"""Review this plan before implementation:

PLAN:
{plan}

Does this make sense to implement? Any red flags?

If OK, respond with EXACTLY: PROCEED
If not OK, respond with EXACTLY: STOP: <reason>
"""

    output = run_claude(prompt, timeout=60)
    print(output)

    if "STOP" in output.upper():
        add_comment(bead_id, f"[IMPLEMENT] Blocked: {output[:200]}")
        return False

    add_comment(bead_id, "[IMPLEMENT] Sanity check passed")
    run_bd(["update", bead_id, "--status", "in_progress"])
    return True


def implement_step(bead_id: str, step_num: int, step_text: str) -> None:
    """Implement a single step from the plan."""
    print(f"\n[IMPLEMENT {step_num}] {step_text[:60]}...")

    bead = get_bead(bead_id)
    plan = bead.get("design", "")

    prompt = f"""TASK: Implement step {step_num} of the plan

STEP TO IMPLEMENT: {step_text}

FULL PLAN CONTEXT:
{plan}

REQUIRED ACTIONS:
1. Read CLAUDE.md for architectural principles
2. Implement the step - write the actual code
3. Verify your implementation aligns with CLAUDE.md principles
4. If it doesn't align, fix it before finishing

Write real code. Make real file changes. This is implementation, not planning.
"""

    output = run_claude(prompt, timeout=600)
    print(output)
    add_comment(bead_id, f"[IMPLEMENT {step_num}] Complete")


def implement_audit(bead_id: str) -> bool:
    """Audit implementation against plan."""
    print("\n[AUDIT] Comparing code to plan...")

    bead = get_bead(bead_id)
    plan = bead.get("design", "")

    prompt = f"""TASK: Audit implementation against the plan

PLAN:
{plan}

REQUIRED ACTIONS:
1. Read CLAUDE.md for architectural principles
2. Review the current code state (read the files that were supposed to be modified)
3. Compare actual code against the plan
4. Verify code follows CLAUDE.md principles

IF changes are needed: Make them, then respond with: CHANGES_MADE: <description>
IF everything is correct: Respond with exactly: AUDIT_PASS

You must respond with one of these two options.
"""

    output = run_claude(prompt, timeout=600)
    print(output)

    if "AUDIT_PASS" in output.upper():
        add_comment(bead_id, "[AUDIT] Passed")
        return True
    else:
        add_comment(bead_id, f"[AUDIT] Changes made: {output[:100]}")
        return False


def parse_plan_steps(plan: str) -> list[str]:
    """Extract numbered steps from plan."""
    lines = plan.split("\n")
    steps = []
    for line in lines:
        stripped = line.strip()
        if stripped and len(stripped) > 2:
            # Check if line starts with a number
            if stripped[0].isdigit() or (stripped.startswith("Step") or stripped.startswith("###")):
                steps.append(stripped)
    return steps if steps else [plan]  # fallback: treat whole plan as one step


# =============================================================================
# TEST PHASE
# =============================================================================

def test_run(bead_id: str) -> bool:
    """Run tests and check if they pass."""
    print("\n[TEST] Running tests...")

    bead = get_bead(bead_id)

    prompt = f"""TASK: Run tests and verify implementation works

GOAL: {bead.get('title', '')}

REQUIRED ACTIONS:
1. Run the test suite: python -m pytest tests/ -v
2. Check for any runtime errors or test failures

IF tests pass: Respond with exactly: TESTS_PASS
IF tests fail: Fix the issues, then respond with: FIXED: <what you fixed>
IF you cannot fix: Respond with: BLOCKED: <reason>

You must respond with one of these three options after running tests.
"""

    output = run_claude(prompt, timeout=600)
    print(output)

    if "TESTS_PASS" in output.upper():
        add_comment(bead_id, "[TEST] All tests passing")
        return True
    elif "BLOCKED" in output.upper():
        add_comment(bead_id, f"[TEST] Blocked: {output[:200]}")
        return False
    else:
        add_comment(bead_id, "[TEST] Fixed issues, will retry")
        return False


def test_final_report(bead_id: str) -> None:
    """Generate final implementation report."""
    print("\n[TEST] Generating final report...")

    bead = get_bead(bead_id)

    prompt = f"""TASK: Generate final implementation report

BEAD: {bead_id}
GOAL: {bead.get('title', '')}
PLAN: {bead.get('design', '')[:2000]}

REQUIRED ACTIONS:
1. Summarize what was implemented
2. List what tests were added/modified
3. Note any deviations from the plan
4. Document any known limitations

MANDATORY - Write the report to this file:
.beads/tmp_notes.md

Write the complete report to that file. Use the Write tool.
"""

    output = run_claude(prompt, timeout=120)
    print(output)
    update_bead_from_temp(bead_id, "notes")
    add_comment(bead_id, "[TEST] Final report generated")


# =============================================================================
# MAIN
# =============================================================================

def run_workflow(todo_file: str) -> None:
    """Run the full workflow."""
    todo_path = Path(todo_file)
    if not todo_path.exists():
        print(f"Error: {todo_file} not found")
        sys.exit(1)

    # Create bead for this task
    title = todo_path.stem.replace("_", " ").replace("PLAN ", "")
    description = f"Implementation of {todo_file}"

    print(f"\n{'='*60}")
    print(f"AUTO: Starting workflow for {todo_file}")
    print(f"{'='*60}")

    bead_id = create_bead(title, description)
    print(f"Created bead: {bead_id}")

    # PLAN PHASE
    print("\n" + "="*60)
    print("PLAN PHASE")
    print("="*60)

    # Step 1: Create initial plan (with retry - this is the critical one)
    if not run_with_retry(plan_step_1_create, bead_id, todo_file=todo_file):
        print("ERROR: Failed to create initial plan after retries")
        return

    # Steps 2-5: Refine plan (no retry needed - design already exists)
    plan_step_2_architecture(bead_id)
    plan_step_3_outcome(bead_id, todo_file)
    plan_step_4_tests(bead_id)
    plan_step_5_concrete(bead_id)

    # IMPLEMENT PHASE
    print("\n" + "="*60)
    print("IMPLEMENT PHASE")
    print("="*60)

    if not implement_sanity_check(bead_id):
        print("Implementation blocked at sanity check")
        return

    bead = get_bead(bead_id)
    steps = parse_plan_steps(bead.get("design", ""))

    for i, step in enumerate(steps, 1):
        implement_step(bead_id, i, step)

    # Audit loop
    for audit_num in range(3):
        if implement_audit(bead_id):
            break

    # TEST PHASE
    print("\n" + "="*60)
    print("TEST PHASE")
    print("="*60)

    for attempt in range(5):
        if test_run(bead_id):
            break

    test_final_report(bead_id)
    close_bead(bead_id)

    print(f"\n{'='*60}")
    print(f"AUTO: Workflow complete for {bead_id}")
    print(f"{'='*60}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    run_workflow(sys.argv[1])
