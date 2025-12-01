"""
RetryOrchestrator - Handles retry logic with provider fallbacks.

Extracted from DelegationManager to follow Single Responsibility Principle.
This class is responsible ONLY for:
- Executing requests with exponential backoff retries
- Handling rate limit errors
- Coordinating provider fallback on exhaustion
- Tracking which providers have been attempted

Does NOT:
- Cache responses (delegates to CacheProtocol)
- Augment prompts (delegates to PromptAugmenterProtocol)
- Manage parallel execution (delegates to BatchSchedulerProtocol)
"""

from typing import Optional, Any
import asyncio
import time

try:
    from ..protocols.delegation import (
        LLMRequest,
        RetryOrchestratorProtocol,
        ProviderRegistryProtocol,
        RateLimitTrackerProtocol,
        OutputInterfaceProtocol,
        ProviderSelectorProtocol,
    )
    from ..providers import LLMResponse
    from ..config import (
        DEFAULT_MAX_RETRIES,
        DEFAULT_QUOTA_THRESHOLD,
    )
    from ..infrastructure.exceptions import (
        RateLimitError,
        AllProvidersRateLimitedError,
        BaseError,
    )
    from ..infrastructure.error_recovery import RetryConfig
except ImportError:
    from protocols.delegation import (
        LLMRequest,
        RetryOrchestratorProtocol,
        ProviderRegistryProtocol,
        RateLimitTrackerProtocol,
        OutputInterfaceProtocol,
        ProviderSelectorProtocol,
    )
    from providers import LLMResponse
    from config import (
        DEFAULT_MAX_RETRIES,
        DEFAULT_QUOTA_THRESHOLD,
    )
    from infrastructure.exceptions import (
        RateLimitError,
        AllProvidersRateLimitedError,
        BaseError,
    )
    from infrastructure.error_recovery import RetryConfig


