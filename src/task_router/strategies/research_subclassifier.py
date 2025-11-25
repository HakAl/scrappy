"""
Research query subclassification.

Determines whether a research query is about the codebase or general knowledge.
"""

import re
from typing import Optional, List, Pattern

from .research_subtype import ResearchSubtype


class ResearchSubclassifier:
    """
    Determines if a research query is about the codebase or general knowledge.

    Codebase indicators:
    - File paths, extensions (.py, .js, etc.)
    - Project-specific terms (from context summary)
    - Code references ("function", "class", "method", "variable")
    - Relative references ("this project", "our code", "the codebase")

    General knowledge indicators:
    - Named entities (people, places, historical events)
    - No file/code references
    - Historical or comparative questions about people/concepts
    - Questions about external tools/technologies not in the project
    """

    CODEBASE_PATTERNS: List[Pattern[str]] = [
        re.compile(r'\b(this|our|the)\s+(project|codebase|code|repo)\b', re.IGNORECASE),
        re.compile(r'\b(file|function|class|method|variable|module|package)\b', re.IGNORECASE),
        re.compile(r'[\w/\\]+\.(py|js|ts|jsx|tsx|java|cpp|go|rs|rb|php|swift|kt)\b', re.IGNORECASE),
        re.compile(r'\b(src|lib|test|tests|app|components?|utils?|helpers?)/\b', re.IGNORECASE),
        re.compile(r'\b(implement(ed|s|ation)?|defined?|declared?)\s+(in|here|above|below)\b', re.IGNORECASE),
        re.compile(r'\b(my|the)\s+(code|implementation|solution)\b', re.IGNORECASE),
        re.compile(r'\b(how\s+does\s+(this|the|my)|what\s+does\s+(this|the|my))\b', re.IGNORECASE),
        re.compile(r'\bwhere\s+is\s+(the|a|an)?\s*\w+\s*(logic|code|implemented|defined)\b', re.IGNORECASE),
    ]

    GENERAL_PATTERNS: List[Pattern[str]] = [
        re.compile(r'\b(who|which\s+person)\s+(is|was|were|invented|created|wrote)\b', re.IGNORECASE),
        re.compile(r'\b(history|historically|invented|created\s+by|founder|discovered)\b', re.IGNORECASE),
        re.compile(r'\b(best|worst|famous|greatest|most\s+influential)\b.*\b(programmer|coder|scientist|developer|person)\b', re.IGNORECASE),
        re.compile(r'\b(dijkstra|turing|knuth|ritchie|torvalds|gosling|stroustrup|van\s+rossum)\b', re.IGNORECASE),
        re.compile(r'\b(compare|comparison|versus|vs\.?|better|worse)\b.*\b(language|framework|tool)\b', re.IGNORECASE),
        re.compile(r'\bwhat\s+is\s+(a|an|the)\s+\w+\s*(pattern|algorithm|concept|theory|principle)\b', re.IGNORECASE),
        re.compile(r'\b(when\s+was|who\s+made|who\s+wrote|origin\s+of)\b', re.IGNORECASE),
    ]

    def classify(
        self,
        query: str,
        context_summary: Optional[str] = None
    ) -> ResearchSubtype:
        """
        Classify a research query as codebase or general knowledge.

        Args:
            query: The user's research query
            context_summary: Optional project context summary for better classification

        Returns:
            ResearchSubtype.CODEBASE or ResearchSubtype.GENERAL
        """
        codebase_score = self._score_codebase_indicators(query)
        general_score = self._score_general_indicators(query)

        if context_summary:
            codebase_score += self._score_context_matches(query, context_summary)

        if general_score > codebase_score:
            return ResearchSubtype.GENERAL
        elif codebase_score > 0:
            return ResearchSubtype.CODEBASE
        else:
            return ResearchSubtype.GENERAL

    def _score_codebase_indicators(self, query: str) -> int:
        """Count codebase indicator matches."""
        return sum(
            1 for pattern in self.CODEBASE_PATTERNS
            if pattern.search(query)
        )

    def _score_general_indicators(self, query: str) -> int:
        """Count general knowledge indicator matches."""
        return sum(
            1 for pattern in self.GENERAL_PATTERNS
            if pattern.search(query)
        )

    def _score_context_matches(self, query: str, context_summary: str) -> int:
        """
        Score matches against project context.

        Extracts key terms from the context summary and checks if they
        appear in the query.
        """
        key_terms = self._extract_key_terms(context_summary)
        query_lower = query.lower()
        return sum(1 for term in key_terms if term in query_lower)

    def _extract_key_terms(self, context_summary: str) -> List[str]:
        """
        Extract key terms from context summary.

        Looks for:
        - Module/class names (PascalCase)
        - Function names (snake_case)
        - File names
        """
        terms = []

        pascal_case = re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', context_summary)
        terms.extend(t.lower() for t in pascal_case)

        snake_case = re.findall(r'\b[a-z]+(?:_[a-z]+)+\b', context_summary)
        terms.extend(snake_case)

        file_names = re.findall(r'\b\w+\.(py|js|ts|java|go|rs)\b', context_summary)
        terms.extend(f[0].lower() for f in file_names if isinstance(f, tuple))

        return list(set(terms))
