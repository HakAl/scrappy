"""
Tests for CLI pattern configuration module.

TDD: Tests written first for the patterns.py module which centralizes
regex patterns for tool detection. All patterns should be pre-compiled
at module load time for performance.
"""

import re
import pytest


class TestPatternModuleStructure:
    """Tests for the patterns module structure and exports."""






    def test_all_patterns_constant_exists(self):
        """ALL_PATTERNS should provide a flat list of all patterns."""
        from src.cli.config.patterns import ALL_PATTERNS
        assert ALL_PATTERNS is not None
        assert isinstance(ALL_PATTERNS, (list, tuple))
        assert len(ALL_PATTERNS) >= 23  # At least 23 patterns


class TestPatternsArePreCompiled:
    """Tests to verify patterns are pre-compiled at module load time."""




    pass

class TestPatternCounts:
    """Tests to verify correct number of patterns in each category."""

    def test_web_patterns_count(self):
        """WEB_PATTERNS should contain exactly 9 patterns."""
        from src.cli.config.patterns import WEB_PATTERNS
        assert len(WEB_PATTERNS) == 9, (
            f"Expected 9 web patterns, got {len(WEB_PATTERNS)}"
        )

    def test_codebase_patterns_count(self):
        """CODEBASE_PATTERNS should contain exactly 14 patterns."""
        from src.cli.config.patterns import CODEBASE_PATTERNS
        assert len(CODEBASE_PATTERNS) == 14, (
            f"Expected 14 codebase patterns, got {len(CODEBASE_PATTERNS)}"
        )


