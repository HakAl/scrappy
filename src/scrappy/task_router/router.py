"""
Central task router that dispatches to appropriate execution strategies.
"""

import time
import warnings
from dataclasses import replace
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple, Union

from .classifier import ClassifiedTask, TaskClassifier, TaskType
from .factory import create_task_classifier
from ..llm.models import TaskClassification as LLMTaskClassification
from ..llm.models import TaskType as LLMTaskType
from .intent_clarifier import (
    AutoClarifier,
    InteractiveClarifier,
)
from .config import ClarificationConfig
from .protocols import (
    ClarificationConfigProtocol,
    DefaultConsoleInput,
    IntentClarifierProtocol,
    TaskRouterInputProtocol,
)
from .metrics_collector import MetricsCollector, RouterMetrics
from .output_handler import (
    ConsoleOutputHandler,
    NullOutputHandler,
)
from .protocols import OutputHandlerProtocol
from .provider_resolver import ProviderResolver
from ..orchestrator.model_selection import ModelSelectionType
from .pure_functions import (
    build_classification_metadata,
    create_escalated_task,
    determine_execution_action,
    needs_clarification,
    should_escalate_confidence,
)
from .strategies import (
    AgentExecutor,
    ConversationExecutor,
    DirectExecutor,
    ExecutionResult,
    OrchestratorLike,
    ResearchExecutor,
)
from .protocols import ExecutionStrategyProtocol
from .validator import InputValidator
from ..protocols.output import StreamingOutputProtocol


