"""
Handler for TESTING intent research.
"""

from typing import List, Any

from ...intent_classifier import QueryIntent, ClassificationResult
from ..io_interface import CLIIOProtocol
from ..config.defaults import TRUNCATE_RESEARCH_LARGE
from .base import BaseResearchHandler


class TestingHandler(BaseResearchHandler):
    """Handler for TESTING intent - finds test files and patterns."""

    @property
    def intent(self) -> QueryIntent:
        """The intent this handler processes."""
        return QueryIntent.TESTING

    def execute(
        self,
        agent: Any,
        classification: ClassificationResult,
        io: CLIIOProtocol
    ) -> List[str]:
        """
        Execute testing research.

        Finds test files and searches for test patterns.

        Args:
            agent: CodeAgent with _tool_list_directory and _tool_search_code methods
            classification: The query classification result
            io: IO interface for progress output

        Returns:
            List of testing results
        """
        results = []

        io.echo("  - Finding test files...")

        # List directory and filter for test files
        success, result = self._safe_tool_call(
            agent._tool_list_directory,
            ".",
            depth=3
        )
        if success:
            # Filter for test directories/files
            test_lines = [
                line for line in result.split('\n')
                if 'test' in line.lower()
            ]
            if test_lines:
                results.append(
                    f"Test files:\n" + '\n'.join(test_lines[:20])
                )

        # Search for test patterns
        io.echo("  - Searching for test patterns...")
        success, result = self._safe_tool_call(
            agent._tool_search_code,
            "def test_|class Test",
            "*.py"
        )
        if success and "No matches" not in result:
            results.append(
                f"Test definitions:\n{result[:TRUNCATE_RESEARCH_LARGE]}"
            )

        return results
