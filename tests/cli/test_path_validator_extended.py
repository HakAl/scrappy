"""Tests for extended path validator with semantic checks.

Tests the path existence, directory, and file validation functionality.
Following TDD - these tests are written first, implementation comes after.
"""

import os
import tempfile
import pytest
from pathlib import Path

from src.cli.validators import (
    validate_path,
    PathValidationResult,
)


class TestPathValidatorExistsCheck:
    """Tests for path existence validation."""

    def test_existing_file_passes_exists_check(self, tmp_path):
        """Should pass when file exists and check_exists=True."""
        test_file = tmp_path / "exists.txt"
        test_file.write_text("content")

        result = validate_path(str(test_file), check_exists=True)
        assert result.is_valid
        assert result.path

    def test_nonexistent_file_fails_exists_check(self, tmp_path):
        """Should fail when file doesn't exist and check_exists=True."""
        nonexistent = tmp_path / "does_not_exist.txt"

        result = validate_path(str(nonexistent), check_exists=True)
        assert not result.is_valid
        assert "exist" in result.error.lower()

    def test_nonexistent_path_passes_without_exists_check(self, tmp_path):
        """Should pass syntax validation even if path doesn't exist."""
        nonexistent = tmp_path / "does_not_exist.txt"

        result = validate_path(str(nonexistent), check_exists=False)
        assert result.is_valid

    def test_default_no_exists_check(self, tmp_path):
        """Default behavior should not check existence."""
        nonexistent = tmp_path / "does_not_exist.txt"

        result = validate_path(str(nonexistent))
        assert result.is_valid

    def test_existing_directory_passes_exists_check(self, tmp_path):
        """Should pass when directory exists and check_exists=True."""
        result = validate_path(str(tmp_path), check_exists=True)
        assert result.is_valid


class TestPathValidatorIsDirCheck:
    """Tests for directory-specific validation."""

    def test_directory_passes_is_dir_check(self, tmp_path):
        """Should pass when path is a directory and must_be_dir=True."""
        result = validate_path(str(tmp_path), check_exists=True, must_be_dir=True)
        assert result.is_valid

    def test_file_fails_is_dir_check(self, tmp_path):
        """Should fail when path is a file but must_be_dir=True."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("content")

        result = validate_path(str(test_file), check_exists=True, must_be_dir=True)
        assert not result.is_valid
        assert "directory" in result.error.lower()

    def test_nonexistent_fails_is_dir_check(self, tmp_path):
        """Should fail when path doesn't exist and must_be_dir=True."""
        nonexistent = tmp_path / "nonexistent"

        result = validate_path(str(nonexistent), check_exists=True, must_be_dir=True)
        assert not result.is_valid

    def test_must_be_dir_implies_exists_check(self, tmp_path):
        """must_be_dir should imply check_exists."""
        nonexistent = tmp_path / "nonexistent"

        result = validate_path(str(nonexistent), must_be_dir=True)
        assert not result.is_valid


class TestPathValidatorIsFileCheck:
    """Tests for file-specific validation."""

    def test_file_passes_is_file_check(self, tmp_path):
        """Should pass when path is a file and must_be_file=True."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("content")

        result = validate_path(str(test_file), check_exists=True, must_be_file=True)
        assert result.is_valid

    def test_directory_fails_is_file_check(self, tmp_path):
        """Should fail when path is a directory but must_be_file=True."""
        result = validate_path(str(tmp_path), check_exists=True, must_be_file=True)
        assert not result.is_valid
        assert "file" in result.error.lower()

    def test_nonexistent_fails_is_file_check(self, tmp_path):
        """Should fail when path doesn't exist and must_be_file=True."""
        nonexistent = tmp_path / "nonexistent.txt"

        result = validate_path(str(nonexistent), check_exists=True, must_be_file=True)
        assert not result.is_valid

    def test_must_be_file_implies_exists_check(self, tmp_path):
        """must_be_file should imply check_exists."""
        nonexistent = tmp_path / "nonexistent.txt"

        result = validate_path(str(nonexistent), must_be_file=True)
        assert not result.is_valid


