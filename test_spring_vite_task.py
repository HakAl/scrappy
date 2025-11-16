#!/usr/bin/env python3
"""
Test script: Human-in-the-loop simulation for Spring + Vite task.
Using auto_confirm=True as requested by user.
"""
import sys
import time
from pathlib import Path

# Use same import pattern as llm_team.py entry point
from src.orchestrator import AgentOrchestrator
from src.agent import CodeAgent, create_git_checkpoint

def main():
    print("=" * 70)
    print("LLM TEAM UX TEST: Spring REST API + Vite React Frontend")
    print("=" * 70)

    # Setup timing
    start_time = time.time()

    # Step 1: Initialize orchestrator
    print("\n[STEP 1] Initializing orchestrator...")
    init_start = time.time()
    try:
        orch = AgentOrchestrator(auto_explore=True)
        init_time = time.time() - init_start
        print(f"  Initialization took: {init_time:.2f}s")
        print(f"  Brain: {orch.brain}")
        # Get providers from registry safely
        if hasattr(orch.registry, '_providers'):
            print(f"  Providers: {list(orch.registry._providers.keys())}")
        else:
            print(f"  Providers: (unable to list)")
    except Exception as e:
        print(f"  ERROR initializing orchestrator: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 2: Create agent
    print("\n[STEP 2] Creating code agent...")
    agent_start = time.time()
    try:
        agent = CodeAgent(orch)
        agent_time = time.time() - agent_start
        print(f"  Agent creation took: {agent_time:.2f}s")
        print(f"  Planner: {agent.planner}")
        print(f"  Executor: {agent.executor}")
        print(f"  Tools available: {len(agent.tools)}")
    except Exception as e:
        print(f"  ERROR creating agent: {e}")
        return

    # Step 3: Create git checkpoint
    print("\n[STEP 3] Creating git checkpoint...")
    checkpoint = create_git_checkpoint(".")
    if checkpoint:
        print(f"  Checkpoint: {checkpoint[:8]}...")
    else:
        print("  WARNING: No checkpoint created (not a git repo?)")

    # Step 4: Define the task
    task = """
    Create a new directory called 'website/' with:

    1. A Spring Boot REST API (Java) with:
       - User registration endpoint (POST /api/auth/register)
       - Login endpoint (POST /api/auth/login)
       - Password reset request endpoint (POST /api/auth/password-reset)
       - Use JWT for authentication
       - Include basic User entity and in-memory H2 database

    2. A Vite + React frontend with:
       - Landing page (/)
       - Login page (/login)
       - Register page (/register)
       - Password reset page (/reset-password)
       - Basic routing with React Router
       - Axios for API calls

    Start by creating the directory structure, then implement the backend, then the frontend.
    Keep implementations simple but functional.
    """

    print("\n[STEP 4] Task definition:")
    print("-" * 70)
    print(task.strip())
    print("-" * 70)

    # Step 5: Run the agent
    print("\n[STEP 5] Running agent (auto_confirm=True)...")
    print("  This simulates accepting all agent actions.")
    print("  Max iterations: 50")
    print("\n" + "=" * 70)
    print("AGENT EXECUTION LOG:")
    print("=" * 70)

    run_start = time.time()
    try:
        result = agent.run(
            task=task,
            max_iterations=50,  # High limit for complex task
            auto_confirm=True   # User said accept everything
        )
        run_time = time.time() - run_start

        print("\n" + "=" * 70)
        print("AGENT RESULTS:")
        print("=" * 70)
        print(f"  Success: {result.get('success', False)}")
        print(f"  Iterations: {result.get('iterations', 0)}")
        print(f"  Run time: {run_time:.2f}s")
        print(f"\nResult message:")
        print("-" * 70)
        print(result.get('result', 'No result message'))
        print("-" * 70)

        # Show audit log summary
        print(f"\nAudit log: {len(agent.audit_log)} actions")
        for i, entry in enumerate(agent.audit_log, 1):
            action = entry.get('action', 'unknown')
            params = entry.get('parameters', {})
            status = "APPROVED" if entry.get('approved', False) else "DENIED"
            print(f"  {i}. [{status}] {action}")
            if action == 'write_file':
                print(f"      File: {params.get('path', 'unknown')}")
            elif action == 'run_command':
                cmd = params.get('command', 'unknown')[:50]
                print(f"      Command: {cmd}...")

        # Save audit log
        audit_file = ".spring_vite_audit.json"
        agent.save_audit_log(audit_file)
        print(f"\nFull audit log saved to: {audit_file}")

    except Exception as e:
        run_time = time.time() - run_start
        print(f"\n  ERROR during agent run: {e}")
        print(f"  Run time before error: {run_time:.2f}s")
        import traceback
        traceback.print_exc()

    # Summary
    total_time = time.time() - start_time
    print("\n" + "=" * 70)
    print("UX TEST SUMMARY:")
    print("=" * 70)
    print(f"Total time: {total_time:.2f}s ({total_time/60:.1f} minutes)")
    print(f"Checkpoint: {checkpoint[:8] if checkpoint else 'None'}")
    print(f"To rollback: git reset --hard {checkpoint}" if checkpoint else "")

    # Check what was created
    print("\n[STEP 6] Checking created artifacts...")
    website_dir = Path("website")
    if website_dir.exists():
        print(f"  website/ directory EXISTS")
        # List contents
        for item in website_dir.iterdir():
            if item.is_dir():
                print(f"    {item.name}/")
            else:
                print(f"    {item.name}")
    else:
        print(f"  website/ directory NOT FOUND")

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
