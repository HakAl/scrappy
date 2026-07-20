"""
Additional tests for AgentOrchestrator to improve coverage.

Focuses on methods not covered by existing test files.
"""

import pytest
from unittest.mock import Mock, patch

from scrappy.orchestrator.core import AgentOrchestrator
from scrappy.orchestrator.output import NullOutput
from scrappy.orchestrator.memory import WorkingMemory
from scrappy.orchestrator.provider_types import LLMResponse
from scrappy.infrastructure.exceptions import (
    RateLimitError,
)


class MockDelegationManager:
    """Mock delegation manager for tests."""

    def __init__(self):
        self.delegate_calls = []
        self.delegate_response = LLMResponse(
            content="mock response",
            model="mock-model",
            provider="mock",
            tokens_used=10
        )
        self.delegate_task_record = {"provider": "mock", "model": "mock-model", "tokens_used": 10}

    def delegate(self, **kwargs):
        self.delegate_calls.append(kwargs)
        return self.delegate_response, self.delegate_task_record

    async def delegate_async(self, **kwargs):
        self.delegate_calls.append(kwargs)
        return self.delegate_response, self.delegate_task_record

    async def stream_delegate(self, **kwargs):
        from scrappy.orchestrator.types import StreamChunk
        yield StreamChunk(content="streamed ")
        yield StreamChunk(content="response", finish_reason="stop")

    def delegate_structured_sync(self, **kwargs):
        return {"result": "structured"}

    def delegate_batch(self, tasks, provider_name):
        return [self.delegate_response for _ in tasks]

    async def batch_delegate_async(self, tasks, provider_name, max_concurrent):
        return [self.delegate_response for _ in tasks]


class MockRegistry:
    """Mock provider registry."""

    def __init__(self):
        self.providers = {"mock": Mock()}

    def list_available(self):
        return ["mock"]

    def list_all(self):
        return ["mock"]

    def get(self, name):
        return self.providers.get(name, Mock())

    def get_provider_info(self):
        return {"mock": {"status": "available"}}


class MockModelSelector:
    """Mock model selection service."""

    def __init__(self):
        self.rate_limited_models = set()
        self.models = ["mock/model-id", "mock/fallback-model"]
        self.default_type = None

    def set_default_type(self, selection_type):
        self.default_type = selection_type

    def get_default_type(self):
        return self.default_type

    def select(self, selection_type, min_context=0, session_preferred=None, exclude=None):
        excluded = exclude or set()
        if session_preferred and session_preferred not in self.rate_limited_models:
            return session_preferred
        for model in self.models:
            if model not in self.rate_limited_models and model not in excluded:
                return model
        from scrappy.orchestrator.model_selection import AllModelsRateLimitedError
        raise AllModelsRateLimitedError("all models unavailable")

    def get_models_for_type(self, selection_type):
        return list(self.models)

    def mark_unhealthy(self, model_id, kind, retry_after=None):
        self.rate_limited_models.add(model_id)

    def is_available(self, model_id):
        return model_id not in self.rate_limited_models


class MockUsageReporter:
    """Mock usage reporter."""

    def __init__(self):
        self.records = []

    def record(self, **kwargs):
        self.records.append(kwargs)

    def get_usage_report(self):
        return {"total_requests": len(self.records)}

    def get_cache_stats(self):
        return {"hits": 0, "misses": 0}

    def clear_cache(self):
        pass


class MockStatusReporter:
    """Mock status reporter."""

    def update_quality_mode(self, mode):
        pass

    def print_status(self):
        pass

    def get_selection_info(self):
        return {"info": "mock"}


class MockContextManager:
    """Mock context manager."""

    def __init__(self):
        self.context = Mock()
        self.context.get_status.return_value = {"status": "ok"}

    def explore_project(self, force=False):
        return {"explored": True}

    def auto_explore(self):
        pass


