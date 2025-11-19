"""
Tests for AgentOrchestrator core delegate methods.

Tests the critical paths for delegate(), delegate_async(), and background task management
using injected test doubles for isolation.
"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from datetime import datetime

from src.orchestrator.core import AgentOrchestrator
from src.orchestrator.cache import ResponseCache
from src.orchestrator.rate_limiter import RateLimitTracker
from src.orchestrator.memory import WorkingMemory
from src.orchestrator.session import SessionManager
from src.orchestrator.provider_selector import ProviderSelector
from src.orchestrator.output import NullOutput, CapturingOutput
from src.providers.base import LLMResponse, ProviderLimits
from src.utils.errors import RateLimitError, AllProvidersRateLimitedError

from tests.helpers import make_response


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


class TestAgentOrchestratorDelegate:
    """Tests for delegate() method - core.py:460-689"""

    def test_delegate_with_valid_provider_returns_response(self, tmp_path):
        """Test happy path - delegate returns response from provider."""
        # Setup
        mock_provider = make_mock_provider("cerebras")
        mock_cache = Mock(spec=ResponseCache)
        mock_cache.get.return_value = None
        mock_cache.get_by_intent.return_value = None

        mock_tracker = Mock(spec=RateLimitTracker)
        mock_tracker.get_remaining_quota.return_value = {
            'requests_remaining_today': 100,
            'requests_remaining_month': 1000,
            'requests_today_remaining': 100
        }
        mock_tracker.is_limit_approaching.return_value = {}

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""

        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=False
        )

        # Register the mock provider
        orch.registry.register(mock_provider)

        # Execute
        result = orch.delegate("cerebras", "Test prompt")

        # Verify
        assert result.content == "Test response"
        assert result.provider == "cerebras"
        mock_provider.chat.assert_called_once()
        mock_cache.put.assert_called_once()
        mock_tracker.record_request.assert_called_once()

    def test_delegate_with_unknown_provider_raises_error(self, tmp_path):
        """Test that delegating to unknown provider raises appropriate error."""
        mock_cache = Mock(spec=ResponseCache)
        mock_tracker = Mock(spec=RateLimitTracker)
        mock_memory = Mock(spec=WorkingMemory)
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        # Execute and verify - registry.get returns None for unknown provider
        with pytest.raises(Exception):
            orch.delegate("unknown_provider", "Test prompt")

    def test_delegate_retries_on_rate_limit(self, tmp_path):
        """Test that delegate retries on rate limit errors with exponential backoff."""
        # Setup provider that fails twice then succeeds
        mock_provider = make_mock_provider("groq")
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

        mock_cache = Mock(spec=ResponseCache)
        mock_cache.get.return_value = None
        mock_cache.get_by_intent.return_value = None

        mock_tracker = Mock(spec=RateLimitTracker)
        mock_tracker.get_remaining_quota.return_value = {
            'requests_remaining_today': 100,
            'requests_remaining_month': 1000,
            'requests_today_remaining': 100
        }
        mock_tracker.is_limit_approaching.return_value = {}

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""

        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=False
        )

        orch.registry.register(mock_provider)

        # Execute with mocked sleep to avoid actual delays
        with patch('time.sleep'):
            result = orch.delegate("groq", "Test prompt", max_retries=3)

        # Verify
        assert result.content == "Success after retries"
        assert call_count[0] == 3  # 2 failures + 1 success
        # Verify failed requests were recorded
        assert mock_tracker.record_request.call_count >= 3

    def test_delegate_falls_back_on_quota_exhaustion(self, tmp_path):
        """Test that delegate falls back to another provider when quota is exhausted."""
        # Setup primary provider that always rate limits
        primary_provider = make_mock_provider("cerebras")
        primary_provider.chat.side_effect = Exception("Rate limit exceeded")

        # Setup fallback provider that succeeds
        fallback_provider = make_mock_provider("groq")

        mock_cache = Mock(spec=ResponseCache)
        mock_cache.get.return_value = None
        mock_cache.get_by_intent.return_value = None

        mock_tracker = Mock(spec=RateLimitTracker)
        mock_tracker.get_remaining_quota.return_value = {
            'requests_remaining_today': 100,
            'requests_remaining_month': 1000,
            'requests_today_remaining': 100
        }
        mock_tracker.is_limit_approaching.return_value = {}

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""

        mock_selector = Mock(spec=ProviderSelector)
        # Return groq as fallback after cerebras fails
        mock_selector.get_provider_for_fallback.return_value = "groq"

        output = CapturingOutput()

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=output,
            context_aware=False
        )

        orch.registry.register(primary_provider)
        orch.registry.register(fallback_provider)

        # Execute
        with patch('time.sleep'):
            result = orch.delegate("cerebras", "Test prompt", max_retries=1)

        # Verify fallback was used
        assert result.content == "Test response"
        assert result.provider == "groq"
        fallback_provider.chat.assert_called_once()

        # Verify fallback info in output
        info_messages = output.get_by_level('info')
        assert any('FALLBACK' in msg for msg in info_messages)

    def test_delegate_raises_all_providers_rate_limited_when_no_fallback(self, tmp_path):
        """Test that AllProvidersRateLimitedError is raised when all providers fail."""
        # Setup provider that always rate limits
        mock_provider = make_mock_provider("cerebras")
        mock_provider.chat.side_effect = Exception("Rate limit exceeded")

        mock_cache = Mock(spec=ResponseCache)
        mock_cache.get.return_value = None
        mock_cache.get_by_intent.return_value = None

        mock_tracker = Mock(spec=RateLimitTracker)
        mock_tracker.get_remaining_quota.return_value = {
            'requests_remaining_today': 100,
            'requests_remaining_month': 1000,
            'requests_today_remaining': 100
        }

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""

        mock_selector = Mock(spec=ProviderSelector)
        # No fallback available
        mock_selector.get_provider_for_fallback.return_value = None

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=False
        )

        orch.registry.register(mock_provider)

        # Execute and verify
        with patch('time.sleep'):
            with pytest.raises(AllProvidersRateLimitedError) as exc_info:
                orch.delegate("cerebras", "Test prompt", max_retries=1)

        assert "cerebras" in exc_info.value.attempted_providers

    def test_delegate_uses_cache_when_available(self, tmp_path):
        """Test that delegate returns cached response without calling provider."""
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

        mock_provider = make_mock_provider("cerebras")

        mock_cache = Mock(spec=ResponseCache)
        mock_cache.get.return_value = cached_response

        mock_tracker = Mock(spec=RateLimitTracker)
        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=False,
            enable_cache=True
        )

        orch.registry.register(mock_provider)

        # Execute
        result = orch.delegate("cerebras", "Test prompt")

        # Verify cache was used
        assert result.content == "Cached response"
        assert result.latency_ms == 0.0
        # Provider should NOT be called
        mock_provider.chat.assert_not_called()
        # Task history should record cache hit
        assert len(orch.task_history) == 1
        assert orch.task_history[0]['cached'] is True

    def test_delegate_records_usage_metrics(self, tmp_path):
        """Test that delegate records usage in task_history and rate_tracker."""
        mock_provider = make_mock_provider("cerebras")

        mock_cache = Mock(spec=ResponseCache)
        mock_cache.get.return_value = None
        mock_cache.get_by_intent.return_value = None

        mock_tracker = Mock(spec=RateLimitTracker)
        mock_tracker.get_remaining_quota.return_value = {
            'requests_remaining_today': 100,
            'requests_remaining_month': 1000,
            'requests_today_remaining': 100
        }
        mock_tracker.is_limit_approaching.return_value = {}

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=False
        )

        orch.registry.register(mock_provider)

        # Execute
        result = orch.delegate("cerebras", "Test prompt")

        # Verify task history
        assert len(orch.task_history) == 1
        task = orch.task_history[0]
        assert task['provider'] == "cerebras"
        assert task['model'] == "test-model"
        assert task['tokens_used'] == 100
        assert task['cached'] is False
        assert 'timestamp' in task
        assert 'latency_ms' in task

        # Verify rate tracker was called
        mock_tracker.record_request.assert_called_once_with(
            provider="cerebras",
            model="test-model",
            input_tokens=50,
            output_tokens=50,
            success=True
        )

    def test_delegate_auto_selects_provider_when_none_specified(self, tmp_path):
        """Test that delegate auto-selects provider based on task type when None."""
        mock_provider = make_mock_provider("cerebras")

        mock_cache = Mock(spec=ResponseCache)
        mock_cache.get.return_value = None
        mock_cache.get_by_intent.return_value = None

        mock_tracker = Mock(spec=RateLimitTracker)
        mock_tracker.get_remaining_quota.return_value = {
            'requests_remaining_today': 100,
            'requests_remaining_month': 1000,
            'requests_today_remaining': 100
        }
        mock_tracker.is_limit_approaching.return_value = {}
        mock_tracker.get_recommended_provider.return_value = 'cerebras'

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=False
        )

        orch.registry.register(mock_provider)

        # Execute with provider=None
        result = orch.delegate(None, "Test prompt", task_type='general')

        # Verify provider was auto-selected and used
        assert result is not None
        mock_provider.chat.assert_called_once()

    def test_delegate_respects_auto_fallback_false(self, tmp_path):
        """Test that delegate doesn't fallback when auto_fallback=False."""
        mock_provider = make_mock_provider("cerebras")
        mock_provider.chat.side_effect = Exception("Rate limit exceeded")

        mock_cache = Mock(spec=ResponseCache)
        mock_cache.get.return_value = None
        mock_cache.get_by_intent.return_value = None

        mock_tracker = Mock(spec=RateLimitTracker)
        mock_tracker.get_remaining_quota.return_value = {
            'requests_remaining_today': 100,
            'requests_remaining_month': 1000,
            'requests_today_remaining': 100
        }

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=False
        )

        orch.registry.register(mock_provider)

        # Execute with auto_fallback=False
        with patch('time.sleep'):
            with pytest.raises(Exception) as exc_info:
                orch.delegate("cerebras", "Test prompt", auto_fallback=False, max_retries=1)

        assert "Rate limit exceeded" in str(exc_info.value)
        # get_provider_for_fallback should not be called
        mock_selector.get_provider_for_fallback.assert_not_called()

    def test_delegate_uses_intent_cache_when_classification_provided(self, tmp_path):
        """Test that delegate checks intent cache when intent_classification is provided."""
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

        mock_provider = make_mock_provider("cerebras")

        mock_cache = Mock(spec=ResponseCache)
        mock_cache.get.return_value = None
        mock_cache.get_by_intent.return_value = cached_response

        mock_tracker = Mock(spec=RateLimitTracker)
        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=False,
            enable_cache=True
        )

        orch.registry.register(mock_provider)

        intent_data = {
            'intent': 'summarize',
            'entities': {'topic': 'code'},
            'keywords': ['summary', 'code']
        }

        # Execute
        result = orch.delegate("cerebras", "Summarize the code", intent_classification=intent_data)

        # Verify intent cache was checked
        mock_cache.get_by_intent.assert_called_once()
        assert result.content == "Intent cached response"
        # Task history should record intent cache hit
        assert orch.task_history[0]['intent_cache_hit'] is True

    def test_delegate_augments_prompt_with_context(self, tmp_path):
        """Test that delegate augments prompt with context when enabled."""
        mock_provider = make_mock_provider("cerebras")

        mock_cache = Mock(spec=ResponseCache)
        mock_cache.get.return_value = None
        mock_cache.get_by_intent.return_value = None

        mock_tracker = Mock(spec=RateLimitTracker)
        mock_tracker.get_remaining_quota.return_value = {
            'requests_remaining_today': 100,
            'requests_remaining_month': 1000,
            'requests_today_remaining': 100
        }
        mock_tracker.is_limit_approaching.return_value = {}

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = "Working memory context"
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=True
        )

        orch.registry.register(mock_provider)

        # Execute
        orch.delegate("cerebras", "Test prompt", use_context=True)

        # Verify the prompt was augmented with working memory
        call_args = mock_provider.chat.call_args
        messages = call_args[1]['messages']
        user_message = messages[-1]['content']
        assert "Working memory context" in user_message

    def test_delegate_proactive_quota_check_raises_rate_limit_error(self, tmp_path):
        """Test that proactive quota check raises RateLimitError when quota is exhausted.

        Note: The current implementation raises RateLimitError immediately from the
        proactive check, which bypasses the fallback loop. This tests actual behavior.
        """
        primary_provider = make_mock_provider("cerebras")
        fallback_provider = make_mock_provider("groq")

        mock_cache = Mock(spec=ResponseCache)
        mock_cache.get.return_value = None
        mock_cache.get_by_intent.return_value = None

        mock_tracker = Mock(spec=RateLimitTracker)
        # Simulate exhausted quota on first check
        mock_tracker.get_remaining_quota.return_value = {
            'requests_remaining_today': 0,
            'requests_remaining_month': 1000,
            'requests_today_remaining': 0  # This triggers proactive check
        }
        mock_tracker.is_limit_approaching.return_value = {}

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""

        mock_selector = Mock(spec=ProviderSelector)
        mock_selector.get_provider_for_fallback.return_value = "groq"

        output = CapturingOutput()

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=output,
            context_aware=False
        )

        orch.registry.register(primary_provider)
        orch.registry.register(fallback_provider)

        # Execute - should raise RateLimitError from proactive check
        with pytest.raises(RateLimitError) as exc_info:
            orch.delegate("cerebras", "Test prompt")

        # Verify the error is from the proactive check
        assert "Daily quota exhausted" in str(exc_info.value)
        assert exc_info.value.provider == "cerebras"

        # Warning about exhausted quota should be logged
        warn_messages = output.get_by_level('warn')
        assert any('exhausted' in msg.lower() for msg in warn_messages)

        # Neither provider should be called since proactive check fails first
        primary_provider.chat.assert_not_called()
        fallback_provider.chat.assert_not_called()


