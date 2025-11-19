"""Path validation for CLI.

Provides validation for file and directory paths including length checks,
character validation, and security checks.
"""

import os
import re
from dataclasses import dataclass
from typing import Optional, List

from .base import CONTROL_CHARS_PATTERN, NEWLINE_PATTERN


@dataclass
class PathValidationResult:
    """Result of path validation.

    Contains the normalized path and any validation errors or warnings.
    Used as the return type for validate_path().

    Attributes:
        is_valid: Whether the path passed all validation checks.
        path: The normalized path with cleaned separators. Empty if invalid.
        error: Description of what failed validation. None if valid.
        warnings: List of non-fatal issues (e.g., excessive traversal). None if no warnings.

    Example:
        >>> result = validate_path("src/cli/validators.py")
        >>> result.is_valid
        True
        >>> result.path
        'src/cli/validators.py'
    """
    is_valid: bool
    path: str = ""
    error: Optional[str] = None
    warnings: Optional[List[str]] = None


# Limits
MAX_PATH_LENGTH = 500
MAX_PATH_COMPONENT_LENGTH = 255

# Invalid characters patterns
WINDOWS_INVALID_CHARS = re.compile(r'[<>"|?*]')
GLOB_CHARS_PATTERN = re.compile(r'[*?]')


def validate_path(
    path_input: str,
    check_exists: bool = False,
    must_be_dir: bool = False,
    must_be_file: bool = False
) -> PathValidationResult:
    """Validate a file or directory path and normalize it.

    Performs comprehensive validation including:
    - None and empty checks
    - Length limits (max 500 characters total, 255 per component)
    - Control character and newline detection
    - Glob character rejection (use actual paths, not patterns)
    - Windows-invalid character detection
    - Path traversal security check (max 3 levels of ..)
    - Optional existence check
    - Optional directory/file type check

    Args:
        path_input: The path string to validate. Can be relative or absolute.
            Forward and back slashes are normalized for the current OS.
        check_exists: If True, verify the path exists on the filesystem.
        must_be_dir: If True, verify the path is a directory (implies check_exists).
        must_be_file: If True, verify the path is a file (implies check_exists).

    Returns:
        PathValidationResult with:
        - is_valid: True if all checks pass
        - path: Normalized path with cleaned separators
        - error: Description of failure if invalid
        - warnings: Security concerns like excessive traversal

    Raises:
        ValueError: If both must_be_dir and must_be_file are True.

    Side Effects:
        None. This is a pure validation function.

    State Changes:
        None. Does not modify any external state or files.

    Example:
        >>> result = validate_path("src//cli/validators.py")
        >>> result.path
        'src/cli/validators.py'

        >>> result = validate_path("/tmp/mydir", must_be_dir=True)
        >>> result.is_valid  # True if /tmp/mydir exists and is a directory
    """
    # Check for conflicting options
    if must_be_dir and must_be_file:
        raise ValueError("Path cannot be both a directory and a file")
    warnings: List[str] = []

    # Handle None input
    if path_input is None:
        return PathValidationResult(
            is_valid=False,
            error="Path cannot be None"
        )

    # Empty check
    if not path_input or not path_input.strip():
        return PathValidationResult(
            is_valid=False,
            error="Path cannot be empty"
        )

    path = path_input.strip()

    # Length check
    if len(path) > MAX_PATH_LENGTH:
        return PathValidationResult(
            is_valid=False,
            error=f"Path exceeds maximum length of {MAX_PATH_LENGTH} characters"
        )

    # Check for control characters (including null)
    if CONTROL_CHARS_PATTERN.search(path):
        return PathValidationResult(
            is_valid=False,
            error="Path contains invalid control characters"
        )

    # Check for newlines
    if NEWLINE_PATTERN.search(path):
        return PathValidationResult(
            is_valid=False,
            error="Path cannot contain newline characters"
        )

    # Check for glob characters (not valid in actual file paths)
    if GLOB_CHARS_PATTERN.search(path):
        return PathValidationResult(
            is_valid=False,
            error="Path contains glob characters (* or ?). Use actual file paths, not patterns."
        )

    # Check for Windows-invalid characters
    # Allow : only at position 1 for drive letters (e.g., C:)
    path_to_check = path
    if len(path) >= 2 and path[1] == ':' and path[0].isalpha():
        # Windows drive path, skip the drive letter part
        path_to_check = path[2:]

    if WINDOWS_INVALID_CHARS.search(path_to_check):
        return PathValidationResult(
            is_valid=False,
            error="Path contains invalid characters (< > \" | ? *)",
            warnings=warnings
        )

    # Check for : in path (invalid on Windows except for drive letter)
    if ':' in path_to_check:
        return PathValidationResult(
            is_valid=False,
            error="Path contains invalid colon character",
            warnings=warnings
        )

    # Check path component lengths
    # Normalize path separators
    normalized = path.replace('\\', '/')
    components = normalized.split('/')

    for component in components:
        if component and len(component) > MAX_PATH_COMPONENT_LENGTH:
            return PathValidationResult(
                is_valid=False,
                error=f"Path component exceeds maximum length of {MAX_PATH_COMPONENT_LENGTH} characters"
            )

    # Normalize double slashes
    while '//' in normalized:
        normalized = normalized.replace('//', '/')

    # Convert back to OS-appropriate separators
    if os.name == 'nt':
        # Keep original Windows paths but normalize doubles
        final_path = path
        while '\\\\' in final_path:
            final_path = final_path.replace('\\\\', '\\')
        while '//' in final_path:
            final_path = final_path.replace('//', '/')
    else:
        final_path = normalized

    # Check for excessive path traversal (security concern)
    traversal_count = path.count('..')
    if traversal_count > 3:
        warnings.append("Excessive path traversal detected")
        return PathValidationResult(
            is_valid=False,
            path=final_path,
            error="Excessive path traversal detected (more than 3 levels)",
            warnings=warnings
        )

    # Semantic checks (existence, directory, file)
    # must_be_dir or must_be_file imply check_exists
    if must_be_dir or must_be_file:
        check_exists = True

    if check_exists:
        from pathlib import Path
        path_obj = Path(final_path)

        if not path_obj.exists():
            return PathValidationResult(
                is_valid=False,
                path=final_path,
                error=f"Path does not exist: {final_path}",
                warnings=warnings if warnings else None
            )

        if must_be_dir and not path_obj.is_dir():
            return PathValidationResult(
                is_valid=False,
                path=final_path,
                error=f"Path is not a directory: {final_path}",
                warnings=warnings if warnings else None
            )

        if must_be_file and not path_obj.is_file():
            return PathValidationResult(
                is_valid=False,
                path=final_path,
                error=f"Path is not a file: {final_path}",
                warnings=warnings if warnings else None
            )

    return PathValidationResult(
        is_valid=True,
        path=final_path,
        warnings=warnings if warnings else None
    )
