"""Tests for API key validation.

Tests API key validation including:
- Format validation (length, characters)
- Placeholder detection
- Security checks (inherited from sanitizer)
- Environment variable name validation
"""

import pytest

from scrappy.infrastructure.validation.api_key import (
    validate_api_key,
    validate_env_var_name,
    is_placeholder_value,
    MIN_KEY_LENGTH,
    MAX_KEY_LENGTH,
)


class TestValidateApiKey:
    """Tests for validate_api_key function."""

    def test_valid_key_passes(self):
        """Valid API key passes validation."""
        result = validate_api_key("sk-1234567890abcdef")
        assert result.is_valid is True
        assert result.sanitized_value == "sk-1234567890abcdef"

    def test_valid_key_with_dashes_and_underscores(self):
        """Keys with dashes and underscores pass."""
        result = validate_api_key("gsk_abc123-def456_ghi789")
        assert result.is_valid is True

    def test_too_short_fails(self):
        """Key shorter than MIN_KEY_LENGTH fails."""
        result = validate_api_key("short")
        assert result.is_valid is False
        assert "short" in result.error.lower()

    def test_too_long_fails(self):
        """Key longer than MAX_KEY_LENGTH fails."""
        result = validate_api_key("x" * (MAX_KEY_LENGTH + 1))
        assert result.is_valid is False
        assert "long" in result.error.lower()

    def test_empty_string_fails(self):
        """Empty string fails validation."""
        result = validate_api_key("")
        assert result.is_valid is False

    def test_whitespace_only_fails(self):
        """Whitespace-only string fails validation."""
        result = validate_api_key("   ")
        assert result.is_valid is False

    def test_spaces_in_key_fails(self):
        """Spaces within key fail validation."""
        result = validate_api_key("sk-1234 5678 9abc")
        assert result.is_valid is False
        assert "space" in result.error.lower()

    def test_strips_surrounding_quotes(self):
        """Surrounding quotes are stripped."""
        result = validate_api_key('"sk-1234567890abcdef"')
        assert result.is_valid is True
        assert result.sanitized_value == "sk-1234567890abcdef"

    def test_strips_surrounding_single_quotes(self):
        """Surrounding single quotes are stripped."""
        result = validate_api_key("'sk-1234567890abcdef'")
        assert result.is_valid is True
        assert result.sanitized_value == "sk-1234567890abcdef"

    # Security tests (inherited from sanitizer)
    def test_path_traversal_fails(self):
        """Path traversal attempt fails."""
        result = validate_api_key("../../../etc/passwd")
        assert result.is_valid is False
        assert "dangerous" in result.error.lower()

    def test_shell_injection_fails(self):
        """Shell injection attempt fails."""
        result = validate_api_key("key123; rm -rf /")
        assert result.is_valid is False
        assert "dangerous" in result.error.lower()

    def test_null_byte_fails(self):
        """Null byte fails."""
        result = validate_api_key("sk-1234567890\x00abcdef")
        assert result.is_valid is False

    def test_newline_fails(self):
        """Newline fails."""
        result = validate_api_key("sk-1234567890\nabcdef")
        assert result.is_valid is False

    def test_non_ascii_fails(self):
        """Non-ASCII characters fail."""
        # Use actual unicode (smart quote)
        result = validate_api_key("sk-1234567890\u201c")
        assert result.is_valid is False
        assert "ascii" in result.error.lower()

    # Placeholder detection tests - using exact matches in PLACEHOLDER_PATTERNS
    @pytest.mark.parametrize("placeholder", [
        "xxxxxxxxxxxx",      # All x's (repeated char pattern)
        "placeholder",       # Exact match in set
        "your-api-key",      # Exact match in set
        "your_api_key_here", # Exact match in set
        "0000000000",        # All zeros (regex pattern)
        "1111111111",        # All ones (regex pattern)
        "abcabcabcabc",      # Repeated pattern
    ])
    def test_placeholder_values_fail(self, placeholder):
        """Known placeholder values fail validation."""
        result = validate_api_key(placeholder)
        assert result.is_valid is False
        assert "placeholder" in result.error.lower()

    # Short placeholders fail due to length check (also acceptable)
    @pytest.mark.parametrize("short_placeholder", [
        "test",
        "testing",
        "xxx",
        "demo",
        "temp",
        "none",
        "null",
    ])
    def test_short_placeholders_fail_validation(self, short_placeholder):
        """Short placeholder values fail validation (too short)."""
        result = validate_api_key(short_placeholder)
        assert result.is_valid is False
        # They fail due to length, which is fine

    def test_repeated_character_fails(self):
        """String of same character (e.g., 'aaaaaaaaaa') fails."""
        result = validate_api_key("a" * 20)
        assert result.is_valid is False
        assert "placeholder" in result.error.lower()

    def test_repeated_pattern_fails(self):
        """Repeated short pattern (e.g., 'abcabcabc') fails."""
        result = validate_api_key("abc" * 10)
        assert result.is_valid is False
        assert "placeholder" in result.error.lower()

    def test_all_zeros_fails(self):
        """String of zeros fails as placeholder."""
        result = validate_api_key("0" * 20)
        assert result.is_valid is False

    def test_valid_looking_key_passes(self):
        """Key that looks real passes."""
        # Real API keys have entropy
        result = validate_api_key("sk-proj-abc123XYZ789defGHI456")
        assert result.is_valid is True

    def test_uuid_format_key_passes(self):
        """UUID-format API keys should pass (e.g., Sambanova uses UUIDs)."""
        # Fake UUID with entropy - not all zeros (regression test)
        result = validate_api_key("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        assert result.is_valid is True

    def test_placeholder_uuid_fails(self):
        """All-zeros UUID should fail as placeholder."""
        result = validate_api_key("00000000-0000-0000-0000-000000000000")
        assert result.is_valid is False
        assert "placeholder" in result.error.lower()


class TestIsPlaceholderValue:
    """Tests for is_placeholder_value function."""

    def test_known_placeholders(self):
        """Known placeholder strings are detected."""
        assert is_placeholder_value("test") is True
        assert is_placeholder_value("changeme") is True
        assert is_placeholder_value("your-api-key-here") is True

    def test_case_insensitive(self):
        """Placeholder detection is case-insensitive."""
        assert is_placeholder_value("TEST") is True
        assert is_placeholder_value("CHANGEME") is True

    def test_empty_is_placeholder(self):
        """Empty string is considered placeholder."""
        assert is_placeholder_value("") is True

    def test_real_key_not_placeholder(self):
        """Real-looking key is not placeholder."""
        assert is_placeholder_value("sk-proj-abc123XYZ789") is False

    def test_repeated_chars_is_placeholder(self):
        """String of same character is placeholder."""
        assert is_placeholder_value("x" * 15) is True
        assert is_placeholder_value("a" * 20) is True

    def test_regex_patterns(self):
        """Regex patterns detect special placeholders."""
        assert is_placeholder_value("0000000000") is True  # All zeros
        assert is_placeholder_value("1111111111") is True  # All ones
        assert is_placeholder_value("..........") is True  # All dots


class TestValidateEnvVarName:
    """Tests for validate_env_var_name function."""

    def test_valid_env_var_name(self):
        """Valid env var name passes."""
        result = validate_env_var_name("GROQ_API_KEY")
        assert result.is_valid is True
        assert result.sanitized_value == "GROQ_API_KEY"

    def test_lowercase_passes(self):
        """Lowercase env var name passes."""
        result = validate_env_var_name("api_key")
        assert result.is_valid is True

    def test_mixed_case_passes(self):
        """Mixed case passes."""
        result = validate_env_var_name("Api_Key_123")
        assert result.is_valid is True

    def test_starts_with_underscore_passes(self):
        """Starting with underscore passes."""
        result = validate_env_var_name("_PRIVATE_KEY")
        assert result.is_valid is True

    def test_empty_fails(self):
        """Empty string fails."""
        result = validate_env_var_name("")
        assert result.is_valid is False

    def test_starts_with_digit_fails(self):
        """Starting with digit fails."""
        result = validate_env_var_name("123_KEY")
        assert result.is_valid is False

    def test_contains_dash_fails(self):
        """Dash fails (not alphanumeric or underscore)."""
        result = validate_env_var_name("API-KEY")
        assert result.is_valid is False

    def test_contains_space_fails(self):
        """Space fails."""
        result = validate_env_var_name("API KEY")
        assert result.is_valid is False

    def test_too_long_fails(self):
        """Very long name fails."""
        result = validate_env_var_name("A" * 150)
        assert result.is_valid is False
        assert "long" in result.error.lower()
