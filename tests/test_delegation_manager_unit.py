"""
Tests for DelegationManager.

Focuses on proving BEHAVIOR works, not structure.
Following CLAUDE.md guidelines:
- Tests prove features work, not just that code runs
- Edge cases covered (cache hits/misses, context augmentation, errors)
- Minimal mocking (only external dependencies: cache, retry orchestrator, etc.)
- Tests would fail if feature breaks

Note: These are UNIT tests testing the delegation coordination flow.
Integration tests with real providers are in other test files.
"""

import pytest
from unittest.mock import Mock
from src.orchestrator.delegation import DelegationManager
from src.providers.base import LLMResponse


# Test Doubles

class MockCache:
    """Test double for CacheProtocol."""

    def __init__(self):
        self._cache = {}
        self.get_calls = []
        self.set_calls = []

    def get(self, provider, prompt, model=None, system_prompt=None, max_tokens=None, temperature=None):
        self.get_calls.append({
            'provider': provider,
            'prompt': prompt,
            'model': model
        })
        key = f"{provider}:{prompt}:{model}"
        return self._cache.get(key)

    def get_by_intent(self, intent, entities):
        return None  # Simplified for tests

    def set(self, provider, prompt, response, model=None, system_prompt=None, max_tokens=None, temperature=None):
        self.set_calls.append({
            'provider': provider,
            'prompt': prompt,
            'model': model
        })
        key = f"{provider}:{prompt}:{model}"
        self._cache[key] = response

    def put(self, response, prompt, model=None, system_prompt=None, max_tokens=None, temperature=None):
        """Alias for set() - implementation uses put()."""
        self.set_calls.append({
            'provider': response.provider,
            'prompt': prompt,
            'model': model
        })
        key = f"{response.provider}:{prompt}:{model}"
        self._cache[key] = response

    def put_by_intent(self, response, intent, entities, keywords):
        """Store by intent for semantic caching."""
        pass  # Simplified for tests


class MockPromptAugmenter:
    """Test double for PromptAugmenterProtocol."""

    def __init__(self, augmented_suffix=" [augmented]"):
        self.augmented_suffix = augmented_suffix
        self.augment_calls = []

    def augment(self, prompt, use_context=False):
        self.augment_calls.append({
            'prompt': prompt,
            'use_context': use_context
        })
        if use_context:
            return prompt + self.augmented_suffix
        return prompt


class MockRetryOrchestrator:
    """Test double for RetryOrchestratorProtocol."""

    def __init__(self, response=None):
        self.response = response or LLMResponse(
            content="test response",
            model="test-model",
            provider="test-provider",
            tokens_used=100
        )
        self.execute_calls = []

    async def execute_with_retry(
        self,
        request,
        excluded_providers=None,
        max_retries=3,
        auto_fallback=True
    ):
        self.execute_calls.append({
            'provider': getattr(request, 'provider', getattr(request, 'provider_name', 'unknown')),
            'prompt': getattr(request, 'prompt', ''),
            'max_retries': max_retries,
            'auto_fallback': auto_fallback,
            'excluded_providers': excluded_providers or set()
        })
        # Return tuple: (response, metadata)
        # Match all fields expected by delegation.py:289-305
        return (self.response, {
            'retries': 0,
            'provider': 'test-provider',
            'model': 'test-model',
            'tokens_used': 100,
            'latency_ms': 50.0,
            'fallback': False,
            'attempts': 1,
            'cache_hit': False
        })


class MockOutput:
    """Test double for OutputInterfaceProtocol."""

    def __init__(self):
        self.debug_messages = []
        self.info_messages = []
        self.warn_messages = []

    def debug(self, msg):
        self.debug_messages.append(msg)

    def info(self, msg):
        self.info_messages.append(msg)

    def warn(self, msg):
        self.warn_messages.append(msg)


class MockBatchScheduler:
    """Test double for BatchSchedulerProtocol."""

    async def schedule_batch_async(self, requests, max_concurrent=5):
        return []


# Tests

class TestCachingBehavior:
    """Test that caching actually works to avoid redundant API calls."""

    @pytest.mark.asyncio
    async def test_checks_cache_before_executing_request(self):
        """Should check cache before delegating to retry orchestrator."""
        cache = MockCache()
        augmenter = MockPromptAugmenter()
        retry_orch = MockRetryOrchestrator()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            retry_orchestrator=retry_orch,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler,
            context_aware=False
        )

        await manager.delegate_async("cerebras", "test prompt")

        # Should have checked cache
        assert len(cache.get_calls) > 0

    @pytest.mark.asyncio
    async def test_returns_cached_response_when_available(self):
        """Should return cached response without calling retry orchestrator."""
        cache = MockCache()
        cached_response = LLMResponse(
            content="cached content",
            model="cached-model",
            provider="cerebras",
            tokens_used=50
        )
        # Pre-populate cache
        cache.set("cerebras", "test prompt", cached_response)

        augmenter = MockPromptAugmenter()
        retry_orch = MockRetryOrchestrator()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            retry_orchestrator=retry_orch,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler,
            context_aware=False
        )

        response, task_record = await manager.delegate_async("cerebras", "test prompt")

        # Should return cached response
        assert response.content == "cached content"
        # Should NOT have called retry orchestrator
        assert len(retry_orch.execute_calls) == 0

    @pytest.mark.asyncio
    async def test_stores_response_in_cache_after_success(self):
        """Should store successful response in cache."""
        cache = MockCache()
        augmenter = MockPromptAugmenter()
        retry_orch = MockRetryOrchestrator()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            retry_orchestrator=retry_orch,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler,
            context_aware=False
        )

        await manager.delegate_async("cerebras", "test prompt")

        # Should have stored in cache
        assert len(cache.set_calls) > 0

    @pytest.mark.asyncio
    async def test_skips_cache_when_use_cache_is_false(self):
        """Should not use cache when use_cache=False."""
        cache = MockCache()
        # Pre-populate cache
        cache.set("cerebras", "test prompt", LLMResponse(
            content="cached", model="m", provider="cerebras", tokens_used=10
        ))

        augmenter = MockPromptAugmenter()
        retry_orch = MockRetryOrchestrator()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            retry_orchestrator=retry_orch,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler,
            context_aware=False
        )

        response, _ = await manager.delegate_async(
            "cerebras",
            "test prompt",
            use_cache=False
        )

        # Should have called retry orchestrator (not used cache)
        assert len(retry_orch.execute_calls) > 0
        # Should get fresh response, not cached
        assert response.content == "test response"


