"""
DelegationManager - Handles LLM delegation with caching and prompt augmentation.

Refactored to follow SOLID principles:
- Single Responsibility: Coordinates delegation flow, delegates LLM calls to LLMService
- Open/Closed: Can extend by swapping protocol implementations
- Dependency Inversion: Depends on protocols, not concretions

After LiteLLM integration (Phase 3):
- Uses LLMServiceProtocol instead of RetryOrchestratorProtocol
- LiteLLM handles retry/fallback internally via Router configuration
- provider_name is now a model GROUP name ("fast", "chat", or "instruct")
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, AsyncIterator, Optional, Type, TypeVar, TYPE_CHECKING

from pydantic import BaseModel

from ..infrastructure.exceptions.provider_errors import AllProvidersRateLimitedError
from .protocols import (
    INTERNAL_KWARGS,
    BatchSchedulerProtocol,
    CacheProtocol,
    PromptAugmenterProtocol,
)
from .constants import (
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_TOKENS,
    DEFAULT_PROVIDER,
    DEFAULT_TEMPERATURE,
)
from .model_selection import MODEL_GROUPS
from .protocols import LLMServiceProtocol, StreamingCompletionProtocol, StructuredOutputProtocol
from .provider_types import LLMResponse
from .rate_limiting.protocols import (
    EnforcementAction,
    EnforcementPolicyProtocol,
    UserNotifierProtocol,
)
from .types import StreamChunk

if TYPE_CHECKING:
    from ..cli.protocols import BaseOutputProtocol as OutputInterfaceProtocol

# Type variable for generic structured output responses
T = TypeVar("T", bound=BaseModel)


# Map legacy provider names to model groups
PROVIDER_TO_GROUP = {
    "groq": "fast",
    "cerebras": "fast",
    "gemini": "instruct",
    "auto": "fast",
    "quality": "chat",  # Legacy name for 70B conversation tier
}


def _resolve_model_group(provider_name: str) -> str:
    """
    Resolve a provider name to a model group for LiteLLM Router.

    Args:
        provider_name: Provider name (could be legacy name like "groq" or group like "fast")

    Returns:
        Model group name ("fast", "chat", or "instruct")
    """
    # If it's already a valid model group, return as-is
    if provider_name in MODEL_GROUPS:
        return provider_name

    # Map legacy provider names to groups
    if provider_name in PROVIDER_TO_GROUP:
        return PROVIDER_TO_GROUP[provider_name]

    # Default to "fast" for unknown providers
    return "fast"


def _select_model_for_context(min_context: int, prefer_group: str = "quality") -> Optional[str]:
    """
    Select a specific model with sufficient context window.

    Used for proactive model selection when caller knows they need large context.
    Falls back to Gemini (1M context) for very large contexts.

    Args:
        min_context: Minimum required context window in tokens
        prefer_group: Preferred model group ("fast" or "quality")

    Returns:
        Specific model ID with sufficient context, or None if none found
    """
    from .litellm_config import MODEL_METADATA

    # Models ordered by context size (largest first for this use case)
    # Prefer models with good context that are also fast/reliable
    large_context_models = [
        ("gemini/gemini-2.5-flash", 1000000),
        ("groq/moonshotai/kimi-k2-instruct", 131072),
        ("cerebras/gpt-oss-120b", 131072),
        ("groq/llama-3.1-8b-instant", 131072),
        ("cerebras/qwen-3-235b-a22b-instruct-2507", 8192),
    ]

    for model_id, context_size in large_context_models:
        if context_size >= min_context:
            # Verify model is in metadata (configured)
            if model_id in MODEL_METADATA:
                return model_id

    return None


def _validate_concrete_model_context(model: str, min_context: int) -> None:
    """Raise if a concrete model cannot satisfy the requested context."""
    if min_context <= 0 or model in MODEL_GROUPS:
        return

    from .litellm_config import MODEL_METADATA

    metadata = MODEL_METADATA.get(model)
    if metadata is None:
        if "/" in model:
            raise ValueError(
                f"No context metadata available for concrete model '{model}'."
            )
        return

    if metadata.context_length < min_context:
        raise ValueError(
            f"Model '{model}' has {metadata.context_length} token context, "
            f"below required {min_context}."
        )


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
    - Pre-request enforcement (block exhausted providers proactively)

    Does NOT:
    - Implement prompt augmentation logic (delegates to PromptAugmenter)
    - Implement retry logic (handled by LiteLLM Router via LLMService)
    - Implement batch scheduling logic (delegates to BatchScheduler)
    - Implement provider selection (handled by LiteLLM Router)
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
        enforcement: Optional[EnforcementPolicyProtocol] = None,
        notifier: Optional[UserNotifierProtocol] = None,
        registry: Optional[Any] = None,
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
            enforcement: Optional enforcement policy for pre-request blocking
            notifier: Optional notifier for rate limit warnings
            registry: Optional provider registry for enforcement lookups
        """
        self._llm_service = llm_service
        self._cache = cache
        self._output = output
        self._prompt_augmenter = prompt_augmenter
        self._batch_scheduler = batch_scheduler
        self._context_aware = context_aware
        self._enforcement = enforcement
        self._notifier = notifier
        self._registry = registry

    def _check_enforcement(
        self,
        provider_name: str,
        model: Optional[str],
        estimated_tokens: int,
    ) -> tuple[str, Optional[str]]:
        """
        Check enforcement policy before making request.

        Args:
            provider_name: Requested provider
            model: Requested model
            estimated_tokens: Estimated token usage

        Returns:
            Tuple of (effective_provider, effective_model) to use

        Raises:
            AllProvidersRateLimitedError: If FAIL action returned
        """
        # Skip enforcement if not configured
        if self._enforcement is None or self._registry is None:
            return provider_name, model

        # Skip enforcement for model groups (let LiteLLM handle it)
        if provider_name in MODEL_GROUPS:
            return provider_name, model

        # Evaluate enforcement decision
        decision = self._enforcement.evaluate(
            provider=provider_name,
            model=model or "default",
            estimated_tokens=estimated_tokens,
            registry=self._registry,
        )

        # Handle decision
        if decision.action == EnforcementAction.ALLOW:
            return provider_name, model

        elif decision.action == EnforcementAction.WARN:
            # Notify user but proceed
            if self._notifier and decision.remaining_quota:
                remaining_pct = decision.remaining_quota.get("requests_remaining_today", 0) / 1000
                remaining_requests = decision.remaining_quota.get("requests_remaining_today", 0)
                self._notifier.notify_approaching_limit(
                    provider=provider_name,
                    remaining_percent=remaining_pct,
                    remaining_requests=remaining_requests,
                )
            return provider_name, model

        elif decision.action == EnforcementAction.BLOCK:
            # Use alternative provider if available
            if decision.alternative_provider:
                if self._notifier:
                    self._notifier.notify_fallback(
                        from_provider=provider_name,
                        to_provider=decision.alternative_provider,
                        reason=decision.reason,
                    )
                # Return alternative provider (model may need resolution)
                return decision.alternative_provider, None
            else:
                # No alternative - fall through to FAIL
                pass

        # FAIL or BLOCK with no alternative
        if self._notifier:
            self._notifier.notify_all_exhausted([provider_name])

        # Build provider details with wait time if available
        provider_details = {}
        if decision.wait_seconds:
            provider_details[provider_name] = {
                "retry_after": decision.wait_seconds,
                "error": decision.reason,
            }

        raise AllProvidersRateLimitedError(
            message="",  # Will be auto-generated with provider details
            attempted_providers=[provider_name],
            provider_details=provider_details,
        )

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
        messages: Optional[list[dict]] = None,
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
            auto_fallback: Deprecated compatibility parameter. Orchestrator-level
                dispatch owns fallback gating; this method accepts but ignores it.
            max_retries: Maximum retry attempts per provider
            selection_type: ModelSelectionType value for fallback filtering (e.g., 'quality')
            min_context: Minimum context length for fallback filtering
            messages: Pre-built messages array (bypasses prompt/system_prompt construction)
            **kwargs: Additional provider-specific arguments

        Returns:
            Tuple of (LLMResponse, task_record dict)

        Raises:
            AllProvidersRateLimitedError: If all providers are rate limited
            ValueError: If input validation fails
        """
        # If messages provided, use directly (skip augmentation, cache, prompt building)
        # This is used for multi-turn conversations where messages array is pre-built
        if messages is not None:
            # Determine model
            if model:
                effective_model = model
            else:
                effective_model = _resolve_model_group(provider_name)

            # Filter out internal kwargs
            filtered_kwargs = {k: v for k, v in kwargs.items() if k not in INTERNAL_KWARGS}

            # Execute directly with provided messages
            response, task_record = self._llm_service.completion_sync(
                model=effective_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **filtered_kwargs,
            )

            # Update task record
            task_record.update({
                'timestamp': datetime.now().isoformat(),
                'context_augmented': False,
                'cached': False,
                'async': False,
            })
            return response, task_record

        # Standard flow: augment prompt, check cache, build messages
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

        # Step 3: Check enforcement policy (pre-request blocking)
        # May redirect to alternative provider if quota exhausted
        effective_provider, effective_model_override = self._check_enforcement(
            provider_name=provider_name,
            model=model,
            estimated_tokens=max_tokens,
        )

        # Step 4: Determine model to use
        # If specific model provided (from ModelSelectionService), use it directly
        # Otherwise resolve provider_name to model group for Router
        if effective_model_override:
            _validate_concrete_model_context(effective_model_override, min_context)
            effective_model = effective_model_override
        elif model:
            # Specific model ID - use directly (e.g., "cerebras/qwen-3-235b-a22b-instruct-2507")
            _validate_concrete_model_context(model, min_context)
            effective_model = model
        elif min_context > 0:
            # Caller specified min context - select model with sufficient context
            context_model = _select_model_for_context(min_context)
            effective_model = context_model if context_model else _resolve_model_group(effective_provider)
        else:
            # Resolve to model group for LiteLLM Router (e.g., "fast", "quality")
            effective_model = _resolve_model_group(effective_provider)

        # Build messages list for LiteLLM
        final_messages = []
        if system_prompt:
            final_messages.append({"role": "system", "content": system_prompt})
        final_messages.append({"role": "user", "content": final_prompt})

        # Filter out internal kwargs that should NOT be passed to provider API
        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in INTERNAL_KWARGS}

        # Step 5: Execute via LLMService (LiteLLM Router handles retry/fallback)
        response, task_record = self._llm_service.completion_sync(
            model=effective_model,
            messages=final_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **filtered_kwargs,
        )

        # Step 6: Store in cache
        if should_use_cache:
            self._cache.put(response, final_prompt, model, system_prompt, max_tokens, temperature)
            if intent_classification:
                self._cache.put_by_intent(
                    response,
                    intent_classification.get('intent', ''),
                    intent_classification.get('entities', {}),
                    intent_classification.get('keywords', [])
                )

        # Step 7: Add context info to task record
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
            auto_fallback: Deprecated compatibility parameter. Orchestrator-level
                dispatch owns fallback gating; this method accepts but ignores it.
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

        # Step 3: Check enforcement policy (pre-request blocking)
        # May redirect to alternative provider if quota exhausted
        effective_provider, effective_model_override = self._check_enforcement(
            provider_name=provider_name,
            model=model,
            estimated_tokens=max_tokens,
        )

        # Step 4: Determine model to use
        # If specific model provided (from ModelSelectionService), use it directly
        # Otherwise resolve provider_name to model group for Router
        if effective_model_override:
            _validate_concrete_model_context(effective_model_override, min_context)
            effective_model = effective_model_override
        elif model:
            # Specific model ID - use directly (e.g., "cerebras/qwen-3-235b-a22b-instruct-2507")
            _validate_concrete_model_context(model, min_context)
            effective_model = model
        elif min_context > 0:
            # Caller specified min context - select model with sufficient context
            context_model = _select_model_for_context(min_context)
            effective_model = context_model if context_model else _resolve_model_group(effective_provider)
        else:
            # Resolve to model group for LiteLLM Router (e.g., "fast", "quality")
            effective_model = _resolve_model_group(effective_provider)

        # Build messages list for LiteLLM
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": final_prompt})

        # Filter out internal kwargs that should NOT be passed to provider API
        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in INTERNAL_KWARGS}

        # Step 5: Execute via LLMService (LiteLLM Router handles retry/fallback)
        response, task_record = await self._llm_service.completion(
            model=effective_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **filtered_kwargs,
        )

        # Step 6: Store in cache
        if should_use_cache:
            self._cache.put(response, final_prompt, model, system_prompt, max_tokens, temperature)
            if intent_classification:
                self._cache.put_by_intent(
                    response,
                    intent_classification.get('intent', ''),
                    intent_classification.get('entities', {}),
                    intent_classification.get('keywords', [])
                )

        # Step 7: Add context info to task record
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
        min_context: int = 0,
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

        # Step 3: Check enforcement policy (pre-request blocking)
        # May redirect to alternative provider if quota exhausted
        effective_provider, effective_model_override = self._check_enforcement(
            provider_name=provider_name,
            model=model,
            estimated_tokens=max_tokens,
        )

        # Step 4: Determine model to use
        # If specific model provided (from ModelSelectionService), use it directly
        # Otherwise resolve provider_name to model group for Router
        if effective_model_override:
            _validate_concrete_model_context(effective_model_override, min_context)
            effective_model = effective_model_override
        elif model:
            # Specific model ID - use directly (e.g., "cerebras/qwen-3-235b-a22b-instruct-2507")
            _validate_concrete_model_context(model, min_context)
            effective_model = model
        elif min_context > 0:
            # Caller specified min context - select model with sufficient context
            context_model = _select_model_for_context(min_context)
            effective_model = context_model if context_model else _resolve_model_group(effective_provider)
        else:
            # Resolve to model group for LiteLLM Router (e.g., "fast", "quality")
            effective_model = _resolve_model_group(effective_provider)

        # Build messages list for LiteLLM
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": final_prompt})

        # Filter out internal kwargs that should NOT be passed to provider API
        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in INTERNAL_KWARGS}

        # Step 5: Stream via LLMService (LiteLLM Router handles retry/fallback)
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
            model=effective_model,
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

        # Step 6: Store complete response in cache
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

    async def delegate_structured(
        self,
        provider_name: str,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        min_context: int = 0,
        **kwargs,
    ) -> T:
        """
        Async delegate with structured output validation using Instructor.

        Returns a validated Pydantic model instance instead of raw text.
        Uses the LLM service's completion_structured method which wraps
        Instructor for automatic validation and retry on parse failures.

        Note: This method does NOT use caching or prompt augmentation.
        It's designed for structured extraction tasks like classification
        where caching semantics differ from free-form text generation.

        Args:
            provider_name: Provider/model group to use ("fast", "quality", or legacy provider name)
            prompt: The user prompt to send
            response_model: Pydantic model class to validate response against
            system_prompt: Optional system prompt for behavioral instructions
            **kwargs: Additional params (max_retries, mode_override, etc.)

        Returns:
            Validated instance of response_model

        Raises:
            pydantic.ValidationError: If response cannot be validated after retries
            AllProvidersRateLimitedError: When all providers exhausted

        Example:
            from scrappy.orchestrator.models import TaskClassification

            result = await delegation_manager.delegate_structured(
                provider_name="fast",
                prompt="Classify: 'write a function to sort a list'",
                response_model=TaskClassification,
                system_prompt="Classify the user intent...",
            )
            # result is a validated TaskClassification instance
        """
        # Check if service supports structured output
        if not isinstance(self._llm_service, StructuredOutputProtocol):
            raise NotImplementedError(
                "LLM service does not support structured output. "
                "Ensure LiteLLMService is used instead of a mock."
            )

        if model:
            _validate_concrete_model_context(model, min_context)
            effective_model = model
        elif min_context > 0:
            context_model = _select_model_for_context(min_context)
            effective_model = context_model if context_model else _resolve_model_group(provider_name)
        else:
            effective_model = _resolve_model_group(provider_name)

        # Build messages list for LiteLLM
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in INTERNAL_KWARGS}

        # Delegate to LLM service's structured output method
        return await self._llm_service.completion_structured(
            model=effective_model,
            messages=messages,
            response_model=response_model,
            **filtered_kwargs,
        )

    def delegate_structured_sync(
        self,
        provider_name: str,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        min_context: int = 0,
        **kwargs,
    ) -> T:
        """
        Sync delegate with structured output validation using Instructor.

        This is the sync version for non-async contexts (like TaskRouter.classify).
        See delegate_structured for full documentation.

        Args:
            provider_name: Provider/model group to use ("fast", "quality", or legacy provider name)
            prompt: The user prompt to send
            response_model: Pydantic model class to validate response against
            system_prompt: Optional system prompt for behavioral instructions
            **kwargs: Additional params (max_retries, mode_override, etc.)

        Returns:
            Validated instance of response_model

        Raises:
            pydantic.ValidationError: If response cannot be validated after retries
            AllProvidersRateLimitedError: When all providers exhausted
        """
        # Check if service supports structured output
        if not hasattr(self._llm_service, 'completion_structured_sync'):
            raise NotImplementedError(
                "LLM service does not support sync structured output. "
                "Ensure LiteLLMService is used instead of a mock."
            )

        if model:
            _validate_concrete_model_context(model, min_context)
            effective_model = model
        elif min_context > 0:
            context_model = _select_model_for_context(min_context)
            effective_model = context_model if context_model else _resolve_model_group(provider_name)
        else:
            effective_model = _resolve_model_group(provider_name)

        # Build messages list for LiteLLM
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in INTERNAL_KWARGS}

        # Delegate to LLM service's sync structured output method
        return self._llm_service.completion_structured_sync(
            model=effective_model,
            messages=messages,
            response_model=response_model,
            **filtered_kwargs,
        )
