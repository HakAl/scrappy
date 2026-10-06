"""
Tests for DelegationManager messages parameter.

Tests that the messages parameter bypasses prompt augmentation and
is passed directly to the LLM service.
"""


import copy
import hashlib
from pathlib import Path

import pytest

from scrappy.orchestrator.cache import ResponseCache
from scrappy.orchestrator.delegation import DelegationManager
from scrappy.orchestrator.output import NullOutput
from scrappy.orchestrator.prompt_augmenter import PromptAugmenter
from tests.helpers import MockLLMService


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


# ---------------------------------------------------------------------------
# g0lk: concrete-model context validation parity for the prebuilt-messages path
#
# The messages branch resolved a model and dispatched without ever validating
# that the model could satisfy min_context, so an undersized concrete model
# reached the service. The repair adds exactly one existing-helper call after
# resolution and before dispatch.
#
# Oracle note (binding): asserting only "raises ValueError" cannot distinguish
# a refusal from a dispatch-then-refuse mutant. Every refusal case below also
# asserts the external LLM boundary was never called.
# ---------------------------------------------------------------------------

# Real catalog facts, not invented fixtures.
KNOWN_8192 = "cerebras/llama-3.3-70b"
KNOWN_LARGE = "gemini/gemini-2.5-flash"
UNKNOWN_QUALIFIED = "cerebras/model-that-does-not-exist"
UNKNOWN_BARE = "model-that-does-not-exist"

# A whitespace-only prompt is the augmentation tripwire: the real
# PromptAugmenter raises on it, so reaching augmentation is observable.
IGNORED_PROMPT = "   "


def create_real_dependency_manager(llm_service):
    """Build a manager with the REAL augmenter and REAL cache.

    Only the LLM service is a double, and only because it is the external
    boundary. Returns the cache so bypass can be proven from its public stats.
    """
    cache = ResponseCache(cache_file=None, output=NullOutput(), auto_load=False)
    manager = DelegationManager(
        llm_service=llm_service,
        prompt_augmenter=PromptAugmenter(),
        cache=cache,
        output=MockOutput(),
        batch_scheduler=MockBatchScheduler(),
    )
    return manager, cache


def assert_cache_untouched(cache):
    """The messages path must not read or write the cache at all."""
    stats = cache.get_stats()
    assert stats["exact_hits"] == 0
    assert stats["exact_misses"] == 0
    assert stats["intent_hits"] == 0
    assert stats["intent_misses"] == 0
    assert stats["saves"] == 0
    assert stats["exact_cache_entries"] == 0
    assert stats["intent_cache_entries"] == 0


class TestMessagesContextValidationRefusal:
    """Refusal cases: the model cannot satisfy min_context, so nothing dispatches."""

    def test_known_insufficient_model_refuses_without_dispatching(self):
        llm_service = MockLLMService()
        manager, cache = create_real_dependency_manager(llm_service)

        with pytest.raises(ValueError) as excinfo:
            manager.delegate(
                provider_name="chat",
                prompt=IGNORED_PROMPT,
                model=KNOWN_8192,
                messages=[{"role": "user", "content": "hello"}],
                min_context=8193,
            )

        message = str(excinfo.value)
        assert KNOWN_8192 in message
        assert "8192" in message
        assert "8193" in message

        # The point of this test: refusal happened BEFORE the boundary call.
        assert llm_service.call_count == 0
        assert llm_service.calls == []
        assert_cache_untouched(cache)

    def test_unknown_provider_qualified_model_refuses_without_dispatching(self):
        llm_service = MockLLMService()
        manager, cache = create_real_dependency_manager(llm_service)

        with pytest.raises(ValueError) as excinfo:
            manager.delegate(
                provider_name="chat",
                prompt=IGNORED_PROMPT,
                model=UNKNOWN_QUALIFIED,
                messages=[{"role": "user", "content": "hello"}],
                min_context=1,
            )

        assert UNKNOWN_QUALIFIED in str(excinfo.value)
        assert llm_service.call_count == 0
        assert llm_service.calls == []
        assert_cache_untouched(cache)

    def test_empty_messages_list_still_enters_and_validates_this_branch(self):
        """An empty list is not None, so the branch is entered and validated."""
        llm_service = MockLLMService()
        manager, _cache = create_real_dependency_manager(llm_service)

        with pytest.raises(ValueError) as excinfo:
            manager.delegate(
                provider_name="chat",
                prompt=IGNORED_PROMPT,
                model=KNOWN_8192,
                messages=[],
                min_context=8193,
            )

        # Not the augmenter's refusal: this is the context refusal.
        assert KNOWN_8192 in str(excinfo.value)
        assert llm_service.call_count == 0


