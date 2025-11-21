"""
Tests for CLI tool detector module.

TDD: Tests written first for the tool_detector.py module which handles
pattern matching to detect when user queries need tool support.
"""

import pytest


class TestNeedsToolSupport:
    """Tests for needs_tool_support() function."""

    def setup_method(self):
        """Import the module under test."""
        from src.cli.tool_detector import needs_tool_support
        self.needs_tool_support = needs_tool_support

    # =========================================================================
    # Web Fetching Pattern Tests
    # =========================================================================

    def test_detects_fetch_docs_pattern(self):
        """Should detect 'fetch docs' patterns as needing tools."""
        assert self.needs_tool_support("fetch the docs for React") is True
        assert self.needs_tool_support("fetch documentation for numpy") is True
        assert self.needs_tool_support("fetch the API docs") is True

    def test_detects_get_from_web_pattern(self):
        """Should detect 'get from web' patterns as needing tools."""
        assert self.needs_tool_support("get info from the website") is True
        assert self.needs_tool_support("retrieve data from the web") is True
        assert self.needs_tool_support("download from the url") is True

    def test_detects_check_package_pattern(self):
        """Should detect 'check package' patterns as needing tools."""
        assert self.needs_tool_support("check the npm package") is True
        assert self.needs_tool_support("check pypi for the version") is True
        assert self.needs_tool_support("check github for releases") is True

    def test_detects_look_up_package_pattern(self):
        """Should detect 'look up package' patterns as needing tools."""
        assert self.needs_tool_support("look up the package info") is True
        assert self.needs_tool_support("lookup library details") is True
        assert self.needs_tool_support("look up module documentation") is True

    def test_detects_latest_version_pattern(self):
        """Should detect 'latest version' patterns as needing tools."""
        assert self.needs_tool_support("what is the latest version of pandas") is True
        assert self.needs_tool_support("what are the current releases") is True
        assert self.needs_tool_support("what is the newest version") is True

    def test_detects_pypi_npm_patterns(self):
        """Should detect pypi/npm info patterns as needing tools."""
        assert self.needs_tool_support("get pypi info for requests") is True
        assert self.needs_tool_support("npm package details") is True
        assert self.needs_tool_support("github info for repo") is True

    def test_detects_from_website_pattern(self):
        """Should detect 'from website' patterns as needing tools."""
        assert self.needs_tool_support("from the website get info") is True
        assert self.needs_tool_support("get data from the docs") is True
        assert self.needs_tool_support("read from the url") is True

    def test_detects_library_docs_pattern(self):
        """Should detect library documentation patterns as needing tools."""
        assert self.needs_tool_support("scikit-learn documentation") is True
        assert self.needs_tool_support("react docs api") is True
        assert self.needs_tool_support("django documentation reference") is True
        assert self.needs_tool_support("flask api docs") is True
        assert self.needs_tool_support("numpy documentation") is True
        assert self.needs_tool_support("pandas docs") is True

    def test_detects_direct_url(self):
        """Should detect direct URLs as needing tools."""
        assert self.needs_tool_support("https://example.com/docs") is True
        assert self.needs_tool_support("check http://api.example.com") is True
        assert self.needs_tool_support("go to https://github.com/user/repo") is True

    def test_detects_package_registry_with_action(self):
        """Should detect package registry keywords with action verbs."""
        assert self.needs_tool_support("fetch from pypi") is True
        assert self.needs_tool_support("check npm registry") is True
        assert self.needs_tool_support("get from github.com") is True
        assert self.needs_tool_support("find in registry") is True

    # =========================================================================
    # Codebase Exploration Pattern Tests
    # =========================================================================

    def test_detects_file_existence_questions(self):
        """Should detect questions about file existence as needing tools."""
        assert self.needs_tool_support("does the file exist") is True
        assert self.needs_tool_support("is there a config.py file") is True
        assert self.needs_tool_support("does the directory contain tests") is True

    def test_detects_file_content_questions(self):
        """Should detect questions about file contents as needing tools."""
        assert self.needs_tool_support("what is in the config file") is True
        assert self.needs_tool_support("what's inside the directory") is True
        assert self.needs_tool_support("show me the code in main.py") is True

    def test_detects_show_file_commands(self):
        """Should detect 'show file' patterns as needing tools."""
        assert self.needs_tool_support("show me the function") is True
        assert self.needs_tool_support("show the file contents") is True
        assert self.needs_tool_support("show me the class definition") is True

    def test_detects_read_file_commands(self):
        """Should detect 'read file' patterns as needing tools."""
        assert self.needs_tool_support("read the config file") is True
        assert self.needs_tool_support("read code from main.py") is True

    def test_detects_list_files_commands(self):
        """Should detect 'list files' patterns as needing tools."""
        assert self.needs_tool_support("list all files") is True
        assert self.needs_tool_support("list the directories") is True
        assert self.needs_tool_support("list folders in src") is True

    def test_detects_structure_questions(self):
        """Should detect questions about project structure as needing tools."""
        assert self.needs_tool_support("structure of the project") is True
        assert self.needs_tool_support("architecture of the codebase") is True
        assert self.needs_tool_support("layout of the code") is True
        assert self.needs_tool_support("how is the project organized") is True
        assert self.needs_tool_support("how is the code structured") is True

    def test_detects_contains_questions(self):
        """Should detect 'does contain' patterns as needing tools."""
        assert self.needs_tool_support("does it have tests") is True
        assert self.needs_tool_support("does the file contain imports") is True
        assert self.needs_tool_support("does the code include logging") is True
        assert self.needs_tool_support("does it use async") is True

    def test_detects_where_questions(self):
        """Should detect 'where is' patterns as needing tools."""
        assert self.needs_tool_support("where is the main function") is True
        assert self.needs_tool_support("where are the tests") is True
        assert self.needs_tool_support("where does it define the class") is True

    def test_detects_find_in_code_patterns(self):
        """Should detect 'find in code' patterns as needing tools."""
        assert self.needs_tool_support("find errors in the code") is True
        assert self.needs_tool_support("find it inside the project") is True
        assert self.needs_tool_support("find within the codebase") is True

    def test_detects_file_extension_mentions(self):
        """Should detect file extension mentions as needing tools."""
        assert self.needs_tool_support("check the main.py file") is True
        assert self.needs_tool_support("look at config.json") is True
        assert self.needs_tool_support("what's in style.css") is True
        assert self.needs_tool_support("update index.html") is True
        assert self.needs_tool_support("review test.ts") is True
        assert self.needs_tool_support("modify component.tsx") is True

    def test_detects_path_patterns(self):
        """Should detect file path patterns as needing tools."""
        assert self.needs_tool_support("look at src/main") is True
        assert self.needs_tool_support("check frontend/app") is True
        assert self.needs_tool_support("what's in tests/unit") is True

    # =========================================================================
    # Negative Tests - Should NOT Need Tools
    # =========================================================================

    def test_simple_questions_no_tools(self):
        """Simple questions should not need tools."""
        assert self.needs_tool_support("what is Python") is False
        assert self.needs_tool_support("explain async await") is False
        assert self.needs_tool_support("how do decorators work") is False

    def test_coding_questions_no_tools(self):
        """General coding questions should not need tools."""
        assert self.needs_tool_support("write a function to sort a list") is False
        assert self.needs_tool_support("how to create a class") is False
        assert self.needs_tool_support("best practices for error handling") is False

    def test_math_questions_no_tools(self):
        """Math questions should not need tools."""
        assert self.needs_tool_support("calculate 2 + 2") is False
        assert self.needs_tool_support("what is the square root of 16") is False

    def test_greetings_no_tools(self):
        """Greetings should not need tools."""
        assert self.needs_tool_support("hello") is False
        assert self.needs_tool_support("hi there") is False
        assert self.needs_tool_support("good morning") is False

    def test_thanks_no_tools(self):
        """Thank you messages should not need tools."""
        assert self.needs_tool_support("thanks") is False
        assert self.needs_tool_support("thank you") is False

    def test_opinion_questions_no_tools(self):
        """Opinion questions should not need tools."""
        assert self.needs_tool_support("which is better, tabs or spaces") is False
        assert self.needs_tool_support("should I use async") is False

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_empty_string_no_tools(self):
        """Empty string should not need tools."""
        assert self.needs_tool_support("") is False

    def test_whitespace_only_no_tools(self):
        """Whitespace only should not need tools."""
        assert self.needs_tool_support("   ") is False
        assert self.needs_tool_support("\n\t") is False

    def test_case_insensitive_detection(self):
        """Pattern matching should be case insensitive."""
        assert self.needs_tool_support("FETCH THE DOCS") is True
        assert self.needs_tool_support("CHECK PYPI") is True
        assert self.needs_tool_support("Where Is The File") is True

    def test_mixed_content_with_patterns(self):
        """Mixed content with patterns should detect need for tools."""
        assert self.needs_tool_support("I want to know where the tests are") is True
        assert self.needs_tool_support("Can you check the npm package for me") is True