class RetryOrchestrator:
    """
    Orchestrates retry logic with provider fallbacks.

    Implements RetryOrchestratorProtocol following SOLID principles:
    - Single Responsibility: Only handles retry/fallback logic
    - Open/Closed: Strategy can be extended without modification
    - Liskov Substitution: Implements protocol contract
    - Interface Segregation: Protocol is minimal and focused
    - Dependency Inversion: Depends on protocol abstractions, not concretions
    """

    def __init__(
        self,
        *,
        registry: ProviderRegistryProtocol,
        rate_tracker: RateLimitTrackerProtocol,
        provider_selector: ProviderSelectorProtocol,
        output: OutputInterfaceProtocol,
        retry_config: Optional[RetryConfig] = None,
    ):
        """
        Initialize RetryOrchestrator.

        All dependencies are injected - NO instantiation inside constructor.

        Args:
            registry: Provider registry for accessing LLM providers
            rate_tracker: Rate limit tracker for monitoring usage
            provider_selector: Provider selector for fallback logic
            output: Output interface for logging messages
            retry_config: Optional retry configuration (uses default if not provided)
        """
        self._registry = registry
        self._rate_tracker = rate_tracker
        self._provider_selector = provider_selector
        self._output = output
        # Use infrastructure's unified retry config (matches legacy: 0.5s * 2^attempt)
        self._retry_config = retry_config or RetryConfig(
            max_retries=DEFAULT_MAX_RETRIES,
            base_delay=0.5,
            multiplier=2.0,
            max_delay=60.0,
            jitter=False  # Keep deterministic behavior for now
        )

    async def execute_with_retry(
        self,
        request: LLMRequest,
        excluded_providers: set[str],
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> tuple[LLMResponse, dict]:
        """
        Execute a request with retries and provider fallback.

        This is the core delegation logic extracted from DelegationManager.
        It handles:
        1. Provider selection (initial or fallback)
        2. Proactive quota checking
        3. Request execution with exponential backoff
        4. Rate limit error handling
        5. Provider fallback on exhaustion

        Args:
            request: The LLM request to execute
            excluded_providers: Providers already attempted (for fallback)
            max_retries: Maximum retry attempts per provider

        Returns:
            Tuple of (LLMResponse, task_record dict with metadata)

        Raises:
            AllProvidersRateLimitedError: When all providers and retries exhausted
            RateLimitError: When rate limits are hit
            KeyError: When requested provider doesn't exist
            Other exceptions: For non-retryable errors
        """
        # Track which providers we've tried
        attempted_providers = list(excluded_providers)
        current_provider_name = request.provider
        current_model = request.model

        # If no provider specified or provider already excluded, get a fallback
        if not current_provider_name or current_provider_name in excluded_providers:
            current_provider_name = self._provider_selector.get_provider_for_fallback(
                exclude=attempted_providers
            )
            if current_provider_name is None:
                self._output.error(
                    f"All providers exhausted. Attempted: {attempted_providers}"
                )
                raise AllProvidersRateLimitedError(
                    message="All providers exhausted",
                    attempted_providers=attempted_providers,
                )

        # Build messages for the LLM call
        messages = []
        if request.system_prompt:
            messages.append({'role': 'system', 'content': request.system_prompt})
        messages.append({'role': 'user', 'content': request.prompt})

        # Keep trying providers until one succeeds
        while True:
            provider = self._registry.get(current_provider_name)

            # Proactive limit check
            try:
                provider_limits = provider.get_limits()
                remaining = self._rate_tracker.get_remaining_quota(
                    current_provider_name,
                    current_model or provider.default_model,
                    provider_limits
                )

                if remaining.get('requests_today_remaining', DEFAULT_QUOTA_THRESHOLD) <= 0:
                    self._output.warn(
                        f"{current_provider_name} has exhausted daily quota, trying fallback..."
                    )
                    raise RateLimitError(
                        message="Daily quota exhausted",
                        provider_name=current_provider_name,
                    )
            except RateLimitError:
                raise
            except Exception as e:
                self._output.warn(
                    f"Proactive limit check failed for {current_provider_name}: {e}"
                )

            # Try the current provider with retries
            last_error = None
            for attempt in range(max_retries):
                try:
                    response = await provider.chat_async(
                        messages=messages,
                        model=current_model,
                        max_tokens=request.max_tokens,
                        temperature=request.temperature,
                        **request.kwargs
                    )

                    # Success! Track rate limits
                    self._rate_tracker.record_request(
                        provider=current_provider_name,
                        model=response.model,
                        input_tokens=response.input_tokens,
                        output_tokens=response.output_tokens,
                        success=True
                    )

                    # Check for approaching limits
                    warnings = self._rate_tracker.is_limit_approaching(
                        current_provider_name, response.model, provider_limits
                    )
                    if warnings.get('message'):
                        response.metadata['rate_limit_warning'] = warnings['message']

                    # Add fallback info if we switched providers
                    if current_provider_name != request.provider:
                        response.metadata['fallback_from'] = request.provider
                        response.metadata['fallback_to'] = current_provider_name
                        response.metadata['attempted_providers'] = attempted_providers

                    # Create task record
                    task_record = {
                        'provider': current_provider_name,
                        'model': response.model,
                        'tokens_used': response.tokens_used,
                        'latency_ms': response.latency_ms,
                        'fallback': current_provider_name != request.provider,
                        'attempts': attempt + 1,
                    }

                    return response, task_record

                except Exception as e:
                    last_error = e

                    # Type-based error classification (replaces string matching)
                    is_retryable = False
                    if isinstance(e, BaseError):
                        # Use new infrastructure's is_retryable property
                        is_retryable = e.is_retryable
                    elif isinstance(e, RateLimitError):
                        # Infrastructure rate limit errors are always retryable
                        is_retryable = True
                    else:
                        # For unknown errors, check if it looks like a rate limit
                        # (fallback for provider exceptions not yet wrapped)
                        error_str = str(e).lower()
                        is_retryable = any(
                            indicator in error_str
                            for indicator in [
                                '429', 'rate limit', 'rate_limit', 'ratelimit',
                                'quota', 'too many requests', 'resource exhausted',
                                'resource_exhausted', 'capacity', 'throttl',
                                'requests per', 'tokens per', 'limit exceeded'
                            ]
                        )

                    if is_retryable:
                        # Record the failed request
                        self._rate_tracker.record_request(
                            provider=current_provider_name,
                            model=current_model or provider.default_model,
                            input_tokens=0,
                            output_tokens=0,
                            success=False,
                            error_message=str(e)
                        )

                        # Exponential backoff using unified infrastructure config
                        if attempt < max_retries - 1:
                            wait_time = self._retry_config.calculate_delay(attempt)
                            self._output.warn(
                                f"Rate limit hit on {current_provider_name}, "
                                f"retrying in {wait_time:.1f}s "
                                f"(attempt {attempt + 1}/{max_retries})..."
                            )
                            await asyncio.sleep(wait_time)
                        else:
                            self._output.warn(
                                f"Rate limit persists on {current_provider_name} "
                                f"after {max_retries} attempts"
                            )
                            break
                    else:
                        # Non-retryable error - raise immediately
                        raise

            # Exhausted retries for current provider
            attempted_providers.append(current_provider_name)

            # Check if auto_fallback is disabled
            if not request.auto_fallback:
                # Don't fallback - raise the last error
                if last_error:
                    raise last_error
                else:
                    raise RateLimitError(
                        message=f"Rate limit exceeded after {max_retries} retries (auto_fallback=False)",
                        provider_name=current_provider_name,
                    )

            # Get next fallback provider
            fallback_provider = self._provider_selector.get_provider_for_fallback(
                exclude=attempted_providers
            )

            if fallback_provider is None:
                self._output.error(
                    f"All providers rate limited. Attempted: {attempted_providers}"
                )
                raise AllProvidersRateLimitedError(
                    message="All providers rate limited",
                    attempted_providers=attempted_providers,
                )

            self._output.info(
                f"[FALLBACK] Switching from {current_provider_name} to {fallback_provider}"
            )
            current_provider_name = fallback_provider
            current_model = None  # Reset to provider default

    def execute_with_retry_sync(
        self,
        request: LLMRequest,
        excluded_providers: set[str],
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> tuple["LLMResponse", dict]:
        """
        Execute a request with retries and provider fallback (synchronous).

        This is the sync version of execute_with_retry. It uses provider.chat()
        directly instead of provider.chat_async(), making it safe to call from
        any thread (including Textual worker threads).

        Args:
            request: The LLM request to execute
            excluded_providers: Providers already attempted (for fallback)
            max_retries: Maximum retry attempts per provider

        Returns:
            Tuple of (LLMResponse, task_record dict with metadata)

        Raises:
            AllProvidersRateLimitedError: When all providers and retries exhausted
            RateLimitError: When rate limits are hit
            KeyError: When requested provider doesn't exist
            Other exceptions: For non-retryable errors
        """
        # Track which providers we've tried
        attempted_providers = list(excluded_providers)
        current_provider_name = request.provider
        current_model = request.model

        # If no provider specified or provider already excluded, get a fallback
        if not current_provider_name or current_provider_name in excluded_providers:
            current_provider_name = self._provider_selector.get_provider_for_fallback(
                exclude=attempted_providers
            )
            if current_provider_name is None:
                self._output.error(
                    f"All providers exhausted. Attempted: {attempted_providers}"
                )
                raise AllProvidersRateLimitedError(
                    message="All providers exhausted",
                    attempted_providers=attempted_providers,
                )

        # Build messages for the LLM call
        messages = []
        if request.system_prompt:
            messages.append({'role': 'system', 'content': request.system_prompt})
        messages.append({'role': 'user', 'content': request.prompt})

        # Keep trying providers until one succeeds
        while True:
            provider = self._registry.get(current_provider_name)

            # Proactive limit check
            try:
                provider_limits = provider.get_limits()
                remaining = self._rate_tracker.get_remaining_quota(
                    current_provider_name,
                    current_model or provider.default_model,
                    provider_limits
                )

                if remaining.get('requests_today_remaining', DEFAULT_QUOTA_THRESHOLD) <= 0:
                    self._output.warn(
                        f"{current_provider_name} has exhausted daily quota, trying fallback..."
                    )
                    raise RateLimitError(
                        message="Daily quota exhausted",
                        provider_name=current_provider_name,
                    )
            except RateLimitError:
                raise
            except Exception as e:
                self._output.warn(
                    f"Proactive limit check failed for {current_provider_name}: {e}"
                )

            # Try the current provider with retries
            last_error = None
            for attempt in range(max_retries):
                try:
                    # Use sync chat() method instead of chat_async()
                    response = provider.chat(
                        messages=messages,
                        model=current_model,
                        max_tokens=request.max_tokens,
                        temperature=request.temperature,
                        **request.kwargs
                    )

                    # Success! Track rate limits
                    self._rate_tracker.record_request(
                        provider=current_provider_name,
                        model=response.model,
                        input_tokens=response.input_tokens,
                        output_tokens=response.output_tokens,
                        success=True
                    )

                    # Check for approaching limits
                    warnings = self._rate_tracker.is_limit_approaching(
                        current_provider_name, response.model, provider_limits
                    )
                    if warnings.get('message'):
                        response.metadata['rate_limit_warning'] = warnings['message']

                    # Add fallback info if we switched providers
                    if current_provider_name != request.provider:
                        response.metadata['fallback_from'] = request.provider
                        response.metadata['fallback_to'] = current_provider_name
                        response.metadata['attempted_providers'] = attempted_providers

                    # Create task record
                    task_record = {
                        'provider': current_provider_name,
                        'model': response.model,
                        'tokens_used': response.tokens_used,
                        'latency_ms': response.latency_ms,
                        'fallback': current_provider_name != request.provider,
                        'attempts': attempt + 1,
                    }

                    return response, task_record

                except Exception as e:
                    last_error = e

                    # Type-based error classification
                    is_retryable = False
                    if isinstance(e, BaseError):
                        is_retryable = e.is_retryable
                    elif isinstance(e, RateLimitError):
                        is_retryable = True
                    else:
                        error_str = str(e).lower()
                        is_retryable = any(
                            indicator in error_str
                            for indicator in [
                                '429', 'rate limit', 'rate_limit', 'ratelimit',
                                'quota', 'too many requests', 'resource exhausted',
                                'resource_exhausted', 'capacity', 'throttl',
                                'requests per', 'tokens per', 'limit exceeded'
                            ]
                        )

                    if is_retryable:
                        # Record the failed request
                        self._rate_tracker.record_request(
                            provider=current_provider_name,
                            model=current_model or provider.default_model,
                            input_tokens=0,
                            output_tokens=0,
                            success=False,
                            error_message=str(e)
                        )

                        # Exponential backoff using sync sleep
                        if attempt < max_retries - 1:
                            wait_time = self._retry_config.calculate_delay(attempt)
                            self._output.warn(
                                f"Rate limit hit on {current_provider_name}, "
                                f"retrying in {wait_time:.1f}s "
                                f"(attempt {attempt + 1}/{max_retries})..."
                            )
                            time.sleep(wait_time)  # Sync sleep instead of asyncio.sleep
                        else:
                            self._output.warn(
                                f"Rate limit persists on {current_provider_name} "
                                f"after {max_retries} attempts"
                            )
                            break
                    else:
                        # Non-retryable error - raise immediately
                        raise

            # Exhausted retries for current provider
            attempted_providers.append(current_provider_name)

            # Check if auto_fallback is disabled
            if not request.auto_fallback:
                if last_error:
                    raise last_error
                else:
                    raise RateLimitError(
                        message=f"Rate limit exceeded after {max_retries} retries (auto_fallback=False)",
                        provider_name=current_provider_name,
                    )

            # Get next fallback provider
            fallback_provider = self._provider_selector.get_provider_for_fallback(
                exclude=attempted_providers
            )

            if fallback_provider is None:
                self._output.error(
                    f"All providers rate limited. Attempted: {attempted_providers}"
                )
                raise AllProvidersRateLimitedError(
                    message="All providers rate limited",
                    attempted_providers=attempted_providers,
                )

            self._output.info(
                f"[FALLBACK] Switching from {current_provider_name} to {fallback_provider}"
            )
            current_provider_name = fallback_provider
            current_model = None  # Reset to provider default
