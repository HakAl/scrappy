"""Conversation classification strategy."""

from typing import List

from ..classification_strategy import PatternBasedStrategy, TaskType


class ConversationStrategy(PatternBasedStrategy):
    """
    Strategy for identifying conversational interactions.

    Matches greetings, acknowledgments, thanks, and other simple
    conversational responses that don't require task execution.
    """

    def task_type(self) -> TaskType:
        """Return CONVERSATION task type."""
        return TaskType.CONVERSATION

    def _init_patterns(self) -> None:
        """Initialize conversation patterns."""
        self.add_patterns([
            (r'^(hi|hello|hey|greetings|good morning|good afternoon)', 1.0, "greeting"),
            (r'^(thanks|thank you|thx)', 1.0, "thanks"),
            (r'^(yes|no|ok|okay|sure|fine|alright)', 0.9, "acknowledgment"),
            (r'^(help|what can you do|capabilities)', 0.85, "help_request"),
            (r'^bye|goodbye|exit|quit', 1.0, "farewell"),
        ])

    def _generate_reasoning(self, patterns: List[str]) -> str:
        """Generate reasoning for conversation classification."""
        if not patterns:
            return ""
        pattern_str = ", ".join(patterns[:3])
        return f"Simple conversation: {pattern_str}"
