"""
DelegationManager - Handles LLM delegation with caching and prompt augmentation.

Refactored to follow SOLID principles:
- Single Responsibility: Coordinates delegation flow, delegates LLM calls to LLMService
- Open/Closed: Can extend by swapping protocol implementations
- Dependency Inversion: Depends on protocols, not concretions

After LiteLLM integration (Phase 3):
- Uses LLMServiceProtocol instead of RetryOrchestratorProtocol
- LiteLLM handles retry/fallback internally via Router configuration
- provider_name is now a model GROUP name ("fast" or "quality")
"""

from typing import Optional, Callable, AsyncIterator
from datetime import datetime
import asyncio

try:
    from ..providers import LLMResponse
    from ..protocols.delegation import (
        LLMRequest,
        CacheProtocol,
        OutputInterfaceProtocol,
        PromptAugmenterProtocol,
        BatchSchedulerProtocol,
        INTERNAL_KWARGS,
    )
    from ..orchestrator.protocols import LLMServiceProtocol, StreamingCompletionProtocol
    from ..orchestrator.types import StreamChunk
    from ..config import (
        DEFAULT_MAX_TOKENS,
        DEFAULT_TEMPERATURE,
        DEFAULT_MAX_RETRIES,
        DEFAULT_PROVIDER,
        DEFAULT_MAX_CONCURRENT,
    )
except ImportError:
    from providers import LLMResponse
    from protocols.delegation import (
        LLMRequest,
        CacheProtocol,
        OutputInterfaceProtocol,
        PromptAugmenterProtocol,
        BatchSchedulerProtocol,
    )
    from orchestrator.protocols import LLMServiceProtocol, StreamingCompletionProtocol
    from orchestrator.types import StreamChunk
    from config import (
        DEFAULT_MAX_TOKENS,
        DEFAULT_TEMPERATURE,
        DEFAULT_MAX_RETRIES,
        DEFAULT_PROVIDER,
        DEFAULT_MAX_CONCURRENT,
    )


# Model groups for LiteLLM Router
MODEL_GROUPS = {"fast", "quality"}

# Map legacy provider names to model groups
PROVIDER_TO_GROUP = {
    "groq": "fast",
    "cerebras": "fast",
    "gemini": "quality",
    "auto": "fast",
}


def _resolve_model_group(provider_name: str) -> str:
    """
    Resolve a provider name to a model group for LiteLLM Router.

    Args:
        provider_name: Provider name (could be legacy name like "groq" or group like "fast")

    Returns:
        Model group name ("fast" or "quality")
    """
    # If it's already a valid model group, return as-is
    if provider_name in MODEL_GROUPS:
        return provider_name

    # Map legacy provider names to groups
    if provider_name in PROVIDER_TO_GROUP:
        return PROVIDER_TO_GROUP[provider_name]

    # Default to "fast" for unknown providers
    return "fast"


