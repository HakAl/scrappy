"""
Tests for DelegationManager.

Focuses on proving BEHAVIOR works, not structure.
Following CLAUDE.md guidelines:
- Tests prove features work, not just that code runs
- Edge cases covered (cache hits/misses, context augmentation, errors)
- Minimal mocking (only external dependencies: cache, llm_service, etc.)
- Tests would fail if feature breaks

After LiteLLM integration (Phase 3):
- Uses LLMServiceProtocol instead of RetryOrchestratorProtocol
- LLM calls go through LLMService.completion()
"""

import pytest
from scrappy.orchestrator.delegation import DelegationManager
from scrappy.orchestrator.provider_types import LLMResponse
from tests.helpers import MockLLMService


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
        """Should check cache before delegating to LLM service."""
        cache = MockCache()
        augmenter = MockPromptAugmenter()
        llm_service = MockLLMService()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            llm_service=llm_service,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler,
            context_aware=False
        )

        await manager.delegate_async("fast", "test prompt")

        # Should have checked cache
        assert len(cache.get_calls) > 0

    @pytest.mark.asyncio
    async def test_returns_cached_response_when_available(self):
        """Should return cached response without calling LLM service."""
        cache = MockCache()
        cached_response = LLMResponse(
            content="cached content",
            model="cached-model",
            provider="fast",
            tokens_used=50
        )
        # Pre-populate cache
        cache.set("fast", "test prompt", cached_response)

        augmenter = MockPromptAugmenter()
        llm_service = MockLLMService()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            llm_service=llm_service,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler,
            context_aware=False
        )

        response, task_record = await manager.delegate_async("fast", "test prompt")

        # Should return cached response
        assert response.content == "cached content"
        # Should NOT have called LLM service
        assert len(llm_service.completion_calls) == 0

    @pytest.mark.asyncio
    async def test_stores_response_in_cache_after_success(self):
        """Should store successful response in cache."""
        cache = MockCache()
        augmenter = MockPromptAugmenter()
        llm_service = MockLLMService()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            llm_service=llm_service,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler,
            context_aware=False
        )

        await manager.delegate_async("fast", "test prompt")

        # Should have stored in cache
        assert len(cache.set_calls) > 0

    @pytest.mark.asyncio
    async def test_skips_cache_when_use_cache_is_false(self):
        """Should not use cache when use_cache=False."""
        cache = MockCache()
        # Pre-populate cache
        cache.set("fast", "test prompt", LLMResponse(
            content="cached", model="m", provider="fast", tokens_used=10
        ))

        augmenter = MockPromptAugmenter()
        llm_service = MockLLMService()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            llm_service=llm_service,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler,
            context_aware=False
        )

        response, _ = await manager.delegate_async(
            "fast",
            "test prompt",
            use_cache=False
        )

        # Should have called LLM service (not used cache)
        assert len(llm_service.completion_calls) > 0
        # Should get fresh response, not cached
        assert response.content == "Test response"


class TestPromptAugmentation:
    """Test that prompt augmentation works correctly."""

    @pytest.mark.asyncio
    async def test_augments_prompt_when_context_aware_is_true(self):
        """Should augment prompt when context_aware=True."""
        cache = MockCache()
        augmenter = MockPromptAugmenter(augmented_suffix=" [augmented]")
        llm_service = MockLLMService()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            llm_service=llm_service,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler,
            context_aware=True  # Enable context
        )

        await manager.delegate_async("fast", "test prompt")

        # Should have called augmenter with use_context=True
        assert len(augmenter.augment_calls) > 0
        assert augmenter.augment_calls[0]['use_context'] is True

    @pytest.mark.asyncio
    async def test_skips_augmentation_when_context_aware_is_false(self):
        """Should not augment prompt when context_aware=False."""
        cache = MockCache()
        augmenter = MockPromptAugmenter()
        llm_service = MockLLMService()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            llm_service=llm_service,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler,
            context_aware=False  # Disable context
        )

        await manager.delegate_async("fast", "test prompt")

        # Should have called augmenter with use_context=False
        assert len(augmenter.augment_calls) > 0
        assert augmenter.augment_calls[0]['use_context'] is False

    @pytest.mark.asyncio
    async def test_respects_use_context_override(self):
        """use_context parameter should override context_aware setting."""
        cache = MockCache()
        augmenter = MockPromptAugmenter()
        llm_service = MockLLMService()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            llm_service=llm_service,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler,
            context_aware=True  # Default is True
        )

        # Override to False
        await manager.delegate_async("fast", "test prompt", use_context=False)

        # Should respect override
        assert augmenter.augment_calls[0]['use_context'] is False


class TestDelegationFlow:
    """Test the overall delegation coordination."""

    @pytest.mark.asyncio
    async def test_delegates_to_llm_service_for_execution(self):
        """Should delegate actual execution to LLM service."""
        cache = MockCache()
        augmenter = MockPromptAugmenter()
        llm_service = MockLLMService()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            llm_service=llm_service,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler
        )

        await manager.delegate_async("fast", "test prompt")

        # Should have called LLM service
        assert len(llm_service.completion_calls) == 1
        assert llm_service.completion_calls[0]['model'] == 'fast'

    @pytest.mark.asyncio
    async def test_concrete_model_below_min_context_fails_before_llm_call(self):
        """Direct concrete async delegation rejects insufficient context."""
        cache = MockCache()
        augmenter = MockPromptAugmenter()
        llm_service = MockLLMService()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            llm_service=llm_service,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler,
        )

        with pytest.raises(ValueError, match="below required 32768"):
            await manager.delegate_async(
                "chat",
                "test prompt",
                model="cerebras/llama-3.3-70b",
                min_context=32768,
                use_cache=False,
            )

        assert len(llm_service.completion_calls) == 0


class TestEdgeCases:
    """Test boundary conditions and edge cases."""

    @pytest.mark.asyncio
    async def test_handles_none_system_prompt(self):
        """Should handle None system_prompt correctly."""
        cache = MockCache()
        augmenter = MockPromptAugmenter()
        llm_service = MockLLMService()
        output = MockOutput()
        scheduler = MockBatchScheduler()

        manager = DelegationManager(
            llm_service=llm_service,
            cache=cache,
            output=output,
            prompt_augmenter=augmenter,
            batch_scheduler=scheduler
        )

        # Should not crash
        response, _ = await manager.delegate_async(
            "fast",
            "test prompt",
            system_prompt=None
        )

        assert response is not None

    # NOTE: Empty prompt validation removed in Phase 3.
    # LiteLLM handles validation internally.
