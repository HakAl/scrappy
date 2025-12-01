"""
Tests for RetryOrchestrator.

Tests behavior, not implementation - following TDD principles:
- Test that features work correctly
- Test edge cases and error conditions
- Use minimal mocking (only external dependencies)
- Tests prove the orchestrator handles retries and fallbacks correctly
"""

import pytest
from unittest.mock import Mock
from datetime import datetime

from scrappy.orchestrator.retry_orchestrator import RetryOrchestrator
from scrappy.protocols.delegation import LLMRequest
from scrappy.providers.base import LLMResponse
from scrappy.infrastructure.exceptions import (
    RateLimitError,
    AllProvidersRateLimitedError,
)


# Test Doubles
# These implement the protocols with minimal behavior for testing


class FakeProvider:
    """Fake provider that can be configured to succeed or fail."""

    def __init__(
        self,
        name: str,
        fail_count: int = 0,
        fail_with: Exception = None,
        response_content: str = "test response",
    ):
        self.name = name
        self.default_model = f"{name}-default"
        self.fail_count = fail_count
        self.fail_with = fail_with
        self.response_content = response_content
        self.call_count = 0
        self.sync_call_count = 0

    async def chat_async(self, messages, model=None, **kwargs):
        """Simulate async LLM call with configurable failure."""
        self.call_count += 1

        # Fail for configured number of times
        if self.call_count <= self.fail_count:
            raise self.fail_with

        # Success
        return LLMResponse(
            content=self.response_content,
            model=model or self.default_model,
            provider=self.name,
            tokens_used=100,
            input_tokens=50,
            output_tokens=50,
            latency_ms=100.0,
            timestamp=datetime.now(),
        )

    def chat(self, messages, model=None, **kwargs):
        """Simulate sync LLM call with configurable failure."""
        self.sync_call_count += 1

        # Fail for configured number of times
        if self.sync_call_count <= self.fail_count:
            raise self.fail_with

        # Success
        return LLMResponse(
            content=self.response_content,
            model=model or self.default_model,
            provider=self.name,
            tokens_used=100,
            input_tokens=50,
            output_tokens=50,
            latency_ms=100.0,
            timestamp=datetime.now(),
        )

    def get_limits(self):
        """Return fake limits."""
        return Mock(requests_per_day=1000)


class FakeProviderRegistry:
    """Fake registry that provides configured providers."""

    def __init__(self):
        self.providers = {}

    def add(self, provider: FakeProvider):
        """Add a provider to the registry."""
        self.providers[provider.name] = provider

    def get(self, name: str):
        """Get a provider by name."""
        if name not in self.providers:
            raise KeyError(f"Provider '{name}' not found")
        return self.providers[name]

    def list_available(self):
        """List all available providers."""
        return list(self.providers.keys())


class FakeRateLimitTracker:
    """Fake rate tracker that tracks requests."""

    def __init__(self):
        self.requests = []

    def record_request(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        success: bool = True,
        error_message: str = None,
    ):
        """Record a request."""
        self.requests.append({
            'provider': provider,
            'model': model,
            'success': success,
            'error_message': error_message,
        })

    def get_remaining_quota(self, provider: str, model: str, limits):
        """Return fake remaining quota."""
        return {
            'requests_today_remaining': 100,
            'tokens_remaining': 10000,
        }

    def is_limit_approaching(self, provider: str, model: str, limits):
        """Return no warnings."""
        return {'warning': False, 'message': None}


class FakeProviderSelector:
    """Fake selector that provides configured fallback order."""

    def __init__(self, fallback_order=None):
        self.fallback_order = fallback_order or []
        self.fallback_index = 0

    def get_provider_for_fallback(self, exclude: list):
        """Get next provider not in exclude list."""
        for provider in self.fallback_order:
            if provider not in exclude:
                return provider
        return None


class FakeOutput:
    """Fake output that captures messages."""

    def __init__(self):
        self.messages = []
        self.warnings = []
        self.errors = []

    def print(self, message: str):
        self.messages.append(message)

    def info(self, message: str):
        self.messages.append(message)

    def warn(self, message: str):
        self.warnings.append(message)

    def error(self, message: str):
        self.errors.append(message)


