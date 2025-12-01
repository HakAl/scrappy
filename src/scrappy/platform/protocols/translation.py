"""
Command translation protocol.

Defines the interface for translating commands between platforms.
"""

from typing import Protocol, Tuple, runtime_checkable


@runtime_checkable
class CommandTranslatorProtocol(Protocol):
    """
    Protocol for translating commands between platforms.

    Implementations handle platform-specific command translation
    while preserving command semantics.

    Example:
        def run_command(translator: CommandTranslatorProtocol, cmd: str):
            translated, was_modified = translator.translate_command(cmd)
            if was_modified:
                print(f"Translated: {cmd} -> {translated}")
            return execute(translated)
    """

    def translate_command(self, command: str) -> Tuple[str, bool]:
        """
        Translate Unix commands to Windows equivalents when necessary.

        Args:
            command: Original command

        Returns:
            Tuple of (translated_command, was_translated)

        Example:
            >>> translator.translate_command("ls -la")
            ("dir", True)  # On Windows
            >>> translator.translate_command("ls -la")
            ("ls -la", False)  # On Unix
        """
        ...

    def normalize_command_paths(self, command: str) -> Tuple[str, bool, str]:
        """
        Normalize paths in shell commands for the current platform.

        On Windows, converts forward slashes to backslashes in path arguments.
        This fixes issues where commands like 'mkdir website/frontend' fail
        because Windows cmd.exe doesn't accept forward slashes in paths.

        Args:
            command: Shell command that may contain paths

        Returns:
            Tuple of (normalized_command, was_modified, message)

        Example:
            >>> translator.normalize_command_paths("mkdir src/components")
            ("mkdir src\\components", True, "Normalized paths for Windows")
        """
        ...

    def normalize_npm_command_for_windows(self, command: str) -> Tuple[str, bool, str]:
        """
        Normalize npm commands for Windows to prevent Unicode output issues.

        On Windows, npm commands with spinners and progress bars can crash due to
        Unicode encoding issues. This function adds flags to suppress these.

        Args:
            command: npm command to normalize

        Returns:
            Tuple of (normalized_command, was_modified, message)

        Example:
            >>> translator.normalize_npm_command_for_windows("npm install")
            ("npm install --no-progress --no-color", True, "Added Windows npm flags")
        """
        ...

    def fix_spring_initializr_command(self, command: str) -> Tuple[str, bool, str]:
        """
        Fix curl/PowerShell commands that use Spring Initializr.

        On Windows, downloading from start.spring.io often fails due to URL
        encoding issues. This function fixes the URL encoding.

        Args:
            command: The shell command to fix

        Returns:
            Tuple of (fixed_command, was_fixed, message)

        Example:
            >>> translator.fix_spring_initializr_command(
            ...     'curl "https://start.spring.io/starter.zip?dependencies=web,jpa"'
            ... )
            ('curl "https://start.spring.io/starter.zip?dependencies=web%2Cjpa"',
             True,
             "Fixed Spring Initializr URL encoding")
        """
        ...
