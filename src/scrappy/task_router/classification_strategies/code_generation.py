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

        # File creation patterns - require specific file extensions or config names
        self.add_patterns([
            # Specific source file extensions (not just any .ext)
            (r'\b(create|generate|write)\s+[\w\-/\\]+\.(py|js|ts|tsx|jsx|java|cpp|c|h|go|rs|rb|php|html|css|scss|json|yaml|yml|xml|sql|sh|bat|ps1|md)\b', 0.9, "create_source_file"),
            # Config/project files by name (allow optional article: "create a requirements.txt")
            (r'\b(create|generate)\s+(?:an?\s+)?(requirements\.txt|package\.json|setup\.py|config|\.gitignore|\.env|Makefile|Dockerfile|docker-compose)', 0.9, "create_config_file"),
            # Polite request with code-specific object (not just "create X")
            (r'^please\s+(create|make|write|generate|add|build)\s+.*(file|script|code|function|class|module|component|api|app)', 0.8, "polite_code_action"),
            # Imperative only with code-specific objects (avoid "create a story")
            (r'^(create|make|write|generate)\s+.*(file|script|code|function|class|module|component|api|app|endpoint|service|tool|utility)', 0.85, "imperative_code_action"),
            # Generic imperative with data/code structures (not creative writing)
            # Matches: "create a list", "make the schema", "create database"
            (r'^(create|make|write|generate)\s+(?:a\s+|the\s+|an\s+)?(list|array|dict|dictionary|set|map|hash|table|schema|database|db|config|structure|handler|manager|wrapper|interface|index|cache|queue|stack|buffer|tree|graph|collection)\b', 0.8, "imperative_data_object"),
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

        # Short follow-up with action verb + pronoun (reasonably safe)
        # "update it", "fix it", "do it" - the verb provides intent signal
        # Note: Bare affirmatives like "yes/ok" are NOT safe without conversation
        # context - they could confirm anything (chat, search, etc.)
        self.add_patterns([
            (r'^(update|fix|create|make|write|add|remove|delete|change|modify|edit)\s+it\.?$', 0.85, "action_pronoun"),
            (r'^(update|fix|create|make)\s+that\.?$', 0.85, "action_pronoun"),
            (r'^do\s+it\.?$', 0.8, "do_it"),  # Slightly lower - more ambiguous
            # NOT including: yes/ok/go ahead - these need conversation context
            # NOT including: 1/2 option selection - needs context of what options were
        ])

    def _generate_reasoning(self, patterns: List[str]) -> str:
        """Generate reasoning for code generation classification."""
        if not patterns:
            return ""
        pattern_str = ", ".join(patterns[:3])
        return f"Requires code writing/modification: {pattern_str}"
