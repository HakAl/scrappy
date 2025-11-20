"""
Intent classification for user queries.
Provides structured intent detection with confidence scoring and entity extraction.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Set


class QueryIntent(Enum):
    """Types of user query intents."""
    FILE_STRUCTURE = "file_structure"
    CODE_SEARCH = "code_search"
    CODE_EXPLANATION = "code_explanation"
    GIT_HISTORY = "git_history"
    DEPENDENCY_INFO = "dependency_info"
    ARCHITECTURE = "architecture"
    BUG_INVESTIGATION = "bug_investigation"
    TESTING = "testing"
    PERFORMANCE = "performance"
    DOCUMENTATION = "documentation"
    REFACTORING = "refactoring"
    SECURITY = "security"
    CONFIGURATION = "configuration"
    GENERAL = "general"


@dataclass
class IntentMatch:
    """Represents a matched intent with confidence and metadata."""
    intent: QueryIntent
    confidence: float  # 0.0 to 1.0
    matched_patterns: List[str] = field(default_factory=list)
    extracted_entities: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class ClassificationResult:
    """Complete classification result for a query."""
    query: str
    primary_intent: IntentMatch
    secondary_intents: List[IntentMatch] = field(default_factory=list)
    entities: Dict[str, List[str]] = field(default_factory=dict)
    keywords: List[str] = field(default_factory=list)

    @property
    def all_intents(self) -> List[IntentMatch]:
        """Get all intents sorted by confidence."""
        return sorted(
            [self.primary_intent] + self.secondary_intents,
            key=lambda x: x.confidence,
            reverse=True
        )


class IntentClassifier:
    """Enhanced intent classifier with pattern matching and entity extraction."""

    def __init__(self):
        self._init_patterns()
        self._init_entity_patterns()

    def _init_patterns(self):
        """Initialize intent detection patterns."""
        # Each pattern has: (regex_pattern, weight)
        # Higher weight = stronger signal
        self.intent_patterns: Dict[QueryIntent, List[tuple]] = {
            QueryIntent.FILE_STRUCTURE: [
                (r'\b(file|folder|directory|dir)\b', 0.6),
                (r'\b(structure|tree|layout|hierarchy)\b', 0.7),
                (r'\bwhat files\b', 0.9),
                (r'\bshow me (the )?(files|folders|directories)\b', 0.9),
                (r'\blist (all )?(files|modules|packages)\b', 0.8),
                (r'\bwhere (is|are) .+ (located|stored|defined)\b', 0.7),
                (r'\bfind (file|module|package)\b', 0.8),
                (r'\b(project|codebase) (structure|layout|organization)\b', 0.9),
            ],
            QueryIntent.CODE_SEARCH: [
                (r'\b(function|method|class|interface|type)\b', 0.6),
                (r'\bwhere is .+ (defined|implemented|declared)\b', 0.9),
                (r'\bfind (the )?(definition|implementation|usage)\b', 0.9),
                (r'\bsearch for\b', 0.7),
                (r'\bwhich (file|module) (contains|has|defines)\b', 0.8),
                (r'\bgrep\b', 0.8),
                (r'\blook for\b', 0.6),
                (r'\blocate\b', 0.7),
            ],
            QueryIntent.CODE_EXPLANATION: [
                (r'\bhow does .+ work\b', 0.9),
                (r'\bwhat does .+ do\b', 0.9),
                (r'\bexplain (how|what|why)\b', 0.9),
                (r'\bunderstand\b', 0.6),
                (r'\bpurpose of\b', 0.8),
                (r'\bwhy (is|does|do)\b', 0.7),
                (r'\bwalk me through\b', 0.9),
                (r'\bcan you explain\b', 0.8),
                (r'\bhow (is|are) .+ (used|called|invoked)\b', 0.8),
            ],
            QueryIntent.GIT_HISTORY: [
                (r'\b(commit|commits)\b', 0.8),
                (r'\b(git|version control)\b', 0.7),
                (r'\b(recent|latest) (changes|updates|modifications)\b', 0.9),
                (r'\bhistory\b', 0.7),
                (r'\bwhat changed\b', 0.9),
                (r'\bwho (changed|modified|wrote)\b', 0.8),
                (r'\bwhen (was|did) .+ (changed|modified|added)\b', 0.8),
                (r'\bblame\b', 0.9),
                (r'\bdiff\b', 0.8),
                (r'\bbranch(es)?\b', 0.7),
            ],
            QueryIntent.DEPENDENCY_INFO: [
                (r'\b(dependency|dependencies)\b', 0.9),
                (r'\b(package|packages|module|modules)\b', 0.6),
                (r'\b(require|requirements|install)\b', 0.8),
                (r'\bimport(s|ed|ing)?\b', 0.6),
                (r'\b(version|versions)\b', 0.7),
                (r'\bwhat (does|do) .+ (use|depend on|require)\b', 0.8),
                (r'\bpip\b', 0.7),
                (r'\bnpm\b', 0.7),
                (r'\bpackage\.json\b', 0.9),
                (r'\brequirements\.txt\b', 0.9),
            ],
            QueryIntent.ARCHITECTURE: [
                (r'\barchitecture\b', 0.9),
                (r'\bdesign (pattern|patterns)\b', 0.9),
                (r'\b(organize|organization|organized)\b', 0.7),
                (r'\bhow (is|are) .+ (structured|organized|designed)\b', 0.8),
                (r'\b(pattern|patterns)\b', 0.6),
                (r'\b(component|components)\b', 0.6),
                (r'\b(layer|layers|layered)\b', 0.7),
                (r'\b(service|services)\b', 0.5),
                (r'\boverall (design|structure)\b', 0.9),
            ],
            QueryIntent.BUG_INVESTIGATION: [
                (r'\b(bug|bugs|issue|issues)\b', 0.8),
                (r'\b(error|errors|exception|exceptions)\b', 0.8),
                (r'\b(fix|fixing|fixed)\b', 0.6),
                (r'\b(crash|crashes|crashing)\b', 0.9),
                (r'\b(fail|fails|failing|failure)\b', 0.8),
                (r'\bwhy (is|does|do) .+ (not working|broken|fail)\b', 0.9),
                (r'\bwhat\'s wrong\b', 0.8),
                (r'\bdebug\b', 0.8),
                (r'\btraceback\b', 0.9),
                (r'\bstack trace\b', 0.9),
            ],
            QueryIntent.TESTING: [
                (r'\b(test|tests|testing)\b', 0.8),
                (r'\b(unittest|pytest|jest|mocha)\b', 0.9),
                (r'\b(coverage|cover)\b', 0.8),
                (r'\b(mock|mocking|stub)\b', 0.8),
                (r'\bhow (to|do I) test\b', 0.9),
                (r'\btest (case|cases|suite)\b', 0.9),
                (r'\b(assert|assertion)\b', 0.7),
            ],
            QueryIntent.PERFORMANCE: [
                (r'\b(performance|perform)\b', 0.8),
                (r'\b(slow|fast|speed|optimize)\b', 0.7),
                (r'\b(memory|cpu|resource)\b', 0.7),
                (r'\b(bottleneck|profil)\b', 0.9),
                (r'\b(latency|throughput)\b', 0.8),
                (r'\bhow (to|can I) (improve|speed up|optimize)\b', 0.9),
                (r'\bwhy is .+ slow\b', 0.9),
            ],
            QueryIntent.DOCUMENTATION: [
                (r'\b(documentation|docs|readme)\b', 0.9),
                (r'\b(comment|comments|docstring)\b', 0.8),
                (r'\bwhere (is|are) .+ documented\b', 0.9),
                (r'\bhow (to|do I) use\b', 0.7),
                (r'\b(usage|example|examples)\b', 0.6),
                (r'\bAPI (docs|documentation|reference)\b', 0.9),
            ],
            QueryIntent.REFACTORING: [
                (r'\b(refactor|refactoring)\b', 0.9),
                (r'\b(clean up|cleanup|improve)\b', 0.6),
                (r'\b(rename|renaming)\b', 0.7),
                (r'\b(extract|extracting)\b', 0.6),
                (r'\b(code smell|anti-pattern)\b', 0.9),
                (r'\bhow (to|can I) (improve|simplify|clean)\b', 0.7),
                (r'\b(duplicate|duplication)\b', 0.7),
            ],
            QueryIntent.SECURITY: [
                (r'\b(security|secure|vulnerability)\b', 0.9),
                (r'\b(auth|authentication|authorization)\b', 0.8),
                (r'\b(permission|permissions)\b', 0.7),
                (r'\b(encrypt|encryption|decrypt)\b', 0.9),
                (r'\b(token|tokens|jwt|oauth)\b', 0.8),
                (r'\b(password|credential)\b', 0.8),
                (r'\b(xss|sql injection|csrf)\b', 0.9),
                (r'\bhow (is|are) .+ (protected|secured)\b', 0.8),
            ],
            QueryIntent.CONFIGURATION: [
                (r'\b(config|configuration|configure)\b', 0.9),
                (r'\b(setting|settings|setup)\b', 0.7),
                (r'\b(environment|env)\b', 0.7),
                (r'\b\.env\b', 0.9),
                (r'\b(option|options|parameter)\b', 0.6),
                (r'\bhow (to|do I) (configure|setup|set up)\b', 0.9),
            ],
        }

    def _init_entity_patterns(self):
        """Initialize entity extraction patterns."""
        self.entity_patterns = {
            'file_path': [
                r'[a-zA-Z_][a-zA-Z0-9_]*\.(py|js|ts|jsx|tsx|java|cpp|c|h|go|rs|rb|php)',  # file.ext
                r'(?:\.?/)?(?:[\w-]+/)*[\w-]+\.\w+',  # path/to/file.ext
                r'(?:src|lib|app|test|tests)/[\w/.-]+',  # common source paths
            ],
            'function_name': [
                r'\b(?:function|def|func)\s+([a-zA-Z_][a-zA-Z0-9_]*)',  # function definition
                r'\b([a-z_][a-z0-9_]*)\s*\(',  # function call (lowercase)
                r'\b(get|set|is|has|can|should|fetch|load|save|create|delete|update|find|search)[A-Z][a-zA-Z0-9_]*',  # camelCase methods
            ],
            'class_name': [
                r'\bclass\s+([A-Z][a-zA-Z0-9_]*)',  # class definition
                r'\b([A-Z][a-zA-Z0-9_]*[a-z][a-zA-Z0-9_]*)\b',  # PascalCase with at least one lowercase (not all caps or single caps)
            ],
            'error_type': [
                r'\b([A-Z][a-zA-Z]*Error)\b',  # SomethingError
                r'\b([A-Z][a-zA-Z]*Exception)\b',  # SomethingException
                r'\bTraceback\b',
                r'\bTypeError|ValueError|KeyError|AttributeError|ImportError|RuntimeError',
            ],
            'package_name': [
                r'\bimport\s+([a-zA-Z_][a-zA-Z0-9_]*)',  # Python import
                r'\bfrom\s+([a-zA-Z_][a-zA-Z0-9_.]*)',  # Python from import
                r'\brequire\([\'"]([^"\']+)[\'"]\)',  # Node require
                r'\bimport\s+.*\s+from\s+[\'"]([^"\']+)[\'"]',  # ES6 import
            ],
            'keyword': [
                r'\b(auth|api|database|db|cache|queue|worker|scheduler|logger|config)\b',
                r'\b(user|admin|role|permission|session|token)\b',
                r'\b(model|view|controller|service|repository|handler)\b',
            ],
        }

    def classify(self, query: str) -> ClassificationResult:
        """Classify a user query and extract relevant information."""
        query_lower = query.lower()

        # Score all intents
        intent_scores: Dict[QueryIntent, IntentMatch] = {}

        for intent, patterns in self.intent_patterns.items():
            score = 0.0
            matched = []

            for pattern, weight in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    score += weight
                    matched.append(pattern)

            if score > 0:
                # Normalize score (cap at 1.0)
                confidence = min(score / len(patterns) * 2, 1.0)
                intent_scores[intent] = IntentMatch(
                    intent=intent,
                    confidence=confidence,
                    matched_patterns=matched
                )

        # Extract entities
        entities = self._extract_entities(query)

        # Boost confidence based on entity extraction
        self._boost_intent_scores(intent_scores, entities)

        # Extract general keywords
        keywords = self._extract_keywords(query)

        # Determine primary and secondary intents
        if not intent_scores:
            primary = IntentMatch(
                intent=QueryIntent.GENERAL,
                confidence=0.5,
                matched_patterns=[]
            )
            secondary = []
        else:
            sorted_intents = sorted(
                intent_scores.values(),
                key=lambda x: x.confidence,
                reverse=True
            )
            primary = sorted_intents[0]
            # Secondary intents with confidence > 0.3
            secondary = [i for i in sorted_intents[1:] if i.confidence > 0.3]

        return ClassificationResult(
            query=query,
            primary_intent=primary,
            secondary_intents=secondary,
            entities=entities,
            keywords=keywords
        )

    def _extract_entities(self, query: str) -> Dict[str, List[str]]:
        """Extract named entities from the query."""
        entities: Dict[str, Set[str]] = {key: set() for key in self.entity_patterns}

        # Common English words to filter from class/function names
        common_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'to', 'of',
            'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through',
            'during', 'before', 'after', 'above', 'below', 'up', 'down', 'out', 'off',
            'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there',
            'when', 'where', 'why', 'how', 'what', 'which', 'who', 'whom', 'whose',
            'this', 'that', 'these', 'those', 'it', 'its', 'me', 'my', 'i', 'you',
            'your', 'we', 'our', 'they', 'their', 'if', 'not', 'no', 'yes', 'but',
            'and', 'or', 'so', 'because', 'while', 'until', 'after', 'before',
            'find', 'show', 'get', 'set', 'list', 'check', 'look', 'see', 'read',
            'write', 'make', 'create', 'delete', 'update', 'change', 'fix', 'add',
            'remove', 'use', 'using', 'used', 'run', 'running', 'test', 'testing',
            'file', 'files', 'folder', 'folders', 'directory', 'directories',
            'class', 'function', 'method', 'module', 'package', 'import', 'code',
            'error', 'errors', 'bug', 'bugs', 'issue', 'issues', 'problem',
        }

        for entity_type, patterns in self.entity_patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, query, re.IGNORECASE)
                if matches:
                    # Handle both single matches and groups
                    for match in matches:
                        if isinstance(match, tuple):
                            entities[entity_type].update(m for m in match if m)
                        else:
                            entities[entity_type].add(match)

        # Filter out common English words from class_name and function_name
        if 'class_name' in entities:
            entities['class_name'] = {
                name for name in entities['class_name']
                if name.lower() not in common_words
                and len(name) > 2
                and (
                    # Must have multiple capitals (PascalCase) or end with specific suffixes
                    sum(1 for c in name if c.isupper()) > 1
                    or name.endswith(('Error', 'Exception', 'Handler', 'Manager', 'Service', 'Repository', 'Controller', 'Factory', 'Builder', 'Provider', 'Adapter', 'Interface', 'Base', 'Abstract', 'Client', 'Server', 'Config', 'Settings', 'Model', 'View', 'Agent', 'Worker'))
                )
            }

        if 'function_name' in entities:
            entities['function_name'] = {
                name for name in entities['function_name']
                if name.lower() not in common_words and len(name) > 2
            }

        # Convert sets to lists
        return {k: list(v) for k, v in entities.items() if v}

    def _boost_intent_scores(
        self,
        intent_scores: Dict[QueryIntent, IntentMatch],
        entities: Dict[str, List[str]]
    ):
        """Boost intent confidence based on extracted entities."""
        boost_map = {
            'file_path': [QueryIntent.FILE_STRUCTURE, QueryIntent.CODE_SEARCH],
            'function_name': [QueryIntent.CODE_SEARCH, QueryIntent.CODE_EXPLANATION],
            'class_name': [QueryIntent.CODE_SEARCH, QueryIntent.CODE_EXPLANATION],
            'error_type': [QueryIntent.BUG_INVESTIGATION],
            'package_name': [QueryIntent.DEPENDENCY_INFO],
        }

        for entity_type, intents in boost_map.items():
            if entity_type in entities:
                for intent in intents:
                    if intent in intent_scores:
                        # Boost by 0.2 for each entity found (max 0.4)
                        boost = min(len(entities[entity_type]) * 0.2, 0.4)
                        intent_scores[intent].confidence = min(
                            intent_scores[intent].confidence + boost,
                            1.0
                        )
                        intent_scores[intent].extracted_entities[entity_type] = entities[entity_type]

    def _extract_keywords(self, query: str) -> List[str]:
        """Extract important keywords from the query."""
        # Remove common stop words
        stop_words = {
            'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'must', 'shall',
            'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
            'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
            'through', 'during', 'before', 'after', 'above', 'below',
            'up', 'down', 'out', 'off', 'over', 'under', 'again',
            'further', 'then', 'once', 'here', 'there', 'when', 'where',
            'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more',
            'most', 'other', 'some', 'such', 'no', 'not', 'only', 'own',
            'same', 'so', 'than', 'too', 'very', 'just', 'but', 'and',
            'or', 'if', 'because', 'this', 'that', 'these', 'those',
            'what', 'which', 'who', 'whom', 'whose', 'it', 'its', 'me',
            'my', 'i', 'you', 'your', 'we', 'our', 'they', 'their',
        }

        # Extract words
        words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', query.lower())

        # Filter and return keywords
        keywords = [
            word for word in words
            if word not in stop_words and len(word) > 2
        ]

        # Remove duplicates while preserving order
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        return unique_keywords


def get_research_actions(result: ClassificationResult) -> List[Dict[str, any]]:
    """
    Convert classification result into actionable research steps.
    Returns a list of actions to perform based on detected intents.
    """
    actions = []

    intent_to_actions = {
        QueryIntent.FILE_STRUCTURE: {
            'action': 'list_directory',
            'priority': 1,
            'description': 'Check directory structure'
        },
        QueryIntent.CODE_SEARCH: {
            'action': 'search_code',
            'priority': 1,
            'description': 'Search for code patterns'
        },
        QueryIntent.CODE_EXPLANATION: {
            'action': 'read_code',
            'priority': 2,
            'description': 'Read relevant source files'
        },
        QueryIntent.GIT_HISTORY: {
            'action': 'git_history',
            'priority': 1,
            'description': 'Check git commit history'
        },
        QueryIntent.DEPENDENCY_INFO: {
            'action': 'check_dependencies',
            'priority': 1,
            'description': 'Examine dependency files'
        },
        QueryIntent.ARCHITECTURE: {
            'action': 'analyze_structure',
            'priority': 2,
            'description': 'Analyze project architecture'
        },
        QueryIntent.BUG_INVESTIGATION: {
            'action': 'debug_search',
            'priority': 1,
            'description': 'Search for error patterns'
        },
        QueryIntent.TESTING: {
            'action': 'find_tests',
            'priority': 1,
            'description': 'Find test files and patterns'
        },
        QueryIntent.PERFORMANCE: {
            'action': 'profile_code',
            'priority': 2,
            'description': 'Analyze performance patterns'
        },
        QueryIntent.DOCUMENTATION: {
            'action': 'find_docs',
            'priority': 1,
            'description': 'Search documentation'
        },
        QueryIntent.REFACTORING: {
            'action': 'analyze_code_quality',
            'priority': 2,
            'description': 'Analyze code for improvements'
        },
        QueryIntent.SECURITY: {
            'action': 'security_scan',
            'priority': 1,
            'description': 'Check security patterns'
        },
        QueryIntent.CONFIGURATION: {
            'action': 'check_config',
            'priority': 1,
            'description': 'Examine configuration files'
        },
    }

    # Add actions for primary intent
    if result.primary_intent.intent in intent_to_actions:
        action = intent_to_actions[result.primary_intent.intent].copy()
        action['intent'] = result.primary_intent.intent
        action['confidence'] = result.primary_intent.confidence
        action['entities'] = result.entities
        action['keywords'] = result.keywords
        actions.append(action)

    # Add actions for high-confidence secondary intents
    for secondary in result.secondary_intents:
        if secondary.confidence > 0.5 and secondary.intent in intent_to_actions:
            action = intent_to_actions[secondary.intent].copy()
            action['intent'] = secondary.intent
            action['confidence'] = secondary.confidence
            action['entities'] = secondary.extracted_entities
            actions.append(action)

    # Sort by priority
    actions.sort(key=lambda x: x['priority'])

    return actions
