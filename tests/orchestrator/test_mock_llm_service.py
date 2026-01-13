"""Tests for MockLLMService."""

import pytest

from scrappy.orchestrator.mock_llm_service import (
    MockLLMService,
    is_mock_mode_enabled,
)


class TestMockModeEnabled:
    """Tests for is_mock_mode_enabled function."""

    def test_returns_false_when_not_set(self, monkeypatch):
        """Returns False when env var is not set."""
        monkeypatch.delenv("SCRAPPY_MOCK_LLM", raising=False)
        assert is_mock_mode_enabled() is False

    def test_returns_true_for_1(self, monkeypatch):
        """Returns True when set to '1'."""
        monkeypatch.setenv("SCRAPPY_MOCK_LLM", "1")
        assert is_mock_mode_enabled() is True

    def test_returns_true_for_true(self, monkeypatch):
        """Returns True when set to 'true'."""
        monkeypatch.setenv("SCRAPPY_MOCK_LLM", "true")
        assert is_mock_mode_enabled() is True

    def test_returns_true_for_yes(self, monkeypatch):
        """Returns True when set to 'yes'."""
        monkeypatch.setenv("SCRAPPY_MOCK_LLM", "yes")
        assert is_mock_mode_enabled() is True

    def test_returns_true_for_on(self, monkeypatch):
        """Returns True when set to 'on'."""
        monkeypatch.setenv("SCRAPPY_MOCK_LLM", "ON")
        assert is_mock_mode_enabled() is True

    def test_returns_false_for_invalid(self, monkeypatch):
        """Returns False for invalid values."""
        monkeypatch.setenv("SCRAPPY_MOCK_LLM", "maybe")
        assert is_mock_mode_enabled() is False


class TestMockLLMService:
    """Tests for MockLLMService class."""

    def test_is_always_configured(self):
        """Service is always configured."""
        service = MockLLMService()
        assert service.configured is True

    def test_configure_returns_true(self):
        """Configure always succeeds."""
        service = MockLLMService()
        assert service.configure() is True

    def test_completion_sync_returns_response(self):
        """completion_sync returns mock response."""
        service = MockLLMService(default_response="Test response")
        response, task_record = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "hello"}],
        )

        assert response.content == "Test response"
        assert response.provider == "mock"
        assert "mock/fast" in response.model
        assert response.tokens_used == 42  # default

    @pytest.mark.asyncio
    async def test_completion_returns_response(self):
        """async completion returns mock response."""
        service = MockLLMService(default_response="Async response")
        response, task_record = await service.completion(
            model="chat",
            messages=[{"role": "user", "content": "hello"}],
        )

        assert response.content == "Async response"
        assert response.provider == "mock"

    def test_tracks_call_count(self):
        """Service tracks call count."""
        service = MockLLMService()
        assert service.call_count == 0

        service.completion_sync(model="fast", messages=[])
        assert service.call_count == 1

        service.completion_sync(model="fast", messages=[])
        assert service.call_count == 2

    def test_records_calls(self):
        """Service records call details."""
        service = MockLLMService()
        messages = [{"role": "user", "content": "test"}]

        service.completion_sync(model="fast", messages=messages)

        assert len(service.calls) == 1
        assert service.last_call["model"] == "fast"
        assert service.last_call["messages"] == messages

    def test_reset_clears_tracking(self):
        """reset clears call tracking."""
        service = MockLLMService()
        service.completion_sync(model="fast", messages=[])
        service.completion_sync(model="fast", messages=[])

        service.reset()

        assert service.call_count == 0
        assert len(service.calls) == 0
        assert service.last_call is None

    def test_respects_env_var_response(self, monkeypatch):
        """Uses SCRAPPY_MOCK_RESPONSE env var."""
        monkeypatch.setenv("SCRAPPY_MOCK_RESPONSE", "Custom response")

        service = MockLLMService()
        response, _ = service.completion_sync(model="fast", messages=[])

        assert response.content == "Custom response"

    def test_respects_env_var_tokens(self, monkeypatch):
        """Uses SCRAPPY_MOCK_TOKENS env var."""
        monkeypatch.setenv("SCRAPPY_MOCK_TOKENS", "100")

        service = MockLLMService()
        response, _ = service.completion_sync(model="fast", messages=[])

        assert response.tokens_used == 100

    def test_task_record_matches_response(self):
        """Task record has matching data to response."""
        service = MockLLMService(default_tokens=50)
        response, task_record = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "hello"}],
        )

        assert task_record["provider"] == response.provider
        assert task_record["model"] == response.model
        assert task_record["tokens_used"] == response.tokens_used
        assert task_record["latency_ms"] == response.latency_ms

    def test_completion_direct_returns_response(self):
        """completion_direct returns mock response (fallback mode)."""
        service = MockLLMService(default_response="Direct response")
        response, task_record = service.completion_direct(
            model="gemini/gemini-2.5-flash",
            messages=[{"role": "user", "content": "hello"}],
        )

        assert response.content == "Direct response"
        assert response.provider == "mock"
        assert "gemini/gemini-2.5-flash" in response.model

    def test_stream_completion_sync_yields_chunks(self):
        """stream_completion_sync yields StreamChunk objects."""
        service = MockLLMService(default_response="Streamed response")

        chunks = list(service.stream_completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "hello"}],
        ))

        assert len(chunks) == 1
        assert chunks[0].content == "Streamed response"
        assert chunks[0].provider == "mock"
        assert chunks[0].finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_stream_completion_yields_chunks(self):
        """async stream_completion yields StreamChunk objects."""
        service = MockLLMService(default_response="Async stream")

        chunks = []
        async for chunk in service.stream_completion(
            model="chat",
            messages=[{"role": "user", "content": "hello"}],
        ):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0].content == "Async stream"
        assert chunks[0].provider == "mock"
        assert chunks[0].finish_reason == "stop"

    def test_stream_completion_sync_tracks_calls(self):
        """stream_completion_sync tracks call count."""
        service = MockLLMService()
        assert service.call_count == 0

        list(service.stream_completion_sync(model="fast", messages=[]))
        assert service.call_count == 1

    def test_completion_direct_tracks_calls(self):
        """completion_direct tracks call count."""
        service = MockLLMService()
        assert service.call_count == 0

        service.completion_direct(model="gpt-4", messages=[])
        assert service.call_count == 1

    def test_stream_completion_direct_yields_chunks(self):
        """stream_completion_direct yields StreamChunk objects for specific model."""
        service = MockLLMService(default_response="Direct stream response")

        chunks = list(service.stream_completion_direct(
            model="cerebras/qwen-3-235b-a22b-instruct-2507",
            messages=[{"role": "user", "content": "hello"}],
        ))

        assert len(chunks) == 1
        assert chunks[0].content == "Direct stream response"
        assert chunks[0].provider == "mock"
        assert chunks[0].finish_reason == "stop"

    def test_stream_completion_direct_tracks_calls(self):
        """stream_completion_direct tracks call count."""
        service = MockLLMService()
        assert service.call_count == 0

        list(service.stream_completion_direct(
            model="cerebras/qwen-3-235b-a22b-instruct-2507",
            messages=[],
        ))
        assert service.call_count == 1


