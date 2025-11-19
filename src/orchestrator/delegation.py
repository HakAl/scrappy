"""
DelegationManager - Handles LLM delegation with retry/fallback logic.

Extracted from AgentOrchestrator to separate delegation concerns.
"""

from typing import Optional, Callable
from datetime import datetime
import asyncio
import time

try:
    from ..providers import ProviderRegistry, LLMResponse
    from ..utils.errors import is_rate_limit_error, RateLimitError, AllProvidersRateLimitedError
except ImportError:
    from providers import ProviderRegistry, LLMResponse
    from utils.errors import is_rate_limit_error, RateLimitError, AllProvidersRateLimitedError

from .cache import ResponseCache
from .rate_limiter import RateLimitTracker
from .provider_selector import ProviderSelector
from .output import OutputInterface, NullOutput


class DelegationManager:
    """
    Handles LLM delegation with retry/fallback logic.

    Responsible for:
    - Delegating prompts to LLM providers
    - Handling rate limit retries with exponential backoff
    - Falling back to alternative providers on quota exhaustion
    - Managing cache interactions
    - Tracking request metrics
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        cache: ResponseCache,
        rate_tracker: RateLimitTracker,
        provider_selector: ProviderSelector,
        output: Optional[OutputInterface] = None,
        context: Optional[object] = None,
        context_aware: bool = False,
        get_working_memory_context: Optional[Callable[[], str]] = None,
    ):
        """
        Initialize DelegationManager.

        Args:
            registry: Provider registry for accessing LLM providers
            cache: Response cache for caching LLM responses
            rate_tracker: Rate limit tracker for monitoring usage
            provider_selector: Provider selector for fallback logic
            output: Output interface for logging messages
            context: Codebase context for prompt augmentation
            context_aware: Whether to augment prompts with context
            get_working_memory_context: Callable to get working memory context string
        """
        self.registry = registry
        self.cache = cache
        self.rate_tracker = rate_tracker
        self.provider_selector = provider_selector
        self.output = output or NullOutput()
        self.context = context
        self.context_aware = context_aware
        self._get_working_memory_context = get_working_memory_context or (lambda: "")

    def delegate(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        use_context: Optional[bool] = None,
        use_cache: Optional[bool] = None,
        intent_classification: Optional[dict] = None,
        auto_fallback: bool = True,
        max_retries: int = 3,
        **kwargs
    ) -> tuple[LLMResponse, dict]:
        """
        Delegate a task to a specific provider with automatic fallback on rate limits.

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
            RateLimitError: If proactive quota check fails
            Exception: Other non-rate-limit errors
        """
        # Determine settings
        should_use_context = use_context if use_context is not None else self.context_aware
        should_use_cache = use_cache if use_cache is not None else True

        # Augment prompt with context if enabled
        final_prompt = prompt
        if should_use_context:
            if self.context and hasattr(self.context, 'is_explored') and self.context.is_explored():
                final_prompt = self.context.augment_prompt(prompt)

            # Add working memory context
            working_memory_context = self._get_working_memory_context()
            if working_memory_context:
                final_prompt = working_memory_context + "\n\n" + final_prompt

        # Check cache first
        cached_response = None
        intent_cache_hit = False
        if should_use_cache:
            cached_response = self.cache.get(
                provider_name, final_prompt, model, system_prompt, max_tokens, temperature
            )
            if not cached_response and intent_classification:
                cached_response = self.cache.get_by_intent(
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
            }
            return cached_response, task_record

        # Build messages
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': final_prompt})

        # Track which providers we've tried
        attempted_providers = []
        current_provider_name = provider_name
        current_model = model

        while True:
            provider = self.registry.get(current_provider_name)

            # Proactive limit check
            try:
                provider_limits = provider.get_limits()
                remaining = self.rate_tracker.get_remaining_quota(
                    current_provider_name, current_model or provider.default_model, provider_limits
                )

                if remaining.get('requests_today_remaining', 100) <= 0:
                    self.output.warn(f"{current_provider_name} has exhausted daily quota, trying fallback...")
                    raise RateLimitError(current_provider_name, "Daily quota exhausted", "requests")
            except RateLimitError:
                raise
            except Exception as e:
                self.output.warn(f"Proactive limit check failed for {current_provider_name}: {e}")

            # Try the current provider with retries
            last_error = None
            for attempt in range(max_retries):
                try:
                    response = provider.chat(
                        messages=messages,
                        model=current_model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        **kwargs
                    )

                    # Success! Store in cache
                    if should_use_cache:
                        self.cache.put(response, final_prompt, current_model, system_prompt, max_tokens, temperature)
                        if intent_classification:
                            self.cache.put_by_intent(
                                response,
                                intent_classification.get('intent', ''),
                                intent_classification.get('entities', {}),
                                intent_classification.get('keywords', [])
                            )

                    # Track rate limits
                    self.rate_tracker.record_request(
                        provider=current_provider_name,
                        model=response.model,
                        input_tokens=response.input_tokens,
                        output_tokens=response.output_tokens,
                        success=True
                    )

                    # Check for approaching limits
                    warnings = self.rate_tracker.is_limit_approaching(
                        current_provider_name, response.model, provider_limits
                    )
                    if warnings.get('message'):
                        response.metadata['rate_limit_warning'] = warnings['message']

                    # Add fallback info if we switched providers
                    if current_provider_name != provider_name:
                        response.metadata['fallback_from'] = provider_name
                        response.metadata['fallback_to'] = current_provider_name
                        response.metadata['attempted_providers'] = attempted_providers

                    # Create task record
                    task_record = {
                        'timestamp': datetime.now().isoformat(),
                        'provider': current_provider_name,
                        'model': response.model,
                        'tokens_used': response.tokens_used,
                        'latency_ms': response.latency_ms,
                        'context_augmented': should_use_context,
                        'cached': False,
                        'fallback': current_provider_name != provider_name,
                        'attempts': attempt + 1,
                    }

                    return response, task_record

                except Exception as e:
                    last_error = e

                    if is_rate_limit_error(e):
                        # Record the failed request
                        self.rate_tracker.record_request(
                            provider=current_provider_name,
                            model=current_model or provider.default_model,
                            input_tokens=0,
                            output_tokens=0,
                            success=False,
                            error_message=str(e)
                        )

                        if attempt < max_retries - 1:
                            wait_time = (2 ** attempt) * 0.5
                            self.output.warn(f"Rate limit hit on {current_provider_name}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})...")
                            time.sleep(wait_time)
                        else:
                            self.output.warn(f"Rate limit persists on {current_provider_name} after {max_retries} attempts")
                            break
                    else:
                        raise

            # Exhausted retries for current provider
            attempted_providers.append(current_provider_name)

            if not auto_fallback:
                raise last_error

            # Get next fallback provider
            fallback_provider = self.provider_selector.get_provider_for_fallback(exclude=attempted_providers)

            if fallback_provider is None:
                self.output.error(f"All providers rate limited. Attempted: {attempted_providers}")
                raise AllProvidersRateLimitedError(attempted_providers)

            self.output.info(f"[FALLBACK] Switching from {current_provider_name} to {fallback_provider}")
            current_provider_name = fallback_provider
            current_model = None

    async def delegate_async(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        use_context: Optional[bool] = None,
        use_cache: Optional[bool] = None,
        intent_classification: Optional[dict] = None,
        auto_fallback: bool = True,
        max_retries: int = 3,
        **kwargs
    ) -> tuple[LLMResponse, dict]:
        """
        Async version of delegate with automatic fallback on rate limits.

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
            RateLimitError: If proactive quota check fails
            Exception: Other non-rate-limit errors
        """
        # Determine settings
        should_use_context = use_context if use_context is not None else self.context_aware
        should_use_cache = use_cache if use_cache is not None else True

        # Augment prompt with context if enabled
        final_prompt = prompt
        if should_use_context:
            if self.context and hasattr(self.context, 'is_explored') and self.context.is_explored():
                final_prompt = self.context.augment_prompt(prompt)

            working_memory_context = self._get_working_memory_context()
            if working_memory_context:
                final_prompt = working_memory_context + "\n\n" + final_prompt

        # Check cache first
        cached_response = None
        intent_cache_hit = False
        if should_use_cache:
            cached_response = self.cache.get(
                provider_name, final_prompt, model, system_prompt, max_tokens, temperature
            )
            if not cached_response and intent_classification:
                cached_response = self.cache.get_by_intent(
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

        # Build messages
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': final_prompt})

        # Track which providers we've tried
        attempted_providers = []
        current_provider_name = provider_name
        current_model = model

        while True:
            provider = self.registry.get(current_provider_name)

            # Proactive limit check
            try:
                provider_limits = provider.get_limits()
                remaining = self.rate_tracker.get_remaining_quota(
                    current_provider_name, current_model or provider.default_model, provider_limits
                )

                if remaining.get('requests_today_remaining', 100) <= 0:
                    self.output.warn(f"{current_provider_name} has exhausted daily quota, trying fallback...")
                    raise RateLimitError(current_provider_name, "Daily quota exhausted", "requests")
            except RateLimitError:
                raise
            except Exception as e:
                self.output.warn(f"Proactive limit check failed for {current_provider_name}: {e}")

            # Try the current provider with retries
            last_error = None
            for attempt in range(max_retries):
                try:
                    response = await provider.chat_async(
                        messages=messages,
                        model=current_model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        **kwargs
                    )

                    # Success! Store in cache (can be done async)
                    if should_use_cache:
                        self.cache.put(response, final_prompt, current_model, system_prompt, max_tokens, temperature)
                        if intent_classification:
                            self.cache.put_by_intent(
                                response,
                                intent_classification.get('intent', ''),
                                intent_classification.get('entities', {}),
                                intent_classification.get('keywords', [])
                            )

                    # Track rate limits
                    self.rate_tracker.record_request(
                        provider=current_provider_name,
                        model=response.model,
                        input_tokens=response.input_tokens,
                        output_tokens=response.output_tokens,
                        success=True
                    )

                    # Check for approaching limits
                    warnings = self.rate_tracker.is_limit_approaching(
                        current_provider_name, response.model, provider_limits
                    )
                    if warnings.get('message'):
                        response.metadata['rate_limit_warning'] = warnings['message']

                    # Add fallback info if we switched providers
                    if current_provider_name != provider_name:
                        response.metadata['fallback_from'] = provider_name
                        response.metadata['fallback_to'] = current_provider_name
                        response.metadata['attempted_providers'] = attempted_providers

                    # Create task record
                    task_record = {
                        'timestamp': datetime.now().isoformat(),
                        'provider': current_provider_name,
                        'model': response.model,
                        'tokens_used': response.tokens_used,
                        'latency_ms': response.latency_ms,
                        'context_augmented': should_use_context,
                        'cached': False,
                        'async': True,
                        'fallback': current_provider_name != provider_name,
                        'attempts': attempt + 1,
                    }

                    return response, task_record

                except Exception as e:
                    last_error = e

                    if is_rate_limit_error(e):
                        self.rate_tracker.record_request(
                            provider=current_provider_name,
                            model=current_model or provider.default_model,
                            input_tokens=0,
                            output_tokens=0,
                            success=False,
                            error_message=str(e)
                        )

                        if attempt < max_retries - 1:
                            wait_time = (2 ** attempt) * 0.5
                            self.output.warn(f"Rate limit hit on {current_provider_name}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})...")
                            await asyncio.sleep(wait_time)
                        else:
                            self.output.warn(f"Rate limit persists on {current_provider_name} after {max_retries} attempts")
                            break
                    else:
                        raise

            # Exhausted retries for current provider
            attempted_providers.append(current_provider_name)

            if not auto_fallback:
                raise last_error

            # Get next fallback provider
            fallback_provider = self.provider_selector.get_provider_for_fallback(exclude=attempted_providers)

            if fallback_provider is None:
                self.output.error(f"All providers rate limited. Attempted: {attempted_providers}")
                raise AllProvidersRateLimitedError(attempted_providers)

            self.output.info(f"[FALLBACK] Switching from {current_provider_name} to {fallback_provider}")
            current_provider_name = fallback_provider
            current_model = None

    def delegate_batch(
        self,
        tasks: list[dict],
        provider_name: str = 'groq',
        **kwargs
    ) -> list[LLMResponse]:
        """
        Process multiple tasks with same provider.

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
                provider_name,
                task['prompt'],
                system_prompt=task.get('system_prompt'),
                **task_kwargs
            )
            results.append(result)
        return results

    async def batch_delegate_async(
        self,
        tasks: list[dict],
        provider_name: str = 'groq',
        max_concurrent: int = 5
    ) -> list[LLMResponse]:
        """
        Process multiple tasks in parallel using async.

        Args:
            tasks: List of task dicts with 'prompt' and optional 'system_prompt', 'kwargs'
            provider_name: Provider to use for all tasks
            max_concurrent: Maximum number of concurrent requests

        Returns:
            List of LLMResponse objects in the same order as input tasks
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_task(task):
            async with semaphore:
                result, _ = await self.delegate_async(
                    provider_name,
                    task['prompt'],
                    system_prompt=task.get('system_prompt'),
                    **task.get('kwargs', {})
                )
                return result

        results = await asyncio.gather(*[process_task(task) for task in tasks])
        return list(results)

    async def multi_provider_query_async(
        self,
        prompt: str,
        providers: list[str] = None,
        **kwargs
    ) -> dict[str, tuple]:
        """
        Query multiple providers in parallel for the same prompt.

        Useful for getting different perspectives or comparing outputs.

        Args:
            prompt: The prompt to send to all providers
            providers: List of provider names (defaults to all available)
            **kwargs: Additional arguments passed to delegate_async

        Returns:
            Dict mapping provider name to (LLMResponse, task_record) tuple
        """
        if providers is None:
            providers = self.registry.list_available()

        async def query_provider(provider_name):
            try:
                response = await self.delegate_async(provider_name, prompt, **kwargs)
                return provider_name, response
            except Exception as e:
                self.output.warn(f"{provider_name} failed: {e}")
                return provider_name, None

        results = await asyncio.gather(*[query_provider(p) for p in providers])
        return {name: response for name, response in results if response is not None}

    def run_async(self, coro):
        """
        Helper to run async code from sync context.

        Usage:
            results = manager.run_async(manager.batch_delegate_async(tasks))
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, create a new task
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(coro)
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            # No event loop, create a new one
            return asyncio.run(coro)
