"""
General user input validation.

Validates user input for chat, commands, and other interactive contexts.
Less strict than API key validation but still security-conscious.

Context-Aware Validation:
- "chat": User queries to the LLM - allow most content
- "command": Slash commands - stricter validation
- "choice": Menu selections - very strict (numbers/letters only)
- "path": File paths - path-specific validation
"""

import re
from typing import Optional

from .sanitizer import (
    ValidationResult,
    sanitize_string,
    strip_control_characters,
    contains_dangerous_patterns,
)


# Default limits
DEFAULT_MAX_LENGTH = 50000  # Chat can be long
COMMAND_MAX_LENGTH = 1000   # Commands should be short
CHOICE_MAX_LENGTH = 10      # Menu choices are tiny


def validate_user_input(
    value: str,
    context: str = "chat",
    max_length: Optional[int] = None,
) -> ValidationResult:
    """
    Validate general user input based on context.

    Args:
        value: User input to validate
        context: Validation context - affects strictness
            - "chat": User queries (lenient)
            - "command": Slash commands (moderate)
            - "choice": Menu selections (strict)
            - "path": File paths (path-aware)
        max_length: Override default max length

    Returns:
        ValidationResult with sanitized value or error

    Example:
        result = validate_user_input(user_query, context="chat")
        if result.is_valid:
            process_query(result.sanitized_value)
    """
    if context == "chat":
        return _validate_chat_input(value, max_length or DEFAULT_MAX_LENGTH)
    elif context == "command":
        return _validate_command_input(value, max_length or COMMAND_MAX_LENGTH)
    elif context == "choice":
        return _validate_choice_input(value, max_length or CHOICE_MAX_LENGTH)
    elif context == "path":
        return _validate_path_input(value, max_length or COMMAND_MAX_LENGTH)
    else:
        # Unknown context - use moderate defaults
        return _validate_chat_input(value, max_length or DEFAULT_MAX_LENGTH)


def _validate_chat_input(value: str, max_length: int) -> ValidationResult:
    """
    Validate chat input (user queries to LLM).

    Chat input is the most lenient - users can ask about anything.
    We only remove truly dangerous content like null bytes.
    """
    if not isinstance(value, str):
        return ValidationResult.invalid(
            f"Expected string, got {type(value).__name__}"
        )

    # Basic emptiness check
    if not value or not value.strip():
        return ValidationResult.invalid("Input cannot be empty")

    # Length check
    if len(value) > max_length:
        return ValidationResult.invalid(
            f"Input too long (max {max_length} chars)"
        )

    # Remove only null bytes and most dangerous control chars
    # Allow newlines, tabs for multiline input
    cleaned = strip_control_characters(value, allow_newlines=True)

    # Remove null bytes explicitly (highest priority threat)
    cleaned = cleaned.replace("\x00", "")

    if not cleaned.strip():
        return ValidationResult.invalid("Input is empty after sanitization")

    return ValidationResult.valid(cleaned)


def _validate_command_input(value: str, max_length: int) -> ValidationResult:
    """
    Validate slash command input.

    Commands are more structured so we can be stricter.
    """
    result = sanitize_string(
        value,
        max_length=max_length,
        allow_newlines=False,  # Commands are single-line
        require_ascii=False,   # Allow unicode in args
        strip_quotes=False,    # Preserve quotes in args
    )

    if not result.is_valid:
        return result

    cleaned = result.sanitized

    # Commands must start with /
    if not cleaned.startswith("/"):
        return ValidationResult.invalid("Commands must start with /")

    return ValidationResult.valid(cleaned)


def _validate_choice_input(value: str, max_length: int) -> ValidationResult:
    """
    Validate menu choice input (1, 2, q, etc.).

    Very strict - only allow alphanumeric characters.
    """
    if not isinstance(value, str):
        return ValidationResult.invalid(
            f"Expected string, got {type(value).__name__}"
        )

    cleaned = value.strip().lower()

    if not cleaned:
        return ValidationResult.invalid("Choice cannot be empty")

    if len(cleaned) > max_length:
        return ValidationResult.invalid("Choice too long")

    # Only allow alphanumeric
    if not re.match(r"^[a-z0-9]+$", cleaned):
        return ValidationResult.invalid("Invalid choice format")

    return ValidationResult.valid(cleaned)


def _validate_path_input(value: str, max_length: int) -> ValidationResult:
    """
    Validate file path input.

    Paths need special handling for traversal attacks.
    """
    if not isinstance(value, str):
        return ValidationResult.invalid(
            f"Expected string, got {type(value).__name__}"
        )

    cleaned = value.strip()

    if not cleaned:
        return ValidationResult.invalid("Path cannot be empty")

    if len(cleaned) > max_length:
        return ValidationResult.invalid(
            f"Path too long (max {max_length} chars)"
        )

    # Check for dangerous patterns
    is_dangerous, reason = contains_dangerous_patterns(cleaned)
    if is_dangerous:
        return ValidationResult.invalid(f"Invalid path: {reason}")

    # Remove control characters
    cleaned = strip_control_characters(cleaned, allow_newlines=False)

    if not cleaned:
        return ValidationResult.invalid("Path is empty after sanitization")

    return ValidationResult.valid(cleaned)


def sanitize_for_display(value: str, max_length: int = 200) -> str:
    """
    Sanitize a string for safe display to user.

    This is for displaying potentially untrusted content
    (e.g., error messages, external data) without XSS-like risks.

    Args:
        value: String to sanitize
        max_length: Truncate to this length

    Returns:
        Safe string for display
    """
    if not value:
        return ""

    if not isinstance(value, str):
        value = str(value)

    # Remove control characters
    cleaned = strip_control_characters(value, allow_newlines=False)

    # Replace null bytes
    cleaned = cleaned.replace("\x00", "")

    # Truncate
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length - 3] + "..."

    return cleaned


def validate_numeric_choice(
    value: str,
    min_val: int = 1,
    max_val: int = 10,
) -> ValidationResult:
    """
    Validate a numeric menu choice.

    Args:
        value: User's choice string
        min_val: Minimum valid number
        max_val: Maximum valid number

    Returns:
        ValidationResult with the number as string if valid
    """
    result = _validate_choice_input(value, CHOICE_MAX_LENGTH)
    if not result.is_valid:
        return result

    cleaned = result.sanitized

    # Check if it's a number
    if not cleaned.isdigit():
        return ValidationResult.invalid(
            f"Please enter a number between {min_val} and {max_val}"
        )

    num = int(cleaned)
    if num < min_val or num > max_val:
        return ValidationResult.invalid(
            f"Please enter a number between {min_val} and {max_val}"
        )

    return ValidationResult.valid(cleaned)
