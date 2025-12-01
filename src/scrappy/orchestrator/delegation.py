"""
DelegationManager - Handles LLM delegation with caching and prompt augmentation.

Refactored to follow SOLID principles:
- Single Responsibility: Coordinates delegation flow, delegates retry logic to RetryOrchestrator
- Open/Closed: Can extend by swapping protocol implementations
- Dependency Inversion: Depends on protocols, not concretions
"""

from typing import Optional, Callable
from datetime import datetime
import asyncio

try:
    from ..providers import LLMResponse
    from ..protocols.delegation import (
        LLMRequest,
        RetryOrchestratorProtocol,
        ProviderRegistryProtocol,
        CacheProtocol,
        RateLimitTrackerProtocol,
        ProviderSelectorProtocol,
        OutputInterfaceProtocol,
        ContextProviderProtocol,
        WorkingMemoryProtocol,
        PromptAugmenterProtocol,
        BatchSchedulerProtocol,
    )
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
        RetryOrchestratorProtocol,
        ProviderRegistryProtocol,
        CacheProtocol,
        RateLimitTrackerProtocol,
        ProviderSelectorProtocol,
        OutputInterfaceProtocol,
        ContextProviderProtocol,
        WorkingMemoryProtocol,
        PromptAugmenterProtocol,
        BatchSchedulerProtocol,
    )
    from config import (
        DEFAULT_MAX_TOKENS,
        DEFAULT_TEMPERATURE,
        DEFAULT_MAX_RETRIES,
        DEFAULT_PROVIDER,
        DEFAULT_MAX_CONCURRENT,
    )


class DelegationManager:
    """
    Coordinates LLM delegation with caching, prompt augmentation, and retry logic.

    Follows SOLID principles:
    - Single Responsibility: Coordinates delegation flow (caching, augmentation, retry)
    - Open/Closed: Extensible via protocol implementations
    - Dependency Inversion: Depends on protocols, not concretions

    Responsibilities:
    - Coordinate delegation flow (caching, augmentation, retry)
    - Check cache before making requests
    - Delegate prompt augmentation to PromptAugmenter
    - Delegate retry/fallback logic to RetryOrchestrator
    - Delegate batch/parallel execution to BatchScheduler
    - Store successful responses in cache
    - Return response with metadata

    Does NOT:
    - Implement prompt augmentation logic (delegates to PromptAugmenter)
    - Implement retry logic (delegates to RetryOrchestrator)
    - Implement batch scheduling logic (delegates to BatchScheduler)
    - Implement provider selection (delegates to ProviderSelector)
    - Implement rate limit tracking (delegates to RateLimitTracker)
    """

    def __init__(
        self,
        *,
        retry_orchestrator: RetryOrchestratorProtocol,
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
            retry_orchestrator: Retry orchestrator for handling retries/fallbacks
            cache: Response cache for caching LLM responses
            output: Output interface for logging messages
            prompt_augmenter: Prompt augmenter for adding context and working memory
            batch_scheduler: Batch scheduler for parallel execution
            context_aware: Whether to augment prompts with context
        """
        self._retry_orchestrator = retry_orchestrator
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

        # Step 3: Create LLMRequest object (validates inputs)
        request = LLMRequest(
            prompt=final_prompt,
            provider=provider_name,
            model=model,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            use_context=use_context,
            use_cache=use_cache,
            intent_classification=intent_classification,
            auto_fallback=auto_fallback,
            kwargs=kwargs,
        )

        # Step 4: Execute with retry/fallback using SYNC method
        response, retry_metadata = self._retry_orchestrator.execute_with_retry_sync(
            request=request,
            excluded_providers=set(),
            max_retries=max_retries,
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

        # Step 6: Create final task record
        task_record = {
            'timestamp': datetime.now().isoformat(),
            'provider': retry_metadata['provider'],
            'model': retry_metadata['model'],
            'tokens_used': retry_metadata['tokens_used'],
            'latency_ms': retry_metadata['latency_ms'],
            'context_augmented': should_use_context,
            'cached': False,
            'async': False,
            'fallback': retry_metadata['fallback'],
            'attempts': retry_metadata['attempts'],
        }

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

        # Step 3: Create LLMRequest object (validates inputs)
        request = LLMRequest(
            prompt=final_prompt,
            provider=provider_name,
            model=model,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            use_context=use_context,
            use_cache=use_cache,
            intent_classification=intent_classification,
            auto_fallback=auto_fallback,
            kwargs=kwargs,
        )

        # Step 4: Execute with retry/fallback (delegate to RetryOrchestrator)
        response, retry_metadata = await self._retry_orchestrator.execute_with_retry(
            request=request,
            excluded_providers=set(),
            max_retries=max_retries,
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

        # Step 6: Create final task record
        task_record = {
            'timestamp': datetime.now().isoformat(),
            'provider': retry_metadata['provider'],
            'model': retry_metadata['model'],
            'tokens_used': retry_metadata['tokens_used'],
            'latency_ms': retry_metadata['latency_ms'],
            'context_augmented': should_use_context,
            'cached': False,
            'async': True,
            'fallback': retry_metadata['fallback'],
            'attempts': retry_metadata['attempts'],
        }

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
