"""
Core AgentOrchestrator implementation.

Central coordinator for multi-provider LLM agent team using composition.
"""

import threading
import time
from typing import Awaitable, Callable, Optional, Iterator, AsyncIterator, TypeVar
from datetime import datetime
from uuid import uuid4

from .provider_types import LLMResponse, LLMProviderProtocol
from ..infrastructure.exceptions import (
    ProviderNotFoundError,
    FailureKind,
    ProviderError,
)

from .output import BaseOutputProtocol
from .types import StreamChunk
from .model_selection import ModelSelectionType, AllModelsRateLimitedError
from .manager_protocols import (
    ContextManagerProtocol,
    BackgroundTaskManagerProtocol,
    DelegationManagerProtocol,
    TaskExecutorProtocol,
    UsageReporterProtocol,
    StatusReporterProtocol,
)
from .factory import OrchestratorFactory
from .model_selection import ModelSelectionServiceProtocol
from .failure_policy import FailureRecord, SHOULD_RETRY_KINDS, get_failure_policy
from .fallback_metrics import provider_fallback_metrics
from .provider_selector import selection_type_for_provider_hint

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
from .provider_types import ProviderAttempt
from .litellm_config import get_configured_models
from ..infrastructure.config.api_keys import create_api_key_service
from ..infrastructure.logging import get_logger


T = TypeVar("T")
logger = get_logger(__name__)


