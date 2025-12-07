"""
Semantic search tool for the code agent.

Provides conceptual code search using embeddings and hybrid search.
Falls back to guiding message when index is not ready.
"""

from typing import Optional

from .base import ToolBase, ToolParameter, ToolResult, ToolContext
from ...context.protocols import SemanticSearchProtocol


class SemanticSearchTool(ToolBase):
    """
    Semantic code search using embeddings and hybrid search.

    Searches codebase for conceptually relevant code using semantic similarity.
    When semantic search is unavailable or not indexed, returns helpful message.
    """

    def __init__(
        self,
        semantic_search: Optional[SemanticSearchProtocol] = None,
    ):
        """Initialize with optional injected semantic search provider.

        Args:
            semantic_search: Pre-configured semantic search backend (for DI).
        """
        self._semantic_search = semantic_search

    @property
    def name(self) -> str:
        return "codebase_search"

    @property
    def description(self) -> str:
        return (
            "Semantic code search for conceptual queries. Finds code based on "
            "meaning, not exact text. Use this for 'how does X work?', 'find "
            "error handling', 'where is authentication?'. Returns relevant code "
            "chunks with file paths and line numbers."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                "query",
                str,
                "Conceptual search query describing what you're looking for",
                required=True
            ),
            ToolParameter(
                "max_tokens",
                int,
                "Token budget for results. Results are truncated when this limit "
                "is reached (default: 4000). Lower values return fewer but faster results.",
                required=False,
                default=4000
            ),
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        query = kwargs["query"]
        max_tokens = kwargs.get("max_tokens", 4000)

        # Check if semantic search is available
        if not self._semantic_search:
            return ToolResult(
                success=True,
                output=(
                    "Semantic search is not available. The codebase may still be "
                    "indexing in the background. Please wait a moment and try again, "
                    "or use find_exact_text for literal pattern matching."
                ),
                metadata={"available": False}
            )

        # Check if index is ready
        if not self._semantic_search.is_indexed():
            return ToolResult(
                success=True,
                output=(
                    "Semantic search index is not ready yet. The codebase is being "
                    "indexed in the background. Please wait a moment and try again, "
                    "or use find_exact_text for literal pattern matching."
                ),
                metadata={"indexed": False}
            )

        # Perform semantic search
        try:
            result = self._semantic_search.search(
                query=query,
                max_tokens=max_tokens
            )

            if not result.chunks:
                return ToolResult(
                    success=True,
                    output=f"No relevant code found for query: '{query}'",
                    metadata={
                        "matches": 0,
                        "tokens_used": result.tokens_used,
                        "query": query
                    }
                )

            # Format output
            output = self._format_results(result.chunks)

            if result.limit_hit:
                output += f"\n\n[Note: Results truncated due to {result.limit_hit}]"

            # Remember search for working memory
            file_paths = [chunk["path"] for chunk in result.chunks]
            context.remember_search(query, file_paths)

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "matches": len(result.chunks),
                    "tokens_used": result.tokens_used,
                    "query": query,
                    "limit_hit": result.limit_hit
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Semantic search error: {str(e)}"
            )

    def _format_results(self, chunks: list[dict]) -> str:
        """Format search results for output.

        Args:
            chunks: List of chunk dicts with keys: path, lines (tuple), content, score

        Returns:
            Formatted string with file paths, line ranges, and content
        """
        lines = []
        for chunk in chunks:
            path = chunk["path"]
            start_line, end_line = chunk["lines"]
            content = chunk["content"]
            score = chunk.get("score", 0.0)

            # Header with file path, line range, and score
            lines.append(f"\n{path}:{start_line}-{end_line} (score: {score:.3f})")
            lines.append("-" * 60)

            # Content with line numbers
            content_lines = content.split("\n")
            for i, line in enumerate(content_lines, start=start_line):
                lines.append(f"{i:4d} | {line}")

        return "\n".join(lines)
