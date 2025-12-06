"""
Multi-phase autonomous workflow orchestrator.

Each step runs in a fresh agent context. State persists only in beads.
No agent survives past its single task.

Usage:
    python workflows/orchestrator.py <bead-id>
    python workflows/orchestrator.py --list  # show ready beads
"""

import asyncio
import subprocess
import json
import sys
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from enum import Enum

# Agent SDK imports
from claude_code_sdk import query, ClaudeCodeOptions, AssistantMessage, TextBlock


class Phase(Enum):
    PLAN = "plan"
    IMPLEMENT = "implement"
    TEST = "test"


@dataclass
class BeadState:
    """State loaded from bead - the ONLY thing passed between agents."""
    id: str
    title: str
    description: str
    status: str
    plan: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Bead operations (persist state, survives context clears)
# ---------------------------------------------------------------------------

def get_bd_exe() -> str:
    """Get path to bd.exe."""
    return str(get_project_root() / ".beads" / "bd.exe")


def load_bead(bead_id: str) -> BeadState:
    """Load bead state from tracker."""
    result = subprocess.run(
        [get_bd_exe(), "show", bead_id, "--json"],
        capture_output=True,
        text=True,
        cwd=get_project_root()
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to load bead {bead_id}: {result.stderr}")

    data = json.loads(result.stdout)
    return BeadState(
        id=data["id"],
        title=data["title"],
        description=data.get("description", ""),
        status=data["status"],
        plan=data.get("design"),  # plan stored in design field
        notes=data.get("notes", ""),
    )


def save_to_bead(bead_id: str, plan: Optional[str] = None, notes: Optional[str] = None) -> None:
    """Save state to bead. This is the persistence layer."""
    args = [get_bd_exe(), "update", bead_id]

    if plan is not None:
        args.extend(["--design", plan])
    if notes is not None:
        args.extend(["--notes", notes])

    result = subprocess.run(args, capture_output=True, text=True, cwd=get_project_root())
    if result.returncode != 0:
        raise RuntimeError(f"Failed to save to bead {bead_id}: {result.stderr}")


def add_comment(bead_id: str, comment: str) -> None:
    """Add a comment to bead for audit trail."""
    result = subprocess.run(
        [get_bd_exe(), "comment", bead_id, comment],
        capture_output=True,
        text=True,
        cwd=get_project_root()
    )
    if result.returncode != 0:
        print(f"Warning: Failed to add comment: {result.stderr}")


def update_status(bead_id: str, status: str) -> None:
    """Update bead status."""
    result = subprocess.run(
        [get_bd_exe(), "update", bead_id, "--status", status],
        capture_output=True,
        text=True,
        cwd=get_project_root()
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to update status: {result.stderr}")


def close_bead(bead_id: str) -> None:
    """Close bead when complete."""
    result = subprocess.run(
        [get_bd_exe(), "close", bead_id],
        capture_output=True,
        text=True,
        cwd=get_project_root()
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to close bead: {result.stderr}")


def get_project_root() -> Path:
    """Get project root directory."""
    return Path(__file__).parent.parent


def get_claude_md() -> str:
    """Load CLAUDE.md for architectural principles."""
    claude_md = get_project_root() / "CLAUDE.md"
    if claude_md.exists():
        return claude_md.read_text()
    return ""


# ---------------------------------------------------------------------------
# Agent execution (fresh context each time)
# ---------------------------------------------------------------------------

async def run_agent(
    task: str,
    system_prompt: str,
    allowed_tools: list[str],
) -> str:
    """
    Run a single agent task with fresh context.
    Agent is created, executes, returns result, and dies.
    Uses query() for stateless one-shot execution.
    """
    options = ClaudeCodeOptions(
        system_prompt=system_prompt,
        allowed_tools=allowed_tools,
        cwd=str(get_project_root()),
        permission_mode="bypassPermissions",  # autonomous mode
    )

    result_text = ""

    async for message in query(prompt=task, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    result_text += block.text
                    print(block.text, end="", flush=True)

    print()  # newline after agent output
    return result_text


# ---------------------------------------------------------------------------
# PLAN Phase (5 fresh agents)
# ---------------------------------------------------------------------------

async def plan_phase(bead_id: str) -> None:
    """
    PLAN phase: 5 sequential agents, each with fresh context.

    1. Review bead -> create initial plan
    2. Refine for architectural goals
    3. Verify achieves desired outcome
    4. Verify tests are covered
    5. Verify steps are concrete
    """
    claude_md = get_claude_md()

    # Agent 1: Create initial plan
    print("\n[PLAN 1/5] Creating initial integration plan...")
    bead = load_bead(bead_id)

    result = await run_agent(
        task=f"""You are creating an integration plan for this task:

BEAD ID: {bead.id}
TITLE: {bead.title}
DESCRIPTION: {bead.description}

Review the codebase and docs to understand the current state.
Then create a step-by-step integration plan.

Output ONLY the plan, formatted as markdown with numbered steps.
Each step should be a concrete action.""",
        system_prompt="You are an architect. Create clear, actionable plans. No fluff.",
        allowed_tools=["Read", "Glob", "Grep"],
    )

    save_to_bead(bead_id, plan=result)
    add_comment(bead_id, "[PLAN 1/5] Initial plan created")
    # Agent dies here. Context cleared.

    # Agent 2: Refine for architecture
    print("\n[PLAN 2/5] Refining for architectural goals...")
    bead = load_bead(bead_id)  # fresh load

    result = await run_agent(
        task=f"""Review and refine this integration plan for architectural quality:

CURRENT PLAN:
{bead.plan}

ARCHITECTURAL PRINCIPLES (from CLAUDE.md):
{claude_md}

Ensure the plan follows:
- SOLID principles
- Protocol-first design
- Dependency injection
- No god classes

Output the REFINED plan. Keep the same format but improve architectural quality.""",
        system_prompt="You are a software architect. Enforce SOLID principles ruthlessly.",
        allowed_tools=["Read", "Glob", "Grep"],
    )

    save_to_bead(bead_id, plan=result)
    add_comment(bead_id, "[PLAN 2/5] Refined for architecture")

    # Agent 3: Verify achieves outcome
    print("\n[PLAN 3/5] Verifying plan achieves desired outcome...")
    bead = load_bead(bead_id)

    result = await run_agent(
        task=f"""Review this plan and verify it achieves the desired outcome:

ORIGINAL GOAL:
{bead.title}
{bead.description}

CURRENT PLAN:
{bead.plan}

Does this plan actually achieve the goal? If not, fix it.
If yes, confirm and output the plan unchanged.

Output the VERIFIED plan (or corrected plan if fixes needed).""",
        system_prompt="You are a critical reviewer. Ensure plans actually solve the stated problem.",
        allowed_tools=["Read", "Glob", "Grep"],
    )

    save_to_bead(bead_id, plan=result)
    add_comment(bead_id, "[PLAN 3/5] Verified achieves outcome")

    # Agent 4: Verify tests covered
    print("\n[PLAN 4/5] Verifying new behavior is tested...")
    bead = load_bead(bead_id)

    result = await run_agent(
        task=f"""Review this plan and ensure new behavior will be tested:

CURRENT PLAN:
{bead.plan}

TESTING PRINCIPLES (from CLAUDE.md):
- Tests must prove features work
- Tests must fail if feature breaks
- No structure-only tests
- No over-mocking
- Edge cases must be covered

Does the plan include adequate testing for new behavior?
If not, add testing steps.

Output the plan with testing steps included/verified.""",
        system_prompt="You are a test engineer. No untested code ships.",
        allowed_tools=["Read", "Glob", "Grep"],
    )

    save_to_bead(bead_id, plan=result)
    add_comment(bead_id, "[PLAN 4/5] Verified tests covered")

    # Agent 5: Verify steps concrete
    print("\n[PLAN 5/5] Verifying all steps are concrete...")
    bead = load_bead(bead_id)

    result = await run_agent(
        task=f"""Review this plan and ensure ALL steps are concrete and actionable:

CURRENT PLAN:
{bead.plan}

Each step must:
- Specify exactly what file(s) to create/modify
- Specify exactly what code to write
- Be achievable in a single focused session
- Have no ambiguity

Vague steps like "implement the feature" are NOT acceptable.
Replace any vague steps with concrete actions.

Output the FINAL concrete plan.""",
        system_prompt="You are a project manager. Vague plans fail. Concrete plans succeed.",
        allowed_tools=["Read", "Glob", "Grep"],
    )

    save_to_bead(bead_id, plan=result)
    add_comment(bead_id, "[PLAN 5/5] All steps concrete - PLAN PHASE COMPLETE")

    print("\n[PLAN COMPLETE] Plan saved to bead.")


# ---------------------------------------------------------------------------
# IMPLEMENT Phase (N agents for N steps + audit loop)
# ---------------------------------------------------------------------------

async def implement_phase(bead_id: str) -> None:
    """
    IMPLEMENT phase: One agent per plan step, plus audit loop.
    """
    claude_md = get_claude_md()

    # Agent: Sanity check before starting
    print("\n[IMPLEMENT] Sanity check...")
    bead = load_bead(bead_id)

    if not bead.plan:
        raise RuntimeError("No plan found in bead. Run plan phase first.")

    result = await run_agent(
        task=f"""Review this plan before implementation:

GOAL: {bead.title}
PLAN:
{bead.plan}

Does this make sense to implement? Any red flags?
If OK, respond with "PROCEED" and list the steps.
If not OK, respond with "STOP" and explain why.""",
        system_prompt="You are a senior engineer doing a final review before coding.",
        allowed_tools=["Read", "Glob", "Grep"],
    )

    if "STOP" in result.upper():
        add_comment(bead_id, f"[IMPLEMENT] Blocked at sanity check: {result[:200]}")
        raise RuntimeError(f"Sanity check failed: {result}")

    add_comment(bead_id, "[IMPLEMENT] Sanity check passed, beginning implementation")
    update_status(bead_id, "in_progress")

    # Parse plan into steps (simple heuristic: numbered lines)
    plan_lines = bead.plan.split("\n")
    steps = [line for line in plan_lines if line.strip() and line.strip()[0].isdigit()]

    if not steps:
        # Fallback: treat whole plan as single step
        steps = [bead.plan]

    # Agent per step
    for i, step in enumerate(steps, 1):
        print(f"\n[IMPLEMENT {i}/{len(steps)}] {step[:60]}...")
        bead = load_bead(bead_id)  # fresh load each time

        result = await run_agent(
            task=f"""Implement this step:

STEP: {step}

FULL PLAN CONTEXT:
{bead.plan}

ARCHITECTURAL PRINCIPLES:
{claude_md}

Implement the step. Write the actual code.
After implementation, verify it aligns with CLAUDE.md principles.
If you had to deviate, explain why.""",
            system_prompt="You are a senior developer. Write clean, tested, SOLID code.",
            allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
        )

        add_comment(bead_id, f"[IMPLEMENT {i}/{len(steps)}] Completed: {step[:50]}")
        # Agent dies. Context cleared.

    # Audit loop
    audit_count = 0
    max_audits = 3

    while audit_count < max_audits:
        audit_count += 1
        print(f"\n[AUDIT {audit_count}/{max_audits}] Comparing code to plan...")
        bead = load_bead(bead_id)

        result = await run_agent(
            task=f"""Audit the implementation against the plan:

PLAN:
{bead.plan}

PRINCIPLES:
{claude_md}

Review the current code state.
Does it match the plan? Does it follow CLAUDE.md principles?

If changes needed, make them and respond "CHANGES_MADE: <description>"
If everything is correct, respond "AUDIT_PASS".""",
            system_prompt="You are a code auditor. Find discrepancies between plan and implementation.",
            allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
        )

        if "AUDIT_PASS" in result.upper():
            add_comment(bead_id, f"[AUDIT {audit_count}] Passed - implementation complete")
            break
        else:
            add_comment(bead_id, f"[AUDIT {audit_count}] Changes made: {result[:100]}")

    print("\n[IMPLEMENT COMPLETE]")


# ---------------------------------------------------------------------------
# TEST Phase (iterative until success)
# ---------------------------------------------------------------------------

async def test_phase(bead_id: str) -> None:
    """
    TEST phase: Run tests, fix if broken, repeat until passing.
    """
    max_attempts = 5
    attempt = 0

    while attempt < max_attempts:
        attempt += 1
        print(f"\n[TEST {attempt}/{max_attempts}] Running tests...")
        bead = load_bead(bead_id)

        result = await run_agent(
            task=f"""Run tests and verify the implementation works:

GOAL: {bead.title}
PLAN: {bead.plan}

1. Run the test suite: python -m pytest tests/ -v
2. Verify the app loads (if applicable)
3. Check for any runtime errors

If tests pass, respond "TESTS_PASS"
If tests fail, fix the issues and respond "FIXED: <what you fixed>"
If you cannot fix, respond "BLOCKED: <reason>" """,
            system_prompt="You are a QA engineer. Tests must pass. App must work.",
            allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
        )

        if "TESTS_PASS" in result.upper():
            add_comment(bead_id, f"[TEST {attempt}] All tests passing")
            break
        elif "BLOCKED" in result.upper():
            add_comment(bead_id, f"[TEST {attempt}] Blocked: {result[:200]}")
            raise RuntimeError(f"Test phase blocked: {result}")
        else:
            add_comment(bead_id, f"[TEST {attempt}] Fixed issues, retrying...")

    # Final report
    print("\n[TEST] Generating final report...")
    bead = load_bead(bead_id)

    result = await run_agent(
        task=f"""Generate a final implementation report:

BEAD: {bead.id}
GOAL: {bead.title}
PLAN: {bead.plan}

Summarize:
1. What was implemented
2. What tests were added/modified
3. Any deviations from the plan
4. Any known limitations

Output a concise markdown report.""",
        system_prompt="You are a technical writer. Be concise and accurate.",
        allowed_tools=["Read", "Glob", "Grep"],
    )

    # Save report to notes
    save_to_bead(bead_id, notes=result)
    add_comment(bead_id, "[TEST] Final report generated - closing bead")
    close_bead(bead_id)

    print("\n[TEST COMPLETE] Bead closed.")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def run_workflow(bead_id: str) -> None:
    """Run full workflow: PLAN -> IMPLEMENT -> TEST"""
    print(f"\n{'='*60}")
    print(f"ORCHESTRATOR: Starting workflow for {bead_id}")
    print(f"{'='*60}")

    try:
        await plan_phase(bead_id)
        await implement_phase(bead_id)
        await test_phase(bead_id)

        print(f"\n{'='*60}")
        print(f"ORCHESTRATOR: Workflow complete for {bead_id}")
        print(f"{'='*60}")

    except Exception as e:
        print(f"\n[ERROR] Workflow failed: {e}")
        add_comment(bead_id, f"[ERROR] Workflow failed: {str(e)[:200]}")
        raise


def list_ready_beads() -> None:
    """List beads ready to work on."""
    result = subprocess.run(
        [get_bd_exe(), "ready", "--json"],
        capture_output=True,
        text=True,
        cwd=get_project_root()
    )
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return

    beads = json.loads(result.stdout) if result.stdout.strip() else []

    if not beads:
        print("No beads ready to work on.")
        return

    print("\nReady beads:")
    for bead in beads:
        print(f"  {bead['id']}: {bead['title']} (P{bead.get('priority', '?')})")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--list":
        list_ready_beads()
        sys.exit(0)

    bead_id = sys.argv[1]
    asyncio.run(run_workflow(bead_id))


if __name__ == "__main__":
    main()