class TestPromptAugmentation:
    """Test that prompt augmentation works correctly."""

    @pytest.mark.asyncio
    async def test_augments_prompt_when_context_aware_is_true(self):
        """Should augment prompt when context_aware=True."""
        cache = MockCache()
        augmenter = MockPromptAugmenter(augmented_suffix=" [augmented]")
        retry_orch = MockRetryOrchestrator()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            retry_orchestrator=retry_orch,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler,
            context_aware=True  # Enable context
        )

        await manager.delegate_async("cerebras", "test prompt")

        # Should have called augmenter with use_context=True
        assert len(augmenter.augment_calls) > 0
        assert augmenter.augment_calls[0]['use_context'] is True

    @pytest.mark.asyncio
    async def test_skips_augmentation_when_context_aware_is_false(self):
        """Should not augment prompt when context_aware=False."""
        cache = MockCache()
        augmenter = MockPromptAugmenter()
        retry_orch = MockRetryOrchestrator()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            retry_orchestrator=retry_orch,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler,
            context_aware=False  # Disable context
        )

        await manager.delegate_async("cerebras", "test prompt")

        # Should have called augmenter with use_context=False
        assert len(augmenter.augment_calls) > 0
        assert augmenter.augment_calls[0]['use_context'] is False

    @pytest.mark.asyncio
    async def test_respects_use_context_override(self):
        """use_context parameter should override context_aware setting."""
        cache = MockCache()
        augmenter = MockPromptAugmenter()
        retry_orch = MockRetryOrchestrator()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            retry_orchestrator=retry_orch,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler,
            context_aware=True  # Default is True
        )

        # Override to False
        await manager.delegate_async("cerebras", "test prompt", use_context=False)

        # Should respect override
        assert augmenter.augment_calls[0]['use_context'] is False


class TestDelegationFlow:
    """Test the overall delegation coordination."""

    @pytest.mark.asyncio
    async def test_delegates_to_retry_orchestrator_for_execution(self):
        """Should delegate actual execution to retry orchestrator."""
        cache = MockCache()
        augmenter = MockPromptAugmenter()
        retry_orch = MockRetryOrchestrator()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            retry_orchestrator=retry_orch,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler
        )

        await manager.delegate_async("cerebras", "test prompt")

        # Should have called retry orchestrator
        assert len(retry_orch.execute_calls) == 1
        assert retry_orch.execute_calls[0]['provider'] == 'cerebras'

    @pytest.mark.asyncio
    async def test_returns_response_and_task_record(self):
        """Should return both response and task record."""
        cache = MockCache()
        augmenter = MockPromptAugmenter()
        retry_orch = MockRetryOrchestrator()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            retry_orchestrator=retry_orch,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler
        )

        response, task_record = await manager.delegate_async("cerebras", "test prompt")

        assert isinstance(response, LLMResponse)
        assert isinstance(task_record, dict)
        assert 'provider' in task_record


class TestEdgeCases:
    """Test boundary conditions and edge cases."""

    @pytest.mark.asyncio
    async def test_handles_none_system_prompt(self):
        """Should handle None system_prompt correctly."""
        cache = MockCache()
        augmenter = MockPromptAugmenter()
        retry_orch = MockRetryOrchestrator()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            retry_orchestrator=retry_orch,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler
        )

        # Should not crash
        response, _ = await manager.delegate_async(
            "cerebras",
            "test prompt",
            system_prompt=None
        )

        assert response is not None

    @pytest.mark.asyncio
    async def test_rejects_empty_prompt(self):
        """Should reject empty prompt with ValueError."""
        cache = MockCache()
        augmenter = MockPromptAugmenter()
        retry_orch = MockRetryOrchestrator()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            retry_orchestrator=retry_orch,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler
        )

        # Should raise ValueError for empty prompt
        with pytest.raises(ValueError, match="prompt cannot be empty"):
            await manager.delegate_async("cerebras", "")


class TestSyncWrapper:
    """Test synchronous delegate() wrapper."""

