"""
API key validation.

Validates API keys before storage or use. API keys are particularly
sensitive because they grant access to external services and are
stored persistently.

Threat Model:
- Path traversal: Attacker provides "../../../etc/passwd" as key
- Shell injection: Attacker provides "key; rm -rf /" as key
- Placeholder values: User forgets to replace "your-api-key-here"
- Encoding attacks: Hidden characters that bypass checks
- Storage corruption: Newlines, null bytes corrupt config file
"""

import re
from typing import Set

from .sanitizer import ValidationResult, sanitize_string


# Minimum and maximum key lengths
MIN_KEY_LENGTH = 10
MAX_KEY_LENGTH = 500

# Known placeholder patterns (case-insensitive)
PLACEHOLDER_PATTERNS: Set[str] = {
    # Generic placeholders
    "test",
    "testing",
    "xxx",
    "xxxx",
    "xxxxx",
    "placeholder",
    "changeme",
    "change-me",
    "change_me",
    "replace-me",
    "replace_me",
    "your-key",
    "your_key",
    "your-api-key",
    "your_api_key",
    "your-api-key-here",
    "your_api_key_here",
    "api-key",
    "api_key",
    "api-key-here",
    "api_key_here",
    "insert-key",
    "insert_key",
    "insert-key-here",
    "insert_key_here",
    "key-here",
    "key_here",
    "put-key-here",
    "put_key_here",
    "enter-key",
    "enter_key",
    "enter-key-here",
    "enter_key_here",
    "example",
    "example-key",
    "example_key",
    "sample",
    "sample-key",
    "sample_key",
    "demo",
    "demo-key",
    "demo_key",
    "fake",
    "fake-key",
    "fake_key",
    "dummy",
    "dummy-key",
    "dummy_key",
    "temp",
    "temp-key",
    "temp_key",
    "temporary",
    "none",
    "null",
    "undefined",
    "todo",
    "fixme",
    "secret",
    "password",
    "pass",
}

# Regex patterns for placeholder detection
PLACEHOLDER_REGEX_PATTERNS = [
    r"^x+$",                    # Just x's
    r"^0+$",                    # Just zeros
    r"^1+$",                    # Just ones
    r"^\.+$",                   # Just dots
    r"^\*+$",                   # Just asterisks
    r"^#+$",                    # Just hashes
    r"^-+$",                    # Just dashes
    r"^_+$",                    # Just underscores
    r"^0{8}-0{4}-0{4}-0{4}-0{12}$",  # All-zeros UUID placeholder
    r"^sk-[x\.]+$",             # OpenAI placeholder pattern
    r"^gsk_[x\.]+$",            # Groq placeholder pattern
]


def is_placeholder_value(value: str) -> bool:
    """
    Check if value appears to be a placeholder rather than real key.

    Args:
        value: The key value to check

    Returns:
        True if value appears to be a placeholder
    """
    if not value:
        return True

    # Normalize for comparison
    normalized = value.lower().strip()

    # Check exact matches
    if normalized in PLACEHOLDER_PATTERNS:
        return True

    # Check regex patterns
    for pattern in PLACEHOLDER_REGEX_PATTERNS:
        if re.match(pattern, normalized):
            return True

    # Check if all same character (e.g., "aaaaaaaaaa")
    if len(set(normalized)) == 1 and len(normalized) >= MIN_KEY_LENGTH:
        return True

    # Check for repeated short patterns (e.g., "abcabcabc")
    if len(normalized) >= 9:
        for pattern_len in range(1, 4):
            pattern = normalized[:pattern_len]
            if pattern * (len(normalized) // pattern_len) == normalized[:len(pattern) * (len(normalized) // pattern_len)]:
                if len(normalized) // pattern_len >= 3:
                    return True

    return False


def validate_api_key(value: str) -> ValidationResult:
    """
    Validate an API key value.

    Performs comprehensive validation including:
    - Basic sanitization (dangerous patterns, control chars)
    - Length validation (10-500 chars)
    - ASCII-only enforcement
    - Placeholder detection
    - Quote stripping

    Args:
        value: The API key to validate

    Returns:
        ValidationResult with sanitized key or error message

    Example:
        result = validate_api_key(user_input)
        if result.is_valid:
            store_key(result.sanitized_value)
        else:
            show_error(result.error)
    """
    # First, apply base sanitization with strict settings
    result = sanitize_string(
        value,
        max_length=MAX_KEY_LENGTH,
        allow_newlines=False,  # API keys should never have newlines
        require_ascii=True,    # API keys should be ASCII only
        strip_quotes=True,     # Users often copy keys with quotes
    )

    if not result.is_valid:
        return result

    cleaned = result.sanitized

    # Additional length check for minimum
    if len(cleaned) < MIN_KEY_LENGTH:
        return ValidationResult.invalid(
            f"API key too short (min {MIN_KEY_LENGTH} chars, got {len(cleaned)})"
        )

    # Check for placeholder values
    if is_placeholder_value(cleaned):
        return ValidationResult.invalid(
            "Value appears to be a placeholder, not a real API key"
        )

    # Check for spaces (API keys typically don't have spaces)
    if " " in cleaned:
        return ValidationResult.invalid(
            "API key should not contain spaces"
        )

    # Check for common invalid characters in API keys
    # Most API keys are alphanumeric with limited special chars
    invalid_chars = set()
    allowed_special = set("-_.")  # Common in API keys
    for char in cleaned:
        if not (char.isalnum() or char in allowed_special):
            invalid_chars.add(char)

    if invalid_chars:
        # Just warn, don't reject - some providers use unusual chars
        warnings = [f"Unusual characters in key: {invalid_chars}"]
        return ValidationResult.valid(cleaned, warnings)

    return ValidationResult.valid(cleaned)


def validate_env_var_name(name: str) -> ValidationResult:
    """
    Validate an environment variable name.

    Environment variable names must be:
    - Non-empty
    - Alphanumeric with underscores
    - Not starting with a digit

    Args:
        name: Environment variable name to validate

    Returns:
        ValidationResult with validated name or error
    """
    if not name:
        return ValidationResult.invalid("Environment variable name cannot be empty")

    if not isinstance(name, str):
        return ValidationResult.invalid(
            f"Expected string, got {type(name).__name__}"
        )

    cleaned = name.strip()

    if not cleaned:
        return ValidationResult.invalid("Environment variable name cannot be empty")

    # Check format: alphanumeric and underscores, not starting with digit
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", cleaned):
        return ValidationResult.invalid(
            "Environment variable name must be alphanumeric with underscores, "
            "not starting with a digit"
        )

    # Check reasonable length
    if len(cleaned) > 100:
        return ValidationResult.invalid(
            "Environment variable name too long (max 100 chars)"
        )

    return ValidationResult.valid(cleaned)
