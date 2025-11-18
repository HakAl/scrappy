"""
Tests for DelegationManager.

Tests the extracted delegation logic including delegate(), delegate_async(),
and batch_delegate() methods with retry/fallback handling.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from src.providers.base import LLMResponse, ProviderLimits
from src.orchestrator.cache import ResponseCache
from src.orchestrator.rate_limiter import RateLimitTracker
from src.orchestrator.provider_selector import ProviderSelector
from src.orchestrator.output import NullOutput, CapturingOutput
from src.utils.errors import RateLimitError, AllProvidersRateLimitedError


def make_mock_provider(name: str = "test_provider", default_model: str = "test-model"):
    """Create a mock provider with all necessary attributes."""
    provider = Mock()
    provider.name = name
    provider.default_model = default_model
    provider.get_limits.return_value = ProviderLimits(
        requests_per_day=1000,
        requests_per_month=30000,
        tokens_per_day=1000000,
        tokens_per_minute=10000
    )

    # Default successful response
    provider.chat.return_value = LLMResponse(
        content="Test response",
        model=default_model,
        provider=name,
        tokens_used=100,
        input_tokens=50,
        output_tokens=50,
        latency_ms=100.0,
        raw_response={},
        metadata={},
        timestamp=datetime.now()
    )

    return provider


def make_mock_async_provider(name: str = "test_provider", default_model: str = "test-model"):
    """Create a mock provider with async chat method."""
    provider = make_mock_provider(name, default_model)

    async def async_chat(**kwargs):
        return provider.chat.return_value

    provider.chat_async = AsyncMock(side_effect=async_chat)
    return provider


def make_mock_registry():
    """Create a mock ProviderRegistry."""
    registry = Mock()
    registry._providers = {}

    def register(provider):
        registry._providers[provider.name] = provider

    def get(name):
        return registry._providers.get(name)

    def list_available():
        return list(registry._providers.keys())

    registry.register = register
    registry.get = get
    registry.list_available = list_available

    return registry


def make_standard_mocks():
    """Create standard mock dependencies for DelegationManager tests."""
    mock_cache = Mock(spec=ResponseCache)
    mock_cache.get.return_value = None
    mock_cache.get_by_intent.return_value = None
    mock_cache.put_async = AsyncMock()

    mock_tracker = Mock(spec=RateLimitTracker)
    mock_tracker.get_remaining_quota.return_value = {
        'requests_remaining_today': 100,
        'requests_remaining_month': 1000,
        'requests_today_remaining': 100
    }
    mock_tracker.is_limit_approaching.return_value = {}
    mock_tracker.record_request_async = AsyncMock()

    mock_selector = Mock(spec=ProviderSelector)

    return mock_cache, mock_tracker, mock_selector


class TestDelegationManagerDelegate:
    """Tests for DelegationManager.delegate() method."""

    def test_delegate_returns_response_from_provider(self):
        """Test that delegate returns response from provider on success."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("cerebras")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        result, task_record = manager.delegate(
            provider_name="cerebras",
            prompt="Test prompt"
        )

        assert result.content == "Test response"
        assert result.provider == "cerebras"
        assert task_record['cached'] is False
        mock_provider.chat.assert_called_once()
        mock_cache.put.assert_called_once()
        mock_tracker.record_request.assert_called_once()

    def test_delegate_returns_cached_response_when_available(self):
        """Test that delegate returns cached response without calling provider."""
        from src.orchestrator.delegation import DelegationManager

        cached_response = LLMResponse(
            content="Cached response",
            model="test-model",
            provider="cerebras",
            tokens_used=50,
            input_tokens=25,
            output_tokens=25,
            latency_ms=0.0,
            raw_response={},
            metadata={},
            timestamp=datetime.now()
        )

        registry = make_mock_registry()
        mock_provider = make_mock_provider("cerebras")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()
        mock_cache.get.return_value = cached_response

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        result, task_record = manager.delegate(
            provider_name="cerebras",
            prompt="Test prompt",
            use_cache=True
        )

        assert result.content == "Cached response"
        assert task_record['cached'] is True
        mock_provider.chat.assert_not_called()

    def test_delegate_retries_on_rate_limit_error(self):
        """Test that delegate retries on rate limit errors with backoff."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("groq")
        registry.register(mock_provider)

        call_count = [0]

        def rate_limit_then_succeed(**kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise Exception("429 Too Many Requests")
            return LLMResponse(
                content="Success after retries",
                model="test-model",
                provider="groq",
                tokens_used=100,
                input_tokens=50,
                output_tokens=50,
                latency_ms=100.0,
                raw_response={},
                metadata={},
                timestamp=datetime.now()
            )

        mock_provider.chat.side_effect = rate_limit_then_succeed

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        with patch('time.sleep'):
            result, _ = manager.delegate(
                provider_name="groq",
                prompt="Test prompt",
                max_retries=3
            )

        assert result.content == "Success after retries"
        assert call_count[0] == 3

    def test_delegate_falls_back_on_quota_exhaustion(self):
        """Test that delegate falls back to another provider on quota exhaustion."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        primary_provider = make_mock_provider("cerebras")
        primary_provider.chat.side_effect = Exception("Rate limit exceeded")
        fallback_provider = make_mock_provider("groq")

        registry.register(primary_provider)
        registry.register(fallback_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()
        mock_selector.get_provider_for_fallback.return_value = "groq"

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        with patch('time.sleep'):
            result, _ = manager.delegate(
                provider_name="cerebras",
                prompt="Test prompt",
                max_retries=1,
                auto_fallback=True
            )

        assert result.content == "Test response"
        assert result.provider == "groq"
        assert 'fallback_from' in result.metadata
        assert result.metadata['fallback_from'] == "cerebras"

    def test_delegate_raises_all_providers_rate_limited_when_no_fallback(self):
        """Test that AllProvidersRateLimitedError is raised when all providers fail."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("cerebras")
        mock_provider.chat.side_effect = Exception("Rate limit exceeded")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()
        mock_selector.get_provider_for_fallback.return_value = None

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        with patch('time.sleep'):
            with pytest.raises(AllProvidersRateLimitedError) as exc_info:
                manager.delegate(
                    provider_name="cerebras",
                    prompt="Test prompt",
                    max_retries=1
                )

        assert "cerebras" in exc_info.value.attempted_providers

    def test_delegate_respects_auto_fallback_false(self):
        """Test that delegate doesn't fallback when auto_fallback=False."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("cerebras")
        mock_provider.chat.side_effect = Exception("Rate limit exceeded")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        with patch('time.sleep'):
            with pytest.raises(Exception) as exc_info:
                manager.delegate(
                    provider_name="cerebras",
                    prompt="Test prompt",
                    auto_fallback=False,
                    max_retries=1
                )

        assert "Rate limit exceeded" in str(exc_info.value)
        mock_selector.get_provider_for_fallback.assert_not_called()

    def test_delegate_uses_intent_cache_when_classification_provided(self):
        """Test that delegate checks intent cache when intent_classification is provided."""
        from src.orchestrator.delegation import DelegationManager

        cached_response = LLMResponse(
            content="Intent cached response",
            model="test-model",
            provider="cerebras",
            tokens_used=50,
            input_tokens=25,
            output_tokens=25,
            latency_ms=0.0,
            raw_response={},
            metadata={},
            timestamp=datetime.now()
        )

        registry = make_mock_registry()
        mock_provider = make_mock_provider("cerebras")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()
        mock_cache.get.return_value = None
        mock_cache.get_by_intent.return_value = cached_response

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        intent_data = {
            'intent': 'summarize',
            'entities': {'topic': 'code'},
            'keywords': ['summary', 'code']
        }

        result, task_record = manager.delegate(
            provider_name="cerebras",
            prompt="Summarize the code",
            use_cache=True,
            intent_classification=intent_data
        )

        assert result.content == "Intent cached response"
        assert task_record['intent_cache_hit'] is True
        mock_cache.get_by_intent.assert_called_once()

    def test_delegate_records_usage_metrics(self):
        """Test that delegate records usage in task record and rate tracker."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("cerebras")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        result, task_record = manager.delegate(
            provider_name="cerebras",
            prompt="Test prompt"
        )

        assert task_record['provider'] == "cerebras"
        assert task_record['model'] == "test-model"
        assert task_record['tokens_used'] == 100
        assert task_record['cached'] is False
        assert 'timestamp' in task_record
        assert 'latency_ms' in task_record

        mock_tracker.record_request.assert_called_once_with(
            provider="cerebras",
            model="test-model",
            input_tokens=50,
            output_tokens=50,
            success=True
        )

    def test_delegate_with_system_prompt(self):
        """Test that system prompt is properly included in messages."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("cerebras")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        manager.delegate(
            provider_name="cerebras",
            prompt="User prompt",
            system_prompt="System instruction"
        )

        call_args = mock_provider.chat.call_args
        messages = call_args[1]['messages']
        assert len(messages) == 2
        assert messages[0]['role'] == 'system'
        assert messages[0]['content'] == 'System instruction'
        assert messages[1]['role'] == 'user'

    def test_delegate_passes_kwargs_to_provider(self):
        """Test that additional kwargs are passed to provider chat method."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("cerebras")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        manager.delegate(
            provider_name="cerebras",
            prompt="Test prompt",
            custom_param="value"
        )

        call_args = mock_provider.chat.call_args
        assert call_args[1].get('custom_param') == "value"

    def test_delegate_proactive_quota_check_triggers_fallback(self):
        """Test that proactive quota check triggers rate limit error."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("cerebras")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()
        mock_tracker.get_remaining_quota.return_value = {
            'requests_remaining_today': 0,
            'requests_remaining_month': 1000,
            'requests_today_remaining': 0
        }

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=CapturingOutput()
        )

        with pytest.raises(RateLimitError) as exc_info:
            manager.delegate(
                provider_name="cerebras",
                prompt="Test prompt"
            )

        assert "Daily quota exhausted" in str(exc_info.value)
        mock_provider.chat.assert_not_called()

    def test_delegate_records_rate_limit_warning_in_metadata(self):
        """Test that approaching rate limit warnings are added to response metadata."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("cerebras")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()
        mock_tracker.is_limit_approaching.return_value = {
            'message': 'Approaching daily request limit'
        }

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        result, _ = manager.delegate(
            provider_name="cerebras",
            prompt="Test prompt"
        )

        assert 'rate_limit_warning' in result.metadata
        assert result.metadata['rate_limit_warning'] == 'Approaching daily request limit'


class TestDelegationManagerDelegateAsync:
    """Tests for DelegationManager.delegate_async() method."""

    @pytest.mark.asyncio
    async def test_delegate_async_returns_response(self):
        """Test async delegation returns response from provider."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_async_provider("cerebras")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        result, _ = await manager.delegate_async(
            provider_name="cerebras",
            prompt="Test prompt"
        )

        assert result.content == "Test response"
        assert result.provider == "cerebras"
        mock_provider.chat_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_delegate_async_uses_cache(self):
        """Test async delegation uses cache when available."""
        from src.orchestrator.delegation import DelegationManager

        cached_response = LLMResponse(
            content="Async cached response",
            model="test-model",
            provider="cerebras",
            tokens_used=50,
            input_tokens=25,
            output_tokens=25,
            latency_ms=0.0,
            raw_response={},
            metadata={},
            timestamp=datetime.now()
        )

        registry = make_mock_registry()
        mock_provider = make_mock_async_provider("cerebras")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()
        mock_cache.get.return_value = cached_response

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        result, task_record = await manager.delegate_async(
            provider_name="cerebras",
            prompt="Test prompt",
            use_cache=True
        )

        assert result.content == "Async cached response"
        assert task_record['async'] is True
        assert task_record['cached'] is True
        mock_provider.chat_async.assert_not_called()

    @pytest.mark.asyncio
    async def test_delegate_async_retries_on_rate_limit(self):
        """Test async delegation retries on rate limit errors."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_async_provider("cerebras")
        registry.register(mock_provider)

        call_count = [0]

        async def rate_limit_then_succeed(**kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise Exception("429 Too Many Requests")
            return mock_provider.chat.return_value

        mock_provider.chat_async = AsyncMock(side_effect=rate_limit_then_succeed)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        result, _ = await manager.delegate_async(
            provider_name="cerebras",
            prompt="Test prompt",
            max_retries=3
        )

        assert result.content == "Test response"
        assert call_count[0] == 3

    @pytest.mark.asyncio
    async def test_delegate_async_falls_back_on_failure(self):
        """Test async delegation falls back to another provider."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        primary_provider = make_mock_async_provider("cerebras")
        primary_provider.chat_async = AsyncMock(side_effect=Exception("Rate limit exceeded"))
        fallback_provider = make_mock_async_provider("groq")

        registry.register(primary_provider)
        registry.register(fallback_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()
        mock_selector.get_provider_for_fallback.return_value = "groq"

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        result, _ = await manager.delegate_async(
            provider_name="cerebras",
            prompt="Test prompt",
            max_retries=1
        )

        assert result.provider == "groq"
        assert result.metadata.get('fallback_from') == "cerebras"
        assert result.metadata.get('fallback_to') == "groq"

    @pytest.mark.asyncio
    async def test_delegate_async_parallel_execution(self):
        """Test that multiple async delegates can run in parallel."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_async_provider("cerebras")
        registry.register(mock_provider)

        async def delayed_response(**kwargs):
            await asyncio.sleep(0.01)
            return mock_provider.chat.return_value

        mock_provider.chat_async = AsyncMock(side_effect=delayed_response)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        results = await asyncio.gather(
            manager.delegate_async("cerebras", "Prompt 1"),
            manager.delegate_async("cerebras", "Prompt 2"),
            manager.delegate_async("cerebras", "Prompt 3")
        )

        assert len(results) == 3
        assert all(r[0].content == "Test response" for r in results)
        assert mock_provider.chat_async.call_count == 3


class TestDelegationManagerBatchDelegate:
    """Tests for DelegationManager.delegate_batch() method."""

    def test_batch_delegate_processes_all_tasks(self):
        """Test that batch_delegate processes all tasks in order."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("groq")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        tasks = [
            {'prompt': 'Task 1'},
            {'prompt': 'Task 2'},
            {'prompt': 'Task 3'}
        ]

        results = manager.delegate_batch(tasks, provider_name="groq")

        assert len(results) == 3
        assert mock_provider.chat.call_count == 3

    def test_batch_delegate_passes_system_prompt(self):
        """Test that batch_delegate passes system_prompt for each task."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("groq")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        tasks = [
            {'prompt': 'Task 1', 'system_prompt': 'System 1'},
            {'prompt': 'Task 2', 'system_prompt': 'System 2'}
        ]

        results = manager.delegate_batch(tasks, provider_name="groq")

        assert len(results) == 2

        # Verify system prompts were passed
        calls = mock_provider.chat.call_args_list
        assert calls[0][1]['messages'][0]['content'] == 'System 1'
        assert calls[1][1]['messages'][0]['content'] == 'System 2'

    def test_batch_delegate_passes_kwargs(self):
        """Test that batch_delegate passes kwargs for each task."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("groq")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        tasks = [
            {'prompt': 'Task 1', 'kwargs': {'temperature': 0.5}},
            {'prompt': 'Task 2', 'kwargs': {'temperature': 0.9}}
        ]

        results = manager.delegate_batch(tasks, provider_name="groq")

        assert len(results) == 2

        # Verify kwargs were passed
        calls = mock_provider.chat.call_args_list
        assert calls[0][1]['temperature'] == 0.5
        assert calls[1][1]['temperature'] == 0.9


