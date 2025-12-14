"""Command validation for CLI.

Provides validation for CLI command strings including parsing,
length checks, and command name validation.
"""

from dataclasses import dataclass
from typing import Optional, List

from .base import CONTROL_CHARS_PATTERN, NEWLINE_PATTERN


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


# Valid commands for the CLI
VALID_COMMANDS = {
    # Core commands
    "help", "status", "quit", "exit", "q", "clear", "history",
    # Task commands
    "plan", "reason", "agent", "smart", "tasks", "classify",
    # Provider commands
    "usage", "models", "model", "setup",
    # Session commands
    "context", "cache", "session", "limits",
    # Multi-provider commands
    "synthesize", "delegate",
    # Codebase commands
    "explore",
    # Mode toggles
    "ml", "multiline", "paste", "autoexec", "verbose", "v"
}

# Limits
MAX_COMMAND_LENGTH = 5000


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
