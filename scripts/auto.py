#!/usr/bin/env python3
"""
Zen Mode: Pure Markdown Workflow.

PHILOSOPHY:
- The File System is the Database.
- Markdown is the API.
- If a file exists, that step is done.

USAGE:
  python scripts/zen_auto.py <TODO_FILE> [flags]

FLAGS:
  --reset        Nuke everything and start over.
  --retry-steps  Keep Plan/Scout, but clear 'Step Complete' logs to force re-implementation.
"""
from __future__ import annotations
import os
import re
import shutil
import subprocess
import sys
import time
import tempfile
from pathlib import Path
from typing import List, Optional

# =============================================================================
# CONFIGURATION
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
WORK_DIR = PROJECT_ROOT / ".agent_work"

# The Artifacts are the State
SCOUT_FILE = WORK_DIR / "scout.md"
PLAN_FILE = WORK_DIR / "plan.md"
LOG_FILE = WORK_DIR / "work_log.md"
NOTES_FILE = WORK_DIR / "final_notes.md"

CLAUDE_EXE = shutil.which("claude")
if not CLAUDE_EXE:
    print("ERROR: claude not found.")
    sys.exit(1)

# Models
MODEL_BRAIN = "opus"  # Planning / Architecture
MODEL_HANDS = "sonnet"  # Coding / Scouting
MODEL_EYES = "haiku"  # Checks / Summaries


# =============================================================================
# CORE UTILS
# =============================================================================

def log(msg: str):
    """Persistent logging to file + stdout."""
    WORK_DIR.mkdir(exist_ok=True)
    ts = time.strftime("%H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"  {msg}")


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_file(path: Path, content: str):
    """Atomic write to prevent corruption."""
    WORK_DIR.mkdir(exist_ok=True)
    # Strip the #EOF sentinel we ask Claude for
    clean_content = re.sub(r"\n?#EOF\s*$", "", content)

    # Write to temp then rename (Atomic)
    with tempfile.NamedTemporaryFile("w", dir=WORK_DIR, delete=False, encoding="utf-8") as tf:
        tf.write(clean_content)
        tmp_path = Path(tf.name)

    tmp_path.replace(path)


def run_claude(prompt: str, model: str, timeout: int = 480) -> Optional[str]:
    """Run Claude in a clean subprocess."""
    cmd = [CLAUDE_EXE, "-p", "--dangerously-skip-permissions", "--model", model]
    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=PROJECT_ROOT, text=True, encoding="utf-8", errors="replace"
        )
        stdout, stderr = proc.communicate(input=prompt, timeout=timeout)
        if proc.returncode != 0:
            log(f"[ERROR] Claude ({model}): {stderr[:200]}")
            return None
        return stdout
    except Exception as e:
        log(f"[ERROR] Subprocess: {e}")
        return None


# =============================================================================
# PHASES
# =============================================================================

def phase_1_scout(todo_file: str):
    if SCOUT_FILE.exists():
        log("[SCOUT] Found existing report. Skipping.")
        return

    log(f"\n[SCOUT] Investigating {todo_file}...")

    prompt = f"""TASK: Scout the codebase for {todo_file}
CONTEXT: Personal Project. Legacy code exists.
GOAL: Map the files. Do NOT plan yet.

ACTIONS:
1. `ls -R`, `find`, `grep` to find relevant files.
2. Read code to understand dependencies.
3. Identify what to DELETE (Clean Code policy).

OUTPUT: Write report to {SCOUT_FILE}
End with: #EOF
"""
    output = run_claude(prompt, model=MODEL_HANDS)
    if output and SCOUT_FILE.exists():
        log("[SCOUT] Complete.")
    else:
        log("[SCOUT] Failed to generate report.")
        sys.exit(1)


