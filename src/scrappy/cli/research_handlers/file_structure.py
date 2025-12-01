"""
Handler for FILE_STRUCTURE intent research.
"""

from typing import List, Any

from ..io_interface import CLIIOProtocol
from .base import QueryIntent, ClassificationResult, BaseResearchHandler


class FileStructureHandler(BaseResearchHandler):
    """Handler for FILE_STRUCTURE intent - lists directory structure."""

    @property
    def intent(self) -> QueryIntent:
        """The intent this handler processes."""
        return QueryIntent.FILE_STRUCTURE

    def execute(
        self,
        agent: Any,
        classification: ClassificationResult,
        io: CLIIOProtocol
    ) -> List[str]:
        """
        Execute file structure research.

        Lists the project directory structure.

        Args:
            agent: CodeAgent with _tool_list_directory method
            classification: The query classification result
            io: IO interface for progress output

        Returns:
            List containing directory structure result
        """
        results = []

        io.echo("  - Checking directory structure...")

        success, result = self._safe_tool_call(
            agent._tool_list_directory,
            ".",
            depth=2
        )

        if success:
            results.append(f"Directory Structure:\n{result}")
        else:
            io.echo(f"    (Warning: Could not list directory: {result})")

        return results
