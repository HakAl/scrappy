#!/usr/bin/env python3
"""
Task Router Integration Example

Shows how to integrate the TaskRouter with the existing orchestrator
for production use.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main():
    """Example of full integration with orchestrator."""
    from task_router import TaskRouter
    from orchestrator import AgentOrchestrator

    print("Initializing Task-Aware Execution System...")

    # 1. Initialize the orchestrator (your existing setup)
    orchestrator = AgentOrchestrator(
        orchestrator_provider="cerebras",  # Fast provider as brain
        auto_explore=False,
        context_aware=True
    )

    # 2. Create the task router with orchestrator
    router = TaskRouter(
        orchestrator=orchestrator,
        project_root=Path.cwd(),
        auto_confirm_direct=False,  # Require confirmation for shell commands
        verbose=True  # Show routing decisions
    )

    # 3. Add custom hooks (optional)
    def log_task(task):
        """Log all tasks before execution."""
        print(f"[LOG] Task: {task.original_input[:50]}...")
        return task

    def track_result(result):
        """Track results after execution."""
        if result.success:
            print(f"[TRACK] Success in {result.execution_time:.2f}s")
        return result

    router.add_pre_hook(log_task)
    router.add_post_hook(track_result)

    # 4. Example: Interactive loop
    print("\nTask-Aware Execution Ready!")
    print("Commands are automatically routed to optimal execution path.\n")

    while True:
        try:
            user_input = input("\n🎯 Enter task (or 'quit'): ").strip()

            if user_input.lower() in ['quit', 'exit', 'q']:
                break

            if not user_input:
                continue

            # Route automatically handles classification and execution
            result = router.route(user_input)

            # The router handles all output, but you can access results
            if not result.success and result.error:
                print(f"\nNote: {result.error}")

        except KeyboardInterrupt:
            print("\n\nExiting...")
            break

    # 5. Show final metrics
    metrics = router.get_metrics()
    print(f"\n📊 Session Summary:")
    print(f"  Tasks executed: {metrics.total_tasks}")
    print(f"  Success rate: {metrics.success_rate:.1%}")
    print(f"  Tokens used: {metrics.total_tokens_used}")


if __name__ == "__main__":
    main()
