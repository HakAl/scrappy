#!/usr/bin/env python3
"""
Context-Aware LLM Agent Team Demo

Demonstrates how the orchestrator automatically learns about your codebase
and uses that knowledge to provide better responses.
"""

import sys
sys.path.insert(0, 'src')

from orchestrator import AgentOrchestrator


def main():
    print("=" * 60)
    print("Context-Aware LLM Agent Team Demo")
    print("=" * 60)
    print()

    # Initialize orchestrator with auto-explore
    print("1. Initializing with auto-explore...")
    print("-" * 60)
    orch = AgentOrchestrator(
        auto_explore=True,  # Automatically scan the codebase
        context_aware=True   # Enable context injection
    )
    print()

    # Check context status
    print("2. Context Status:")
    print("-" * 60)
    status = orch.get_context_status()
    print(f"  Project: {status['project_path']}")
    print(f"  Explored: {status['is_explored']}")
    print(f"  Has Summary: {status['has_summary']}")
    print(f"  Total Files: {status['total_files']}")
    print(f"  Cache File: {status['cache_file']}")
    print()

    if status['has_summary']:
        print("3. Generated Project Summary:")
        print("-" * 60)
        print(orch.context.summary)
        print()

    # Demo: Query without context
    print("4. Query WITHOUT context:")
    print("-" * 60)
    query = "What's the best way to add a new provider to this system?"

    response_no_context = orch.delegate(
        orch.brain,
        query,
        use_context=False,  # Disable context
        max_tokens=300
    )

    print(f"Query: {query}")
    print(f"\nResponse (no context):")
    print(response_no_context.content)
    print(f"\n[{response_no_context.tokens_used} tokens, {response_no_context.latency_ms:.0f}ms]")
    print()

    # Demo: Query with context
    print("5. Query WITH context:")
    print("-" * 60)

    response_with_context = orch.delegate(
        orch.brain,
        query,
        use_context=True,  # Enable context
        max_tokens=300
    )

    print(f"Query: {query}")
    print(f"\nResponse (with context):")
    print(response_with_context.content)
    print(f"\n[{response_with_context.tokens_used} tokens, {response_with_context.latency_ms:.0f}ms]")
    print()

    # Demo: Context-aware planning
    print("6. Context-Aware Task Planning:")
    print("-" * 60)
    task = "Add rate limit monitoring dashboard"

    # First augment the task with context
    augmented_task = orch.context.augment_prompt(task)

    print(f"Original task: {task}")
    print(f"\nAugmented prompt preview:")
    print(augmented_task[:500] + "..." if len(augmented_task) > 500 else augmented_task)
    print()

    # Plan with context
    steps = orch.plan(task)
    print("Generated Plan:")
    for i, step in enumerate(steps, 1):
        if isinstance(step, dict):
            print(f"  {i}. {step.get('step', 'Step')}")
            print(f"     {step.get('description', '')}")
            print(f"     [Provider: {step.get('provider_type', 'general')}]")
        else:
            print(f"  {i}. {step}")
    print()

    # Demo: Relevant context extraction
    print("7. Smart Context Selection:")
    print("-" * 60)

    queries = [
        "How do I add configuration options?",
        "What testing framework is used?",
        "Explain the provider architecture"
    ]

    for q in queries:
        relevant = orch.context.get_relevant_context(q)
        print(f"Query: {q}")
        print(f"Relevant context: {relevant[:200]}..." if len(relevant) > 200 else f"Relevant context: {relevant}")
        print()

    # Usage report
    print("8. Usage Report:")
    print("-" * 60)
    report = orch.get_usage_report()
    print(f"Total Tasks: {report['total_tasks']}")
    print(f"Session Duration: {report['session_duration']}")

    if report.get('by_provider'):
        for provider, stats in report['by_provider'].items():
            print(f"\n  {provider}:")
            print(f"    Requests: {stats['count']}")
            print(f"    Total Tokens: {stats['total_tokens']:,}")
            print(f"    Avg Latency: {stats['avg_latency_ms']:.0f}ms")

    print()
    print("=" * 60)
    print("Demo Complete!")
    print("=" * 60)
    print()
    print("Key Takeaways:")
    print("- Context is automatically cached to .llm_team_context.json")
    print("- Subsequent runs load cached context instantly")
    print("- Prompts are augmented with project knowledge")
    print("- Better responses without manual context explanation")
    print()
    print("Try running the CLI with:")
    print("  python llm_team.py --auto-explore")
    print("  /context")
    print("  /context toggle")


if __name__ == "__main__":
    main()
