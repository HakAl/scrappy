"""
Handler for GIT_HISTORY intent research.
"""

from typing import List, Any

from ...intent_classifier import QueryIntent, ClassificationResult
from ..io_interface import CLIIOProtocol
from .base import BaseResearchHandler


class GitHistoryHandler(BaseResearchHandler):
    """Handler for GIT_HISTORY intent - retrieves git history and status."""

    @property
    def intent(self) -> QueryIntent:
        """The intent this handler processes."""
        return QueryIntent.GIT_HISTORY

    def execute(
        self,
        agent: Any,
        classification: ClassificationResult,
        io: CLIIOProtocol
    ) -> List[str]:
        """
        Execute git history research.

        Retrieves git log and git status.

        Args:
            agent: CodeAgent with _tool_git_log and _tool_git_status methods
            classification: The query classification result
            io: IO interface for progress output

        Returns:
            List of git history results
        """
        results = []

        # Get git log
        io.echo("  - Checking git history...")
        success, result = self._safe_tool_call(agent._tool_git_log, n=10)
        if success:
            results.append(f"Recent Commits:\n{result}")

        # Get git status
        io.echo("  - Checking git status...")
        success, result = self._safe_tool_call(agent._tool_git_status)
        if success:
            results.append(f"Git Status:\n{result}")

        return results
