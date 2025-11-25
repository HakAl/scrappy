"""
Central task router that dispatches to appropriate execution strategies.
"""

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .classifier import ClassifiedTask, TaskClassifier, TaskType
from .intent_clarifier import (
    AutoClarifier,
    IntentClarifierInterface,
    InteractiveClarifier,
)
from .protocols import (
    ClarificationConfigProtocol,
    DefaultConsoleInput,
    TaskRouterInputProtocol,
)
from src.config.schema import ClarificationConfig
from .json_extractor import JSONExtractor
from .metrics_collector import MetricsCollector, RouterMetrics
from .output_handler import (
    ConsoleOutputHandler,
    NullOutputHandler,
    OutputHandlerInterface,
)
from .provider_resolver import ProviderResolver
from .pure_functions import (
    build_classification_metadata,
    create_escalated_task,
    determine_execution_action,
    needs_clarification,
    parse_llm_classification_response,
    should_escalate_confidence,
)
from .strategies import (
    AgentExecutor,
    ConversationExecutor,
    DirectExecutor,
    ExecutionResult,
    ExecutionStrategy,
    OrchestratorLike,
    ResearchExecutor,
)
from .validator import InputValidator


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
        intent_clarifier: Optional[IntentClarifierInterface] = None,
        output_handler: Optional[OutputHandlerInterface] = None,
        input_handler: Optional[TaskRouterInputProtocol] = None,
        validator: Optional[InputValidator] = None,
        classifier: Optional[TaskClassifier] = None,
        metrics_collector: Optional[MetricsCollector] = None,
        provider_resolver: Optional[ProviderResolver] = None,
        strategies: Optional[Dict[TaskType, ExecutionStrategy]] = None,
        clarification_config: Optional[ClarificationConfigProtocol] = None,
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
        """
        self.orchestrator = orchestrator
        self.project_root = project_root or Path.cwd()
        self.auto_confirm_direct = auto_confirm_direct
        self.verbose = verbose

        # Input handler for user interaction (confirmations, prompts)
        self._input_handler = input_handler or DefaultConsoleInput()

        # Dependency injection - use provided or create defaults
        self.intent_clarifier = intent_clarifier or InteractiveClarifier(io=self._input_handler)
        self.output_handler = output_handler or (
            ConsoleOutputHandler() if verbose else NullOutputHandler()
        )
        self.validator = validator or InputValidator()

        self.classifier = classifier or TaskClassifier()
        self.metrics_collector = metrics_collector or MetricsCollector()
        self.provider_resolver = provider_resolver or ProviderResolver(orchestrator=orchestrator)

        # Inject strategies or use defaults
        self.strategies: Dict[TaskType, ExecutionStrategy] = (
            strategies or self._create_default_strategies()
        )

        # Pre/post hooks for extensibility
        self._pre_hooks: List[Callable[[ClassifiedTask], ClassifiedTask]] = []
        self._post_hooks: List[Callable[[ExecutionResult], ExecutionResult]] = []

        # Clarification configuration (injectable for testing)
        self._clarification_config = clarification_config or ClarificationConfig()

        # Intent clarification settings
        self.clarify_on_low_confidence = True
        self.escalate_on_low_confidence = True
        self.use_llm_classification = True  # Use LLM for low-confidence cases

    @property
    def confidence_threshold(self) -> float:
        """Get confidence threshold from config (for backwards compatibility)."""
        return self._clarification_config.confidence_threshold

    def _create_default_strategies(self) -> Dict[TaskType, ExecutionStrategy]:
        """Create default execution strategies (factory method for defaults only)."""
        strategies: Dict[TaskType, ExecutionStrategy] = {}

        # Direct command executor (no AI needed)
        strategies[TaskType.DIRECT_COMMAND] = DirectExecutor(
            working_dir=self.project_root,
            require_confirmation=not self.auto_confirm_direct
        )

        # Conversation handler
        strategies[TaskType.CONVERSATION] = ConversationExecutor(
            orchestrator=self.orchestrator
        )

        # AI-powered strategies (require orchestrator)
        if self.orchestrator:
            # Provider will be resolved dynamically per task
            strategies[TaskType.RESEARCH] = ResearchExecutor(
                orchestrator=self.orchestrator,
                project_root=self.project_root,
                max_tool_iterations=3
            )

            strategies[TaskType.CODE_GENERATION] = AgentExecutor(
                orchestrator=self.orchestrator,
                project_root=self.project_root,
                max_iterations=10,
                require_approval=True
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
        Uses a fast provider for quick disambiguation.

        Args:
            task: Initially classified task with low confidence

        Returns:
            Task with potentially updated classification based on LLM analysis
        """
        if not self.orchestrator:
            return task

        if self.verbose:
            self.output_handler.log_info("Using LLM for semantic classification...")

        # Build a focused prompt for classification
        system_prompt = """You are a task classifier. Analyze the user's request and classify it into ONE of these categories:

1. RESEARCH - User wants information, explanation, or analysis (reading/learning)
2. CODE_GENERATION - User wants you to create, modify, or write code/files (doing/acting)
3. DIRECT_COMMAND - User wants to run a specific shell command
4. CONVERSATION - Simple greeting or acknowledgment

IMPORTANT: Focus on the user's PRIMARY INTENT:
- "Explain X" or "How does X work?" = RESEARCH (they want to learn)
- "Create X" or "Write X for me" = CODE_GENERATION (they want action)
- "Explain how to create X" = RESEARCH (they want to learn how, not have you do it)
- "Create X and explain it" = CODE_GENERATION (primary intent is creation)

Respond with ONLY a JSON object:
{
  "task_type": "RESEARCH" | "CODE_GENERATION" | "DIRECT_COMMAND" | "CONVERSATION",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of why this classification"
}"""

        user_prompt = f"""Classify this user request:
"{task.original_input}"

Current rule-based classification: {task.task_type.value} (confidence: {task.confidence:.2f})
Rule-based reasoning: {task.reasoning}

What is the user's PRIMARY intent? Respond with JSON only."""

        try:
            # Use fast provider for quick classification
            provider_to_use = None
            if hasattr(self.orchestrator, 'providers'):
                available = self.orchestrator.providers.list_available()
                # Prefer fast providers
                for pref in ['cerebras', 'groq', 'gemini']:
                    if pref in available:
                        provider_to_use = pref
                        break

            if not provider_to_use:
                if self.verbose:
                    self.output_handler.log_info("No provider available for LLM classification")
                return task

            # Make LLM call
            response = self.orchestrator.delegate(
                provider_to_use,
                user_prompt,
                system_prompt=system_prompt,
                max_tokens=200,
                temperature=0.1,  # Low temperature for consistent classification
                use_context=False
            )

            # Parse response using pure function
            response_text = response.content.strip()
            result = parse_llm_classification_response(response_text)

            if result is None:
                if self.verbose:
                    self.output_handler.log_info("Failed to parse LLM classification response")
                return task

            # Update task based on LLM classification
            llm_type_str = result['task_type']
            llm_confidence = float(result['confidence'])
            llm_reasoning = result['reasoning']

            # Map string to TaskType
            type_map = {
                'RESEARCH': TaskType.RESEARCH,
                'CODE_GENERATION': TaskType.CODE_GENERATION,
                'DIRECT_COMMAND': TaskType.DIRECT_COMMAND,
                'CONVERSATION': TaskType.CONVERSATION,
            }

            if llm_type_str in type_map:
                new_type = type_map[llm_type_str]

                # Only accept LLM classification if it's confident
                if llm_confidence >= 0.7:
                    old_type = task.task_type.value
                    task = replace(
                        task,
                        task_type=new_type,
                        confidence=llm_confidence,
                        reasoning=f"LLM semantic classification: {llm_reasoning} (was {old_type}, confidence {llm_confidence:.2f})"
                    )

                    if self.verbose:
                        if old_type != new_type.value:
                            self.output_handler.log_info(f"LLM reclassified: {old_type} -> {new_type.value} ({llm_confidence:.0%})")
                        else:
                            self.output_handler.log_info(f"LLM confirmed: {new_type.value} ({llm_confidence:.0%})")
                else:
                    if self.verbose:
                        self.output_handler.log_info(f"LLM uncertain ({llm_confidence:.0%}), keeping rule-based classification")

        except json.JSONDecodeError as e:
            if self.verbose:
                self.output_handler.log_info(f"Failed to parse LLM response: {e}")
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
        return self.provider_resolver.resolve(hint)

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

    def _get_strategy(self, task: ClassifiedTask) -> Optional[ExecutionStrategy]:
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
        strategy: ExecutionStrategy
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

    def set_strategy(self, task_type: TaskType, strategy: ExecutionStrategy):
        """Override a strategy for a task type."""
        self.strategies[task_type] = strategy

    def __repr__(self) -> str:
        strategies = ", ".join([
            f"{t.value}: {s.name}"
            for t, s in self.strategies.items()
        ])
        return f"TaskRouter(strategies={{{strategies}}})"
