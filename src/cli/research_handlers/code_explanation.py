"""
Handler for CODE_EXPLANATION intent research.
"""

from typing import List, Any

from ..io_interface import CLIIOProtocol
from ..config.defaults import TRUNCATE_FILE_CONTENT
from .base import QueryIntent, ClassificationResult, BaseResearchHandler


class CodeExplanationHandler(BaseResearchHandler):
    """Handler for CODE_EXPLANATION intent - reads files for explanation."""

    @property
    def intent(self) -> QueryIntent:
        """The intent this handler processes."""
        return QueryIntent.CODE_EXPLANATION

    def execute(
        self,
        agent: Any,
        classification: ClassificationResult,
        io: CLIIOProtocol
    ) -> List[str]:
        """
        Execute code explanation research.

        Reads specific files extracted from the query.

        Args:
            agent: CodeAgent with _tool_read_file method
            classification: The query classification result
            io: IO interface for progress output

        Returns:
            List of file content results
        """
        results = []

        # Read specific files if paths are extracted
        for file_path in classification.entities.get('file_path', [])[:2]:
            io.echo(f"  - Reading file '{file_path}'...")
            success, result = self._safe_tool_call(
                agent._tool_read_file,
                file_path,
                max_lines=100
            )
            if success:
                results.append(
                    f"File '{file_path}':\n{result[:TRUNCATE_FILE_CONTENT]}"
                )

        return results