class TestMockLLMServiceIntegration:
    """Integration tests verifying MockLLMService works with graph nodes."""

    def test_works_with_think_delegator(self):
        """MockLLMService integrates correctly with LiteLLMThinkDelegator."""
        from scrappy.graph.nodes.think_delegator import LiteLLMThinkDelegator

        service = MockLLMService(default_response="Mock think response")
        delegator = LiteLLMThinkDelegator(service)

        messages = [
            {"role": "system", "content": "You are a test assistant"},
            {"role": "user", "content": "Test input"},
        ]

        result = delegator.complete(messages=messages, tools=None, current_tier="fast")

        assert result is not None
        assert service.call_count == 1
        # Response content should be from the mock
        assert result.is_success
        assert "Mock think response" in result.content

    def test_works_with_think_node(self):
        """MockThinkDelegator integrates correctly with think_node."""
        from scrappy.graph.nodes.think import think_node
        from scrappy.graph.nodes.mock_think_delegator import MockThinkDelegator
        from scrappy.graph.protocols import ThinkResult
        from scrappy.graph.state import AgentState

        delegator = MockThinkDelegator(
            default_response=ThinkResult(content="Mock think response")
        )

        state = AgentState(
            input="Test input",
            task="Test task",
            original_task="Test task",
            messages=[],
            current_tier="fast",
        )

        result = think_node(state, delegator)

        assert result is not None
        assert delegator.call_count == 1
        # Response should be in the messages
        assert len(result.messages) > 0
        # The mock response should be in the assistant message
        assert any("Mock think response" in str(msg.get("content", "")) for msg in result.messages)

    def test_streaming_works_with_think_node(self):
        """MockLLMService streaming integrates with think_node."""
        service = MockLLMService(default_response="Streamed mock response")

        # Verify streaming yields proper chunks
        chunks = list(service.stream_completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        ))

        assert len(chunks) == 1
        assert chunks[0].content == "Streamed mock response"
        assert chunks[0].finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_async_streaming_works(self):
        """MockLLMService async streaming works correctly."""
        service = MockLLMService(default_response="Async streamed response")

        chunks = []
        async for chunk in service.stream_completion(
            model="chat",
            messages=[{"role": "user", "content": "test"}],
        ):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0].content == "Async streamed response"
        assert chunks[0].finish_reason == "stop"
