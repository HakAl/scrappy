#!/usr/bin/env python3
# Standalone version - copy to project and modify as needed
"""
Zen Lint: Universal "Lazy Coder" Detector.
Scans for forbidden patterns (TODO, FIXME, SHIM).
"""
import sys
import re
import json
import fnmatch
import argparse
import subprocess
import ipaddress
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional, Set

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

# Scope Constants
ALL = "ALL"
CODE = "CODE"
COMMENT = "COMMENT"
RAW = "RAW"  # Check original line with whitespace preserved

# Severity levels
SEVERITIES = ["HIGH", "MEDIUM", "LOW"]


@dataclass
class Rule:
    name: str
    pattern: str
    scope: str = ALL
    severity: str = "LOW"
    ignore_case: bool = True  # Most rules are case-insensitive; secrets opt out
    _compiled: re.Pattern = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        flags = re.IGNORECASE if self.ignore_case else 0
        self._compiled = re.compile(self.pattern, flags)

    def search(self, text: str) -> bool:
        return bool(self._compiled.search(text))


# -----------------------------------------------------------------------------
# Rules Definition
# -----------------------------------------------------------------------------

QUALITY_RULES = [
    # === HIGH SEVERITY: Security & Breakage ===
    Rule("API_KEY",
         r"['\"].{0,30}(api[_-]?key|secret|token|password|credential).{0,30}['\"]\s*[:=]\s*['\"][a-zA-Z0-9_\-]{8,}['\"]",
         CODE, "HIGH", ignore_case=False),
    Rule("PLACEHOLDER", r"\b[A-Z_]{2,}_HERE\b", CODE, "HIGH"),
    Rule("POSSIBLE_SECRET", r"\b(passwd|password|secret|api_?key)\s*=\s*['\"][^'\"]{8,}['\"]",
         CODE, "HIGH", ignore_case=False),
    Rule("CONFLICT_MARKER", r"^[<>=]{7}", ALL, "HIGH"),
    Rule("TRUNCATION_MARKER", r"(\.{3}|...)\s*(rest of|remaining|more|etc|continues|implementation)", ALL, "HIGH"),
    Rule("INCOMPLETE_IMPL", r"#\s*(TODO|FIXME):\s*(implement|finish|complete|add)\b", ALL, "HIGH"),
    Rule("OVERLY_GENERIC_EXCEPT", r"except\s*:\s*$", CODE, "HIGH"),
    Rule("BARE_RETURN_IN_CATCH", r"catch\s*\([^)]*\)\s*\{\s*return\s*;?\s*\}", CODE, "HIGH"),

    # === MEDIUM SEVERITY: Maintenance & Debt ===
    Rule("TODO", r"\bTODO\b", COMMENT, "MEDIUM"),
    Rule("FIXME", r"\bFIXME\b", COMMENT, "MEDIUM"),
    Rule("HACK", r"\bHACK\b", COMMENT, "MEDIUM"),
    Rule("XXX", r"\bXXX\b", COMMENT, "MEDIUM"),
    Rule("STUB_IMPL", r"^\s*(pass|\.{3})\s*$", CODE, "MEDIUM"),
    Rule("NOT_IMPLEMENTED", r"(raise\s+)?NotImplementedError|not\s+implemented", CODE, "MEDIUM"),
    Rule("HARDCODED_IP",
         # Simple pattern to match IP-like strings (validated separately)
         r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b",
         CODE, "MEDIUM"),
    Rule("AI_COMMENT_BOILERPLATE",
         r"^\s*#\s*(This (function|method|class|module)|The following)\s+(is used to|responsible for|will|provides|represents)\b",
         COMMENT, "MEDIUM"),
    Rule("INLINE_IMPORT",
         r"^\s+(?:import\s+\w|from\s+\w+\s+import|require\s*\(|using\s+\w)",
         RAW, "MEDIUM"),

    # === LOW SEVERITY: Smells & Cleanup ===
    Rule("DEBUG_PRINT", r"\b(console\.log|print|System\.out\.print|fmt\.Print(ln)?|puts|dd|var_dump)\s*\(", CODE,
         "LOW"),
    Rule("DEAD_COMMENT", r"\b(unused|dead code|commented.?out|remove.?this|delete.?this)\b", COMMENT, "LOW"),
    Rule("TEMP_FIX", r"\b(temp|temporary|workaround|band.?aid)\b", COMMENT, "LOW"),
    Rule("LINT_DISABLE", r"(eslint-disable|pylint:\s*disable|noqa|@ts-ignore|@ts-expect-error|rubocop:disable)",
         COMMENT, "LOW"),
    Rule("EXAMPLE_DATA", r"['\"](example|test[@.]|foo|bar|john[._]?doe|jane[._]?doe|lorem ipsum|acme)['\"]", CODE,
         "LOW"),
    Rule("CATCH_ALL_EXCEPTION", r"except\s+Exception\s*:|catch\s*\(\s*(Exception|Error|Throwable)\s+\w+\s*\)", CODE,
         "LOW"),
    Rule("MAGIC_NUMBER", r"(?<![0-9a-zA-Z_.])(86400|3600|31536000|604800|1440|525600)(?![0-9])", CODE, "LOW"),
    Rule("EMPTY_CATCH", r"(except.*:\s*pass|catch\s*\([^)]*\)\s*\{\s*\})", CODE, "LOW"),
    Rule("COPY_PASTE_COMMENT", r"(copied from|copy.?pasted?|stolen from|borrowed from)", COMMENT, "LOW"),
    Rule("EMPTY_DOCSTRING", r'("""|\'\'\')\s*\1', CODE, "LOW"),
]

