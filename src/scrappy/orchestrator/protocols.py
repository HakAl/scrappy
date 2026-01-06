"""
Protocols for orchestrator module.

Defines abstract interfaces (Protocols) for orchestrator implementations,
enabling loose coupling and better testability throughout the codebase.
"""

from typing import Protocol, Optional, Dict, Any, List, runtime_checkable, AsyncIterator, Type, TypeVar

from pydantic import BaseModel

from ..providers.base import LLMResponse, LLMProviderBase, ProviderLimits
from .types import StreamChunk

# Type variable for generic structured output responses
T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class Orchestrator(Protocol):
    """
    Protocol for orchestrator implementations.

    Defines the minimal interface required for an orchestrator that can
    delegate tasks to LLM providers and report usage statistics.

    This protocol enables:
    - Type hints that accept any conforming implementation
    - Easy substitution of test mocks for unit testing
    - Loose coupling between components and the orchestrator

    Implementations:
    - AgentOrchestrator: Full-featured multi-provider orchestrator
    - ConfigurableTestOrchestrator: Test mock in tests/helpers.py
    """

    def delegate(
        self,
        provider_name: Optional[str] = None,
        prompt: str = "",
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        messages: Optional[list[dict]] = None,
        **kwargs: Any
    ) -> LLMResponse:
        """
        Delegate a task to an LLM provider.

        Args:
            provider_name: Target provider (None for auto-selection)
            prompt: The prompt to send to the LLM
            model: Specific model to use (None for provider default)
            system_prompt: System prompt for context
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            messages: Pre-built messages array (bypasses prompt/system_prompt)
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMResponse with the provider's response
        """
        ...

    async def delegate_async(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs: Any
    ) -> LLMResponse:
        """
        Asynchronously delegate a task to an LLM provider.

        Args:
            provider_name: Target provider
            prompt: The prompt to send to the LLM
            model: Specific model to use (None for provider default)
            system_prompt: System prompt for context
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMResponse with the provider's response
        """
        ...

    def get_usage_report(self) -> Dict[str, Any]:
        """
        Get usage statistics report.

        Returns:
            Dictionary containing usage statistics including:
            - total_tasks: Total tasks delegated
            - by_provider: Per-provider breakdown
            - cache_stats: Cache hit/miss statistics
        """
        ...


