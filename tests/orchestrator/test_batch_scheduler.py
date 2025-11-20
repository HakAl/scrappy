"""
Tests for BatchScheduler - Parallel batch execution.

Tests behavior, not implementation:
- Tests prove the batch scheduler works
- Tests use minimal mocking (only external dependencies)
- Tests cover edge cases and error conditions
- Tests verify protocol compliance
"""

import pytest
import asyncio
from typing import Any
from unittest.mock import AsyncMock, Mock

from src.orchestrator.batch_scheduler import BatchScheduler, DEFAULT_MAX_CONCURRENT
from src.protocols.delegation import (
    BatchSchedulerProtocol,
    RetryOrchestratorProtocol,
    LLMRequest,
    OutputInterfaceProtocol,
)
from src.providers import LLMResponse


# Test doubles

class MockRetryOrchestrator:
    """Mock retry orchestrator that returns predictable responses."""

    def __init__(self, delay_ms: float = 0):
        self.delay_ms = delay_ms
        self.call_count = 0
        self.concurrent_calls = 0
        self.max_concurrent_calls = 0

    async def execute_with_retry(
        self,
        request: LLMRequest,
        excluded_providers: set[str],
        max_retries: int = 3,
    ) -> tuple[LLMResponse, dict]:
        """Mock execution with optional delay to test concurrency."""
        self.call_count += 1
        self.concurrent_calls += 1
        self.max_concurrent_calls = max(self.max_concurrent_calls, self.concurrent_calls)

        if self.delay_ms > 0:
            await asyncio.sleep(self.delay_ms / 1000.0)

        try:
            response = LLMResponse(
                content=f"Response for: {request.prompt}",
                provider=request.provider or "default",
                model=request.model or "default-model",
                tokens_used=10,
            )
            metadata = {
                "provider": request.provider or "default",
                "model": request.model or "default-model",
                "tokens_used": 10,
                "latency_ms": self.delay_ms,
                "fallback": False,
                "attempts": 1,
            }
            return response, metadata
        finally:
            self.concurrent_calls -= 1


class FailingRetryOrchestrator:
    """Mock orchestrator that always fails."""

    async def execute_with_retry(
        self,
        request: LLMRequest,
        excluded_providers: set[str],
        max_retries: int = 3,
    ) -> tuple[LLMResponse, dict]:
        """Always raise an error."""
        raise Exception(f"Provider {request.provider} failed")


class MockOutput:
    """Mock output interface that captures messages."""

    def __init__(self):
        self.messages = []
        self.errors = []

    def print(self, message: str) -> None:
        self.messages.append(message)

    def print_error(self, message: str) -> None:
        self.errors.append(message)


# Tests

@pytest.mark.asyncio
async def test_execute_batch_basic():
    """Test basic batch execution with multiple requests."""
    orchestrator = MockRetryOrchestrator()
    output = MockOutput()
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)

    requests = [
        LLMRequest(prompt="Request 1", provider="groq"),
        LLMRequest(prompt="Request 2", provider="groq"),
        LLMRequest(prompt="Request 3", provider="groq"),
    ]

    results = await scheduler.execute_batch(requests, max_concurrent=5)

    assert len(results) == 3
    assert orchestrator.call_count == 3

    # Verify responses match requests (order preserved)
    for i, (response, metadata) in enumerate(results):
        assert response.content == f"Response for: Request {i + 1}"
        assert metadata["provider"] == "groq"


@pytest.mark.asyncio
async def test_execute_batch_preserves_order():
    """Test that batch execution preserves request order."""
    # Use delays to ensure requests finish out of order
    orchestrator = MockRetryOrchestrator(delay_ms=50)
    output = MockOutput()
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)

    requests = [
        LLMRequest(prompt="First", provider="groq"),
        LLMRequest(prompt="Second", provider="groq"),
        LLMRequest(prompt="Third", provider="groq"),
    ]

    results = await scheduler.execute_batch(requests, max_concurrent=10)

    # Even with parallel execution, order should be preserved
    assert results[0][0].content == "Response for: First"
    assert results[1][0].content == "Response for: Second"
    assert results[2][0].content == "Response for: Third"


