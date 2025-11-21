"""
Tests for CLI paths configuration module.
"""

import pytest

class TestSkipDirsProperties:
    """Tests for properties of skip directories."""

    def test_skip_dirs_no_duplicates(self):
        """SKIP_DIRS should not contain duplicates."""
        from src.cli.config.paths import SKIP_DIRS
        # Convert to list to check for duplicates if it isn't already a set
        skip_list = list(SKIP_DIRS)
        assert len(skip_list) == len(set(skip_list)), "SKIP_DIRS contains duplicates"

    def test_skip_dirs_no_slashes(self):
        """Skip directory names should not contain slashes."""
        from src.cli.config.paths import SKIP_DIRS
        for dir_name in SKIP_DIRS:
            assert '/' not in dir_name, f"Entry {dir_name} contains /"
            assert '\\' not in dir_name, f"Entry {dir_name} contains \\"

class TestPathsDocumentation:
    """Tests to verify paths have proper documentation."""

    def test_all_skip_dirs_documented(self):
        """Each skip directory should have documentation."""
        from src.cli.config.paths import SKIP_DIRS, SKIP_DIRS_DESCRIPTIONS
        for dir_name in SKIP_DIRS:
            assert dir_name in SKIP_DIRS_DESCRIPTIONS, (
                f"Directory {dir_name} should be documented in SKIP_DIRS_DESCRIPTIONS"
            )