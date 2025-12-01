"""Base validation infrastructure.

Provides shared validation utilities, patterns, and the ValidationError exception
used across all validation modules.
"""

import re
from typing import Optional


class ValidationError(Exception):
    """Exception raised for validation failures.

    This exception provides context about what failed validation and why,
    enabling better error messages and debugging.

    Attributes:
        field: Name of the field that failed validation (e.g., 'command', 'path').
        value: The invalid value that was provided.
        message: Human-readable description of the validation failure.

    Example:
        >>> raise ValidationError("Path too long", field="path", value="/very/long/...")
        ValidationError: Path too long
    """

    def __init__(self, message: str, field: Optional[str] = None, value: Optional[str] = None):
        """Initialize a ValidationError.

        Args:
            message: Human-readable description of the validation failure.
            field: Optional name of the field that failed validation.
            value: Optional invalid value that was provided.
        """
        super().__init__(message)
        self.field = field
        self.value = value


# Shared regex patterns for validation
CONTROL_CHARS_PATTERN = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
NEWLINE_PATTERN = re.compile(r'[\r\n]')
