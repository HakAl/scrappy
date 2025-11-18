"""
Task classification for routing to appropriate execution strategies.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

from ..platform_utils import is_windows, validate_command_for_platform


class TaskType(Enum):
    """High-level task categories for execution routing."""
    DIRECT_COMMAND = "direct_command"      # Simple shell commands, no agent loop
    CODE_GENERATION = "code_generation"    # Full agent with planning and tools
    RESEARCH = "research"                  # Fast provider, lightweight research
    CONVERSATION = "conversation"          # Simple Q&A, no execution needed


@dataclass
class ClassifiedTask:
    """Result of task classification."""
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
    matched_patterns: List[str] = field(default_factory=list)
    extracted_files: List[str] = field(default_factory=list)  # File references found in input
    extracted_directories: List[str] = field(default_factory=list)  # Directory references found


class TaskClassifier:
    """
    Classifies user tasks into execution strategies.

    Priority order:
    1. DIRECT_COMMAND - Simple shell/system commands
    2. CODE_GENERATION - Writing/modifying code
    3. RESEARCH - Information gathering and analysis
    4. CONVERSATION - Simple Q&A
    """

    def __init__(self):
        self._init_patterns()

    def _init_patterns(self):
        """Initialize pattern matchers for each task type."""

        # Direct command patterns - shell commands that need no AI reasoning
        self.direct_command_patterns = [
            # Package managers
            (r'^(pip|pip3)\s+(install|uninstall|freeze|list|show)', 1.0, "pip_command"),
            (r'^npx\s+', 1.0, "npx_command"),  # npx can run any package, so match broadly
            (r'^(npm|yarn|pnpm)\s+(install|add|remove|run|build|test|start)', 1.0, "npm_command"),
            (r'^(cargo|rustup)\s+(install|build|run|test|add|remove)', 1.0, "cargo_command"),
            (r'^(gem|bundle)\s+(install|exec|update)', 1.0, "gem_command"),
            (r'^(go)\s+(get|build|run|test|mod)', 1.0, "go_command"),

            # Git commands
            (r'^git\s+(status|log|diff|branch|checkout|pull|push|add|commit|stash)', 1.0, "git_command"),
            (r'^git\s+\S+', 0.9, "git_generic"),

            # System commands
            (r'^(ls|dir|pwd|cd|mkdir|rmdir|rm|cp|mv|touch|cat|head|tail)\s*', 0.95, "filesystem_command"),
            (r'^(docker|docker-compose|podman)\s+\S+', 1.0, "docker_command"),
            (r'^(kubectl|k8s|helm)\s+\S+', 1.0, "kubernetes_command"),
            (r'^(python|python3|node|ruby|java|javac)\s+\S+', 0.9, "interpreter_command"),

            # Build/test commands
            # Negative lookahead to avoid matching "make a X" (which is create, not build)
            (r'^(make|cmake|gradle|mvn)(?!\s+a\s)\s*', 1.0, "build_command"),
            (r'^pytest\s*', 1.0, "test_command"),
            (r'^(tox|nox|coverage)\s*', 1.0, "test_command"),

            # Direct command request patterns
            (r'^run\s+(pip|npm|git|docker|pytest|make)\s+', 0.95, "run_explicit"),
            (r'^execute\s+', 0.9, "execute_explicit"),
            (r'^install\s+(\S+)', 0.85, "install_request"),
            (r'^(start|stop|restart)\s+\S+', 0.8, "service_control"),
        ]

        # Code generation patterns - requires full agent loop
        self.code_generation_patterns = [
            # Explicit code writing
            (r'\b(write|create|implement|build|develop|add)\s+.*(function|class|method|module|component|feature|endpoint|api|service)', 0.95, "write_code"),
            (r'\b(write|create|implement)\s+.*\.(py|js|ts|java|cpp|go|rs)\b', 0.9, "write_file"),
            (r'\brefactor\s+', 0.9, "refactor"),
            (r'\b(fix|patch|repair)\s+.*(bug|issue|error|problem)', 0.85, "fix_code"),
            (r'\b(fix|patch|repair)\s+.*(broken|failing|failed)', 0.85, "fix_broken"),
            (r'\badd\s+.*to\s+', 0.75, "add_feature"),
            (r'\bmodify\s+', 0.8, "modify_code"),
            (r'\bupdate\s+.*(code|function|class|implementation)', 0.85, "update_code"),
            (r'\bchange\s+.*(implementation|behavior|logic)', 0.8, "change_code"),

            # File creation patterns (any file type, not just code)
            (r'\b(create|generate|write)\s+[\w\-]+\.\w+\b', 0.85, "create_any_file"),
            (r'\b(create|generate)\s+(requirements|package\.json|setup\.py|config|\.gitignore|\.env|Makefile|Dockerfile)', 0.9, "create_config_file"),
            (r'^please\s+(create|make|write|generate|add|build)\b', 0.8, "polite_action"),
            # Match create/make/write commands - removed list from exclusions since we want to create lists too
            (r'^(create|make|write|generate)\s+', 0.9, "imperative_action"),

            # Multi-step tasks
            (r'\bthen\s+', 0.7, "multi_step"),
            (r'\bafter\s+that\s+', 0.7, "multi_step"),
            (r'\bfirst\s+.*then\s+', 0.85, "explicit_multi_step"),
            (r'\bstep\s*\d+', 0.8, "numbered_steps"),

            # Complex operations
            (r'\b(integrate|connect|wire up|hook up)\s+', 0.85, "integration"),
            (r'\b(migrate|upgrade|convert)\s+', 0.8, "migration"),
            (r'\b(test|unit test|integration test).*and\s+(fix|update)', 0.9, "test_and_fix"),
            (r'\bmake sure.*(works|passes|compiles)', 0.75, "verify_task"),
        ]

        # Research patterns - fast provider, no file modifications
        self.research_patterns = [
            # Questions
            (r'^(what|where|why|how|when|which|who)\s+', 0.8, "question"),
            (r'\?$', 0.6, "question_mark"),

            # Explanation requests (higher weight to win over create/write actions)
            (r'\b(explain|describe|tell me about|what is|what are)\s+', 1.0, "explanation"),
            (r'\bhow does\s+.*work', 1.0, "how_works"),
            (r'\bwhat does\s+.*do', 1.0, "what_does"),
            (r'\bhow to\s+', 0.95, "how_to"),

            # Analysis requests
            (r'\b(analyze|review|check|examine|inspect|look at)\s+', 0.8, "analysis"),
            (r'\b(find|search|locate|show me)\s+', 0.75, "search"),
            # Lower priority for listing to allow create/make/write actions to win
            (r'\b(list|enumerate|summarize|overview)\s+', 0.7, "listing"),

            # Information gathering
            (r'\b(understand|learn about|tell me)\s+', 0.85, "information"),
            (r'\bwhat.*architecture', 0.9, "architecture_question"),
            (r'\bwhat.*structure', 0.85, "structure_question"),
            (r'\bhow.*organized', 0.85, "organization_question"),

            # Reading/viewing
            (r'\b(read|view|see|show)\s+.*file', 0.75, "read_file"),
            (r'\bwhat.*contains', 0.8, "contents_question"),
        ]

        # Conversation patterns - simple responses
        self.conversation_patterns = [
            (r'^(hi|hello|hey|greetings|good morning|good afternoon)', 1.0, "greeting"),
            (r'^(thanks|thank you|thx)', 1.0, "thanks"),
            (r'^(yes|no|ok|okay|sure|fine|alright)', 0.9, "acknowledgment"),
            (r'^(help|what can you do|capabilities)', 0.85, "help_request"),
            (r'^bye|goodbye|exit|quit', 1.0, "farewell"),
        ]

    def classify(self, user_input: str) -> ClassifiedTask:
        """
        Classify user input into appropriate task type.

        Returns ClassifiedTask with type, confidence, and metadata.
        """
        input_stripped = user_input.strip()
        input_lower = input_stripped.lower()

        # Track all matches
        scores: Dict[TaskType, float] = {t: 0.0 for t in TaskType}
        matched: Dict[TaskType, List[str]] = {t: [] for t in TaskType}
        extracted_cmd: Optional[str] = None

        # 1. Check for direct commands first (highest priority for simple tasks)
        for pattern, weight, name in self.direct_command_patterns:
            match = re.search(pattern, input_lower, re.IGNORECASE)
            if match:
                scores[TaskType.DIRECT_COMMAND] += weight
                matched[TaskType.DIRECT_COMMAND].append(name)
                if not extracted_cmd:
                    extracted_cmd = input_stripped

        # 2. Check for code generation patterns
        for pattern, weight, name in self.code_generation_patterns:
            if re.search(pattern, input_lower, re.IGNORECASE):
                scores[TaskType.CODE_GENERATION] += weight
                matched[TaskType.CODE_GENERATION].append(name)

        # 3. Check for research patterns
        for pattern, weight, name in self.research_patterns:
            if re.search(pattern, input_lower, re.IGNORECASE):
                scores[TaskType.RESEARCH] += weight
                matched[TaskType.RESEARCH].append(name)

        # 4. Check for conversation patterns
        for pattern, weight, name in self.conversation_patterns:
            if re.search(pattern, input_lower, re.IGNORECASE):
                scores[TaskType.CONVERSATION] += weight
                matched[TaskType.CONVERSATION].append(name)

        # Normalize scores
        for task_type in scores:
            if scores[task_type] > 0:
                # Cap at 1.0 but consider multiple matches boost confidence
                scores[task_type] = min(scores[task_type], 1.0)

        # Determine winning task type
        best_type = max(scores.keys(), key=lambda t: scores[t])
        best_score = scores[best_type]

        # If no patterns matched, default to research (safest)
        if best_score == 0:
            best_type = TaskType.RESEARCH
            best_score = 0.5
            reasoning = "No specific patterns matched, defaulting to research"
        else:
            reasoning = self._generate_reasoning(best_type, matched[best_type])

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
            matched_patterns=matched[best_type],
            extracted_files=extracted_files,
            extracted_directories=extracted_dirs
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
        complexity += min(multi_step_count, 2)

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

        # Find all file references
        for match in re.finditer(file_ext_pattern, input_text, re.IGNORECASE):
            file_ref = match.group(1)
            # Normalize path separators
            file_ref = file_ref.replace('\\', '/')
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