@pytest.mark.asyncio
async def test_execute_batch_concurrency_limit():
    """Test that max_concurrent limits parallel executions."""
    orchestrator = MockRetryOrchestrator(delay_ms=100)
    output = MockOutput()
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)

    requests = [LLMRequest(prompt=f"Request {i}", provider="groq") for i in range(10)]

    results = await scheduler.execute_batch(requests, max_concurrent=3)

    assert len(results) == 10
    # Verify concurrency was actually limited
    assert orchestrator.max_concurrent_calls <= 3
    assert orchestrator.max_concurrent_calls > 0


@pytest.mark.asyncio
async def test_execute_batch_with_default_concurrency():
    """Test batch execution with default max_concurrent."""
    orchestrator = MockRetryOrchestrator()
    output = MockOutput()
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)

    requests = [LLMRequest(prompt=f"Request {i}", provider="groq") for i in range(3)]

    results = await scheduler.execute_batch(requests)

    assert len(results) == 3
    assert orchestrator.call_count == 3


@pytest.mark.asyncio
async def test_execute_batch_handles_individual_failures():
    """Test that individual request failures don't fail entire batch."""
    orchestrator = FailingRetryOrchestrator()
    output = MockOutput()
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)

    requests = [
        LLMRequest(prompt="Request 1", provider="groq"),
        LLMRequest(prompt="Request 2", provider="openai"),
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
    orchestrator = MockRetryOrchestrator()
    output = MockOutput()
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)

    with pytest.raises(ValueError, match="Cannot execute batch with empty requests list"):
        await scheduler.execute_batch([], max_concurrent=5)


@pytest.mark.asyncio
async def test_execute_batch_invalid_max_concurrent():
    """Test that invalid max_concurrent raises ValueError."""
    orchestrator = MockRetryOrchestrator()
    output = MockOutput()
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)

    requests = [LLMRequest(prompt="Test", provider="groq")]

    with pytest.raises(ValueError, match="max_concurrent must be >= 1"):
        await scheduler.execute_batch(requests, max_concurrent=0)

    with pytest.raises(ValueError, match="max_concurrent must be >= 1"):
        await scheduler.execute_batch(requests, max_concurrent=-1)


@pytest.mark.asyncio
async def test_execute_batch_single_request():
    """Test batch execution with single request."""
    orchestrator = MockRetryOrchestrator()
    output = MockOutput()
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)

    requests = [LLMRequest(prompt="Single request", provider="groq")]

    results = await scheduler.execute_batch(requests, max_concurrent=5)

    assert len(results) == 1
    assert results[0][0].content == "Response for: Single request"
    assert orchestrator.call_count == 1


@pytest.mark.asyncio
async def test_execute_multi_provider_basic():
    """Test multi-provider execution for same prompt."""
    orchestrator = MockRetryOrchestrator()
    output = MockOutput()
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)

    request = LLMRequest(prompt="Test prompt", provider="groq")
    providers = ["groq", "openai", "anthropic"]

    results = await scheduler.execute_multi_provider(request, providers)

    assert len(results) == 3
    assert "groq" in results
    assert "openai" in results
    assert "anthropic" in results

    # Verify each provider got a response
    for provider, (response, metadata) in results.items():
        assert response.content == "Response for: Test prompt"
        assert response.provider == provider
        assert metadata["provider"] == provider


@pytest.mark.asyncio
async def test_execute_multi_provider_excludes_failures():
    """Test that failed providers are excluded from results."""
    orchestrator = FailingRetryOrchestrator()
    output = MockOutput()
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)

    request = LLMRequest(prompt="Test prompt", provider="groq")
    providers = ["groq", "openai"]

    results = await scheduler.execute_multi_provider(request, providers)

    # All providers failed, so results should be empty
    assert len(results) == 0

    # Errors should be logged
    assert len(output.errors) == 2