# Language syntax definitions: (line_comment, block_start, block_end)
LANG_SYNTAX = {
    '.py': ('#', '"""', '"""'),
    '.pyi': ('#', '"""', '"""'),
    '.js': ('//', '/*', '*/'),
    '.mjs': ('//', '/*', '*/'),
    '.cjs': ('//', '/*', '*/'),
    '.ts': ('//', '/*', '*/'),
    '.jsx': ('//', '/*', '*/'),
    '.tsx': ('//', '/*', '*/'),
    '.java': ('//', '/*', '*/'),
    '.kt': ('//', '/*', '*/'),
    '.scala': ('//', '/*', '*/'),
    '.c': ('//', '/*', '*/'),
    '.h': ('//', '/*', '*/'),
    '.cpp': ('//', '/*', '*/'),
    '.hpp': ('//', '/*', '*/'),
    '.cc': ('//', '/*', '*/'),
    '.cs': ('//', '/*', '*/'),
    '.go': ('//', '/*', '*/'),
    '.rs': ('//', '/*', '*/'),
    '.swift': ('//', '/*', '*/'),
    '.php': ('//', '/*', '*/'),
    '.rb': ('#', '=begin', '=end'),
    '.sh': ('#', None, None),
    '.bash': ('#', None, None),
    '.zsh': ('#', None, None),
    '.fish': ('#', None, None),
    '.yaml': ('#', None, None),
    '.yml': ('#', None, None),
    '.toml': ('#', None, None),
    '.ini': (';', None, None),
    '.sql': ('--', '/*', '*/'),
    '.lua': ('--', '--[[', ']]'),
    '.r': ('#', None, None),
    '.jl': ('#', '#=', '=#'),
}

IGNORE_DIRS: Set[str] = {
    # Version control
    ".git", ".svn", ".hg", ".zen",
    # Python
    "__pycache__", "venv", ".venv", "env", ".eggs", "*.egg-info",
    ".mypy_cache", ".pytest_cache", ".tox", ".nox", ".ruff_cache",
    "site-packages", "htmlcov", ".hypothesis",
    # JavaScript/Node
    "node_modules", "bower_components", ".npm", ".yarn", ".pnpm",
    # Build outputs
    "dist", "build", "target", "bin", "obj", "out", "_build",
    "cmake-build-debug", "cmake-build-release", "CMakeFiles",
    # IDE/Editor
    ".idea", ".vscode", ".vs", ".eclipse", ".settings",
    # Coverage
    "coverage", ".coverage", ".nyc_output",
    # Framework-specific
    ".next", ".nuxt", ".output", ".svelte-kit", ".astro",
    ".angular", ".docusaurus", ".meteor",
    # Infrastructure/Deploy
    ".terraform", ".serverless", ".aws-sam", "cdk.out",
    ".vercel", ".netlify", ".firebase",
    # Other languages
    ".gradle", ".cargo", ".stack-work", "Pods", "Carthage",
    "DerivedData", "vendor", "deps", "elm-stuff",
    # Misc
    "tmp", "temp", "cache", ".cache", "logs",
}

