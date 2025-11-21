"""
OrchestratorFactory - Creates default components for AgentOrchestrator.

Following SOLID principles:
- Single Responsibility: Only responsible for component creation
- Dependency Inversion: Creates components via protocols
- Open/Closed: Can be extended by subclassing
"""

from typing import Optional, Callable
from datetime import datetime
from pathlib import Path

try:
    from ..providers import ProviderRegistry
    from ..context import CodebaseContext
except ImportError:
    from providers import ProviderRegistry
    from context import CodebaseContext

from .cache import ResponseCache
from .rate_limiting import create_rate_limit_tracker, RateLimitTracker
from .memory import WorkingMemory
from .session import SessionManager
from .task_executor import TaskExecutor
from .provider_selector import ProviderSelector
from .output import OutputInterface, ConsoleOutput
from .delegation import DelegationManager
from .retry_orchestrator import RetryOrchestrator
from .prompt_augmenter import PromptAugmenter
from .batch_scheduler import BatchScheduler
from .background import BackgroundTaskManager
from .status_reporter import ProviderStatusReporter
from .usage_reporter import UsageReporter
from .context_coordinator import ContextCoordinator
from .manager_protocols import ContextManagerProtocol, BackgroundTaskManagerProtocol

# Import protocols for type hints (Dependency Inversion Principle)
from .protocols import (
    CacheProtocol,
    RateLimitTrackerProtocol,
    SessionManagerProtocol,
    WorkingMemoryProtocol,
    ProviderSelectorProtocol,
    ProviderRegistryProtocol,
    ContextProvider,
)


class OrchestratorComponents:
    """
    Container for orchestrator components.

    Holds all created components to avoid parameter explosion.
    Uses protocol type hints following Dependency Inversion Principle.
    """

    def __init__(self):
        self.output: Optional[OutputInterface] = None
        self.registry: Optional[ProviderRegistryProtocol] = None
        self.background_manager: Optional[BackgroundTaskManagerProtocol] = None
        self.codebase_context: Optional[ContextProvider] = None
        self.cache: Optional[CacheProtocol] = None
        self.rate_tracker: Optional[RateLimitTrackerProtocol] = None
        self.working_memory: Optional[WorkingMemoryProtocol] = None
        self.session_manager: Optional[SessionManagerProtocol] = None
        self.provider_selector: Optional[ProviderSelectorProtocol] = None
        self.usage_reporter: Optional[UsageReporter] = None
        self.status_reporter: Optional[ProviderStatusReporter] = None
        self.task_executor: Optional[TaskExecutor] = None
        self.context_manager: Optional[ContextManagerProtocol] = None
        self.delegation_manager: Optional[DelegationManager] = None


