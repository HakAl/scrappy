"""Input validation layer for CLI.

Provides validators for commands, paths, and providers with length limits,
empty checks, and character validation.
"""

from dataclasses import dataclass
from typing import Optional, List
import re
import os


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


@dataclass
class CommandValidationResult:
    """Result of command validation.

    Contains the parsed command components and any validation errors or warnings.
    Used as the return type for validate_command().

    Attributes:
        is_valid: Whether the command passed all validation checks.
        command: The parsed command name (lowercase, without slash). Empty if invalid.
        args: The arguments portion of the command. Empty if no arguments.
        error: Description of what failed validation. None if valid.
        warnings: List of non-fatal issues detected. None if no warnings.

    Example:
        >>> result = validate_command("/plan my task")
        >>> result.is_valid
        True
        >>> result.command
        'plan'
        >>> result.args
        'my task'
    """
    is_valid: bool
    command: str = ""
    args: str = ""
    error: Optional[str] = None
    warnings: Optional[List[str]] = None


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


# Valid commands for the CLI
VALID_COMMANDS = {
    # Core commands
    "help", "status", "quit", "exit", "q", "clear",
    # Task commands
    "plan", "reason", "agent", "smart", "tasks", "classify",
    # Provider commands
    "providers", "brain", "usage", "models",
    # Session commands
    "context", "cache", "session", "limits",
    # Multi-provider commands
    "synthesize", "delegate",
    # Codebase commands
    "explore",
    # Mode toggles
    "auto", "route", "autoroute", "ml", "multiline", "paste", "autoexec"
}

# Valid providers
VALID_PROVIDERS = {
    "cerebras", "groq", "gemini", "cohere", "github_models"
}

# Limits
MAX_COMMAND_LENGTH = 5000
MAX_PATH_LENGTH = 500
MAX_PATH_COMPONENT_LENGTH = 255
MAX_PROVIDER_LENGTH = 50

# Invalid characters patterns
CONTROL_CHARS_PATTERN = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
NEWLINE_PATTERN = re.compile(r'[\r\n]')
WINDOWS_INVALID_CHARS = re.compile(r'[<>"|?*]')
GLOB_CHARS_PATTERN = re.compile(r'[*?]')


def validate_command(command_input: str) -> CommandValidationResult:
    """Validate a CLI command string and parse its components.

    Performs comprehensive validation including:
    - None and empty checks
    - Length limits (max 5000 characters)
    - Control character detection
    - Slash prefix requirement
    - Command name validation against VALID_COMMANDS

    Args:
        command_input: The command string to validate (e.g., "/help" or "/plan task").
            Must start with a slash and contain a valid command name.

    Returns:
        CommandValidationResult with:
        - is_valid: True if all checks pass
        - command: Parsed command name (lowercase)
        - args: Any arguments after the command
        - error: Description of failure if invalid

    Side Effects:
        None. This is a pure validation function.

    State Changes:
        None. Does not modify any external state.

    Example:
        >>> result = validate_command("/plan implement feature")
        >>> if result.is_valid:
        ...     print(f"Command: {result.command}, Args: {result.args}")
        Command: plan, Args: implement feature
    """
    # Handle None input
    if command_input is None:
        return CommandValidationResult(
            is_valid=False,
            error="Command cannot be None"
        )

    # Empty check
    if not command_input or not command_input.strip():
        return CommandValidationResult(
            is_valid=False,
            error="Command cannot be empty"
        )

    # Strip whitespace
    command_input = command_input.strip()

    # Length check
    if len(command_input) > MAX_COMMAND_LENGTH:
        return CommandValidationResult(
            is_valid=False,
            error=f"Command exceeds maximum length of {MAX_COMMAND_LENGTH} characters"
        )

    # Check for control characters
    if CONTROL_CHARS_PATTERN.search(command_input):
        return CommandValidationResult(
            is_valid=False,
            error="Command contains invalid control characters"
        )

    # Check for newlines
    if NEWLINE_PATTERN.search(command_input):
        return CommandValidationResult(
            is_valid=False,
            error="Command cannot contain newline characters"
        )

    # Must start with /
    if not command_input.startswith('/'):
        return CommandValidationResult(
            is_valid=False,
            error="Command must start with a slash (/)"
        )

    # Remove the leading slash
    without_slash = command_input[1:]

    # Check for empty command name
    if not without_slash or not without_slash.strip():
        return CommandValidationResult(
            is_valid=False,
            error="Command name cannot be empty after slash"
        )

    # Split command and args
    parts = without_slash.split(None, 1)
    cmd_name = parts[0].lower()  # Normalize to lowercase
    args = parts[1] if len(parts) > 1 else ""

    # Validate command name
    if cmd_name not in VALID_COMMANDS:
        return CommandValidationResult(
            is_valid=False,
            error=f"Unknown command: {cmd_name}"
        )

    return CommandValidationResult(
        is_valid=True,
        command=cmd_name,
        args=args
    )


def validate_path(path_input: str) -> PathValidationResult:
    """Validate a file or directory path and normalize it.

    Performs comprehensive validation including:
    - None and empty checks
    - Length limits (max 500 characters total, 255 per component)
    - Control character and newline detection
    - Glob character rejection (use actual paths, not patterns)
    - Windows-invalid character detection
    - Path traversal security check (max 3 levels of ..)

    Args:
        path_input: The path string to validate. Can be relative or absolute.
            Forward and back slashes are normalized for the current OS.

    Returns:
        PathValidationResult with:
        - is_valid: True if all checks pass
        - path: Normalized path with cleaned separators
        - error: Description of failure if invalid
        - warnings: Security concerns like excessive traversal

    Side Effects:
        None. This is a pure validation function.

    State Changes:
        None. Does not modify any external state or files.

    Example:
        >>> result = validate_path("src//cli/validators.py")
        >>> result.path
        'src/cli/validators.py'
    """
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

    return PathValidationResult(
        is_valid=True,
        path=final_path,
        warnings=warnings if warnings else None
    )


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