class DelegationManager:
    """
    Coordinates LLM delegation with caching, prompt augmentation, and LLM service calls.

    Follows SOLID principles:
    - Single Responsibility: Coordinates delegation flow (caching, augmentation, LLM calls)
    - Open/Closed: Extensible via protocol implementations
    - Dependency Inversion: Depends on protocols, not concretions

    Responsibilities:
    - Coordinate delegation flow (caching, augmentation, LLM calls)
    - Check cache before making requests
    - Delegate prompt augmentation to PromptAugmenter
    - Delegate LLM calls to LLMService (which uses LiteLLM Router for retry/fallback)
    - Delegate batch/parallel execution to BatchScheduler
    - Store successful responses in cache
    - Return response with metadata

    Does NOT:
    - Implement prompt augmentation logic (delegates to PromptAugmenter)
    - Implement retry logic (handled by LiteLLM Router via LLMService)
    - Implement batch scheduling logic (delegates to BatchScheduler)
    - Implement provider selection (handled by LiteLLM Router)
    - Implement rate limit tracking (handled by LiteLLM callbacks)
    """

    def __init__(
        self,
        *,
        llm_service: LLMServiceProtocol,
        cache: CacheProtocol,
        output: OutputInterfaceProtocol,
        prompt_augmenter: PromptAugmenterProtocol,
        batch_scheduler: BatchSchedulerProtocol,
        context_aware: bool = False,
    ):
        """
        Initialize DelegationManager.

        All dependencies are injected - NO instantiation inside constructor.

        Args:
            llm_service: LLM service for making completion calls (uses LiteLLM Router)
            cache: Response cache for caching LLM responses
            output: Output interface for logging messages
            prompt_augmenter: Prompt augmenter for adding context and working memory
            batch_scheduler: Batch scheduler for parallel execution
            context_aware: Whether to augment prompts with context
        """
        self._llm_service = llm_service
        self._cache = cache
        self._output = output
        self._prompt_augmenter = prompt_augmenter
        self._batch_scheduler = batch_scheduler
        self._context_aware = context_aware

    def delegate(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        use_context: Optional[bool] = None,
        use_cache: Optional[bool] = None,
        intent_classification: Optional[dict] = None,
        auto_fallback: bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
        selection_type: Optional[str] = None,
        min_context: int = 0,
        **kwargs
    ) -> tuple[LLMResponse, dict]:
        """
        Synchronous delegation with caching, prompt augmentation, and retry/fallback.

        This method uses synchronous provider methods (provider.chat()) directly,
        making it safe to call from any thread including Textual worker threads.

        For async code, use delegate_async() directly.

        Args:
            provider_name: Initial provider to try
            prompt: The prompt to send
            model: Specific model (optional)
            system_prompt: System prompt (optional)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            use_context: Override context augmentation setting
            use_cache: Override cache setting
            intent_classification: Intent data for semantic caching
            auto_fallback: Automatically try other providers on rate limit
            max_retries: Maximum retry attempts per provider
            selection_type: ModelSelectionType value for fallback filtering (e.g., 'quality')
            min_context: Minimum context length for fallback filtering
            **kwargs: Additional provider-specific arguments

        Returns:
            Tuple of (LLMResponse, task_record dict)

        Raises:
            AllProvidersRateLimitedError: If all providers are rate limited
            ValueError: If input validation fails
        """
        # Determine settings
        should_use_context = use_context if use_context is not None else self._context_aware
        should_use_cache = use_cache if use_cache is not None else True

        # Step 1: Augment prompt with context and working memory
        final_prompt = self._prompt_augmenter.augment(prompt, use_context=should_use_context)

        # Step 2: Check cache first
        cached_response = None
        intent_cache_hit = False
        if should_use_cache:
            cached_response = self._cache.get(
                provider_name, final_prompt, model, system_prompt, max_tokens, temperature
            )
            if not cached_response and intent_classification:
                cached_response = self._cache.get_by_intent(
                    intent_classification.get('intent', ''),
                    intent_classification.get('entities', {}),
                    intent_classification.get('keywords', []),
                    provider_name,
                    model
                )
                if cached_response:
                    intent_cache_hit = True

        if cached_response:
            task_record = {
                'timestamp': datetime.now().isoformat(),
                'provider': provider_name,
                'model': cached_response.model,
                'tokens_used': cached_response.tokens_used,
                'latency_ms': 0.0,
                'context_augmented': should_use_context,
                'cached': True,
                'intent_cache_hit': intent_cache_hit,
                'async': False,
            }
            return cached_response, task_record

        # Step 3: Resolve model group and build messages
        model_group = _resolve_model_group(provider_name)

        # Build messages list for LiteLLM
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": final_prompt})

        # Filter out internal kwargs that should NOT be passed to provider API
        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in INTERNAL_KWARGS}

        # Step 4: Execute via LLMService (LiteLLM Router handles retry/fallback)
        response, task_record = self._llm_service.completion_sync(
            model=model_group,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **filtered_kwargs,
        )

        # Step 5: Store in cache
        if should_use_cache:
            self._cache.put(response, final_prompt, model, system_prompt, max_tokens, temperature)
            if intent_classification:
                self._cache.put_by_intent(
                    response,
                    intent_classification.get('intent', ''),
                    intent_classification.get('entities', {}),
                    intent_classification.get('keywords', [])
                )

        # Step 6: Add context info to task record
        task_record['context_augmented'] = should_use_context
        task_record['cached'] = False
        task_record['async'] = False

        return response, task_record

    async def delegate_async(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        use_context: Optional[bool] = None,
        use_cache: Optional[bool] = None,
        intent_classification: Optional[dict] = None,
        auto_fallback: bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
        selection_type: Optional[str] = None,
        min_context: int = 0,
        **kwargs
    ) -> tuple[LLMResponse, dict]:
        """
        Async delegation with caching, prompt augmentation, and retry/fallback logic.

        This is the primary implementation. The sync delegate() method is a thin
        wrapper that calls asyncio.run() on this method.

        Args:
            provider_name: Initial provider to try
            prompt: The prompt to send
            model: Specific model (optional)
            system_prompt: System prompt (optional)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            use_context: Override context augmentation setting
            use_cache: Override cache setting
            intent_classification: Intent data for semantic caching
            auto_fallback: Automatically try other providers on rate limit
            max_retries: Maximum retry attempts per provider
            selection_type: ModelSelectionType value for fallback filtering (e.g., 'quality')
            min_context: Minimum context length for fallback filtering
            **kwargs: Additional provider-specific arguments

        Returns:
            Tuple of (LLMResponse, task_record dict)

        Raises:
            AllProvidersRateLimitedError: If all providers are rate limited
            ValueError: If input validation fails
        """
        # Determine settings
        should_use_context = use_context if use_context is not None else self._context_aware
        should_use_cache = use_cache if use_cache is not None else True

        # Step 1: Augment prompt with context and working memory
        final_prompt = self._prompt_augmenter.augment(prompt, use_context=should_use_context)

        # Step 2: Check cache first
        cached_response = None
        intent_cache_hit = False
        if should_use_cache:
            cached_response = self._cache.get(
                provider_name, final_prompt, model, system_prompt, max_tokens, temperature
            )
            if not cached_response and intent_classification:
                cached_response = self._cache.get_by_intent(
                    intent_classification.get('intent', ''),
                    intent_classification.get('entities', {}),
                    intent_classification.get('keywords', []),
                    provider_name,
                    model
                )
                if cached_response:
                    intent_cache_hit = True

        if cached_response:
            task_record = {
                'timestamp': datetime.now().isoformat(),
                'provider': provider_name,
                'model': cached_response.model,
                'tokens_used': cached_response.tokens_used,
                'latency_ms': 0.0,
                'context_augmented': should_use_context,
                'cached': True,
                'intent_cache_hit': intent_cache_hit,
                'async': True,
            }
            return cached_response, task_record

        # Step 3: Resolve model group and build messages
        model_group = _resolve_model_group(provider_name)

        # Build messages list for LiteLLM
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": final_prompt})

        # Filter out internal kwargs that should NOT be passed to provider API
        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in INTERNAL_KWARGS}

        # Step 4: Execute via LLMService (LiteLLM Router handles retry/fallback)
        response, task_record = await self._llm_service.completion(
            model=model_group,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **filtered_kwargs,
        )

        # Step 5: Store in cache
        if should_use_cache:
            self._cache.put(response, final_prompt, model, system_prompt, max_tokens, temperature)
            if intent_classification:
                self._cache.put_by_intent(
                    response,
                    intent_classification.get('intent', ''),
                    intent_classification.get('entities', {}),
                    intent_classification.get('keywords', [])
                )

        # Step 6: Add context info to task record
        task_record['context_augmented'] = should_use_context
        task_record['cached'] = False
        task_record['async'] = True

        return response, task_record

    def delegate_batch(
        self,
        tasks: list[dict],
        provider_name: str = DEFAULT_PROVIDER,
        **kwargs
    ) -> list[LLMResponse]:
        """
        Process multiple tasks with same provider (synchronous).

        This method processes tasks sequentially using the sync delegate() method,
        making it safe to call from any thread including Textual worker threads.

        For parallel async processing, use batch_delegate_async() directly.

        Args:
            tasks: List of task dicts with 'prompt' and optional 'system_prompt', 'kwargs'
            provider_name: Provider to use for all tasks
            **kwargs: Additional arguments passed to delegate

        Returns:
            List of LLMResponse objects in the same order as input tasks
        """
        results = []
        for task in tasks:
            task_kwargs = task.get('kwargs', {})
            task_kwargs.update(kwargs)

            result, _ = self.delegate(
                provider_name=provider_name,
                prompt=task['prompt'],
                system_prompt=task.get('system_prompt'),
                **task_kwargs
            )
            results.append(result)

        return results

    async def batch_delegate_async(
        self,
        tasks: list[dict],
        provider_name: str = DEFAULT_PROVIDER,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        **kwargs
    ) -> list[LLMResponse]:
        """
        Process multiple tasks in parallel using async.

        This method parallelizes calls to delegate_async, ensuring each task
        goes through the full delegation flow (augmentation, caching, retry).
        Uses semaphore for concurrency control.

        Args:
            tasks: List of task dicts with 'prompt' and optional 'system_prompt', 'kwargs'
            provider_name: Provider to use for all tasks
            max_concurrent: Maximum number of concurrent requests
            **kwargs: Additional arguments passed to all tasks

        Returns:
            List of LLMResponse objects in the same order as input tasks
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_task(task):
            """Process a single task through full delegation flow."""
            async with semaphore:
                task_kwargs = task.get('kwargs', {})
                task_kwargs.update(kwargs)

                result, _ = await self.delegate_async(
                    provider_name=provider_name,
                    prompt=task['prompt'],
                    system_prompt=task.get('system_prompt'),
                    **task_kwargs
                )
                return result

        # Execute all tasks in parallel and preserve order
        results = await asyncio.gather(*[process_task(task) for task in tasks])
        return list(results)

    async def multi_provider_query_async(
        self,
        prompt: str,
        providers: list[str],
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        **kwargs
    ) -> dict[str, tuple]:
        """
        Query multiple providers in parallel for the same prompt (delegates to BatchScheduler).

        This method now delegates to BatchScheduler for parallel multi-provider queries,
        eliminating ~15 lines of duplicate logic.

        Useful for getting different perspectives or comparing outputs.

        Args:
            prompt: The prompt to send to all providers
            providers: List of provider names to query
            model: Specific model (optional)
            system_prompt: System prompt (optional)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional arguments passed to requests

        Returns:
            Dict mapping provider name to (LLMResponse, task_record) tuple.
            Failed providers are excluded from results.

        Raises:
            ValueError: If providers list is empty
        """
        # Create LLMRequest object (provider will be overridden per provider)
        request = LLMRequest(
            prompt=prompt,
            provider=providers[0] if providers else DEFAULT_PROVIDER,  # Default, will be overridden
            model=model,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            use_context=kwargs.get('use_context'),
            use_cache=kwargs.get('use_cache'),
            intent_classification=kwargs.get('intent_classification'),
            auto_fallback=False,  # No fallback in multi-provider mode
            kwargs=kwargs,
        )

        # Delegate to BatchScheduler for parallel multi-provider execution
        return await self._batch_scheduler.execute_multi_provider(
            request=request,
            providers=providers,
        )

    async def stream_delegate(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        use_context: Optional[bool] = None,
        use_cache: Optional[bool] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream delegation with prompt augmentation and cache checking.

        This method streams LLM responses chunk-by-chunk, enabling real-time
        display of generated text. Unlike delegate_async which returns a complete
        response, this yields incremental StreamChunk objects as they arrive.

        Cache behavior:
        - If cache hit: yields single StreamChunk with full cached content
        - If cache miss: streams from provider, then caches final result

        Args:
            provider_name: Initial provider to try
            prompt: The prompt to send
            model: Specific model (optional)
            system_prompt: System prompt (optional)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            use_context: Override context augmentation setting
            use_cache: Override cache setting
            **kwargs: Additional provider-specific arguments

        Yields:
            StreamChunk objects as they arrive from the provider

        Raises:
            AllProvidersRateLimitedError: If all providers are rate limited
            ContextWindowExceededError: When quality tier also exceeds context
            ValueError: If input validation fails

        Example:
            async for chunk in delegation_manager.stream_delegate(
                provider_name="fast",
                prompt="Write a story",
                max_tokens=500
            ):
                print(chunk.content, end="", flush=True)
        """
        # Determine settings
        should_use_context = use_context if use_context is not None else self._context_aware
        should_use_cache = use_cache if use_cache is not None else True

        # Step 1: Augment prompt with context and working memory
        final_prompt = self._prompt_augmenter.augment(prompt, use_context=should_use_context)

        # Step 2: Check cache first
        cached_response = None
        if should_use_cache:
            cached_response = self._cache.get(
                provider_name, final_prompt, model, system_prompt, max_tokens, temperature
            )

        if cached_response:
            # Cache hit - yield single chunk with full cached content
            yield StreamChunk(
                content=cached_response.content,
                tool_call_fragments=[],
                finish_reason="stop",
                model=cached_response.model,
                provider=cached_response.provider,
                metadata={
                    "cached": True,
                    "context_augmented": should_use_context,
                }
            )
            return

        # Step 3: Resolve model group and build messages
        model_group = _resolve_model_group(provider_name)

        # Build messages list for LiteLLM
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": final_prompt})

        # Filter out internal kwargs that should NOT be passed to provider API
        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in INTERNAL_KWARGS}

        # Step 4: Stream via LLMService (LiteLLM Router handles retry/fallback)
        # Check if service supports streaming
        if not isinstance(self._llm_service, StreamingCompletionProtocol):
            raise NotImplementedError(
                "LLM service does not support streaming. "
                "Ensure LiteLLMService is used instead of a mock."
            )

        # Accumulate full response for caching
        full_content = []
        final_chunk = None

        async for chunk in self._llm_service.stream_completion(
            model=model_group,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **filtered_kwargs,
        ):
            # Accumulate content for caching
            if chunk.content:
                full_content.append(chunk.content)

            # Track final chunk for metadata
            final_chunk = chunk

            # Yield chunk to caller
            yield chunk

        # Step 5: Store complete response in cache
        if should_use_cache and final_chunk:
            # Build LLMResponse from accumulated chunks
            cached_llm_response = LLMResponse(
                content="".join(full_content),
                model=final_chunk.model,
                provider=final_chunk.provider,
                tokens_used=0,  # Token counting not available in streaming
                latency_ms=0.0,  # Latency handled by streaming layer
                metadata={
                    "finish_reason": final_chunk.finish_reason,
                    "context_augmented": should_use_context,
                    "streamed": True,
                }
            )
            self._cache.put(
                cached_llm_response,
                final_prompt,
                model,
                system_prompt,
                max_tokens,
                temperature
            )
