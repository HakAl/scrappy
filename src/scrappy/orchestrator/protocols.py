"""
Protocols for orchestrator module.

Defines abstract interfaces (Protocols) for orchestrator implementations,
enabling loose coupling and better testability throughout the codebase.

This is the canonical location for all orchestrator-related protocols including:
- LLM request/response types (LLMRequest)
- Delegation protocols (PromptAugmenterProtocol, BatchSchedulerProtocol)
- Provider management (ProviderRegistryProtocol, ProviderSelectorProtocol)
- Caching and rate limiting (CacheProtocol, RateLimitTrackerProtocol)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Optional, Dict, Any, List, runtime_checkable, AsyncIterator, Iterator, Type, TypeVar

from pydantic import BaseModel

from .model_selection import ModelSelectionType
from .provider_types import LLMResponse, LLMProviderProtocol, ProviderLimits
from .types import StreamChunk

# Type variable for generic structured output responses
T = TypeVar("T", bound=BaseModel)


# =============================================================================
# Request Types (from protocols/delegation.py)
# =============================================================================

# Internal kwargs that should NOT be passed to provider APIs
# These are orchestration metadata, not provider parameters
INTERNAL_KWARGS = frozenset({
    'task_type',  # Internal hint for orchestration (e.g., 'planning', 'execution')
    'selection_type',  # ModelSelectionType used for provider selection (for fallback)
    'min_context',  # Minimum context length required (for fallback filtering)
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
    selection_type: Optional[str] = None
    min_context: int = 0
    kwargs: Optional[dict[str, Any]] = None

    def __post_init__(self):
        """Validate request parameters and filter internal kwargs."""
        if self.kwargs is None:
            object.__setattr__(self, 'kwargs', {})
        else:
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


@runtime_checkable
class ProviderAttemptProtocol(Protocol):
    """Protocol for provider attempt records."""

    provider: str
    model: str
    success: bool
    error: Optional[str]


# =============================================================================
# Delegation Protocols (from protocols/delegation.py)
# =============================================================================

class PromptAugmenterProtocol(Protocol):
    """
    Augments prompts with contextual information.

    Responsibilities:
    - Add codebase context to prompts
    - Add working memory/recent interactions
    - Manage context window constraints
    """

    def augment(
        self,
        prompt: str,
        use_context: bool = True,
    ) -> str:
        """Augment a prompt with contextual information."""
        ...


class BatchSchedulerProtocol(Protocol):
    """
    Schedules and executes parallel batch requests.

    Responsibilities:
    - Execute multiple requests in parallel
    - Manage concurrency limits
    - Coordinate multi-provider queries
    """

    async def execute_batch(
        self,
        requests: list[LLMRequest],
        max_concurrent: int = 5,
    ) -> list[tuple[Any, dict]]:
        """Execute multiple requests in parallel."""
        ...

    async def execute_multi_provider(
        self,
        request: LLMRequest,
        providers: list[str],
    ) -> dict[str, tuple[Any, dict]]:
        """Execute same request across multiple providers in parallel."""
        ...


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

    def refresh_provider_configuration(self) -> bool:
        """Reload provider configuration after setup changes."""
        ...

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
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> Optional[LLMResponse]:
        """
        Get cached response.

        Args:
            provider: Provider name
            prompt: Prompt text
            model: Model name (optional)
            system_prompt: System prompt (optional)
            max_tokens: Maximum tokens (optional)
            temperature: Temperature value (optional)

        Returns:
            Cached LLMResponse if found and not expired, None otherwise
        """
        ...

    def put(
        self,
        response: LLMResponse,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> None:
        """
        Store response in cache.

        Args:
            response: LLMResponse to cache
            prompt: Prompt text
            model: Model name (optional)
            system_prompt: System prompt (optional)
            max_tokens: Maximum tokens (optional)
            temperature: Temperature value (optional)
        """
        ...

    def get_by_intent(
        self,
        intent: str,
        entities: dict,
        keywords: list,
        provider: str,
        model: Optional[str] = None,
    ) -> Optional[LLMResponse]:
        """
        Get cached response by classified intent and extracted entities.
        """
        ...

    def put_by_intent(
        self,
        response: LLMResponse,
        intent: str,
        entities: dict,
        keywords: list,
    ) -> None:
        """
        Store response in the intent-based cache.
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

    Example:
        def track(tracker: RateLimitTrackerProtocol, provider: str, model: str) -> None:
            tracker.record_request(provider, model, input_tokens=10, output_tokens=5)
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

    def get_remaining_quota(
        self,
        provider: str,
        model: str,
        limits: ProviderLimits,
    ) -> dict[str, Any]:
        """
        Get remaining quota for provider/model.

        Args:
            provider: Provider name
            model: Model name
            limits: Provider limits configuration

        Returns:
            Dictionary with remaining quota details
        """
        ...

    def is_rate_limited(self, provider_name: str, registry: Any) -> bool:
        """
        Check if provider is currently rate limited.

        Args:
            provider_name: Provider name
            registry: Provider registry for limit lookup

        Returns:
            True if provider is rate limited, False otherwise
        """
        ...

    def reset_rate_tracking(self, provider_name: Optional[str] = None) -> None:
        """
        Reset rate limit tracking.

        Args:
            provider_name: Provider to reset (None for all providers)
        """
        ...

    def get_rate_limit_status_extended(self, registry: Any) -> dict[str, Any]:
        """
        Get extended rate limit status for all providers.

        Args:
            registry: Provider registry for limit lookup

        Returns:
            Dictionary mapping provider names to extended status info
        """
        ...

    def check_all_warnings(self, registry: Any) -> List[str]:
        """
        Check all providers for rate limit warnings.

        Args:
            registry: Provider registry for limit lookup

        Returns:
            List of warning messages
        """
        ...

    def get_remaining_quota_for_provider(
        self,
        provider_name: str,
        registry: Any,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Get remaining quota for a provider.

        Args:
            provider_name: Provider name
            registry: Provider registry for limit lookup
            model: Specific model (optional)

        Returns:
            Dictionary with remaining quota details
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

    Example:
        def restore(session: SessionManagerProtocol) -> dict:
            return session.load_session()
    """

    def save_session(
        self,
        working_memory: "WorkingMemoryProtocol",
        task_history: list,
        session_start: datetime,
        conversation_history: Optional[list] = None,
    ) -> str:
        """
        Save current session to disk.

        Args:
            working_memory: Working memory to persist
            task_history: Task history entries
            session_start: When the session started
            conversation_history: Optional conversation history entries

        Returns:
            Path or identifier of the saved session
        """
        ...

    def load_session(self) -> dict:
        """
        Load previous session from disk.

        Returns:
            Dictionary with 'status' and restored session state
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

    Example:
        def pick(selector: ProviderSelectorProtocol, requirements: dict) -> str:
            return selector.recommend(requirements)
    """

    def setup_brain(self, preferred_provider: Optional[str] = None) -> tuple[str, None]:
        """
        Set up the brain provider for orchestration.

        Args:
            preferred_provider: Preferred provider name (used if available)

        Returns:
            Tuple of (provider name, None placeholder)
        """
        ...

    def get_model(self, selection_type: ModelSelectionType) -> tuple[str, None]:
        """
        Get provider for a model selection type.

        Args:
            selection_type: Model selection type (fast, balanced, etc.)

        Returns:
            Tuple of (provider name, None placeholder)
        """
        ...

    def recommend(self, requirements: dict) -> str:
        """
        Recommend a provider for the given requirements.

        Args:
            requirements: Requirement hints (task type, context size, etc.)

        Returns:
            Recommended provider name
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

    Example:
        def get_model(registry: ProviderRegistryProtocol, name: str) -> LLMProviderProtocol:
            return registry.get(name)
    """

    def register(self, provider: LLMProviderProtocol) -> None:
        """
        Register a provider.

        Args:
            provider: LLMProviderProtocol instance to register

        Raises:
            ValueError: If provider with same name already registered
        """
        ...

    def get(self, name: str) -> LLMProviderProtocol:
        """
        Get provider by name.

        Args:
            name: Provider name

        Returns:
            LLMProviderProtocol instance

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

    def list_available(self) -> list[str]:
        """
        List names of providers that are currently available.

        Returns:
            List of available provider names
        """
        ...

    def get_provider_info(self) -> dict[str, dict]:
        """
        Get detailed information for all registered providers.

        Returns:
            Dictionary mapping provider names to info dictionaries
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

    Example:
        def persist(memory: WorkingMemoryProtocol) -> dict:
            return memory.to_dict()
    """

    def clear(self) -> None:
        """
        Clear all memory.
        """
        ...

    def to_dict(self) -> dict:
        """
        Serialize working memory to a dictionary for persistence.

        Returns:
            Dictionary representation of memory state
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

    def configure(self) -> bool:
        """Reload provider configuration and return whether any model is available."""
        ...

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

    def stream_completion_direct(
        self,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> Iterator[StreamChunk]:
        """
        Stream completion directly with a specific model (bypasses Router).

        Use this for deterministic model selection when you need to stream
        from a specific model rather than letting the Router shuffle.

        Args:
            model: Specific model name (e.g., "cerebras/qwen-3-235b-a22b-instruct-2507")
            messages: Chat messages
            **kwargs: Additional params (max_tokens, temperature, tools, tool_choice, etc.)

        Yields:
            StreamChunk objects as they arrive from the provider

        Raises:
            NotConfiguredError: When service not configured with API keys
            AllProvidersRateLimitedError: When model is rate limited
            ValueError: When provider is unknown
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

    def on_success(self, provider: str, model: str, latency_ms: float, tokens: int = 0) -> None:
        """
        Record a successful request.

        Args:
            provider: Provider name (e.g., "groq")
            model: Full model ID (e.g., "groq/llama-3.1-8b-instant")
            latency_ms: Request latency in milliseconds
            tokens: Total tokens used (input + output)
        """
        ...

    def on_failure(self, provider: str, error: str, latency_ms: float = 0.0) -> None:
        """
        Record a failed request.

        Args:
            provider: Provider name (e.g., "groq")
            error: Error message
            latency_ms: Request latency in milliseconds
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

    def stream_completion(
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
