"""
Input validation and sanitization module.

Provides centralized, secure validation for all user input in scrappy.
This is a security-critical module - all user input should flow through here.

Architecture:
- sanitizer.py: Core dangerous pattern detection and string sanitization
- api_key.py: API key specific validation (uses sanitizer)
- user_input.py: General user input validation (uses sanitizer)

Usage:
    from scrappy.infrastructure.validation import (
        validate_api_key,
        validate_user_input,
        sanitize_string,
        ValidationResult,
    )

    # Validate API key
    result = validate_api_key(user_provided_key)
    if not result.is_valid:
        print(f"Invalid key: {result.error}")
    else:
        safe_key = result.sanitized_value

    # Validate general input
    result = validate_user_input(user_query, context="chat")
    if result.is_valid:
        process(result.sanitized_value)
"""

from .sanitizer import (
    ValidationResult,
    sanitize_string,
    contains_dangerous_patterns,
    strip_control_characters,
)
from .api_key import validate_api_key, is_placeholder_value, validate_env_var_name
from .user_input import validate_user_input, sanitize_for_display

__all__ = [
    # Core types
    "ValidationResult",
    # Sanitizer functions
    "sanitize_string",
    "contains_dangerous_patterns",
    "strip_control_characters",
    # API key validation
    "validate_api_key",
    "validate_env_var_name",
    "is_placeholder_value",
    # User input validation
    "validate_user_input",
    "sanitize_for_display",
]