IGNORE_FILES: Set[str] = {
    # Lock files
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "go.sum",
    "Cargo.lock", "Gemfile.lock", "poetry.lock", "composer.lock",
    "packages.lock.json", "flake.lock", "pubspec.lock",
    # OS artifacts
    ".DS_Store", "Thumbs.db", "desktop.ini",
    # Editor artifacts
    ".gitignore", ".gitattributes", ".editorconfig",
    # Docs/meta (not code)
    "LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE",
    "CHANGELOG.md", "CHANGELOG", "HISTORY.md",
    "AUTHORS", "CONTRIBUTORS", "CODEOWNERS",
    # Config files (too many false positives)
    ".prettierrc", ".eslintrc", ".stylelintrc",
    "tsconfig.json", "jsconfig.json",
    # Misc
    ".npmrc", ".nvmrc", ".python-version", ".ruby-version",
    ".tool-versions", "requirements.txt", "Pipfile",
    # Environment files (should be gitignored, not our job)
    ".env", ".env.local", ".env.development", ".env.production",
    ".env.test", ".env.staging", ".env.example",
}

IGNORE_EXTS: Set[str] = {
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".bmp",
    # Documents (binary)
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    # Documentation (text) - too many false positives
    ".md", ".markdown", ".rst", ".txt", ".adoc", ".textile",
    # Archives
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    # Binaries
    ".exe", ".dll", ".so", ".dylib", ".class", ".pyc", ".pyo", ".o", ".a",
    # Fonts
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    # Media
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv", ".flac", ".ogg",
    # Generated/minified
    ".min.js", ".min.css", ".map", ".bundle.js",
    # Data files
    ".csv", ".tsv", ".json", ".xml", ".lock",
}

# Suppression patterns for different comment styles
SUPPRESS_PATTERNS = {
    '#': re.compile(r"#\s*lint:(ignore|disable)(?:\s+([A-Z_]+))?\b", re.IGNORECASE),
    '//': re.compile(r"//\s*lint:(ignore|disable)(?:\s+([A-Z_]+))?\b", re.IGNORECASE),
    '--': re.compile(r"--\s*lint:(ignore|disable)(?:\s+([A-Z_]+))?\b", re.IGNORECASE),
    ';': re.compile(r";\s*lint:(ignore|disable)(?:\s+([A-Z_]+))?\b", re.IGNORECASE),
}

def get_suppression_match(line: str, ext: str):
    """Check for lint suppression comment based on language."""
    syntax = LANG_SYNTAX.get(ext)
    if syntax and syntax[0]:
        pattern = SUPPRESS_PATTERNS.get(syntax[0])
        if pattern:
            return pattern.search(line)
    # Fallback: try all patterns
    for pattern in SUPPRESS_PATTERNS.values():
        match = pattern.search(line)
        if match:
            return match
    return None

# Rules that should be skipped in test files (mock secrets are common)
TEST_EXEMPT_RULES: Set[str] = {"API_KEY", "POSSIBLE_SECRET", "EXAMPLE_DATA"}

# Patterns that indicate a test file (checked against full path)
# Matches: test_*.py, *_test.py, *.test.js, *.spec.ts, tests/, __tests__/
TEST_FILE_PATTERNS = re.compile(
    r"([\\/]|^)(tests?|spec|__tests__)[\\/]|"  # test directories
    r"[\\/]test_[^\\/]*$|"                      # /test_*.ext
    r"_test\.[^\\/]+$|"                         # *_test.ext
    r"\.test\.[^\\/]+$|"                        # *.test.ext
    r"\.spec\.[^\\/]+$",                        # *.spec.ext
    re.IGNORECASE
)


# -----------------------------------------------------------------------------
# Core Logic
# -----------------------------------------------------------------------------

def is_binary(path: Path, sample_size: int = 8192, threshold: float = 0.10, min_size: int = 1024) -> bool:
    """Check if file is binary using null byte ratio heuristic."""
    try:
        file_size = path.stat().st_size
        # Small files (< 1KB) are assumed to be text to avoid favicon/icon misdetection
        if file_size < min_size:
            return False
        blob = path.read_bytes()[:sample_size]
        if not blob:
            return False
        return blob.count(b'\0') / len(blob) > threshold
    except Exception:
        return True


