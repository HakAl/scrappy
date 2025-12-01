"""Research classification strategy."""

from typing import List

from ..classification_strategy import PatternBasedStrategy, TaskType


class ResearchStrategy(PatternBasedStrategy):
    """
    Strategy for identifying research and information gathering tasks.

    Matches questions, explanation requests, and analysis tasks.
    Uses fast provider for lightweight research.
    """

    def task_type(self) -> TaskType:
        """Return RESEARCH task type."""
        return TaskType.RESEARCH

    def _init_patterns(self) -> None:
        """Initialize research patterns."""
        # Questions
        self.add_patterns([
            (r'^(what|where|why|how|when|which|who)\s+', 0.8, "question"),
            (r'\?$', 0.6, "question_mark"),
        ])

        # Explanation requests (higher weight to win over create/write)
        self.add_patterns([
            (r'\b(explain|describe|tell me about|what is|what are)\s+', 1.0, "explanation"),
            (r'\bhow does\s+.*work', 1.0, "how_works"),
            (r'\bwhat does\s+.*do', 1.0, "what_does"),
            (r'\bhow to\s+', 0.95, "how_to"),
        ])

        # Analysis requests
        self.add_patterns([
            (r'\b(analyze|review|check|examine|inspect|look at)\s+', 0.8, "analysis"),
            (r'\b(find|search|locate|show me)\s+', 0.75, "search"),
            (r'\b(list|enumerate|summarize|overview)\s+', 0.7, "listing"),
        ])

        # Information gathering
        self.add_patterns([
            (r'\b(understand|learn about|tell me)\s+', 0.85, "information"),
            (r'\bwhat.*architecture', 0.9, "architecture_question"),
            (r'\bwhat.*structure', 0.85, "structure_question"),
            (r'\bhow.*organized', 0.85, "organization_question"),
        ])

        # Reading/viewing
        self.add_patterns([
            (r'\b(read|view|see|show)\s+.*file', 0.75, "read_file"),
            (r'\bwhat.*contains', 0.8, "contents_question"),
        ])

    def _generate_reasoning(self, patterns: List[str]) -> str:
        """Generate reasoning for research classification."""
        if not patterns:
            return ""
        pattern_str = ", ".join(patterns[:3])
        return f"Information gathering task: {pattern_str}"
