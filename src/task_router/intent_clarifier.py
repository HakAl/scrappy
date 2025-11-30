"""
Intent clarification implementations.

This module provides injectable intent clarification to make the code testable.
Following the dependency inversion principle, implementations conform to the
IntentClarifierProtocol defined in protocols.py.
"""
from dataclasses import replace
from typing import Callable, Optional

from .classifier import ClassifiedTask, TaskType
from .protocols import DefaultConsoleInput, IntentClarifierProtocol, TaskRouterInputProtocol


class InteractiveClarifier:
    """
    Interactive clarifier that prompts the user for input.

    This is the default clarifier for CLI usage. It asks the user
    to choose between different interpretations of their request.

    The input source is injectable via TaskRouterInputProtocol to enable:
    - Non-blocking input in Textual UI
    - Testable code with mock input
    - CLI fallback via DefaultConsoleInput
    """

    def __init__(
        self,
        io: Optional[TaskRouterInputProtocol] = None
    ):
        """
        Initialize interactive clarifier.

        Args:
            io: Input protocol for user interaction. If None, uses
                DefaultConsoleInput for CLI usage.
        """
        self._io = io or DefaultConsoleInput()

    def clarify(self, task: ClassifiedTask) -> ClassifiedTask:
        """
        Ask user to clarify their intent when classification is ambiguous.

        Presents the user with 3 choices:
        1. EXPLAIN how to do this (research/information only)
        2. Actually DO this for you (execute/create/modify)
        3. Keep current classification
        """
        self._io.output(f"\nIntent Clarification Needed")
        self._io.output(f"   Classified as: {task.task_type.value} (confidence: {task.confidence:.0%})")
        self._io.output(f"   Input: \"{task.original_input}\"")
        self._io.output(f"\nDid you want me to:")
        self._io.output(f"  [1] EXPLAIN how to do this (research/information only)")
        self._io.output(f"  [2] Actually DO this for you (execute/create/modify)")
        self._io.output(f"  [3] Keep current classification ({task.task_type.value})")

        try:
            choice = self._io.prompt("\nChoice [1/2/3]: ", default="3").strip()
        except (EOFError, KeyboardInterrupt):
            # User cancelled, keep original
            return task

        if choice == "1":
            # User wants explanation (research mode)
            return replace(
                task,
                task_type=TaskType.RESEARCH,
                reasoning=f"User clarified: research/explain only. Original: {task.reasoning}",
                confidence=1.0  # User confirmed
            )
        elif choice == "2":
            # User wants action (code generation mode)
            return replace(
                task,
                task_type=TaskType.CODE_GENERATION,
                reasoning=f"User clarified: execute/create. Original: {task.reasoning}",
                confidence=1.0  # User confirmed
            )
        # else: choice == "3" or invalid input, keep original

        return task


class AutoClarifier:
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
                return replace(
                    task,
                    task_type=TaskType.CODE_GENERATION,
                    reasoning=f"Auto-escalated from {task.task_type.value} due to ambiguity. Original: {task.reasoning}"
                )
        # else: keep original

        return task


class NullClarifier:
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
