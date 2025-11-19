"""String validation helpers for CLI.

Provides consistent helpers for empty/whitespace string validation
that standardize common patterns across the CLI codebase.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class StringValidationResult:
    """Result of string validation.

    Contains the validated/normalized value and any validation errors.
    Used as the return type for validate_non_empty().

    Attributes:
        is_valid: Whether the string passed validation.
        value: The normalized string value (stripped). Empty if invalid.
        error: Description of what failed validation. None if valid.

    Example:
        >>> result = validate_non_empty("  hello  ")
        >>> result.is_valid
        True
        >>> result.value
        'hello'
    """
    is_valid: bool
    value: str = ""
    error: Optional[str] = None


def is_empty_or_whitespace(value: Optional[str]) -> bool:
    """Check if a string is None, empty, or whitespace-only.

    This is a simple helper to standardize the common pattern of checking
    for empty or whitespace-only strings.

    Args:
        value: The string to check. Can be None.

    Returns:
        True if value is None, empty, or contains only whitespace.
        False otherwise.

    Side Effects:
        None. This is a pure function.

    Example:
        >>> is_empty_or_whitespace(None)
        True
        >>> is_empty_or_whitespace("")
        True
        >>> is_empty_or_whitespace("   ")
        True
        >>> is_empty_or_whitespace("hello")
        False
    """
    if value is None:
        return True
    return not value.strip()


def normalize_string(value: Optional[str]) -> str:
    """Normalize a string by stripping whitespace and handling None.

    Args:
        value: The string to normalize. Can be None.

    Returns:
        The stripped string, or empty string if value is None.

    Side Effects:
        None. This is a pure function.

    Example:
        >>> normalize_string(None)
        ''
        >>> normalize_string("  hello  ")
        'hello'
    """
    if value is None:
        return ""
    return value.strip()


def validate_non_empty(
    value: Optional[str],
    field_name: str = "value"
) -> StringValidationResult:
    """Validate that a string is non-empty and non-whitespace.

    Performs validation including:
    - None check
    - Empty string check
    - Whitespace-only check

    Args:
        value: The string to validate. Can be None.
        field_name: Name of the field for error messages (default: "value").

    Returns:
        StringValidationResult with:
        - is_valid: True if string has content
        - value: Normalized (stripped) string
        - error: Description of failure if invalid

    Side Effects:
        None. This is a pure validation function.

    State Changes:
        None. Does not modify any external state.

    Example:
        >>> result = validate_non_empty("  hello  ")
        >>> if result.is_valid:
        ...     print(f"Value: {result.value}")
        Value: hello

        >>> result = validate_non_empty("", field_name="username")
        >>> result.error
        'username cannot be empty'
    """
    # Handle None
    if value is None:
        return StringValidationResult(
            is_valid=False,
            value="",
            error=f"{field_name} cannot be empty"
        )

    # Strip and check
    normalized = value.strip()
    if not normalized:
        return StringValidationResult(
            is_valid=False,
            value="",
            error=f"{field_name} cannot be empty"
        )

    return StringValidationResult(
        is_valid=True,
        value=normalized,
        error=None
    )