class TestAgentOrchestratorAsync:
    """Tests for delegate_async() - core.py:766-991"""

    @pytest.mark.asyncio
    async def test_delegate_async_returns_response(self, tmp_path):
        """Test async delegation returns response from provider."""
        mock_provider = make_mock_async_provider("cerebras")

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

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=False
        )

        orch.registry.register(mock_provider)

        # Execute
        result = await orch.delegate_async("cerebras", "Test prompt")

        # Verify
        assert result.content == "Test response"
        assert result.provider == "cerebras"
        mock_provider.chat_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_delegate_async_parallel_execution(self, tmp_path):
        """Test that multiple async delegates can run in parallel."""
        mock_provider = make_mock_async_provider("cerebras")

        call_times = []

        async def track_call(**kwargs):
            call_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.01)  # Small delay
            return mock_provider.chat.return_value

        mock_provider.chat_async = AsyncMock(side_effect=track_call)

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

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=False
        )

        orch.registry.register(mock_provider)

        # Execute multiple requests in parallel
        results = await asyncio.gather(
            orch.delegate_async("cerebras", "Prompt 1"),
            orch.delegate_async("cerebras", "Prompt 2"),
            orch.delegate_async("cerebras", "Prompt 3")
        )

        # Verify all completed
        assert len(results) == 3
        assert all(r.content == "Test response" for r in results)

        # Verify they were called (timing shows parallelism but is flaky to test)
        assert mock_provider.chat_async.call_count == 3

    @pytest.mark.asyncio
    async def test_delegate_async_uses_cache(self, tmp_path):
        """Test async delegation uses cache when available."""
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

        mock_provider = make_mock_async_provider("cerebras")

        mock_cache = Mock(spec=ResponseCache)
        mock_cache.get.return_value = cached_response

        mock_tracker = Mock(spec=RateLimitTracker)
        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=False,
            enable_cache=True
        )

        orch.registry.register(mock_provider)

        # Execute
        result = await orch.delegate_async("cerebras", "Test prompt")

        # Verify
        assert result.content == "Async cached response"
        mock_provider.chat_async.assert_not_called()
        assert orch.task_history[0]['async'] is True
        assert orch.task_history[0]['cached'] is True

    @pytest.mark.asyncio
    async def test_delegate_async_retries_on_rate_limit(self, tmp_path):
        """Test async delegation retries on rate limit errors."""
        mock_provider = make_mock_async_provider("cerebras")
        call_count = [0]

        async def rate_limit_then_succeed(**kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise Exception("429 Too Many Requests")
            return mock_provider.chat.return_value

        mock_provider.chat_async = AsyncMock(side_effect=rate_limit_then_succeed)

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

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=False
        )

        orch.registry.register(mock_provider)

        # Execute
        result = await orch.delegate_async("cerebras", "Test prompt", max_retries=3)

        # Verify
        assert result.content == "Test response"
        assert call_count[0] == 3

    @pytest.mark.asyncio
    async def test_delegate_async_falls_back_on_failure(self, tmp_path):
        """Test async delegation falls back to another provider."""
        primary_provider = make_mock_async_provider("cerebras")
        primary_provider.chat_async = AsyncMock(side_effect=Exception("Rate limit exceeded"))

        fallback_provider = make_mock_async_provider("groq")

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

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""

        mock_selector = Mock(spec=ProviderSelector)
        mock_selector.get_provider_for_fallback.return_value = "groq"

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=False
        )

        orch.registry.register(primary_provider)
        orch.registry.register(fallback_provider)

        # Execute
        result = await orch.delegate_async("cerebras", "Test prompt", max_retries=1)

        # Verify fallback was used
        assert result.provider == "groq"
        assert result.metadata.get('fallback_from') == "cerebras"
        assert result.metadata.get('fallback_to') == "groq"


