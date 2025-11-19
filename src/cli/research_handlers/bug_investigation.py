"""
Handler for BUG_INVESTIGATION intent research.
"""

from typing import List, Any

from ...intent_classifier import QueryIntent, ClassificationResult
from ..io_interface import CLIIOProtocol
from ..config.defaults import TRUNCATE_RESEARCH_LARGE
from .base import BaseResearchHandler


class BugInvestigationHandler(BaseResearchHandler):
    """Handler for BUG_INVESTIGATION intent - searches for error patterns."""

    @property
    def intent(self) -> QueryIntent:
        """The intent this handler processes."""
        return QueryIntent.BUG_INVESTIGATION

    def execute(
        self,
        agent: Any,
        classification: ClassificationResult,
        io: CLIIOProtocol
    ) -> List[str]:
        """
        Execute bug investigation research.

        Searches for error types and error handling patterns.

        Args:
            agent: CodeAgent with _tool_search_code method
            classification: The query classification result
            io: IO interface for progress output

        Returns:
            List of bug investigation results
        """
        results = []

        # Search for error types mentioned
        for error_type in classification.entities.get('error_type', [])[:3]:
            io.echo(f"  - Searching for '{error_type}'...")
            success, result = self._safe_tool_call(
                agent._tool_search_code,
                error_type,
                "*.py"
            )
            if success and "No matches" not in result:
                results.append(
                    f"Error '{error_type}' occurrences:\n{result[:TRUNCATE_RESEARCH_LARGE]}"
                )

        # Check for error handling patterns if no specific error type
        if not classification.entities.get('error_type'):
            io.echo("  - Searching for error handling...")
            success, result = self._safe_tool_call(
                agent._tool_search_code,
                "except|raise|Error",
                "*.py"
            )
            if success and "No matches" not in result:
                results.append(
                    f"Error handling patterns:\n{result[:TRUNCATE_RESEARCH_LARGE]}"
                )

        return results
