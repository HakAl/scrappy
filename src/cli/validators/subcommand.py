"""Subcommand validation for CLI.

Provides validation for command subarguments like 'cache clear',
'context explore', 'session save', etc.
"""

from dataclasses import dataclass
from typing import Optional, Set, Dict


@dataclass
class SubcommandValidationResult:
    """Result of subcommand validation.

    Contains the parsed subcommand and any validation errors.
    Used as the return type for validate_subcommand().

    Attributes:
        is_valid: Whether the subcommand passed all validation checks.
        subcommand: The parsed subcommand (lowercase). Empty if no subcommand.
        args: Any arguments after the subcommand. Empty if no arguments.
        error: Description of what failed validation. None if valid.

    Example:
        >>> result = validate_subcommand("cache", "clear")
        >>> result.is_valid
        True
        >>> result.subcommand
        'clear'
    """
    is_valid: bool
    subcommand: str = ""
    args: str = ""
    error: Optional[str] = None


# Registry of valid subcommands per command
# Empty string is implicitly allowed for all commands (show status)
COMMAND_SUBCOMMANDS: Dict[str, Set[str]] = {
    "cache": {"clear", "toggle"},
    "context": {"explore", "refresh", "clear", "clearmem", "toggle", "add"},
    "session": {"save", "load", "clear", "toggle"},
    "limits": {"reset"},  # Special handling for provider filter
}

# Subcommands that require additional arguments
SUBCOMMANDS_WITH_ARGS: Dict[str, Set[str]] = {
    "context": {"add"},
    "limits": {"reset"},  # reset can optionally take a provider name
}

# Commands that allow passthrough of unknown subcommands as arguments
# (e.g., /limits anthropic passes "anthropic" as args for filtering)
PASSTHROUGH_COMMANDS: Set[str] = {"limits"}


def validate_subcommand(command: str, args_input: Optional[str]) -> SubcommandValidationResult:
    """Validate a subcommand for a given command.

    Performs validation including:
    - Command existence in registry
    - Subcommand validity against registered options
    - Case-insensitive matching with normalization
    - Argument extraction for compound subcommands

    Args:
        command: The main command name (e.g., "cache", "context", "session").
            Will be normalized to lowercase.
        args_input: The subcommand and arguments string (e.g., "clear", "save filename").
            Can be None or empty for "show status" behavior.

    Returns:
        SubcommandValidationResult with:
        - is_valid: True if subcommand is valid for the command
        - subcommand: Parsed subcommand name (lowercase)
        - args: Remaining arguments after subcommand
        - error: Description of failure if invalid

    Side Effects:
        None. This is a pure validation function.

    State Changes:
        None. Does not modify any external state.

    Example:
        >>> result = validate_subcommand("cache", "clear")
        >>> if result.is_valid:
        ...     print(f"Subcommand: {result.subcommand}")
        Subcommand: clear

        >>> result = validate_subcommand("session", "save my_file")
        >>> result.subcommand
        'save'
        >>> result.args
        'my_file'
    """
    # Normalize command
    if command is None:
        return SubcommandValidationResult(
            is_valid=False,
            error="Command cannot be None"
        )

    command = command.strip().lower()

    # Check if command is in registry
    if command not in COMMAND_SUBCOMMANDS:
        return SubcommandValidationResult(
            is_valid=False,
            error=f"Unknown command '{command}'. Valid commands: {', '.join(sorted(COMMAND_SUBCOMMANDS.keys()))}"
        )

    # Handle None/empty args (show status behavior)
    if args_input is None or not args_input.strip():
        return SubcommandValidationResult(
            is_valid=True,
            subcommand="",
            args=""
        )

    # Normalize args
    args_input = args_input.strip()

    # Split into subcommand and remaining args
    parts = args_input.split(None, 1)
    subcommand_candidate = parts[0].lower()
    remaining_args = parts[1] if len(parts) > 1 else ""

    # Get valid subcommands for this command
    valid_subcommands = COMMAND_SUBCOMMANDS[command]

    # Check if it's a valid subcommand
    if subcommand_candidate in valid_subcommands:
        return SubcommandValidationResult(
            is_valid=True,
            subcommand=subcommand_candidate,
            args=remaining_args
        )

    # For passthrough commands, treat unknown subcommand as argument
    if command in PASSTHROUGH_COMMANDS:
        return SubcommandValidationResult(
            is_valid=True,
            subcommand="",
            args=args_input
        )

    # Invalid subcommand
    valid_options = sorted(valid_subcommands)
    return SubcommandValidationResult(
        is_valid=False,
        error=f"Unknown subcommand '{subcommand_candidate}' for {command}. Valid options: {', '.join(valid_options)}"
    )