def find_string_ranges(line: str) -> List[Tuple[int, int]]:
    """
    Find ranges of string literals in a line to avoid false comment detection.
    Returns list of (start, end) indices.
    Handles both single/double quotes and triple-quoted strings.
    """
    ranges = []
    i = 0
    length = len(line)

    while i < length:
        c = line[i]

        if c in ('"', "'", '`'):
            # Check for triple-quoted string
            if i + 2 < length and line[i:i+3] in ('"""', "'''"):
                triple = line[i:i+3]
                start = i
                i += 3
                # Look for closing triple quote
                while i + 2 < length:
                    if line[i] == '\\':
                        i += 2  # Skip escaped character
                        continue
                    if line[i:i+3] == triple:
                        ranges.append((start, i + 3))
                        i += 3
                        break
                    i += 1
                else:
                    # Unclosed triple quote - don't add to ranges (spans multiple lines)
                    i = length
            else:
                # Single-quoted string
                quote_char = c
                start = i
                i += 1
                while i < length:
                    if line[i] == '\\' and i + 1 < length:
                        i += 2  # Skip escaped character
                        continue
                    if line[i] == quote_char:
                        ranges.append((start, i + 1))
                        i += 1
                        break
                    i += 1
                else:
                    # Unclosed string - don't add to ranges
                    pass
        else:
            i += 1

    return ranges


def is_in_string(pos: int, ranges: List[Tuple[int, int]]) -> bool:
    """Check if a position falls within any string literal range."""
    return any(start <= pos < end for start, end in ranges)


def split_code_comment(line: str, ext: str) -> Tuple[str, str]:
    """
    Splits a line into (code, comment) with string-awareness.
    """
    syntax = LANG_SYNTAX.get(ext)

    if not syntax or not syntax[0]:
        return line, ""

    comment_char = syntax[0]
    string_ranges = find_string_ranges(line)

    # Find comment start that's not inside a string
    idx = 0
    while True:
        pos = line.find(comment_char, idx)
        if pos == -1:
            return line, ""

        if not is_in_string(pos, string_ranges):
            return line[:pos], line[pos + len(comment_char):]

        idx = pos + 1


@dataclass
class MultilineState:
    """Track multi-line comment state across lines."""
    in_block: bool = False
    block_end: Optional[str] = None


# Patterns that indicate a stub is legitimate (abstract methods, protocols)
ABSTRACT_PATTERNS = re.compile(
    r"@(abc\.)?(abstractmethod|abstractproperty)|"
    r"class\s+\w+\s*\([^)]*\b(ABC|Protocol|Interface)\b|"
    r"virtual|abstract\s+(class|void|int|string|bool)",
    re.IGNORECASE
)


