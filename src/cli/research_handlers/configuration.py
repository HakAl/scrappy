"""
Handler for CONFIGURATION intent research.
"""

from typing import List, Any

from ...intent_classifier import QueryIntent, ClassificationResult
from ..io_interface import CLIIOProtocol
from ..config.defaults import TRUNCATE_RESEARCH_LARGE
from ..config.extensions import CONFIGURATION_FILES
from .base import BaseResearchHandler


class ConfigurationHandler(BaseResearchHandler):
    """Handler for CONFIGURATION intent - checks config files and usage."""

    @property
    def intent(self) -> QueryIntent:
        """The intent this handler processes."""
        return QueryIntent.CONFIGURATION

    def execute(
        self,
        agent: Any,
        classification: ClassificationResult,
        io: CLIIOProtocol
    ) -> List[str]:
        """
        Execute configuration research.

        Reads configuration files and searches for config usage.

        Args:
            agent: CodeAgent with _tool_read_file and _tool_search_code methods
            classification: The query classification result
            io: IO interface for progress output

        Returns:
            List of configuration results
        """
        results = []

        io.echo("  - Checking configuration files...")

        # Read configuration files
        for config_file in CONFIGURATION_FILES:
            success, result = self._safe_tool_call(
                agent._tool_read_file,
                config_file,
                max_lines=100
            )
            if success and "not found" not in result.lower():
                results.append(f"Configuration ({config_file}):\n{result}")

        # Search for config usage
        io.echo("  - Searching for config usage...")
        success, result = self._safe_tool_call(
            agent._tool_search_code,
            "config|CONFIG|settings|Settings",
            "*.py"
        )
        if success and "No matches" not in result:
            results.append(
                f"Configuration usage:\n{result[:TRUNCATE_RESEARCH_LARGE]}"
            )

        return results
