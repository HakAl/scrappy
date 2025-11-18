"""
Classification strategy interface and base classes.

Defines the strategy pattern for task classification, allowing different
classification approaches to be encapsulated and easily extended.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple, Optional


class TaskType(Enum):
    """High-level task categories for execution routing."""
    DIRECT_COMMAND = "direct_command"      # Simple shell commands, no agent loop
    CODE_GENERATION = "code_generation"    # Full agent with planning and tools
    RESEARCH = "research"                  # Fast provider, lightweight research
    CONVERSATION = "conversation"          # Simple Q&A, no execution needed


@dataclass
class StrategyResult:
    """Result from a classification strategy evaluation."""
    score: float  # 0.0 to unlimited (will be normalized)
    confidence: float  # 0.0 to 1.0
    matched_patterns: List[str]
    reasoning: str
    extracted_command: Optional[str] = None


class ClassificationStrategy(ABC):
    """
    Base class for classification strategies.

    Each strategy encapsulates the logic for identifying one task type.
    Strategies evaluate input and return a score indicating how well
    the input matches their task type.
    """

    def __init__(self):
        """Initialize strategy with its patterns."""
        self.patterns: List[Tuple[str, float, str]] = []
        self._init_patterns()

    @abstractmethod
    def _init_patterns(self) -> None:
        """Initialize pattern matchers for this strategy."""
        pass

    @abstractmethod
    def task_type(self) -> TaskType:
        """Return the task type this strategy identifies."""
        pass

    def evaluate(self, user_input: str) -> StrategyResult:
        """
        Evaluate input against this strategy's patterns.

        Args:
            user_input: User input to classify

        Returns:
            StrategyResult with score and metadata
        """
        input_stripped = user_input.strip()
        input_lower = input_stripped.lower()

        score = 0.0
        matched = []
        extracted_cmd = None

        # Check all patterns for this strategy
        for pattern, weight, name in self.patterns:
            match = re.search(pattern, input_lower, re.IGNORECASE)
            if match:
                score += weight
                matched.append(name)
                # For direct commands, extract the command
                if not extracted_cmd and self.task_type() == TaskType.DIRECT_COMMAND:
                    extracted_cmd = input_stripped

        # Normalize score (cap at 1.0)
        confidence = min(score, 1.0)

        # Generate reasoning
        reasoning = self._generate_reasoning(matched)

        return StrategyResult(
            score=score,
            confidence=confidence,
            matched_patterns=matched,
            reasoning=reasoning,
            extracted_command=extracted_cmd
        )

    def _generate_reasoning(self, patterns: List[str]) -> str:
        """Generate human-readable reasoning for this strategy."""
        if not patterns:
            return ""

        pattern_str = ", ".join(patterns[:3])
        return f"{self.task_type().value}: {pattern_str}"


class PatternBasedStrategy(ClassificationStrategy):
    """
    Base class for pattern-based strategies.

    Provides common functionality for strategies that use regex patterns.
    Subclasses only need to define their patterns.
    """

    def add_pattern(self, pattern: str, weight: float, name: str) -> None:
        """Add a pattern to this strategy."""
        self.patterns.append((pattern, weight, name))

    def add_patterns(self, patterns: List[Tuple[str, float, str]]) -> None:
        """Add multiple patterns to this strategy."""
        self.patterns.extend(patterns)
