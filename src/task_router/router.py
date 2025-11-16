"""
Central task router that dispatches to appropriate execution strategies.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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
            self.strategies[TaskType.RESEARCH] = ResearchExecutor(
                orchestrator=self.orchestrator,
                preferred_provider="cerebras"  # Fast provider for research
            )

            self.strategies[TaskType.CODE_GENERATION] = AgentExecutor(
                orchestrator=self.orchestrator,
                project_root=self.project_root,
                max_iterations=10,
                require_approval=True
            )

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

        # 2. Apply pre-execution hooks
        for hook in self._pre_hooks:
            classified = hook(classified)

        # 3. Get appropriate strategy
        strategy = self._get_strategy(classified)

        if not strategy:
            return ExecutionResult(
                success=False,
                output="",
                error=f"No strategy available for task type: {classified.task_type}",
                execution_time=time.time() - start_time
            )

        # 4. Confirm execution if needed
        if not self._should_execute(classified, strategy):
            return ExecutionResult(
                success=False,
                output="",
                error="Execution cancelled by user",
                execution_time=time.time() - start_time
            )

        # 5. Execute
        if self.verbose:
            print(f"  Executing with: {strategy.name}")

        result = strategy.execute(classified)

        # 6. Apply post-execution hooks
        for hook in self._post_hooks:
            result = hook(result)

        # 7. Update metrics
        self._update_metrics(classified, result)

        # 8. Add classification info to result
        result.metadata["classification"] = {
            "type": classified.task_type.value,
            "confidence": classified.confidence,
            "complexity": classified.complexity_score,
            "reasoning": classified.reasoning
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
