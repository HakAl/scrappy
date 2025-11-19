"""
Handler for ARCHITECTURE intent research.
"""

from typing import List, Any

from ...intent_classifier import QueryIntent, ClassificationResult
from ..io_interface import CLIIOProtocol
from ..config.defaults import TRUNCATE_RESEARCH_MEDIUM
from .base import BaseResearchHandler


class ArchitectureHandler(BaseResearchHandler):
    """Handler for ARCHITECTURE intent - analyzes project architecture."""

    @property
    def intent(self) -> QueryIntent:
        """The intent this handler processes."""
        return QueryIntent.ARCHITECTURE

    def execute(
        self,
        agent: Any,
        classification: ClassificationResult,
        io: CLIIOProtocol
    ) -> List[str]:
        """
        Execute architecture research.

        Lists project structure and searches for architectural patterns.

        Args:
            agent: CodeAgent with _tool_list_directory and _tool_search_code methods
            classification: The query classification result
            io: IO interface for progress output

        Returns:
            List of architecture results
        """
        results = []

        io.echo("  - Analyzing project architecture...")

        # Get project structure
        success, result = self._safe_tool_call(
            agent._tool_list_directory,
            ".",
            depth=3
        )
        if success:
            results.append(f"Project Structure:\n{result}")

        # Look for architectural patterns
        for pattern in ['service', 'controller', 'model', 'repository', 'handler']:
            success, result = self._safe_tool_call(
                agent._tool_search_code,
                f"class.*{pattern}",
                "*.py"
            )
            if success and "No matches" not in result:
                results.append(
                    f"Architecture pattern '{pattern}':\n{result[:TRUNCATE_RESEARCH_MEDIUM]}"
                )
                break

        return results
