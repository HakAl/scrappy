"""
Core AgentOrchestrator implementation.

Central coordinator for multi-provider LLM agent team using composition.
"""

from typing import Optional, AsyncIterator
from datetime import datetime
import asyncio
import time

try:
    from ..providers import ProviderRegistry, LLMResponse
    from ..context import CodebaseContext
    from ..exceptions.delegation import ProviderNotFoundError
    from ..infrastructure.exceptions import RateLimitError, AllProvidersRateLimitedError
except ImportError:
    from providers import ProviderRegistry, LLMResponse
    from context import CodebaseContext
    from exceptions.delegation import ProviderNotFoundError
    from infrastructure.exceptions import RateLimitError, AllProvidersRateLimitedError

from .cache import ResponseCache
from .rate_limiting import RateLimitTracker
from .memory import WorkingMemory
from .session import SessionManager
from .task_executor import TaskExecutor
from .provider_selector import ProviderSelector
from .output import BaseOutputProtocol, ConsoleOutput
from .delegation import DelegationManager
from .types import StreamChunk
from .prompt_augmenter import PromptAugmenter
from .batch_scheduler import BatchScheduler
from .background import BackgroundTaskManager
from .status_reporter import ProviderStatusReporter
from .usage_reporter import UsageReporter
from .context_coordinator import ContextCoordinator
from .model_selection import ModelSelectionType, AllModelsRateLimitedError
from .manager_protocols import (
    ContextManagerProtocol,
    BackgroundTaskManagerProtocol,
    DelegationManagerProtocol,
    TaskExecutorProtocol,
    UsageReporterProtocol,
    StatusReporterProtocol,
)
from .factory import OrchestratorFactory, OrchestratorComponents
from .model_selection import ModelSelectionServiceProtocol

# Import protocols for type hints (Dependency Inversion Principle)
from .protocols import (
    CacheProtocol,
    RateLimitTrackerProtocol,
    SessionManagerProtocol,
    WorkingMemoryProtocol,
    ProviderSelectorProtocol,
    ProviderRegistryProtocol,
    ContextProvider,
    LLMServiceProtocol,
    ProviderStatusTrackerProtocol,
)