# Fixtures


@pytest.fixture
def fake_registry():
    """Provide a fake provider registry."""
    return FakeProviderRegistry()


@pytest.fixture
def fake_rate_tracker():
    """Provide a fake rate limit tracker."""
    return FakeRateLimitTracker()


@pytest.fixture
def fake_output():
    """Provide a fake output interface."""
    return FakeOutput()


@pytest.fixture
def fake_selector():
    """Provide a fake provider selector."""
    return FakeProviderSelector(fallback_order=['groq', 'cerebras', 'gemini'])


@pytest.fixture
def orchestrator(fake_registry, fake_rate_tracker, fake_selector, fake_output):
    """Provide a RetryOrchestrator with fake dependencies."""
    return RetryOrchestrator(
        registry=fake_registry,
        rate_tracker=fake_rate_tracker,
        provider_selector=fake_selector,
        output=fake_output,
    )


# Tests - Behavior Verification


class TestRetryOrchestratorSuccessPath:
    """Tests that verify successful request execution."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self, orchestrator, fake_registry):
        """Verify request succeeds without retries when provider responds."""
        # Setup: Provider that succeeds immediately
        provider = FakeProvider('groq', fail_count=0)
        fake_registry.add(provider)

        # Execute
        request = LLMRequest(
            prompt="test prompt",
            provider="groq",
        )
        response, metadata = await orchestrator.execute_with_retry(
            request=request,
            excluded_providers=set(),
        )

        # Verify
        assert response.content == "test response"
        assert response.provider == "groq"
        assert metadata['provider'] == "groq"
        assert metadata['attempts'] == 1
        assert metadata['fallback'] is False
        assert provider.call_count == 1

    @pytest.mark.asyncio
    async def test_succeeds_after_retry(self, orchestrator, fake_registry, fake_output):
        """Verify request succeeds after retrying on rate limit."""
        # Setup: Provider that fails once with rate limit, then succeeds
        provider = FakeProvider(
            'groq',
            fail_count=1,
            fail_with=RateLimitError('groq', 'rate limited'),
        )
        fake_registry.add(provider)

        # Execute
        request = LLMRequest(prompt="test prompt", provider="groq")
        response, metadata = await orchestrator.execute_with_retry(
            request=request,
            excluded_providers=set(),
            max_retries=3,
        )

        # Verify
        assert response.content == "test response"
        assert provider.call_count == 2  # Failed once, succeeded on retry
        assert metadata['attempts'] == 2
        assert len(fake_output.warnings) > 0  # Should have warned about retry


class TestRetryOrchestratorFallback:
    """Tests that verify provider fallback logic."""

    @pytest.mark.asyncio
    async def test_falls_back_to_next_provider(
        self,
        orchestrator,
        fake_registry,
        fake_output,
    ):
        """Verify orchestrator falls back to next provider when first exhausted."""
        # Setup: First provider always fails, second succeeds
        groq = FakeProvider(
            'groq',
            fail_count=999,
            fail_with=RateLimitError('groq', 'rate limited'),
        )
        cerebras = FakeProvider('cerebras', fail_count=0)
        fake_registry.add(groq)
        fake_registry.add(cerebras)

        # Execute
        request = LLMRequest(prompt="test prompt", provider="groq")
        response, metadata = await orchestrator.execute_with_retry(
            request=request,
            excluded_providers=set(),
            max_retries=2,
        )

        # Verify
        assert response.provider == "cerebras"  # Fell back to cerebras
        assert metadata['fallback'] is True
        assert response.metadata['fallback_from'] == "groq"
        assert response.metadata['fallback_to'] == "cerebras"
        assert groq.call_count == 2  # Tried max_retries times
        assert cerebras.call_count == 1  # Succeeded on first attempt
        assert any('[FALLBACK]' in msg for msg in fake_output.messages)

    @pytest.mark.asyncio
    async def test_includes_attempted_providers_in_metadata(
        self,
        orchestrator,
        fake_registry,
    ):
        """Verify metadata includes list of attempted providers."""
        # Setup
        groq = FakeProvider(
            'groq',
            fail_count=999,
            fail_with=RateLimitError('groq', 'rate limited'),
        )
        cerebras = FakeProvider('cerebras', fail_count=0)
        fake_registry.add(groq)
        fake_registry.add(cerebras)

        # Execute
        request = LLMRequest(prompt="test prompt", provider="groq")
        response, metadata = await orchestrator.execute_with_retry(
            request=request,
            excluded_providers=set(),
            max_retries=1,
        )

        # Verify
        assert 'attempted_providers' in response.metadata
        assert 'groq' in response.metadata['attempted_providers']


class TestRetryOrchestratorErrorHandling:
    """Tests that verify error handling behavior."""

    @pytest.mark.asyncio
    async def test_raises_when_all_providers_exhausted(
        self,
        orchestrator,
        fake_registry,
        fake_output,
    ):
        """Verify error raised when all providers are rate limited."""
        # Setup: All providers fail
        groq = FakeProvider(
            'groq',
            fail_count=999,
            fail_with=RateLimitError('groq', 'rate limited'),
        )
        cerebras = FakeProvider(
            'cerebras',
            fail_count=999,
            fail_with=RateLimitError('cerebras', 'rate limited'),
        )
        gemini = FakeProvider(
            'gemini',
            fail_count=999,
            fail_with=RateLimitError('gemini', 'rate limited'),
        )
        fake_registry.add(groq)
        fake_registry.add(cerebras)
        fake_registry.add(gemini)

        # Execute & Verify
        request = LLMRequest(prompt="test prompt", provider="groq")
        with pytest.raises(AllProvidersRateLimitedError) as exc_info:
            await orchestrator.execute_with_retry(
                request=request,
                excluded_providers=set(),
                max_retries=1,
            )

        # Verify error message includes attempted providers
        assert 'groq' in exc_info.value.attempted_providers
        assert 'cerebras' in exc_info.value.attempted_providers
        assert 'gemini' in exc_info.value.attempted_providers

    @pytest.mark.asyncio
    async def test_raises_non_rate_limit_errors_immediately(
        self,
        orchestrator,
        fake_registry,
    ):
        """Verify non-rate-limit errors are raised immediately without retry."""
        # Setup: Provider that fails with non-rate-limit error
        provider = FakeProvider(
            'groq',
            fail_count=999,
            fail_with=ValueError("Invalid model configuration"),
        )
        fake_registry.add(provider)

        # Execute & Verify
        request = LLMRequest(prompt="test prompt", provider="groq")
        with pytest.raises(ValueError, match="Invalid model configuration"):
            await orchestrator.execute_with_retry(
                request=request,
                excluded_providers=set(),
            )

        # Verify it didn't retry
        assert provider.call_count == 1  # Only tried once


class TestRetryOrchestratorRateLimitTracking:
    """Tests that verify rate limit tracking integration."""

    @pytest.mark.asyncio
    async def test_records_successful_requests(
        self,
        orchestrator,
        fake_registry,
        fake_rate_tracker,
    ):
        """Verify successful requests are recorded in rate tracker."""
        # Setup
        provider = FakeProvider('groq', fail_count=0)
        fake_registry.add(provider)

        # Execute
        request = LLMRequest(prompt="test prompt", provider="groq")
        await orchestrator.execute_with_retry(
            request=request,
            excluded_providers=set(),
        )

        # Verify
        assert len(fake_rate_tracker.requests) == 1
        assert fake_rate_tracker.requests[0]['provider'] == 'groq'
        assert fake_rate_tracker.requests[0]['success'] is True

    @pytest.mark.asyncio
    async def test_records_failed_rate_limit_requests(
        self,
        orchestrator,
        fake_registry,
        fake_rate_tracker,
    ):
        """Verify failed rate limit requests are recorded."""
        # Setup: Provider fails with rate limit then succeeds
        provider = FakeProvider(
            'groq',
            fail_count=1,
            fail_with=RateLimitError('groq', 'rate limited'),
        )
        fake_registry.add(provider)

        # Execute
        request = LLMRequest(prompt="test prompt", provider="groq")
        await orchestrator.execute_with_retry(
            request=request,
            excluded_providers=set(),
        )

        # Verify: Should have 2 records (1 failure, 1 success)
        assert len(fake_rate_tracker.requests) == 2
        assert fake_rate_tracker.requests[0]['success'] is False  # First attempt failed
        assert fake_rate_tracker.requests[1]['success'] is True   # Retry succeeded


class TestRetryOrchestratorEdgeCases:
    """Tests that verify edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_handles_empty_prompt_in_request(self, orchestrator):
        """Verify request validation catches empty prompts."""
        # LLMRequest validates in __post_init__, so this should raise
        with pytest.raises(ValueError, match="prompt cannot be empty"):
            LLMRequest(prompt="", provider="groq")

    @pytest.mark.asyncio
    async def test_handles_invalid_temperature(self, orchestrator):
        """Verify request validation catches invalid temperature."""
        with pytest.raises(ValueError, match="temperature must be"):
            LLMRequest(prompt="test", provider="groq", temperature=3.0)

    @pytest.mark.asyncio
    async def test_handles_invalid_max_tokens(self, orchestrator):
        """Verify request validation catches invalid max_tokens."""
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            LLMRequest(prompt="test", provider="groq", max_tokens=-1)

    @pytest.mark.asyncio
    async def test_handles_unknown_provider(self, orchestrator, fake_registry):
        """Verify error when provider doesn't exist in registry."""
        # Execute & Verify
        request = LLMRequest(prompt="test prompt", provider="unknown_provider")
        with pytest.raises(KeyError, match="Provider 'unknown_provider' not found"):
            await orchestrator.execute_with_retry(
                request=request,
                excluded_providers=set(),
            )

    @pytest.mark.asyncio
    async def test_respects_max_retries_parameter(
        self,
        orchestrator,
        fake_registry,
    ):
        """Verify max_retries parameter is respected."""
        # Setup: All providers fail so we can count retries
        groq = FakeProvider(
            'groq',
            fail_count=999,
            fail_with=RateLimitError('groq', 'rate limited'),
        )
        cerebras = FakeProvider(
            'cerebras',
            fail_count=999,
            fail_with=RateLimitError('cerebras', 'rate limited'),
        )
        gemini = FakeProvider(
            'gemini',
            fail_count=999,
            fail_with=RateLimitError('gemini', 'rate limited'),
        )
        fake_registry.add(groq)
        fake_registry.add(cerebras)
        fake_registry.add(gemini)

        # Execute with max_retries=2
        request = LLMRequest(prompt="test prompt", provider="groq")
        try:
            await orchestrator.execute_with_retry(
                request=request,
                excluded_providers=set(),
                max_retries=2,
            )
        except AllProvidersRateLimitedError:
            pass

        # Verify it tried exactly max_retries times before moving to next provider
        assert groq.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_already_excluded_provider(
        self,
        orchestrator,
        fake_registry,
    ):
        """Verify behavior when requested provider is already excluded."""
        # Setup
        cerebras = FakeProvider('cerebras', fail_count=0)
        fake_registry.add(cerebras)

        # Execute: Request groq but groq is excluded, should fallback to cerebras
        request = LLMRequest(prompt="test prompt", provider="groq")
        response, metadata = await orchestrator.execute_with_retry(
            request=request,
            excluded_providers={'groq'},  # groq already excluded
        )

        # Verify: Should have used cerebras (first available fallback)
        assert response.provider == "cerebras"
        assert metadata['fallback'] is True