class MockSessionManager:
    """Mock session manager."""

    def save_session(self, working_memory, task_history, created_at, conversation_history):
        return "/path/to/session"

    def load_session(self):
        return {
            "status": "loaded",
            "working_memory": WorkingMemory(),
            "task_history": [],
            "saved_at": "2024-01-01",
            "files_restored": 0,
            "searches_restored": 0,
            "git_ops_restored": 0,
            "discoveries_restored": 0,
            "tasks_restored": 0,
            "conversation_history": [],
        }

    def clear_session(self):
        pass


class MockTaskExecutor:
    """Mock task executor."""

    def plan(self, task, context, max_steps):
        return [{"step": 1, "action": "do something"}]

    def reason(self, question, context, evidence):
        return {"conclusion": "reasoned answer"}

    def synthesize(self, results, prompt):
        return "synthesized result"


class MockBackgroundManager:
    """Mock background task manager."""

    def submit_background_task(self, coro):
        return "task-123"

    async def wait_for_background_tasks(self, timeout):
        return {"completed": True}

    def get_task_status(self):
        return {"pending": 0, "errors": []}

    def clear_background_errors(self):
        pass

    def cancel_task(self, task_id):
        return True


class MockRateTracker:
    """Mock rate limit tracker."""

    def is_rate_limited(self, provider_name, registry):
        return False

    def get_rate_limit_status_extended(self, registry):
        return {"status": "ok"}

    def get_remaining_quota_for_provider(self, provider_name, registry, model):
        return {"remaining": 100}

    def check_all_warnings(self, registry):
        return []

    def reset_rate_tracking(self, provider_name):
        pass


@pytest.fixture
def mock_orchestrator(tmp_path):
    """Create an orchestrator with all dependencies mocked."""
    return AgentOrchestrator(
        project_path=str(tmp_path),
        output=NullOutput(),
        registry=MockRegistry(),
        cache=Mock(),
        rate_tracker=MockRateTracker(),
        working_memory=WorkingMemory(),
        session_manager=MockSessionManager(),
        usage_reporter=MockUsageReporter(),
        status_reporter=MockStatusReporter(),
        task_executor=MockTaskExecutor(),
        context_manager=MockContextManager(),
        delegation_manager=MockDelegationManager(),
        background_manager=MockBackgroundManager(),
        model_selector=MockModelSelector(),
    )


class TestInitialize:
    """Tests for the initialize() method."""

    def test_initialize_auto_registers_providers(self, mock_orchestrator):
        """Initialize with auto_register=True sets up brain."""
        result = mock_orchestrator.initialize(auto_register=True)
        assert result is mock_orchestrator  # Returns self for chaining
        assert mock_orchestrator._brain_name == "instruct"

    def test_initialize_without_auto_register(self, mock_orchestrator):
        """Initialize with auto_register=False skips provider setup."""
        mock_orchestrator._brain_name = None
        result = mock_orchestrator.initialize(auto_register=False)
        assert result is mock_orchestrator
        # Brain should not be set when auto_register=False
        assert mock_orchestrator._brain_name is None


class TestBrainProperty:
    """Tests for brain property getter/setter."""

    def test_brain_getter_returns_name(self, mock_orchestrator):
        """brain property returns the brain name."""
        mock_orchestrator._brain_name = "test-brain"
        assert mock_orchestrator.brain == "test-brain"

    def test_brain_setter_accepts_valid_provider(self, mock_orchestrator):
        """brain setter accepts a valid provider."""
        mock_orchestrator.brain = "mock"
        assert mock_orchestrator._brain_name == "mock"


class TestStatus:
    """Tests for status() method."""

    def test_status_returns_comprehensive_info(self, mock_orchestrator):
        """status() returns comprehensive orchestrator state."""
        mock_orchestrator._brain_name = "test-brain"

        with patch("scrappy.orchestrator.litellm_config.get_configured_models") as mock_models, \
             patch("scrappy.orchestrator.litellm_config.get_available_groups") as mock_groups, \
             patch("scrappy.orchestrator.core.create_api_key_service"):
            mock_models.return_value = []
            mock_groups.return_value = ["fast", "quality"]

            status = mock_orchestrator.status()

            assert "model_groups" in status
            assert "orchestrator_brain" in status
            assert status["orchestrator_brain"] == "test-brain"
            assert status["quality_mode"] is True