@runtime_checkable
class CacheProtocol(Protocol):
    """
    Protocol for response caching.

    Abstracts caching behavior to enable testing with different cache
    implementations and strategies.

    Implementations:
    - ResponseCache: File-based caching with TTL
    - InMemoryCache: In-memory caching for testing
    - NullCache: No-op cache for disabling caching

    Example:
        def get_response(cache: CacheProtocol, provider: str, prompt: str) -> Optional[LLMResponse]:
            return cache.get(provider, prompt)
    """

    def get(
        self,
        provider: str,
        prompt: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Optional[LLMResponse]:
        """
        Get cached response.

        Args:
            provider: Provider name
            prompt: Prompt text
            model: Model name (optional)
            temperature: Temperature value (optional)

        Returns:
            Cached LLMResponse if found and not expired, None otherwise
        """
        ...

    def put(
        self,
        response: LLMResponse,
        provider: str,
        prompt: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        ttl_hours: Optional[int] = None,
    ) -> None:
        """
        Store response in cache.

        Args:
            response: LLMResponse to cache
            provider: Provider name
            prompt: Prompt text
            model: Model name (optional)
            temperature: Temperature value (optional)
            ttl_hours: Time-to-live in hours (None for default)
        """
        ...

    def clear(self) -> None:
        """
        Clear all cached responses.
        """
        ...

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary containing:
            - hits: Number of cache hits
            - misses: Number of cache misses
            - size: Number of cached entries
            - hit_rate: Cache hit rate (0.0 to 1.0)
        """
        ...

    def invalidate(
        self,
        provider: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> int:
        """
        Invalidate specific cache entries.

        Args:
            provider: Provider name (None for all providers)
            prompt: Prompt pattern (None for all prompts)

        Returns:
            Number of entries invalidated
        """
        ...


@runtime_checkable
class RateLimitTrackerProtocol(Protocol):
    """
    Protocol for rate limit tracking.

    Abstracts rate limiting logic to enable testing without time delays
    and support different rate limiting strategies.

    Implementations:
    - RateLimitTracker: File-based tracking with time windows
    - InMemoryRateLimitTracker: In-memory tracking for testing
    - UnlimitedRateLimiter: No rate limits (for testing)

    Example:
        def make_request(tracker: RateLimitTrackerProtocol, provider: str) -> bool:
            if not tracker.can_make_request(provider):
                return False
            tracker.record_request(provider)
            return True
    """

    def can_make_request(self, provider: str) -> bool:
        """
        Check if request can be made without exceeding rate limits.

        Args:
            provider: Provider name

        Returns:
            True if request can be made, False if rate limited
        """
        ...

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
        Record a request for rate limiting.

        Args:
            provider: Provider name
            model: Model name
            input_tokens: Input token count
            output_tokens: Output token count
            success: Whether request succeeded
            error_message: Optional error message
        """
        ...

    def get_remaining(self, provider: str) -> Dict[str, int]:
        """
        Get remaining capacity before rate limits.

        Args:
            provider: Provider name

        Returns:
            Dictionary containing:
            - requests_remaining: Requests remaining in current window
            - tokens_remaining: Tokens remaining in current window
            - window_reset: Seconds until window resets
        """
        ...

    def get_limits(self, provider: str) -> Optional[ProviderLimits]:
        """
        Get configured rate limits for provider.

        Args:
            provider: Provider name

        Returns:
            ProviderLimits if configured, None otherwise
        """
        ...

    def reset(self, provider: Optional[str] = None) -> None:
        """
        Reset rate limit tracking.

        Args:
            provider: Provider to reset (None for all providers)
        """
        ...

    def get_status(self) -> Dict[str, Any]:
        """
        Get rate limit status for all providers.

        Returns:
            Dictionary mapping provider names to status info
        """
        ...


@runtime_checkable
class SessionManagerProtocol(Protocol):
    """
    Protocol for session persistence.

    Abstracts session management to enable testing without file I/O
    and support different persistence strategies.

    Implementations:
    - SessionManager: File-based session persistence
    - InMemorySessionManager: In-memory sessions for testing
    - NullSessionManager: No session persistence

    Example:
        def save_work(session: SessionManagerProtocol, data: Dict[str, Any]) -> None:
            session.save("my_session", data)
    """

    def save(self, session_id: str, data: Dict[str, Any]) -> None:
        """
        Save session data.

        Args:
            session_id: Unique session identifier
            data: Session data to persist
        """
        ...

    def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Load session data.

        Args:
            session_id: Unique session identifier

        Returns:
            Session data if found, None otherwise
        """
        ...

    def list_sessions(self) -> List[str]:
        """
        List all session IDs.

        Returns:
            List of session IDs
        """
        ...

    def delete(self, session_id: str) -> bool:
        """
        Delete session.

        Args:
            session_id: Unique session identifier

        Returns:
            True if session was deleted, False if not found
        """
        ...

    def exists(self, session_id: str) -> bool:
        """
        Check if session exists.

        Args:
            session_id: Unique session identifier

        Returns:
            True if session exists, False otherwise
        """
        ...

    def clear_all(self) -> int:
        """
        Clear all sessions.

        Returns:
            Number of sessions deleted
        """
        ...


@runtime_checkable
class ProviderSelectorProtocol(Protocol):
    """
    Protocol for provider selection.

    Abstracts provider selection logic to enable testing with
    controlled selection and support different selection strategies.

    Implementations:
    - ProviderSelector: Smart selection based on availability and limits
    - RandomSelector: Random provider selection (for testing)
    - FixedSelector: Always returns specific provider (for testing)
    - RoundRobinSelector: Round-robin selection across providers

    Example:
        def get_provider(selector: ProviderSelectorProtocol) -> str:
            return selector.select_provider()
    """

    def select_provider(
        self,
        task_type: Optional[str] = None,
        preferred: Optional[str] = None,
        exclude: Optional[List[str]] = None,
    ) -> str:
        """
        Select appropriate provider for task.

        Args:
            task_type: Type of task (affects selection)
            preferred: Preferred provider name (used if available)
            exclude: Providers to exclude from selection

        Returns:
            Selected provider name

        Raises:
            ValueError: If no suitable provider available
        """
        ...

    def get_available_providers(self) -> List[str]:
        """
        Get list of currently available providers.

        Returns:
            List of provider names that are available
        """
        ...

    def is_available(self, provider: str) -> bool:
        """
        Check if specific provider is available.

        Args:
            provider: Provider name

        Returns:
            True if provider is available, False otherwise
        """
        ...

    def mark_unavailable(self, provider: str, duration_seconds: int = 60) -> None:
        """
        Temporarily mark provider as unavailable.

        Args:
            provider: Provider name
            duration_seconds: How long to mark unavailable
        """
        ...


@runtime_checkable
class ProviderRegistryProtocol(Protocol):
    """
    Protocol for provider registry.

    Abstracts provider registration and retrieval to enable testing
    with mock providers and support different registry strategies.

    Implementations:
    - ProviderRegistry: Standard provider registry
    - TestProviderRegistry: Registry with mock providers for testing

    Example:
        def get_model(registry: ProviderRegistryProtocol, name: str) -> LLMProviderBase:
            return registry.get(name)
    """

    def register(self, provider: LLMProviderBase) -> None:
        """
        Register a provider.

        Args:
            provider: LLMProviderBase instance to register

        Raises:
            ValueError: If provider with same name already registered
        """
        ...

    def get(self, name: str) -> LLMProviderBase:
        """
        Get provider by name.

        Args:
            name: Provider name

        Returns:
            LLMProviderBase instance

        Raises:
            KeyError: If provider not found
        """
        ...

    def list_all(self) -> List[str]:
        """
        List all registered provider names.

        Returns:
            List of provider names
        """
        ...

    def unregister(self, name: str) -> bool:
        """
        Unregister a provider.

        Args:
            name: Provider name

        Returns:
            True if provider was unregistered, False if not found
        """
        ...

    def exists(self, name: str) -> bool:
        """
        Check if provider is registered.

        Args:
            name: Provider name

        Returns:
            True if provider is registered, False otherwise
        """
        ...

    def clear(self) -> None:
        """
        Clear all registered providers.
        """
        ...


@runtime_checkable
class WorkingMemoryProtocol(Protocol):
    """
    Protocol for working memory.

    Abstracts working memory to enable testing with controlled
    memory state and support different memory strategies.

    Implementations:
    - WorkingMemory: Standard working memory with history
    - InMemoryWorkingMemory: In-memory only (for testing)
    - NullMemory: No memory retention (for testing)

    Example:
        def remember(memory: WorkingMemoryProtocol, item: str) -> None:
            memory.add(item)

        def recall(memory: WorkingMemoryProtocol, n: int) -> List[str]:
            return memory.get_recent(n)
    """

    def add(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add item to working memory.

        Args:
            content: Content to remember
            metadata: Optional metadata about the content
        """
        ...

    def get_recent(self, n: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent items from memory.

        Args:
            n: Number of recent items to retrieve

        Returns:
            List of recent items with metadata
        """
        ...

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search memory for relevant items.

        Args:
            query: Search query
            limit: Maximum items to return

        Returns:
            List of relevant items with metadata
        """
        ...

    def clear(self) -> None:
        """
        Clear all memory.
        """
        ...

    def summarize(self) -> str:
        """
        Get summary of current memory state.

        Returns:
            Summary string
        """
        ...

    def size(self) -> int:
        """
        Get number of items in memory.

        Returns:
            Number of items
        """
        ...


# Import the unified output protocol from the central protocols module




@runtime_checkable
class ContextProvider(Protocol):
    """
    Protocol for providing codebase context.

    Abstracts codebase context operations to enable testing with
    controlled context and support different context strategies.

    Implementations:
    - CodebaseContext: Full codebase exploration and analysis
    - MockContext: Preset context for testing
    - NullContext: No context provided

    Example:
        def check_context(ctx: ContextProvider) -> bool:
            if ctx.is_explored():
                summary = ctx.get_summary()
                return len(summary) > 0
            return False
    """

    def is_explored(self) -> bool:
        """
        Check if the codebase has been explored.

        Returns:
            True if codebase has been explored, False otherwise
        """
        ...

    def get_summary(self) -> str:
        """
        Get a summary of the codebase context.

        Returns:
            Context summary string
        """
        ...


@runtime_checkable
class OrchestratorAdapter(Protocol):
    """
    Minimal interface for orchestrator functionality needed by CodeAgent.

    Abstracts orchestrator operations to enable testing the agent without
    a full orchestrator and support different orchestration strategies.

    This protocol defines only what the agent actually needs:
    - List available providers
    - Delegate LLM calls
    - Access codebase context

    Implementations:
    - AgentOrchestratorAdapter: Wraps full AgentOrchestrator
    - MockOrchestrator: Returns preset responses for testing
    - TestOrchestrator: Configurable test double

    Example:
        def query_llm(orch: OrchestratorAdapter, prompt: str) -> str:
            providers = orch.list_providers()
            if providers:
                response = orch.delegate(providers[0], prompt)
                return response.content
            return ""
    """

    @property
    def context(self) -> ContextProvider:
        """
        Get the context provider.

        Returns:
            ContextProvider instance
        """
        ...

    def list_providers(self) -> List[str]:
        """
        List available LLM providers.

        Returns:
            List of provider names
        """
        ...

    def delegate(
        self,
        provider: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        use_context: bool = False,
        messages: Optional[list[dict]] = None
    ) -> LLMResponse:
        """
        Delegate a prompt to an LLM provider.

        Args:
            provider: Name of the provider to use
            prompt: User prompt to send
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            use_context: Whether to augment with codebase context
            messages: Pre-built messages array (bypasses prompt/system_prompt)

        Returns:
            LLMResponse with the model's response
        """
        ...

    def delegate_with_tools(
        self,
        provider: str,
        prompt: str,
        tools: List[dict],
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        tool_choice: str = "auto",
        messages: Optional[list[dict]] = None,
        **kwargs: Any
    ) -> LLMResponse:
        """
        Delegate to an LLM provider with native tool calling support.

        Args:
            provider: Name of the provider to use
            prompt: User prompt to send
            tools: List of OpenAI-compatible tool schemas
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            messages: Pre-built messages array (bypasses prompt/system_prompt)
            tool_choice: How the model should choose tools ("auto", "none", or specific tool)
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMResponse with tool_calls field populated if model decided to call tools
        """
        ...


@runtime_checkable
class LLMServiceProtocol(Protocol):
    """
    Simple LLM completion interface.

    After LiteLLM integration, this replaces RetryOrchestratorProtocol.
    LiteLLM handles retry/fallback internally via Router configuration.

    Usage:
    - model parameter is a model GROUP name ("fast" or "quality")
    - LiteLLM Router selects actual model within the group
    - Returns (LLMResponse, task_record dict) tuple

    Implementations:
    - LiteLLMService: Production implementation using LiteLLM Router
    - MockLLMService: Test double for unit tests

    Example:
        service: LLMServiceProtocol = ...
        response, task_record = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=100
        )
    """

    async def completion(
        self,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> tuple[LLMResponse, dict]:
        """
        Execute async completion via LiteLLM Router.

        Args:
            model: Model group name ("fast" or "quality")
            messages: Chat messages [{"role": "user", "content": "..."}]
            **kwargs: Additional params (max_tokens, temperature, tools, tool_choice, etc.)

        Returns:
            Tuple of (LLMResponse, task_record dict)

        Raises:
            AllProvidersRateLimitedError: When all providers exhausted
            ContextWindowExceededError: When quality tier also exceeds context (fatal)
        """
        ...

    def completion_sync(
        self,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> tuple[LLMResponse, dict]:
        """
        Sync version for non-async contexts (Textual workers).

        Args:
            model: Model group name ("fast" or "quality")
            messages: Chat messages [{"role": "user", "content": "..."}]
            **kwargs: Additional params (max_tokens, temperature, tools, tool_choice, etc.)

        Returns:
            Tuple of (LLMResponse, task_record dict)

        Raises:
            AllProvidersRateLimitedError: When all providers exhausted
            ContextWindowExceededError: When quality tier also exceeds context (fatal)
        """
        ...


@runtime_checkable
class ProviderStatusTrackerProtocol(Protocol):
    """
    Tracks provider health from callbacks and health checks.

    Used by:
    - RateTrackingCallback: Records success/failure events
    - /status command: Displays provider health

    Implementations:
    - ProviderStatusTracker: Production implementation
    """

    def on_success(self, provider: str, model: str, latency_ms: float) -> None:
        """
        Record a successful request.

        Args:
            provider: Provider name (e.g., "groq")
            model: Full model ID (e.g., "groq/llama-3.1-8b-instant")
            latency_ms: Request latency in milliseconds
        """
        ...

    def on_failure(self, provider: str, error: str) -> None:
        """
        Record a failed request.

        Args:
            provider: Provider name (e.g., "groq")
            error: Error message
        """
        ...

    def get_status(self, provider: str) -> Optional[Any]:
        """
        Get status for a provider.

        Args:
            provider: Provider name

        Returns:
            ProviderStatus or None if no data
        """
        ...

    def get_all_status(self) -> dict[str, Any]:
        """
        Get status for all providers.

        Returns:
            Dict mapping provider name to ProviderStatus
        """
        ...


@runtime_checkable
class StreamingCompletionProtocol(Protocol):
    """
    Protocol for streaming LLM completions.

    Extends LLMServiceProtocol with streaming capabilities that yield
    incremental chunks as they arrive from the provider.

    Usage:
    - model parameter is a model GROUP name ("fast" or "quality")
    - Yields StreamChunk objects as they arrive
    - Returns final (LLMResponse, task_record dict) tuple after streaming completes

    Implementations:
    - LiteLLMService: Production streaming via LiteLLM Router
    - MockStreamingRouter: Test double for unit tests

    Example:
        service: StreamingCompletionProtocol = ...
        async for chunk in service.stream_completion(
            model="fast",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=100
        ):
            print(chunk.content, end="", flush=True)
    """

    async def stream_completion(
        self,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Execute streaming completion via LiteLLM Router.

        Args:
            model: Model group name ("fast" or "quality")
            messages: Chat messages [{"role": "user", "content": "..."}]
            **kwargs: Additional params (max_tokens, temperature, tools, tool_choice, etc.)

        Yields:
            StreamChunk objects as they arrive from the provider

        Raises:
            AllProvidersRateLimitedError: When all providers exhausted
            ContextWindowExceededError: When quality tier also exceeds context (fatal)
            StreamStuckError: When stream stalls or times out
        """
        ...


@runtime_checkable
class KeyValidatorProtocol(Protocol):
    """
    Protocol for API key validation.

    Provides a lightweight interface for validating API keys without
    requiring the full LLMService. Used by the setup wizard to test
    keys before saving.

    This protocol enables instant wizard startup by avoiding heavy
    litellm imports until validation is actually needed.

    Implementations:
    - LiteLLMKeyValidator: Production implementation with lazy imports
    - MockKeyValidator: Test double for unit tests

    Example:
        validator: KeyValidatorProtocol = LiteLLMKeyValidator()
        is_valid, error = validator.validate_key("groq/llama-3.1-8b", "gsk_...")
        if is_valid:
            save_key(...)
    """

    def validate_key(
        self,
        model: str,
        api_key: str,
        timeout: float = 10.0,
    ) -> tuple[bool, Optional[str]]:
        """
        Validate an API key by making a minimal completion call.

        Args:
            model: LiteLLM model ID (e.g., "groq/llama-3.1-8b-instant")
            api_key: API key to validate
            timeout: Timeout in seconds

        Returns:
            Tuple of (is_valid, error_message)
            - (True, None) if key is valid
            - (False, "error description") if invalid
        """
        ...


@runtime_checkable
class StructuredOutputProtocol(Protocol):
    """
    Protocol for structured output with Pydantic validation.

    Provides async structured output capabilities using Instructor,
    returning validated Pydantic model instances instead of raw text.

    Usage:
    - model parameter is a model GROUP name ("fast" or "quality")
    - response_model is a Pydantic model class for validation
    - Returns validated instance of response_model

    Implementations:
    - LiteLLMService: Production implementation with Instructor
    - MockStructuredService: Test double for unit tests

    Example:
        class TaskClassification(BaseModel):
            task_type: str
            confidence: float

        service: StructuredOutputProtocol = ...
        result = await service.completion_structured(
            model="fast",
            messages=[{"role": "user", "content": "Classify this task"}],
            response_model=TaskClassification,
        )
        # result is a validated TaskClassification instance
    """

    async def completion_structured(
        self,
        model: str,
        messages: list[dict],
        response_model: Type[T],
        **kwargs,
    ) -> T:
        """
        Execute async structured completion with Pydantic validation.

        Args:
            model: Model group name ("fast" or "quality")
            messages: Chat messages [{"role": "user", "content": "..."}]
            response_model: Pydantic model class to validate response against
            **kwargs: Additional params (max_retries, mode_override, etc.)

        Returns:
            Validated instance of response_model

        Raises:
            pydantic.ValidationError: If response cannot be validated after retries
            AllProvidersRateLimitedError: When all providers exhausted
        """
        ...
