"""
Validation for agent task completion.

Ensures completion is legitimate by checking for meaningful work performed
and detecting indicators of incomplete tasks.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Set, runtime_checkable


@dataclass
class CompletionValidation:
    """Result of completion validation."""

    allow_completion: bool
    reason: str
    suggestions: List[str] = field(default_factory=list)


@runtime_checkable
class CompletionValidatorProtocol(Protocol):
    """Protocol for validating task completion."""

    def validate(
        self,
        tools_executed: List[str],
        task_description: str,
        result_text: Optional[str] = None,
        complete_attempts: int = 0,
    ) -> CompletionValidation:
        """
        Validate if completion should be allowed.

        Args:
            tools_executed: List of tools that have been executed
            task_description: Original task description
            result_text: Agent's completion message
            complete_attempts: Number of times completion has been attempted

        Returns:
            CompletionValidation with allow flag and reason
        """
        ...


class CompletionValidator:
    """
    Validates that task completion is legitimate.

    Checks:
    1. Meaningful actions performed (file writes, commands)
    2. No obvious incomplete state indicators
    3. Allows override on second attempt (trust agent judgment)
    """

    # Patterns indicating incomplete work
    # These are specific to avoid false positives like "I fixed the TODO items"
    INCOMPLETE_PATTERNS = [
        # Code comment markers (Python/Shell, C-style, block comments)
        r"#\s*(?:TODO|FIXME|HACK|XXX)\b",
        r"//\s*(?:TODO|FIXME|HACK|XXX)\b",
        r"/\*\s*(?:TODO|FIXME|HACK|XXX)\b",
        # Standalone markers with colon (common in prose and code)
        r"\b(?:TODO|FIXME|HACK|XXX)\s*:",
        # Phrases indicating remaining work
        r"not yet implemented",
        r"will implement later",
        r"need to add more",
        r"remaining work",
        r"still need to",
    ]

    def __init__(self, meaningful_actions: Set[str]):
        """
        Initialize validator.

        Args:
            meaningful_actions: Set of action names considered meaningful
        """
        self._meaningful_actions = meaningful_actions
        self._incomplete_regex = re.compile(
            "|".join(self.INCOMPLETE_PATTERNS),
            re.IGNORECASE
        )

    def validate(
        self,
        tools_executed: List[str],
        task_description: str,
        result_text: Optional[str] = None,
        complete_attempts: int = 0,
    ) -> CompletionValidation:
        """
        Validate completion request.

        Args:
            tools_executed: List of executed tool names
            task_description: Original task description
            result_text: Agent's completion message
            complete_attempts: Number of prior completion attempts

        Returns:
            CompletionValidation with result
        """
        # Allow on second attempt - trust agent judgment after pushback
        if complete_attempts >= 1:
            return CompletionValidation(
                allow_completion=True,
                reason="Completion allowed after prior attempt"
            )

        # Check for meaningful work
        meaningful_work = [
            t for t in tools_executed
            if t in self._meaningful_actions
        ]

        if not meaningful_work:
            return CompletionValidation(
                allow_completion=False,
                reason="No meaningful actions performed",
                suggestions=[
                    "Use write_file to create or modify files",
                    "Use run_command to execute necessary commands",
                    "Explain why no file changes are needed",
                ]
            )

        # Check for incomplete indicators in result text
        if result_text:
            incomplete_match = self._check_incomplete_indicators(result_text)
            if incomplete_match:
                return CompletionValidation(
                    allow_completion=False,
                    reason=f"Task appears incomplete: found '{incomplete_match}'",
                    suggestions=["Address the incomplete items before completing"]
                )

        return CompletionValidation(
            allow_completion=True,
            reason="Completion validated"
        )

    def _check_incomplete_indicators(self, text: str) -> Optional[str]:
        """
        Check for indicators that task is incomplete.

        Args:
            text: Text to check (typically the completion message)

        Returns:
            Matched indicator text if found, None otherwise
        """
        match = self._incomplete_regex.search(text)
        if match:
            return match.group()
        return None
