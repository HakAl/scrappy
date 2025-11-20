"""
Tests for platform utilities - cross-platform support and command validation.
"""
import pytest
import sys
from unittest.mock import patch, MagicMock

from src.platform_utils import (
    get_platform_name,
    is_windows,
    is_unix,
    is_macos,
    validate_command_for_platform,
    get_dangerous_commands,
    normalize_path_for_shell,
    normalize_command_paths,
)


class TestPlatformDetection:
    """Tests for platform detection."""

    @pytest.mark.unit

    @pytest.mark.unit
    def test_get_platform_name_known_value(self):
        """Test that platform is one of known values."""
        platform = get_platform_name()
        known_platforms = ["Windows", "Linux", "macOS"]
        assert platform in known_platforms or platform.startswith("FreeBSD") or platform.startswith("OpenBSD")

    @pytest.mark.unit

    @pytest.mark.unit

    @pytest.mark.unit

    @pytest.mark.unit
    def test_platform_consistency(self):
        """Test that platform checks are consistent."""
        # Can't be both Windows and Unix at the same time
        if is_windows():
            assert not is_unix()
            assert not is_macos()
        if is_macos():
            assert is_unix()  # macOS is Unix
            assert not is_windows()


class TestDangerousCommandDetection:
    """Tests for dangerous command detection."""

    @pytest.mark.unit
    def test_get_dangerous_commands_returns_list(self):
        """Test that dangerous commands returns a list."""
        dangerous = get_dangerous_commands()
        assert isinstance(dangerous, list)
        assert len(dangerous) > 0

    @pytest.mark.unit
    def test_dangerous_commands_contains_patterns(self):
        """Test that dangerous commands contains expected patterns."""
        dangerous = get_dangerous_commands()

        # Common patterns should be present
        has_mkfs = any("mkfs" in cmd for cmd in dangerous)
        has_format = any("format" in cmd for cmd in dangerous)

        assert has_mkfs or has_format

    @pytest.mark.unit
    def test_platform_specific_dangerous_commands(self):
        """Test that platform-specific commands are included."""
        dangerous = get_dangerous_commands()

        if is_windows():
            # Should have Windows-specific dangerous commands
            has_del = any("del" in cmd for cmd in dangerous)
            has_rmdir = any("rmdir" in cmd for cmd in dangerous)
            assert has_del or has_rmdir
        else:
            # Should have Unix-specific dangerous commands (regex patterns)
            # Patterns use \s+ for spaces, so check for "rm" and "rf" in pattern
            has_rm_rf = any("rm" in cmd and "rf" in cmd for cmd in dangerous)
            assert has_rm_rf

    @pytest.mark.unit
    def test_dangerous_commands_not_empty(self):
        """Test that list is not empty."""
        dangerous = get_dangerous_commands()
        assert len(dangerous) > 5  # Should have several patterns


class TestCommandValidation:
    """Tests for command validation by platform."""

    @pytest.mark.unit
    def test_validate_safe_command(self):
        """Test that safe commands pass validation."""
        is_valid, warning = validate_command_for_platform("git status")
        assert is_valid is True

    @pytest.mark.unit
    def test_validate_empty_command(self):
        """Test that empty commands fail validation."""
        is_valid, warning = validate_command_for_platform("")
        assert is_valid is False
        assert "Empty" in warning

    @pytest.mark.unit
    def test_validate_returns_tuple(self):
        """Test that validation returns proper tuple."""
        result = validate_command_for_platform("echo test")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)

    @pytest.mark.unit
    def test_whitespace_only_command(self):
        """Test that whitespace-only command fails."""
        is_valid, warning = validate_command_for_platform("   ")
        assert is_valid is False
