"""
Task classification for routing to appropriate execution strategies.

Refactored to use Strategy Pattern for better maintainability and extensibility.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from ..platform_utils import is_windows, validate_command_for_platform
from .classification_strategy import TaskType
from .classification_strategies import (
    DirectCommandStrategy,
    CodeGenerationStrategy,
    ResearchStrategy,
    ConversationStrategy,
)


@dataclass(frozen=True)
class ClassifiedTask:
    """Result of task classification (immutable)."""
    original_input: str
    task_type: TaskType
    confidence: float  # 0.0 to 1.0
    reasoning: str
    extracted_command: Optional[str] = None  # For DIRECT_COMMAND
    suggested_provider: Optional[str] = None  # Provider hint (from classifier)
    override_provider: Optional[str] = None  # Manual provider override (takes precedence)
    complexity_score: int = 1  # 1-10 scale
    requires_planning: bool = False
    requires_tools: bool = False
    matched_patterns: Tuple[str, ...] = ()  # Patterns that matched (immutable)
    extracted_files: Tuple[str, ...] = ()  # File references found in input (immutable)
    extracted_directories: Tuple[str, ...] = ()  # Directory references found (immutable)


class TaskClassifier:
    """
    Classifies user tasks into execution strategies using Strategy Pattern.

    Uses pluggable classification strategies for better maintainability.
    Each strategy encapsulates patterns for one task type.

    Priority order:
    1. DIRECT_COMMAND - Simple shell/system commands
    2. CODE_GENERATION - Writing/modifying code
    3. RESEARCH - Information gathering and analysis
    4. CONVERSATION - Simple Q&A
    """

    def __init__(self, strategies: Optional[List] = None):
        """
        Initialize classifier with strategies.

        Args:
            strategies: Optional list of custom strategies to use.
                       If None, uses default strategies.
        """
        if strategies is None:
            self.strategies = [
                DirectCommandStrategy(),
                CodeGenerationStrategy(),
                ResearchStrategy(),
                ConversationStrategy(),
            ]
        else:
            self.strategies = strategies

        # Keep backward compatibility by initializing pattern lists
        self._init_patterns()

    def _init_patterns(self):
        """
        Initialize pattern lists for backward compatibility.

        These are now populated from strategies but kept for any code
        that might reference them directly.
        """
        # Populate pattern lists from strategies for backward compatibility
        self.direct_command_patterns = []
        self.code_generation_patterns = []
        self.research_patterns = []
        self.conversation_patterns = []

        for strategy in self.strategies:
            task_type = strategy.task_type()
            if task_type == TaskType.DIRECT_COMMAND:
                self.direct_command_patterns = strategy.patterns
            elif task_type == TaskType.CODE_GENERATION:
                self.code_generation_patterns = strategy.patterns
            elif task_type == TaskType.RESEARCH:
                self.research_patterns = strategy.patterns
            elif task_type == TaskType.CONVERSATION:
                self.conversation_patterns = strategy.patterns

    def classify(self, user_input: str) -> ClassifiedTask:
        """
        Classify user input using pluggable strategies.

        Each strategy evaluates the input and returns a score.
        The strategy with the highest score determines the task type.

        Returns ClassifiedTask with type, confidence, and metadata.
        """
        input_stripped = user_input.strip()

        # Evaluate input with all strategies
        results = {}
        for strategy in self.strategies:
            result = strategy.evaluate(input_stripped)
            results[strategy.task_type()] = result

        # Find best match
        best_type = max(results.keys(), key=lambda t: results[t].confidence)
        best_result = results[best_type]

        # If no patterns matched, default to research (safest)
        if best_result.confidence == 0:
            best_type = TaskType.RESEARCH
            best_score = 0.5
            reasoning = "No specific patterns matched, defaulting to research"
            matched = []
            extracted_cmd = None
        else:
            best_score = best_result.confidence
            reasoning = best_result.reasoning
            matched = best_result.matched_patterns
            extracted_cmd = best_result.extracted_command

        # Calculate complexity
        complexity = self._calculate_complexity(input_stripped, best_type)

        # Determine if planning/tools are needed
        requires_planning = best_type == TaskType.CODE_GENERATION and complexity >= 7
        requires_tools = best_type in [TaskType.CODE_GENERATION, TaskType.RESEARCH]

        # Suggest provider based on task type
        suggested_provider = self._suggest_provider(best_type, complexity)

        # Override to quality provider if task requires codebase analysis
        if best_type == TaskType.CODE_GENERATION and self._requires_analysis(input_stripped):
            suggested_provider = "quality"
            reasoning += " [Requires codebase analysis - using quality provider]"

        # Extract file and directory references
        extracted_files, extracted_dirs = self._extract_file_references(input_stripped)

        return ClassifiedTask(
            original_input=input_stripped,
            task_type=best_type,
            confidence=best_score,
            reasoning=reasoning,
            extracted_command=extracted_cmd if best_type == TaskType.DIRECT_COMMAND else None,
            suggested_provider=suggested_provider,
            complexity_score=complexity,
            requires_planning=requires_planning,
            requires_tools=requires_tools,
            matched_patterns=tuple(matched),
            extracted_files=tuple(extracted_files),
            extracted_directories=tuple(extracted_dirs)
        )

    def _generate_reasoning(self, task_type: TaskType, patterns: List[str]) -> str:
        """Generate human-readable reasoning for classification."""
        pattern_str = ", ".join(patterns[:3])

        reasons = {
            TaskType.DIRECT_COMMAND: f"Detected direct command patterns: {pattern_str}",
            TaskType.CODE_GENERATION: f"Requires code writing/modification: {pattern_str}",
            TaskType.RESEARCH: f"Information gathering task: {pattern_str}",
            TaskType.CONVERSATION: f"Simple conversation: {pattern_str}",
        }

        return reasons.get(task_type, f"Matched patterns: {pattern_str}")

    def _calculate_complexity(self, input_text: str, task_type: TaskType) -> int:
        """
        Calculate task complexity on 1-10 scale.

        Factors:
        - Length of input
        - Number of distinct actions
        - Presence of conditional logic
        - Multi-step indicators
        """
        complexity = 1

        # Base complexity by type
        # Base complexity by type (lowered to avoid over-planning)
        type_base = {
            TaskType.DIRECT_COMMAND: 1,
            TaskType.CONVERSATION: 1,
            TaskType.RESEARCH: 2,
            TaskType.CODE_GENERATION: 3,  # Simple file ops shouldn't be complex
        }
        complexity = type_base.get(task_type, 3)

        # Length factor
        word_count = len(input_text.split())
        if word_count > 50:
            complexity += 2
        elif word_count > 20:
            complexity += 1

        # Multi-step indicators
        multi_step_keywords = ['then', 'after that', 'next', 'and then', 'finally', 'first', 'second']
        multi_step_count = sum(1 for keyword in multi_step_keywords if keyword in input_text.lower())
        # Give higher bonus for multi-step tasks (at least +2 if any multi-step detected)
        if multi_step_count > 0:
            complexity += min(multi_step_count + 1, 3)

        # Action count (only boost for 3+ distinct actions)
        action_words = ['create', 'write', 'update', 'modify', 'delete', 'add', 'remove', 'fix', 'refactor', 'test', 'implement']
        action_count = sum(1 for word in action_words if word in input_text.lower())
        if action_count >= 3:
            complexity += action_count - 1

        # High complexity indicators
        if any(word in input_text.lower() for word in ['multiple', 'several', 'all files', 'each']):
            complexity += 2
        if any(word in input_text.lower() for word in ['refactor', 'redesign', 'migrate', 'integrate']):
            complexity += 2

        return min(complexity, 10)

    def _suggest_provider(self, task_type: TaskType, complexity: int) -> Optional[str]:
        """
        Suggest optimal provider for task type.

        Returns provider hint that can be resolved by ProviderSelector:
        - "fast": Quick response (Cerebras/Groq)
        - "quality": High quality (70B models)
        - None: No LLM needed
        """
        if task_type == TaskType.DIRECT_COMMAND:
            return None  # No LLM needed

        if task_type == TaskType.CONVERSATION:
            return "fast"  # Quick responses

        if task_type == TaskType.RESEARCH:
            return "fast"  # Fast provider for research

        if task_type == TaskType.CODE_GENERATION:
            if complexity >= 7:
                return "quality"  # 70B model for complex tasks
            else:
                return "fast"  # 8B model for simpler code tasks

        return "fast"

    def _requires_analysis(self, input_text: str) -> bool:
        """
        Check if task requires codebase analysis, warranting a quality provider.

        Some tasks look simple but require intelligent analysis of the codebase.
        """
        input_lower = input_text.lower()

        # Tasks that require analyzing project structure
        analysis_patterns = [
            ('requirements', 'create'),  # Need to analyze imports
            ('requirements', 'generate'),
            ('dockerfile', 'create'),  # Need to analyze project structure
            ('package.json', 'create'),  # Need to analyze dependencies
            ('.gitignore', 'create'),  # Need to analyze file types
            ('refactor', ''),  # Any refactoring requires understanding
            ('migrate', ''),  # Migration requires analysis
        ]

        for pattern in analysis_patterns:
            if all(word in input_lower for word in pattern if word):
                return True

        return False

    def _extract_file_references(self, input_text: str) -> tuple[List[str], List[str]]:
        """
        Extract file and directory references from user input.

        Returns:
            Tuple of (file_references, directory_references)
        """
        files = []
        directories = []

        # Common file extensions
        file_ext_pattern = r'\b([\w\-./\\]+\.(?:js|jsx|ts|tsx|py|java|cpp|c|h|hpp|rs|go|rb|php|css|scss|html|json|yaml|yml|xml|md|txt|sql|sh|bat|ps1|toml|ini|conf|env))\b'

        # Dotfiles pattern (files starting with dot)
        dotfile_pattern = r'(?:^|\s)(\.(?:gitignore|env|dockerignore|editorconfig|eslintrc|prettierrc|babelrc|npmrc|gitattributes))\b'

        # Find all file references
        for match in re.finditer(file_ext_pattern, input_text, re.IGNORECASE):
            file_ref = match.group(1)
            # Normalize path separators
            file_ref = file_ref.replace('\\', '/')
            if file_ref not in files:
                files.append(file_ref)

        # Find dotfiles
        for match in re.finditer(dotfile_pattern, input_text, re.IGNORECASE):
            file_ref = match.group(1)
            if file_ref not in files:
                files.append(file_ref)

        # Extract directory references
        # Common directory names in projects
        dir_patterns = [
            r'\b(frontend|backend|src|lib|test|tests|app|components?|pages?|views?|controllers?|models?|services?|utils?|helpers?|config|public|static|dist|build|node_modules)/?\b',
            r'\b([\w\-]+)/\b',  # Simple path-like pattern
        ]

        for pattern in dir_patterns:
            for match in re.finditer(pattern, input_text, re.IGNORECASE):
                dir_ref = match.group(1).rstrip('/')
                if dir_ref not in directories and dir_ref.lower() not in ['a', 'i', 'the', 'to', 'of', 'in', 'on', 'at']:
                    directories.append(dir_ref)

        return files, directories

    def is_safe_command(self, command: str) -> bool:
        """
        Check if a direct command is safe to execute.

        Blocks potentially dangerous commands and validates platform compatibility.
        """
        # First check platform compatibility
        is_valid, warning = validate_command_for_platform(command)
        if not is_valid:
            # Command is not valid for this platform
            return False

        dangerous_patterns = [
            r'\brm\s+-rf\s+[/~]',  # rm -rf on root or home
            r'\brm\s+-rf\s+\*',    # rm -rf *
            r'\bsudo\s+rm\b',      # sudo rm
            r'\bformat\b',         # format
            r'\bdd\s+if=',         # dd command
            r'\bmkfs\b',           # make filesystem
            r':\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;',  # fork bomb - flexible spacing
            r'\bchmod\s+-r\s+777\s+/',  # chmod 777 on root (lowercase after .lower())
            r'>\s*/dev/sd',        # write to disk
            r'\bwget.*\|\s*bash',  # download and execute
            r'\bcurl.*\|\s*bash',  # download and execute
        ]

        # Add Windows-specific dangerous patterns
        if is_windows():
            dangerous_patterns.extend([
                r'\bdel\s+/[fqs].*[/\\]\*',  # del /f /s with wildcards
                r'\brmdir\s+/s\s+/q\s+[a-zA-Z]:\\',  # rmdir /s /q on drive root
                r'\bformat\s+[a-zA-Z]:',  # format drive
                r'\breg\s+delete\b',  # registry deletion
                r'\bdiskpart\b',  # disk partitioning
            ])

        cmd_lower = command.lower()
        for pattern in dangerous_patterns:
            if re.search(pattern, cmd_lower):
                return False

        return True
