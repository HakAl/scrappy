"""Provider validation for CLI.

Provides validation for LLM provider names including format checks
and validation against known providers.
"""

import re
from dataclasses import dataclass
from typing import Optional, List

from .base import CONTROL_CHARS_PATTERN


@dataclass
class ProviderValidationResult:
    """Result of provider validation.

    Contains the normalized provider name and any validation errors or warnings.
    Used as the return type for validate_provider().

    Attributes:
        is_valid: Whether the provider passed all validation checks.
        provider: The normalized provider name (lowercase). Empty if invalid.
        error: Description of what failed validation. None if valid.
        warnings: List of non-fatal issues. None if no warnings.

    Example:
        >>> result = validate_provider("Cerebras")
        >>> result.is_valid
        True
        >>> result.provider
        'cerebras'
    """
    is_valid: bool
    provider: str = ""
    error: Optional[str] = None
    warnings: Optional[List[str]] = None


# Valid providers
VALID_PROVIDERS = {
    "cerebras", "groq", "gemini", "cohere", "github_models"
}

# Limits
MAX_PROVIDER_LENGTH = 50


def validate_provider(provider_input: str) -> ProviderValidationResult:
    """Validate a provider name and normalize it.

    Performs comprehensive validation including:
    - None and empty checks
    - Length limits (max 50 characters)
    - Control character detection
    - Space rejection
    - Alphanumeric and underscore only (must start with letter)
    - Validation against VALID_PROVIDERS set

    Args:
        provider_input: The provider name to validate (e.g., "cerebras", "Groq").
            Case-insensitive; will be normalized to lowercase.

    Returns:
        ProviderValidationResult with:
        - is_valid: True if all checks pass
        - provider: Normalized provider name (lowercase)
        - error: Description of failure if invalid

    Side Effects:
        None. This is a pure validation function.

    State Changes:
        None. Does not modify any external state.

    Example:
        >>> result = validate_provider("CEREBRAS")
        >>> result.is_valid
        True
        >>> result.provider
        'cerebras'
    """
    # Handle None input
    if provider_input is None:
        return ProviderValidationResult(
            is_valid=False,
            error="Provider cannot be None"
        )

    # Empty check
    if not provider_input or not provider_input.strip():
        return ProviderValidationResult(
            is_valid=False,
            error="Provider cannot be empty"
        )

    # Strip whitespace
    provider = provider_input.strip()

    # Length check
    if len(provider) > MAX_PROVIDER_LENGTH:
        return ProviderValidationResult(
            is_valid=False,
            error=f"Provider name exceeds maximum length of {MAX_PROVIDER_LENGTH} characters"
        )

    # Check for control characters
    if CONTROL_CHARS_PATTERN.search(provider):
        return ProviderValidationResult(
            is_valid=False,
            error="Provider name contains invalid characters"
        )

    # Check for spaces
    if ' ' in provider:
        return ProviderValidationResult(
            is_valid=False,
            error="Provider name cannot contain spaces"
        )

    # Check for special characters (only alphanumeric and underscore allowed)
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', provider):
        # Check if it starts with a number
        if provider[0].isdigit():
            return ProviderValidationResult(
                is_valid=False,
                error="Provider name cannot start with a number"
            )
        return ProviderValidationResult(
            is_valid=False,
            error="Provider name contains invalid characters"
        )

    # Normalize to lowercase
    provider_lower = provider.lower()

    # Validate against known providers
    if provider_lower not in VALID_PROVIDERS:
        return ProviderValidationResult(
            is_valid=False,
            error=f"Unknown provider: {provider_lower}. Valid providers are: {', '.join(sorted(VALID_PROVIDERS))}"
        )

    return ProviderValidationResult(
        is_valid=True,
        provider=provider_lower
    )
