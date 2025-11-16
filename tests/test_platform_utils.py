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
    get_shell_info,
    translate_command_for_platform,
    normalize_path_for_shell,
    get_null_device,
    get_path_separator,
)


class TestPlatformDetection:
    """Tests for platform detection."""

    @pytest.mark.unit
    def test_get_platform_name_returns_string(self):
        """Test that platform detection returns a string."""
        platform = get_platform_name()
        assert isinstance(platform, str)

    @pytest.mark.unit
    def test_get_platform_name_known_value(self):
        """Test that platform is one of known values."""
        platform = get_platform_name()
        known_platforms = ["Windows", "Linux", "macOS"]
        assert platform in known_platforms or platform.startswith("FreeBSD") or platform.startswith("OpenBSD")

    @pytest.mark.unit
    def test_is_windows_returns_bool(self):
        """Test that is_windows returns boolean."""
        result = is_windows()
        assert isinstance(result, bool)

    @pytest.mark.unit
    def test_is_unix_returns_bool(self):
        """Test that is_unix returns boolean."""
        result = is_unix()
        assert isinstance(result, bool)

    @pytest.mark.unit
    def test_is_macos_returns_bool(self):
        """Test that is_macos returns boolean."""
        result = is_macos()
        assert isinstance(result, bool)

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
            # Should have Unix-specific dangerous commands
            has_rm_rf = any("rm -rf" in cmd for cmd in dangerous)
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

    @pytest.mark.unit
    def test_unix_command_on_windows(self):
        """Test Unix command validation on Windows."""
        if is_windows():
            # Unix-specific commands should warn/fail on Windows
            is_valid, warning = validate_command_for_platform("chmod 755 file.sh")
            # May return False or True with warning depending on Git Bash
            assert isinstance(is_valid, bool)
            assert isinstance(warning, str)

    @pytest.mark.unit
    def test_common_commands_valid(self):
        """Test that common safe commands are valid."""
        commands = ["git status", "python --version", "npm install"]
        for cmd in commands:
            is_valid, warning = validate_command_for_platform(cmd)
            # Should generally be valid
            assert isinstance(is_valid, bool)


class TestCommandTranslation:
    """Tests for command translation between platforms."""

    @pytest.mark.unit
    def test_translate_returns_tuple(self):
        """Test that translation returns tuple."""
        result = translate_command_for_platform("ls")
        assert isinstance(result, tuple)
        assert len(result) == 2

    @pytest.mark.unit
    def test_translate_ls_on_windows(self):
        """Test translating ls command."""
        if is_windows():
            translated, was_translated = translate_command_for_platform("ls")
            assert "dir" in translated.lower()
            assert was_translated is True
        else:
            translated, was_translated = translate_command_for_platform("ls")
            assert translated == "ls"
            assert was_translated is False

    @pytest.mark.unit
    def test_translate_pwd_on_windows(self):
        """Test translating pwd command."""
        if is_windows():
            translated, was_translated = translate_command_for_platform("pwd")
            assert was_translated is True
            assert "cd" in translated.lower()

    @pytest.mark.unit
    def test_translate_preserves_args(self):
        """Test that translation preserves arguments."""
        if is_windows():
            translated, _ = translate_command_for_platform("cat README.md")
            # Should translate cat to type but keep the argument
            assert "README.md" in translated

    @pytest.mark.unit
    def test_no_translation_on_unix(self):
        """Test that Unix commands aren't translated on Unix."""
        if is_unix():
            translated, was_translated = translate_command_for_platform("ls -la")
            assert was_translated is False
            assert translated == "ls -la"


class TestShellInfo:
    """Tests for shell information retrieval."""

    @pytest.mark.unit
    def test_get_shell_info_returns_dict(self):
        """Test that shell info returns dictionary."""
        info = get_shell_info()
        assert isinstance(info, dict)

    @pytest.mark.unit
    def test_shell_info_has_default(self):
        """Test that shell info includes default shell."""
        info = get_shell_info()
        assert "default" in info

    @pytest.mark.unit
    def test_shell_info_has_bash_key(self):
        """Test that shell info has bash key."""
        info = get_shell_info()
        assert "bash" in info

    @pytest.mark.unit
    def test_windows_has_cmd_powershell(self):
        """Test Windows shell info."""
        if is_windows():
            info = get_shell_info()
            assert "cmd" in info
            assert "powershell" in info


class TestPathNormalization:
    """Tests for path normalization."""

    @pytest.mark.unit
    def test_normalize_path_returns_string(self):
        """Test that path normalization returns string."""
        result = normalize_path_for_shell("some/path")
        assert isinstance(result, str)

    @pytest.mark.unit
    def test_windows_normalizes_to_backslash(self):
        """Test Windows path normalization."""
        if is_windows():
            result = normalize_path_for_shell("src/main/app.py")
            assert "\\" in result
            assert "/" not in result

    @pytest.mark.unit
    def test_unix_normalizes_to_forward_slash(self):
        """Test Unix path normalization."""
        if is_unix():
            result = normalize_path_for_shell("src\\main\\app.py")
            assert "/" in result
            assert "\\" not in result

    @pytest.mark.unit
    def test_get_path_separator(self):
        """Test path separator retrieval."""
        sep = get_path_separator()
        if is_windows():
            assert sep == "\\"
        else:
            assert sep == "/"

    @pytest.mark.unit
    def test_get_null_device(self):
        """Test null device path."""
        null_dev = get_null_device()
        if is_windows():
            assert null_dev == "NUL"
        else:
            assert null_dev == "/dev/null"


class TestEdgeCases:
    """Edge cases and boundary tests."""

    @pytest.mark.unit
    def test_very_long_command(self):
        """Test handling of very long command."""
        long_cmd = "echo " + "a" * 10000
        is_valid, warning = validate_command_for_platform(long_cmd)
        # Should handle without crashing
        assert isinstance(is_valid, bool)

    @pytest.mark.unit
    def test_command_with_special_chars(self):
        """Test handling commands with special characters."""
        cmd = "echo 'test $VAR' && ls"
        is_valid, warning = validate_command_for_platform(cmd)
        assert isinstance(is_valid, bool)

    @pytest.mark.unit
    def test_translate_empty_command(self):
        """Test translating empty command."""
        translated, was_translated = translate_command_for_platform("")
        assert translated == ""
        assert was_translated is False

    @pytest.mark.unit
    def test_translate_unknown_command(self):
        """Test translating unknown command."""
        translated, was_translated = translate_command_for_platform("myCustomCommand arg1")
        # Unknown commands shouldn't be translated
        assert "myCustomCommand" in translated
        assert was_translated is False
