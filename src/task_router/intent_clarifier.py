"""
Intent clarification interfaces and implementations.

This module provides injectable intent clarification to make the code testable.
Following the dependency inversion principle, we define an interface (Protocol)
that can be swapped with different implementations.

DEPRECATION NOTICE:
IntentClarifierInterface (ABC) is deprecated. Use IntentClarifierProtocol from
protocols.py instead. The ABC will be removed in a future version.
"""
import warnings
from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Callable, Optional, Union

from .classifier import ClassifiedTask, TaskType
from .protocols import DefaultConsoleInput, TaskRouterInputProtocol


class IntentClarifierInterface(ABC):
    """
    Interface for intent clarification.

    DEPRECATED: Use IntentClarifierProtocol instead.

    This ABC is maintained for backwards compatibility. New code should
    implement the IntentClarifierProtocol from protocols.py instead of
    inheriting from this class.

    Implementations can provide interactive, automatic, or null clarification.
    This makes the code testable and flexible.
    """

    def __init_subclass__(cls, **kwargs):
        """Emit deprecation warning when subclassing."""
        super().__init_subclass__(**kwargs)
        # Only warn for external subclasses, not the ones in this module
        if cls.__module__ != __name__:
            warnings.warn(
                f"{cls.__name__} inherits from IntentClarifierInterface which is "
                "deprecated. Implement IntentClarifierProtocol instead.",
                DeprecationWarning,
                stacklevel=2,
            )

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

    The input source is injectable via TaskRouterInputProtocol to enable:
    - Non-blocking input in Textual UI
    - Testable code with mock input
    - CLI fallback via DefaultConsoleInput
    """

    def __init__(
        self,
        io: Optional[TaskRouterInputProtocol] = None,
        # Legacy parameters for backwards compatibility
        input_fn: Optional[Callable[[str], str]] = None,
        output_fn: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize interactive clarifier.

        Args:
            io: Input protocol for user interaction. If None, uses
                DefaultConsoleInput for backwards compatibility with
                non-Textual usage.
            input_fn: DEPRECATED - Legacy function to get user input.
                      Use io parameter instead.
            output_fn: DEPRECATED - Legacy function to display prompts.
                       Use io parameter instead.

        Note:
            If both io and legacy parameters are provided, io takes precedence.
            Legacy parameters are maintained for backwards compatibility but
            will be removed in a future version.
        """
        if io is not None:
            self._io = io
        elif input_fn is not None or output_fn is not None:
            # Legacy mode: wrap functions in adapter
            self._io = _LegacyInputAdapter(
                input_fn=input_fn or input,
                output_fn=output_fn or print
            )
        else:
            # Default: use shared console input
            self._io = DefaultConsoleInput()

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


class _LegacyInputAdapter:
    """
    Adapter to wrap legacy input_fn/output_fn in TaskRouterInputProtocol.

    This maintains backwards compatibility with code that passed
    input_fn and output_fn to InteractiveClarifier.
    """

    def __init__(
        self,
        input_fn: Callable[[str], str],
        output_fn: Callable[[str], None]
    ):
        self._input_fn = input_fn
        self._output_fn = output_fn

    def prompt(self, text: str, default: str = "") -> str:
        """Get text input using legacy function."""
        try:
            result = self._input_fn(text)
            return result if result else default
        except (EOFError, KeyboardInterrupt):
            return default

    def confirm(self, text: str, default: bool = False) -> bool:
        """Get yes/no confirmation using legacy function."""
        try:
            result = self._input_fn(text).strip().lower()
            return result in ('y', 'yes')
        except (EOFError, KeyboardInterrupt):
            return default

    def output(self, message: str) -> None:
        """Output message using legacy function."""
        self._output_fn(message)


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
                return replace(
                    task,
                    task_type=TaskType.CODE_GENERATION,
                    reasoning=f"Auto-escalated from {task.task_type.value} due to ambiguity. Original: {task.reasoning}"
                )
        # else: keep original

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