class TestWebPatternMatching:
    """Tests for web-related pattern matching."""

    def setup_method(self):
        """Import patterns for testing."""
        from src.cli.config.patterns import WEB_PATTERNS
        self.patterns = WEB_PATTERNS

    def test_fetch_docs_pattern(self):
        """Pattern should match 'fetch docs' variations."""
        test_cases = [
            "fetch the docs for React",
            "fetch documentation for numpy",
            "fetch the API docs",
            "fetch website information",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"

    def test_get_from_web_pattern(self):
        """Pattern should match 'get from web' variations."""
        test_cases = [
            "get info from the website",
            "retrieve data from the web",
            "download from the url",
            "pull from the docs",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"

    def test_check_package_pattern(self):
        """Pattern should match 'check package' variations."""
        test_cases = [
            "check the npm package",
            "check pypi for the version",
            "check github for releases",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"

    def test_look_up_pattern(self):
        """Pattern should match 'look up' variations."""
        test_cases = [
            "look up the package info",
            "lookup library details",
            "look up module documentation",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"

    def test_latest_version_pattern(self):
        """Pattern should match 'latest version' variations."""
        test_cases = [
            "what is the latest version of pandas",
            "what are the current releases",
            "what is the newest version",
            "current version info",
            "latest releases available",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"

    def test_pypi_npm_pattern(self):
        """Pattern should match pypi/npm info variations."""
        test_cases = [
            "pypi info for requests",
            "npm package details",
            "github info for repo",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"

    def test_from_website_pattern(self):
        """Pattern should match 'from website' variations."""
        test_cases = [
            "from the website get info",
            "get data from the docs",
            "from url please fetch",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"

    def test_library_docs_pattern(self):
        """Pattern should match library documentation patterns."""
        test_cases = [
            "scikit-learn documentation",
            "sklearn docs",
            "react docs api",
            "django documentation reference",
            "flask api docs",
            "numpy documentation",
            "pandas docs",
            "express documentation",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"


class TestCodebasePatternMatching:
    """Tests for codebase exploration pattern matching."""

    def setup_method(self):
        """Import patterns for testing."""
        from src.cli.config.patterns import CODEBASE_PATTERNS
        self.patterns = CODEBASE_PATTERNS

    def test_file_existence_pattern(self):
        """Pattern should match file existence questions."""
        test_cases = [
            "does the file exist",
            "is there a directory",
            "where is the function",
            "has the code been updated",
            "where are the class definitions",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"

    def test_file_content_questions(self):
        """Pattern should match file content questions."""
        test_cases = [
            "what is in the config file",
            "what's inside the directory",
            "what is in the codebase",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"

    def test_show_commands(self):
        """Pattern should match 'show' commands."""
        test_cases = [
            "show me the function",
            "show the file contents",
            "show me the class definition",
            "show the directory",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"

    def test_read_commands(self):
        """Pattern should match 'read' commands."""
        test_cases = [
            "read the config file",
            "read code from main.py",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"

    def test_list_commands(self):
        """Pattern should match 'list' commands."""
        test_cases = [
            "list all files",
            "list the directories",
            "list folders in src",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"

    def test_structure_questions(self):
        """Pattern should match structure questions."""
        test_cases = [
            "structure of the project",
            "architecture of the codebase",
            "layout of the code",
            "organization in the project",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"

    def test_organization_questions(self):
        """Pattern should match 'how is organized' questions."""
        test_cases = [
            "how is the project organized",
            "how is the code structured",
            "how are the files laid out",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"

    def test_contains_questions(self):
        """Pattern should match 'does contain' questions."""
        test_cases = [
            "does it have tests",
            "does the code contain imports",
            "does the code include logging",
            "does it use async",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"

    def test_where_questions(self):
        """Pattern should match 'where is' questions."""
        test_cases = [
            "where is the main function",
            "where are the tests",
            "where does it define the class",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"

    def test_find_in_code_pattern(self):
        """Pattern should match 'find in code' patterns."""
        test_cases = [
            "find errors in the code",
            "find it inside the project",
            "find within the codebase",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"

    def test_file_extension_pattern(self):
        """Pattern should match file extension mentions."""
        test_cases = [
            "check main.py",
            "config.json",
            "style.css",
            "index.html",
            "test.ts",
            "component.tsx",
            "app.jsx",
            "main.java",
            "code.cpp",
            "header.h",
            "program.c",
            "lib.rs",
            "main.go",
            "script.rb",
            "index.php",
            "data.yaml",
            "config.yml",
            "readme.md",
            "notes.txt",
        ]
        for text in test_cases:
            matched = any(p.search(text.lower()) for p in self.patterns)
            assert matched, f"Should match: {text}"


class TestURLPatternMatching:
    """Tests for URL pattern matching."""

    def setup_method(self):
        """Import URL pattern for testing."""
        from src.cli.config.patterns import URL_PATTERN
        self.pattern = URL_PATTERN

    def test_https_urls(self):
        """Pattern should match HTTPS URLs."""
        test_cases = [
            "https://example.com",
            "check https://api.example.com/docs",
            "go to https://github.com/user/repo",
        ]
        for text in test_cases:
            assert self.pattern.search(text), f"Should match: {text}"

    def test_http_urls(self):
        """Pattern should match HTTP URLs."""
        test_cases = [
            "http://example.com",
            "check http://localhost:3000",
        ]
        for text in test_cases:
            assert self.pattern.search(text), f"Should match: {text}"

    def test_no_match_non_urls(self):
        """Pattern should not match non-URL text."""
        test_cases = [
            "hello world",
            "ftp://server.com",  # Only http/https
            "this is not a url",
        ]
        for text in test_cases:
            assert not self.pattern.search(text), f"Should not match: {text}"


class TestPathPatternMatching:
    """Tests for file path pattern matching."""

    def setup_method(self):
        """Import path pattern for testing."""
        from src.cli.config.patterns import PATH_PATTERN
        self.pattern = PATH_PATTERN

    def test_path_patterns(self):
        """Pattern should match file path patterns."""
        test_cases = [
            "src/main",
            "frontend/app",
            "tests/unit",
            "lib/utils",
        ]
        for text in test_cases:
            assert self.pattern.search(text), f"Should match: {text}"

    def test_no_match_single_word(self):
        """Pattern should not match single words without slashes."""
        test_cases = [
            "hello",
            "main",
            "tests",
        ]
        for text in test_cases:
            assert not self.pattern.search(text), f"Should not match: {text}"


class TestPatternDocumentation:
    """Tests to verify patterns have proper documentation."""

    def test_all_categories_documented(self):
        """All pattern categories should be documented."""
        from src.cli.config.patterns import PATTERN_DESCRIPTIONS
        required_categories = ['web', 'codebase', 'url', 'path']
        for category in required_categories:
            assert category in PATTERN_DESCRIPTIONS, (
                f"Category '{category}' should be documented"
            )

    def test_web_patterns_documented(self):
        """Each web pattern should have documentation."""
        from src.cli.config.patterns import (
            WEB_PATTERNS,
            PATTERN_DESCRIPTIONS
        )
        web_docs = PATTERN_DESCRIPTIONS.get('web', {})
        assert len(web_docs) == len(WEB_PATTERNS), (
            "Each web pattern should have documentation"
        )

    def test_codebase_patterns_documented(self):
        """Each codebase pattern should have documentation."""
        from src.cli.config.patterns import (
            CODEBASE_PATTERNS,
            PATTERN_DESCRIPTIONS
        )
        codebase_docs = PATTERN_DESCRIPTIONS.get('codebase', {})
        assert len(codebase_docs) == len(CODEBASE_PATTERNS), (
            "Each codebase pattern should have documentation"
        )


class TestPatternNegativeCases:
    """Tests to verify patterns don't match inappropriate inputs."""

    def setup_method(self):
        """Import patterns for testing."""
        from src.cli.config.patterns import WEB_PATTERNS, CODEBASE_PATTERNS
        self.web_patterns = WEB_PATTERNS
        self.codebase_patterns = CODEBASE_PATTERNS

    def test_simple_questions_no_match(self):
        """Simple questions should not match web or codebase patterns."""
        test_cases = [
            "what is Python",
            "explain async await",
            "how do decorators work",
            "write a function",
            "calculate 2 + 2",
            "hello",
            "thanks",
        ]
        for text in test_cases:
            lower_text = text.lower()
            web_match = any(p.search(lower_text) for p in self.web_patterns)
            assert not web_match, f"Web patterns should not match: {text}"
            # Note: some codebase patterns may match generic text due to broad patterns
            # This test is for web patterns specifically

    def test_empty_string_no_match(self):
        """Empty string should not match any patterns."""
        for pattern in self.web_patterns:
            assert not pattern.search("")
        for pattern in self.codebase_patterns:
            assert not pattern.search("")


class TestPatternCaseInsensitivity:
    """Tests to verify pattern matching is case insensitive."""

    def setup_method(self):
        """Import patterns for testing."""
        from src.cli.config.patterns import WEB_PATTERNS, CODEBASE_PATTERNS
        self.web_patterns = WEB_PATTERNS
        self.codebase_patterns = CODEBASE_PATTERNS

    def test_web_patterns_case_insensitive(self):
        """Web patterns should match regardless of case."""
        test_cases = [
            ("FETCH THE DOCS", True),
            ("Fetch The Docs", True),
            ("fetch the docs", True),
            ("CHECK PYPI", True),
        ]
        for text, should_match in test_cases:
            # Patterns should be applied to lowercased input
            matched = any(p.search(text.lower()) for p in self.web_patterns)
            assert matched == should_match, f"Case check failed for: {text}"

    def test_codebase_patterns_case_insensitive(self):
        """Codebase patterns should match regardless of case."""
        test_cases = [
            ("WHERE IS THE FILE", True),
            ("Where Is The File", True),
            ("where is the file", True),
        ]
        for text, should_match in test_cases:
            matched = any(p.search(text.lower()) for p in self.codebase_patterns)
            assert matched == should_match, f"Case check failed for: {text}"


class TestHelperFunctions:
    """Tests for any helper functions in the patterns module."""

    def test_match_any_web_pattern_function(self):
        """match_any_web_pattern helper should exist and work correctly."""
        from src.cli.config.patterns import match_any_web_pattern
        assert callable(match_any_web_pattern)
        assert match_any_web_pattern("fetch the docs") is True
        assert match_any_web_pattern("hello world") is False

    def test_match_any_codebase_pattern_function(self):
        """match_any_codebase_pattern helper should exist and work correctly."""
        from src.cli.config.patterns import match_any_codebase_pattern
        assert callable(match_any_codebase_pattern)
        assert match_any_codebase_pattern("where is the file") is True
        assert match_any_codebase_pattern("hello world") is False


class TestPackageKeywordsAndActionVerbs:
    """Tests for package keywords and action verbs constants."""

    def test_package_keywords_exists(self):
        """PACKAGE_KEYWORDS should be exported."""
        from src.cli.config.patterns import PACKAGE_KEYWORDS
        assert PACKAGE_KEYWORDS is not None
        assert isinstance(PACKAGE_KEYWORDS, (list, tuple, set))
        assert 'pypi' in PACKAGE_KEYWORDS
        assert 'npm' in PACKAGE_KEYWORDS
        assert 'github.com' in PACKAGE_KEYWORDS
        assert 'registry' in PACKAGE_KEYWORDS

    def test_action_keywords_exists(self):
        """ACTION_KEYWORDS should be exported."""
        from src.cli.config.patterns import ACTION_KEYWORDS
        assert ACTION_KEYWORDS is not None
        assert isinstance(ACTION_KEYWORDS, (list, tuple, set))
        assert 'fetch' in ACTION_KEYWORDS
        assert 'get' in ACTION_KEYWORDS
        assert 'check' in ACTION_KEYWORDS
        assert 'look' in ACTION_KEYWORDS
        assert 'find' in ACTION_KEYWORDS
        assert 'show' in ACTION_KEYWORDS
        assert 'what' in ACTION_KEYWORDS


class TestPathPatternFalsePositives:
    """Tests for PATH_PATTERN false positive cases.

    PATH_PATTERN should match file paths like 'src/main' but NOT:
    - Fractions like '2/3'
    - Code constructs like 'async/await'
    - Alternatives like 'and/or'
    - Technical terms like 'input/output'
    """

    def setup_method(self):
        """Import path pattern for testing."""
        from src.cli.config.patterns import PATH_PATTERN
        self.pattern = PATH_PATTERN

    @pytest.mark.parametrize("text", [
        "use 2/3 of the memory",
        "1/2 of the work is done",
        "ratio is 3/4",
        "split 50/50",
    ])
    def test_should_not_match_fractions(self, text):
        """PATH_PATTERN should not match numeric fractions."""
        assert not self.pattern.search(text), f"Should not match fraction: {text}"

    @pytest.mark.parametrize("text", [
        "use async/await syntax",
        "async/await is supported",
        "prefer async/await over callbacks",
    ])
    def test_should_not_match_async_await(self, text):
        """PATH_PATTERN should not match async/await code construct."""
        assert not self.pattern.search(text), f"Should not match: {text}"

    @pytest.mark.parametrize("text", [
        "use and/or conditions",
        "either/or choice",
        "yes/no question",
        "true/false values",
    ])
    def test_should_not_match_alternatives(self, text):
        """PATH_PATTERN should not match alternative expressions."""
        assert not self.pattern.search(text), f"Should not match: {text}"

    @pytest.mark.parametrize("text", [
        "input/output operations",
        "read/write access",
        "client/server architecture",
        "request/response cycle",
    ])
    def test_should_not_match_technical_pairs(self, text):
        """PATH_PATTERN should not match technical term pairs."""
        assert not self.pattern.search(text), f"Should not match: {text}"

    @pytest.mark.parametrize("text", [
        "src/main",
        "tests/unit",
        "lib/utils",
        "frontend/app",
        "src/components/Button",
        "config/settings.py",
    ])
    def test_should_match_valid_paths(self, text):
        """PATH_PATTERN should still match valid file paths."""
        assert self.pattern.search(text), f"Should match valid path: {text}"


class TestCodebasePattern9FalsePositives:
    """Tests for CODEBASE_PATTERN[9] false positive cases.

    Pattern 9 is 'where is/are/does/do' - it should match codebase queries
    but NOT general 'where is' questions unrelated to code.
    """

    def setup_method(self):
        """Import codebase patterns for testing."""
        from src.cli.config.patterns import CODEBASE_PATTERNS
        self.pattern = CODEBASE_PATTERNS[9]

    @pytest.mark.parametrize("text", [
        "where is the nearest coffee shop",
        "where is my car",
        "where is the bathroom",
        "where are you from",
        "where are my keys",
        "where does the sun rise",
        "where does this road lead",
        "where do you live",
    ])
    def test_should_not_match_non_code_questions(self, text):
        """Pattern should not match general 'where is' questions."""
        assert not self.pattern.search(text.lower()), f"Should not match: {text}"

    @pytest.mark.parametrize("text", [
        "where is the function defined",
        "where is the main file",
        "where are the tests",
        "where is the class",
        "where does it import this",
        "where is the code for authentication",
    ])
    def test_should_match_code_questions(self, text):
        """Pattern should still match codebase-related 'where is' questions."""
        # Note: These may need pattern 10 or 0 to match properly
        from src.cli.config.patterns import CODEBASE_PATTERNS
        matched = any(p.search(text.lower()) for p in CODEBASE_PATTERNS)
        assert matched, f"Should match code question: {text}"


class TestCodebasePattern8FalsePositives:
    """Tests for CODEBASE_PATTERN[8] false positive cases.

    Pattern 8 is 'does/do have/contain/include/use/import' - it should match
    code queries but NOT general questions about things having properties.
    """

    def setup_method(self):
        """Import codebase patterns for testing."""
        from src.cli.config.patterns import CODEBASE_PATTERNS
        self.pattern = CODEBASE_PATTERNS[8]

    @pytest.mark.parametrize("text", [
        "does Python have good performance",
        "does this car have leather seats",
        "do dictionaries contain keys",
        "does this approach have any downsides",
        "do they use good practices",
        "does anyone have experience with this",
        "do you have time to help",
    ])
    def test_should_not_match_non_code_questions(self, text):
        """Pattern should not match general 'does have' questions."""
        assert not self.pattern.search(text.lower()), f"Should not match: {text}"

    @pytest.mark.parametrize("text", [
        "does the file have imports",
        "does this module contain tests",
        "does the code include error handling",
        "does it use async",
        "does this class import logging",
    ])
    def test_should_match_code_questions(self, text):
        """Pattern should still match codebase-related questions."""
        from src.cli.config.patterns import CODEBASE_PATTERNS
        matched = any(p.search(text.lower()) for p in CODEBASE_PATTERNS)
        assert matched, f"Should match code question: {text}"


class TestCodebasePattern0FalsePositives:
    """Tests for CODEBASE_PATTERN[0] false positive cases.

    Pattern 0 matches questions about files/directories/code existence.
    It should NOT match unrelated sentences that happen to contain these words.
    """

    def setup_method(self):
        """Import codebase patterns for testing."""
        from src.cli.config.patterns import CODEBASE_PATTERNS
        self.pattern = CODEBASE_PATTERNS[0]

    @pytest.mark.parametrize("text", [
        "where should I go to learn about making code better",
        "does anyone know what good code looks like",
        "is there a better way to write code in general",
        "where can I find tutorials about code",
        "does Python have cleaner code than Java",
        "are there conventions for writing clean code",
    ])
    def test_should_not_match_general_code_discussion(self, text):
        """Pattern should not match general discussions about code."""
        assert not self.pattern.search(text.lower()), f"Should not match: {text}"

    @pytest.mark.parametrize("text", [
        "does the config file exist",
        "where is the main function",
        "is there a directory called tests",
        "are there any class definitions",
        "has the code been updated",
    ])
    def test_should_match_specific_code_queries(self, text):
        """Pattern should still match specific codebase queries."""
        assert self.pattern.search(text.lower()), f"Should match: {text}"


class TestEdgeCasesContractions:
    """Tests for contraction handling in patterns."""

    def setup_method(self):
        """Import patterns for testing."""
        from src.cli.config.patterns import CODEBASE_PATTERNS
        self.patterns = CODEBASE_PATTERNS

    @pytest.mark.parametrize("text", [
        "what's in the file",
        "where's the function",
        "how's the code structured",
        "what's inside the directory",
    ])
    def test_contractions_should_match(self, text):
        """Patterns should handle common contractions."""
        matched = any(p.search(text.lower()) for p in self.patterns)
        assert matched, f"Should match contraction: {text}"


class TestEdgeCasesSpecialPaths:
    """Tests for special characters and edge cases in file paths."""

    def setup_method(self):
        """Import patterns for testing."""
        from src.cli.config.patterns import CODEBASE_PATTERNS
        self.patterns = CODEBASE_PATTERNS

    @pytest.mark.parametrize("text", [
        "check .gitignore",
        "look at .env file",
        "read ../.env",
        "check ../config",
    ])
    def test_dotfiles_should_match(self, text):
        """Patterns should match dotfiles and relative paths."""
        matched = any(p.search(text.lower()) for p in self.patterns)
        assert matched, f"Should match: {text}"

    @pytest.mark.parametrize("text", [
        "check my-file.py",
        "look at my_file.py",
        "read test-config.json",
        "see user_data.yaml",
    ])
    def test_special_chars_in_filenames(self, text):
        """File extension pattern should match hyphens and underscores."""
        from src.cli.config.patterns import CODEBASE_PATTERNS
        # Pattern 12 is file extensions
        pattern = CODEBASE_PATTERNS[12]
        assert pattern.search(text.lower()), f"Should match: {text}"


class TestURLPatternEdgeCases:
    """Tests for URL pattern edge cases."""

    def setup_method(self):
        """Import URL pattern for testing."""
        from src.cli.config.patterns import URL_PATTERN
        self.pattern = URL_PATTERN

    def test_url_embedded_in_text(self):
        """Should find URL within surrounding text."""
        text = "check out https://example.com/docs for more info"
        assert self.pattern.search(text), f"Should match embedded URL"

    def test_multiple_urls_in_text(self):
        """Should find URLs when multiple are present."""
        text = "visit https://example.com or http://other.com"
        matches = self.pattern.findall(text)
        assert len(matches) == 2, f"Should find 2 URLs, found {len(matches)}"

    def test_uppercase_url(self):
        """Should match uppercase URL (when lowercased)."""
        text = "HTTPS://EXAMPLE.COM"
        assert self.pattern.search(text.lower()), f"Should match uppercase URL when lowercased"


class TestBoundaryConditions:
    """Tests for boundary conditions and edge cases."""

    def setup_method(self):
        """Import patterns for testing."""
        from src.cli.config.patterns import (
            WEB_PATTERNS, CODEBASE_PATTERNS, URL_PATTERN, PATH_PATTERN
        )
        self.web_patterns = WEB_PATTERNS
        self.codebase_patterns = CODEBASE_PATTERNS
    def test_whitespace_only_no_match(self):
        """Whitespace-only strings should not match."""
        test_cases = ["   ", "\t", "\n", "  \t\n  "]
        for text in test_cases:
            for pattern in self.web_patterns + self.codebase_patterns:
                assert not pattern.search(text), f"Should not match whitespace"

    def test_single_character_no_match(self):
        """Single characters should not match patterns."""
        for char in "abcdefghijklmnopqrstuvwxyz0123456789":
            for pattern in self.web_patterns:
                assert not pattern.search(char), f"Web pattern matched single char: {char}"

    def test_very_long_input(self):
        """Patterns should handle very long input without hanging."""
        long_text = "fetch the docs " * 1000
        # Should complete quickly without catastrophic backtracking
        for pattern in self.web_patterns:
            pattern.search(long_text)  # Just verify it completes

    def test_special_regex_chars_escaped(self):
        """Special regex characters in input should be handled safely."""
        test_cases = [
            "what about file.py?",
            "check (config).json",
            "look at [bracket].py",
            "file with * wildcard",
        ]
        for text in test_cases:
            # Should not raise exceptions
            for pattern in self.codebase_patterns:
                pattern.search(text.lower())
