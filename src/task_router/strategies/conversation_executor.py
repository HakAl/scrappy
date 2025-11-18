"""
Simple conversation handling without task execution.
"""

import time
from typing import Optional

from ..classifier import ClassifiedTask, TaskType
from .base import ExecutionResult, ExecutionStrategy, OrchestratorLike


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
