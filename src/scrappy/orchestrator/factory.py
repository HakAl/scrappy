"""
OrchestratorFactory - Creates default components for AgentOrchestrator.

Following SOLID principles:
- Single Responsibility: Only responsible for component creation
- Dependency Inversion: Creates components via protocols
- Open/Closed: Can be extended by subclassing
"""

import logging
from typing import Optional, Callable
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

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
from .output import BaseOutputProtocol, ConsoleOutput

from .delegation import DelegationManager
from .retry_orchestrator import RetryOrchestrator
from .prompt_augmenter import PromptAugmenter
from .batch_scheduler import BatchScheduler
from .background import BackgroundTaskManager
from .status_reporter import ProviderStatusReporter
from .usage_reporter import UsageReporter
from .context_coordinator import ContextCoordinator
from .config import OrchestratorConfig
from .manager_protocols import (
    ContextManagerProtocol,
    BackgroundTaskManagerProtocol,
    DelegationManagerProtocol,
    TaskExecutorProtocol,
    UsageReporterProtocol,
    StatusReporterProtocol,
)

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
from ..infrastructure.protocols import PathProviderProtocol
from ..infrastructure.paths import ScrappyPathProvider


class OrchestratorComponents:
    """
    Container for orchestrator components.

    Holds all created components to avoid parameter explosion.
    Uses protocol type hints following Dependency Inversion Principle.
    """

    def __init__(self):
        self.output: Optional[BaseOutputProtocol] = None
        self.registry: Optional[ProviderRegistryProtocol] = None
        self.background_manager: Optional[BackgroundTaskManagerProtocol] = None
        self.codebase_context: Optional[ContextProvider] = None
        self.cache: Optional[CacheProtocol] = None
        self.rate_tracker: Optional[RateLimitTrackerProtocol] = None
        self.working_memory: Optional[WorkingMemoryProtocol] = None
        self.session_manager: Optional[SessionManagerProtocol] = None
        self.provider_selector: Optional[ProviderSelectorProtocol] = None
        self.usage_reporter: Optional[UsageReporterProtocol] = None
        self.status_reporter: Optional[StatusReporterProtocol] = None
        self.task_executor: Optional[TaskExecutorProtocol] = None
        self.context_manager: Optional[ContextManagerProtocol] = None
        self.delegation_manager: Optional[DelegationManagerProtocol] = None


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
        path_provider: Optional[PathProviderProtocol] = None,
        config: Optional[OrchestratorConfig] = None,
        enable_semantic_search: bool = True,
    ):
        """
        Initialize factory with configuration.

        NO side effects - only assigns configuration.

        Args:
            project_path: Path to project directory
            cache_ttl_hours: Cache TTL in hours
            verbose_selection: Enable verbose provider selection
            context_aware: Enable context awareness
            created_at: Creation timestamp
            path_provider: Path provider for data files (auto-creates if None)
            config: OrchestratorConfig instance (creates default if None)
            enable_semantic_search: Enable background semantic search initialization (default: True)
        """
        self.project_path = project_path
        self.cache_ttl_hours = cache_ttl_hours
        self.verbose_selection = verbose_selection
        self.context_aware = context_aware
        self.enable_semantic_search = enable_semantic_search
        self.created_at = created_at or datetime.now()
        self.config = config or OrchestratorConfig()

        # Create path provider if not provided
        if path_provider is None:
            project_root = Path(project_path) if project_path else Path(".")
            path_provider = ScrappyPathProvider(project_root)
        self._path_provider = path_provider

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

        # Provider selector (needs config)
        components.provider_selector = self.create_provider_selector(
            components.registry,
            components.output,
            self.config
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

    def create_output(self) -> BaseOutputProtocol:
        """Create default output interface."""
        return ConsoleOutput()

    def create_registry(self) -> ProviderRegistryProtocol:
        """Create default provider registry."""
        return ProviderRegistry()

    def create_background_manager(self) -> BackgroundTaskManagerProtocol:
        """Create default background task manager."""
        return BackgroundTaskManager()

    def create_codebase_context(self) -> ContextProvider:
        """Create default codebase context with semantic search if enabled."""
        context = CodebaseContext(self.project_path)

        if self.enable_semantic_search:
            try:
                from ..context.semantic.config import SemanticIndexConfig
                from ..context.semantic.state import LanceDBIndexStateManager
                from ..context.semantic.decision import ThresholdDecisionMaker
                from ..context.semantic_manager import SemanticSearchManager

                config = SemanticIndexConfig()
                db_path = Path(self.project_path) / config.db_dir_name if self.project_path else None

                if db_path:
                    state_manager = LanceDBIndexStateManager(db_path)
                    decision_maker = ThresholdDecisionMaker(config)

                    # Create semantic manager with dependencies
                    semantic_manager = SemanticSearchManager(
                        project_path=Path(self.project_path) if self.project_path else Path("."),
                        config=config,
                        state_manager=state_manager,
                        decision_maker=decision_maker,
                    )

                    # Replace default semantic manager with configured one
                    context._semantic_manager = semantic_manager

                    # Start background initialization
                    context.start_background_initialization()
            except ImportError as e:
                # Semantic search dependencies not available, fall back to basic context
                logger.warning(f"Semantic search dependencies not available: {e}")

        return context

    def create_cache(self, codebase_context: ContextProvider) -> CacheProtocol:
        """Create default response cache."""
        if self._path_provider:
            cache_path = self._path_provider.response_cache_file()
        else:
            # Fallback for backwards compatibility
            cache_path = codebase_context.project_path / ".llm_response_cache.json"
        return ResponseCache(
            cache_file=str(cache_path),
            default_ttl_hours=self.cache_ttl_hours
        )

    def create_rate_tracker(self, codebase_context: ContextProvider) -> RateLimitTrackerProtocol:
        """Create default rate limit tracker."""
        if self._path_provider:
            tracker_path = self._path_provider.rate_limits_file()
        else:
            # Fallback for backwards compatibility
            tracker_path = codebase_context.project_path / ".llm_rate_limits.json"
        return create_rate_limit_tracker(
            tracker_file=str(tracker_path),
            auto_load=True,
            config=self.config
        )

    def create_working_memory(self) -> WorkingMemoryProtocol:
        """Create default working memory."""
        return WorkingMemory()

    def create_session_manager(self, codebase_context: ContextProvider) -> SessionManagerProtocol:
        """Create default session manager."""
        return SessionManager(codebase_context.project_path, self._path_provider)

    def create_provider_selector(
        self,
        registry: ProviderRegistryProtocol,
        output: BaseOutputProtocol,
        config: OrchestratorConfig
    ) -> ProviderSelectorProtocol:
        """Create default provider selector."""
        return ProviderSelector(
            registry,
            verbose=self.verbose_selection,
            output=output,
            config=config
        )

    def create_usage_reporter(self, cache: CacheProtocol) -> UsageReporterProtocol:
        """Create default usage reporter."""
        return UsageReporter(cache=cache, created_at=self.created_at)

    def create_status_reporter(
        self,
        registry: ProviderRegistryProtocol,
        provider_selector: ProviderSelectorProtocol,
        output: BaseOutputProtocol,
        brain_name: Optional[str] = None
    ) -> StatusReporterProtocol:
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
    ) -> TaskExecutorProtocol:
        """Create default task executor."""
        return TaskExecutor(
            get_brain_provider=brain_provider_getter or (lambda: None),
            get_brain_name=brain_name_getter or (lambda: None),
            record_task=task_history_recorder or (lambda task: None)
        )

    def create_context_manager(
        self,
        codebase_context: ContextProvider,
        output: BaseOutputProtocol,
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
        output: BaseOutputProtocol,
        rate_tracker: RateLimitTrackerProtocol,
        provider_selector: ProviderSelectorProtocol,
        working_memory: WorkingMemoryProtocol,
        context_manager: ContextManagerProtocol
    ) -> DelegationManagerProtocol:
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