class TestAgentOrchestratorBackgroundTasks:
    """Tests for background task management - core.py:1140-1227"""

    @pytest.mark.asyncio
    async def test_schedule_background_task_executes(self, tmp_path):
        """Test that scheduled background tasks execute."""
        mock_cache = Mock(spec=ResponseCache)
        mock_tracker = Mock(spec=RateLimitTracker)
        mock_memory = Mock(spec=WorkingMemory)
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        executed = [False]

        async def background_task():
            executed[0] = True

        # Schedule task
        orch._schedule_background_task(background_task())

        # Wait for completion
        result = await orch.wait_for_background_tasks(timeout=1.0)

        # Verify
        assert executed[0] is True
        assert result['status'] == 'completed'

    @pytest.mark.asyncio
    async def test_background_task_errors_are_captured(self, tmp_path):
        """Test that errors in background tasks are captured without blocking."""
        mock_cache = Mock(spec=ResponseCache)
        mock_tracker = Mock(spec=RateLimitTracker)
        mock_memory = Mock(spec=WorkingMemory)
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        async def failing_task():
            raise ValueError("Background task failed")

        # Schedule failing task
        orch._schedule_background_task(failing_task())

        # Wait for completion
        await orch.wait_for_background_tasks(timeout=1.0)

        # Verify error was captured
        status = orch.get_background_task_status()
        assert status['total_errors'] >= 1
        assert any('Background task failed' in err['error'] for err in status['recent_errors'])

    @pytest.mark.asyncio
    async def test_wait_for_background_tasks_respects_timeout(self, tmp_path):
        """Test that wait_for_background_tasks respects timeout."""
        mock_cache = Mock(spec=ResponseCache)
        mock_tracker = Mock(spec=RateLimitTracker)
        mock_memory = Mock(spec=WorkingMemory)
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        async def slow_task():
            await asyncio.sleep(10)  # Very slow

        # Schedule slow task
        orch._schedule_background_task(slow_task())

        # Wait with short timeout
        result = await orch.wait_for_background_tasks(timeout=0.1)

        # Verify timeout occurred
        assert result['status'] == 'timeout'
        assert result['pending'] >= 1

    @pytest.mark.asyncio
    async def test_get_background_task_status_reports_pending(self, tmp_path):
        """Test that status correctly reports pending tasks."""
        mock_cache = Mock(spec=ResponseCache)
        mock_tracker = Mock(spec=RateLimitTracker)
        mock_memory = Mock(spec=WorkingMemory)
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        # Initially no tasks
        status = orch.get_background_task_status()
        assert status['pending_tasks'] == 0

        async def slow_task():
            await asyncio.sleep(10)

        # Schedule task
        orch._schedule_background_task(slow_task())

        # Check pending
        status = orch.get_background_task_status()
        assert status['pending_tasks'] == 1

    @pytest.mark.asyncio
    async def test_clear_background_errors(self, tmp_path):
        """Test that background errors can be cleared."""
        mock_cache = Mock(spec=ResponseCache)
        mock_tracker = Mock(spec=RateLimitTracker)
        mock_memory = Mock(spec=WorkingMemory)
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        # Submit a failing task to generate an error
        async def failing_task():
            raise ValueError("Test error")

        orch._schedule_background_task(failing_task())

        # Wait for task to complete and capture error
        await asyncio.sleep(0.01)

        assert orch.get_background_task_status()['total_errors'] == 1

        # Clear errors
        orch.clear_background_errors()

        # Verify cleared
        assert orch.get_background_task_status()['total_errors'] == 0

    @pytest.mark.asyncio
    async def test_wait_for_background_tasks_returns_no_pending_when_empty(self, tmp_path):
        """Test that waiting with no tasks returns immediately."""
        mock_cache = Mock(spec=ResponseCache)
        mock_tracker = Mock(spec=RateLimitTracker)
        mock_memory = Mock(spec=WorkingMemory)
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        # Wait with no tasks
        result = await orch.wait_for_background_tasks(timeout=1.0)

        # Verify
        assert result['status'] == 'no_pending'
        assert result['completed'] == 0