class TestDelegationManagerPromptAugmentation:
    """Tests for prompt augmentation with context and working memory."""

    def test_delegate_augments_prompt_with_context(self):
        """Test that delegate augments prompt with codebase context."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("cerebras")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()

        # Mock context
        mock_context = Mock()
        mock_context.is_explored.return_value = True
        mock_context.augment_prompt.return_value = "Augmented: Test prompt"

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput(),
            context=mock_context,
            context_aware=True
        )

        manager.delegate(
            provider_name="cerebras",
            prompt="Test prompt",
            use_context=True
        )

        call_args = mock_provider.chat.call_args
        messages = call_args[1]['messages']
        assert "Augmented" in messages[-1]['content']

    def test_delegate_augments_prompt_with_working_memory(self):
        """Test that delegate augments prompt with working memory."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("cerebras")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()

        # Mock context
        mock_context = Mock()
        mock_context.is_explored.return_value = False

        # Working memory getter
        def get_working_memory():
            return "Working memory context"

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput(),
            context=mock_context,
            context_aware=True,
            get_working_memory_context=get_working_memory
        )

        manager.delegate(
            provider_name="cerebras",
            prompt="Test prompt",
            use_context=True
        )

        call_args = mock_provider.chat.call_args
        messages = call_args[1]['messages']
        assert "Working memory context" in messages[-1]['content']

    def test_delegate_skips_context_augmentation_when_disabled(self):
        """Test that delegate skips context augmentation when use_context=False."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("cerebras")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()

        mock_context = Mock()
        mock_context.is_explored.return_value = True
        mock_context.augment_prompt.return_value = "Augmented prompt"

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput(),
            context=mock_context,
            context_aware=True
        )

        manager.delegate(
            provider_name="cerebras",
            prompt="Original prompt",
            use_context=False
        )

        call_args = mock_provider.chat.call_args
        messages = call_args[1]['messages']
        # Original prompt should be passed without augmentation
        assert messages[-1]['content'] == "Original prompt"
        mock_context.augment_prompt.assert_not_called()


class TestDelegationManagerCacheControl:
    """Tests for cache control behavior."""

    def test_delegate_stores_response_in_cache(self):
        """Test that successful response is stored in cache."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("cerebras")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        manager.delegate(
            provider_name="cerebras",
            prompt="Test prompt",
            use_cache=True
        )

        mock_cache.put.assert_called_once()

    def test_delegate_stores_intent_cache_when_classification_provided(self):
        """Test that response is stored in intent cache when classification provided."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("cerebras")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        intent_data = {
            'intent': 'summarize',
            'entities': {'topic': 'code'},
            'keywords': ['summary']
        }

        manager.delegate(
            provider_name="cerebras",
            prompt="Test prompt",
            use_cache=True,
            intent_classification=intent_data
        )

        mock_cache.put.assert_called_once()
        mock_cache.put_by_intent.assert_called_once()

    def test_delegate_skips_cache_when_disabled(self):
        """Test that cache is not used when use_cache=False."""
        from src.orchestrator.delegation import DelegationManager

        registry = make_mock_registry()
        mock_provider = make_mock_provider("cerebras")
        registry.register(mock_provider)

        mock_cache, mock_tracker, mock_selector = make_standard_mocks()
        mock_cache.get.return_value = LLMResponse(
            content="Cached",
            model="test",
            provider="cerebras",
            tokens_used=10,
            input_tokens=5,
            output_tokens=5,
            latency_ms=0.0,
            raw_response={},
            metadata={},
            timestamp=datetime.now()
        )

        manager = DelegationManager(
            registry=registry,
            cache=mock_cache,
            rate_tracker=mock_tracker,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        result, _ = manager.delegate(
            provider_name="cerebras",
            prompt="Test prompt",
            use_cache=False
        )

        assert result.content == "Test response"
        mock_provider.chat.assert_called_once()
        mock_cache.get.assert_not_called()
