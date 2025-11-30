"""
Intent and entity patterns.

Configuration data for intent classification and entity extraction.
Separated from logic to enable easy pattern updates without code changes.
"""

from typing import Dict, List, Tuple
from ..protocols import QueryIntent


INTENT_PATTERNS: Dict[QueryIntent, List[Tuple[str, float]]] = {
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


ENTITY_PATTERNS: Dict[str, List[str]] = {
    'file_path': [
        r'[a-zA-Z_][a-zA-Z0-9_]*\.(py|js|ts|jsx|tsx|java|cpp|c|h|go|rs|rb|php)',
        r'(?:\.?/)?(?:[\w-]+/)*[\w-]+\.\w+',
        r'(?:src|lib|app|test|tests)/[\w/.-]+',
    ],
    'function_name': [
        r'\b(?:function|def|func)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
        r'\b([a-z_][a-z0-9_]*)\s*\(',
        r'\b(get|set|is|has|can|should|fetch|load|save|create|delete|update|find|search)[A-Z][a-zA-Z0-9_]*',
    ],
    'class_name': [
        r'\bclass\s+([A-Z][a-zA-Z0-9_]*)',
        r'\b([A-Z][a-zA-Z0-9_]*[a-z][a-zA-Z0-9_]*)\b',
    ],
    'error_type': [
        r'\b([A-Z][a-zA-Z]*Error)\b',
        r'\b([A-Z][a-zA-Z]*Exception)\b',
        r'\bTraceback\b',
        r'\bTypeError|ValueError|KeyError|AttributeError|ImportError|RuntimeError',
    ],
    'package_name': [
        r'\bimport\s+([a-zA-Z_][a-zA-Z0-9_]*)',
        r'\bfrom\s+([a-zA-Z_][a-zA-Z0-9_.]*)',
        r'\brequire\([\'"]([^"\']+)[\'"]\)',
        r'\bimport\s+.*\s+from\s+[\'"]([^"\']+)[\'"]',
    ],
    'keyword': [
        r'\b(auth|api|database|db|cache|queue|worker|scheduler|logger|config)\b',
        r'\b(user|admin|role|permission|session|token)\b',
        r'\b(model|view|controller|service|repository|handler)\b',
    ],
}


ENTITY_BOOST_MAP: Dict[str, List[QueryIntent]] = {
    'file_path': [QueryIntent.FILE_STRUCTURE],
    'function_name': [QueryIntent.CODE_EXPLANATION],
    'class_name': [QueryIntent.CODE_EXPLANATION],
    'error_type': [QueryIntent.BUG_INVESTIGATION],
    'package_name': [QueryIntent.DEPENDENCY_INFO],
}


COMMON_WORDS = {
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


STOP_WORDS = {
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
