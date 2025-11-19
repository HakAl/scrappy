"""
Base protocol and utilities for research handlers.
"""

from typing import Protocol, List, Tuple, Any
from abc import abstractmethod

from ...intent_classifier import QueryIntent, ClassificationResult
from ..io_interface import CLIIOProtocol


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