class TestPathValidatorCombinedChecks:
    """Tests for combined validation flags."""

    def test_cannot_be_both_file_and_dir(self):
        """Should raise error if both must_be_file and must_be_dir are True."""
        with pytest.raises((ValueError, TypeError)):
            validate_path("some/path", must_be_file=True, must_be_dir=True)

    def test_existing_file_full_validation(self, tmp_path):
        """Full validation of existing file should pass all checks."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# code")

        result = validate_path(str(test_file), check_exists=True, must_be_file=True)
        assert result.is_valid
        assert "test.py" in result.path

    def test_existing_dir_full_validation(self, tmp_path):
        """Full validation of existing directory should pass all checks."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        result = validate_path(str(subdir), check_exists=True, must_be_dir=True)
        assert result.is_valid
        assert "subdir" in result.path

    def test_syntax_error_takes_precedence(self, tmp_path):
        """Syntax errors should be caught before existence checks."""
        # Empty path should fail before we even check existence
        result = validate_path("", check_exists=True)
        assert not result.is_valid
        assert "empty" in result.error.lower()

    def test_invalid_chars_caught_before_exists_check(self, tmp_path):
        """Invalid characters should be caught before existence check."""
        result = validate_path("file\x00.txt", check_exists=True)
        assert not result.is_valid
        assert "character" in result.error.lower()


class TestPathValidatorEdgeCases:
    """Edge cases for extended path validation."""

    def test_symlink_as_file(self, tmp_path):
        """Symlinks to files should pass must_be_file check."""
        # Create a file and a symlink to it
        real_file = tmp_path / "real.txt"
        real_file.write_text("content")

        link = tmp_path / "link.txt"
        try:
            link.symlink_to(real_file)
            result = validate_path(str(link), check_exists=True, must_be_file=True)
            assert result.is_valid
        except OSError:
            pytest.skip("Symlinks not supported on this platform")

    def test_symlink_as_directory(self, tmp_path):
        """Symlinks to directories should pass must_be_dir check."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        link = tmp_path / "link_dir"
        try:
            link.symlink_to(subdir)
            result = validate_path(str(link), check_exists=True, must_be_dir=True)
            assert result.is_valid
        except OSError:
            pytest.skip("Symlinks not supported on this platform")

    def test_current_directory_reference(self, tmp_path):
        """Current directory (.) should pass is_dir check."""
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = validate_path(".", check_exists=True, must_be_dir=True)
            assert result.is_valid
        finally:
            os.chdir(original_cwd)

    def test_parent_directory_reference(self, tmp_path):
        """Parent directory (..) should pass is_dir check when exists."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        original_cwd = os.getcwd()
        try:
            os.chdir(subdir)
            result = validate_path("..", check_exists=True, must_be_dir=True)
            assert result.is_valid
        finally:
            os.chdir(original_cwd)

    def test_empty_file_passes_file_check(self, tmp_path):
        """Empty files should still pass must_be_file check."""
        empty_file = tmp_path / "empty.txt"
        empty_file.touch()

        result = validate_path(str(empty_file), check_exists=True, must_be_file=True)
        assert result.is_valid

    def test_hidden_file_passes_checks(self, tmp_path):
        """Hidden files (starting with .) should pass checks."""
        hidden = tmp_path / ".hidden"
        hidden.write_text("secret")

        result = validate_path(str(hidden), check_exists=True, must_be_file=True)
        assert result.is_valid

    def test_hidden_directory_passes_checks(self, tmp_path):
        """Hidden directories should pass checks."""
        hidden_dir = tmp_path / ".hidden_dir"
        hidden_dir.mkdir()

        result = validate_path(str(hidden_dir), check_exists=True, must_be_dir=True)
        assert result.is_valid


class TestPathValidatorErrorMessages:
    """Test that error messages are informative."""

    def test_nonexistent_error_includes_path(self, tmp_path):
        """Error for nonexistent path should mention the path."""
        nonexistent = tmp_path / "missing.txt"

        result = validate_path(str(nonexistent), check_exists=True)
        assert not result.is_valid
        # Error should help user understand what's wrong
        assert "exist" in result.error.lower() or "not found" in result.error.lower()

    def test_not_directory_error_is_clear(self, tmp_path):
        """Error when file given but dir expected should be clear."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("content")

        result = validate_path(str(test_file), check_exists=True, must_be_dir=True)
        assert not result.is_valid
        assert "directory" in result.error.lower()

    def test_not_file_error_is_clear(self, tmp_path):
        """Error when dir given but file expected should be clear."""
        result = validate_path(str(tmp_path), check_exists=True, must_be_file=True)
        assert not result.is_valid
        assert "file" in result.error.lower()