class TaskRouter:
    """
    Central dispatcher for task-type aware execution.

    Automatically classifies tasks and routes them to optimal strategies:
    - DIRECT_COMMAND → DirectExecutor (no agent loop)
    - CODE_GENERATION → AgentExecutor (full planning)
    - RESEARCH → ResearchExecutor (fast provider)
    - CONVERSATION → ConversationExecutor (simple responses)
    """

    def __init__(
        self,
        orchestrator: Optional[OrchestratorLike] = None,
        project_root: Optional[Path] = None,
        auto_confirm_direct: bool = False,
        verbose: bool = True,
        intent_clarifier: Optional[IntentClarifierProtocol] = None,
        output_handler: Optional[OutputHandlerProtocol] = None,
        input_handler: Optional[TaskRouterInputProtocol] = None,
        validator: Optional[InputValidator] = None,
        classifier: Optional[TaskClassifier] = None,
        metrics_collector: Optional[MetricsCollector] = None,
        provider_resolver: Optional[ProviderResolver] = None,
        strategies: Optional[Dict[TaskType, ExecutionStrategyProtocol]] = None,
        clarification_config: Optional[ClarificationConfigProtocol] = None,
        io: Optional[Any] = None,  # CLIIOProtocol - for passing to AgentExecutor
    ):
        """
        Initialize TaskRouter with execution strategies.

        Args:
            orchestrator: LLM orchestrator for AI-powered tasks
            project_root: Project directory for file operations
            auto_confirm_direct: Skip confirmation for direct commands
            verbose: Print routing decisions
            intent_clarifier: Injectable clarifier for ambiguous tasks (default: InteractiveClarifier)
            output_handler: Injectable output handler (default: based on verbose)
            input_handler: Injectable input handler for user prompts/confirmations
                          (default: DefaultConsoleInput). IMPORTANT: In Textual mode,
                          inject CLIIOInputAdapter to avoid blocking on input().
            validator: Injectable input validator (default: InputValidator)
            classifier: Injectable task classifier (default: TaskClassifier)
            metrics_collector: Injectable metrics collector (default: MetricsCollector)
            provider_resolver: Injectable provider resolver (default: ProviderResolver)
            strategies: Injectable execution strategies (default: created via factory)
            clarification_config: Injectable config for clarification behavior
                                 (default: ClarificationConfig with default thresholds)
            io: CLIIOProtocol instance for passing to AgentExecutor. In TUI mode,
                this should be the bridged UnifiedIO to avoid deadlocks.
        """
        self.orchestrator = orchestrator
        self.project_root = project_root or Path.cwd()
        self.auto_confirm_direct = auto_confirm_direct
        self.verbose = verbose
        self._io = io  # Store for passing to AgentExecutor

        # Input handler for user interaction (confirmations, prompts)
        self._input_handler = input_handler or DefaultConsoleInput()

        # Dependency injection - use provided or create defaults
        self.intent_clarifier = intent_clarifier or InteractiveClarifier(io=self._input_handler)
        self.output_handler = output_handler or (
            ConsoleOutputHandler() if verbose else NullOutputHandler()
        )
        self.validator = validator or InputValidator()

        # Use factory to get classifier with SemanticRouter (lazy init, no warm_up here)
        self.classifier = classifier or create_task_classifier(warm_up=False)
        self.metrics_collector = metrics_collector or MetricsCollector()
        self.provider_resolver = provider_resolver or ProviderResolver(orchestrator=orchestrator)

        # Inject strategies or use defaults
        self.strategies: Dict[TaskType, ExecutionStrategyProtocol] = (
            strategies or self._create_default_strategies()
        )

        # Pre/post hooks for extensibility
        self._pre_hooks: List[Callable[[ClassifiedTask], ClassifiedTask]] = []
        self._post_hooks: List[Callable[[ExecutionResult], ExecutionResult]] = []

        # Clarification configuration (injectable for testing)
        if clarification_config is None:
            warnings.warn(
                "Default confidence_threshold changed from 0.65 to 0.7 in v2.0. "
                "Pass explicit ClarificationConfig to suppress this warning.",
                DeprecationWarning,
                stacklevel=2,
            )
            clarification_config = ClarificationConfig()
        self._clarification_config = clarification_config

        # Intent clarification settings
        # Intent clarification disabled: Semantic router + auto-escalation
        # handles ambiguity without interrupting user flow
        self.clarify_on_low_confidence = False
        self.escalate_on_low_confidence = True
        self.use_llm_classification = True  # Use LLM for low-confidence cases

    @property
    def confidence_threshold(self) -> float:
        """Get confidence threshold from config (for backwards compatibility)."""
        return self._clarification_config.confidence_threshold

    def _create_default_strategies(self) -> Dict[TaskType, ExecutionStrategyProtocol]:
        """Create default execution strategies (factory method for defaults only)."""
        strategies: Dict[TaskType, ExecutionStrategyProtocol] = {}

        # Direct command executor (no AI needed)
        strategies[TaskType.DIRECT_COMMAND] = DirectExecutor(
            working_dir=self.project_root,
            require_confirmation=not self.auto_confirm_direct
        )

        # AI-powered strategies (require orchestrator)
        if self.orchestrator:
            # Conversation handler (requires LLM)
            strategies[TaskType.CONVERSATION] = ConversationExecutor(
                orchestrator=self.orchestrator
            )
            # Provider will be resolved dynamically per task
            strategies[TaskType.RESEARCH] = ResearchExecutor(
                orchestrator=self.orchestrator,
                project_root=self.project_root,
                max_tool_iterations=3
            )

            strategies[TaskType.CODE_GENERATION] = AgentExecutor(
                orchestrator=self.orchestrator,
                project_root=self.project_root,
                max_iterations=50,
                require_approval=True,
                io=self._io,
            )

        return strategies

    def _needs_intent_clarification(self, task: ClassifiedTask) -> bool:
        """
        Check if task needs user clarification due to ambiguity.

        Delegates to pure function for the calculation logic.

        Returns True when:
        - Confidence is below threshold
        - Confidence is in medium range AND has conflicting signals

        Returns False when:
        - Confidence is at or above high_confidence_bypass (trust the classifier)
        """
        return needs_clarification(task, self._clarification_config)

    def _clarify_intent(self, task: ClassifiedTask) -> ClassifiedTask:
        """
        Ask user to clarify their intent when classification is ambiguous.

        Uses the injected intent_clarifier to enable testability.
        """
        return self.intent_clarifier.clarify(task)

    def _apply_confidence_escalation(self, task: ClassifiedTask) -> ClassifiedTask:
        """
        Escalate task to more capable executor when confidence is low.

        If classified as RESEARCH with low confidence but has action indicators,
        escalate to CODE_GENERATION which can do everything RESEARCH can + more.

        Uses pure functions for calculation, keeps logging as side effect.
        """
        if not self.escalate_on_low_confidence:
            return task

        # Use pure function to determine if escalation is needed
        if should_escalate_confidence(task, threshold=0.7):
            original_type = task.task_type.value
            # Use pure function to create escalated task
            task = create_escalated_task(task)
            # Side effect: logging
            if self.verbose:
                self.output_handler.log_info(f"Escalated: {original_type} -> CODE_GENERATION (low confidence + action words)")

        return task

    def _classify_with_llm(self, task: ClassifiedTask) -> ClassifiedTask:
        """
        Use LLM to semantically classify ambiguous tasks.

        Called when rule-based classification has low confidence.
        Uses Instructor for validated structured output.

        Args:
            task: Initially classified task with low confidence

        Returns:
            Task with potentially updated classification based on LLM analysis
        """
        if not self.orchestrator:
            return task

        if self.verbose:
            self.output_handler.log_info("Using LLM for semantic classification...")

        # Behavioral instructions go in system prompt (not Field descriptions)
        system_prompt = """You are a task classifier. Analyze the user's request and classify it into ONE of these categories:

1. RESEARCH - User wants information, explanation, or analysis (reading/learning)
2. CODE_GENERATION - User wants you to create, modify, or write code/files (doing/acting)
3. DIRECT_COMMAND - User wants to run a specific shell command
4. CONVERSATION - Simple greeting or acknowledgment

IMPORTANT: Focus on the user's PRIMARY INTENT:
- "Explain X" or "How does X work?" = RESEARCH (they want to learn)
- "Create X" or "Write X for me" = CODE_GENERATION (they want action)
- "Explain how to create X" = RESEARCH (they want to learn how, not have you do it)
- "Create X and explain it" = CODE_GENERATION (primary intent is creation)"""

        user_prompt = f"""Classify this user request:
"{task.original_input}"

Current rule-based classification: {task.task_type.value} (confidence: {task.confidence:.2f})
Rule-based reasoning: {task.reasoning}

What is the user's PRIMARY intent?"""

        # Map LLM TaskType enum to router TaskType enum
        llm_to_router_type = {
            LLMTaskType.RESEARCH: TaskType.RESEARCH,
            LLMTaskType.CODE_GENERATION: TaskType.CODE_GENERATION,
            LLMTaskType.DIRECT_COMMAND: TaskType.DIRECT_COMMAND,
            LLMTaskType.CONVERSATION: TaskType.CONVERSATION,
        }

        try:
            # Use structured output for validated classification
            result: LLMTaskClassification = self.orchestrator.delegate_structured(
                provider_name="fast",  # Model group, not specific provider
                prompt=user_prompt,
                response_model=LLMTaskClassification,
                system_prompt=system_prompt,
                max_tokens=200,
                temperature=0.1,  # Low temperature for consistent classification
            )

            # Map LLM TaskType to router TaskType
            new_type = llm_to_router_type.get(result.task_type)
            if new_type is None:
                if self.verbose:
                    self.output_handler.log_info(f"Unknown task type from LLM: {result.task_type}")
                return task

            # Only accept LLM classification if it's confident
            if result.confidence >= 0.7:
                old_type = task.task_type.value
                task = replace(
                    task,
                    task_type=new_type,
                    confidence=result.confidence,
                    reasoning=f"LLM semantic classification: {result.reasoning} (was {old_type}, confidence {result.confidence:.2f})"
                )

                if self.verbose:
                    if old_type != new_type.value:
                        self.output_handler.log_info(f"LLM reclassified: {old_type} -> {new_type.value} ({result.confidence:.0%})")
                    else:
                        self.output_handler.log_info(f"LLM confirmed: {new_type.value} ({result.confidence:.0%})")
            else:
                if self.verbose:
                    self.output_handler.log_info(f"LLM uncertain ({result.confidence:.0%}), keeping rule-based classification")

        except Exception as e:
            if self.verbose:
                self.output_handler.log_info(f"LLM classification failed: {e}")

        return task

    def _resolve_provider(self, hint: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolve provider hint to actual provider name and model.

        Args:
            hint: Provider hint ("fast", "quality", etc.) or None

        Returns:
            Tuple of (provider_name, model_name) or (None, None) if no resolution needed
        """
        if hint is None:
            return (None, None)

        # Convert string hint to ModelSelectionType
        selection_type = self._hint_to_selection_type(hint)
        return self.provider_resolver.resolve(selection_type)

    def _hint_to_selection_type(self, hint: str) -> Optional[ModelSelectionType]:
        """
        Convert string hint to ModelSelectionType enum.

        Args:
            hint: String hint like "fast", "quality", "planning"

        Returns:
            ModelSelectionType or None if unknown
        """
        hint_lower = hint.lower()

        # Map legacy hints to new enum values
        if hint_lower in ['fast', 'high_volume', 'general']:
            return ModelSelectionType.FAST
        elif hint_lower in ['quality', 'chat']:
            return ModelSelectionType.CHAT
        elif hint_lower == 'planning':
            return ModelSelectionType.INSTRUCT
        elif hint_lower == 'embed':
            return ModelSelectionType.EMBED

        # Unknown hint - default to FAST
        return ModelSelectionType.FAST

    def route(self, user_input: str, *, provider: Optional[str] = None) -> ExecutionResult:
        """
        Route user input to appropriate execution strategy.

        Args:
            user_input: User's task/query
            provider: Optional provider hint ("fast", "quality") or specific provider name

        Returns:
            ExecutionResult with output and metadata
        """
        start_time = time.time()

        # 0. Validate input at boundary
        is_valid, error_message = self.validator.validate_user_input(user_input)
        if not is_valid:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Invalid input: {error_message}",
                execution_time=time.time() - start_time
            )

        # 1. Classify the task
        classified = self.classifier.classify(user_input)

        # 2. Apply provider override if specified
        if provider:
            classified = replace(classified, override_provider=provider)

        if self.verbose:
            self._log_classification(classified)

        # 2. Apply confidence escalation (auto-upgrade low-confidence tasks)
        classified = self._apply_confidence_escalation(classified)

        # 3. LLM fallback for low-confidence classifications
        if self.use_llm_classification and classified.confidence < self.confidence_threshold:
            if self.verbose:
                self.output_handler.log_info(f"Low confidence ({classified.confidence:.0%}) - trying LLM classification")
            classified = self._classify_with_llm(classified)

        # 4. Clarify intent if still needed (ask user when ambiguous)
        # Only ask user if LLM classification also has low confidence
        if self.clarify_on_low_confidence and self._needs_intent_clarification(classified):
            classified = self._clarify_intent(classified)

        # 5. Resolve provider (override takes precedence over suggestion)
        provider_hint = classified.override_provider or classified.suggested_provider
        provider_name, model_name = self._resolve_provider(provider_hint)

        if self.verbose and provider_name:
            model_info = f" ({model_name})" if model_name else ""
            source = "override" if classified.override_provider else "hint"
            self.output_handler.log_provider_selection(
                provider=provider_name,
                model=model_name,
                source=f"{source}: {provider_hint}"
            )

        # 3. Apply pre-execution hooks
        for hook in self._pre_hooks:
            classified = hook(classified)

        # 4. Get appropriate strategy
        strategy = self._get_strategy(classified)

        if not strategy:
            return ExecutionResult(
                success=False,
                output="",
                error=f"No strategy available for task type: {classified.task_type}",
                execution_time=time.time() - start_time
            )

        # 5. Confirm execution if needed
        if not self._should_execute(classified, strategy):
            return ExecutionResult(
                success=False,
                output="",
                error="Execution cancelled by user",
                execution_time=time.time() - start_time
            )

        # 6. Execute with resolved provider
        if self.verbose:
            self.output_handler.log_execution_start(strategy.name)

        # Pass resolved provider info to strategy if it supports it
        if hasattr(strategy, 'set_provider'):
            strategy.set_provider(provider_name, model_name)

        result = strategy.execute(classified)

        # 7. Apply post-execution hooks
        for hook in self._post_hooks:
            result = hook(result)

        # 8. Update metrics
        self._update_metrics(classified, result)

        # 9. Add classification info to result using pure function
        result.metadata["classification"] = build_classification_metadata(
            classified, provider_name, model_name
        )

        return result

    def _prepare_for_execution(
        self,
        user_input: str,
        provider: Optional[str] = None
    ) -> Tuple[Optional[ClassifiedTask], Optional[ExecutionStrategyProtocol], Optional[str], Optional[str], Optional[ExecutionResult]]:
        """
        Prepare task for execution - shared logic between route() and route_streaming().

        Performs validation, classification, provider resolution, and strategy selection.

        Args:
            user_input: User's task/query
            provider: Optional provider hint

        Returns:
            Tuple of (classified_task, strategy, provider_name, model_name, error_result)
            If error_result is not None, the other values should be ignored.
        """
        start_time = time.time()

        # 0. Validate input at boundary
        is_valid, error_message = self.validator.validate_user_input(user_input)
        if not is_valid:
            return (None, None, None, None, ExecutionResult(
                success=False,
                output="",
                error=f"Invalid input: {error_message}",
                execution_time=time.time() - start_time
            ))

        # 1. Classify the task
        classified = self.classifier.classify(user_input)

        # 2. Apply provider override if specified
        if provider:
            classified = replace(classified, override_provider=provider)

        if self.verbose:
            self._log_classification(classified)

        # 3. Apply confidence escalation (auto-upgrade low-confidence tasks)
        classified = self._apply_confidence_escalation(classified)

        # 4. LLM fallback for low-confidence classifications
        if self.use_llm_classification and classified.confidence < self.confidence_threshold:
            if self.verbose:
                self.output_handler.log_info(f"Low confidence ({classified.confidence:.0%}) - trying LLM classification")
            classified = self._classify_with_llm(classified)

        # 5. Clarify intent if still needed (ask user when ambiguous)
        if self.clarify_on_low_confidence and self._needs_intent_clarification(classified):
            classified = self._clarify_intent(classified)

        # 6. Resolve provider (override takes precedence over suggestion)
        provider_hint = classified.override_provider or classified.suggested_provider
        provider_name, model_name = self._resolve_provider(provider_hint)

        if self.verbose and provider_name:
            model_info = f" ({model_name})" if model_name else ""
            source = "override" if classified.override_provider else "hint"
            self.output_handler.log_provider_selection(
                provider=provider_name,
                model=model_name,
                source=f"{source}: {provider_hint}"
            )

        # 7. Apply pre-execution hooks
        for hook in self._pre_hooks:
            classified = hook(classified)

        # 8. Get appropriate strategy
        strategy = self._get_strategy(classified)

        if not strategy:
            return (None, None, None, None, ExecutionResult(
                success=False,
                output="",
                error=f"No strategy available for task type: {classified.task_type}",
                execution_time=time.time() - start_time
            ))

        return (classified, strategy, provider_name, model_name, None)

    async def route_streaming(
        self,
        user_input: str,
        output: StreamingOutputProtocol,
        *,
        provider: Optional[str] = None
    ) -> ExecutionResult:
        """
        Route user input with streaming output.

        Like route(), but streams response tokens/events to the output protocol
        as they arrive, enabling real-time display.

        Supports two strategy patterns:
        - ResearchExecutor: execute_streaming(task, output) -> ExecutionResult
        - AgentExecutor: execute_streaming(task) -> AsyncIterator[AgentEvent]

        Args:
            user_input: User's task/query
            output: Streaming output protocol for real-time display
            provider: Optional provider hint ("fast", "quality") or specific provider name

        Returns:
            ExecutionResult with output and metadata
        """
        start_time = time.time()

        # Prepare task (shared with route())
        classified, strategy, provider_name, model_name, error_result = self._prepare_for_execution(
            user_input, provider
        )

        if error_result:
            return error_result

        # Confirm execution if needed
        if not self._should_execute(classified, strategy):
            return ExecutionResult(
                success=False,
                output="",
                error="Execution cancelled by user",
                execution_time=time.time() - start_time
            )

        # Execute with streaming
        if self.verbose:
            self.output_handler.log_execution_start(strategy.name)

        # Pass resolved provider info to strategy if it supports it
        if hasattr(strategy, 'set_provider'):
            strategy.set_provider(provider_name, model_name)

        # Check if strategy supports streaming
        if hasattr(strategy, 'execute_streaming'):
            result = await self._execute_streaming(strategy, classified, output)
        else:
            # Fallback to non-streaming execution
            if self.verbose:
                self.output_handler.log_info(f"Strategy {strategy.name} does not support streaming, falling back to sync")
            result = strategy.execute(classified)

        # Apply post-execution hooks
        for hook in self._post_hooks:
            result = hook(result)

        # Update metrics
        self._update_metrics(classified, result)

        # Add classification info to result
        result.metadata["classification"] = build_classification_metadata(
            classified, provider_name, model_name
        )

        return result

    async def _execute_streaming(
        self,
        strategy: ExecutionStrategyProtocol,
        task: ClassifiedTask,
        output: StreamingOutputProtocol
    ) -> ExecutionResult:
        """
        Execute strategy with streaming, handling different strategy patterns.

        Adapts to two patterns:
        - Pattern A (ResearchExecutor): execute_streaming(task, output) -> ExecutionResult
        - Pattern B (AgentExecutor): execute_streaming(task) -> AsyncIterator[AgentEvent]
        """
        import inspect

        execute_streaming = getattr(strategy, 'execute_streaming')
        sig = inspect.signature(execute_streaming)
        params = list(sig.parameters.keys())

        # Pattern A: Takes output protocol, returns result
        if 'output' in params:
            return await execute_streaming(task, output)

        # Pattern B: Yields events (AgentExecutor pattern)
        # Iterate events, write to output, collect final result
        await output.stream_start(metadata={"task_type": task.task_type.value, "strategy": strategy.name})

        start_time = time.time()
        accumulated_content = []
        final_result = None
        tokens_used = 0
        success = True  # Default to success

        try:
            async for event in execute_streaming(task):
                # Handle different event types
                if event.event_type == "thought_token":
                    await output.stream_token(event.content)
                    accumulated_content.append(event.content)
                elif event.event_type == "thought_start":
                    pass  # Could add visual indicator
                elif event.event_type == "thought_end":
                    await output.stream_token("\n")
                    accumulated_content.append("\n")
                elif event.event_type == "action_start":
                    action_name = event.metadata.get("action", "unknown")
                    await output.stream_token(f"\n[Action: {action_name}]\n")
                    accumulated_content.append(f"\n[Action: {action_name}]\n")
                elif event.event_type == "action_end":
                    action_name = event.metadata.get("action", "unknown")
                    action_success = event.metadata.get("success", True)
                    status = "done" if action_success else "failed"
                    await output.stream_token(f"[{action_name}: {status}]\n")
                    accumulated_content.append(f"[{action_name}: {status}]\n")
                elif event.event_type == "complete":
                    final_result = event.content
                    success = event.metadata.get("success", True)
                elif event.event_type == "error":
                    from ..orchestrator.streaming_util import format_stream_error
                    error_display = format_stream_error(
                        error=event.content,
                        chunks_received=len(accumulated_content),
                        metadata=event.metadata
                    )
                    await output.stream_token(error_display)
                    accumulated_content.append(error_display)
                    final_result = event.content
                    success = False
        finally:
            await output.stream_end(metadata={"tokens": tokens_used})

        return ExecutionResult(
            success=success,
            output=final_result or "".join(accumulated_content),
            execution_time=time.time() - start_time,
            tokens_used=tokens_used,
            provider_used=strategy.name,
            metadata={"streaming": True, "event_count": len(accumulated_content)}
        )

    def _get_strategy(self, task: ClassifiedTask) -> Optional[ExecutionStrategyProtocol]:
        """Get the execution strategy for a task type."""
        strategy = self.strategies.get(task.task_type)

        if strategy and strategy.can_handle(task):
            return strategy

        # Fallback logic
        if task.task_type in [TaskType.RESEARCH, TaskType.CODE_GENERATION]:
            if not self.orchestrator:
                if self.verbose:
                    self.output_handler.log_info(f"No orchestrator available for {task.task_type}")
                # Fall back to conversation for unsupported AI tasks
                return self.strategies.get(TaskType.CONVERSATION)

        return strategy

    def _should_execute(
        self,
        task: ClassifiedTask,
        strategy: ExecutionStrategyProtocol
    ) -> bool:
        """
        Check if execution should proceed.

        Uses pure function for decision logic, keeps I/O as side effect.
        May prompt for confirmation based on task type and settings.
        """
        # Determine if command is safe (for direct commands)
        is_safe = True
        if task.task_type == TaskType.DIRECT_COMMAND and task.extracted_command:
            is_safe = self.classifier.is_safe_command(task.extracted_command)

        # Use pure function for decision
        action = determine_execution_action(
            task_type=task.task_type,
            auto_confirm=self.auto_confirm_direct,
            command=task.extracted_command,
            is_safe=is_safe
        )

        # Handle the decision with appropriate side effects
        if action == "execute":
            return True

        if action == "block":
            if self.verbose:
                self.output_handler.log_info(f"Command blocked: {task.extracted_command}")
            return False

        if action == "confirm":
            # Side effect: user interaction via injected input handler
            # (avoids blocking in Textual worker threads)
            if self.verbose:
                self.output_handler.log_info(f"Command: {task.extracted_command}")
            return self._input_handler.confirm(
                f"  Execute '{task.extracted_command}'? [y/N]: ",
                default=False
            )

        return True

    def _log_classification(self, task: ClassifiedTask):
        """Log classification decision using injected output handler."""
        self.output_handler.log_classification(
            task_type=task.task_type.value,
            confidence=task.confidence,
            complexity=task.complexity_score,
            reasoning=task.reasoning
        )

        if task.extracted_command:
            self.output_handler.log_info(f"Command: {task.extracted_command}")

        if task.requires_planning:
            self.output_handler.log_info(f"Requires planning: Yes")

    def _update_metrics(self, task: ClassifiedTask, result: ExecutionResult):
        """Update routing metrics."""
        self.metrics_collector.update(task, result)

    def add_pre_hook(self, hook: Callable[[ClassifiedTask], ClassifiedTask]):
        """Add pre-execution hook for task modification."""
        self._pre_hooks.append(hook)

    def add_post_hook(self, hook: Callable[[ExecutionResult], ExecutionResult]):
        """Add post-execution hook for result processing."""
        self._post_hooks.append(hook)

    def get_metrics(self) -> RouterMetrics:
        """Get current routing metrics."""
        return self.metrics_collector.get_metrics()

    def classify_only(self, user_input: str) -> ClassifiedTask:
        """Classify task without executing (for debugging/preview)."""
        return self.classifier.classify(user_input)

    def set_strategy(self, task_type: TaskType, strategy: ExecutionStrategyProtocol):
        """Override a strategy for a task type."""
        self.strategies[task_type] = strategy

    def __repr__(self) -> str:
        strategies = ", ".join([
            f"{t.value}: {s.name}"
            for t, s in self.strategies.items()
        ])
        return f"TaskRouter(strategies={{{strategies}}})"
