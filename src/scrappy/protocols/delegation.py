"""
Delegation protocol definitions.

This module defines the contracts that all delegation-related components must follow.
All protocols use structural subtyping (PEP 544) for maximum flexibility and testability.

Following SOLID principles:
- Single Responsibility: Each protocol defines one cohesive behavior
- Open/Closed: Implementations can be swapped without modifying delegation logic
- Liskov Substitution: Any implementation satisfying the protocol can be used
- Interface Segregation: Protocols are minimal and focused
- Dependency Inversion: Delegation logic depends on abstractions, not concretions
"""

from typing import Protocol, Optional, Any
from dataclasses import dataclass


# Internal kwargs that should NOT be passed to provider APIs
# These are orchestration metadata, not provider parameters
INTERNAL_KWARGS = frozenset({
    'task_type',  # Internal hint for orchestration (e.g., 'planning', 'execution')
    'selection_type',  # ModelSelectionType used for provider selection (for fallback)
    'min_context',  # Minimum context length required (for fallback filtering)
    # Add future internal kwargs here
})


@dataclass(frozen=True)
class LLMRequest:
    """
    Value object representing a request to an LLM provider.

    Immutable to ensure request integrity throughout the delegation pipeline.
    """
    prompt: str
    provider: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    max_tokens: int = 1000
    temperature: float = 0.7
    use_context: Optional[bool] = None
    use_cache: Optional[bool] = None
    intent_classification: Optional[dict] = None
    auto_fallback: bool = True
    # Fallback metadata - helps maintain selection constraints during provider fallback
    selection_type: Optional[str] = None  # ModelSelectionType.value (e.g., 'quality', 'fast')
    min_context: int = 0  # Minimum context length required (0 = no constraint)
    kwargs: dict = None

    def __post_init__(self):
        """Validate request parameters and filter internal kwargs."""
        if self.kwargs is None:
            object.__setattr__(self, 'kwargs', {})
        else:
            # Filter out internal kwargs that should NOT be passed to provider API
            filtered_kwargs = {
                k: v for k, v in self.kwargs.items()
                if k not in INTERNAL_KWARGS
            }
            object.__setattr__(self, 'kwargs', filtered_kwargs)

        if not self.prompt or not self.prompt.strip():
            raise ValueError("prompt cannot be empty")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(f"temperature must be 0.0-2.0, got {self.temperature}")
        if self.max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {self.max_tokens}")


class PromptAugmenterProtocol(Protocol):
    """
    Augments prompts with contextual information.

    Responsibilities:
    - Add codebase context to prompts
    - Add working memory/recent interactions
    - Manage context window constraints

    Does NOT:
    - Make LLM calls
    - Cache responses
    - Handle retries
    """

    def augment(
        self,
        prompt: str,
        use_context: bool = True,
    ) -> str:
        """
        Augment a prompt with contextual information.

        Args:
            prompt: Original user prompt
            use_context: Whether to include codebase context

        Returns:
            Augmented prompt ready for LLM
        """
        ...