def is_private_or_special_ip(ip_str: str) -> bool:
    """Check if IP is private, loopback, link-local, or otherwise special/reserved."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private or
            ip.is_loopback or
            ip.is_link_local or
            ip.is_reserved or
            ip.is_multicast
        )
    except ValueError:
        # Not a valid IP address
        return False


def check_file(path: str, min_severity: str = "LOW", config: Optional[Dict] = None) -> List[Dict]:
    """Scan a file for violations."""
    p = Path(path)

    if p.name == Path(__file__).name:
        return []

    # Pre-checks
    if not p.exists() or not p.is_file():
        return []
    if p.name in IGNORE_FILES:
        return []
    if p.suffix.lower() in IGNORE_EXTS:
        return []
    if any(p.name.endswith(ext) for ext in ['.min.js', '.min.css']):
        return []
    if is_binary(p):
        return []

    violations = []
    severity_threshold = SEVERITIES.index(min_severity)

    # Check if this is a test file (exempt from secret detection rules)
    is_test_file = bool(TEST_FILE_PATTERNS.search(str(p)))

    # Get rules (with config overrides if provided)
    rules = QUALITY_RULES
    if config:
        disabled = set(config.get("disabled_rules", []))
        rules = [r for r in rules if r.name not in disabled]

    # Skip secret detection rules in test files
    if is_test_file:
        rules = [r for r in rules if r.name not in TEST_EXEMPT_RULES]

    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        ext = p.suffix.lower()
        syntax = LANG_SYNTAX.get(ext)

        # Multi-line comment tracking
        ml_state = MultilineState()

        for i, line in enumerate(lines):
            line_num = i + 1
            original_line = line
            stripped = line.strip()

            if not stripped:
                continue

            # Check for inline suppression
            suppression_match = get_suppression_match(line, ext)
            if suppression_match:
                specific_rule = suppression_match.group(2)
                if not specific_rule:
                    # Suppress all rules for this line
                    continue

            # Handle multi-line comment state
            is_comment_line = False
            string_ranges = find_string_ranges(stripped)

            if syntax and syntax[1] and syntax[2]:
                block_start, block_end = syntax[1], syntax[2]

                if ml_state.in_block:
                    is_comment_line = True
                    if block_end in stripped:
                        ml_state.in_block = False
                else:
                    # Check for block comment start, but not inside strings
                    start_pos = stripped.find(block_start)
                    if start_pos != -1 and not is_in_string(start_pos, string_ranges):
                        end_pos = stripped.find(block_end, start_pos + len(block_start))
                        if end_pos == -1:
                            ml_state.in_block = True
                            ml_state.block_end = block_end

            # Split code and comment
            if is_comment_line:
                code_part, comment_part = "", stripped
            else:
                code_part, comment_part = split_code_comment(stripped, ext)

            for rule in rules:
                # Check severity threshold
                if SEVERITIES.index(rule.severity) > severity_threshold:
                    continue

                if suppression_match and suppression_match.group(2):
                    if rule.name.upper() == suppression_match.group(2).upper():
                        continue

                # Determine target text based on scope
                if rule.scope == ALL:
                    target = stripped
                elif rule.scope == RAW:
                    target = original_line
                elif rule.scope == CODE:
                    target = code_part
                elif rule.scope == COMMENT:
                    target = comment_part
                else:
                    target = stripped

                if not target:
                    continue

                match = rule._compiled.search(target)
                if match:
                    # Skip STUB_IMPL for abstract methods/protocols
                    if rule.name == "STUB_IMPL":
                        # Check previous lines for abstract/protocol context
                        context_start = max(0, i - 5)
                        context = "\n".join(lines[context_start:i + 1])
                        if ABSTRACT_PATTERNS.search(context):
                            continue

                    # Skip HARDCODED_IP for private/special IPs
                    if rule.name == "HARDCODED_IP":
                        ip_str = match.group(1)  # Extract IP from capturing group
                        if is_private_or_special_ip(ip_str):
                            continue

                    violations.append({
                        'rule': rule.name,
                        'severity': rule.severity,
                        'file': str(p),
                        'line': line_num,
                        'content': stripped[:80]  # Shorter preview
                    })

    except Exception as e:
        print(f"Error scanning {path}: {e}", file=sys.stderr)

    return violations


def get_git_changes() -> List[str]:
    """Get list of changed files from git (including staged)."""
    files = set()
    try:
        # Check if HEAD exists (repo may have no commits yet)
        head_exists = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False
        ).returncode == 0

        if head_exists:
            # Get unstaged changes
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                files.update(result.stdout.splitlines())

            # Get staged changes
            result = subprocess.run(
                ["git", "diff", "--name-only", "--cached", "HEAD"],
                capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                files.update(result.stdout.splitlines())
        else:
            # No commits yet - get all staged files
            result = subprocess.run(
                ["git", "diff", "--name-only", "--cached"],
                capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                files.update(result.stdout.splitlines())

        # Get untracked files
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            files.update(result.stdout.splitlines())
    except FileNotFoundError:
        pass
    return [f for f in files if f]


def load_config(config_path: Optional[str]) -> Optional[Dict]:
    """Load configuration from JSON file."""
    if not config_path:
        # Look for default config files
        for name in [".lintrc.json", ".lintrc", "lint.config.json"]:
            if Path(name).exists():
                config_path = name
                break

    if config_path and Path(config_path).exists():
        try:
            with open(config_path) as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load config {config_path}: {e}", file=sys.stderr)

    return None


# -----------------------------------------------------------------------------
# Reporting
# -----------------------------------------------------------------------------

def print_report(violations: List[Dict], output_format: str = "text") -> int:
    """Print violations report and return exit code."""

    if output_format == "json":
        print(json.dumps({"violations": violations, "count": len(violations)}, indent=2))
        high_count = sum(1 for v in violations if v['severity'] == "HIGH")
        return 1 if high_count > 0 else 0

    # SARIF format for CI integration
    if output_format == "sarif":
        sarif = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "zen-lint",
                        "version": "1.0.0",
                        "rules": [{"id": r.name, "shortDescription": {"text": r.name}} for r in QUALITY_RULES]
                    }
                },
                "results": [
                    {
                        "ruleId": v['rule'],
                        "level": "error" if v['severity'] == "HIGH" else (
                            "warning" if v['severity'] == "MEDIUM" else "note"),
                        "message": {"text": v['content']},
                        "locations": [{
                            "physicalLocation": {
                                "artifactLocation": {"uri": v['file']},
                                "region": {"startLine": v['line']}
                            }
                        }]
                    } for v in violations
                ]
            }]
        }
        print(json.dumps(sarif, indent=2))
        high_count = sum(1 for v in violations if v['severity'] == "HIGH")
        return 1 if high_count > 0 else 0

    # Text format - compact for agents
    if not violations:
        print("[PASS] No issues.")
        return 0

    severity_order = {s: i for i, s in enumerate(SEVERITIES)}
    violations.sort(key=lambda x: (severity_order.get(x['severity'], 99), x['file'], x['line']))

    print(f"Found {len(violations)} issue(s):\n")

    for v in violations:
        print(f"[{v['severity']}] {v['file']}:{v['line']} {v['rule']}")

    # Summary
    counts = {s: sum(1 for v in violations if v['severity'] == s) for s in SEVERITIES}
    summary = ", ".join(f"{counts[s]} {s.lower()}" for s in SEVERITIES if counts[s])
    print(f"\nSummary: {summary}")

    if counts["HIGH"] > 0:
        print("[FAIL] High severity issues found.")
        return 1
    return 0


def print_rules():
    """Print all available rules."""
    print("\nAvailable Rules:\n")
    for sev in SEVERITIES:
        rules = [r for r in QUALITY_RULES if r.severity == sev]
        if rules:
            print(f"[{sev}]")
            for r in rules:
                print(f"  {r.name}: {r.pattern[:60]}{'...' if len(r.pattern) > 60 else ''}")
            print()


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Universal Code Quality Linter - Detect lazy coder patterns",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                     # Lint git changes (or current dir)
  %(prog)s src/ tests/         # Lint specific directories
  %(prog)s -s HIGH             # Only show high severity issues
  %(prog)s -f json             # Output as JSON for CI
  %(prog)s --list-rules        # Show all available rules

Inline suppression:
  # lint:ignore              - Suppress all rules for this line
  # lint:ignore TODO         - Suppress specific rule

Config file (.lintrc.json):
  {"disabled_rules": ["DEBUG_PRINT", "MAGIC_NUMBER"]}
        """
    )

    parser.add_argument("paths", nargs="*", help="Files or directories to scan")
    parser.add_argument("-s", "--severity", choices=SEVERITIES, default="LOW",
                        help="Minimum severity level to report (default: LOW)")
    parser.add_argument("-f", "--format", choices=["text", "json", "sarif"], default="text",
                        help="Output format (default: text)")
    parser.add_argument("-c", "--config", help="Path to config file")
    parser.add_argument("--list-rules", action="store_true", help="List all available rules")

    args = parser.parse_args()

    if args.list_rules:
        print_rules()
        sys.exit(0)

    # Load config
    config = load_config(args.config)

    # Determine paths to scan
    paths = args.paths
    if not paths:
        paths = get_git_changes()
        if not paths:
            paths = ["."]

    all_violations = []

    for root_arg in paths:
        path = Path(root_arg)
        if path.is_file():
            all_violations.extend(check_file(str(path), args.severity, config))
        elif path.is_dir():
            for p in path.rglob("*"):
                if any(part in IGNORE_DIRS or any(fnmatch.fnmatch(part, pattern) for pattern in IGNORE_DIRS)
                       for part in p.parts):
                    continue
                if p.is_file():
                    all_violations.extend(check_file(str(p), args.severity, config))
        else:
            print(f"Warning: {root_arg} not found", file=sys.stderr)

    exit_code = print_report(all_violations, args.format)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
