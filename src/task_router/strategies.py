"""
Execution strategies for different task types.
Each strategy optimizes for its specific use case.
"""

import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol
from pathlib import Path

from .classifier import ClassifiedTask, TaskType


@dataclass
class ExecutionResult:
    """Result from task execution."""
    success: bool
    output: str
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    provider_used: Optional[str] = None


class OrchestratorLike(Protocol):
    """Protocol for orchestrator dependency."""

    def delegate(self, prompt: str, provider_name: Optional[str] = None) -> Any:
        """Delegate prompt to a provider."""
        ...

    def get_context(self) -> Optional[Any]:
        """Get codebase context."""
        ...


class ExecutionStrategy(ABC):
    """Abstract base for execution strategies."""

    @abstractmethod
    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        """Execute the classified task."""
        pass

    @abstractmethod
    def can_handle(self, task: ClassifiedTask) -> bool:
        """Check if this strategy can handle the task."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name for logging."""
        pass


class DirectExecutor(ExecutionStrategy):
    """
    Direct command execution without agent loop.

    Best for:
    - pip install, npm install
    - git status, git log
    - Simple filesystem operations
    - Build commands (make, pytest)

    Features:
    - No LLM involvement
    - Immediate execution
    - Timeout protection
    - Safety checks
    """

    def __init__(
        self,
        working_dir: Optional[Path] = None,
        timeout: int = 60,
        require_confirmation: bool = True
    ):
        self.working_dir = working_dir or Path.cwd()
        self.timeout = timeout
        self.require_confirmation = require_confirmation

    @property
    def name(self) -> str:
        return "DirectExecutor"

    def can_handle(self, task: ClassifiedTask) -> bool:
        return (
            task.task_type == TaskType.DIRECT_COMMAND
            and task.extracted_command is not None
        )

    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        """Execute direct command in shell."""
        if not task.extracted_command:
            return ExecutionResult(
                success=False,
                output="",
                error="No command extracted from task"
            )

        command = task.extracted_command

        # Safety check
        from .classifier import TaskClassifier
        classifier = TaskClassifier()
        if not classifier.is_safe_command(command):
            return ExecutionResult(
                success=False,
                output="",
                error=f"Command blocked for safety: {command}"
            )

        start_time = time.time()

        try:
            # Execute command
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self.working_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout
            )

            execution_time = time.time() - start_time

            if result.returncode == 0:
                return ExecutionResult(
                    success=True,
                    output=result.stdout,
                    error=result.stderr if result.stderr else None,
                    execution_time=execution_time,
                    metadata={
                        "command": command,
                        "return_code": result.returncode,
                        "working_dir": str(self.working_dir)
                    }
                )
            else:
                return ExecutionResult(
                    success=False,
                    output=result.stdout,
                    error=result.stderr or f"Command failed with code {result.returncode}",
                    execution_time=execution_time,
                    metadata={
                        "command": command,
                        "return_code": result.returncode
                    }
                )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Command timed out after {self.timeout}s",
                execution_time=self.timeout,
                metadata={"command": command}
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Execution error: {str(e)}",
                metadata={"command": command}
            )


class ResearchExecutor(ExecutionStrategy):
    """
    Fast research and information gathering.

    Best for:
    - Explaining code
    - Answering questions
    - Code analysis
    - Architecture overview

    Features:
    - Uses fastest available provider (Cerebras)
    - No file modifications
    - Context-aware responses
    - Lightweight tool access (read-only)
    """

    def __init__(
        self,
        orchestrator: OrchestratorLike,
        preferred_provider: str = "cerebras"
    ):
        self.orchestrator = orchestrator
        self.preferred_provider = preferred_provider

    @property
    def name(self) -> str:
        return "ResearchExecutor"

    def can_handle(self, task: ClassifiedTask) -> bool:
        return task.task_type == TaskType.RESEARCH

    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        """Execute research task with fast provider."""
        start_time = time.time()

        try:
            # Build research prompt with context
            prompt = self._build_research_prompt(task)

            # Delegate to fast provider
            response = self.orchestrator.delegate(
                prompt=prompt,
                provider_name=self.preferred_provider
            )

            execution_time = time.time() - start_time

            # Extract response details
            if hasattr(response, 'text'):
                output = response.text
                tokens = getattr(response, 'tokens_used', 0)
                provider = getattr(response, 'provider', self.preferred_provider)
            else:
                output = str(response)
                tokens = 0
                provider = self.preferred_provider

            return ExecutionResult(
                success=True,
                output=output,
                execution_time=execution_time,
                tokens_used=tokens,
                provider_used=provider,
                metadata={
                    "task_type": "research",
                    "complexity": task.complexity_score
                }
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Research execution failed: {str(e)}",
                execution_time=time.time() - start_time
            )

    def _build_research_prompt(self, task: ClassifiedTask) -> str:
        """Build optimized prompt for research tasks."""
        # Get context if available
        context_info = ""
        try:
            context = self.orchestrator.get_context()
            if context and hasattr(context, 'get_summary'):
                context_info = f"\n\nProject Context:\n{context.get_summary()}\n"
        except Exception:
            pass

        return f"""Research Task:
{task.original_input}
{context_info}
Please provide a concise, informative response. Focus on accuracy and clarity.
If this involves code analysis, explain the key concepts clearly.
"""


