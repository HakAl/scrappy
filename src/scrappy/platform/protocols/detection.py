"""
Platform detection protocol.

Defines the interface for platform detection and tool availability checking.
"""

from typing import Protocol, Optional, Dict, runtime_checkable, Literal

PlatformType = Literal["Windows", "macOS", "Linux", "FreeBSD", "OpenBSD", "NetBSD"]


@runtime_checkable
class PlatformDetectorProtocol(Protocol):
    """
    Protocol for platform detection and tool availability.

    NOTE: src/context/platform.py::PlatformDetector already implements
    most of this contract (get_platform, has_tool).

    Implementations must provide platform detection methods
    and shell information without side effects.

    Example:
        def check_platform(detector: PlatformDetectorProtocol):
            if detector.is_windows():
                print(f"Running on Windows")
            else:
                print(f"Running on {detector.get_platform_name()}")
    """

    def is_windows(self) -> bool:
        """
        Check if running on Windows.

        Returns:
            True if Windows, False otherwise
        """
        ...

    def is_unix(self) -> bool:
        """
        Check if running on Unix-like system (Linux, macOS, BSD).

        Returns:
            True if Unix-like, False otherwise
        """
        ...

    def is_macos(self) -> bool:
        """
        Check if running on macOS.

        Returns:
            True if macOS, False otherwise
        """
        ...

    def get_platform_name(self) -> str:
        """
        Get human-readable platform name.

        Returns:
            Platform name (e.g., 'Windows', 'macOS', 'Linux')
        """
        ...

    def get_shell_info(self) -> Dict[str, Optional[str]]:
        """
        Get information about available shells.

        Returns:
            Dict with keys:
            - 'default': Default shell path
            - 'bash': Bash shell path (if available)
            - 'powershell': PowerShell path (if available)
            - 'cmd': cmd.exe path (if available)
            - 'sh': sh shell path (if available)

        Example:
            >>> detector.get_shell_info()
            {'default': '/bin/bash', 'bash': '/bin/bash', 'sh': '/bin/sh'}
        """
        ...

    def has_git_bash(self) -> bool:
        """
        Check if Git Bash is available (common on Windows).

        Returns:
            True if Git Bash is available, False otherwise
        """
        ...

    def has_tool(self, tool_name: str) -> bool:
        """
        Check if a command-line tool is available.

        Args:
            tool_name: Name of the tool/command to check

        Returns:
            True if tool is available in PATH, False otherwise

        Example:
            >>> detector.has_tool('git')
            True
            >>> detector.has_tool('nonexistent_tool')
            False
        """
        ...
