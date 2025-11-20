"""
Command validation protocol.

Defines the interface for validating commands before execution.
"""

from typing import Protocol, Tuple, List, runtime_checkable


@runtime_checkable
class CommandValidatorProtocol(Protocol):
    """
    Protocol for validating commands before execution.

    Implementations check for dangerous commands, platform compatibility,
    and other validation rules.

    Example:
        def safe_execute(validator: CommandValidatorProtocol, cmd: str):
            is_valid, warning = validator.validate_command_for_platform(cmd)
            if not is_valid:
                raise ValueError(f"Invalid command: {warning}")
            return execute(cmd)
    """

    def validate_command_for_platform(self, command: str) -> Tuple[bool, str]:
        """
        Validate if a command is appropriate for the current platform.

        Checks for:
        - Platform-specific commands (Unix commands on Windows, etc.)
        - Empty commands
        - PowerShell cmdlets in cmd.exe context
        - Other platform compatibility issues

        Args:
            command: Command to validate

        Returns:
            Tuple of (is_valid, warning_message)

        Example:
            >>> validator.validate_command_for_platform("ls -la")
            (True, "")  # On Unix
            >>> validator.validate_command_for_platform("ls -la")
            (False, "Unix command 'ls' not available on Windows")  # On Windows
        """
        ...

    def get_dangerous_commands(self) -> List[str]:
        """
        Get list of dangerous command patterns for the current platform.

        Returns regex patterns that match commands that could be destructive
        (e.g., recursive deletes on system directories, disk formatting).

        Returns:
            List of dangerous command patterns (regex strings)

        Example:
            >>> validator.get_dangerous_commands()
            ['\\brm\\s+-rf\\s+/$', '\\bformat\\s+[a-zA-Z]:']
        """
        ...

    def get_interactive_commands(self) -> List[str]:
        """
        Get list of commands that may prompt for user input.

        These commands might hang if run in non-interactive contexts.

        Returns:
            List of interactive command patterns

        Example:
            >>> validator.get_interactive_commands()
            ['git commit', 'npm init', 'sudo ', 'ssh ']
        """
        ...
