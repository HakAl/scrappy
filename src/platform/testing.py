"""
Testing utilities for platform module.

Provides mock implementations for testing platform-dependent code.
"""

from src.platform.protocols.detection import PlatformDetectorProtocol


class MockPlatformDetector:
    """Mock platform detector for testing."""

    def __init__(self, is_windows: bool = False, has_git_bash: bool = False):
        """
        Initialize mock detector.

        Args:
            is_windows: Whether to simulate Windows platform
            has_git_bash: Whether to simulate Git Bash presence
        """
        self._is_windows = is_windows
        self._has_git_bash = has_git_bash

    def is_windows(self) -> bool:
        """Check if platform is Windows."""
        return self._is_windows

    def is_unix(self) -> bool:
        """Check if platform is Unix-like."""
        return not self._is_windows

    def has_git_bash(self) -> bool:
        """Check if Git Bash is available."""
        return self._has_git_bash

    def get_platform_name(self) -> str:
        """Get platform name."""
        return "Windows" if self._is_windows else "Unix"
