"""Tests for extended provider validator with availability checks.

Tests the provider availability validation functionality.
Following TDD - these tests are written first, implementation comes after.
"""


from scrappy.cli.validators import (
    validate_provider,
)


class TestProviderValidatorAvailabilityCheck:
    """Tests for provider availability validation."""

    def test_available_provider_passes_check(self):
        """Should pass when provider is in available list."""
        available = ["cerebras", "groq", "gemini"]

        result = validate_provider("cerebras", available_providers=available)
        assert result.is_valid
        assert result.provider == "cerebras"

    def test_unavailable_provider_fails_check(self):
        """Should fail when provider is not in available list."""
        available = ["groq", "gemini"]

        result = validate_provider("cerebras", available_providers=available)
        assert not result.is_valid
        assert "available" in result.error.lower() or "unavailable" in result.error.lower()

    def test_default_no_availability_check(self):
        """Default behavior should not check availability."""
        # Without available_providers, just validate syntax
        result = validate_provider("cerebras")
        assert result.is_valid

    def test_empty_available_list_fails_all(self):
        """Should fail when available list is empty."""
        result = validate_provider("cerebras", available_providers=[])
        assert not result.is_valid

    def test_case_insensitive_availability_check(self):
        """Availability check should be case-insensitive."""
        available = ["cerebras", "groq"]

        result = validate_provider("CEREBRAS", available_providers=available)
        assert result.is_valid
        assert result.provider == "cerebras"

    def test_unknown_provider_not_in_valid_set(self):
        """Should fail for unknown provider even if in available list."""
        # "unknown" is not a valid provider name
        available = ["unknown", "cerebras"]

        result = validate_provider("unknown", available_providers=available)
        assert not result.is_valid
        # Should fail because "unknown" is not in VALID_PROVIDERS

    def test_valid_but_unavailable_shows_available_options(self):
        """Error message should list available providers."""
        available = ["groq", "gemini"]

        result = validate_provider("cerebras", available_providers=available)
        assert not result.is_valid
        # Error should help user know what's available
        assert "groq" in result.error or "available" in result.error.lower()


class TestProviderValidatorEdgeCases:
    """Edge cases for extended provider validation."""

    def test_whitespace_in_available_list_handled(self):
        """Available list with whitespace in names should still work."""
        available = ["cerebras", " groq ", "gemini"]

        result = validate_provider("groq", available_providers=available)
        # Should match despite whitespace
        assert result.is_valid

    def test_single_provider_available(self):
        """Should work with only one provider available."""
        available = ["cerebras"]

        result = validate_provider("cerebras", available_providers=available)
        assert result.is_valid

    def test_all_providers_available(self):
        """Should work when all valid providers are available."""
        available = ["cerebras", "groq", "gemini", "sambanova"]

        for provider in available:
            result = validate_provider(provider, available_providers=available)
            assert result.is_valid

    def test_syntax_error_before_availability_check(self):
        """Syntax errors should be caught before availability check."""
        available = ["cerebras", "groq"]

        # Empty provider should fail before availability check
        result = validate_provider("", available_providers=available)
        assert not result.is_valid
        assert "empty" in result.error.lower()

    def test_invalid_chars_before_availability_check(self):
        """Invalid characters should be caught before availability check."""
        available = ["cerebras", "groq"]

        result = validate_provider("cerebras!", available_providers=available)
        assert not result.is_valid
        assert "character" in result.error.lower() or "invalid" in result.error.lower()


class TestProviderValidatorErrorMessages:
    """Test that error messages are informative."""

    def test_unavailable_error_lists_options(self):
        """Error for unavailable provider should list available options."""
        available = ["groq", "gemini"]

        result = validate_provider("cerebras", available_providers=available)
        assert not result.is_valid
        # Should mention what's available
        assert "groq" in result.error or "gemini" in result.error or "available" in result.error.lower()

    def test_unavailable_error_mentions_provider(self):
        """Error should mention the requested provider."""
        available = ["groq"]

        result = validate_provider("cerebras", available_providers=available)
        assert not result.is_valid
        # Error should mention what was requested
        assert "cerebras" in result.error.lower()


class TestProviderValidatorIntegration:
    """Integration tests for availability checking."""

    def test_validates_and_checks_availability(self):
        """Should validate syntax AND check availability."""
        available = ["cerebras", "groq"]

        # Valid syntax, available
        result = validate_provider("cerebras", available_providers=available)
        assert result.is_valid

        # Valid syntax, not available
        result = validate_provider("gemini", available_providers=available)
        assert not result.is_valid

        # Invalid syntax (should fail before availability check)
        result = validate_provider("", available_providers=available)
        assert not result.is_valid
        assert "empty" in result.error.lower()

    def test_normalized_provider_returned(self):
        """Should return normalized provider name even with availability check."""
        available = ["cerebras", "groq"]

        result = validate_provider("CEREBRAS", available_providers=available)
        assert result.is_valid
        assert result.provider == "cerebras"  # Normalized

    def test_none_available_providers_skips_check(self):
        """None for available_providers should skip availability check."""
        # Should just do syntax validation
        result = validate_provider("cerebras", available_providers=None)
        assert result.is_valid
