"""
Intent clarification interfaces and implementations.

This module provides injectable intent clarification to make the code testable.
Following the dependency inversion principle, we define an interface (Protocol)
that can be swapped with different implementations.
"""
from abc import ABC, abstractmethod
from typing import Callable, Optional

from .classifier import ClassifiedTask, TaskType


class IntentClarifierInterface(ABC):
    """
    Interface for intent clarification.

    Implementations can provide interactive, automatic, or null clarification.
    This makes the code testable and flexible.
    """

    @abstractmethod
    def clarify(self, task: ClassifiedTask) -> ClassifiedTask:
        """
        Clarify user intent for an ambiguous task.

        Args:
            task: The classified task that may need clarification

        Returns:
            ClassifiedTask with potentially updated task_type and confidence
        """
        pass


class InteractiveClarifier(IntentClarifierInterface):
    """
    Interactive clarifier that prompts the user for input.

    This is the default clarifier for CLI usage. It asks the user
    to choose between different interpretations of their request.

    The input source is injectable to enable testing.
    """

    def __init__(
        self,
        input_fn: Optional[Callable[[str], str]] = None,
        output_fn: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize interactive clarifier.

        Args:
            input_fn: Function to get user input (default: builtins.input)
            output_fn: Function to display prompts (default: print)
        """
        self.input_fn = input_fn or input
        self.output_fn = output_fn or print

    def clarify(self, task: ClassifiedTask) -> ClassifiedTask:
        """
        Ask user to clarify their intent when classification is ambiguous.

        Presents the user with 3 choices:
        1. EXPLAIN how to do this (research/information only)
        2. Actually DO this for you (execute/create/modify)
        3. Keep current classification
        """
        self.output_fn(f"\nIntent Clarification Needed")
        self.output_fn(f"   Classified as: {task.task_type.value} (confidence: {task.confidence:.0%})")
        self.output_fn(f"   Input: \"{task.original_input}\"")
        self.output_fn(f"\nDid you want me to:")
        self.output_fn(f"  [1] EXPLAIN how to do this (research/information only)")
        self.output_fn(f"  [2] Actually DO this for you (execute/create/modify)")
        self.output_fn(f"  [3] Keep current classification ({task.task_type.value})")

        try:
            choice = self.input_fn("\nChoice [1/2/3]: ").strip()
        except (EOFError, KeyboardInterrupt):
            # User cancelled, keep original
            return task

        if choice == "1":
            # User wants explanation (research mode)
            task.task_type = TaskType.RESEARCH
            task.reasoning = f"User clarified: research/explain only. Original: {task.reasoning}"
            task.confidence = 1.0  # User confirmed
        elif choice == "2":
            # User wants action (code generation mode)
            task.task_type = TaskType.CODE_GENERATION
            task.reasoning = f"User clarified: execute/create. Original: {task.reasoning}"
            task.confidence = 1.0  # User confirmed
        # else: choice == "3" or invalid input, keep original (do nothing)

        return task


class AutoClarifier(IntentClarifierInterface):
    """
    Automatic clarifier that applies a default action without prompting.

    Useful for:
    - CI/CD environments where interactive prompts are not possible
    - Batch processing
    - Automated testing
    - Silent mode operation

    Can be configured to either:
    - "escalate": Upgrade to CODE_GENERATION (safer, more capable)
    - "keep": Keep the original classification
    """

    def __init__(self, default_action: str = "escalate"):
        """
        Initialize auto clarifier.

        Args:
            default_action: Either "escalate" or "keep"
        """
        if default_action not in ["escalate", "keep"]:
            raise ValueError("default_action must be 'escalate' or 'keep'")

        self.default_action = default_action

    def clarify(self, task: ClassifiedTask) -> ClassifiedTask:
        """Apply automatic clarification based on configured default action."""
        if self.default_action == "escalate":
            # Auto-escalate to CODE_GENERATION if not already
            if task.task_type != TaskType.CODE_GENERATION:
                task.task_type = TaskType.CODE_GENERATION
                task.reasoning = f"Auto-escalated from {task.task_type.value} due to ambiguity. Original: {task.reasoning}"
        # else: keep original (do nothing)

        return task


class NullClarifier(IntentClarifierInterface):
    """
    Null clarifier that never modifies tasks.

    Useful when:
    - Clarification is disabled entirely
    - You want to trust the classifier completely
    - Testing specific paths without clarification
    """

    def clarify(self, task: ClassifiedTask) -> ClassifiedTask:
        """Return task unchanged - no clarification."""
        return task
