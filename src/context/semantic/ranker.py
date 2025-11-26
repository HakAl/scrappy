"""
Search result ranking for semantic search.

Provides configurable ranking of search results based on multiple signals:
- Vector similarity (semantic relevance)
- Full-text search score (keyword matches)
- Exact match boost (query substring in content)
- Path match boost (query terms in file path)
"""

from typing import List, Optional, Set

from src.context.protocols import RankingConfig, ScoredChunk


class DefaultResultRanker:
    """
    Re-ranks search results with configurable weighted scoring.

    Scoring formula:
        final_score = (vector_score * vector_weight) +
                      (fts_score * fts_weight) +
                      exact_match_boost (if query substring found) +
                      path_match_boost (proportional to matching terms)

    This enables tuning the balance between semantic and keyword-based
    search, plus rewarding exact matches and relevant file paths.

    Implements ResultRankerProtocol.
    """

    def __init__(self, config: Optional[RankingConfig] = None):
        """
        Initialize result ranker.

        Args:
            config: Optional ranking configuration (uses defaults if None)
        """
        self._config = config or RankingConfig()

    def rank(
        self,
        query: str,
        candidates: List[ScoredChunk],
        config: Optional[RankingConfig] = None,
    ) -> List[ScoredChunk]:
        """
        Re-rank candidates based on multiple signals.

        Args:
            query: Original search query
            candidates: Raw results from search backend
            config: Optional ranking configuration (overrides instance config)

        Returns:
            Re-ranked list of chunks (highest score first)
        """
        if not candidates:
            return []

        cfg = config or self._config
        query_lower = query.lower()
        query_terms = self._extract_query_terms(query_lower)

        for chunk in candidates:
            chunk.final_score = self._compute_final_score(
                chunk=chunk,
                query_lower=query_lower,
                query_terms=query_terms,
                config=cfg,
            )

        # Sort by final score (descending - highest first)
        return sorted(candidates, key=lambda c: c.final_score, reverse=True)

    def _compute_final_score(
        self,
        chunk: ScoredChunk,
        query_lower: str,
        query_terms: Set[str],
        config: RankingConfig,
    ) -> float:
        """
        Compute final score for a single chunk.

        Args:
            chunk: The chunk to score
            query_lower: Lowercase query string
            query_terms: Set of query terms for path matching
            config: Ranking configuration

        Returns:
            Final computed score
        """
        # Base score from vector + FTS
        base_score = (
            chunk.vector_score * config.vector_weight +
            chunk.fts_score * config.fts_weight
        )

        # Exact match boost - query appears as substring in content
        exact_boost = 0.0
        if query_lower and query_lower in chunk.content.lower():
            exact_boost = config.exact_match_boost
            chunk.match_details["exact_match"] = True

        # Path match boost - query terms appear in file path
        path_boost = 0.0
        if query_terms:
            path_lower = chunk.file_path.lower()
            matching_terms = [term for term in query_terms if term in path_lower]
            if matching_terms:
                # Proportional boost based on matching term count
                path_boost = config.path_match_boost * (
                    len(matching_terms) / len(query_terms)
                )
                chunk.match_details["path_matches"] = matching_terms

        return base_score + exact_boost + path_boost

    def _extract_query_terms(self, query_lower: str) -> Set[str]:
        """
        Extract meaningful terms from query for path matching.

        Filters out very short terms (< 2 chars) that would match too broadly.

        Args:
            query_lower: Lowercase query string

        Returns:
            Set of query terms for matching
        """
        terms = set(query_lower.split())
        # Filter out terms that are too short to be meaningful
        return {term for term in terms if len(term) >= 2}


class PassthroughRanker:
    """
    No-op ranker that returns candidates unchanged.

    Useful for testing or when ranking is not needed.

    Implements ResultRankerProtocol.
    """

    def rank(
        self,
        query: str,
        candidates: List[ScoredChunk],
        config: Optional[RankingConfig] = None,
    ) -> List[ScoredChunk]:
        """
        Return candidates unchanged.

        Args:
            query: Original search query (ignored)
            candidates: Raw results from search backend
            config: Ranking configuration (ignored)

        Returns:
            Same list of chunks, unmodified
        """
        return candidates
