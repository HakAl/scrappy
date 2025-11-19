"""
Platform detection and tool availability checking.

Provides platform identification and command-line tool detection
with caching for performance.
"""

import shutil
import sys
from typing import Optional


class PlatformDetector:
    """
    Detects the current platform and checks for available tools.

    Results are cached for performance since platform and tool
    availability don't change during a session.

    Usage:
        detector = PlatformDetector()

        if detector.get_platform() == 'windows':
            # Windows-specific logic
            pass

        if detector.has_tool('git'):
            # Use git
            pass
    """

    def __init__(self):
        """Initialize the platform detector with empty caches."""
        self._platform: Optional[str] = None
        self._tool_cache: dict = {}

    def get_platform(self) -> str:
        """
        Get the current platform (cached).

        Returns:
            Platform identifier: 'windows', 'darwin', 'linux', or 'unix'
        """
        if self._platform is None:
            if sys.platform == 'win32':
                self._platform = 'windows'
            elif sys.platform == 'darwin':
                self._platform = 'darwin'
            elif sys.platform.startswith('linux'):
                self._platform = 'linux'
            else:
                self._platform = 'unix'

        return self._platform

    def has_tool(self, tool_name: str) -> bool:
        """
        Check if a command-line tool is available (cached).

        Args:
            tool_name: Name of the tool/command to check

        Returns:
            True if tool is available, False otherwise
        """
        if not tool_name or ' ' in tool_name:
            return False

        if tool_name not in self._tool_cache:
            self._tool_cache[tool_name] = shutil.which(tool_name) is not None

        return self._tool_cache[tool_name]
