#!/usr/bin/env python3
"""
Test script to demonstrate async/parallel execution benefits.

This script compares sequential vs parallel LLM API calls to show performance improvements.
"""

import asyncio
import time
from src.orchestrator import AgentOrchestrator


def test_sequential_batch(orch, tasks, provider='cerebras'):
    """Test sequential batch processing (old way)."""
    print(f"\n{'='*60}")
    print(f"SEQUENTIAL BATCH PROCESSING ({len(tasks)} tasks)")
    print(f"{'='*60}")

    start = time.time()
    results = orch.batch_delegate(tasks, provider_name=provider)
    elapsed = time.time() - start

    print(f"Total time: {elapsed:.2f} seconds")
    print(f"Average per task: {elapsed/len(tasks):.2f} seconds")

    for i, result in enumerate(results):
        print(f"  Task {i+1}: {result.latency_ms:.0f}ms, {result.tokens_used} tokens")

    return elapsed, results


async def test_parallel_batch(orch, tasks, provider='cerebras', max_concurrent=5):
    """Test parallel batch processing (new async way)."""
    print(f"\n{'='*60}")
    print(f"PARALLEL BATCH PROCESSING ({len(tasks)} tasks, max_concurrent={max_concurrent})")
    print(f"{'='*60}")

    start = time.time()
    results = await orch.batch_delegate_async(tasks, provider_name=provider, max_concurrent=max_concurrent)
    elapsed = time.time() - start

    print(f"Total time: {elapsed:.2f} seconds")
    print(f"Average per task: {elapsed/len(tasks):.2f} seconds")

    for i, result in enumerate(results):
        print(f"  Task {i+1}: {result.latency_ms:.0f}ms, {result.tokens_used} tokens")

    return elapsed, results


async def test_multi_provider(orch, prompt):
    """Test querying multiple providers in parallel."""
    print(f"\n{'='*60}")
    print("MULTI-PROVIDER PARALLEL QUERY")
    print(f"{'='*60}")

    start = time.time()
    results = await orch.multi_provider_query_async(
        prompt,
        providers=['cerebras', 'groq'],  # Query both providers
        max_tokens=100,
        use_context=False,
        use_cache=False
    )
    elapsed = time.time() - start

    print(f"Total time: {elapsed:.2f} seconds")
    print(f"Providers queried: {list(results.keys())}")

    for provider, response in results.items():
        print(f"\n  {provider}:")
        print(f"    Latency: {response.latency_ms:.0f}ms")
        print(f"    Tokens: {response.tokens_used}")
        print(f"    Response: {response.content[:100]}...")

    return elapsed, results


def main():
    print("Initializing orchestrator...")
    orch = AgentOrchestrator(
        auto_register=True,
        context_aware=False,  # Disable context for cleaner test
        enable_cache=False    # Disable cache for accurate timing
    )

    # Test tasks - simple prompts
    test_tasks = [
        {'prompt': 'What is 2+2? Reply with just the number.'},
        {'prompt': 'What is the capital of France? One word answer.'},
        {'prompt': 'What color is the sky? One word answer.'},
        {'prompt': 'How many days in a week? Just the number.'},
        {'prompt': 'What is H2O commonly called? One word answer.'},
    ]

    available = orch.registry.list_available()
    print(f"\nAvailable providers: {available}")

    if not available:
        print("No providers available! Check your API keys.")
        return

    # Pick a provider for testing
    test_provider = 'cerebras' if 'cerebras' in available else available[0]
    print(f"Using provider: {test_provider}")

    # Test 1: Sequential vs Parallel Batch
    print("\n" + "="*60)
    print(" PERFORMANCE COMPARISON TEST")
    print("="*60)

    # Sequential test
    seq_time, seq_results = test_sequential_batch(orch, test_tasks, test_provider)

    # Wait a moment to let rate limits reset
    print("\nWaiting 2 seconds for rate limits to reset...")
    time.sleep(2)

    # Parallel test - use max_concurrent=2 to be conservative with rate limits
    async def run_parallel_tests():
        par_time, par_results = await test_parallel_batch(orch, test_tasks, test_provider, max_concurrent=2)
        return par_time, par_results

    par_time, par_results = asyncio.run(run_parallel_tests())

    # Calculate improvement
    improvement = ((seq_time - par_time) / seq_time) * 100
    speedup = seq_time / par_time

    print(f"\n{'='*60}")
    print(" RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Sequential: {seq_time:.2f} seconds")
    print(f"Parallel:   {par_time:.2f} seconds")
    print(f"Improvement: {improvement:.1f}% faster")
    print(f"Speedup: {speedup:.2f}x")

    # Test 2: Multi-provider query (if multiple providers available)
    if len(available) >= 2:
        print("\n" + "="*60)
        print(" MULTI-PROVIDER PARALLEL QUERY TEST")
        print("="*60)

        async def run_multi_provider():
            return await test_multi_provider(
                orch,
                "What is the meaning of life? Brief answer."
            )

        multi_time, multi_results = asyncio.run(run_multi_provider())
        print(f"\nQueried {len(multi_results)} providers in {multi_time:.2f} seconds (in parallel)")
        print(f"Sequential would take ~{multi_time * len(multi_results):.2f} seconds")

    print("\n" + "="*60)
    print(" ASYNC IMPLEMENTATION COMPLETE!")
    print("="*60)
    print("\nNew async methods available:")
    print("  - orch.delegate_async() - Single async request")
    print("  - orch.batch_delegate_async() - Parallel batch processing")
    print("  - orch.multi_provider_query_async() - Query multiple providers")
    print("\nUsage example:")
    print("  results = await orch.batch_delegate_async(tasks, 'cerebras', max_concurrent=5)")
    print("  # Or from sync code:")
    print("  import asyncio")
    print("  results = asyncio.run(orch.batch_delegate_async(tasks))")


if __name__ == "__main__":
    main()
