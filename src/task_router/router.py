"""
Central task router that dispatches to appropriate execution strategies.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .classifier import ClassifiedTask, TaskClassifier, TaskType
from .strategies import (
    AgentExecutor,
    ConversationExecutor,
    DirectExecutor,
    ExecutionResult,
    ExecutionStrategy,
    OrchestratorLike,
    ResearchExecutor,
)


@dataclass
class RouterMetrics:
    """Metrics tracking for task routing."""
    total_tasks: int = 0
    tasks_by_type: Dict[str, int] = field(default_factory=dict)
    avg_execution_time: float = 0.0
    total_tokens_used: int = 0
    success_rate: float = 1.0


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
        verbose: bool = True
    ):
        """
        Initialize TaskRouter with execution strategies.

        Args:
            orchestrator: LLM orchestrator for AI-powered tasks
            project_root: Project directory for file operations
            auto_confirm_direct: Skip confirmation for direct commands
            verbose: Print routing decisions
        """
        self.orchestrator = orchestrator
        self.project_root = project_root or Path.cwd()
        self.auto_confirm_direct = auto_confirm_direct
        self.verbose = verbose

        self.classifier = TaskClassifier()
        self.strategies: Dict[TaskType, ExecutionStrategy] = {}
        self.metrics = RouterMetrics()

        # Pre/post hooks for extensibility
        self._pre_hooks: List[Callable[[ClassifiedTask], ClassifiedTask]] = []
        self._post_hooks: List[Callable[[ExecutionResult], ExecutionResult]] = []

        # Intent clarification settings
        self.clarify_on_low_confidence = True
        self.confidence_threshold = 0.65
        self.escalate_on_low_confidence = True

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

        Modifies task type based on user response.
        """
        print(f"\n🤔 Intent Clarification Needed")
        print(f"   Classified as: {task.task_type.value} (confidence: {task.confidence:.0%})")
        print(f"   Input: \"{task.original_input}\"")
        print(f"\nDid you want me to:")
        print(f"  [1] EXPLAIN how to do this (research/information only)")
        print(f"  [2] Actually DO this for you (execute/create/modify)")
        print(f"  [3] Keep current classification ({task.task_type.value})")

        try:
            choice = input("\nChoice [1/2/3]: ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = "3"

        if choice == "1":
            task.task_type = TaskType.RESEARCH
            task.reasoning = f"User clarified: research/explain only. Original: {task.reasoning}"
            task.confidence = 1.0  # User confirmed
            if self.verbose:
                print(f"  ✓ Switching to RESEARCH mode")
        elif choice == "2":
            task.task_type = TaskType.CODE_GENERATION
            task.reasoning = f"User clarified: execute/create. Original: {task.reasoning}"
            task.confidence = 1.0  # User confirmed
            if self.verbose:
                print(f"  ✓ Switching to CODE_GENERATION mode")
        else:
            if self.verbose:
                print(f"  ✓ Keeping {task.task_type.value} classification")

        return task

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
                print(f"  ⬆️ Escalated: {original_type} → CODE_GENERATION (low confidence + action words)")

        return task

    def _resolve_provider(self, hint: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolve provider hint to actual provider name and model.

        Args:
            hint: Provider hint ("fast", "quality", etc.) or None

        Returns:
            Tuple of (provider_name, model_name) or (None, None) if no resolution needed
        """
        if not hint or not self.orchestrator:
            return (None, None)

        try:
            # Try to use ProviderSelector if available
            if hasattr(self.orchestrator, 'providers'):
                from ..orchestrator.provider_selector import ProviderSelector
                selector = ProviderSelector(self.orchestrator.providers)
                return selector.select_for_task(hint)
        except Exception:
            pass

        # Fallback: simple mapping
        available = []
        try:
            if hasattr(self.orchestrator, 'providers'):
                available = self.orchestrator.providers.list_available()
        except Exception:
            pass

        if hint in ['fast', 'high_volume', 'general']:
            # Prefer Cerebras > Groq > Gemini
            if 'cerebras' in available:
                return ('cerebras', None)
            elif 'groq' in available:
                return ('groq', None)
            elif 'gemini' in available:
                return ('gemini', None)
        elif hint == 'quality':
            # Use 70B models
            if 'cerebras' in available:
                return ('cerebras', 'llama-3.3-70b')
            elif 'groq' in available:
                return ('groq', 'llama-3.3-70b-versatile')
            elif 'gemini' in available:
                return ('gemini', None)

        return (None, None)

    def route(self, user_input: str) -> ExecutionResult:
        """
        Route user input to appropriate execution strategy.

        Returns ExecutionResult with output and metadata.
        """
        start_time = time.time()

        # 1. Classify the task
        classified = self.classifier.classify(user_input)

        if self.verbose:
            self._log_classification(classified)

        # 2. Apply confidence escalation (auto-upgrade low-confidence tasks)
        classified = self._apply_confidence_escalation(classified)

        # 3. Clarify intent if needed (ask user when ambiguous)
        if self.clarify_on_low_confidence and self._needs_intent_clarification(classified):
            classified = self._clarify_intent(classified)

        # 4. Resolve provider (override takes precedence over suggestion)
        provider_hint = classified.override_provider or classified.suggested_provider
        provider_name, model_name = self._resolve_provider(provider_hint)

        if self.verbose and provider_name:
            model_info = f" ({model_name})" if model_name else ""
            source = "override" if classified.override_provider else "hint"
            print(f"  Provider: {provider_name}{model_info} ({source}: {provider_hint})")

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
            print(f"  Executing with: {strategy.name}")

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
            "resolved_model": model_name
        }

        return result

    def route_with_provider(
        self,
        user_input: str,
        provider_override: Optional[str] = None
    ) -> ExecutionResult:
        """
        Route user input with optional provider override.

        Args:
            user_input: User's task/query
            provider_override: Force specific provider type ("fast", "quality", or provider name)

        Returns:
            ExecutionResult with output and metadata
        """
        # Classify first
        classified = self.classifier.classify(user_input)

        # Apply override if provided
        if provider_override:
            classified.override_provider = provider_override

        # Now route with the modified classification
        start_time = time.time()

        if self.verbose:
            self._log_classification(classified)

        # Resolve provider (override takes precedence)
        provider_hint = classified.override_provider or classified.suggested_provider
        provider_name, model_name = self._resolve_provider(provider_hint)

        if self.verbose and provider_name:
            model_info = f" ({model_name})" if model_name else ""
            source = "override" if classified.override_provider else "hint"
            print(f"  Provider: {provider_name}{model_info} ({source}: {provider_hint})")

        # Apply pre-execution hooks
        for hook in self._pre_hooks:
            classified = hook(classified)

        # Get appropriate strategy
        strategy = self._get_strategy(classified)

        if not strategy:
            return ExecutionResult(
                success=False,
                output="",
                error=f"No strategy available for task type: {classified.task_type}",
                execution_time=time.time() - start_time
            )

        # Confirm execution if needed
        if not self._should_execute(classified, strategy):
            return ExecutionResult(
                success=False,
                output="",
                error="Execution cancelled by user",
                execution_time=time.time() - start_time
            )

        # Execute with resolved provider
        if self.verbose:
            print(f"  Executing with: {strategy.name}")

        if hasattr(strategy, 'set_provider'):
            strategy.set_provider(provider_name, model_name)

        result = strategy.execute(classified)

        # Apply post-execution hooks
        for hook in self._post_hooks:
            result = hook(result)

        # Update metrics
        self._update_metrics(classified, result)

        # Add classification info to result
        result.metadata["classification"] = {
            "type": classified.task_type.value,
            "confidence": classified.confidence,
            "complexity": classified.complexity_score,
            "reasoning": classified.reasoning,
            "suggested_provider": classified.suggested_provider,
            "override_provider": classified.override_provider,
            "resolved_provider": provider_name,
            "resolved_model": model_name
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
                    print(f"  ⚠️ No orchestrator available for {task.task_type}")
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
                        print(f"  ⚠️ Command blocked: {task.extracted_command}")
                    return False

            # Confirm with user
            if self.verbose:
                print(f"  Command: {task.extracted_command}")
                response = input("  Execute? [y/N]: ").strip().lower()
                return response in ['y', 'yes']

        # Code generation always proceeds (has its own approval loop)
        if task.task_type == TaskType.CODE_GENERATION:
            return True

        return True

    def _log_classification(self, task: ClassifiedTask):
        """Log classification decision."""
        print(f"\n📋 Task Classification:")
        print(f"  Type: {task.task_type.value}")
        print(f"  Confidence: {task.confidence:.2f}")
        print(f"  Complexity: {task.complexity_score}/10")
        print(f"  Reasoning: {task.reasoning}")

        if task.extracted_command:
            print(f"  Command: {task.extracted_command}")

        if task.requires_planning:
            print(f"  Requires planning: Yes")

    def _update_metrics(self, task: ClassifiedTask, result: ExecutionResult):
        """Update routing metrics."""
        self.metrics.total_tasks += 1

        # Track by type
        type_key = task.task_type.value
        if type_key not in self.metrics.tasks_by_type:
            self.metrics.tasks_by_type[type_key] = 0
        self.metrics.tasks_by_type[type_key] += 1

        # Update average execution time
        n = self.metrics.total_tasks
        old_avg = self.metrics.avg_execution_time
        self.metrics.avg_execution_time = old_avg + (result.execution_time - old_avg) / n

        # Track tokens
        self.metrics.total_tokens_used += result.tokens_used

        # Update success rate
        if not result.success:
            success_count = self.metrics.success_rate * (n - 1)
            self.metrics.success_rate = success_count / n

    def add_pre_hook(self, hook: Callable[[ClassifiedTask], ClassifiedTask]):
        """Add pre-execution hook for task modification."""
        self._pre_hooks.append(hook)

    def add_post_hook(self, hook: Callable[[ExecutionResult], ExecutionResult]):
        """Add post-execution hook for result processing."""
        self._post_hooks.append(hook)

    def get_metrics(self) -> RouterMetrics:
        """Get current routing metrics."""
        return self.metrics

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
