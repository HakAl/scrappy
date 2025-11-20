"""
Tests for PromptAugmenter - Prompt augmentation with context and working memory.

Tests follow CLAUDE.md guidelines:
- Test behavior, not implementation
- Cover edge cases
- Prove features work
- Minimal mocking (only protocols)
"""

import pytest
from src.orchestrator.prompt_augmenter import PromptAugmenter


# Test Doubles (implementing protocols)

class FakeContext:
    """Test double for ContextProviderProtocol."""

    def __init__(self, explored: bool = True, augmented_prompt: str = None):
        self._explored = explored
        self._augmented_prompt = augmented_prompt

    def is_explored(self) -> bool:
        return self._explored

    def augment_prompt(self, prompt: str) -> str:
        if self._augmented_prompt:
            return self._augmented_prompt
        # Default behavior: add context marker
        return f"[CONTEXT]\n{prompt}"


class FakeWorkingMemory:
    """Test double for WorkingMemoryProtocol."""

    def __init__(self, context: str = None):
        self._context = context

    def get_context(self) -> str:
        return self._context


# Tests for basic functionality

def test_augment_with_no_context_or_memory_returns_original_prompt():
    """Test that augment returns original prompt when no context or memory available."""
    augmenter = PromptAugmenter()
    prompt = "What is the meaning of life?"

    result = augmenter.augment(prompt)

    assert result == prompt


def test_augment_with_codebase_context_adds_context():
    """Test that augment adds codebase context when available and explored."""
    context = FakeContext(explored=True, augmented_prompt="[CONTEXT]\nWhat is the meaning of life?")
    augmenter = PromptAugmenter(context=context)
    prompt = "What is the meaning of life?"

    result = augmenter.augment(prompt)

    assert result == "[CONTEXT]\nWhat is the meaning of life?"
    assert "[CONTEXT]" in result


def test_augment_with_working_memory_prepends_memory():
    """Test that augment prepends working memory when available."""
    memory = FakeWorkingMemory(context="Recent conversation:\nUser asked about life.\nAssistant explained 42.")
    augmenter = PromptAugmenter(working_memory=memory)
    prompt = "What is the meaning of life?"

    result = augmenter.augment(prompt)

    assert result.startswith("Recent conversation:")
    assert "What is the meaning of life?" in result
    assert "\n\n" in result  # Should have double newline separator


def test_augment_with_both_context_and_memory():
    """Test that augment combines both codebase context and working memory correctly."""
    context = FakeContext(explored=True, augmented_prompt="[CONTEXT]\nWhat is the meaning of life?")
    memory = FakeWorkingMemory(context="Recent conversation:\nUser asked about life.")
    augmenter = PromptAugmenter(context=context, working_memory=memory)
    prompt = "What is the meaning of life?"

    result = augmenter.augment(prompt)

    # Working memory should come first, then the context-augmented prompt
    assert result.startswith("Recent conversation:")
    assert "[CONTEXT]" in result
    assert "\n\n" in result


def test_augment_respects_order_working_memory_then_context():
    """Test that working memory is prepended before codebase context is added."""
    context = FakeContext(explored=True, augmented_prompt="[CONTEXT]\nOriginal prompt")
    memory = FakeWorkingMemory(context="[MEMORY]")
    augmenter = PromptAugmenter(context=context, working_memory=memory)
    prompt = "Original prompt"

    result = augmenter.augment(prompt)

    # Expected: [MEMORY]\n\n[CONTEXT]\nOriginal prompt
    # Working memory comes first, then context-augmented prompt
    assert result == "[MEMORY]\n\n[CONTEXT]\nOriginal prompt"


# Tests for use_context flag

def test_augment_with_use_context_false_skips_context():
    """Test that use_context=False skips codebase context augmentation."""
    context = FakeContext(explored=True, augmented_prompt="[CONTEXT]\nWhat is the meaning of life?")
    augmenter = PromptAugmenter(context=context)
    prompt = "What is the meaning of life?"

    result = augmenter.augment(prompt, use_context=False)

    # Should return original prompt without context augmentation
    assert result == prompt
    assert "[CONTEXT]" not in result


def test_augment_with_use_context_false_still_adds_working_memory():
    """Test that use_context=False still prepends working memory."""
    context = FakeContext(explored=True, augmented_prompt="[CONTEXT]\nWhat is the meaning of life?")
    memory = FakeWorkingMemory(context="[MEMORY]")
    augmenter = PromptAugmenter(context=context, working_memory=memory)
    prompt = "What is the meaning of life?"

    result = augmenter.augment(prompt, use_context=False)

    # Should have working memory but not codebase context
    assert result.startswith("[MEMORY]")
    assert "[CONTEXT]" not in result
    assert "What is the meaning of life?" in result


