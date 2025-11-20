"""
Regex-based intent classifier.

Implements intent classification using pattern matching with weighted scores.
"""

import re
from typing import Dict, List, Tuple, Optional
from ..protocols import (
    IntentClassifierProtocol,
    IntentResult,
    QueryIntent,
)
from .patterns import INTENT_PATTERNS


class RegexIntentClassifier(IntentClassifierProtocol):
    """
    Regex-based intent classifier.

    Classifies user queries by matching against predefined regex patterns
    with weighted scoring. Each pattern contributes to an overall confidence
    score for its associated intent.

    Dependencies:
    - patterns: Dictionary mapping intents to (pattern, weight) tuples

    Example:
        classifier = RegexIntentClassifier()
        result = classifier.classify("show me the file structure")
        assert result.intent == QueryIntent.FILE_STRUCTURE
        assert result.confidence > 0.5
    """

    def __init__(
        self,
        patterns: Optional[Dict[QueryIntent, List[Tuple[str, float]]]] = None,
    ):
        """
        Initialize classifier with patterns.

        Args:
            patterns: Optional custom patterns. Defaults to INTENT_PATTERNS.
        """
        self.patterns = patterns if patterns is not None else INTENT_PATTERNS

    def classify(self, query: str) -> IntentResult:
        """
        Classifies a query into an intent with confidence score.

        Algorithm:
        1. Convert query to lowercase for case-insensitive matching
        2. For each intent, sum weights of all matching patterns
        3. Normalize score to 0.0-1.0 range
        4. Return intent with highest confidence, or GENERAL if none match

        Args:
            query: User's query string

        Returns:
            IntentResult containing:
            - intent: Classified intent enum
            - confidence: Confidence score (0.0 to 1.0)
            - metadata: Dict with 'matched_patterns' list
        """
        if not query:
            return IntentResult(
                intent=QueryIntent.GENERAL,
                confidence=0.5,
                metadata={'matched_patterns': []}
            )

        query_lower = query.lower()
        best_score = 0.0
        best_intent = QueryIntent.GENERAL
        best_matched = []

        for intent, patterns in self.patterns.items():
            score = 0.0
            matched = []

            for pattern, weight in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    score += weight
                    matched.append(pattern)

            if score > 0:
                confidence = self._normalize_score(score, len(patterns))

                if confidence > best_score:
                    best_score = confidence
                    best_intent = intent
                    best_matched = matched

        if best_score == 0.0:
            best_score = 0.5

        return IntentResult(
            intent=best_intent,
            confidence=best_score,
            metadata={'matched_patterns': best_matched}
        )

    def _normalize_score(self, score: float, pattern_count: int) -> float:
        """
        Normalize raw score to 0.0-1.0 range.

        Uses a formula that considers both the raw score and the number
        of patterns, allowing for high confidence even with few pattern matches.

        Args:
            score: Raw score (sum of pattern weights)
            pattern_count: Total number of patterns for this intent

        Returns:
            Normalized confidence score (0.0 to 1.0)
        """
        if pattern_count == 0:
            return 0.0

        return min(score / pattern_count * 2, 1.0)