def phase_2_plan(todo_file: str):
    if PLAN_FILE.exists():
        log("[PLAN] Found existing plan. Skipping.")
        return

    log("\n[PLAN] Drafting Architecture...")
    scout_data = read_file(SCOUT_FILE)

    prompt = f"""TASK: Create execution plan for {todo_file}
CONTEXT: Personal Project. "Clean Code" > "Backward Compatibility".

SCOUT REPORT:
{scout_data}

REQUIRED:
1. Create a numbered list of ATOMIC steps.
2. "DELETE file X" (No deprecation).
3. "UPDATE callers" (No adapters).
4. Include a final Verification step.

OUTPUT: Write to {PLAN_FILE}
End with: #EOF
"""
    output = run_claude(prompt, model=MODEL_BRAIN)
    if output and PLAN_FILE.exists():
        log("[PLAN] Complete.")
    else:
        log("[PLAN] Failed to generate plan.")
        sys.exit(1)


def phase_3_implement():
    plan_content = read_file(PLAN_FILE)

    # Robust Regex: Handle missing trailing newline by appending \n
    # Looks for "Step N:" or "1." followed by content until next step
    steps = re.findall(
        r"(?:^|\n)(?:Step\s+\d+|[0-9]+\.)[:\s]+(.*?)(?=\n(?:Step|[0-9]+\.)|$)",
        plan_content + "\n",
        re.DOTALL | re.IGNORECASE
    )

    if not steps:
        # Fallback for bullets
        steps = re.findall(r"(?:^|\n)[-*]\s+(.*?)(?=\n[-*]|$)", plan_content)

    log(f"\n[IMPLEMENT] Found {len(steps)} steps.")

    for i, step_text in enumerate(steps, 1):
        step_text = step_text.strip()

        # Simple Resume Logic: Check log file for completion
        if f"[COMPLETE] Step {i}" in read_file(LOG_FILE):
            log(f"[SKIP] Step {i} (Already done)")
            continue

        log(f"\n[STEP {i}] {step_text[:60]}...")

        prompt = f"""TASK: Implement Step {i}
STEP: {step_text}
FULL PLAN: {plan_content}

RULES:
1. DELETE old code (No shims).
2. Update callers immediately.
3. No broken imports.

CRITICAL: WRITE CODE or DELETE FILES.
End with: STEP_COMPLETE or STEP_BLOCKED
"""
        output = run_claude(prompt, model=MODEL_HANDS, timeout=600)

        if output and "STEP_COMPLETE" in output:
            log(f"[COMPLETE] Step {i}")
        else:
            log(f"[FAILED] Step {i}")
            sys.exit(1)


def phase_4_verify():
    log("\n[VERIFY] Running Tests...")

    prompt = f"""Run tests (pytest) and verify app loads.
If tests fail due to deleted code, UPDATE THE TEST.
End with: TESTS_PASS or TESTS_FAIL
"""
    output = run_claude(prompt, model=MODEL_HANDS, timeout=600)

    if output and "TESTS_PASS" in output:
        log("[VERIFY] Passed.")
    else:
        log("[VERIFY] Failed.")
        sys.exit(1)

    # Generate Note
    prompt = f"Summarize changes. Write to {NOTES_FILE}. End with #EOF"
    run_claude(prompt, model=MODEL_EYES, timeout=120)


# =============================================================================
# MAIN
# =============================================================================

def handle_flags():
    """Handle CLI flags for reset and retry."""
    if "--reset" in sys.argv:
        if WORK_DIR.exists(): shutil.rmtree(WORK_DIR)
        print("Reset complete. Starting fresh.")

    if "--retry-steps" in sys.argv or "--resume" in sys.argv:
        # "Resume" usually implies continuing, which is default.
        # But per user request, this flag clears completion markers to FORCE retry.
        if LOG_FILE.exists():
            print("Clearing completion markers to force step retry...")
            lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
            # Filter out [COMPLETE] lines
            clean_log = "\n".join(l for l in lines if "[COMPLETE] Step" not in l)
            LOG_FILE.write_text(clean_log + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python zen_auto.py <TODO_FILE> [--reset] [--retry-steps]")
        sys.exit(1)

    todo = sys.argv[1]
    handle_flags()

    try:
        phase_1_scout(todo)
        phase_2_plan(todo)
        phase_3_implement()
        phase_4_verify()
        print("\nSUCCESS.")
        sys.exit(0)

    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(130)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)