class TestContextMethods:
    """Tests for context-related methods."""

    def test_explore_project_delegates(self, mock_orchestrator):
        """explore_project delegates to context manager."""
        result = mock_orchestrator.explore_project(force=True)
        assert result == {"explored": True}

    def test_get_context_status_delegates(self, mock_orchestrator):
        """get_context_status delegates to context."""
        result = mock_orchestrator.get_context_status()
        assert result == {"status": "ok"}

    def test_context_property_returns_context(self, mock_orchestrator):
        """context property returns the underlying context."""
        ctx = mock_orchestrator.context
        assert ctx is mock_orchestrator.context_manager.context


class TestSessionMethods:
    """Tests for session management methods."""

    def test_save_session_delegates(self, mock_orchestrator):
        """save_session delegates to session manager."""
        result = mock_orchestrator.save_session(conversation_history=[])
        assert result == "/path/to/session"

    def test_load_session_restores_state(self, mock_orchestrator):
        """load_session restores working memory and task history."""
        result = mock_orchestrator.load_session()
        assert result["status"] == "loaded"


class TestTaskExecutionMethods:
    """Tests for task execution methods."""

    def test_plan_delegates(self, mock_orchestrator):
        """plan() delegates to task executor."""
        result = mock_orchestrator.plan("test task", context="ctx", max_steps=5)
        assert len(result) == 1

    def test_reason_delegates(self, mock_orchestrator):
        """reason() delegates to task executor."""
        result = mock_orchestrator.reason("why?", context="ctx", evidence=["a"])
        assert result["conclusion"] == "reasoned answer"

    def test_synthesize_delegates(self, mock_orchestrator):
        """synthesize() delegates to task executor."""
        result = mock_orchestrator.synthesize([], "synthesize prompt")
        assert result == "synthesized result"


class TestProviderSelection:
    """Tests for provider selection methods."""

    def test_is_rate_limited_delegates(self, mock_orchestrator):
        """is_rate_limited delegates to rate tracker."""
        result = mock_orchestrator.is_rate_limited("mock")
        assert result is False


class TestDelegate:
    """Tests for delegate() method."""

    def test_delegate_uses_model_selector(self, mock_orchestrator):
        """delegate() uses model selector for model selection."""
        response = mock_orchestrator.delegate(prompt="test prompt")
        assert response.content == "mock response"

    def test_delegate_respects_explicit_model(self, mock_orchestrator):
        """delegate() uses explicit model when provided."""
        response = mock_orchestrator.delegate(
            prompt="test",
            model="explicit/model-id"
        )
        assert response.content == "mock response"
        # Verify the explicit model was passed through
        calls = mock_orchestrator.delegation_manager.delegate_calls
        assert any(c.get("model") == "explicit/model-id" for c in calls)

    def test_delegate_records_task_completion(self, mock_orchestrator):
        """delegate() records task completion in usage reporter."""
        mock_orchestrator.delegate(prompt="test")
        assert len(mock_orchestrator.usage_reporter.records) == 1

    def test_delegate_fallback_on_rate_limit(self, mock_orchestrator):
        """delegate() tries fallback on rate limit."""
        call_count = 0
        def rate_limit_once(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RateLimitError("rate limited", provider_name="mock")
            return LLMResponse(
                content="success",
                model="fallback-model",
                provider="mock",
                tokens_used=10
            ), {"provider": "mock"}

        mock_orchestrator.delegation_manager.delegate = rate_limit_once
        response = mock_orchestrator.delegate(prompt="test", auto_fallback=True)
        assert response.content == "success"


class TestDelegateStructured:
    """Tests for delegate_structured() method."""

    def test_delegate_structured_delegates(self, mock_orchestrator):
        """delegate_structured delegates to delegation manager."""
        from pydantic import BaseModel

        class TestModel(BaseModel):
            result: str

        result = mock_orchestrator.delegate_structured(
            provider_name="mock",
            prompt="test",
            response_model=TestModel
        )
        assert result == {"result": "structured"}


class TestBatchDelegate:
    """Tests for batch_delegate() method."""

    def test_batch_delegate_processes_multiple_tasks(self, mock_orchestrator):
        """batch_delegate processes multiple tasks."""
        tasks = [{"prompt": "task1"}, {"prompt": "task2"}]
        results = mock_orchestrator.batch_delegate(tasks, provider_name="mock")
        assert len(results) == 2


class TestAsyncMethods:
    """Tests for async delegation methods."""

    @pytest.mark.asyncio
    async def test_delegate_async_returns_response(self, mock_orchestrator):
        """delegate_async returns response from delegation manager."""
        response = await mock_orchestrator.delegate_async(
            provider_name="mock",
            prompt="test"
        )
        assert response.content == "mock response"

    @pytest.mark.asyncio
    async def test_stream_delegate_yields_chunks(self, mock_orchestrator):
        """stream_delegate yields stream chunks."""
        chunks = []
        async for chunk in mock_orchestrator.stream_delegate(prompt="test"):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0].content == "streamed "
        assert chunks[1].finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_batch_delegate_async_processes_tasks(self, mock_orchestrator):
        """batch_delegate_async processes multiple tasks."""
        tasks = [{"prompt": "task1"}, {"prompt": "task2"}]
        results = await mock_orchestrator.batch_delegate_async(
            tasks, provider_name="mock", max_concurrent=5
        )
        assert len(results) == 2