class AgentExecutor(ExecutionStrategy):
    """
    Full agent loop with planning and tool use.

    Best for:
    - Writing new code
    - Refactoring existing code
    - Multi-step implementations
    - Bug fixes

    Features:
    - Full planning phase
    - Human-in-the-loop approval
    - Tool access (file, git, search)
    - Iterative execution
    """

    def __init__(
        self,
        orchestrator: OrchestratorLike,
        project_root: Optional[Path] = None,
        max_iterations: int = 10,
        require_approval: bool = True
    ):
        self.orchestrator = orchestrator
        self.project_root = project_root or Path.cwd()
        self.max_iterations = max_iterations
        self.require_approval = require_approval

    @property
    def name(self) -> str:
        return "AgentExecutor"

    def can_handle(self, task: ClassifiedTask) -> bool:
        return task.task_type == TaskType.CODE_GENERATION

    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        """Execute code generation task with full agent loop."""
        start_time = time.time()

        try:
            # Import CodeAgent here to avoid circular imports
            from ..agent import CodeAgent, ConversationState
            from ..orchestrator_adapter import AgentOrchestratorAdapter

            # Create adapter for CodeAgent
            adapter = AgentOrchestratorAdapter(self.orchestrator)

            # Initialize CodeAgent
            agent = CodeAgent(
                orchestrator=adapter,
                project_root=self.project_root,
                max_iterations=self.max_iterations,
                require_approval=self.require_approval
            )

            # Run planning phase if needed
            if task.requires_planning:
                plan_result = self._run_planning(task)
                if plan_result:
                    task_with_plan = f"{task.original_input}\n\nPlan:\n{plan_result}"
                else:
                    task_with_plan = task.original_input
            else:
                task_with_plan = task.original_input

            # Execute with agent loop
            results = agent.run(task_with_plan)

            execution_time = time.time() - start_time

            # Format results
            output_parts = []
            total_tokens = 0

            for i, result in enumerate(results, 1):
                output_parts.append(f"Step {i}: {result.action.action}")
                if result.output:
                    output_parts.append(f"  Output: {result.output[:500]}")
                if not result.approved:
                    output_parts.append("  [User declined]")

            return ExecutionResult(
                success=all(r.approved for r in results),
                output="\n".join(output_parts),
                execution_time=execution_time,
                tokens_used=total_tokens,
                provider_used="agent_loop",
                metadata={
                    "iterations": len(results),
                    "actions": [r.action.action for r in results],
                    "all_approved": all(r.approved for r in results)
                }
            )

        except ImportError as e:
            # Fallback if CodeAgent not available
            return self._fallback_execution(task, start_time, str(e))
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Agent execution failed: {str(e)}",
                execution_time=time.time() - start_time
            )

    def _run_planning(self, task: ClassifiedTask) -> Optional[str]:
        """Run planning phase for complex tasks."""
        try:
            if hasattr(self.orchestrator, 'plan'):
                plan = self.orchestrator.plan(task.original_input)
                if isinstance(plan, list):
                    return "\n".join([f"- {step}" for step in plan])
                return str(plan)
        except Exception:
            pass
        return None

    def _fallback_execution(
        self,
        task: ClassifiedTask,
        start_time: float,
        import_error: str
    ) -> ExecutionResult:
        """
        Fallback to simple LLM generation if CodeAgent unavailable.
        """
        try:
            prompt = f"""Code Generation Task:
{task.original_input}

Please provide the code implementation. Include:
1. Clear code with comments
2. Any necessary imports
3. Brief explanation of the approach
"""
            response = self.orchestrator.delegate(prompt)

            if hasattr(response, 'text'):
                output = response.text
                tokens = getattr(response, 'tokens_used', 0)
            else:
                output = str(response)
                tokens = 0

            return ExecutionResult(
                success=True,
                output=output,
                execution_time=time.time() - start_time,
                tokens_used=tokens,
                provider_used="fallback_llm",
                metadata={
                    "fallback_reason": import_error,
                    "mode": "simple_generation"
                }
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Fallback execution failed: {str(e)}",
                execution_time=time.time() - start_time
            )


class ConversationExecutor(ExecutionStrategy):
    """
    Simple conversation handling without task execution.

    Best for:
    - Greetings
    - Acknowledgments
    - Help requests
    - Simple Q&A
    """

    def __init__(self, orchestrator: Optional[OrchestratorLike] = None):
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "ConversationExecutor"

    def can_handle(self, task: ClassifiedTask) -> bool:
        return task.task_type == TaskType.CONVERSATION

    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        """Handle simple conversation."""
        start_time = time.time()

        # Pre-defined responses for common patterns
        responses = {
            "greeting": "Hello! I'm ready to help with your tasks. What would you like to do?",
            "thanks": "You're welcome! Let me know if you need anything else.",
            "acknowledgment": "Understood. What's next?",
            "help_request": "I can help with:\n- Direct commands (pip install, git status)\n- Code generation (write, refactor, fix)\n- Research (explain code, analyze architecture)\n\nWhat would you like to do?",
            "farewell": "Goodbye! Feel free to return anytime."
        }

        # Find matching pattern
        for pattern in task.matched_patterns:
            if pattern in responses:
                return ExecutionResult(
                    success=True,
                    output=responses[pattern],
                    execution_time=time.time() - start_time,
                    metadata={"pattern": pattern}
                )

        # Default response
        return ExecutionResult(
            success=True,
            output="I understand. How can I assist you?",
            execution_time=time.time() - start_time
        )
