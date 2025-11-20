"""
Core AgentOrchestrator implementation.

Central coordinator for multi-provider LLM agent team using composition.
"""

from typing import Optional
from datetime import datetime
import asyncio
import time

try:
    from ..providers import ProviderRegistry, LLMResponse
    from ..context import CodebaseContext
    from ..utils.errors import is_rate_limit_error, RateLimitError, AllProvidersRateLimitedError
except ImportError:
    from providers import ProviderRegistry, LLMResponse
    from context import CodebaseContext
    from utils.errors import is_rate_limit_error, RateLimitError, AllProvidersRateLimitedError

from .cache import ResponseCache
from .rate_limiter import RateLimitTracker
from .memory import WorkingMemory
from .session import SessionManager
from .task_executor import TaskExecutor
from .provider_selector import ProviderSelector
from .output import OutputInterface, ConsoleOutput
from .delegation import DelegationManager
from .background import BackgroundTaskManager
from .registration import ProviderRegistrar
from .status_reporter import ProviderStatusReporter
from .usage_reporter import UsageReporter
from .context_manager import ContextManager
from .manager_protocols import ContextManagerProtocol, BackgroundTaskManagerProtocol


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
        output: Optional[OutputInterface] = None,
        # Injectable dependencies for testability
        registry: Optional[ProviderRegistry] = None,
        codebase_context: Optional[CodebaseContext] = None,
        cache: Optional[ResponseCache] = None,
        rate_tracker: Optional[RateLimitTracker] = None,
        working_memory: Optional[WorkingMemory] = None,
        session_manager: Optional[SessionManager] = None,
        provider_selector: Optional[ProviderSelector] = None,
        usage_reporter: Optional[UsageReporter] = None,
        status_reporter: Optional[ProviderStatusReporter] = None,
        task_executor: Optional[TaskExecutor] = None,
        context_manager: Optional[ContextManagerProtocol] = None,
        delegation_manager: Optional[DelegationManager] = None,
        background_manager: Optional[BackgroundTaskManagerProtocol] = None,
    ):
        """
        Initialize orchestrator (dependencies only - NO side effects).

        Call initialize() after construction to set up providers and brain.

        Args:
            project_path: Path to project for context awareness
            context_aware: Enable context-augmented prompts
            enable_cache: Enable response caching
            cache_ttl_hours: Time-to-live for cache entries in hours
            verbose_selection: Show detailed provider selection logic
            output: Output interface for messages (default: ConsoleOutput)
            registry: Injectable provider registry (default: creates new ProviderRegistry)
            codebase_context: Injectable codebase context (default: creates new CodebaseContext)
            cache: Injectable response cache (default: creates new ResponseCache)
            rate_tracker: Injectable rate limit tracker (default: creates new RateLimitTracker)
            working_memory: Injectable working memory (default: creates new WorkingMemory)
            session_manager: Injectable session manager (default: creates new SessionManager)
            provider_selector: Injectable provider selector (default: creates new ProviderSelector)
            usage_reporter: Injectable usage reporter (default: creates new UsageReporter)
            status_reporter: Injectable status reporter (default: creates new ProviderStatusReporter)
            task_executor: Injectable task executor (default: creates new TaskExecutor)
            context_manager: Injectable context manager (default: creates new ContextManager)
            delegation_manager: Injectable delegation manager (default: creates new DelegationManager)
            background_manager: Injectable background task manager (default: creates new BackgroundTaskManager)
        """
        # Store config for factory methods
        self._project_path = project_path
        self._cache_ttl_hours = cache_ttl_hours
        self._verbose_selection = verbose_selection

        # Core components
        self.output = output or self._create_default_output()
        self.registry = registry or self._create_default_registry()
        self.task_history: list[dict] = []
        self.created_at = datetime.now()
        self._brain = None
        self._brain_name = None
        self.context_aware = context_aware
        self.caching_enabled = enable_cache
        self.verbose_selection = verbose_selection

        # Initialize dependencies using injected or factory methods
        self.background_manager = background_manager or self._create_default_background_manager()

        # Codebase context (needed for other components)
        _codebase_context = codebase_context or self._create_default_codebase_context()

        # Composed components
        self.cache = cache or self._create_default_cache(_codebase_context)
        self.rate_tracker = rate_tracker or self._create_default_rate_tracker(_codebase_context)
        self.working_memory = working_memory or self._create_default_working_memory()
        self.session_manager = session_manager or self._create_default_session_manager(_codebase_context)
        self.provider_selector = provider_selector or self._create_default_provider_selector()
        self.usage_reporter = usage_reporter or self._create_default_usage_reporter()

        # Initialize status reporter (can be created now, will use current brain state)
        self._status_reporter = status_reporter or self._create_default_status_reporter()

        # Initialize task executor
        self.task_executor = task_executor or self._create_default_task_executor()

        # Initialize context manager (after task_executor since it needs summary generation)
        self.context_manager = context_manager or self._create_default_context_manager(_codebase_context)

        # Initialize delegation manager
        self.delegation_manager = delegation_manager or self._create_default_delegation_manager()

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
        """Attempt to register all known providers."""
        registrar = ProviderRegistrar(self.registry, self.output)
        registrar.auto_register_all()

    def _setup_brain(self, preferred_provider: Optional[str] = None):
        """Set up the orchestrator's reasoning brain."""
        try:
            self._brain_name, self._brain = self.provider_selector.setup_brain(preferred_provider)
            self.output.info(f"[BRAIN] Using {self._brain_name} as orchestrator brain")
        except RuntimeError as e:
            self.output.warn(str(e))

    # Factory methods for default dependencies

    def _create_default_output(self) -> OutputInterface:
        """Create default output interface."""
        return ConsoleOutput()

    def _create_default_registry(self) -> ProviderRegistry:
        """Create default provider registry."""
        return ProviderRegistry()

    def _create_default_background_manager(self) -> BackgroundTaskManagerProtocol:
        """Create default background task manager."""
        return BackgroundTaskManager()

    def _create_default_codebase_context(self) -> CodebaseContext:
        """Create default codebase context."""
        return CodebaseContext(self._project_path)

    def _create_default_cache(self, codebase_context: CodebaseContext) -> ResponseCache:
        """Create default response cache."""
        return ResponseCache(
            cache_file=str(codebase_context.project_path / ".llm_response_cache.json"),
            default_ttl_hours=self._cache_ttl_hours
        )

    def _create_default_rate_tracker(self, codebase_context: CodebaseContext) -> RateLimitTracker:
        """Create default rate limit tracker."""
        return RateLimitTracker(
            tracker_file=str(codebase_context.project_path / ".llm_rate_limits.json")
        )

    def _create_default_working_memory(self) -> WorkingMemory:
        """Create default working memory."""
        return WorkingMemory()

    def _create_default_session_manager(self, codebase_context: CodebaseContext) -> SessionManager:
        """Create default session manager."""
        return SessionManager(codebase_context.project_path)

    def _create_default_provider_selector(self) -> ProviderSelector:
        """Create default provider selector."""
        return ProviderSelector(self.registry, verbose=self._verbose_selection, output=self.output)

    def _create_default_usage_reporter(self) -> UsageReporter:
        """Create default usage reporter."""
        return UsageReporter(cache=self.cache, created_at=self.created_at)

    def _create_default_status_reporter(self) -> ProviderStatusReporter:
        """Create default status reporter."""
        return ProviderStatusReporter(
            registry=self.registry,
            provider_selector=self.provider_selector,
            output=self.output,
            brain_name=self._brain_name,
            verbose_selection=self.verbose_selection
        )

    def _create_default_task_executor(self) -> TaskExecutor:
        """Create default task executor."""
        return TaskExecutor(
            get_brain_provider=lambda: self._brain,
            get_brain_name=lambda: self._brain_name,
            record_task=lambda task: self.task_history.append(task)
        )

    def _create_default_context_manager(self, codebase_context: CodebaseContext) -> ContextManager:
        """Create default context manager."""
        return ContextManager(
            context=codebase_context,
            output=self.output,
            generate_summary_func=self.task_executor.generate_context_summary
        )

    def _create_default_delegation_manager(self) -> DelegationManager:
        """Create default delegation manager."""
        return DelegationManager(
            registry=self.registry,
            cache=self.cache,
            rate_tracker=self.rate_tracker,
            provider_selector=self.provider_selector,
            output=self.output,
            context=self.context_manager.context,
            context_aware=self.context_aware,
            get_working_memory_context=self.working_memory.get_context_string
        )

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
        self._brain = self.registry.get(provider_name)
        self._brain_name = provider_name

    @property
    def brain_provider(self):
        """Access the actual brain provider object."""
        if not self._brain:
            raise RuntimeError("No orchestrator brain configured. No providers available?")
        return self._brain

    def status(self) -> dict:
        """Get current status of all providers."""
        return {
            'available_providers': self.registry.list_available(),
            'all_providers': self.registry.list_all(),
            'provider_details': self.registry.get_provider_info(),
            'orchestrator_brain': self._brain_name,
            'tasks_executed': len(self.task_history),
            'session_start': self.created_at.isoformat(),
        }

    def print_provider_status(self):
        """Print comprehensive provider status summary."""
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

    def get_recommended_provider(self, task_type: str = 'general') -> Optional[str]:
        """
        Get recommended provider based on task type and current rate limit status.

        Args:
            task_type: Type of task ('planning', 'execution', 'quick', 'general')

        Returns:
            Provider name or None if no providers available
        """
        return self.rate_tracker.get_recommended_provider(task_type, self.registry)

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
        task_type: str = 'general',
        **kwargs
    ) -> LLMResponse:
        """
        Delegate a task to a specific provider with automatic fallback on rate limits.

        Args:
            provider_name: Initial provider to try (None for auto-selection)
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
            task_type: Type of task for auto provider selection ('planning', 'execution', 'general')
            **kwargs: Additional provider-specific arguments

        Returns:
            LLMResponse from successful provider

        Raises:
            AllProvidersRateLimitedError: If all providers are rate limited
            Exception: Other non-rate-limit errors
        """
        # Auto-select provider if not specified
        if provider_name is None:
            provider_name = self.get_recommended_provider(task_type)
            if provider_name is None:
                raise Exception("No providers available")

        # Determine cache setting
        should_use_cache = use_cache if use_cache is not None else self.caching_enabled

        # Delegate to DelegationManager
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
            **kwargs
        )

        # Record task in usage reporter (if task_record has required fields)
        if task_record and 'provider' in task_record:
            self.usage_reporter.record(
                provider=task_record['provider'],
                tokens_used=task_record.get('tokens_used', 0),
                cached=task_record.get('cached', False),
                metadata={
                    'latency_ms': task_record.get('latency_ms', 0),
                    'model': task_record.get('model', ''),
                    'context_augmented': task_record.get('context_augmented', False),
                    'fallback': task_record.get('fallback', False),
                    'attempts': task_record.get('attempts', 1),
                }
            )

        # Keep task_history for backward compatibility (session save/load)
        if task_record:
            self.task_history.append(task_record)

        return response

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
        from intent_classifier import IntentClassifier

        classifier = IntentClassifier()
        classification_result = classifier.classify(prompt)

        intent_classification = {
            'intent': classification_result.primary_intent.intent.value,
            'entities': classification_result.entities,
            'keywords': classification_result.keywords
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

    def delegate_smart(self, prompt: str, task_type: str = 'general', **kwargs) -> LLMResponse:
        """Automatically select best provider for task type."""
        if task_type == 'reasoning':
            reasoning_result = self.reason(prompt)
            if isinstance(reasoning_result, dict):
                content = f"Analysis: {reasoning_result.get('analysis', '')}\n\nConclusion: {reasoning_result.get('conclusion', '')}"
            else:
                content = str(reasoning_result)
            return LLMResponse(
                content=content,
                model=self.brain_provider.default_model,
                provider=self._brain_name,
                tokens_used=0,
                input_tokens=0,
                output_tokens=0,
                latency_ms=0.0,
                raw_response=reasoning_result,
                metadata={'task_type': 'reasoning', 'via': 'orchestrator_brain'},
                timestamp=datetime.now()
            )

        provider_name, model = self.provider_selector.select_for_task(task_type)
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

        # Record task in usage reporter (if task_record has required fields)
        if task_record and 'provider' in task_record:
            self.usage_reporter.record(
                provider=task_record['provider'],
                tokens_used=task_record.get('tokens_used', 0),
                cached=task_record.get('cached', False),
                metadata={
                    'latency_ms': task_record.get('latency_ms', 0),
                    'model': task_record.get('model', ''),
                    'context_augmented': task_record.get('context_augmented', False),
                    'fallback': task_record.get('fallback', False),
                    'attempts': task_record.get('attempts', 1),
                    'async': task_record.get('async', True),
                }
            )

        # Keep task_history for backward compatibility (session save/load)
        if task_record:
            self.task_history.append(task_record)

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

    def run_async(self, coro):
        """
        Helper to run async code from sync context.

        Usage:
            results = orch.run_async(orch.batch_delegate_async(tasks))
        """
        return self.delegation_manager.run_async(coro)

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
