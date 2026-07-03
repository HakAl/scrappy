r"""
Core string sanitization and dangerous pattern detection.

This module provides the foundation for all input validation in scrappy.
It detects and handles:
- Path traversal attacks (../, ..\)
- Shell injection patterns (;, |, $, &, `, etc.)
- Null bytes and control characters
- Unicode normalization issues
- Encoding attacks

Security Principles:
- Deny by default: Unknown patterns are suspicious
- Defense in depth: Multiple layers of validation
- Fail closed: On error, reject the input
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass(frozen=True)
class ValidationResult:
    """
    Result of validation/sanitization operation.

    Immutable to prevent accidental modification of security-critical data.

    Attributes:
        is_valid: Whether the input passed validation
        error: Human-readable error message if invalid
        sanitized_value: Cleaned value if valid, None if invalid
        warnings: Non-fatal issues detected (for logging)
    """
    is_valid: bool
    error: Optional[str] = None
    sanitized_value: Optional[str] = None
    warnings: Tuple[str, ...] = ()

    @property
    def sanitized(self) -> str:
        """Sanitized value of a valid result.

        Valid results always carry a sanitized value; calling this on an
        invalid result is a programming error and raises instead of
        letting None leak into string handling.
        """
        if self.sanitized_value is None:
            raise ValueError(
                "sanitized value requested from an invalid ValidationResult"
            )
        return self.sanitized_value

    @property
    def error_message(self) -> str:
        """Error message of an invalid result.

        Invalid results always carry an error; calling this on a valid
        result is a programming error and raises instead of letting None
        leak into user-facing output.
        """
        if self.error is None:
            raise ValueError(
                "error message requested from a valid ValidationResult"
            )
        return self.error

    @staticmethod
    def valid(value: str, warnings: Optional[List[str]] = None) -> "ValidationResult":
        """Create a valid result with sanitized value."""
        return ValidationResult(
            is_valid=True,
            sanitized_value=value,
            warnings=tuple(warnings) if warnings else (),
        )

    @staticmethod
    def invalid(error: str) -> "ValidationResult":
        """Create an invalid result with error message."""
        return ValidationResult(is_valid=False, error=error)


# Path traversal patterns
PATH_TRAVERSAL_PATTERNS = [
    r"\.\./",           # Unix parent dir
    r"\.\.\\",          # Windows parent dir
    r"\.\.$",           # Trailing ..
    r"^/",              # Absolute Unix path
    r"^[A-Za-z]:",      # Absolute Windows path (C:, D:, etc.)
    r"^\\\\",           # UNC path
    r"~",               # Home directory expansion
]

# Shell metacharacters that could enable injection
SHELL_METACHARACTERS = [
    ";",    # Command separator
    "|",    # Pipe
    "&",    # Background/AND
    "$",    # Variable expansion
    "`",    # Command substitution
    "$(", # Command substitution
    "${",   # Variable expansion
    ">",    # Redirect output
    "<",    # Redirect input
    ">>",   # Append output
    "<<",   # Here document
    "||",   # OR
    "&&",   # AND
    "\n",   # Newline (command separator)
    "\r",   # Carriage return
]

# Control characters (ASCII 0-31 except tab, newline, carriage return for some contexts)
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Null byte - particularly dangerous
NULL_BYTE_PATTERN = re.compile(r"\x00")

# Unicode normalization attack patterns
UNICODE_CONFUSABLES = [
    "\u2024",  # One dot leader (looks like .)
    "\u2025",  # Two dot leader (looks like ..)
    "\u2026",  # Horizontal ellipsis
    "\uff0f",  # Fullwidth solidus (looks like /)
    "\uff3c",  # Fullwidth reverse solidus (looks like \)
]


def contains_dangerous_patterns(value: str) -> Tuple[bool, str]:
    """
    Check if string contains patterns that could enable attacks.

    Args:
        value: String to check

    Returns:
        Tuple of (is_dangerous, reason)
        - (True, reason) if dangerous pattern found
        - (False, "") if safe
    """
    if not value:
        return False, ""

    # Check for null bytes first - always dangerous
    if NULL_BYTE_PATTERN.search(value):
        return True, "Contains null byte"

    # Check for control characters
    if CONTROL_CHAR_PATTERN.search(value):
        return True, "Contains control characters"

    # Check for path traversal
    for pattern in PATH_TRAVERSAL_PATTERNS:
        if re.search(pattern, value, re.IGNORECASE):
            return True, "Contains path traversal pattern"

    # Check for shell metacharacters
    for char in SHELL_METACHARACTERS:
        if char in value:
            return True, "Contains shell metacharacter"

    # Check for unicode confusables
    for confusable in UNICODE_CONFUSABLES:
        if confusable in value:
            return True, "Contains suspicious unicode character"

    return False, ""


def strip_control_characters(value: str, allow_newlines: bool = False) -> str:
    """
    Remove control characters from string.

    Args:
        value: String to clean
        allow_newlines: If True, preserve newlines and carriage returns

    Returns:
        String with control characters removed
    """
    if not value:
        return value

    if allow_newlines:
        # Remove all control chars except \t, \n, \r
        pattern = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    else:
        # Remove all control chars including \n, \r but keep \t
        pattern = re.compile(r"[\x00-\x08\x0a-\x0c\x0e-\x1f\x7f]")

    return pattern.sub("", value)


def normalize_unicode(value: str) -> str:
    """
    Normalize unicode to NFC form and replace confusables.

    NFC normalization ensures consistent representation of characters
    that can be encoded multiple ways (e.g., e + combining acute = e).

    Args:
        value: String to normalize

    Returns:
        NFC-normalized string with confusables replaced
    """
    if not value:
        return value

    # NFC normalization
    normalized = unicodedata.normalize("NFC", value)

    # Replace known confusables with ASCII equivalents
    replacements = {
        "\u2024": ".",   # One dot leader
        "\u2025": "..",  # Two dot leader
        "\u2026": "...", # Horizontal ellipsis
        "\uff0f": "/",   # Fullwidth solidus
        "\uff3c": "\\",  # Fullwidth reverse solidus
    }
    for confusable, replacement in replacements.items():
        normalized = normalized.replace(confusable, replacement)

    return normalized


def is_ascii_printable(value: str, allow_extended: bool = False) -> bool:
    """
    Check if string contains only ASCII printable characters.

    Args:
        value: String to check
        allow_extended: If True, allow extended ASCII (128-255)

    Returns:
        True if all characters are printable ASCII
    """
    if not value:
        return True

    if allow_extended:
        # Allow 32-126 (printable) and 128-255 (extended)
        return all(32 <= ord(c) <= 126 or 128 <= ord(c) <= 255 for c in value)
    else:
        # Strict ASCII printable only (32-126)
        return all(32 <= ord(c) <= 126 for c in value)


def sanitize_string(
    value: str,
    max_length: int = 10000,
    allow_newlines: bool = False,
    require_ascii: bool = False,
    strip_quotes: bool = False,
) -> ValidationResult:
    """
    Sanitize a string value for safe use.

    This is the main entry point for string sanitization. It performs:
    1. Type and emptiness checks
    2. Length validation
    3. Unicode normalization
    4. Control character removal
    5. Dangerous pattern detection
    6. Optional ASCII enforcement

    Args:
        value: String to sanitize
        max_length: Maximum allowed length (DoS protection)
        allow_newlines: If True, preserve newlines in output
        require_ascii: If True, reject non-ASCII characters
        strip_quotes: If True, remove surrounding quotes

    Returns:
        ValidationResult with sanitized value or error
    """
    # Type check
    if not isinstance(value, str):
        return ValidationResult.invalid(
            f"Expected string, got {type(value).__name__}"
        )

    # Strip surrounding whitespace
    cleaned = value.strip()

    # Emptiness check
    if not cleaned:
        return ValidationResult.invalid("Value cannot be empty")

    # Strip surrounding quotes if requested
    if strip_quotes:
        if (cleaned.startswith('"') and cleaned.endswith('"')) or \
           (cleaned.startswith("'") and cleaned.endswith("'")):
            cleaned = cleaned[1:-1].strip()
            if not cleaned:
                return ValidationResult.invalid("Value cannot be empty after removing quotes")

    # Length check (before any processing to prevent DoS)
    if len(cleaned) > max_length:
        return ValidationResult.invalid(
            f"Value too long (max {max_length} chars, got {len(cleaned)})"
        )

    # Normalize unicode
    cleaned = normalize_unicode(cleaned)

    # Check for dangerous patterns AFTER normalization
    # (normalization might reveal hidden patterns)
    is_dangerous, reason = contains_dangerous_patterns(cleaned)
    if is_dangerous:
        return ValidationResult.invalid(f"Dangerous input: {reason}")

    # Remove control characters
    cleaned = strip_control_characters(cleaned, allow_newlines=allow_newlines)

    # ASCII check if required
    if require_ascii and not is_ascii_printable(cleaned):
        return ValidationResult.invalid("Value must contain only ASCII characters")

    # Final emptiness check after all processing
    if not cleaned.strip():
        return ValidationResult.invalid("Value is empty after sanitization")

    return ValidationResult.valid(cleaned)
