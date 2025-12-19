"""
Tests for DelegationManager messages parameter.

Tests that the messages parameter bypasses prompt augmentation and
is passed directly to the LLM service.
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime

from scrappy.orchestrator.delegation import DelegationManager
from scrappy.providers.base import LLMResponse


class MockLLMService:
    """Mock LLM service for testing."""

    def __init__(self, response_content="Test response"):
        self.response_content = response_content
        self.last_call_kwargs = None

    def completion_sync(self, **kwargs):
        self.last_call_kwargs = kwargs
        response = LLMResponse(
            content=self.response_content,
            model=kwargs.get("model", "test-model"),
            provider="test-provider",
            tokens_used=10,
        )
        task_record = {
            "provider": "test-provider",
            "model": "test-model",
            "tokens_used": 10,
            "latency_ms": 100,
        }
        return response, task_record


class MockCache:
    """Mock cache that never hits."""

    def get(self, *args, **kwargs):
        return None

    def get_by_intent(self, *args, **kwargs):
        return None

    def put(self, *args, **kwargs):
        pass

    def put_by_intent(self, *args, **kwargs):
        pass


class MockAugmenter:
    """Mock augmenter that tracks calls."""

    def __init__(self):
        self.called = False
        self.last_prompt = None

    def augment(self, prompt, use_context=True):
        self.called = True
        self.last_prompt = prompt
        return f"augmented:{prompt}"


class MockOutput:
    """Mock output interface."""

    def echo(self, *args, **kwargs):
        pass

    def secho(self, *args, **kwargs):
        pass


class MockBatchScheduler:
    """Mock batch scheduler."""

    def execute_batch(self, *args, **kwargs):
        return []


def create_delegation_manager(llm_service, augmenter, cache):
    """Helper to create DelegationManager with all required mocks."""
    return DelegationManager(
        llm_service=llm_service,
        prompt_augmenter=augmenter,
        cache=cache,
        output=MockOutput(),
        batch_scheduler=MockBatchScheduler(),
    )


class TestDelegationMessages:
    """Tests for messages parameter in DelegationManager.delegate()."""

    def test_delegate_uses_messages_when_provided(self):
        """Messages param should bypass prompt/system_prompt construction."""
        llm_service = MockLLMService()
        augmenter = MockAugmenter()
        cache = MockCache()

        manager = create_delegation_manager(llm_service, augmenter, cache)

        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "user", "content": "How are you?"},
        ]

        response, task_record = manager.delegate(
            provider_name="fast",
            prompt="this should be ignored",
            messages=messages,
        )

        # Verify LLM service received exact messages array
        assert llm_service.last_call_kwargs["messages"] == messages

    def test_delegate_skips_augmentation_when_messages_provided(self):
        """Should not call augmenter when messages provided."""
        llm_service = MockLLMService()
        augmenter = MockAugmenter()
        cache = MockCache()

        manager = create_delegation_manager(llm_service, augmenter, cache)

        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "task"},
        ]

        manager.delegate(
            provider_name="fast",
            prompt="",
            messages=messages,
        )

        # Augmenter should NOT be called
        assert not augmenter.called

    def test_delegate_builds_messages_when_not_provided(self):
        """Without messages, should build from prompt/system_prompt."""
        llm_service = MockLLMService()
        augmenter = MockAugmenter()
        cache = MockCache()

        manager = create_delegation_manager(llm_service, augmenter, cache)

        manager.delegate(
            provider_name="fast",
            prompt="Hello",
            system_prompt="Be helpful",
        )

        # Augmenter should be called
        assert augmenter.called
        assert augmenter.last_prompt == "Hello"

        # Messages should be built from augmented prompt and system_prompt
        messages = llm_service.last_call_kwargs["messages"]
        assert len(messages) == 2
        assert messages[0] == {"role": "system", "content": "Be helpful"}
        assert messages[1] == {"role": "user", "content": "augmented:Hello"}

    def test_delegate_with_messages_sets_correct_task_record(self):
        """Task record should indicate no context augmentation when messages provided."""
        llm_service = MockLLMService()
        augmenter = MockAugmenter()
        cache = MockCache()

        manager = create_delegation_manager(llm_service, augmenter, cache)

        messages = [{"role": "user", "content": "test"}]

        response, task_record = manager.delegate(
            provider_name="fast",
            prompt="",
            messages=messages,
        )

        assert task_record["context_augmented"] is False
        assert task_record["cached"] is False

    def test_delegate_with_messages_passes_kwargs(self):
        """Additional kwargs should still be passed through when using messages."""
        llm_service = MockLLMService()
        augmenter = MockAugmenter()
        cache = MockCache()

        manager = create_delegation_manager(llm_service, augmenter, cache)

        messages = [{"role": "user", "content": "test"}]

        manager.delegate(
            provider_name="fast",
            prompt="",
            messages=messages,
            max_tokens=500,
            temperature=0.5,
        )

        assert llm_service.last_call_kwargs["max_tokens"] == 500
        assert llm_service.last_call_kwargs["temperature"] == 0.5

    def test_delegate_with_messages_resolves_model(self):
        """Model resolution should still work when using messages."""
        llm_service = MockLLMService()
        augmenter = MockAugmenter()
        cache = MockCache()

        manager = create_delegation_manager(llm_service, augmenter, cache)

        messages = [{"role": "user", "content": "test"}]

        # Test with provider_name that maps to model group
        manager.delegate(
            provider_name="fast",
            prompt="",
            messages=messages,
        )

        # Model should be resolved (fast -> fast model group)
        assert "model" in llm_service.last_call_kwargs

    def test_delegate_with_empty_messages_list(self):
        """Empty messages list should still bypass augmentation."""
        llm_service = MockLLMService()
        augmenter = MockAugmenter()
        cache = MockCache()

        manager = create_delegation_manager(llm_service, augmenter, cache)

        # Empty list is truthy for "is not None" check
        messages = []

        manager.delegate(
            provider_name="fast",
            prompt="should be ignored",
            messages=messages,
        )

        # Augmenter should NOT be called (messages was provided, even if empty)
        assert not augmenter.called
        assert llm_service.last_call_kwargs["messages"] == []
