#!/usr/bin/env python3
"""
Test script to demonstrate background cache writes (fire-and-forget).

This script shows how cache writes don't block the response return.
"""

import asyncio
import time
from src.orchestrator import AgentOrchestrator


async def test_background_writes():
    """Test that cache writes happen in background without blocking."""
    print("Initializing orchestrator...")
    orch = AgentOrchestrator(
        auto_register=True,
        context_aware=False,  # Disable context for cleaner test
        enable_cache=True     # Enable cache to test background writes
    )

    available = orch.registry.list_available()
    print(f"\nAvailable providers: {available}")

    if not available:
        print("No providers available! Check your API keys.")
        return

    # Pick a provider for testing
    test_provider = 'cerebras' if 'cerebras' in available else available[0]
    print(f"Using provider: {test_provider}")

    print("\n" + "="*60)
    print(" BACKGROUND CACHE WRITE TEST")
    print("="*60)

    # Test 1: Response returns immediately, writes happen in background
    print("\n1. Testing immediate response with background writes...")

    # Clear any previous cache entries for clean test
    orch.clear_cache()

    start = time.time()
    response = await orch.delegate_async(
        test_provider,
        'What is 5+5? Reply with just the number.',
        use_cache=True
    )
    response_time = time.time() - start

    # Check background task status immediately after response
    bg_status = orch.get_background_task_status()

    print(f"   Response received in: {response_time*1000:.2f}ms")
    print(f"   Response: {response.content.strip()[:50]}")
    print(f"   Pending background tasks: {bg_status['pending_tasks']}")

    # Wait a moment to let background tasks complete
    await asyncio.sleep(0.1)

    bg_status_after = orch.get_background_task_status()
    print(f"   After 100ms wait, pending tasks: {bg_status_after['pending_tasks']}")

    # Test 2: Verify cache was persisted
    print("\n2. Verifying cache persistence...")
    cache_stats = orch.get_cache_stats()
    print(f"   Cache entries: {cache_stats['exact_cache_entries']}")
    print(f"   Cache saves: {cache_stats['saves']}")

    # Test 3: Multiple parallel requests with background writes
    print("\n3. Testing parallel requests with background writes...")

    tasks = [
        {'prompt': 'What is 6+6? Reply with just the number.'},
        {'prompt': 'What is 7+7? Reply with just the number.'},
        {'prompt': 'What is 8+8? Reply with just the number.'},
    ]

    start = time.time()
    results = await orch.batch_delegate_async(tasks, test_provider, max_concurrent=3)
    total_time = time.time() - start

    # Check background tasks immediately
    bg_status_parallel = orch.get_background_task_status()

    print(f"   Completed {len(results)} requests in {total_time*1000:.2f}ms")
    print(f"   Pending background writes: {bg_status_parallel['pending_tasks']}")

    for i, result in enumerate(results):
        print(f"   Task {i+1}: {result.content.strip()[:30]}, {result.latency_ms:.0f}ms")

    # Test 4: Wait for all background tasks to complete
    print("\n4. Waiting for background tasks to complete...")
    wait_result = await orch.wait_for_background_tasks(timeout=5.0)
    print(f"   Status: {wait_result['status']}")
    print(f"   Completed: {wait_result.get('completed', 0)} tasks")
    print(f"   Errors: {wait_result['errors']}")

    # Test 5: Verify all writes completed
    print("\n5. Final verification...")
    cache_stats_final = orch.get_cache_stats()
    print(f"   Total cache entries: {cache_stats_final['exact_cache_entries']}")
    print(f"   Total cache saves: {cache_stats_final['saves']}")

    rate_status = orch.get_rate_limit_status()
    provider_usage = rate_status.get('providers', {}).get(test_provider, {})
    print(f"   Rate tracker - Requests today: {provider_usage.get('total_requests_today', 0)}")
    print(f"   Rate tracker - Tokens today: {provider_usage.get('total_tokens_today', 0)}")

    # Test 6: Check for any background errors
    print("\n6. Background task error log...")
    bg_final = orch.get_background_task_status()
    if bg_final['total_errors'] > 0:
        print(f"   Total errors: {bg_final['total_errors']}")
        for error in bg_final['recent_errors']:
            print(f"   - {error['type']}: {error['error'][:100]}")
    else:
        print(f"   No errors - all background writes succeeded!")

    # Final summary
    print("\n" + "="*60)
    print(" BACKGROUND CACHE WRITE IMPLEMENTATION SUMMARY")
    print("="*60)
    print("\nKey improvements:")
    print("  - Response returns immediately (no blocking on file I/O)")
    print("  - Cache writes happen asynchronously in background")
    print("  - Rate limit tracking is non-blocking")
    print("  - Background task errors are captured without affecting main flow")
    print("  - Tasks are tracked to prevent garbage collection")
    print("  - Optional wait_for_background_tasks() for testing/shutdown")

    print("\nNew methods added:")
    print("  - orch._schedule_background_task(coro)")
    print("  - await orch.wait_for_background_tasks(timeout)")
    print("  - orch.get_background_task_status()")
    print("  - orch.clear_background_errors()")

    print("\nPerformance benefits:")
    print("  - Lower perceived latency (response returns faster)")
    print("  - Better throughput for parallel requests")
    print("  - File I/O doesn't block the event loop")
    print("  - Graceful error handling for persistence failures")


def main():
    asyncio.run(test_background_writes())


if __name__ == "__main__":
    main()
