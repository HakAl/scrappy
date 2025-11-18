"""Code generation classification strategy."""

from typing import List

from ..classification_strategy import PatternBasedStrategy, TaskType


class CodeGenerationStrategy(PatternBasedStrategy):
    """
    Strategy for identifying code generation tasks.

    Matches requests to write, modify, or create code and files.
    Requires full agent loop with planning and tools.
    """

    def task_type(self) -> TaskType:
        """Return CODE_GENERATION task type."""
        return TaskType.CODE_GENERATION

    def _init_patterns(self) -> None:
        """Initialize code generation patterns."""
        # Explicit code writing
        self.add_patterns([
            (r'\b(write|create|implement|build|develop|add)\s+.*(function|class|method|module|component|feature|endpoint|api|service)', 0.95, "write_code"),
            (r'\b(write|create|implement)\s+.*\.(py|js|ts|java|cpp|go|rs)\b', 0.9, "write_file"),
            (r'\brefactor\b', 0.9, "refactor"),  # Match word boundary, not requiring space
            (r'\b(fix|patch|repair)\s+.*(bug|issue|error|problem)', 0.85, "fix_code"),
            (r'\b(fix|patch|repair)\s+.*(broken|failing|failed)', 0.85, "fix_broken"),
            (r'\badd\s+.*to\s+', 0.75, "add_feature"),
            (r'\bmodify\s+', 0.8, "modify_code"),
            (r'\bupdate\s+.*(code|function|class|implementation)', 0.85, "update_code"),
            (r'\bchange\s+.*(implementation|behavior|logic)', 0.8, "change_code"),
        ])

        # File creation patterns
        self.add_patterns([
            (r'\b(create|generate|write)\s+[\w\-]+\.\w+\b', 0.85, "create_any_file"),
            (r'\b(create|generate)\s+(requirements|package\.json|setup\.py|config|\.gitignore|\.env|Makefile|Dockerfile)', 0.9, "create_config_file"),
            (r'^please\s+(create|make|write|generate|add|build)\b', 0.8, "polite_action"),
            (r'^(create|make|write|generate)\s+', 0.9, "imperative_action"),
        ])

        # Multi-step tasks
        self.add_patterns([
            (r'\bthen\s+', 0.7, "multi_step"),
            (r'\bafter\s+that\s+', 0.7, "multi_step"),
            (r'\bfirst\s+.*then\s+', 0.85, "explicit_multi_step"),
            (r'\bstep\s*\d+', 0.8, "numbered_steps"),
        ])

        # Complex operations
        self.add_patterns([
            (r'\b(integrate|connect|wire up|hook up)\s+', 0.85, "integration"),
            (r'\b(migrate|upgrade|convert)\s+', 0.8, "migration"),
            (r'\b(test|unit test|integration test).*and\s+(fix|update)', 0.9, "test_and_fix"),
            (r'\bmake sure.*(works|passes|compiles)', 0.75, "verify_task"),
        ])

    def _generate_reasoning(self, patterns: List[str]) -> str:
        """Generate reasoning for code generation classification."""
        if not patterns:
            return ""
        pattern_str = ", ".join(patterns[:3])
        return f"Requires code writing/modification: {pattern_str}"