class TestRetryOrchestratorSyncPath:
    """Tests for the synchronous execute_with_retry_sync method."""

    def test_sync_succeeds_on_first_attempt(self, orchestrator, fake_registry):
        """Verify sync request succeeds without retries when provider responds."""
        # Setup: Provider that succeeds immediately
        provider = FakeProvider('groq', fail_count=0)
        fake_registry.add(provider)

        # Execute using SYNC method
        request = LLMRequest(
            prompt="test prompt",
            provider="groq",
        )
        response, metadata = orchestrator.execute_with_retry_sync(
            request=request,
            excluded_providers=set(),
        )

        # Verify
        assert response.content == "test response"
        assert response.provider == "groq"
        assert metadata['provider'] == "groq"
        assert metadata['attempts'] == 1
        assert metadata['fallback'] is False
        assert provider.sync_call_count == 1  # Used sync method

    def test_sync_succeeds_after_retry(self, orchestrator, fake_registry, fake_output):
        """Verify sync request succeeds after retrying on rate limit."""
        # Setup: Provider that fails once with rate limit, then succeeds
        provider = FakeProvider(
            'groq',
            fail_count=1,
            fail_with=RateLimitError('groq', 'rate limited'),
        )
        fake_registry.add(provider)

        # Execute using SYNC method
        request = LLMRequest(prompt="test prompt", provider="groq")
        response, metadata = orchestrator.execute_with_retry_sync(
            request=request,
            excluded_providers=set(),
            max_retries=3,
        )

        # Verify
        assert response.content == "test response"
        assert provider.sync_call_count == 2  # Failed once, succeeded on retry
        assert metadata['attempts'] == 2
        assert len(fake_output.warnings) > 0  # Should have warned about retry

    def test_sync_falls_back_to_next_provider(
        self,
        orchestrator,
        fake_registry,
        fake_output,
    ):
        """Verify sync orchestrator falls back to next provider when first exhausted."""
        # Setup: First provider always fails, second succeeds
        groq = FakeProvider(
            'groq',
            fail_count=999,
            fail_with=RateLimitError('groq', 'rate limited'),
        )
        cerebras = FakeProvider('cerebras', fail_count=0)
        fake_registry.add(groq)
        fake_registry.add(cerebras)

        # Execute using SYNC method
        request = LLMRequest(prompt="test prompt", provider="groq")
        response, metadata = orchestrator.execute_with_retry_sync(
            request=request,
            excluded_providers=set(),
            max_retries=2,
        )

        # Verify
        assert response.provider == "cerebras"  # Fell back to cerebras
        assert metadata['fallback'] is True
        assert response.metadata['fallback_from'] == "groq"
        assert response.metadata['fallback_to'] == "cerebras"
        assert groq.sync_call_count == 2  # Tried max_retries times
        assert cerebras.sync_call_count == 1  # Succeeded on first attempt

    def test_sync_raises_when_all_providers_exhausted(
        self,
        orchestrator,
        fake_registry,
        fake_output,
    ):
        """Verify error raised when all providers are rate limited (sync)."""
        # Setup: All providers fail
        groq = FakeProvider(
            'groq',
            fail_count=999,
            fail_with=RateLimitError('groq', 'rate limited'),
        )
        cerebras = FakeProvider(
            'cerebras',
            fail_count=999,
            fail_with=RateLimitError('cerebras', 'rate limited'),
        )
        gemini = FakeProvider(
            'gemini',
            fail_count=999,
            fail_with=RateLimitError('gemini', 'rate limited'),
        )
        fake_registry.add(groq)
        fake_registry.add(cerebras)
        fake_registry.add(gemini)

        # Execute & Verify
        request = LLMRequest(prompt="test prompt", provider="groq")
        with pytest.raises(AllProvidersRateLimitedError) as exc_info:
            orchestrator.execute_with_retry_sync(
                request=request,
                excluded_providers=set(),
                max_retries=1,
            )

        # Verify error message includes attempted providers
        assert 'groq' in exc_info.value.attempted_providers
        assert 'cerebras' in exc_info.value.attempted_providers
        assert 'gemini' in exc_info.value.attempted_providers

    def test_sync_raises_non_rate_limit_errors_immediately(
        self,
        orchestrator,
        fake_registry,
    ):
        """Verify non-rate-limit errors are raised immediately without retry (sync)."""
        # Setup: Provider that fails with non-rate-limit error
        provider = FakeProvider(
            'groq',
            fail_count=999,
            fail_with=ValueError("Invalid model configuration"),
        )
        fake_registry.add(provider)

        # Execute & Verify
        request = LLMRequest(prompt="test prompt", provider="groq")
        with pytest.raises(ValueError, match="Invalid model configuration"):
            orchestrator.execute_with_retry_sync(
                request=request,
                excluded_providers=set(),
            )

        # Verify it didn't retry
        assert provider.sync_call_count == 1  # Only tried once
