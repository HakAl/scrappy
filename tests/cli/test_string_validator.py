"""Tests for string validation helpers.

Tests the validation helpers for empty/whitespace string checks
that standardize common patterns across the CLI.
"""

import pytest
from src.cli.validators.string import (
    is_empty_or_whitespace,
    normalize_string,
    StringValidationResult,
    validate_non_empty,
)


class TestIsEmptyOrWhitespace:
    """Tests for is_empty_or_whitespace() helper."""



    def test_whitespace_only_is_empty(self):
        """Whitespace-only string should be treated as empty."""
        assert is_empty_or_whitespace("   ") is True
        assert is_empty_or_whitespace("\t") is True
        assert is_empty_or_whitespace("\n") is True
        assert is_empty_or_whitespace("  \t\n  ") is True

    def test_non_empty_string_is_not_empty(self):
        """Non-empty string should not be treated as empty."""
        assert is_empty_or_whitespace("hello") is False
        assert is_empty_or_whitespace("a") is False
        assert is_empty_or_whitespace("0") is False

    def test_string_with_spaces_is_not_empty(self):
        """String with spaces around content should not be empty."""
        assert is_empty_or_whitespace("  hello  ") is False
        assert is_empty_or_whitespace("\tfoo\n") is False


class TestNormalizeString:
    """Tests for normalize_string() helper."""



    def test_strips_whitespace(self):
        """Should strip leading and trailing whitespace."""
        assert normalize_string("  hello  ") == "hello"
        assert normalize_string("\tfoo\n") == "foo"


    def test_whitespace_only_returns_empty(self):
        """Whitespace-only should normalize to empty string."""
        assert normalize_string("   ") == ""
        assert normalize_string("\t\n") == ""


class TestValidateNonEmpty:
    """Tests for validate_non_empty() function."""

    def test_valid_string_is_valid(self):
        """Non-empty string should be valid."""
        result = validate_non_empty("hello")
        assert result.is_valid is True
        assert result.value == "hello"
        assert result.error is None

    def test_string_with_spaces_is_valid(self):
        """String with content and spaces should be valid."""
        result = validate_non_empty("  hello  ")
        assert result.is_valid is True
        assert result.value == "hello"  # Should be stripped

    def test_none_is_invalid(self):
        """None should be invalid."""
        result = validate_non_empty(None)
        assert result.is_valid is False
        assert result.error is not None
        assert "empty" in result.error.lower() or "none" in result.error.lower()

    def test_empty_string_is_invalid(self):
        """Empty string should be invalid."""
        result = validate_non_empty("")
        assert result.is_valid is False
        assert "empty" in result.error.lower()

    def test_whitespace_only_is_invalid(self):
        """Whitespace-only string should be invalid."""
        result = validate_non_empty("   ")
        assert result.is_valid is False
        assert "empty" in result.error.lower()

    def test_custom_field_name_in_error(self):
        """Custom field name should appear in error message."""
        result = validate_non_empty("", field_name="username")
        assert result.is_valid is False
        assert "username" in result.error.lower()

    def test_default_field_name_is_value(self):
        """Default field name should be 'value'."""
        result = validate_non_empty("")
        assert "value" in result.error.lower()


class TestStringValidationResult:
    """Tests for StringValidationResult dataclass."""

    def test_result_has_required_attributes(self):
        """Result should have is_valid, value, and error."""
        result = StringValidationResult(
            is_valid=True,
            value="test",
            error=None
        )
        assert result.is_valid is True
        assert result.value == "test"
        assert result.error is None

    def test_invalid_result_has_error(self):
        """Invalid result should contain error message."""
        result = StringValidationResult(
            is_valid=False,
            value="",
            error="Value cannot be empty"
        )
        assert result.is_valid is False
        assert result.error is not None


class TestStringValidatorIntegration:
    """Integration tests for string validators."""


    def test_validator_is_pure_function(self):
        """Validator should have no side effects."""
        result1 = validate_non_empty("test")
        result2 = validate_non_empty("test")

        assert result1.is_valid == result2.is_valid
        assert result1.value == result2.value

    def test_helper_functions_are_consistent(self):
        """Helper functions should be consistent with validate_non_empty."""
        test_cases = [None, "", "   ", "hello", "  hello  "]

        for value in test_cases:
            is_empty = is_empty_or_whitespace(value)
            result = validate_non_empty(value)

            # If is_empty returns True, validation should fail
            if is_empty:
                assert not result.is_valid
            else:
                assert result.is_valid