class CacheProtocol(Protocol):
    """
    Caches LLM responses to reduce API calls and costs.

    Responsibilities:
    - Store and retrieve cached responses
    - Generate cache keys from request parameters
    - Support semantic/intent-based caching
    - Handle cache invalidation

    Does NOT:
    - Make LLM calls
    - Handle retries
    - Augment prompts
    """

    def get(
        self,
        provider: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> Optional[Any]:
        """
        Get cached response if available.

        Args:
            provider: Provider name
            prompt: The prompt (potentially augmented)
            model: Model name
            system_prompt: System prompt
            max_tokens: Maximum tokens
            temperature: Temperature parameter

        Returns:
            Cached LLMResponse or None if not cached
        """
        ...

    def put(
        self,
        response: Any,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> None:
        """
        Store a response in the cache.

        Args:
            response: LLMResponse to cache
            prompt: The prompt used
            model: Model name
            system_prompt: System prompt
            max_tokens: Maximum tokens
            temperature: Temperature parameter
        """
        ...

    def get_by_intent(
        self,
        intent: str,
        entities: dict,
        keywords: list[str],
        provider: str,
        model: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Get cached response by semantic intent.

        Args:
            intent: Classified intent
            entities: Extracted entities
            keywords: Keywords from query
            provider: Provider name
            model: Model name

        Returns:
            Cached LLMResponse or None
        """
        ...

    def put_by_intent(
        self,
        response: Any,
        intent: str,
        entities: dict,
        keywords: list[str],
    ) -> None:
        """
        Store a response with intent metadata for semantic caching.

        Args:
            response: LLMResponse to cache
            intent: Classified intent
            entities: Extracted entities
            keywords: Keywords from query
        """
        ...


class RetryOrchestratorProtocol(Protocol):
    """
    Orchestrates retry logic with provider fallbacks.

    DEPRECATED: Use LLMServiceProtocol instead. LiteLLM Router handles
    retry and fallback logic internally. This protocol is kept for
    backward compatibility during migration.

    Responsibilities:
    - Execute requests with exponential backoff retries
    - Handle rate limit errors
    - Coordinate provider fallback on exhaustion
    - Track which providers have been attempted

    Does NOT:
    - Cache responses
    - Augment prompts
    - Manage parallel execution

    This is the core delegation logic extracted from DelegationManager.
    """

    async def execute_with_retry(
        self,
        request: LLMRequest,
        excluded_providers: set[str],
        max_retries: int = 3,
    ) -> tuple[Any, dict]:
        """
        Execute a request with retries and provider fallback (async).

        Args:
            request: The LLM request to execute
            excluded_providers: Providers already attempted (for fallback)
            max_retries: Maximum retry attempts per provider

        Returns:
            Tuple of (LLMResponse, task_record dict with metadata)

        Raises:
            RetryExhaustedError: When all providers and retries exhausted
            ProviderNotFoundError: When requested provider doesn't exist
            Other exceptions: For non-retryable errors
        """
        ...

    def execute_with_retry_sync(
        self,
        request: LLMRequest,
        excluded_providers: set[str],
        max_retries: int = 3,
    ) -> tuple[Any, dict]:
        """
        Execute a request with retries and provider fallback (sync).

        Synchronous version that uses provider.chat() directly instead of
        provider.chat_async(). Safe to call from any thread.

        Args:
            request: The LLM request to execute
            excluded_providers: Providers already attempted (for fallback)
            max_retries: Maximum retry attempts per provider

        Returns:
            Tuple of (LLMResponse, task_record dict with metadata)

        Raises:
            RetryExhaustedError: When all providers and retries exhausted
            ProviderNotFoundError: When requested provider doesn't exist
            Other exceptions: For non-retryable errors
        """
        ...


class BatchSchedulerProtocol(Protocol):
    """
    Schedules and executes parallel batch requests.

    Responsibilities:
    - Execute multiple requests in parallel
    - Manage concurrency limits
    - Coordinate multi-provider queries
    - Preserve request order in results

    Does NOT:
    - Handle single request retries (handled by LLMService via LiteLLM Router)
    - Cache responses (delegates to CacheProtocol)
    - Augment prompts (delegates to PromptAugmenter)
    """

    async def execute_batch(
        self,
        requests: list[LLMRequest],
        max_concurrent: int = 5,
    ) -> list[tuple[Any, dict]]:
        """
        Execute multiple requests in parallel.

        Args:
            requests: List of LLM requests
            max_concurrent: Maximum concurrent executions

        Returns:
            List of (LLMResponse, task_record) tuples in same order as requests
        """
        ...

    async def execute_multi_provider(
        self,
        request: LLMRequest,
        providers: list[str],
    ) -> dict[str, tuple[Any, dict]]:
        """
        Execute same request across multiple providers in parallel.

        Useful for comparing outputs or getting different perspectives.

        Args:
            request: The LLM request
            providers: List of provider names to query

        Returns:
            Dict mapping provider name to (LLMResponse, task_record) tuple
        """
        ...


class ProviderRegistryProtocol(Protocol):
    """
    Registry of available LLM providers.

    Responsibilities:
    - Store and retrieve provider instances
    - List available providers
    - Validate provider existence

    Does NOT:
    - Make LLM calls
    - Handle retries or fallbacks
    - Track rate limits
    """

    def get(self, name: str) -> Any:
        """
        Get a provider by name.

        Args:
            name: Provider name

        Returns:
            Provider instance

        Raises:
            KeyError: If provider not found
        """
        ...

    def list_available(self) -> list[str]:
        """
        List all available provider names.

        Returns:
            List of provider name strings
        """
        ...


class RateLimitTrackerProtocol(Protocol):
    """
    Tracks rate limits across providers.

    Responsibilities:
    - Record successful and failed requests
    - Track token usage
    - Monitor quota consumption
    - Detect approaching limits

    Does NOT:
    - Make LLM calls
    - Implement retry logic
    - Select providers
    """

    def record_request(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Record a request for rate limit tracking.

        Args:
            provider: Provider name
            model: Model name
            input_tokens: Input tokens used
            output_tokens: Output tokens used
            success: Whether request succeeded
            error_message: Error message if failed
        """
        ...

    def get_remaining_quota(
        self,
        provider: str,
        model: str,
        limits: Any,
    ) -> dict:
        """
        Get remaining quota for a provider/model.

        Args:
            provider: Provider name
            model: Model name
            limits: Provider limits object

        Returns:
            Dict with quota information like:
            {
                'requests_today_remaining': int,
                'tokens_remaining': int,
                ...
            }
        """
        ...

    def is_limit_approaching(
        self,
        provider: str,
        model: str,
        limits: Any,
    ) -> dict:
        """
        Check if provider is approaching rate limits.

        Args:
            provider: Provider name
            model: Model name
            limits: Provider limits object

        Returns:
            Dict with warning information like:
            {
                'warning': bool,
                'message': str,
                'percentage_used': float,
            }
        """
        ...


class ContextProviderProtocol(Protocol):
    """
    Provides contextual information about the codebase.

    Responsibilities:
    - Check if context is available/explored
    - Generate context strings for prompts
    - Manage context window size

    Does NOT:
    - Make LLM calls
    - Cache responses
    - Handle retries
    """

    def is_explored(self) -> bool:
        """
        Check if codebase context has been explored.

        Returns:
            True if context is available
        """
        ...

    def augment_prompt(self, prompt: str) -> str:
        """
        Augment a prompt with codebase context.

        Args:
            prompt: Original prompt

        Returns:
            Prompt with context prepended/appended
        """
        ...


class WorkingMemoryProtocol(Protocol):
    """
    Provides working memory / recent interaction context.

    Responsibilities:
    - Maintain recent conversation history
    - Generate context strings from history
    - Manage memory window size

    Does NOT:
    - Make LLM calls
    - Cache LLM responses
    - Handle retries
    """

    def get_context(self) -> str:
        """
        Get working memory context string.

        Returns:
            Context string summarizing recent interactions
        """
        ...


class OutputInterfaceProtocol(Protocol):
    """
    Output interface for logging and display.

    Responsibilities:
    - Display informational messages
    - Display warnings
    - Display errors

    Does NOT:
    - Make decisions about what to log
    - Format complex data structures
    - Handle retries or business logic
    """

    def print(self, message: str) -> None:
        """Print informational message."""
        ...

    def info(self, message: str) -> None:
        """Print info-level message."""
        ...

    def warn(self, message: str) -> None:
        """Print warning message."""
        ...

    def error(self, message: str) -> None:
        """Print error message."""
        ...


class ProviderSelectorProtocol(Protocol):
    """
    Selects providers for fallback logic.

    Responsibilities:
    - Choose next provider for fallback
    - Consider provider availability
    - Exclude already-attempted providers

    Does NOT:
    - Make LLM calls
    - Track rate limits
    - Implement retry logic
    """

    def get_provider_for_fallback(
        self,
        exclude: list[str],
    ) -> Optional[str]:
        """
        Get next provider to try for fallback.

        Args:
            exclude: Provider names already attempted

        Returns:
            Next provider name to try, or None if all exhausted
        """
        ...