class AgentOrchestrator:
    """
    Central coordinator for multi-provider LLM agent team.

    Usage with Claude Code as reasoning layer:
        orch = AgentOrchestrator()
        orch.initialize(auto_register=True)
        result = orch.delegate('groq', 'Summarize this text: ...')
        embeddings = orch.providers.get('cohere').embed(['text1', 'text2'])
    """

    def __init__(
        self,
        project_path: Optional[str] = None,
        context_aware: bool = True,
        enable_cache: bool = True,
        cache_ttl_hours: int = 24,
        verbose_selection: bool = False,
        enable_semantic_search: bool = False,
        quality_mode: bool = True,
        output: Optional[BaseOutputProtocol] = None,
        # Injectable dependencies for testability (using protocols for Dependency Inversion)
        registry: Optional[ProviderRegistryProtocol] = None,
        codebase_context: Optional[ContextProvider] = None,
        cache: Optional[CacheProtocol] = None,
        rate_tracker: Optional[RateLimitTrackerProtocol] = None,
        working_memory: Optional[WorkingMemoryProtocol] = None,
        session_manager: Optional[SessionManagerProtocol] = None,
        provider_selector: Optional[ProviderSelectorProtocol] = None,
        usage_reporter: Optional[UsageReporterProtocol] = None,
        status_reporter: Optional[StatusReporterProtocol] = None,
        task_executor: Optional[TaskExecutorProtocol] = None,
        context_manager: Optional[ContextManagerProtocol] = None,
        delegation_manager: Optional[DelegationManagerProtocol] = None,
        background_manager: Optional[BackgroundTaskManagerProtocol] = None,
        llm_service: Optional[LLMServiceProtocol] = None,
        provider_status_tracker: Optional[ProviderStatusTrackerProtocol] = None,
        model_selector: Optional[ModelSelectionServiceProtocol] = None,
    ):
        """
        Initialize orchestrator (dependencies only - NO side effects).

        Call initialize() after construction to set up providers and brain.

        All dependencies can be injected for testing, or will be created with
        sensible defaults using OrchestratorFactory.
        """
        # Core state
        self.task_history: list[dict] = []
        self.created_at = datetime.now()
        self._brain = None
        self._brain_name = None
        self.context_aware = context_aware
        self.caching_enabled = enable_cache
        self.verbose_selection = verbose_selection
        self.enable_semantic_search = enable_semantic_search
        self.quality_mode = quality_mode

        # Session-sticky model preferences (per selection type)
        # Maps ModelSelectionType -> preferred model ID
        self._preferred_models: dict[ModelSelectionType, str] = {}

        # Use injected components or create defaults via factory
        if all([
            output, registry, cache, rate_tracker, working_memory,
            session_manager, provider_selector, usage_reporter, status_reporter,
            task_executor, context_manager, delegation_manager, background_manager
        ]):
            # All components provided - use them directly
            self.output = output
            self.registry = registry
            self.cache = cache
            self.rate_tracker = rate_tracker
            self.working_memory = working_memory
            self.session_manager = session_manager
            self.provider_selector = provider_selector
            self.usage_reporter = usage_reporter
            self._status_reporter = status_reporter
            self.task_executor = task_executor
            self.context_manager = context_manager
            self.delegation_manager = delegation_manager
            self.background_manager = background_manager
            self.llm_service = llm_service
            self.provider_status_tracker = provider_status_tracker
            self.model_selector = model_selector
        else:
            # Create missing components via factory
            factory = OrchestratorFactory(
                project_path=project_path,
                cache_ttl_hours=cache_ttl_hours,
                verbose_selection=verbose_selection,
                context_aware=context_aware,
                created_at=self.created_at,
                enable_semantic_search=enable_semantic_search
            )

            components = factory.create_all_components(
                brain_provider_getter=lambda: self._brain,
                brain_name_getter=lambda: self._brain_name,
                task_history_recorder=lambda task: self.task_history.append(task)
            )

            # Assign components (use injected or factory-created)
            self.output = output or components.output
            self.registry = registry or components.registry
            self.background_manager = background_manager or components.background_manager
            self.cache = cache or components.cache
            self.rate_tracker = rate_tracker or components.rate_tracker
            self.working_memory = working_memory or components.working_memory
            self.session_manager = session_manager or components.session_manager
            self.provider_selector = provider_selector or components.provider_selector
            self.usage_reporter = usage_reporter or components.usage_reporter
            self._status_reporter = status_reporter or components.status_reporter
            self.task_executor = task_executor or components.task_executor
            self.context_manager = context_manager or components.context_manager
            self.delegation_manager = delegation_manager or components.delegation_manager
            self.llm_service = llm_service or components.llm_service
            self.provider_status_tracker = provider_status_tracker or components.provider_status_tracker
            self.model_selector = model_selector or components.model_selector

    def initialize(
        self,
        auto_register: bool = True,
        orchestrator_provider: Optional[str] = None,
        auto_explore: bool = False,
        show_provider_status: bool = False,
    ):
        """
        Initialize orchestrator with providers and brain setup.

        Call this after construction to perform setup operations.

        Args:
            auto_register: Automatically register available providers
            orchestrator_provider: Provider to use as the "brain" for planning/reasoning
            auto_explore: Automatically explore codebase after initialization
            show_provider_status: Display provider status summary on startup

        Returns:
            self (for method chaining)
        """
        # Register providers and set up brain
        if auto_register:
            self._auto_register_providers()
            self._setup_brain(orchestrator_provider)

        # Show provider status if requested
        if auto_register and show_provider_status:
            self.print_provider_status()

        # Auto-explore if requested
        if auto_explore and self._brain:
            self.context_manager.auto_explore()

        return self

    def _auto_register_providers(self):
        """
        Auto-register providers (no-op after LiteLLM migration).

        NOTE: Provider registration is no longer needed. LiteLLM Router handles
        all provider routing internally based on configured API keys.
        This method is kept for backward compatibility with initialize() interface.
        """
        pass

    def _setup_brain(self, preferred_provider: Optional[str] = None):
        """Set up the orchestrator's reasoning brain."""
        try:
            self._brain_name, self._brain = self.provider_selector.setup_brain(preferred_provider)
            self.output.info(f"[BRAIN] Using {self._brain_name} as orchestrator brain")
        except RuntimeError:
            # Silent failure - no providers available
            # The TUI will handle this by launching the setup wizard
            pass

    def _record_task_completion(self, task_record: dict, is_async: bool = False) -> None:
        """
        Record task completion in usage reporter and history.

        Extracted to avoid duplication between sync and async delegate methods.
        """
        if not task_record or 'provider' not in task_record:
            return

        metadata = {
            'latency_ms': task_record.get('latency_ms', 0),
            'model': task_record.get('model', ''),
            'context_augmented': task_record.get('context_augmented', False),
            'fallback': task_record.get('fallback', False),
            'attempts': task_record.get('attempts', 1),
        }

        if is_async:
            metadata['async'] = task_record.get('async', True)

        self.usage_reporter.record(
            provider=task_record['provider'],
            tokens_used=task_record.get('tokens_used', 0),
            cached=task_record.get('cached', False),
            metadata=metadata
        )

        self.task_history.append(task_record)

    # Provider Management

    @property
    def context(self):
        """
        Access the underlying codebase context.

        For backward compatibility, provides direct access to CodebaseContext.
        New code should prefer using context_manager for orchestration-level operations.

        Returns:
            CodebaseContext instance
        """
        return self.context_manager.context

    @property
    def providers(self) -> ProviderRegistry:
        """Access the provider registry."""
        return self.registry

    @property
    def brain(self):
        """Access the orchestrator's reasoning brain provider name.

        Returns None if no brain is configured (e.g., no providers available).
        """
        return self._brain_name

    @brain.setter
    def brain(self, provider_name: str):
        """Set the orchestrator's reasoning brain."""
        available = self.registry.list_available()
        if provider_name not in available:
            raise ValueError(f"Provider '{provider_name}' not available. Available: {available}")
        provider = self.registry.get(provider_name)
        # Check if provider supports agent/brain role
        if hasattr(provider, 'supports_agent_role') and not provider.supports_agent_role:
            raise ValueError(
                f"Provider '{provider_name}' does not support agent/brain roles (aggressive rate limiting). "
                f"Use for general tasks only."
            )
        self._brain = provider
        self._brain_name = provider_name

    @property
    def brain_provider(self):
        """Access the actual brain provider object."""
        if not self._brain:
            raise RuntimeError("No orchestrator brain configured. No providers available?")
        return self._brain

    def status(self) -> dict:
        """Get current status of all providers and model groups."""
        from .litellm_config import get_configured_models, get_available_groups
        from ..infrastructure.config.api_keys import create_api_key_service

        # Get LiteLLM model group info
        api_key_service = create_api_key_service()
        configured_models = get_configured_models(api_key_service)
        available_groups = get_available_groups(api_key_service)

        # Get provider health status if tracker available
        provider_health = {}
        if self.provider_status_tracker:
            provider_health = {
                name: {
                    'healthy': status.healthy,
                    'last_latency_ms': status.last_latency_ms,
                    'request_count': status.request_count,
                    'error_count': status.error_count,
                    'last_error': status.last_error,
                }
                for name, status in self.provider_status_tracker.get_all_status().items()
            }

        return {
            # LiteLLM model groups (new)
            'model_groups': list(available_groups),
            'configured_models': [
                {
                    'model_id': m.model_id,
                    'provider': m.provider,
                    'group': m.group,
                    'context_length': m.context_length,
                }
                for m in configured_models
            ],
            'provider_health': provider_health,
            # Legacy fields (for backward compat)
            'available_providers': self.registry.list_available(),
            'all_providers': self.registry.list_all(),
            'provider_details': self.registry.get_provider_info(),
            'orchestrator_brain': self._brain_name,
            'tasks_executed': len(self.task_history),
            'session_start': self.created_at.isoformat(),
            'quality_mode': self.quality_mode,
        }

    def print_provider_status(self):
        """Print comprehensive provider status summary."""
        # Update status reporter with current quality_mode before printing
        self._status_reporter.update_quality_mode(self.quality_mode)
        self._status_reporter.print_status()

    def get_provider_selection_info(self) -> dict:
        """Get detailed provider selection information."""
        return self._status_reporter.get_selection_info()

    # Context Management

    def explore_project(self, force: bool = False) -> dict:
        """
        Manually trigger project exploration.

        Delegates to ContextManager for orchestration-level coordination.
        """
        return self.context_manager.explore_project(force=force)

    def get_context_status(self) -> dict:
        """
        Get current codebase context status.

        Delegates directly to the underlying CodebaseContext.
        """
        return self.context.get_status()


    # Session Management (delegates to SessionManager)

    def save_session(self, conversation_history: list = None) -> str:
        """Save current session to disk."""
        return self.session_manager.save_session(
            self.working_memory,
            self.task_history,
            self.created_at,
            conversation_history
        )

    def load_session(self) -> dict:
        """Load previous session from disk."""
        result = self.session_manager.load_session()

        if result['status'] == 'loaded':
            # Restore working memory
            self.working_memory = result['working_memory']
            # Restore task history
            self.task_history = result['task_history']

            # Return relevant info (remove internal working_memory object)
            return {
                'status': 'loaded',
                'saved_at': result['saved_at'],
                'files_restored': result['files_restored'],
                'searches_restored': result['searches_restored'],
                'git_ops_restored': result['git_ops_restored'],
                'discoveries_restored': result['discoveries_restored'],
                'tasks_restored': result['tasks_restored'],
                'conversation_history': result['conversation_history'],
            }

        return result

    def clear_session(self):
        """Delete saved session file."""
        self.session_manager.clear_session()

    # Task Execution (delegates to TaskExecutor)

    def plan(self, task: str, context: Optional[str] = None, max_steps: int = 10) -> list[dict]:
        """Break down a complex task into steps."""
        return self.task_executor.plan(task, context, max_steps)

    def reason(self, question: str, context: Optional[str] = None, evidence: Optional[list[str]] = None) -> dict:
        """Use the orchestrator brain for complex reasoning."""
        return self.task_executor.reason(question, context, evidence)

    def synthesize(self, results: list[LLMResponse], synthesis_prompt: str = "Synthesize these results into a coherent summary:") -> str:
        """Synthesize multiple agent results."""
        return self.task_executor.synthesize(results, synthesis_prompt)

    # Provider Selection

    def get_recommended_provider(
        self,
        selection_type: ModelSelectionType = ModelSelectionType.FAST
    ) -> Optional[str]:
        """
        Get recommended provider for a selection type.

        Args:
            selection_type: What kind of model is needed

        Returns:
            Provider name or None
        """
        try:
            provider_name, _ = self.provider_selector.get_model(selection_type)
            return provider_name
        except RuntimeError:
            return None

    def is_rate_limited(self, provider_name: str) -> bool:
        """
        Check if a provider is currently rate limited.

        Args:
            provider_name: Name of provider to check

        Returns:
            True if provider is rate limited, False otherwise
        """
        return self.rate_tracker.is_rate_limited(provider_name, self.registry)

    # Delegation

    def delegate(
        self,
        provider_name: Optional[str] = None,
        prompt: str = "",
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        use_context: Optional[bool] = None,
        use_cache: Optional[bool] = None,
        intent_classification: Optional[dict] = None,
        auto_fallback: bool = True,
        max_retries: int = 3,
        selection_type: Optional[ModelSelectionType] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Delegate a task to a specific provider with automatic fallback on rate limits.

        Args:
            provider_name: Provider/group hint (e.g., "fast", "quality") - used for
                          backward compatibility. Prefer using selection_type instead.
            prompt: The prompt to send
            model: Specific model ID (e.g., "groq/llama-3.1-8b-instant"). If provided,
                  bypasses model selection and uses this model directly.
            system_prompt: System prompt (optional)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            use_context: Override context augmentation setting
            use_cache: Override cache setting
            intent_classification: Intent data for semantic caching
            auto_fallback: Automatically try other providers on rate limit (default True)
            max_retries: Maximum retry attempts per provider (default 3)
            selection_type: What kind of model to use (FAST, QUALITY, etc.)
            **kwargs: Additional provider-specific arguments

        Returns:
            LLMResponse from successful provider

        Raises:
            AllProvidersRateLimitedError: If all providers are rate limited
            ProviderNotFoundError: If no providers are available
            ValueError: If no models configured for selection type
        """
        # Determine selection type based on quality_mode if not explicitly provided
        if selection_type is None:
            selection_type = ModelSelectionType.QUALITY if self.quality_mode else ModelSelectionType.FAST

        # Use ModelSelectionService for deterministic model selection
        # Only if model not explicitly provided
        if model is None and self.model_selector is not None:
            try:
                # Get session-preferred model for this selection type
                session_preferred = self._preferred_models.get(selection_type)

                # Select specific model (deterministic, priority-based)
                model = self.model_selector.select(selection_type, session_preferred)

                # Update session preference (sticky for this session)
                self._preferred_models[selection_type] = model
            except ValueError:
                # No models configured for this type - fall through to legacy system
                pass

        # Fallback: if no model_selector or model still None, use legacy provider selection
        if model is None:
            if provider_name is None:
                provider_name = self.get_recommended_provider(selection_type)
                if provider_name is None:
                    available = list(self.providers.list_available())
                    raise ProviderNotFoundError(
                        provider_name="<auto-select>",
                        available_providers=available
                    )

        # Determine cache setting
        should_use_cache = use_cache if use_cache is not None else self.caching_enabled

        # Determine min_context based on selection type (32k for QUALITY mode)
        min_context = 32768 if selection_type == ModelSelectionType.QUALITY else 0

        # Delegate with rate limit handling and fallback
        max_attempts = 3  # Limit fallback attempts
        attempt = 0
        last_error = None

        while attempt < max_attempts:
            attempt += 1
            try:
                response, task_record = self.delegation_manager.delegate(
                    provider_name=provider_name,
                    prompt=prompt,
                    model=model,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    use_context=use_context,
                    use_cache=should_use_cache,
                    intent_classification=intent_classification,
                    auto_fallback=auto_fallback,
                    max_retries=max_retries,
                    selection_type=selection_type.value if selection_type else None,
                    min_context=min_context,
                    **kwargs
                )

                # Record task completion
                self._record_task_completion(task_record, is_async=False)
                return response

            except RateLimitError as e:
                last_error = e
                # Mark current model as rate limited
                if model and self.model_selector is not None:
                    self.model_selector.mark_rate_limited(model)

                # Try to select a different model
                if self.model_selector is not None and auto_fallback:
                    try:
                        # Clear session preference to allow different model
                        self._preferred_models.pop(selection_type, None)

                        # Try to get a new model (will skip rate-limited ones)
                        model = self.model_selector.select(selection_type, session_preferred=None)
                        self._preferred_models[selection_type] = model
                        continue  # Retry with new model

                    except AllModelsRateLimitedError:
                        # All models exhausted - re-raise with clear message
                        raise AllModelsRateLimitedError(
                            f"All {selection_type.value} models are rate limited. "
                            f"Try again later."
                        ) from e
                else:
                    # No fallback available
                    raise

        # Should not reach here, but handle edge case
        if last_error:
            raise last_error
        raise AllProvidersRateLimitedError("Delegation failed after max attempts")

    async def stream_delegate(
        self,
        provider_name: Optional[str] = None,
        prompt: str = "",
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        use_context: Optional[bool] = None,
        use_cache: Optional[bool] = None,
        selection_type: Optional[ModelSelectionType] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream a delegation with real-time token delivery.

        Unlike delegate() which returns a complete response, this method
        yields StreamChunk objects as they arrive from the provider,
        enabling real-time display of generated text.

        Args:
            provider_name: Provider/group hint - used for backward compatibility.
            prompt: The prompt to send
            model: Specific model ID. If provided, bypasses model selection.
            system_prompt: System prompt (optional)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            use_context: Override context augmentation setting
            use_cache: Override cache setting
            selection_type: What kind of model to use (FAST, QUALITY, etc.)
            **kwargs: Additional provider-specific arguments

        Yields:
            StreamChunk objects as they arrive from the provider

        Raises:
            AllProvidersRateLimitedError: If all providers are rate limited
            ProviderNotFoundError: If no providers are available
            ValueError: If no models configured for selection type

        Example:
            async for chunk in orchestrator.stream_delegate(
                prompt="Write a story about a robot",
                max_tokens=500
            ):
                print(chunk.content, end="", flush=True)
        """
        # Determine selection type based on quality_mode if not explicitly provided
        if selection_type is None:
            selection_type = ModelSelectionType.QUALITY if self.quality_mode else ModelSelectionType.FAST

        # Use ModelSelectionService for deterministic model selection
        # Only if model not explicitly provided
        if model is None and self.model_selector is not None:
            try:
                # Get session-preferred model for this selection type
                session_preferred = self._preferred_models.get(selection_type)

                # Select specific model (deterministic, priority-based)
                model = self.model_selector.select(selection_type, session_preferred)

                # Update session preference (sticky for this session)
                self._preferred_models[selection_type] = model
            except ValueError:
                # No models configured for this type - fall through to legacy system
                pass

        # Fallback: if no model_selector or model still None, use legacy provider selection
        if model is None:
            if provider_name is None:
                provider_name = self.get_recommended_provider(selection_type)
                if provider_name is None:
                    available = list(self.providers.list_available())
                    raise ProviderNotFoundError(
                        provider_name="<auto-select>",
                        available_providers=available
                    )

        # Determine cache setting
        should_use_cache = use_cache if use_cache is not None else self.caching_enabled

        # Delegate to DelegationManager's stream_delegate
        async for chunk in self.delegation_manager.stream_delegate(
            provider_name=provider_name,
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            use_context=use_context,
            use_cache=should_use_cache,
            **kwargs
        ):
            yield chunk

    def delegate_with_intent(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        use_context: Optional[bool] = None,
        use_cache: Optional[bool] = None,
        **kwargs
    ) -> LLMResponse:
        """Delegate a task with automatic intent classification for semantic caching."""
        from scrappy.task_router.intent import RegexIntentClassifier, RegexEntityExtractor

        classifier = RegexIntentClassifier()
        extractor = RegexEntityExtractor()

        intent_result = classifier.classify(prompt)
        entities = extractor.extract(prompt)

        intent_classification = {
            'intent': intent_result.intent.value,
            'entities': entities,
            'keywords': []  # Keywords can be extracted from metadata if needed
        }

        return self.delegate(
            provider_name=provider_name,
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            use_context=use_context,
            use_cache=use_cache,
            intent_classification=intent_classification,
            **kwargs
        )

    def delegate_smart(
        self,
        prompt: str,
        selection_type: ModelSelectionType = ModelSelectionType.FAST,
        **kwargs
    ) -> LLMResponse:
        """
        Delegate with automatic provider/model selection.

        Args:
            prompt: The prompt to send
            selection_type: What kind of model to use
            **kwargs: Additional arguments for delegate()

        Returns:
            LLMResponse from selected provider
        """
        provider_name, model = self.provider_selector.get_model(selection_type)
        return self.delegate(provider_name, prompt, model=model, **kwargs)

    def batch_delegate(self, tasks: list[dict], provider_name: str = 'groq') -> list[LLMResponse]:
        """Process multiple tasks with same provider."""
        return self.delegation_manager.delegate_batch(tasks, provider_name)

    # Async Methods

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
    ) -> LLMResponse:
        """
        Async version of delegate with automatic fallback on rate limits.

        Enables parallel execution of multiple LLM requests with recovery.

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
            auto_fallback: Automatically try other providers on rate limit (default True)
            max_retries: Maximum retry attempts per provider (default 3)
            **kwargs: Additional provider-specific arguments

        Returns:
            LLMResponse from successful provider

        Raises:
            AllProvidersRateLimitedError: If all providers are rate limited
            Exception: Other non-rate-limit errors
        """
        # Determine cache setting
        should_use_cache = use_cache if use_cache is not None else self.caching_enabled

        # Delegate to DelegationManager
        response, task_record = await self.delegation_manager.delegate_async(
            provider_name=provider_name,
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            use_context=use_context,
            use_cache=should_use_cache,
            intent_classification=intent_classification,
            auto_fallback=auto_fallback,
            max_retries=max_retries,
            **kwargs
        )

        # Record task completion
        self._record_task_completion(task_record, is_async=True)

        return response

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
            max_concurrent: Maximum number of concurrent requests (to respect rate limits)

        Returns:
            List of LLMResponse objects in the same order as input tasks

        Example:
            tasks = [
                {'prompt': 'Summarize this: ...'},
                {'prompt': 'Analyze this: ...'},
                {'prompt': 'Explain this: ...'}
            ]
            results = await orch.batch_delegate_async(tasks, 'cerebras', max_concurrent=3)
        """
        return await self.delegation_manager.batch_delegate_async(
            tasks, provider_name, max_concurrent
        )

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
        return await self.delegation_manager.multi_provider_query_async(
            prompt, providers, **kwargs
        )

    # Usage and Cache Statistics (delegates to UsageReporter)

    def get_usage_report(self) -> dict:
        """Get usage statistics for current session."""
        return self.usage_reporter.get_usage_report()

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return self.usage_reporter.get_cache_stats()

    def clear_cache(self):
        """Clear the response cache."""
        self.usage_reporter.clear_cache()

    def toggle_cache(self) -> bool:
        """
        Toggle caching on/off. Returns new state.

        Note: This toggles the orchestrator's caching preference.
        Use clear_cache() to clear existing cached responses.
        """
        self.caching_enabled = not self.caching_enabled
        return self.caching_enabled

    # Background Task Management (delegates to BackgroundTaskManager)

    def _schedule_background_task(self, coro) -> str:
        """
        Schedule a coroutine as a background task (fire-and-forget).

        The task will run without blocking the caller. Errors are captured
        but don't affect the main flow.

        Args:
            coro: Coroutine to execute in background

        Returns:
            str: Task ID for tracking/cancellation
        """
        return self.background_manager.submit_background_task(coro)

    async def wait_for_background_tasks(self, timeout: float = 5.0) -> dict:
        """
        Wait for all pending background tasks to complete.

        Useful for testing or graceful shutdown.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            Dict with completion status
        """
        return await self.background_manager.wait_for_background_tasks(timeout)

    def get_background_task_status(self) -> dict:
        """
        Get status of background task processing.

        Returns:
            Dict with pending task count and recent errors
        """
        return self.background_manager.get_task_status()

    def clear_background_errors(self):
        """Clear the background error log."""
        self.background_manager.clear_background_errors()

    def cancel_background_task(self, task_id: str) -> bool:
        """
        Cancel a pending background task.

        Args:
            task_id: ID returned from _schedule_background_task

        Returns:
            True if task was found and cancelled, False otherwise
        """
        return self.background_manager.cancel_task(task_id)

    # Rate Limit Management

    def get_rate_limit_status(self) -> dict:
        """Get current rate limit usage for all providers."""
        return self.rate_tracker.get_rate_limit_status_extended(self.registry)

    def get_remaining_quota(self, provider_name: str, model: Optional[str] = None) -> dict:
        """Get remaining quota for a specific provider."""
        return self.rate_tracker.get_remaining_quota_for_provider(
            provider_name, self.registry, model
        )

    def check_rate_limit_warnings(self) -> list[str]:
        """Check for any approaching rate limits across all providers."""
        return self.rate_tracker.check_all_warnings(self.registry)

    def reset_rate_tracking(self, provider_name: Optional[str] = None):
        """Reset rate tracking data."""
        self.rate_tracker.reset_rate_tracking(provider_name)

    def recommend_provider(self, requirements: dict) -> str:
        """Recommend best provider based on requirements."""
        return self.provider_selector.recommend(requirements)


def create_orchestrator() -> AgentOrchestrator:
    """Factory function to create an initialized orchestrator."""
    orch = AgentOrchestrator()
    orch.initialize(auto_register=True)
    return orch
