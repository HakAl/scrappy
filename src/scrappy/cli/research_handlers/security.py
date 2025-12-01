"""
Handler for SECURITY intent research.
"""

from typing import List, Any

from ..io_interface import CLIIOProtocol
from ..config.defaults import TRUNCATE_RESEARCH_MEDIUM
from .base import QueryIntent, ClassificationResult, BaseResearchHandler


class SecurityHandler(BaseResearchHandler):
    """Handler for SECURITY intent - searches for security patterns."""

    @property
    def intent(self) -> QueryIntent:
        """The intent this handler processes."""
        return QueryIntent.SECURITY

    def execute(
        self,
        agent: Any,
        classification: ClassificationResult,
        io: CLIIOProtocol
    ) -> List[str]:
        """
        Execute security research.

        Searches for security-related patterns in code.

        Args:
            agent: CodeAgent with _tool_search_code method
            classification: The query classification result
            io: IO interface for progress output

        Returns:
            List of security results
        """
        results = []
        tools_used = 0

        io.echo("  - Checking security patterns...")

        for pattern in ['auth', 'permission', 'token', 'password', 'encrypt']:
            success, result = self._safe_tool_call(
                agent._tool_search_code,
                pattern,
                "*.py"
            )
            if success and "No matches" not in result:
                results.append(
                    f"Security pattern '{pattern}':\n{result[:TRUNCATE_RESEARCH_MEDIUM]}"
                )
                tools_used += 1
                if tools_used >= 3:
                    break

        return results
