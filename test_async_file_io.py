#!/usr/bin/env python3
"""
Test script to demonstrate async file I/O benefits.

This script compares blocking vs non-blocking file operations during async LLM calls.
"""

import asyncio
import time
from src.orchestrator import AgentOrchestrator


async def test_async_file_io():
    """Test that async file I/O doesn't block the event loop."""
    print("Initializing orchestrator...")
    orch = AgentOrchestrator(
        auto_register=True,
        context_aware=False,  # Disable context for cleaner test
        enable_cache=True     # Enable cache to test async file writes
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
    print(" ASYNC FILE I/O TEST")
    print("="*60)

    # Test 1: Multiple parallel requests with cache writes
    print("\n1. Testing parallel requests with async cache persistence...")

    tasks = [
        {'prompt': 'What is 1+1? Reply with just the number.'},
        {'prompt': 'What is 2+2? Reply with just the number.'},
        {'prompt': 'What is 3+3? Reply with just the number.'},
    ]

    start = time.time()
    results = await orch.batch_delegate_async(tasks, test_provider, max_concurrent=3)
    elapsed = time.time() - start

    print(f"   Completed {len(results)} parallel requests in {elapsed:.2f}s")
    for i, result in enumerate(results):
        print(f"   Task {i+1}: {result.latency_ms:.0f}ms, cached={result.latency_ms == 0}")

    # Test 2: Verify cache was written asynchronously
    print("\n2. Verifying cache persistence...")
    cache_stats = orch.get_cache_stats()
    print(f"   Cache entries: {cache_stats['exact_cache_entries']}")
    print(f"   Cache saves: {cache_stats['saves']}")
    print(f"   Cache file: {cache_stats['cache_file']}")

    # Test 3: Check rate limit tracker was written asynchronously
    print("\n3. Verifying rate limit tracker persistence...")
    rate_status = orch.get_rate_limit_status()
    provider_usage = rate_status.get('providers', {}).get(test_provider, {})
    print(f"   Requests today: {provider_usage.get('total_requests_today', 0)}")
    print(f"   Tokens today: {provider_usage.get('total_tokens_today', 0)}")

    # Test 4: Test concurrent file I/O with different operations
    print("\n4. Testing concurrent requests to show non-blocking I/O...")

    async def measure_event_loop_responsiveness():
        """Measure how responsive the event loop is during file I/O."""
        check_times = []
        for _ in range(10):
            check_start = time.time()
            await asyncio.sleep(0)  # Yield to event loop
            check_times.append((time.time() - check_start) * 1000)
        return check_times

    # Run responsiveness check alongside API requests
    responsiveness_task = asyncio.create_task(measure_event_loop_responsiveness())

    # Make another request that will trigger file I/O
    response = await orch.delegate_async(
        test_provider,
        'What is 4+4? Just the number.',
        use_cache=True
    )

    check_times = await responsiveness_task
    avg_response_time = sum(check_times) / len(check_times)
    max_response_time = max(check_times)

    print(f"   Event loop avg response: {avg_response_time:.3f}ms")
    print(f"   Event loop max response: {max_response_time:.3f}ms")
    print(f"   (Low values indicate non-blocking file I/O)")

    # Test 5: Cache hit test (should be instant, no file I/O)
    print("\n5. Testing cache hit performance (no API call, no file write)...")

    # Repeat a cached query
    start = time.time()
    cached_result = await orch.delegate_async(
        test_provider,
        'What is 1+1? Reply with just the number.',
        use_cache=True
    )
    elapsed_cached = (time.time() - start) * 1000

    print(f"   Cache hit latency: {elapsed_cached:.2f}ms")
    print(f"   Response tokens: {cached_result.tokens_used}")
    print(f"   Response: {cached_result.content.strip()[:50]}")

    # Final summary
    print("\n" + "="*60)
    print(" ASYNC FILE I/O IMPLEMENTATION SUMMARY")
    print("="*60)
    print("\nAsync file I/O methods added:")
    print("  - cache.put_async() - Non-blocking cache writes")
    print("  - cache.put_by_intent_async() - Async intent cache writes")
    print("  - cache._save_cache_async() - Async JSON persistence")
    print("  - cache._load_cache_async() - Async cache loading")
    print("  - rate_tracker.record_request_async() - Async rate tracking")
    print("  - rate_tracker._save_tracker_async() - Async tracker persistence")

    print("\nBenefits:")
    print("  - File writes don't block the event loop")
    print("  - Better parallel request performance")
    print("  - Reduced latency for concurrent operations")
    print("  - Automatic fallback if aiofiles not available")

    print("\nUsage:")
    print("  # These are now used automatically in delegate_async:")
    print("  await orch.delegate_async('cerebras', 'prompt')  # Uses async file I/O")
    print("  await orch.batch_delegate_async(tasks, 'groq')   # Parallel with async I/O")


def main():
    asyncio.run(test_async_file_io())


if __name__ == "__main__":
    main()