class TestMessagesContextValidationAccepts:
    """Accepted cases: exactly one dispatch with the expected model."""

    @pytest.mark.parametrize(
        "model,provider_name,min_context,expected_model",
        [
            # Exact boundary: available == required is sufficient.
            (KNOWN_8192, "chat", 8192, KNOWN_8192),
            # Greater available context than required.
            (KNOWN_8192, "chat", 4096, KNOWN_8192),
            (KNOWN_LARGE, "instruct", 131072, KNOWN_LARGE),
            # Unknown bare name has no provider prefix, so it stays exempt.
            (UNKNOWN_BARE, "chat", 999999, UNKNOWN_BARE),
            # Explicit model groups are exempt and pass through unchanged.
            ("chat", "chat", 999999, "chat"),
            ("instruct", "instruct", 999999, "instruct"),
            ("fast", "fast", 999999, "fast"),
            # No model: provider resolves to a group, which is exempt.
            (None, "groq", 999999, "fast"),
            # Non-positive min_context is exempt even for otherwise rejected models.
            (UNKNOWN_QUALIFIED, "chat", 0, UNKNOWN_QUALIFIED),
            (UNKNOWN_QUALIFIED, "chat", -1, UNKNOWN_QUALIFIED),
            (KNOWN_8192, "chat", 0, KNOWN_8192),
        ],
    )
    def test_accepted_dispatches_once_with_expected_model(
        self, model, provider_name, min_context, expected_model
    ):
        llm_service = MockLLMService()
        manager, cache = create_real_dependency_manager(llm_service)

        messages = [{"role": "user", "content": "hello"}]

        response, task_record = manager.delegate(
            provider_name=provider_name,
            prompt=IGNORED_PROMPT,
            model=model,
            messages=messages,
            min_context=min_context,
        )

        assert llm_service.call_count == 1
        assert llm_service.calls[0]["model"] == expected_model
        assert task_record["cached"] is False
        assert task_record["context_augmented"] is False
        assert task_record["async"] is False
        assert_cache_untouched(cache)

    def test_min_context_omitted_is_accepted(self):
        """Omitting min_context entirely must not start refusing work."""
        llm_service = MockLLMService()
        manager, cache = create_real_dependency_manager(llm_service)

        manager.delegate(
            provider_name="chat",
            prompt=IGNORED_PROMPT,
            model=KNOWN_8192,
            messages=[{"role": "user", "content": "hello"}],
        )

        assert llm_service.call_count == 1
        assert llm_service.calls[0]["model"] == KNOWN_8192
        assert_cache_untouched(cache)

    def test_accepted_dispatch_preserves_message_content_and_kwargs(self):
        """Messages reach the boundary by content, compared to an independent snapshot."""
        llm_service = MockLLMService()
        manager, cache = create_real_dependency_manager(llm_service)

        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ]
        # Independent deep snapshot: the mock retains the caller's list, so
        # comparing against that same object would also pass under in-place
        # mutation.
        expected_messages = copy.deepcopy(messages)

        manager.delegate(
            provider_name="chat",
            prompt=IGNORED_PROMPT,
            model=KNOWN_8192,
            messages=messages,
            min_context=8192,
            top_p=0.9,
            task_type="planning",
        )

        call = llm_service.calls[0]
        assert call["messages"] == expected_messages
        # Provider kwargs survive.
        assert call["top_p"] == 0.9
        # Internal kwargs are filtered out, as before.
        assert "task_type" not in call
        assert "min_context" not in call
        assert_cache_untouched(cache)


class TestMessagesValidationPreservesExistingBehavior:
    """Controls: unchanged paths must stay unchanged."""

    def test_standard_flow_still_refuses_empty_prompt_without_messages(self):
        """The existing no-messages refusal control, ordering untouched."""
        llm_service = MockLLMService()
        manager, _cache = create_real_dependency_manager(llm_service)

        with pytest.raises(ValueError) as excinfo:
            manager.delegate(provider_name="chat", prompt=IGNORED_PROMPT)

        assert "prompt cannot be empty" in str(excinfo.value)
        assert llm_service.call_count == 0

    def test_runtime_binding_receipt(self):
        """Guard: the modules under test import from this same source tree.

        Without this, a root-tree import could satisfy or mask the repair while
        appearing to exercise the candidate.
        """
        import scrappy.orchestrator.delegation as delegation_module
        import scrappy.orchestrator.litellm_config as litellm_config_module
        import scrappy.orchestrator.model_selection as model_selection_module
        import scrappy.orchestrator.provider_catalog as provider_catalog_module
        import tests.helpers as helpers_module

        tree_root = Path(__file__).resolve().parents[2]
        modules = {
            "delegation": delegation_module,
            "litellm_config": litellm_config_module,
            "model_selection": model_selection_module,
            "provider_catalog": provider_catalog_module,
            "tests.helpers": helpers_module,
            "this_test": None,
        }

        for name, module in modules.items():
            path = Path(__file__).resolve() if module is None else Path(module.__file__).resolve()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            print(f"RUNTIME-ORIGIN {name} {path} sha256={digest}")
            assert tree_root in path.parents, f"{name} imported from outside the tree under test: {path}"