def _format_trace_chain(attempts_list: list[ProviderAttempt]) -> Optional[str]:
    """Format provider attempts into a human-friendly fallback chain."""
    if len(attempts_list) <= 1:
        return None

    parts: list[str] = []
    for entry in attempts_list:
        if entry.success:
            model_name = entry.model
            if "/" in model_name:
                model_name = model_name.split("/", 1)[1]
            parts.append(f"{entry.provider}: {model_name}")
        else:
            if entry.error:
                parts.append(f"{entry.provider}({entry.error})")
            else:
                parts.append(entry.provider)

    return "->".join(parts)


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
        self._brain: Optional[LLMProviderProtocol] = None
        self._brain_name: Optional[str] = None
        self.context_aware = context_aware
        self.caching_enabled = enable_cache
        self.verbose_selection = verbose_selection
        self.enable_semantic_search = enable_semantic_search
        self.quality_mode = quality_mode

        # Per-selection-type model preferences. User preferences are reserved
        # for an explicit user-choice writer; see scrappy-1n7g.
        # Fallback preferences are soft and recover when priority selection
        # becomes available again.
        self._user_preferred_models: dict[ModelSelectionType, str] = {}
        self._fallback_preferred_models: dict[ModelSelectionType, str] = {}
        self._preferred_models_lock = threading.Lock()

        # Use injected components or create defaults via factory.
        # Explicit truthiness chain (identical semantics to all([...]))
        # so mypy narrows each component to non-None in this branch.
        if (
            output and registry and cache and rate_tracker and working_memory
            and session_manager and provider_selector and usage_reporter
            and status_reporter and task_executor and context_manager
            and delegation_manager and background_manager
        ):
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

    def _select_fallback_model(
        self,
        selection_type: ModelSelectionType,
        failed_model: Optional[str],
        failure_kind: FailureKind,
        retry_after: Optional[float] = None,
        exclude: Optional[set[str]] = None,
        min_context: int = 0,
        failure_summary: Optional[dict[str, FailureRecord]] = None,
    ) -> Optional[str]:
        """Mark the current model unavailable and select the next candidate."""
        if failed_model is None or self.model_selector is None:
            return None

        self.model_selector.mark_unhealthy(
            failed_model,
            failure_kind,
            retry_after=retry_after,
        )

        try:
            next_model = self.model_selector.select(
                selection_type,
                min_context=min_context,
                session_preferred=None,
                exclude=exclude,
            )
        except AllModelsRateLimitedError as error:
            # Fallback exhaustion and initial-selection exhaustion are mutually
            # exclusive for one request, but both count selection exhaustion.
            provider_fallback_metrics.record_selection_exhausted(
                selection_type=selection_type.value,
            )
            combined_summary = dict(getattr(error, "failure_summary", {}) or {})
            if failure_summary:
                combined_summary.update(failure_summary)
            raise AllModelsRateLimitedError(
                str(error),
                failure_summary=combined_summary,
            ) from error

        with self._preferred_models_lock:
            self._fallback_preferred_models[selection_type] = next_model
        return next_model

    def _min_context_for(self, selection_type: ModelSelectionType) -> int:
        """Return minimum context window for a selection type."""
        return 32768 if selection_type == ModelSelectionType.CHAT else 0

    def _select_initial_model(
        self,
        selection_type: ModelSelectionType,
        explicit_model: Optional[str],
        min_context: int,
    ) -> Optional[str]:
        """
        Select the first model for a request.

        Explicit concrete models are validated by DelegationManager downstream.
        """
        if explicit_model is not None:
            return explicit_model
        if self.model_selector is None:
            return None

        self._recover_fallback_preference(selection_type, min_context)
        preferred = self._preferred_model_for(selection_type, min_context)

        try:
            return self.model_selector.select(
                selection_type,
                min_context=min_context,
                session_preferred=preferred,
            )
        except AllModelsRateLimitedError:
            # Initial selection failed before any attempt, so this does not
            # double-count the fallback exhaustion path.
            provider_fallback_metrics.record_selection_exhausted(
                selection_type=selection_type.value,
            )
            raise
        except ValueError:
            return None

    def _recover_fallback_preference(
        self,
        selection_type: ModelSelectionType,
        min_context: int,
    ) -> None:
        """Clear fallback stickiness once priority selection has recovered."""
        if self.model_selector is None:
            return

        with self._preferred_models_lock:
            fallback_preferred = self._fallback_preferred_models.get(selection_type)

        if not fallback_preferred:
            return

        priority_models = self.model_selector.get_models_for_type(selection_type)
        priority_one = next(
            (
                model
                for model in priority_models
                if self._model_satisfies_min_context(model, min_context)
            ),
            None,
        )
        if (
            priority_one is None
            or priority_one == fallback_preferred
            or not self.model_selector.is_available(priority_one)
        ):
            return

        with self._preferred_models_lock:
            if self._fallback_preferred_models.get(selection_type) == fallback_preferred:
                self._fallback_preferred_models.pop(selection_type, None)

    def _preferred_model_for(
        self,
        selection_type: ModelSelectionType,
        min_context: int,
    ) -> Optional[str]:
        """Return the valid preferred model for a selection type, if any."""
        if self.model_selector is None:
            return None

        with self._preferred_models_lock:
            user_preferred = self._user_preferred_models.get(selection_type)
            fallback_preferred = self._fallback_preferred_models.get(selection_type)

        for candidate in (user_preferred, fallback_preferred):
            if (
                candidate
                and self.model_selector.is_available(candidate)
                and self._model_satisfies_min_context(candidate, min_context)
            ):
                return candidate

        return None

    def _model_satisfies_min_context(self, model: str, min_context: int) -> bool:
        """Return whether a model satisfies the request context requirement."""
        if min_context <= 0:
            return True

        from .litellm_config import MODEL_METADATA

        metadata = MODEL_METADATA.get(model)
        return bool(metadata and metadata.context_length >= min_context)

    def _dispatch_sync_with_fallback(
        self,
        *,
        selection_type: ModelSelectionType,
        initial_model: Optional[str],
        min_context: int,
        auto_fallback: bool,
        run_attempt: Callable[[Optional[str]], T],
    ) -> tuple[T, Optional[str]]:
        """Run a concrete-model sync dispatch loop with policy-based fallback."""
        # Keep behavior mirrored with _dispatch_async_with_fallback except for
        # the async helper awaiting run_attempt.
        model = initial_model
        tried_models: set[str] = set()
        failure_summary: dict[str, FailureRecord] = {}
        attempts: list[ProviderAttempt] = []
        request_id = uuid4().hex
        started_at = time.perf_counter()

        while True:
            try:
                result = run_attempt(model)
                if model is not None:
                    attempts.append(ProviderAttempt(
                        provider=self._provider_from_model(model),
                        model=model,
                        success=True,
                    ))
                self._emit_fallback_event(
                    request_id=request_id,
                    attempts=attempts,
                    elapsed_ms=(time.perf_counter() - started_at) * 1000,
                )
                return result, _format_trace_chain(attempts)
            except ProviderError as error:
                if model is None:
                    raise

                kind = error.failure_kind
                failure_summary[model] = FailureRecord.from_error(model, error)
                attempts.append(ProviderAttempt(
                    provider=error.provider_name or self._provider_from_model(model),
                    model=model,
                    success=False,
                    error=kind.value,
                    retry_after=error.retry_after,
                ))

                if kind == FailureKind.EXHAUSTED:
                    raise
                if not auto_fallback:
                    raise
                if kind not in SHOULD_RETRY_KINDS:
                    raise

                tried_models.add(model)
                next_model = self._select_fallback_model(
                    selection_type=selection_type,
                    failed_model=model,
                    failure_kind=kind,
                    retry_after=error.retry_after,
                    exclude=tried_models,
                    min_context=min_context,
                    failure_summary=failure_summary,
                )
                if next_model is None:
                    raise
                model = next_model

    def _stream_with_fallback_sync(
        self,
        *,
        selection_type: ModelSelectionType,
        initial_model: str,
        min_context: int,
        auto_fallback: bool,
        stream_attempt: Callable[[str], Iterator[StreamChunk]],
    ) -> Iterator[StreamChunk]:
        """Run a sync streaming dispatch loop with pre-output fallback."""
        # Keep behavior mirrored with _stream_with_fallback_async except for
        # async iteration over stream_attempt.
        model = initial_model
        tried_models: set[str] = set()
        failure_summary: dict[str, FailureRecord] = {}
        attempts: list[ProviderAttempt] = []
        request_id = uuid4().hex
        started_at = time.perf_counter()
        # Request-lifetime output state: once any attempt reaches the user,
        # later failures must surface instead of switching models mid-stream.
        partial_content_chars = 0
        emitted_semantic_output = False

        while True:
            try:
                for chunk in stream_attempt(model):
                    content_chars = len(chunk.content or "")
                    semantic_output = self._stream_chunk_has_semantic_output(chunk)
                    yield chunk
                    partial_content_chars += content_chars
                    emitted_semantic_output = (
                        emitted_semantic_output or semantic_output
                    )

                attempts.append(ProviderAttempt(
                    provider=self._provider_from_model(model),
                    model=model,
                    success=True,
                ))

                trace_chain = _format_trace_chain(attempts)
                self._emit_fallback_event(
                    request_id=request_id,
                    attempts=attempts,
                    elapsed_ms=(time.perf_counter() - started_at) * 1000,
                )
                if trace_chain:
                    # Consumer trace metadata complements the structured
                    # provider_fallback telemetry event above.
                    yield StreamChunk(
                        content="",
                        model=model,
                        provider=self._provider_from_model(model),
                        metadata={"trace_chain": trace_chain},
                    )
                return

            except ProviderError as error:
                kind = error.failure_kind
                failure_summary[model] = FailureRecord.from_error(model, error)
                attempts.append(ProviderAttempt(
                    provider=error.provider_name or self._provider_from_model(model),
                    model=model,
                    success=False,
                    error=kind.value,
                    retry_after=error.retry_after,
                ))

                if partial_content_chars > 0 or emitted_semantic_output:
                    error.context = {
                        **error.context,
                        "partial_content_chars": partial_content_chars,
                        "emitted_semantic_output": emitted_semantic_output,
                    }
                    raise
                if kind == FailureKind.EXHAUSTED:
                    raise
                if not auto_fallback:
                    raise
                if kind not in SHOULD_RETRY_KINDS:
                    raise
                if self.model_selector is None:
                    raise

                tried_models.add(model)
                next_model = self._select_fallback_model(
                    selection_type=selection_type,
                    failed_model=model,
                    failure_kind=kind,
                    retry_after=error.retry_after,
                    exclude=tried_models,
                    min_context=min_context,
                    failure_summary=failure_summary,
                )
                if next_model is None:
                    raise
                model = next_model

    async def _dispatch_async_with_fallback(
        self,
        *,
        selection_type: ModelSelectionType,
        initial_model: Optional[str],
        min_context: int,
        auto_fallback: bool,
        run_attempt: Callable[[Optional[str]], Awaitable[T]],
    ) -> tuple[T, Optional[str]]:
        """Run a concrete-model async dispatch loop with policy-based fallback."""
        # Keep behavior mirrored with _dispatch_sync_with_fallback except for
        # awaiting run_attempt.
        model = initial_model
        tried_models: set[str] = set()
        failure_summary: dict[str, FailureRecord] = {}
        attempts: list[ProviderAttempt] = []
        request_id = uuid4().hex
        started_at = time.perf_counter()

        while True:
            try:
                result = await run_attempt(model)
                if model is not None:
                    attempts.append(ProviderAttempt(
                        provider=self._provider_from_model(model),
                        model=model,
                        success=True,
                    ))
                self._emit_fallback_event(
                    request_id=request_id,
                    attempts=attempts,
                    elapsed_ms=(time.perf_counter() - started_at) * 1000,
                )
                return result, _format_trace_chain(attempts)
            except ProviderError as error:
                if model is None:
                    raise

                kind = error.failure_kind
                failure_summary[model] = FailureRecord.from_error(model, error)
                attempts.append(ProviderAttempt(
                    provider=error.provider_name or self._provider_from_model(model),
                    model=model,
                    success=False,
                    error=kind.value,
                    retry_after=error.retry_after,
                ))

                if kind == FailureKind.EXHAUSTED:
                    raise
                if not auto_fallback:
                    raise
                if kind not in SHOULD_RETRY_KINDS:
                    raise

                tried_models.add(model)
                next_model = self._select_fallback_model(
                    selection_type=selection_type,
                    failed_model=model,
                    failure_kind=kind,
                    retry_after=error.retry_after,
                    exclude=tried_models,
                    min_context=min_context,
                    failure_summary=failure_summary,
                )
                if next_model is None:
                    raise
                model = next_model

    async def _stream_with_fallback_async(
        self,
        *,
        selection_type: ModelSelectionType,
        initial_model: str,
        min_context: int,
        auto_fallback: bool,
        stream_attempt: Callable[[str], AsyncIterator[StreamChunk]],
    ) -> AsyncIterator[StreamChunk]:
        """Run an async streaming dispatch loop with pre-output fallback."""
        # Keep behavior mirrored with _stream_with_fallback_sync except for
        # async iteration over stream_attempt.
        model = initial_model
        tried_models: set[str] = set()
        failure_summary: dict[str, FailureRecord] = {}
        attempts: list[ProviderAttempt] = []
        request_id = uuid4().hex
        started_at = time.perf_counter()
        # Request-lifetime output state: once any attempt reaches the user,
        # later failures must surface instead of switching models mid-stream.
        partial_content_chars = 0
        emitted_semantic_output = False

        while True:
            try:
                async for chunk in stream_attempt(model):
                    content_chars = len(chunk.content or "")
                    semantic_output = self._stream_chunk_has_semantic_output(chunk)
                    yield chunk
                    partial_content_chars += content_chars
                    emitted_semantic_output = (
                        emitted_semantic_output or semantic_output
                    )

                attempts.append(ProviderAttempt(
                    provider=self._provider_from_model(model),
                    model=model,
                    success=True,
                ))

                trace_chain = _format_trace_chain(attempts)
                self._emit_fallback_event(
                    request_id=request_id,
                    attempts=attempts,
                    elapsed_ms=(time.perf_counter() - started_at) * 1000,
                )
                if trace_chain:
                    # Consumer trace metadata complements the structured
                    # provider_fallback telemetry event above.
                    yield StreamChunk(
                        content="",
                        model=model,
                        provider=self._provider_from_model(model),
                        metadata={"trace_chain": trace_chain},
                    )
                return

            except ProviderError as error:
                kind = error.failure_kind
                failure_summary[model] = FailureRecord.from_error(model, error)
                attempts.append(ProviderAttempt(
                    provider=error.provider_name or self._provider_from_model(model),
                    model=model,
                    success=False,
                    error=kind.value,
                    retry_after=error.retry_after,
                ))

                if partial_content_chars > 0 or emitted_semantic_output:
                    error.context = {
                        **error.context,
                        "partial_content_chars": partial_content_chars,
                        "emitted_semantic_output": emitted_semantic_output,
                    }
                    raise
                if kind == FailureKind.EXHAUSTED:
                    raise
                if not auto_fallback:
                    raise
                if kind not in SHOULD_RETRY_KINDS:
                    raise
                if self.model_selector is None:
                    raise

                tried_models.add(model)
                next_model = self._select_fallback_model(
                    selection_type=selection_type,
                    failed_model=model,
                    failure_kind=kind,
                    retry_after=error.retry_after,
                    exclude=tried_models,
                    min_context=min_context,
                    failure_summary=failure_summary,
                )
                if next_model is None:
                    raise
                model = next_model

    @staticmethod
    def _stream_chunk_has_semantic_output(chunk: StreamChunk) -> bool:
        """Return whether a chunk exposed non-text semantic output."""
        return bool(chunk.tool_call_fragments)

    @staticmethod
    def _provider_from_model(model: str) -> str:
        """Extract provider prefix from a provider/model string."""
        if "/" in model:
            return model.split("/", 1)[0]
        return model

    def _emit_fallback_event(
        self,
        *,
        request_id: str,
        attempts: list[ProviderAttempt],
        elapsed_ms: float,
    ) -> None:
        """Emit a structured event after a successful fallback."""
        if len(attempts) <= 1 or not attempts[-1].success:
            return

        failed = next(
            (attempt for attempt in reversed(attempts[:-1]) if not attempt.success),
            None,
        )
        if failed is None:
            return

        failure_kind_value = failed.error or FailureKind.UNKNOWN.value
        try:
            scope = get_failure_policy(FailureKind(failure_kind_value)).scope.value
        except ValueError:
            scope = None

        successful = attempts[-1]
        provider_fallback_metrics.record_fallback(
            from_provider=failed.provider,
            to_provider=successful.provider,
            failure_kind=failure_kind_value,
        )
        logger.info(
            "provider_fallback",
            extra={
                "event": "provider_fallback",
                "request_id": request_id,
                "attempt_n": len(attempts),
                "from_model": failed.model,
                "from_provider": failed.provider,
                "to_model": successful.model,
                "to_provider": successful.provider,
                "failure_kind": failure_kind_value,
                "retry_after": failed.retry_after,
                "scope": scope,
                "elapsed_ms": elapsed_ms,
            },
        )

    def refresh_provider_configuration(self) -> bool:
        """
        Reload provider configuration after setup changes.

        The orchestrator owns this path so LiteLLM router refresh, model
        selection refresh, and credential-related health clearing stay in sync.
        """
        configured = False
        if self.llm_service is not None:
            configured = self.llm_service.configure()

        if self.model_selector is not None:
            api_key_service = create_api_key_service()
            configured_models = {
                metadata.model_id
                for metadata in get_configured_models(api_key_service)
            }
            self.model_selector.update_configured(configured_models)
            self.model_selector.clear_failure_kinds({
                FailureKind.AUTH,
                FailureKind.PAYMENT_REQUIRED,
            })

        return configured

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
        if "trace_chain" in task_record:
            metadata["trace_chain"] = task_record["trace_chain"]

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
    def providers(self) -> ProviderRegistryProtocol:
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
                    # New rolling window metrics
                    'success_rate': status.success_rate,
                    'avg_latency_ms': status.avg_latency_ms,
                    'total_tokens': status.total_tokens,
                    'window_size': status.window_size,
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

    def save_session(self, conversation_history: Optional[list] = None) -> str:
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
            selection_type: What kind of model to use (FAST, CHAT, INSTRUCT, etc.)
            **kwargs: Additional provider-specific arguments

        Returns:
            LLMResponse from successful provider

        Raises:
            AllProvidersRateLimitedError: If all providers are rate limited
            ProviderNotFoundError: If no providers are available
            ValueError: If no models configured for selection type
        """
        # Determine selection type based on quality_mode if not explicitly provided.
        if selection_type is None:
            # Explicit provider or group hints take precedence over quality_mode.
            selection_type = (
                selection_type_for_provider_hint(provider_name)
                if provider_name is not None
                else ModelSelectionType.CHAT if self.quality_mode else ModelSelectionType.FAST
            )

        min_context = self._min_context_for(selection_type)

        # Use ModelSelectionService for deterministic model selection.
        model = self._select_initial_model(selection_type, model, min_context)

        # Fallback: if no model_selector or model still None, use legacy provider selection
        if model is None:
            if provider_name is None:
                provider_name = self.get_recommended_provider(selection_type)
                if provider_name is None:
                    available = list(self.providers.list_available())
                    raise ProviderNotFoundError(
                        "No provider available for auto-select",
                        provider_name="<auto-select>",
                        available_providers=available
                    )

        # Determine cache setting
        should_use_cache = use_cache if use_cache is not None else self.caching_enabled

        provider_hint = provider_name or selection_type.value

        def run_attempt(attempt_model: Optional[str]) -> tuple[LLMResponse, dict]:
            return self.delegation_manager.delegate(
                provider_name=provider_hint,
                prompt=prompt,
                model=attempt_model,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                use_context=use_context,
                use_cache=should_use_cache,
                intent_classification=intent_classification,
                max_retries=max_retries,
                selection_type=selection_type.value,
                min_context=min_context,
                **kwargs
            )

        (response, task_record), trace_chain = self._dispatch_sync_with_fallback(
            selection_type=selection_type,
            initial_model=model,
            min_context=min_context,
            auto_fallback=auto_fallback,
            run_attempt=run_attempt,
        )

        if trace_chain:
            task_record["trace_chain"] = trace_chain
            task_record["fallback"] = True

        self._record_task_completion(task_record, is_async=False)
        return response

    def stream_completion_with_fallback(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        selection_type: Optional[ModelSelectionType] = None,
        auto_fallback: bool = True,
        **kwargs
    ) -> Iterator[StreamChunk]:
        """
        Stream completion with automatic model selection and fallback on rate limit.

        This is the streaming equivalent of delegate() - it handles:
        - Model selection via model_selector (if no model provided)
        - Rate limit detection and automatic fallback to another model
        - Session-sticky model preferences

        Args:
            messages: Chat messages in OpenAI format
            model: Specific model ID (optional - will select if not provided)
            selection_type: Model selection type (default: INSTRUCT)
            auto_fallback: Automatically try another model before output is emitted.
            **kwargs: Additional params (max_tokens, temperature, tools, etc.)

        Yields:
            StreamChunk objects as they arrive from the provider

        Raises:
            AllModelsRateLimitedError: If all models are rate limited
            ValueError: If no models configured for selection type
        """
        if self.llm_service is None:
            raise ValueError("LLM service not configured")
        llm_service = self.llm_service

        # Default to INSTRUCT for agent work
        if selection_type is None:
            selection_type = ModelSelectionType.INSTRUCT

        min_context = self._min_context_for(selection_type)

        # Select model if not provided.
        model = self._select_initial_model(selection_type, model, min_context)

        if model is None:
            raise ValueError(f"No model available for {selection_type.value}")

        def stream_attempt(attempt_model: str) -> Iterator[StreamChunk]:
            yield from llm_service.stream_completion_direct(
                model=attempt_model,
                messages=messages,
                **kwargs,
            )

        yield from self._stream_with_fallback_sync(
            selection_type=selection_type,
            initial_model=model,
            min_context=min_context,
            auto_fallback=auto_fallback,
            stream_attempt=stream_attempt,
        )

    def delegate_structured(
        self,
        provider_name: str,
        prompt: str,
        response_model: type,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        auto_fallback: bool = True,
        selection_type: Optional[ModelSelectionType | str] = None,
        min_context: Optional[int] = None,
        **kwargs
    ):
        """
        Delegate with structured output validation using Instructor.

        Returns a validated Pydantic model instance instead of raw text.
        Uses Instructor for automatic validation and retry on parse failures.

        Args:
            provider_name: Provider/group hint (e.g., "fast", "quality")
            prompt: The user prompt to send
            response_model: Pydantic model class to validate response against
            system_prompt: Optional system prompt for behavioral instructions
            model: Specific model ID. If provided, bypasses initial selection.
            auto_fallback: Automatically try other models on retryable failures.
            selection_type: Selection type or value used for fallback candidates.
            min_context: Minimum required context window.
            **kwargs: Additional params (max_retries, mode_override, etc.)

        Returns:
            Validated instance of response_model

        Raises:
            pydantic.ValidationError: If response cannot be validated after retries
            AllProvidersRateLimitedError: When all providers exhausted
        """
        if isinstance(selection_type, ModelSelectionType):
            resolved_selection_type = selection_type
        elif selection_type:
            resolved_selection_type = ModelSelectionType(selection_type)
        else:
            resolved_selection_type = selection_type_for_provider_hint(provider_name)

        resolved_min_context = (
            self._min_context_for(resolved_selection_type)
            if min_context is None
            else min_context
        )
        selected_model = self._select_initial_model(
            resolved_selection_type,
            model,
            resolved_min_context,
        )

        def run_attempt(attempt_model: Optional[str]):
            return self.delegation_manager.delegate_structured_sync(
                provider_name=provider_name,
                prompt=prompt,
                response_model=response_model,
                system_prompt=system_prompt,
                model=attempt_model,
                selection_type=resolved_selection_type.value,
                min_context=resolved_min_context,
                **kwargs,
            )

        result, _trace_chain = self._dispatch_sync_with_fallback(
            selection_type=resolved_selection_type,
            initial_model=selected_model,
            min_context=resolved_min_context,
            auto_fallback=auto_fallback,
            run_attempt=run_attempt,
        )
        return result

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
        auto_fallback: bool = True,
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
            auto_fallback: Automatically try another model before output is emitted.
            selection_type: What kind of model to use (FAST, CHAT, INSTRUCT, etc.)
            **kwargs: Additional provider-specific arguments

        Yields:
            StreamChunk objects as they arrive from the provider

        Raises:
            AllModelsRateLimitedError: If all selected models are unhealthy
            ProviderNotFoundError: If no providers are available
            ValueError: If no models configured for selection type

        Example:
            async for chunk in orchestrator.stream_delegate(
                prompt="Write a story about a robot",
                max_tokens=500
            ):
                print(chunk.content, end="", flush=True)
        """
        # Determine selection type based on quality_mode if not explicitly provided.
        if selection_type is None:
            # Explicit provider or group hints take precedence over quality_mode.
            selection_type = (
                selection_type_for_provider_hint(provider_name)
                if provider_name is not None
                else ModelSelectionType.CHAT if self.quality_mode else ModelSelectionType.FAST
            )

        min_context = self._min_context_for(selection_type)

        # Use ModelSelectionService for deterministic model selection.
        model = self._select_initial_model(selection_type, model, min_context)

        if self.delegation_manager is None:
            raise ValueError("Delegation manager not configured")
        delegation_manager = self.delegation_manager

        # Fallback: if no model_selector or model still None, use legacy provider selection
        if model is None:
            if provider_name is None:
                provider_name = self.get_recommended_provider(selection_type)
                if provider_name is None:
                    available = list(self.providers.list_available())
                    raise ProviderNotFoundError(
                        "No provider available for auto-select",
                        provider_name="<auto-select>",
                        available_providers=available
                    )

        # Determine cache setting
        should_use_cache = use_cache if use_cache is not None else self.caching_enabled
        provider_hint = provider_name or selection_type.value

        async def stream_attempt(attempt_model: str) -> AsyncIterator[StreamChunk]:
            async for chunk in delegation_manager.stream_delegate(
                provider_name=provider_hint,
                prompt=prompt,
                model=attempt_model,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                use_context=use_context,
                use_cache=should_use_cache,
                min_context=min_context,
                **kwargs
            ):
                yield chunk

        if model is None:
            # Legacy no-model-selector streaming uses provider hints directly
            # and does not participate in orchestrator self-healing telemetry.
            async for chunk in delegation_manager.stream_delegate(
                provider_name=provider_hint,
                prompt=prompt,
                model=None,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                use_context=use_context,
                use_cache=should_use_cache,
                min_context=min_context,
                **kwargs
            ):
                yield chunk
            return

        async for chunk in self._stream_with_fallback_async(
            selection_type=selection_type,
            initial_model=model,
            min_context=min_context,
            auto_fallback=auto_fallback,
            stream_attempt=stream_attempt,
        ):
            yield chunk

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
        selection_type: Optional[ModelSelectionType] = None,
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
            selection_type: What kind of model to use (FAST, CHAT, INSTRUCT, etc.)
            **kwargs: Additional provider-specific arguments

        Returns:
            LLMResponse from successful provider

        Raises:
            AllModelsRateLimitedError: If all selected models are unhealthy
            Exception: Other non-rate-limit errors
        """
        if selection_type is None:
            # Explicit provider or group hints take precedence over quality_mode.
            selection_type = (
                selection_type_for_provider_hint(provider_name)
                if provider_name is not None
                else ModelSelectionType.CHAT if self.quality_mode else ModelSelectionType.FAST
            )

        min_context = self._min_context_for(selection_type)
        model = self._select_initial_model(selection_type, model, min_context)

        if self.delegation_manager is None:
            raise ValueError("Delegation manager not configured")
        delegation_manager = self.delegation_manager

        # Determine cache setting
        should_use_cache = use_cache if use_cache is not None else self.caching_enabled
        provider_hint = provider_name or selection_type.value

        async def run_attempt(attempt_model: Optional[str]) -> tuple[LLMResponse, dict]:
            return await delegation_manager.delegate_async(
                provider_name=provider_hint,
                prompt=prompt,
                model=attempt_model,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                use_context=use_context,
                use_cache=should_use_cache,
                intent_classification=intent_classification,
                max_retries=max_retries,
                selection_type=selection_type.value,
                min_context=min_context,
                **kwargs
            )

        (response, task_record), trace_chain = await self._dispatch_async_with_fallback(
            selection_type=selection_type,
            initial_model=model,
            min_context=min_context,
            auto_fallback=auto_fallback,
            run_attempt=run_attempt,
        )

        if trace_chain:
            task_record["trace_chain"] = trace_chain
            task_record["fallback"] = True

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

        This intentionally bypasses orchestrator-level model fallback so each
        batch item keeps the provider/model routing supplied by the caller.

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

        This intentionally bypasses orchestrator-level model fallback because
        each provider is queried as an independent comparison target.

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

    def cancel_all_background_tasks(self) -> int:
        """
        Cancel all pending background tasks.

        Called during shutdown to prevent tasks from blocking exit.

        Returns:
            Number of tasks that were cancelled
        """
        return self.background_manager.cancel_all_tasks()

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
