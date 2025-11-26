"""
File prioritization for semantic search indexing.

Assigns priority to files to ensure most important files are indexed first:
- README files (highest priority - project overview)
- Source code files (second highest - main content)
- Documentation files (third - supplementary info)
- Test files (lower - useful but not primary)
- Other files (lowest - config, data, etc.)
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import FrozenSet, List, Optional


@dataclass(frozen=True)
class FilePriorityConfig:
    """
    Configuration for file prioritization.

    Defines patterns for categorizing files by priority.
    All pattern matching is case-insensitive.
    """

    # Source code extensions (high priority)
    source_extensions: FrozenSet[str] = frozenset({
        '.py', '.pyi',  # Python
        '.js', '.jsx', '.mjs', '.cjs',  # JavaScript
        '.ts', '.tsx', '.mts', '.cts',  # TypeScript
        '.go',  # Go
        '.rs',  # Rust
        '.java', '.kt', '.kts',  # JVM
        '.c', '.cpp', '.cc', '.cxx', '.h', '.hpp',  # C/C++
        '.cs',  # C#
        '.rb',  # Ruby
        '.php',  # PHP
        '.swift',  # Swift
        '.scala',  # Scala
        '.ex', '.exs',  # Elixir
        '.clj', '.cljs',  # Clojure
        '.hs',  # Haskell
        '.ml', '.mli',  # OCaml
        '.lua',  # Lua
        '.r',  # R
        '.jl',  # Julia
    })

    # README file names (highest priority)
    readme_patterns: FrozenSet[str] = frozenset({
        'readme.md',
        'readme.rst',
        'readme.txt',
        'readme',
    })

    # Documentation directory patterns
    docs_patterns: FrozenSet[str] = frozenset({
        'docs/',
        'doc/',
        'documentation/',
        'wiki/',
    })

    # Test directory patterns (match before source to catch test/*.py)
    test_patterns: FrozenSet[str] = frozenset({
        'test/',
        'tests/',
        'spec/',
        'specs/',
        '__tests__/',
        'test_',  # test_*.py files
        '_test.',  # *_test.py files
    })


class DefaultFilePrioritizer:
    """
    Prioritizes files for indexing: README > Source > Docs > Tests > Other.

    This ensures the most useful context is indexed first, which is
    especially important for large codebases where indexing may be
    interrupted or partial.

    Priority Levels:
    - PRIORITY_README (0): README files - project overview
    - PRIORITY_SOURCE (1): Source code files - main content
    - PRIORITY_DOCS (2): Documentation files
    - PRIORITY_TESTS (3): Test files
    - PRIORITY_OTHER (4): Everything else

    Implements FilePrioritizerProtocol.
    """

    PRIORITY_README = 0
    PRIORITY_SOURCE = 1
    PRIORITY_DOCS = 2
    PRIORITY_TESTS = 3
    PRIORITY_OTHER = 4

    def __init__(self, config: Optional[FilePriorityConfig] = None):
        """
        Initialize file prioritizer.

        Args:
            config: Optional configuration (uses defaults if None)
        """
        self._config = config or FilePriorityConfig()

    def get_priority(self, file_path: Path) -> int:
        """
        Assign priority to a file (lower = higher priority).

        Priority determination order:
        1. Check if README file (highest priority)
        2. Check if in test directory (must check before source)
        3. Check if source code extension
        4. Check if in documentation directory
        5. Default to OTHER priority

        Args:
            file_path: Path to the file

        Returns:
            Priority value (0 = highest, 4 = lowest)
        """
        name_lower = file_path.name.lower()
        # Normalize path separators for cross-platform matching
        path_str = str(file_path).lower().replace('\\', '/')

        # Priority 0: README files
        if name_lower in self._config.readme_patterns:
            return self.PRIORITY_README

        # Priority 3: Test files (check BEFORE source to catch test/*.py)
        # Check both path patterns and filename patterns
        if self._is_test_file(path_str, name_lower):
            return self.PRIORITY_TESTS

        # Priority 1: Source code files
        suffix_lower = file_path.suffix.lower()
        if suffix_lower in self._config.source_extensions:
            return self.PRIORITY_SOURCE

        # Priority 2: Documentation files
        if any(pattern in path_str for pattern in self._config.docs_patterns):
            return self.PRIORITY_DOCS

        # Priority 4: Everything else
        return self.PRIORITY_OTHER

    def _is_test_file(self, path_str: str, name_lower: str) -> bool:
        """
        Check if file is a test file based on path or name patterns.

        Args:
            path_str: Normalized file path string (lowercase, forward slashes)
            name_lower: Lowercase filename

        Returns:
            True if file is a test file
        """
        # Directory-based test patterns
        dir_patterns = {'test/', 'tests/', 'spec/', 'specs/', '__tests__/'}
        if any(pattern in path_str for pattern in dir_patterns):
            return True

        # Filename-based test patterns
        if name_lower.startswith('test_'):
            return True
        if '_test.' in name_lower:
            return True

        return False

    def sort_by_priority(self, files: List[Path]) -> List[Path]:
        """
        Sort files by priority (highest priority first).

        Uses stable sort to preserve original order within same priority.

        Args:
            files: List of file paths to sort

        Returns:
            Sorted list of file paths (lowest priority number first)
        """
        return sorted(files, key=self.get_priority)
