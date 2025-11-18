"""
Central task router that dispatches to appropriate execution strategies.
"""

import json
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .classifier import ClassifiedTask, TaskClassifier, TaskType
from .intent_clarifier import (
    AutoClarifier,
    IntentClarifierInterface,
    InteractiveClarifier,
)
from .json_extractor import JSONExtractor
from .metrics_collector import MetricsCollector, RouterMetrics
from .output_handler import (
    ConsoleOutputHandler,
    NullOutputHandler,
    OutputHandlerInterface,
)
from .provider_resolver import ProviderResolver
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
        validator: Optional[InputValidator] = None
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
            validator: Injectable input validator (default: InputValidator)
        """
        self.orchestrator = orchestrator
        self.project_root = project_root or Path.cwd()
        self.auto_confirm_direct = auto_confirm_direct
        self.verbose = verbose

        # Dependency injection - use provided or create defaults
        self.intent_clarifier = intent_clarifier or InteractiveClarifier()
        self.output_handler = output_handler or (
            ConsoleOutputHandler() if verbose else NullOutputHandler()
        )
        self.validator = validator or InputValidator()

        self.classifier = TaskClassifier()
        self.strategies: Dict[TaskType, ExecutionStrategy] = {}
        self.metrics_collector = MetricsCollector()
        self.provider_resolver = ProviderResolver(orchestrator=orchestrator)

        # Pre/post hooks for extensibility
        self._pre_hooks: List[Callable[[ClassifiedTask], ClassifiedTask]] = []
        self._post_hooks: List[Callable[[ExecutionResult], ExecutionResult]] = []

        # Intent clarification settings
        self.clarify_on_low_confidence = True
        self.confidence_threshold = 0.65
        self.escalate_on_low_confidence = True
        self.use_llm_classification = True  # Use LLM for low-confidence cases

        self._setup_strategies()

    def _setup_strategies(self):
        """Initialize execution strategies."""
        # Direct command executor (no AI needed)
        self.strategies[TaskType.DIRECT_COMMAND] = DirectExecutor(
            working_dir=self.project_root,
            require_confirmation=not self.auto_confirm_direct
        )

        # Conversation handler
        self.strategies[TaskType.CONVERSATION] = ConversationExecutor(
            orchestrator=self.orchestrator
        )

        # AI-powered strategies (require orchestrator)
        if self.orchestrator:
            # Provider will be resolved dynamically per task
            self.strategies[TaskType.RESEARCH] = ResearchExecutor(
                orchestrator=self.orchestrator,
                project_root=self.project_root,
                max_tool_iterations=3
            )

            self.strategies[TaskType.CODE_GENERATION] = AgentExecutor(
                orchestrator=self.orchestrator,
                project_root=self.project_root,
                max_iterations=10,
                require_approval=True
            )

    def _needs_intent_clarification(self, task: ClassifiedTask) -> bool:
        """
        Check if task needs user clarification due to ambiguity.

        Returns True when:
        - Confidence is below threshold
        - Has conflicting signals (action verb + question pattern)
        - Task type is RESEARCH but has strong action indicators
        - Has both explanation words AND action words (ambiguous intent)
        """
        # Low confidence always needs clarification
        if task.confidence < self.confidence_threshold:
            return True

        input_lower = task.original_input.lower()

        # Conflicting signals: action verb but classified as research
        if task.task_type == TaskType.RESEARCH:
            action_verbs = ['create', 'write', 'make', 'add', 'build', 'generate', 'implement', 'fix', 'update']
            has_strong_action = any(f' {verb} ' in f' {input_lower} ' or input_lower.startswith(verb)
                                   for verb in action_verbs)
            if has_strong_action:
                return True

        # Has question mark but also action verb (ambiguous)
        has_question = '?' in task.original_input
        has_action = any(verb in input_lower for verb in ['create', 'write', 'make', 'add', 'generate'])
        if has_question and has_action:
            return True

        # NEW: Conflicting signals - has BOTH explanation AND action keywords
        explanation_words = ['explain', 'describe', 'tell me', 'what is', 'how does', 'how to']
        action_words = ['create', 'write', 'make', 'add', 'build', 'generate', 'implement']

        has_explanation = any(word in input_lower for word in explanation_words)
        has_action_word = any(word in input_lower for word in action_words)

        if has_explanation and has_action_word:
            return True

        return False

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
        """
        if not self.escalate_on_low_confidence:
            return task

        # Only escalate RESEARCH tasks
        if task.task_type != TaskType.RESEARCH:
            return task

        # Check for action indicators that suggest this should be CODE_GENERATION
        input_lower = task.original_input.lower()
        action_indicators = [
            'create', 'write', 'make', 'add', 'build', 'generate',
            'implement', 'fix', 'update', 'modify', 'delete', 'remove'
        ]

        has_action_word = any(word in input_lower for word in action_indicators)

        # Escalate if low confidence and has action indicators
        if task.confidence < 0.7 and has_action_word:
            original_type = task.task_type.value
            task.task_type = TaskType.CODE_GENERATION
            task.reasoning = f"Escalated from {original_type} due to low confidence ({task.confidence:.2f}) with action indicators"
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

            # Parse response
            response_text = response.content.strip()

            # Extract JSON from response using JSONExtractor utility
            extractor = JSONExtractor()
            response_text = extractor.extract(response_text)

            result = json.loads(response_text)

            # Update task based on LLM classification
            llm_type_str = result.get('task_type', '').upper()
            llm_confidence = float(result.get('confidence', 0.5))
            llm_reasoning = result.get('reasoning', 'LLM classification')

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
                    task.task_type = new_type
                    task.confidence = llm_confidence
                    task.reasoning = f"LLM semantic classification: {llm_reasoning} (was {old_type}, confidence {task.confidence:.2f})"

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
            classified.override_provider = provider

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

        # 9. Add classification info to result
        result.metadata["classification"] = {
            "type": classified.task_type.value,
            "confidence": classified.confidence,
            "complexity": classified.complexity_score,
            "reasoning": classified.reasoning,
            "suggested_provider": classified.suggested_provider,
            "override_provider": classified.override_provider,
            "resolved_provider": provider_name,
            "resolved_model": model_name,
            "used_llm_classification": "LLM semantic classification" in classified.reasoning
        }

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

        May prompt for confirmation based on task type and settings.
        """
        # Auto-execute safe tasks
        if task.task_type == TaskType.CONVERSATION:
            return True

        if task.task_type == TaskType.RESEARCH:
            return True

        # Direct commands may need confirmation
        if task.task_type == TaskType.DIRECT_COMMAND:
            if self.auto_confirm_direct:
                return True

            # Check if command is safe
            if task.extracted_command:
                if not self.classifier.is_safe_command(task.extracted_command):
                    if self.verbose:
                        self.output_handler.log_info(f"Command blocked: {task.extracted_command}")
                    return False

            # Confirm with user
            if self.verbose:
                self.output_handler.log_info(f"Command: {task.extracted_command}")
                response = input("  Execute? [y/N]: ").strip().lower()
                return response in ['y', 'yes']

        # Code generation always proceeds (has its own approval loop)
        if task.task_type == TaskType.CODE_GENERATION:
            return True

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
