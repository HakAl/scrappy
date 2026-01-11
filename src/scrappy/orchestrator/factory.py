"""
OrchestratorFactory - Creates default components for AgentOrchestrator.

Following SOLID principles:
- Single Responsibility: Only responsible for component creation
- Dependency Inversion: Creates components via protocols
- Open/Closed: Can be extended by subclassing
"""

import logging
from typing import Optional, Callable, Any
from datetime import datetime
from pathlib import Path

from ..infrastructure.logging import StructuredLogger

logger = logging.getLogger(__name__)

from .provider_types import ProviderRegistry
from ..context import CodebaseContext
from ..infrastructure.config.api_keys import create_api_key_service

from .cache import ResponseCache
from .rate_limiting import (
    create_rate_limit_tracker,
    create_enforcement_components,
    install_rate_limit_hooks,
    is_rate_limit_hooks_installed,
)
from .memory import WorkingMemory
from .session import SessionManager
from .task_executor import TaskExecutor
from .provider_selector import ProviderSelector
from .output import BaseOutputProtocol, ConsoleOutput

from .delegation import DelegationManager
from .prompt_augmenter import PromptAugmenter
from .batch_scheduler import BatchScheduler
from .background import BackgroundTaskManager
from .status_reporter import ProviderStatusReporter
from .usage_reporter import UsageReporter
from .context_coordinator import ContextCoordinator
from .config import OrchestratorConfig
from .litellm_service import LiteLLMService
from .litellm_config import create_litellm_router
# NOTE: litellm_callbacks imports litellm at top level, so we import it lazily
# in create_llm_service() to avoid 2s startup delay
from .provider_status import ProviderStatusTracker
from .model_selection import ModelSelectionService, ModelSelectionServiceProtocol
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
    LLMServiceProtocol,
    ProviderStatusTrackerProtocol,
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
        self.llm_service: Optional[LLMServiceProtocol] = None
        self.provider_status_tracker: Optional[ProviderStatusTrackerProtocol] = None
        self.model_selector: Optional[ModelSelectionServiceProtocol] = None


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
        task_history_recorder: Optional[Callable] = None,
        # Legacy parameters - ignored
        brain_provider_getter: Optional[Callable] = None,
        brain_name_getter: Optional[Callable] = None,
    ) -> OrchestratorComponents:
        """
        Create all default components with proper dependency injection.

        Args:
            task_history_recorder: Callable to record tasks
            brain_provider_getter: DEPRECATED - ignored
            brain_name_getter: DEPRECATED - ignored

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

        # Model selector (deterministic model selection)
        components.model_selector = self.create_model_selector()

        # Provider status tracker for LiteLLM callbacks
        components.provider_status_tracker = self.create_provider_status_tracker()

        # LLM Service (uses LiteLLM Router)
        # Always created - configures itself when API keys are available
        components.llm_service = self.create_llm_service(
            components.output,
            components.rate_tracker,
            components.provider_status_tracker
        )

        # Usage reporter
        components.usage_reporter = self.create_usage_reporter(components.cache)

        # Task executor (needs llm_service for LLM calls)
        components.task_executor = self.create_task_executor(
            components.llm_service,
            task_history_recorder
        )

        # Context manager (needs task executor for summary generation)
        components.context_manager = self.create_context_manager(
            components.codebase_context,
            components.output,
            components.task_executor
        )

        # Delegation manager (needs many dependencies)
        # Always created - llm_service handles NotConfiguredError if no keys
        components.delegation_manager = self.create_delegation_manager(
            components.llm_service,
            components.cache,
            components.output,
            components.working_memory,
            components.context_manager,
            components.rate_tracker,
            components.registry,
        )

        # Status reporter (will need to be updated after brain is set)
        components.status_reporter = self.create_status_reporter(
            components.registry,
            components.provider_selector,
            components.output,
            brain_name=None,  # Will be updated after brain setup
            quality_mode=self.config.quality_mode
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
        """Create default rate limit tracker with HTTP header capture."""
        if self._path_provider:
            # Ensure user dir exists and migrate any project-level rate limits
            self._path_provider.ensure_user_dir()
            tracker_path = self._path_provider.rate_limits_file()
        else:
            # Fallback for backwards compatibility
            tracker_path = codebase_context.project_path / ".llm_rate_limits.json"
        tracker = create_rate_limit_tracker(
            tracker_file=str(tracker_path),
            auto_load=True,
            config=self.config
        )

        # Install httpx hooks to capture rate limit headers from API responses
        # Only install once (idempotent) - hooks intercept all httpx requests
        if not is_rate_limit_hooks_installed():
            install_rate_limit_hooks(tracker)
            logger.debug("Installed httpx rate limit header capture hooks")

        return tracker

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
        brain_name: Optional[str] = None,
        quality_mode: bool = True
    ) -> StatusReporterProtocol:
        """Create default status reporter."""
        return ProviderStatusReporter(
            registry=registry,
            provider_selector=provider_selector,
            output=output,
            brain_name=brain_name,
            verbose_selection=self.verbose_selection,
            quality_mode=quality_mode
        )

    def create_task_executor(
        self,
        llm_service: Any,
        task_history_recorder: Optional[Callable] = None
    ) -> TaskExecutorProtocol:
        """Create default task executor."""
        return TaskExecutor(
            llm_service=llm_service,
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

    def create_provider_status_tracker(self) -> ProviderStatusTrackerProtocol:
        """Create default provider status tracker for health monitoring."""
        return ProviderStatusTracker()

    def create_model_selector(self) -> ModelSelectionServiceProtocol:
        """
        Create model selection service with configured models.

        Determines which models have API keys configured and creates
        a selector that provides deterministic, priority-based selection.
        """
        api_key_service = create_api_key_service()
        configured_models = self._get_configured_models(api_key_service)
        return ModelSelectionService(configured_models=configured_models)

    def _get_configured_models(self, api_key_service) -> set[str]:
        """
        Get set of model IDs that have API keys configured.

        Maps provider names to their configured models based on
        which API keys are present.

        Returns:
            Set of model IDs in "provider/model" format
        """
        from .model_selection import MODEL_PRIORITIES

        # Map providers to their API key names
        provider_to_key = {
            "groq": "GROQ_API_KEY",
            "cerebras": "CEREBRAS_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "sambanova": "SAMBANOVA_API_KEY",
        }

        configured = set()

        # Collect all models from priorities
        all_models = set()
        for models in MODEL_PRIORITIES.values():
            all_models.update(models)

        # Check which providers have API keys configured
        configured_providers = set()
        for provider, key_name in provider_to_key.items():
            if api_key_service.get_key(key_name):
                configured_providers.add(provider)

        logger.debug(f"Configured providers: {configured_providers}")

        # Check which models have API keys
        for model_id in all_models:
            # Extract provider from model_id (e.g., "groq/llama-3.1-8b" -> "groq")
            provider = model_id.split("/")[0]

            if provider in configured_providers:
                configured.add(model_id)

        logger.debug(f"Configured models: {configured}")
        return configured

    def create_llm_service(
        self,
        output: BaseOutputProtocol,
        rate_tracker: RateLimitTrackerProtocol,
        status_tracker: ProviderStatusTrackerProtocol
    ) -> LLMServiceProtocol:
        """
        Create default LLM service using LiteLLM Router.

        Following SOLID principles - wires up all LiteLLM dependencies.

        Creates:
        1. RateTrackingCallback - for usage and status tracking
        2. Empty LiteLLM Router - configured later via service.configure()
        3. LiteLLMService - wrapping router for completion calls

        Service is always created. If API keys exist, router is configured
        immediately. Otherwise, configure() must be called after wizard
        saves keys.
        """
        # Lazy import to avoid 2s litellm startup delay
        from .litellm_callbacks import create_rate_tracking_callback

        # Create callback for usage tracking (D9) and status display (D10)
        callback = create_rate_tracking_callback(
            rate_tracker=rate_tracker,
            status_tracker=status_tracker,
        )

        # Get api key service - passed to LiteLLMService for configure()
        api_key_service = create_api_key_service()

        # Create empty router - will be configured via service.configure()
        router = create_litellm_router(callbacks=[callback])

        # Create logger for API request/response debugging
        api_logger = None
        if self._path_provider:
            log_file = self._path_provider.debug_log_file()
            api_logger = StructuredLogger(
                name="llm_service",
                log_file=log_file,
                level=logging.DEBUG,
            )

        # Create service with all dependencies
        service = LiteLLMService(
            router=router,
            api_key_service=api_key_service,
            output=output,
            callback=callback,
            logger=api_logger,
        )

        # Try to configure if keys already exist
        service.configure()

        return service

    def create_delegation_manager(
        self,
        llm_service: LLMServiceProtocol,
        cache: CacheProtocol,
        output: BaseOutputProtocol,
        working_memory: WorkingMemoryProtocol,
        context_manager: ContextManagerProtocol,
        rate_tracker: RateLimitTrackerProtocol,
        registry: ProviderRegistryProtocol,
    ) -> DelegationManagerProtocol:
        """
        Create default delegation manager with all collaborators.

        Following SOLID principles - wires up all dependencies.
        Uses LiteLLMService for LLM calls (LiteLLM Router handles retry/fallback).
        Includes rate limit enforcement for pre-request blocking.
        """
        # Create PromptAugmenter
        prompt_augmenter = PromptAugmenter(
            context=context_manager.context,
            working_memory=working_memory,
        )

        # Create BatchScheduler (uses LLMService)
        batch_scheduler = BatchScheduler(
            llm_service=llm_service,
            output=output,
        )

        # Create enforcement components from existing rate tracker
        # (tracker is already wired to RateTrackingCallback for usage recording)
        enforcement_components = create_enforcement_components(
            tracker=rate_tracker,
            config=self.config,
            output=output,
        )

        # Create DelegationManager with all dependencies including enforcement
        return DelegationManager(
            llm_service=llm_service,
            cache=cache,
            output=output,
            prompt_augmenter=prompt_augmenter,
            batch_scheduler=batch_scheduler,
            context_aware=self.context_aware,
            enforcement=enforcement_components.enforcement,
            notifier=enforcement_components.notifier,
            registry=registry,
        )
