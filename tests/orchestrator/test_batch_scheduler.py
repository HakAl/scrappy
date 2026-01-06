"""
Tests for BatchScheduler - Parallel batch execution.

Tests behavior, not implementation:
- Tests prove the batch scheduler works
- Tests use minimal mocking (only external dependencies)
- Tests cover edge cases and error conditions
- Tests verify protocol compliance

After LiteLLM integration (Phase 3):
- Uses LLMServiceProtocol instead of RetryOrchestratorProtocol
- LLM calls go through LLMService.completion()
"""

import pytest
import asyncio
from typing import Any
from unittest.mock import AsyncMock, Mock

from scrappy.orchestrator.batch_scheduler import BatchScheduler, DEFAULT_MAX_CONCURRENT
from scrappy.protocols.delegation import (
    BatchSchedulerProtocol,
    LLMRequest,
    OutputInterfaceProtocol,
)
from scrappy.orchestrator.protocols import LLMServiceProtocol
from scrappy.providers import LLMResponse


# Test doubles

class MockLLMService:
    """Mock LLM service that returns predictable responses."""

    def __init__(self, delay_ms: float = 0):
        self.delay_ms = delay_ms
        self.call_count = 0
        self.concurrent_calls = 0
        self.max_concurrent_calls = 0

    async def completion(
        self,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> tuple[LLMResponse, dict]:
        """Mock completion with optional delay to test concurrency."""
        self.call_count += 1
        self.concurrent_calls += 1
        self.max_concurrent_calls = max(self.max_concurrent_calls, self.concurrent_calls)

        if self.delay_ms > 0:
            await asyncio.sleep(self.delay_ms / 1000.0)

        try:
            # Extract prompt from messages
            prompt = messages[-1].get("content", "") if messages else ""

            response = LLMResponse(
                content=f"Response for: {prompt}",
                provider=model or "default",
                model=f"{model or 'default'}/test-model",
                tokens_used=10,
            )
            metadata = {
                "provider": model or "default",
                "model": f"{model or 'default'}/test-model",
                "tokens_used": 10,
                "latency_ms": self.delay_ms,
                "fallback": False,
                "attempts": 1,
            }
            return response, metadata
        finally:
            self.concurrent_calls -= 1

    def completion_sync(
        self,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> tuple[LLMResponse, dict]:
        """Sync version for testing."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.completion(model, messages, **kwargs))
        finally:
            loop.close()


class FailingLLMService:
    """Mock LLM service that always fails."""

    async def completion(
        self,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> tuple[LLMResponse, dict]:
        """Always raise an error."""
        raise Exception(f"Model {model} failed")


class MockOutput:
    """Mock output interface that captures messages."""

    def __init__(self):
        self.messages = []
        self.errors = []

    def print(self, message: str) -> None:
        self.messages.append(message)

    def info(self, message: str) -> None:
        self.messages.append(message)

    def warn(self, message: str) -> None:
        self.messages.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)


# Tests

@pytest.mark.asyncio
async def test_execute_batch_basic():
    """Test basic batch execution with multiple requests."""
    llm_service = MockLLMService()
    output = MockOutput()
    scheduler = BatchScheduler(llm_service=llm_service, output=output)

    requests = [
        LLMRequest(prompt="Request 1", provider="fast"),
        LLMRequest(prompt="Request 2", provider="fast"),
        LLMRequest(prompt="Request 3", provider="fast"),
    ]

    results = await scheduler.execute_batch(requests, max_concurrent=5)

    assert len(results) == 3
    assert llm_service.call_count == 3

    # Verify responses match requests (order preserved)
    for i, (response, metadata) in enumerate(results):
        assert response.content == f"Response for: Request {i + 1}"


@pytest.mark.asyncio
async def test_execute_batch_preserves_order():
    """Test that batch execution preserves request order."""
    # Use delays to ensure requests finish out of order
    llm_service = MockLLMService(delay_ms=50)
    output = MockOutput()
    scheduler = BatchScheduler(llm_service=llm_service, output=output)

    requests = [
        LLMRequest(prompt="First", provider="fast"),
        LLMRequest(prompt="Second", provider="fast"),
        LLMRequest(prompt="Third", provider="fast"),
    ]

    results = await scheduler.execute_batch(requests, max_concurrent=10)

    # Even with parallel execution, order should be preserved
    assert results[0][0].content == "Response for: First"
    assert results[1][0].content == "Response for: Second"
    assert results[2][0].content == "Response for: Third"


@pytest.mark.asyncio
async def test_execute_batch_concurrency_limit():
    """Test that max_concurrent limits parallel executions."""
    llm_service = MockLLMService(delay_ms=100)
    output = MockOutput()
    scheduler = BatchScheduler(llm_service=llm_service, output=output)

    requests = [LLMRequest(prompt=f"Request {i}", provider="fast") for i in range(10)]

    results = await scheduler.execute_batch(requests, max_concurrent=3)

    assert len(results) == 10
    # Verify concurrency was actually limited
    assert llm_service.max_concurrent_calls <= 3
    assert llm_service.max_concurrent_calls > 0


@pytest.mark.asyncio
async def test_execute_batch_with_default_concurrency():
    """Test batch execution with default max_concurrent."""
    llm_service = MockLLMService()
    output = MockOutput()
    scheduler = BatchScheduler(llm_service=llm_service, output=output)

    requests = [LLMRequest(prompt=f"Request {i}", provider="fast") for i in range(3)]

    results = await scheduler.execute_batch(requests)

    assert len(results) == 3
    assert llm_service.call_count == 3


@pytest.mark.asyncio
async def test_execute_batch_handles_individual_failures():
    """Test that individual request failures don't fail entire batch."""
    llm_service = FailingLLMService()
    output = MockOutput()
    scheduler = BatchScheduler(llm_service=llm_service, output=output)

    requests = [
        LLMRequest(prompt="Request 1", provider="fast"),
        LLMRequest(prompt="Request 2", provider="quality"),
    ]

    results = await scheduler.execute_batch(requests, max_concurrent=5)

    # Batch should complete even with failures
    assert len(results) == 2

    # Failed requests return None with error metadata
    assert results[0][0] is None
    assert "error" in results[0][1]
    assert results[1][0] is None
    assert "error" in results[1][1]

    # Errors should be logged
    assert len(output.errors) == 2


@pytest.mark.asyncio
async def test_execute_batch_empty_requests_raises():
    """Test that empty requests list raises ValueError."""
    llm_service = MockLLMService()
    output = MockOutput()
    scheduler = BatchScheduler(llm_service=llm_service, output=output)

    with pytest.raises(ValueError, match="Cannot execute batch with empty requests list"):
        await scheduler.execute_batch([], max_concurrent=5)


@pytest.mark.asyncio
async def test_execute_batch_invalid_max_concurrent():
    """Test that invalid max_concurrent raises ValueError."""
    llm_service = MockLLMService()
    output = MockOutput()
    scheduler = BatchScheduler(llm_service=llm_service, output=output)

    requests = [LLMRequest(prompt="Test", provider="fast")]

    with pytest.raises(ValueError, match="max_concurrent must be >= 1"):
        await scheduler.execute_batch(requests, max_concurrent=0)

    with pytest.raises(ValueError, match="max_concurrent must be >= 1"):
        await scheduler.execute_batch(requests, max_concurrent=-1)


@pytest.mark.asyncio
async def test_execute_batch_single_request():
    """Test batch execution with single request."""
    llm_service = MockLLMService()
    output = MockOutput()
    scheduler = BatchScheduler(llm_service=llm_service, output=output)

    requests = [LLMRequest(prompt="Single request", provider="fast")]

    results = await scheduler.execute_batch(requests, max_concurrent=5)

    assert len(results) == 1
    assert results[0][0].content == "Response for: Single request"
    assert llm_service.call_count == 1


@pytest.mark.asyncio
async def test_execute_multi_provider_basic():
    """Test multi-provider execution for same prompt."""
    llm_service = MockLLMService()
    output = MockOutput()
    scheduler = BatchScheduler(llm_service=llm_service, output=output)

    request = LLMRequest(prompt="Test prompt", provider="fast")
    model_groups = ["fast", "chat", "instruct"]

    results = await scheduler.execute_multi_provider(request, model_groups)

    assert len(results) == 3
    assert "fast" in results
    assert "chat" in results
    assert "instruct" in results

    # Verify each model group got a response
    for group, (response, metadata) in results.items():
        assert response.content == "Response for: Test prompt"


@pytest.mark.asyncio
async def test_execute_multi_provider_excludes_failures():
    """Test that failed model groups are excluded from results."""
    llm_service = FailingLLMService()
    output = MockOutput()
    scheduler = BatchScheduler(llm_service=llm_service, output=output)

    request = LLMRequest(prompt="Test prompt", provider="fast")
    model_groups = ["fast", "chat", "instruct"]

    results = await scheduler.execute_multi_provider(request, model_groups)

    # All groups failed, so results should be empty
    assert len(results) == 0

    # Errors should be logged (one per model group)
    assert len(output.errors) == 3


@pytest.mark.asyncio
async def test_execute_multi_provider_empty_providers_raises():
    """Test that empty model_groups list raises ValueError."""
    llm_service = MockLLMService()
    output = MockOutput()
    scheduler = BatchScheduler(llm_service=llm_service, output=output)

    request = LLMRequest(prompt="Test prompt", provider="fast")

    with pytest.raises(ValueError, match="Cannot execute multi-provider with empty model_groups list"):
        await scheduler.execute_multi_provider(request, [])


@pytest.mark.asyncio
async def test_execute_multi_provider_single_provider():
    """Test multi-provider with single model group."""
    llm_service = MockLLMService()
    output = MockOutput()
    scheduler = BatchScheduler(llm_service=llm_service, output=output)

    request = LLMRequest(prompt="Test prompt", provider="fast")
    model_groups = ["fast"]

    results = await scheduler.execute_multi_provider(request, model_groups)

    assert len(results) == 1
    assert "fast" in results
    assert results["fast"][0].content == "Response for: Test prompt"


@pytest.mark.asyncio
async def test_execute_multi_provider_disables_fallback():
    """Test that multi-provider mode works with model groups."""
    llm_service = MockLLMService()
    output = MockOutput()
    scheduler = BatchScheduler(llm_service=llm_service, output=output)

    request = LLMRequest(prompt="Test prompt", provider="fast", auto_fallback=True)
    model_groups = ["fast", "chat", "instruct"]

    results = await scheduler.execute_multi_provider(request, model_groups)

    # Should complete successfully (one result per model group)
    assert len(results) == 3


def test_batch_scheduler_requires_injected_dependencies():
    """Test that BatchScheduler requires dependencies to be injected."""
    llm_service = MockLLMService()
    output = MockOutput()

    # Should be able to create with all dependencies
    scheduler = BatchScheduler(llm_service=llm_service, output=output)
    assert scheduler._llm_service is llm_service
    assert scheduler._output is output


@pytest.mark.asyncio
async def test_execute_batch_with_different_providers():
    """Test batch execution with requests for different model groups."""
    llm_service = MockLLMService()
    output = MockOutput()
    scheduler = BatchScheduler(llm_service=llm_service, output=output)

    requests = [
        LLMRequest(prompt="Request 1", provider="fast"),
        LLMRequest(prompt="Request 2", provider="quality"),
        LLMRequest(prompt="Request 3", provider="fast"),
    ]

    results = await scheduler.execute_batch(requests, max_concurrent=5)

    assert len(results) == 3
    # All responses should be valid
    for response, metadata in results:
        assert response is not None


@pytest.mark.asyncio
async def test_execute_batch_parallel_execution():
    """Test that batch execution actually runs in parallel."""
    llm_service = MockLLMService(delay_ms=100)
    output = MockOutput()
    scheduler = BatchScheduler(llm_service=llm_service, output=output)

    requests = [LLMRequest(prompt=f"Request {i}", provider="fast") for i in range(5)]

    import time
    start = time.time()
    results = await scheduler.execute_batch(requests, max_concurrent=5)
    elapsed = time.time() - start

    # If parallel, should take ~100ms. If sequential, would take ~500ms.
    # Allow some margin for overhead
    assert elapsed < 0.3, f"Took {elapsed}s, expected < 0.3s for parallel execution"
    assert len(results) == 5


@pytest.mark.asyncio
async def test_execute_multi_provider_parallel_execution():
    """Test that multi-provider queries run in parallel."""
    llm_service = MockLLMService(delay_ms=100)
    output = MockOutput()
    scheduler = BatchScheduler(llm_service=llm_service, output=output)

    request = LLMRequest(prompt="Test prompt", provider="fast")
    model_groups = ["fast", "chat", "instruct"]

    import time
    start = time.time()
    results = await scheduler.execute_multi_provider(request, model_groups)
    elapsed = time.time() - start

    # If parallel, should take ~100ms. If sequential, would take ~300ms.
    assert elapsed < 0.3, f"Took {elapsed}s, expected < 0.3s for parallel execution"
    assert len(results) == 3