def test_augment_with_use_context_true_adds_context():
    """Test that use_context=True includes codebase context."""
    context = FakeContext(explored=True, augmented_prompt="[CONTEXT]\nWhat is the meaning of life?")
    augmenter = PromptAugmenter(context=context)
    prompt = "What is the meaning of life?"

    result = augmenter.augment(prompt, use_context=True)

    assert "[CONTEXT]" in result


# Tests for edge cases

def test_augment_with_empty_prompt_raises_error():
    """Test that empty prompt raises ValueError."""
    augmenter = PromptAugmenter()

    with pytest.raises(ValueError, match="prompt cannot be empty or None"):
        augmenter.augment("")


def test_augment_with_none_prompt_raises_error():
    """Test that None prompt raises ValueError."""
    augmenter = PromptAugmenter()

    with pytest.raises(ValueError, match="prompt cannot be empty or None"):
        augmenter.augment(None)


def test_augment_with_context_not_explored_skips_context():
    """Test that context augmentation is skipped when context is not explored."""
    context = FakeContext(explored=False)
    augmenter = PromptAugmenter(context=context)
    prompt = "What is the meaning of life?"

    result = augmenter.augment(prompt)

    # Should return original prompt since context is not explored
    assert result == prompt


def test_augment_with_empty_working_memory_does_not_prepend():
    """Test that empty working memory context is not prepended."""
    memory = FakeWorkingMemory(context="")
    augmenter = PromptAugmenter(working_memory=memory)
    prompt = "What is the meaning of life?"

    result = augmenter.augment(prompt)

    # Should return original prompt without prepending empty string
    assert result == prompt


def test_augment_with_none_working_memory_does_not_prepend():
    """Test that None working memory context is handled gracefully."""
    memory = FakeWorkingMemory(context=None)
    augmenter = PromptAugmenter(working_memory=memory)
    prompt = "What is the meaning of life?"

    result = augmenter.augment(prompt)

    # Should return original prompt
    assert result == prompt


def test_augment_with_whitespace_only_prompt_raises_error():
    """Test that whitespace-only prompt raises ValueError."""
    augmenter = PromptAugmenter()

    with pytest.raises(ValueError, match="prompt cannot be empty or None"):
        augmenter.augment("   \n\t  ")


# Tests for multiple calls (idempotency checks)

def test_augment_multiple_calls_with_same_prompt():
    """Test that multiple calls with same prompt produce same result."""
    context = FakeContext(explored=True, augmented_prompt="[CONTEXT]\nWhat is the meaning of life?")
    memory = FakeWorkingMemory(context="[MEMORY]")
    augmenter = PromptAugmenter(context=context, working_memory=memory)
    prompt = "What is the meaning of life?"

    result1 = augmenter.augment(prompt)
    result2 = augmenter.augment(prompt)

    assert result1 == result2


def test_augment_multiple_calls_with_different_prompts():
    """Test that augmenter works correctly with different prompts."""
    context = FakeContext(explored=True)
    augmenter = PromptAugmenter(context=context)

    result1 = augmenter.augment("First prompt")
    result2 = augmenter.augment("Second prompt")

    assert "First prompt" in result1
    assert "Second prompt" in result2
    assert result1 != result2


# Tests for protocol compliance

def test_prompt_augmenter_implements_protocol():
    """Test that PromptAugmenter implements PromptAugmenterProtocol."""
    from src.protocols.delegation import PromptAugmenterProtocol

    augmenter = PromptAugmenter()

    # Should have augment method
    assert hasattr(augmenter, 'augment')
    assert callable(augmenter.augment)

    # Test that it works as expected by the protocol
    result = augmenter.augment("test prompt")
    assert isinstance(result, str)


# Tests for dependency injection

def test_constructor_with_no_dependencies():
    """Test that constructor works with no dependencies."""
    augmenter = PromptAugmenter()

    assert augmenter is not None
    assert augmenter._context is None
    assert augmenter._working_memory is None


def test_constructor_with_only_context():
    """Test that constructor works with only context dependency."""
    context = FakeContext()
    augmenter = PromptAugmenter(context=context)

    assert augmenter._context is context
    assert augmenter._working_memory is None


def test_constructor_with_only_working_memory():
    """Test that constructor works with only working memory dependency."""
    memory = FakeWorkingMemory()
    augmenter = PromptAugmenter(working_memory=memory)

    assert augmenter._context is None
    assert augmenter._working_memory is memory


def test_constructor_with_all_dependencies():
    """Test that constructor works with all dependencies."""
    context = FakeContext()
    memory = FakeWorkingMemory()
    augmenter = PromptAugmenter(context=context, working_memory=memory)

    assert augmenter._context is context
    assert augmenter._working_memory is memory
