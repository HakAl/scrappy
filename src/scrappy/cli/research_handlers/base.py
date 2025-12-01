"""
Base protocol and utilities for research handlers.
"""

from typing import Protocol, List, Tuple, Any, Dict
from abc import abstractmethod
from dataclasses import dataclass, field

from scrappy.task_router.protocols import QueryIntent, IntentResult
from ..io_interface import CLIIOProtocol

# Re-export for backward compatibility
__all__ = ['QueryIntent', 'ClassificationResult', 'ResearchHandler', 'BaseResearchHandler']


@dataclass
class ClassificationResult:
    """
    Compatibility wrapper for handler interface.

    Wraps IntentResult and entities into the format expected by handlers.
    This allows handlers to access classification.entities and classification.keywords
    without needing to change their implementation.
    """
    query: str
    intent_result: IntentResult
    entities: Dict[str, List[str]] = field(default_factory=dict)
    keywords: List[str] = field(default_factory=list)

    @property
    def primary_intent(self):
        """Compatibility property to access intent from IntentResult."""
        return self.intent_result


class ResearchHandler(Protocol):
    """Protocol that all research handlers must implement."""

    @property
    def intent(self) -> QueryIntent:
        """The intent this handler processes."""
        ...

    def execute(
        self,
        agent: Any,
        classification: ClassificationResult,
        io: CLIIOProtocol
    ) -> List[str]:
        """
        Execute research for this intent.

        Args:
            agent: CodeAgent with tool methods for research
            classification: The query classification result
            io: IO interface for progress output

        Returns:
            List of research result strings
        """
        ...


class BaseResearchHandler:
    """Base class providing common utilities for research handlers."""

    def _safe_tool_call(
        self,
        tool_func,
        *args,
        **kwargs
    ) -> Tuple[bool, str]:
        """
        Safely call a tool function and handle errors.

        Args:
            tool_func: The tool function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Tuple of (success: bool, result: str)
        """
        try:
            result = tool_func(*args, **kwargs)
            if result and "Error" not in str(result):
                return True, result
            return False, result or ""
        except Exception as e:
            return False, f"Error: {str(e)}"
