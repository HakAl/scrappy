"""
Handler for CODE_SEARCH intent research.
"""

from typing import List, Any, Set

from ...intent_classifier import QueryIntent, ClassificationResult
from ..io_interface import CLIIOProtocol
from ..config.defaults import TRUNCATE_RESEARCH_LARGE
from .base import BaseResearchHandler


class CodeSearchHandler(BaseResearchHandler):
    """Handler for CODE_SEARCH intent - searches for code patterns."""

    @property
    def intent(self) -> QueryIntent:
        """The intent this handler processes."""
        return QueryIntent.CODE_SEARCH

    def execute(
        self,
        agent: Any,
        classification: ClassificationResult,
        io: CLIIOProtocol
    ) -> List[str]:
        """
        Execute code search research.

        Searches for classes, functions, and keywords extracted from the query.

        Args:
            agent: CodeAgent with _tool_search_code method
            classification: The query classification result
            io: IO interface for progress output

        Returns:
            List of search results
        """
        results = []
        searched: Set[str] = set()

        # Search for class names
        for class_name in classification.entities.get('class_name', [])[:3]:
            if class_name not in searched:
                io.echo(f"  - Searching for class '{class_name}'...")
                success, result = self._safe_tool_call(
                    agent._tool_search_code,
                    f"class {class_name}",
                    "*.py"
                )
                if success and "No matches" not in result:
                    results.append(
                        f"Class '{class_name}':\n{result[:TRUNCATE_RESEARCH_LARGE]}"
                    )
                searched.add(class_name)

        # Search for function names
        for func_name in classification.entities.get('function_name', [])[:3]:
            if func_name not in searched:
                io.echo(f"  - Searching for function '{func_name}'...")
                success, result = self._safe_tool_call(
                    agent._tool_search_code,
                    f"def {func_name}",
                    "*.py"
                )
                if success and "No matches" not in result:
                    results.append(
                        f"Function '{func_name}':\n{result[:TRUNCATE_RESEARCH_LARGE]}"
                    )
                searched.add(func_name)

        # Search for keywords if no entities found
        if not searched and classification.keywords:
            for keyword in classification.keywords[:3]:
                if len(keyword) > 3:
                    io.echo(f"  - Searching for '{keyword}'...")
                    success, result = self._safe_tool_call(
                        agent._tool_search_code,
                        keyword,
                        "*.py"
                    )
                    if success and "No matches" not in result:
                        results.append(
                            f"Code containing '{keyword}':\n{result[:TRUNCATE_RESEARCH_LARGE]}"
                        )
                        break

        return results
