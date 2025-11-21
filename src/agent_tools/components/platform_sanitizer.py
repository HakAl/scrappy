"""
Platform-specific command sanitization components.

Implements PlatformSanitizerProtocol to handle OS-specific command
adjustments, path normalization, and command translation.
"""

import os
from pathlib import Path


class WindowsSanitizer:
    """
    Windows-specific command sanitizer.

    Handles path normalization and command adjustments for Windows.
    """

    def __init__(self):
        """Initialize Windows sanitizer."""
        pass

    def sanitize(self, command: str) -> str:
        """
        Apply Windows-specific command fixes.

        Args:
            command: Original command string

        Returns:
            Sanitized command appropriate for Windows
        """
        # Import platform utilities if available
        try:
            from ...platform_utils import (
                normalize_command_paths,
                normalize_npm_command_for_windows,
                fix_spring_initializr_command,
            )

            # Apply fixes in order
            command, _, _ = fix_spring_initializr_command(command)
            command, _, _ = normalize_npm_command_for_windows(command)
            command, _, _ = normalize_command_paths(command)

        except ImportError:
            pass

        return command

    def normalize_path(self, path: str) -> str:
        """
        Normalize path for Windows.

        Args:
            path: Path to normalize

        Returns:
            Windows-appropriate path with backslashes
        """
        return str(Path(path).as_posix()).replace('/', '\\')


class UnixSanitizer:
    """
    Unix-specific command sanitizer.

    Minimal processing for Unix-like systems (Linux, macOS).
    """

    def __init__(self):
        """Initialize Unix sanitizer."""
        pass

    def sanitize(self, command: str) -> str:
        """
        Apply Unix-specific command fixes (usually none needed).

        Args:
            command: Original command string

        Returns:
            Command (typically unchanged on Unix)
        """
        return command

    def normalize_path(self, path: str) -> str:
        """
        Normalize path for Unix.

        Args:
            path: Path to normalize

        Returns:
            Unix-appropriate path with forward slashes
        """
        return str(Path(path).as_posix())
