"""
Platform detection implementation.

Provides concrete implementation of PlatformDetectorProtocol with
platform detection, shell detection, and tool availability checking.
"""

import platform
import shutil
from typing import Dict, Optional

from src.platform.protocols.detection import PlatformDetectorProtocol, PlatformType


class SystemPlatformDetector:
    """
    Concrete implementation of platform detection protocol.

    Provides platform detection, shell information, and tool availability
    checking with caching for performance.

    All dependencies are injected via constructor to enable testing.
    """

    def __init__(self):
        """
        Initialize the system platform detector.

        Note: No side effects in constructor - only initializes cache storage.
        """
        self._shell_info_cache: Optional[Dict[str, Optional[str]]] = None
        self._tool_cache: Dict[str, bool] = {}

    def is_windows(self) -> bool:
        """Check if running on Windows."""
        return platform.system() == "Windows"

    def is_unix(self) -> bool:
        """Check if running on Unix-like system (Linux, macOS, BSD)."""
        return platform.system() in ("Linux", "Darwin", "FreeBSD", "OpenBSD", "NetBSD")

    def is_macos(self) -> bool:
        """Check if running on macOS."""
        return platform.system() == "Darwin"

    def get_platform_name(self) -> PlatformType:
        """
        Get human-readable platform name.

        Returns:
            Platform name as defined in PlatformType literal.
        """
        system = platform.system()
        if system == "Windows":
            return "Windows"
        elif system == "Darwin":
            return "macOS"
        elif system == "Linux":
            return "Linux"
        elif system == "FreeBSD":
            return "FreeBSD"
        elif system == "OpenBSD":
            return "OpenBSD"
        elif system == "NetBSD":
            return "NetBSD"
        else:
            return "Linux"

    def get_shell_info(self) -> Dict[str, Optional[str]]:
        """
        Get information about available shells.

        Results are cached since shell availability doesn't change during session.

        Returns:
            Dict with 'default', 'bash', 'powershell', 'cmd', 'sh' keys.
        """
        if self._shell_info_cache is not None:
            return self._shell_info_cache.copy()

        info = {
            'default': None,
            'bash': shutil.which('bash'),
            'powershell': None,
            'cmd': None,
            'sh': shutil.which('sh'),
        }

        if self.is_windows():
            info['cmd'] = shutil.which('cmd')
            info['powershell'] = shutil.which('powershell') or shutil.which('pwsh')
            info['default'] = info['cmd'] or info['powershell']
        else:
            info['default'] = info['bash'] or info['sh']

        self._shell_info_cache = info
        return info.copy()

    def has_git_bash(self) -> bool:
        """
        Check if Git Bash is available (common on Windows).

        Returns:
            True if Git Bash is detected, False otherwise.
        """
        if not self.is_windows():
            return False

        bash_path = shutil.which('bash')
        return bash_path is not None and 'git' in bash_path.lower()

    def has_tool(self, tool_name: str) -> bool:
        """
        Check if a command-line tool is available.

        Results are cached since tool availability doesn't change during session.

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