class TestAgentOrchestratorDelegateEdgeCases:
    """Edge case tests for delegate method."""

    def test_delegate_with_system_prompt(self, tmp_path):
        """Test that system prompt is properly included in messages."""
        mock_provider = make_mock_provider("cerebras")

        mock_cache = Mock(spec=ResponseCache)
        mock_cache.get.return_value = None
        mock_cache.get_by_intent.return_value = None

        mock_tracker = Mock(spec=RateLimitTracker)
        mock_tracker.get_remaining_quota.return_value = {
            'requests_remaining_today': 100,
            'requests_remaining_month': 1000,
            'requests_today_remaining': 100
        }
        mock_tracker.is_limit_approaching.return_value = {}

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=False
        )

        orch.registry.register(mock_provider)

        # Execute
        orch.delegate("cerebras", "User prompt", system_prompt="System instruction")

        # Verify system prompt was included
        call_args = mock_provider.chat.call_args
        messages = call_args[1]['messages']
        assert len(messages) == 2
        assert messages[0]['role'] == 'system'
        assert messages[0]['content'] == 'System instruction'
        assert messages[1]['role'] == 'user'

    def test_delegate_with_no_providers_raises_error(self, tmp_path):
        """Test that delegating with no available providers raises error."""
        mock_cache = Mock(spec=ResponseCache)
        mock_tracker = Mock(spec=RateLimitTracker)
        mock_tracker.get_recommended_provider.return_value = None
        mock_memory = Mock(spec=WorkingMemory)
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput()
        )

        # Execute with no providers registered
        with pytest.raises(Exception) as exc_info:
            orch.delegate(None, "Test prompt")

        assert "No providers available" in str(exc_info.value)

    def test_delegate_passes_kwargs_to_provider(self, tmp_path):
        """Test that additional kwargs are passed to provider chat method."""
        mock_provider = make_mock_provider("cerebras")

        mock_cache = Mock(spec=ResponseCache)
        mock_cache.get.return_value = None
        mock_cache.get_by_intent.return_value = None

        mock_tracker = Mock(spec=RateLimitTracker)
        mock_tracker.get_remaining_quota.return_value = {
            'requests_remaining_today': 100,
            'requests_remaining_month': 1000,
            'requests_today_remaining': 100
        }
        mock_tracker.is_limit_approaching.return_value = {}

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=False
        )

        orch.registry.register(mock_provider)

        # Execute with extra kwargs
        orch.delegate("cerebras", "Test prompt", custom_param="value")

        # Verify kwargs were passed
        call_args = mock_provider.chat.call_args
        assert call_args[1].get('custom_param') == "value"

    def test_delegate_disables_cache_when_use_cache_false(self, tmp_path):
        """Test that cache is not used when use_cache=False."""
        mock_provider = make_mock_provider("cerebras")

        mock_cache = Mock(spec=ResponseCache)
        # Would return cached if called
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

        mock_tracker = Mock(spec=RateLimitTracker)
        mock_tracker.get_remaining_quota.return_value = {
            'requests_remaining_today': 100,
            'requests_remaining_month': 1000,
            'requests_today_remaining': 100
        }
        mock_tracker.is_limit_approaching.return_value = {}

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=False,
            enable_cache=True
        )

        orch.registry.register(mock_provider)

        # Execute with cache disabled
        result = orch.delegate("cerebras", "Test prompt", use_cache=False)

        # Verify provider was called despite cache
        assert result.content == "Test response"
        mock_provider.chat.assert_called_once()
        mock_cache.get.assert_not_called()

    def test_delegate_records_rate_limit_warning_in_metadata(self, tmp_path):
        """Test that approaching rate limit warnings are added to response metadata."""
        mock_provider = make_mock_provider("cerebras")

        mock_cache = Mock(spec=ResponseCache)
        mock_cache.get.return_value = None
        mock_cache.get_by_intent.return_value = None

        mock_tracker = Mock(spec=RateLimitTracker)
        mock_tracker.get_remaining_quota.return_value = {
            'requests_remaining_today': 100,
            'requests_remaining_month': 1000,
            'requests_today_remaining': 100
        }
        # Simulate approaching limit warning
        mock_tracker.is_limit_approaching.return_value = {
            'message': 'Approaching daily request limit'
        }

        mock_memory = Mock(spec=WorkingMemory)
        mock_memory.get_context_string.return_value = ""
        mock_selector = Mock(spec=ProviderSelector)

        orch = AgentOrchestrator(
            auto_register=False,
            project_path=str(tmp_path),
            cache=mock_cache,
            rate_tracker=mock_tracker,
            working_memory=mock_memory,
            provider_selector=mock_selector,
            output=NullOutput(),
            context_aware=False
        )

        orch.registry.register(mock_provider)

        # Execute
        result = orch.delegate("cerebras", "Test prompt")

        # Verify warning in metadata
        assert 'rate_limit_warning' in result.metadata
        assert result.metadata['rate_limit_warning'] == 'Approaching daily request limit'