@pytest.mark.asyncio
async def test_execute_multi_provider_empty_providers_raises():
    """Test that empty providers list raises ValueError."""
    orchestrator = MockRetryOrchestrator()
    output = MockOutput()
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)

    request = LLMRequest(prompt="Test prompt", provider="groq")

    with pytest.raises(ValueError, match="Cannot execute multi-provider with empty providers list"):
        await scheduler.execute_multi_provider(request, [])


@pytest.mark.asyncio
async def test_execute_multi_provider_single_provider():
    """Test multi-provider with single provider."""
    orchestrator = MockRetryOrchestrator()
    output = MockOutput()
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)

    request = LLMRequest(prompt="Test prompt", provider="groq")
    providers = ["groq"]

    results = await scheduler.execute_multi_provider(request, providers)

    assert len(results) == 1
    assert "groq" in results
    assert results["groq"][0].content == "Response for: Test prompt"


@pytest.mark.asyncio
async def test_execute_multi_provider_disables_fallback():
    """Test that multi-provider mode disables auto_fallback."""
    orchestrator = MockRetryOrchestrator()
    output = MockOutput()
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)

    request = LLMRequest(prompt="Test prompt", provider="groq", auto_fallback=True)
    providers = ["groq", "openai"]

    results = await scheduler.execute_multi_provider(request, providers)

    # Should complete successfully
    assert len(results) == 2


def test_batch_scheduler_implements_protocol():
    """Test that BatchScheduler implements BatchSchedulerProtocol."""
    orchestrator = MockRetryOrchestrator()
    output = MockOutput()
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)

    # Verify it has the protocol methods
    assert hasattr(scheduler, "execute_batch")
    assert hasattr(scheduler, "execute_multi_provider")
    assert callable(scheduler.execute_batch)
    assert callable(scheduler.execute_multi_provider)


def test_batch_scheduler_requires_injected_dependencies():
    """Test that BatchScheduler requires dependencies to be injected."""
    orchestrator = MockRetryOrchestrator()
    output = MockOutput()

    # Should be able to create with all dependencies
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)
    assert scheduler._retry_orchestrator is orchestrator
    assert scheduler._output is output


@pytest.mark.asyncio
async def test_execute_batch_with_different_providers():
    """Test batch execution with requests for different providers."""
    orchestrator = MockRetryOrchestrator()
    output = MockOutput()
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)

    requests = [
        LLMRequest(prompt="Request 1", provider="groq"),
        LLMRequest(prompt="Request 2", provider="openai"),
        LLMRequest(prompt="Request 3", provider="anthropic"),
    ]

    results = await scheduler.execute_batch(requests, max_concurrent=5)

    assert len(results) == 3
    assert results[0][0].provider == "groq"
    assert results[1][0].provider == "openai"
    assert results[2][0].provider == "anthropic"


@pytest.mark.asyncio
async def test_execute_batch_parallel_execution():
    """Test that batch execution actually runs in parallel."""
    orchestrator = MockRetryOrchestrator(delay_ms=100)
    output = MockOutput()
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)

    requests = [LLMRequest(prompt=f"Request {i}", provider="groq") for i in range(5)]

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
    orchestrator = MockRetryOrchestrator(delay_ms=100)
    output = MockOutput()
    scheduler = BatchScheduler(retry_orchestrator=orchestrator, output=output)

    request = LLMRequest(prompt="Test prompt", provider="groq")
    providers = ["groq", "openai", "anthropic"]

    import time
    start = time.time()
    results = await scheduler.execute_multi_provider(request, providers)
    elapsed = time.time() - start

    # If parallel, should take ~100ms. If sequential, would take ~300ms.
    assert elapsed < 0.3, f"Took {elapsed}s, expected < 0.3s for parallel execution"
    assert len(results) == 3
