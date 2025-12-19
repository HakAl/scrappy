"""
Factory for building agent execution context.

Creates AgentContext with system prompt, active tools, and passive RAG context.
Handles tool filtering based on semantic search readiness and budget heuristics
for adaptive RAG context.
"""

import re
from typing import Optional, List, TYPE_CHECKING

from .types import AgentContext
from ..agent_config import AgentConfig
from ..agent_tools.tools import ToolRegistry

if TYPE_CHECKING:
    from ..context.protocols import SemanticSearchManagerProtocol


class AgentContextFactory:
    """
    Builds agent execution context with dynamic tool filtering and passive RAG.

    Single Responsibility: Create AgentContext based on task and state.

    Responsibilities:
    - Filter tools based on semantic search availability
    - Compute passive RAG context budget heuristically
    - Build search strategy prompt section
    - Assemble final AgentContext
    """

    def __init__(
        self,
        semantic_manager: Optional['SemanticSearchManagerProtocol'],
        config: AgentConfig,
        tool_registry: ToolRegistry,
    ):
        """Initialize context factory.

        Args:
            semantic_manager: Semantic search manager for RAG context
            config: Agent configuration
            tool_registry: Registry of available tools
        """
        self._semantic_manager = semantic_manager
        self._config = config
        self._tool_registry = tool_registry

    def build_context(
        self,
        task: str,
        base_system_prompt: str,
    ) -> AgentContext:
        """
        Build agent context for a task.

        Args:
            task: User task description
            base_system_prompt: Base system prompt template

        Returns:
            AgentContext with system_prompt, active_tools, passive_rag_context
        """
        # 1. Filter tools based on semantic search readiness
        active_tools = self._get_active_tools()

        # 2. Compute passive RAG context if enabled
        passive_rag_context = None
        if self._config.passive_rag_enabled and self._semantic_manager:
            passive_rag_context = self._build_passive_rag_context(task)

        # 3. Build final system prompt with search strategy section
        system_prompt = self._build_system_prompt(
            base_system_prompt,
            active_tools,
            passive_rag_context
        )

        return AgentContext(
            system_prompt=system_prompt,
            active_tools=active_tools,
            passive_rag_context=passive_rag_context,
        )

    def _get_active_tools(self) -> List[str]:
        """
        Get list of active tool names, filtering out unavailable ones.

        Filters out codebase_search tool if semantic search is not ready.

        Returns:
            List of active tool names
        """
        all_tools = [tool.name for tool in self._tool_registry.list_all()]

        # Filter out codebase_search if not ready
        if not self._is_semantic_search_ready():
            return [name for name in all_tools if name != "codebase_search"]

        return all_tools

    def _is_semantic_search_ready(self) -> bool:
        """Check if semantic search is ready to use.

        Returns:
            True if semantic search is indexed and ready, False otherwise
        """
        if not self._semantic_manager:
            return False
        return self._semantic_manager.is_ready()

    def _build_passive_rag_context(self, task: str) -> Optional[str]:
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

            # Format chunks into context string
            return self._format_rag_context(result.chunks)

        except Exception:
            # Silently fail - passive RAG is optional
            return None

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
        base_budget = self._config.passive_rag_max_tokens
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

    def _format_rag_context(self, chunks: List[dict]) -> Optional[str]:
        """
        Format RAG chunks into context string with quality filtering.

        Uses elbow filtering: absolute floor + relative gap detection to
        filter out low-relevance results that add noise rather than signal.

        Args:
            chunks: List of chunk dicts with keys: path, lines, content, score

        Returns:
            Formatted context string, or None if no quality results
        """
        import logging
        logger = logging.getLogger(__name__)

        if not chunks:
            return None

        # Sort by score descending
        chunks = sorted(chunks, key=lambda x: x.get('score', 0), reverse=True)

        # Log scores for calibration
        scores = [c.get('score', 0) for c in chunks]
        logger.debug(f"RAG scores: {scores}")

        # Filter thresholds from config
        min_score = self._config.rag_min_score
        max_gap = self._config.rag_max_gap

        # Top result must meet floor
        if chunks[0].get('score', 0) < min_score:
            logger.debug(f"RAG: top score {chunks[0].get('score', 0)} below floor {min_score}")
            return None

        # Elbow filtering
        filtered = [chunks[0]]
        prev_score = chunks[0]['score']

        for chunk in chunks[1:]:
            score = chunk.get('score', 0)

            # Check absolute floor
            if score < min_score:
                break

            # Check relative gap (elbow detection)
            if (prev_score - score) > max_gap:
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

    def _build_system_prompt(
        self,
        base_prompt: str,
        active_tools: List[str],
        passive_rag_context: Optional[str],
    ) -> str:
        """
        Build final system prompt with search strategy and RAG context.

        Args:
            base_prompt: Base system prompt template
            active_tools: List of active tool names
            passive_rag_context: Optional RAG context block

        Returns:
            Complete system prompt
        """
        sections = [base_prompt]

        # Add search strategy section
        search_strategy = self._build_search_strategy_section(active_tools)
        if search_strategy:
            sections.append(search_strategy)

        # Add passive RAG context if available
        if passive_rag_context:
            sections.append("\n---\n")
            sections.append(passive_rag_context)

        return "\n\n".join(sections)

    def _build_search_strategy_section(self, active_tools: List[str]) -> str:
        """
        Build search strategy guidance section based on available tools.

        Args:
            active_tools: List of active tool names

        Returns:
            Search strategy prompt section
        """
        has_semantic = "codebase_search" in active_tools
        has_exact = "find_exact_text" in active_tools

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
