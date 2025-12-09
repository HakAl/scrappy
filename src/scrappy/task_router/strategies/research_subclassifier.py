"""
Research query subclassification.

Determines whether a research query is about the codebase or general knowledge.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple

from .research_subtype import ResearchSubtype


@dataclass
class SubclassificationResult:
    """Result of research query subclassification."""
    subtype: ResearchSubtype
    matched_files: Tuple[str, ...]  # Project files matching query terms


class ResearchSubclassifier:
    """
    Determines if a research query is about the codebase or general knowledge.

    Uses file_index to extract project-specific terms and match against the query.
    """

    def classify(
        self,
        query: str,
        file_index: Optional[dict] = None
    ) -> ResearchSubtype:
        """
        Classify a research query as codebase or general knowledge.

        Uses a 2-step approach:
        1. Extract project terms from file_index that match the query
        2. If matches found, return CODEBASE; otherwise GENERAL

        Args:
            query: The user's research query
            file_index: Optional file index mapping categories to file paths

        Returns:
            ResearchSubtype.CODEBASE or ResearchSubtype.GENERAL
        """
        result = self.classify_with_matches(query, file_index)
        return result.subtype

    def classify_with_matches(
        self,
        query: str,
        file_index: Optional[dict] = None
    ) -> SubclassificationResult:
        """
        Classify a research query and return matched project files.

        Args:
            query: The user's research query
            file_index: Optional file index mapping categories to file paths

        Returns:
            SubclassificationResult with subtype and matched files
        """
        # Step 1: Extract project terms and matching files from file_index
        if file_index:
            matched_terms, matched_files = self._extract_project_terms_and_files(query, file_index)

            # Step 2: If matches found, return CODEBASE with files
            if matched_terms:
                return SubclassificationResult(
                    subtype=ResearchSubtype.CODEBASE,
                    matched_files=tuple(matched_files)
                )

        # No matches or no file_index: return GENERAL
        return SubclassificationResult(
            subtype=ResearchSubtype.GENERAL,
            matched_files=()
        )

    def _extract_project_terms(self, query: str, file_index: dict) -> List[str]:
        """
        Extract project-specific terms from query that match file_index entries.

        Args:
            query: The user's research query
            file_index: File index mapping categories to file paths

        Returns:
            List of matched project terms (lowercased)
        """
        terms, _ = self._extract_project_terms_and_files(query, file_index)
        return terms

    def _extract_project_terms_and_files(
        self, query: str, file_index: dict
    ) -> Tuple[List[str], List[str]]:
        """
        Extract project-specific terms and matching files from file_index.

        Extracts words and bigrams from the query and matches them against:
        - file_index keys (categories)
        - Directory names in file paths
        - File basenames in file paths

        Also tracks which actual files match the query terms.

        Args:
            query: The user's research query
            file_index: File index mapping categories to file paths

        Returns:
            Tuple of (matched_terms, matched_files)
        """
        matched_terms = []
        matched_files = set()
        query_lower = query.lower()

        # Extract individual words and bigrams from query
        words = re.findall(r'\b\w+\b', query_lower)
        query_terms = set(words)

        # Generate bigrams (e.g., "task router" from "task", "router")
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i + 1]}"
            query_terms.add(bigram)

        # Build term-to-files mapping for tracking which files match
        # Maps lowercased term -> set of file paths containing that term
        term_to_files: dict[str, set] = {}

        # Add category names (file_index keys)
        for category, file_paths in file_index.items():
            category_lower = category.lower()
            if category_lower not in term_to_files:
                term_to_files[category_lower] = set()
            term_to_files[category_lower].update(file_paths)

        # Add directory names and file basenames from paths
        for file_paths in file_index.values():
            for file_path in file_paths:
                path_obj = Path(file_path)

                # Add directory names (e.g., "task_router" from "task_router/strategies")
                for part in path_obj.parts:
                    if part and part != '.':
                        part_lower = part.lower()
                        if part_lower not in term_to_files:
                            term_to_files[part_lower] = set()
                        term_to_files[part_lower].add(file_path)

                        # Also add version with underscores replaced by spaces
                        if '_' in part:
                            spaced = part.replace('_', ' ').lower()
                            if spaced not in term_to_files:
                                term_to_files[spaced] = set()
                            term_to_files[spaced].add(file_path)

                # Add file basename without extension
                if path_obj.stem:
                    stem_lower = path_obj.stem.lower()
                    if stem_lower not in term_to_files:
                        term_to_files[stem_lower] = set()
                    term_to_files[stem_lower].add(file_path)

                    if '_' in path_obj.stem:
                        spaced = path_obj.stem.replace('_', ' ').lower()
                        if spaced not in term_to_files:
                            term_to_files[spaced] = set()
                        term_to_files[spaced].add(file_path)

        # Find matches between query terms and project terms
        for query_term in query_terms:
            if query_term in term_to_files:
                matched_terms.append(query_term)
                matched_files.update(term_to_files[query_term])

        return matched_terms, sorted(matched_files)
