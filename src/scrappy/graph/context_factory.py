"""
Context factory for graph-based agent.

Builds agent execution context with passive RAG and search strategy guidance.
Ported from agent/context_factory.py for the graph package.

Single Responsibility: Create context (RAG, search strategy) based on task.
"""

import re
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from scrappy.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from scrappy.context.protocols import SemanticSearchManagerProtocol

logger = get_logger(__name__)


@dataclass
class RAGConfig:
    """Configuration for passive RAG context."""
    max_tokens: int = 2000
    min_score: float = 0.3
    max_gap: float = 0.15


class GraphContextFactory:
    """
    Builds agent execution context with dynamic RAG and search strategy.

    Single Responsibility: Create context based on task and available tools.

    Features:
    - Passive RAG with heuristic budget boosting
    - Elbow filtering for quality results
    - Search strategy guidance based on available tools

    Example:
        factory = GraphContextFactory(semantic_manager)
        rag_context = factory.build_rag_context("explain the authentication flow")
        search_guidance = factory.build_search_strategy_section(["codebase_search", "find_exact_text"])
    """

    def __init__(
        self,
        semantic_manager: Optional['SemanticSearchManagerProtocol'] = None,
        config: Optional[RAGConfig] = None,
    ):
        """
        Initialize context factory.

        Args:
            semantic_manager: Semantic search manager for RAG context
            config: RAG configuration (uses defaults if None)
        """
        self._semantic_manager = semantic_manager
        self._config = config or RAGConfig()

    def build_rag_context(self, task: str) -> Optional[str]:
        """
        Build passive RAG context using semantic search.

        Computes token budget using heuristics based on task complexity,
        then performs semantic search to retrieve relevant code context.

        Args:
            task: User task description

        Returns:
            Formatted RAG context string, or None if unavailable
        """
        if not self._semantic_manager or not self._semantic_manager.is_ready():
            return None

        # Compute budget with heuristics
        max_tokens = self._compute_rag_budget(task)

        # Perform semantic search
        try:
            result = self._semantic_manager.search(task, max_tokens=max_tokens)

            if not result or not result.chunks:
                return None

            # Format chunks into context string with quality filtering
            return self._format_rag_context(result.chunks)

        except Exception as e:
            # Silently fail - passive RAG is optional
            logger.debug("Passive RAG failed: %s", e)
            return None

    def build_search_strategy_section(self, tool_names: list[str]) -> str:
        """
        Build search strategy guidance section based on available tools.

        Args:
            tool_names: List of active tool names

        Returns:
            Search strategy prompt section, empty string if no search tools
        """
        has_semantic = "codebase_search" in tool_names
        has_exact = "find_exact_text" in tool_names

        if not has_semantic and not has_exact:
            return ""

        lines = ["## Code Search Strategy"]

        if has_semantic:
            lines.append(
                "- Use `codebase_search` for conceptual queries: 'how does X work', "
                "'find error handling', 'where is authentication logic'"
            )

        if has_exact:
            lines.append(
                "- Use `find_exact_text` for literal pattern matching: specific "
                "function names, class names, exact strings"
            )

        if has_semantic and has_exact:
            lines.append(
                "\nPrefer semantic search for exploratory tasks. Use exact text "
                "search when you know the specific identifier you're looking for."
            )

        return "\n".join(lines)

    def is_ready(self) -> bool:
        """
        Check if context factory is ready (semantic search indexed).

        Returns:
            True if ready to provide RAG context, False otherwise
        """
        if not self._semantic_manager:
            return False
        return self._semantic_manager.is_ready()

    def _compute_rag_budget(self, task: str) -> int:
        """
        Compute token budget for passive RAG based on task heuristics.

        Boosts budget when task mentions:
        - File references (paths with / or backslash or extensions)
        - Identifiers (class names, function names, variables)
        - Multiple concepts requiring broader context

        Args:
            task: User task description

        Returns:
            Token budget (boosted from base config value)
        """
        base_budget = self._config.max_tokens
        boost_factor = 1.0

        # Boost for file references
        file_pattern = r'(?:[a-zA-Z_][\w/\\]*\.[a-z]+)|(?:src/)|(?:tests/)'
        if re.search(file_pattern, task):
            boost_factor += 0.3

        # Boost for identifiers (CamelCase, snake_case)
        identifier_pattern = r'\b(?:[A-Z][a-z]+){2,}|[a-z_]+_[a-z_]+'
        identifiers = re.findall(identifier_pattern, task)
        if len(identifiers) >= 4:
            boost_factor += 0.4
        elif len(identifiers) >= 2:
            boost_factor += 0.2

        # Boost for question words indicating exploration
        exploration_words = ['how', 'where', 'what', 'why', 'explain', 'understand']
        if any(word in task.lower() for word in exploration_words):
            boost_factor += 0.2

        # Cap boost at 2x base budget
        boost_factor = min(boost_factor, 2.0)

        return int(base_budget * boost_factor)

    def _format_rag_context(self, chunks: list[dict]) -> Optional[str]:
        """
        Format RAG chunks into context string with quality filtering.

        Uses elbow filtering: absolute floor + relative gap detection to
        filter out low-relevance results that add noise rather than signal.

        Args:
            chunks: List of chunk dicts with keys: path, lines, content, score

        Returns:
            Formatted context string, or None if no quality results
        """
        if not chunks:
            return None

        # Sort by score descending
        chunks = sorted(chunks, key=lambda x: x.get('score', 0), reverse=True)

        # Top result must meet floor
        if chunks[0].get('score', 0) < self._config.min_score:
            logger.debug(
                "RAG: top score %s below floor %s",
                chunks[0].get('score', 0),
                self._config.min_score
            )
            return None

        # Elbow filtering
        filtered = [chunks[0]]
        prev_score = chunks[0]['score']

        for chunk in chunks[1:]:
            score = chunk.get('score', 0)

            # Check absolute floor
            if score < self._config.min_score:
                break

            # Check relative gap (elbow detection)
            if (prev_score - score) > self._config.max_gap:
                break

            filtered.append(chunk)
            prev_score = score

        # Format survivors
        lines = ["## Relevant Codebase Context\n"]

        for chunk in filtered:
            path = chunk["path"]
            start_line, end_line = chunk["lines"]
            content = chunk["content"]

            lines.append(f"\n### {path}:{start_line}-{end_line}")
            lines.append("```")
            lines.append(content.rstrip())
            lines.append("```")

        return "\n".join(lines)


class NullContextFactory:
    """
    No-op context factory for when RAG is unavailable.

    Implements ContextFactoryProtocol but returns empty/None for all methods.
    Use when semantic search is not configured or unavailable.
    """

    def build_rag_context(self, task: str) -> None:
        """Returns None - no RAG available."""
        return None

    def build_search_strategy_section(self, tool_names: list[str]) -> str:
        """Returns empty string - no search strategy guidance."""
        return ""

    def is_ready(self) -> bool:
        """Returns False - always unavailable."""
        return False


# Verify protocol compliance at import time
def _verify_protocols() -> None:
    """Verify implementations satisfy the protocol."""
    # Import here to avoid circular import and redefinition
    from scrappy.graph import protocols

    # These will raise if protocol not satisfied
    assert isinstance(GraphContextFactory(None), protocols.ContextFactoryProtocol)
    assert isinstance(NullContextFactory(), protocols.ContextFactoryProtocol)


_verify_protocols()
