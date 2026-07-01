"""
PromptAugmenter - Handles prompt augmentation with context and working memory.

Follows SOLID principles:
- Single Responsibility: Only augments prompts, nothing else
- Open/Closed: Extensible via protocol implementation
- Dependency Inversion: Depends on protocols, not concretions
"""

from typing import Optional

from .protocols import (
    ContextProvider as ContextProviderProtocol,
    WorkingMemoryProtocol,
)


class PromptAugmenter:
    """
    Augments prompts with codebase context and working memory.

    Follows Single Responsibility Principle - only handles prompt augmentation.
    All dependencies are injected, making this class easy to test and extend.

    Responsibilities:
    - Add codebase context to prompts (if available and explored)
    - Add working memory/recent interactions to prompts (if available)
    - Manage the order of context augmentation (working memory first, then codebase context)

    Does NOT:
    - Make LLM calls
    - Cache responses
    - Handle retries
    - Track rate limits
    - Select providers
    """

    def __init__(
        self,
        *,
        context: Optional[ContextProviderProtocol] = None,
        working_memory: Optional[WorkingMemoryProtocol] = None,
    ):
        """
        Initialize PromptAugmenter.

        All dependencies are injected - NO instantiation inside constructor.

        Args:
            context: Codebase context provider (optional)
            working_memory: Working memory provider (optional)
        """
        self._context = context
        self._working_memory = working_memory

    def augment(
        self,
        prompt: str,
        use_context: bool = True,
    ) -> str:
        """
        Augment a prompt with contextual information.

        The augmentation process:
        1. Start with original prompt
        2. If codebase context is available and explored, augment with it
        3. If working memory is available, prepend it to the prompt

        This ensures working memory (recent interactions) appears before
        the main prompt, providing immediate context for the LLM.

        Args:
            prompt: Original user prompt
            use_context: Whether to include codebase context

        Returns:
            Augmented prompt ready for LLM

        Raises:
            ValueError: If prompt is empty or None
        """
        if not prompt or not prompt.strip():
            raise ValueError("prompt cannot be empty or None")

        final_prompt = prompt

        # Step 1: Augment with codebase context if available
        if use_context and self._context:
            # Only augment if the context has been explored
            # This prevents augmenting prompts with stale/missing context
            if self._context.is_explored():
                final_prompt = self._context.augment_prompt(prompt)

        # Step 2: Prepend working memory if available
        if self._working_memory:
            working_memory_context = self._working_memory.get_context()
            if working_memory_context:
                # Prepend working memory with double newline separator
                final_prompt = working_memory_context + "\n\n" + final_prompt

        return final_prompt
