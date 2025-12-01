"""
Handler for DEPENDENCY_INFO intent research.
"""

from typing import List, Any

from ..io_interface import CLIIOProtocol
from ..config.defaults import TRUNCATE_RESEARCH_MEDIUM
from ..config.extensions import DEPENDENCY_FILES
from .base import QueryIntent, ClassificationResult, BaseResearchHandler


class DependencyInfoHandler(BaseResearchHandler):
    """Handler for DEPENDENCY_INFO intent - checks dependencies."""

    @property
    def intent(self) -> QueryIntent:
        """The intent this handler processes."""
        return QueryIntent.DEPENDENCY_INFO

    def execute(
        self,
        agent: Any,
        classification: ClassificationResult,
        io: CLIIOProtocol
    ) -> List[str]:
        """
        Execute dependency info research.

        Reads dependency files and searches for package usage.

        Args:
            agent: CodeAgent with _tool_read_file and _tool_search_code methods
            classification: The query classification result
            io: IO interface for progress output

        Returns:
            List of dependency results
        """
        results = []

        io.echo("  - Checking dependencies...")

        # Check for common dependency files
        for dep_file in DEPENDENCY_FILES[:4]:
            success, result = self._safe_tool_call(
                agent._tool_read_file,
                dep_file,
                max_lines=50
            )
            if success and "not found" not in result.lower():
                results.append(f"Dependencies ({dep_file}):\n{result}")
                break

        # Search for specific package imports
        for pkg in classification.entities.get('package_name', [])[:3]:
            io.echo(f"  - Searching for '{pkg}' usage...")
            success, result = self._safe_tool_call(
                agent._tool_search_code,
                f"import {pkg}",
                "*.py"
            )
            if success and "No matches" not in result:
                results.append(
                    f"Usage of '{pkg}':\n{result[:TRUNCATE_RESEARCH_MEDIUM]}"
                )

        return results
