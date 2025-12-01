"""
Handler for DOCUMENTATION intent research.
"""

from typing import List, Any

from ..io_interface import CLIIOProtocol
from .base import QueryIntent, ClassificationResult, BaseResearchHandler


class DocumentationHandler(BaseResearchHandler):
    """Handler for DOCUMENTATION intent - finds documentation files."""

    @property
    def intent(self) -> QueryIntent:
        """The intent this handler processes."""
        return QueryIntent.DOCUMENTATION

    def execute(
        self,
        agent: Any,
        classification: ClassificationResult,
        io: CLIIOProtocol
    ) -> List[str]:
        """
        Execute documentation research.

        Lists documentation files in the project.

        Args:
            agent: CodeAgent with _tool_list_directory method
            classification: The query classification result
            io: IO interface for progress output

        Returns:
            List of documentation results
        """
        results = []

        io.echo("  - Searching documentation...")

        success, result = self._safe_tool_call(
            agent._tool_list_directory,
            ".",
            depth=2
        )
        if success:
            doc_lines = [
                line for line in result.split('\n')
                if any(ext in line.lower() for ext in ['.md', '.rst', '.txt', 'readme', 'doc'])
            ]
            if doc_lines:
                results.append(
                    f"Documentation files:\n" + '\n'.join(doc_lines[:15])
                )

        return results