class OrchestratorFactory:
    """
    Factory for creating default orchestrator components.

    Single Responsibility: Component creation and wiring
    Following Dependency Injection principles
    """

    def __init__(
        self,
        project_path: Optional[str] = None,
        cache_ttl_hours: int = 24,
        verbose_selection: bool = False,
        context_aware: bool = True,
        created_at: Optional[datetime] = None,
    ):
        """
        Initialize factory with configuration.

        NO side effects - only assigns configuration.
        """
        self.project_path = project_path
        self.cache_ttl_hours = cache_ttl_hours
        self.verbose_selection = verbose_selection
        self.context_aware = context_aware
        self.created_at = created_at or datetime.now()

    def create_all_components(
        self,
        brain_provider_getter: Optional[Callable] = None,
        brain_name_getter: Optional[Callable] = None,
        task_history_recorder: Optional[Callable] = None,
    ) -> OrchestratorComponents:
        """
        Create all default components with proper dependency injection.

        Args:
            brain_provider_getter: Callable that returns brain provider
            brain_name_getter: Callable that returns brain name
            task_history_recorder: Callable to record tasks

        Returns:
            OrchestratorComponents with all components initialized
        """
        components = OrchestratorComponents()

        # Core components (no dependencies)
        components.output = self.create_output()
        components.registry = self.create_registry()
        components.background_manager = self.create_background_manager()
        components.working_memory = self.create_working_memory()

        # Codebase context (needs project path)
        components.codebase_context = self.create_codebase_context()

        # Components that depend on codebase context
        components.cache = self.create_cache(components.codebase_context)
        components.rate_tracker = self.create_rate_tracker(components.codebase_context)
        components.session_manager = self.create_session_manager(components.codebase_context)

        # Provider selector
        components.provider_selector = self.create_provider_selector(
            components.registry,
            components.output
        )

        # Usage reporter
        components.usage_reporter = self.create_usage_reporter(components.cache)

        # Task executor (needs brain getters and task recorder)
        components.task_executor = self.create_task_executor(
            brain_provider_getter,
            brain_name_getter,
            task_history_recorder
        )

        # Context manager (needs task executor for summary generation)
        components.context_manager = self.create_context_manager(
            components.codebase_context,
            components.output,
            components.task_executor
        )

        # Delegation manager (needs many dependencies)
        components.delegation_manager = self.create_delegation_manager(
            components.registry,
            components.cache,
            components.output,
            components.rate_tracker,
            components.provider_selector,
            components.working_memory,
            components.context_manager
        )

        # Status reporter (will need to be updated after brain is set)
        components.status_reporter = self.create_status_reporter(
            components.registry,
            components.provider_selector,
            components.output,
            brain_name=None  # Will be updated after brain setup
        )

        return components

    def create_output(self) -> OutputInterface:
        """Create default output interface."""
        return ConsoleOutput()

    def create_registry(self) -> ProviderRegistryProtocol:
        """Create default provider registry."""
        return ProviderRegistry()

    def create_background_manager(self) -> BackgroundTaskManagerProtocol:
        """Create default background task manager."""
        return BackgroundTaskManager()

    def create_codebase_context(self) -> ContextProvider:
        """Create default codebase context."""
        return CodebaseContext(self.project_path)

    def create_cache(self, codebase_context: ContextProvider) -> CacheProtocol:
        """Create default response cache."""
        cache_path = codebase_context.project_path / ".llm_response_cache.json"
        return ResponseCache(
            cache_file=str(cache_path),
            default_ttl_hours=self.cache_ttl_hours
        )

    def create_rate_tracker(self, codebase_context: ContextProvider) -> RateLimitTrackerProtocol:
        """Create default rate limit tracker."""
        tracker_path = codebase_context.project_path / ".llm_rate_limits.json"
        return create_rate_limit_tracker(tracker_file=str(tracker_path), auto_load=True)

    def create_working_memory(self) -> WorkingMemoryProtocol:
        """Create default working memory."""
        return WorkingMemory()

    def create_session_manager(self, codebase_context: ContextProvider) -> SessionManagerProtocol:
        """Create default session manager."""
        return SessionManager(codebase_context.project_path)

    def create_provider_selector(
        self,
        registry: ProviderRegistryProtocol,
        output: OutputInterface
    ) -> ProviderSelectorProtocol:
        """Create default provider selector."""
        return ProviderSelector(
            registry,
            verbose=self.verbose_selection,
            output=output
        )

    def create_usage_reporter(self, cache: CacheProtocol) -> UsageReporter:
        """Create default usage reporter."""
        return UsageReporter(cache=cache, created_at=self.created_at)

    def create_status_reporter(
        self,
        registry: ProviderRegistryProtocol,
        provider_selector: ProviderSelectorProtocol,
        output: OutputInterface,
        brain_name: Optional[str] = None
    ) -> ProviderStatusReporter:
        """Create default status reporter."""
        return ProviderStatusReporter(
            registry=registry,
            provider_selector=provider_selector,
            output=output,
            brain_name=brain_name,
            verbose_selection=self.verbose_selection
        )

    def create_task_executor(
        self,
        brain_provider_getter: Optional[Callable] = None,
        brain_name_getter: Optional[Callable] = None,
        task_history_recorder: Optional[Callable] = None
    ) -> TaskExecutor:
        """Create default task executor."""
        return TaskExecutor(
            get_brain_provider=brain_provider_getter or (lambda: None),
            get_brain_name=brain_name_getter or (lambda: None),
            record_task=task_history_recorder or (lambda task: None)
        )

    def create_context_manager(
        self,
        codebase_context: ContextProvider,
        output: OutputInterface,
        task_executor: TaskExecutor
    ) -> ContextCoordinator:
        """Create default context coordinator."""
        return ContextCoordinator(
            context=codebase_context,
            output=output,
            generate_summary_func=task_executor.generate_context_summary
        )

    def create_delegation_manager(
        self,
        registry: ProviderRegistryProtocol,
        cache: CacheProtocol,
        output: OutputInterface,
        rate_tracker: RateLimitTrackerProtocol,
        provider_selector: ProviderSelectorProtocol,
        working_memory: WorkingMemoryProtocol,
        context_manager: ContextManagerProtocol
    ) -> DelegationManager:
        """
        Create default delegation manager with all collaborators.

        Following SOLID principles - wires up all dependencies.
        """
        # Create RetryOrchestrator
        retry_orchestrator = RetryOrchestrator(
            registry=registry,
            rate_tracker=rate_tracker,
            provider_selector=provider_selector,
            output=output,
        )

        # Create PromptAugmenter
        prompt_augmenter = PromptAugmenter(
            context=context_manager.context,
            working_memory=working_memory,
        )

        # Create BatchScheduler
        batch_scheduler = BatchScheduler(
            retry_orchestrator=retry_orchestrator,
            output=output,
        )

        # Create DelegationManager with all dependencies
        return DelegationManager(
            retry_orchestrator=retry_orchestrator,
            cache=cache,
            output=output,
            prompt_augmenter=prompt_augmenter,
            batch_scheduler=batch_scheduler,
            context_aware=self.context_aware,
        )