class TestUsageAndCacheMethods:
    """Tests for usage reporting and cache methods."""

    def test_get_usage_report_delegates(self, mock_orchestrator):
        """get_usage_report delegates to usage reporter."""
        result = mock_orchestrator.get_usage_report()
        assert "total_requests" in result

    def test_get_cache_stats_delegates(self, mock_orchestrator):
        """get_cache_stats delegates to usage reporter."""
        result = mock_orchestrator.get_cache_stats()
        assert "hits" in result

    def test_toggle_cache_toggles_state(self, mock_orchestrator):
        """toggle_cache toggles caching state."""
        initial = mock_orchestrator.caching_enabled
        result = mock_orchestrator.toggle_cache()
        assert result != initial
        assert mock_orchestrator.caching_enabled == result


class TestBackgroundTaskMethods:
    """Tests for background task methods."""

    def test_schedule_background_task_returns_id(self, mock_orchestrator):
        """_schedule_background_task returns task ID."""
        async def dummy_coro():
            pass
        task_id = mock_orchestrator._schedule_background_task(dummy_coro())
        assert task_id == "task-123"

    @pytest.mark.asyncio
    async def test_wait_for_background_tasks(self, mock_orchestrator):
        """wait_for_background_tasks waits for completion."""
        result = await mock_orchestrator.wait_for_background_tasks(timeout=5.0)
        assert result["completed"] is True

    def test_get_background_task_status(self, mock_orchestrator):
        """get_background_task_status returns status."""
        result = mock_orchestrator.get_background_task_status()
        assert "pending" in result

    def test_cancel_background_task(self, mock_orchestrator):
        """cancel_background_task delegates to manager."""
        result = mock_orchestrator.cancel_background_task("task-123")
        assert result is True


class TestRateLimitMethods:
    """Tests for rate limit methods."""

    def test_get_rate_limit_status_delegates(self, mock_orchestrator):
        """get_rate_limit_status delegates to rate tracker."""
        result = mock_orchestrator.get_rate_limit_status()
        assert result == {"status": "ok"}

    def test_get_remaining_quota_delegates(self, mock_orchestrator):
        """get_remaining_quota delegates to rate tracker."""
        result = mock_orchestrator.get_remaining_quota("mock")
        assert result["remaining"] == 100

    def test_check_rate_limit_warnings_delegates(self, mock_orchestrator):
        """check_rate_limit_warnings delegates to rate tracker."""
        result = mock_orchestrator.check_rate_limit_warnings()
        assert result == []
