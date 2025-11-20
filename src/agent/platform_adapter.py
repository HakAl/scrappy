"""
Platform utilities adapter.

Provides concrete implementations of PlatformUtilsProtocol for different
platforms and testing scenarios.

MIGRATION NOTE: This module has been updated to use the new platform
architecture (src/platform/) while maintaining full backward compatibility.
"""

from typing import Tuple, Optional

from .protocols import PlatformUtilsProtocol
from src.platform.protocols.orchestrator import PlatformOrchestratorProtocol
from src.platform.factory import create_platform_orchestrator


class RealPlatformUtils:
    """
    Real platform utilities implementation.

    Uses the new PlatformOrchestrator architecture internally while
    maintaining the PlatformUtilsProtocol interface for backward compatibility.

    ARCHITECTURE: This class bridges the old PlatformUtilsProtocol to the
    new protocol-based platform architecture, allowing gradual migration.
    """

    def __init__(
        self,
        orchestrator: Optional[PlatformOrchestratorProtocol] = None
    ):
        """
        Initialize with optional orchestrator dependency injection.

        Args:
            orchestrator: Platform orchestrator. Creates default if None.
        """
        self._orchestrator = orchestrator or create_platform_orchestrator()

    def is_windows(self) -> bool:
        """
        Check if running on Windows.

        Returns:
            True if Windows, False otherwise
        """
        return self._orchestrator.detector.is_windows()

    def is_unix(self) -> bool:
        """
        Check if running on Unix-like OS.

        Returns:
            True if Unix-like, False otherwise
        """
        return self._orchestrator.detector.is_unix()

    def is_macos(self) -> bool:
        """
        Check if running on macOS.

        Returns:
            True if macOS, False otherwise
        """
        return self._orchestrator.detector.is_macos()

    def get_platform_name(self) -> str:
        """
        Get platform name.

        Returns:
            Platform name (e.g., 'Windows', 'Linux', 'macOS')
        """
        return self._orchestrator.detector.get_platform_name()

    def validate_command(self, command: str) -> Tuple[bool, str]:
        """
        Validate command for current platform.

        Args:
            command: Command to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        return self._orchestrator.validator.validate_command_for_platform(command)

    def translate_command(self, command: str) -> Tuple[str, bool]:
        """
        Translate command for current platform.

        Args:
            command: Command to translate

        Returns:
            Tuple of (translated_command, was_modified)
        """
        return self._orchestrator.translator.translate_command(command)


class MockPlatformUtils:
    """
    Mock platform utilities for testing.

    Allows configuring platform behavior for testing different
    platform scenarios without changing the actual platform.
    """

    def __init__(
        self,
        platform: str = "linux",
        is_windows_val: bool = False,
        is_unix_val: bool = True,
        is_macos_val: bool = False,
    ):
        """
        Initialize mock platform.

        Args:
            platform: Platform name to simulate
            is_windows_val: Whether to simulate Windows
            is_unix_val: Whether to simulate Unix
            is_macos_val: Whether to simulate macOS
        """
        self._platform = platform
        self._is_windows = is_windows_val
        self._is_unix = is_unix_val
        self._is_macos = is_macos_val

    def is_windows(self) -> bool:
        """
        Check if simulating Windows.

        Returns:
            Configured Windows flag
        """
        return self._is_windows

    def is_unix(self) -> bool:
        """
        Check if simulating Unix.

        Returns:
            Configured Unix flag
        """
        return self._is_unix

    def is_macos(self) -> bool:
        """
        Check if simulating macOS.

        Returns:
            Configured macOS flag
        """
        return self._is_macos

    def get_platform_name(self) -> str:
        """
        Get simulated platform name.

        Returns:
            Configured platform name
        """
        return self._platform

    def validate_command(self, command: str) -> Tuple[bool, str]:
        """
        Mock command validation (always passes).

        Args:
            command: Command to validate

        Returns:
            Tuple of (True, "")
        """
        return (True, "")

    def translate_command(self, command: str) -> Tuple[str, bool]:
        """
        Mock command translation (no-op).

        Args:
            command: Command to translate

        Returns:
            Tuple of (command, False) - unchanged
        """
        return (command, False)
