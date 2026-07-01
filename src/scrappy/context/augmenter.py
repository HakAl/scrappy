"""
Context augmentation for prompts.

Builds context blocks for prompt augmentation from various sources
(summary, structure, git history, semantic search).
"""

import logging
from pathlib import Path
from typing import Optional, Callable

from .protocols import SearchResult, SemanticSearchManagerProtocol

logger = logging.getLogger(__name__)


class ContextAugmenter:
    """
    Augments prompts with codebase context.

    Builds context blocks for prompt augmentation from various sources
    (summary, structure, git history, semantic search).

    Single Responsibility: Format context for prompts.

    Usage:
        augmenter = ContextAugmenter(
            project_path=Path("/path/to/project"),
            summary_provider=lambda: "Project summary...",
            structure_provider=lambda: {"total_files": 100},
            git_history_provider=lambda: {"current_branch": "main"},
            file_index_provider=lambda: {"python": ["main.py"]},
        )

        augmented = augmenter.augment("Fix the bug")
    """

    def __init__(
        self,
        project_path: Path,
        summary_provider: Callable[[], Optional[str]],
        structure_provider: Callable[[], dict],
        git_history_provider: Callable[[], dict],
        file_index_provider: Callable[[], dict],
        is_explored_provider: Callable[[], bool],
        semantic_manager: Optional[SemanticSearchManagerProtocol] = None,
    ):
        """
        Initialize context augmenter.

        Args:
            project_path: Path to project root
            summary_provider: Function returning project summary (or None)
            structure_provider: Function returning structure dict
            git_history_provider: Function returning git history dict
            file_index_provider: Function returning file index dict
            is_explored_provider: Function returning whether codebase is explored
            semantic_manager: Optional semantic search manager for semantic context
        """
        self._project_path = project_path
        self._summary_provider = summary_provider
        self._structure_provider = structure_provider
        self._git_history_provider = git_history_provider
        self._file_index_provider = file_index_provider
        self._is_explored_provider = is_explored_provider
        self._semantic_manager = semantic_manager

    def augment(self, prompt: str, include_files: bool = False) -> str:
        """
        Augment a prompt with codebase context.

        Args:
            prompt: Original user prompt
            include_files: Whether to include file listings

        Returns:
            Augmented prompt with context blocks
        """
        if not self._is_explored_provider():
            return prompt

        context_parts = []

        # Add project summary if available
        summary = self._summary_provider()
        if summary:
            context_parts.append(f"Project Context:\n{summary}")

        # Add structure info
        structure = self._structure_provider()
        if structure:
            structure_info = [
                f"Project: {self._project_path.name}",
                f"Files: {structure.get('total_files', 0)} total",
                f"Languages: {', '.join(k for k, v in structure.get('by_type', {}).items() if v > 0 and k != 'other')}",
            ]
            context_parts.append("Structure:\n" + "\n".join(structure_info))

        # Add git history info
        git_history = self._git_history_provider()
        if git_history:
            git_info = []
            if git_history.get('current_branch'):
                git_info.append(f"Branch: {git_history['current_branch']}")
            if git_history.get('recent_commits'):
                commits = git_history['recent_commits'][:5]
                git_info.append("Recent commits:\n" + "\n".join(f"  {c}" for c in commits))
            if git_history.get('recently_changed_files'):
                changed = git_history['recently_changed_files'][:10]
                git_info.append(f"Recently changed: {', '.join(changed)}")
            if git_info:
                context_parts.append("Git History:\n" + "\n".join(git_info))

        # Optionally include relevant file listings
        if include_files:
            file_index = self._file_index_provider()
            if file_index:
                py_files = file_index.get('python', [])[:20]
                if py_files:
                    context_parts.append("Python files:\n" + "\n".join(f"  - {f}" for f in py_files))

        if context_parts:
            context_block = "\n\n".join(context_parts)
            return f"""[Codebase Context]
{context_block}

[User Request]
{prompt}"""

        return prompt

    def get_relevant_context(self, query: str, max_tokens: int = 4000) -> str:
        """
        Get context relevant to a specific query.

        Uses semantic search if available, falls back to keyword matching.

        Args:
            query: Query to find relevant context for
            max_tokens: Maximum tokens to return

        Returns:
            Relevant context string
        """
        if not self._is_explored_provider():
            return ""

        # Try semantic search first
        if self._semantic_manager:
            result = self._semantic_manager.search(query, max_tokens=max_tokens)
            if result and result.chunks:
                logger.debug(f"Using semantic search ({len(result.chunks)} chunks)")
                return self._format_search_result(result)

        # Fall back to keyword matching
        logger.debug("Using keyword-based context")
        return self._get_keyword_context(query)

    def _format_search_result(self, result: SearchResult) -> str:
        """
        Format search result into context string.

        Args:
            result: SearchResult from semantic search

        Returns:
            Formatted context string
        """
        if not result.chunks:
            return ""

        parts = []
        for chunk in result.chunks:
            header = f"--- {chunk['path']} (lines {chunk['lines'][0]}-{chunk['lines'][1]}) ---"
            parts.append(f"{header}\n{chunk['content']}\n")

        return "\n".join(parts)

    def _get_keyword_context(self, query: str) -> str:
        """
        Get context using keyword matching.

        Args:
            query: Search query

        Returns:
            Context string based on keyword matching
        """
        query_lower = query.lower()
        relevant_parts = []

        # Always include summary
        summary = self._summary_provider()
        if summary:
            relevant_parts.append(f"Project: {summary}")

        file_index = self._file_index_provider()

        # Check for file-specific keywords
        if any(word in query_lower for word in ['file', 'module', 'class', 'function', 'import']):
            py_files = file_index.get('python', [])[:10]
            if py_files:
                relevant_parts.append("Key Python files:\n" + "\n".join(f"  {f}" for f in py_files))

        # Check for config-related queries
        # Note: key_files not available here - would need to be injected if needed
        if any(word in query_lower for word in ['config', 'setup', 'install', 'dependency', 'require']):
            # Could add key_files_provider if this functionality is needed
            pass

        # Check for architecture queries
        structure = self._structure_provider()
        if any(word in query_lower for word in ['architecture', 'structure', 'organize', 'pattern']):
            dirs = structure.get('directories', [])
            if dirs:
                relevant_parts.append(f"Project directories: {', '.join(dirs)}")

        return "\n\n".join(relevant_parts)


class NullContextAugmenter:
    """
    No-op context augmenter.

    Returns prompts unchanged. Used when context is not available.
    """

    def augment(self, prompt: str, include_files: bool = False) -> str:
        """Return prompt unchanged."""
        return prompt

    def get_relevant_context(self, query: str, max_tokens: int = 4000) -> str:
        """Return empty string."""
        return ""
