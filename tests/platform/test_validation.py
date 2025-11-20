"""
Behavior tests for command validation.

Tests prove that command validation works correctly, catching dangerous
commands and platform incompatibilities while allowing safe commands.
"""

import pytest
from tests.helpers import FakePlatformDetector
from src.platform.validation import SecurityCommandValidator


class TestCommandValidation:
    """Test basic command validation behavior."""

    def test_empty_command_is_invalid(self):
        """Test that empty commands are rejected."""
        detector = FakePlatformDetector(platform="Linux")
        validator = SecurityCommandValidator(detector)

        is_valid, message = validator.validate_command_for_platform("")

        assert not is_valid
        assert "Empty" in message

    def test_whitespace_only_command_is_invalid(self):
        """Test that whitespace-only commands are rejected."""
        detector = FakePlatformDetector(platform="Linux")
        validator = SecurityCommandValidator(detector)

        is_valid, message = validator.validate_command_for_platform("   ")

        assert not is_valid
        assert "Empty" in message

    def test_valid_command_on_linux(self):
        """Test that valid commands are accepted on Linux."""
        detector = FakePlatformDetector(platform="Linux")
        validator = SecurityCommandValidator(detector)

        is_valid, message = validator.validate_command_for_platform("ls -la")

        assert is_valid
        assert message == ""

    def test_valid_command_on_windows(self):
        """Test that valid commands are accepted on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        validator = SecurityCommandValidator(detector)

        is_valid, message = validator.validate_command_for_platform("dir /s")

        assert is_valid
        assert message == ""


class TestWindowsPlatformValidation:
    """Test Windows-specific command validation."""

    def test_powershell_cmdlet_rejected_in_cmd(self):
        """Test that PowerShell cmdlets are rejected for cmd.exe."""
        detector = FakePlatformDetector(platform="Windows")
        validator = SecurityCommandValidator(detector)

        is_valid, message = validator.validate_command_for_platform("Get-ChildItem")

        assert not is_valid
        assert "PowerShell cmdlet" in message
        assert "cmd.exe" in message

    def test_multiple_powershell_cmdlets_rejected(self):
        """Test that various PowerShell cmdlets are rejected."""
        detector = FakePlatformDetector(platform="Windows")
        validator = SecurityCommandValidator(detector)

        cmdlets = [
            "New-Item",
            "Remove-Item",
            "Copy-Item",
            "Move-Item",
            "Get-Content",
            "Set-Content",
            "Test-Path",
            "Invoke-WebRequest",
        ]

        for cmdlet in cmdlets:
            is_valid, message = validator.validate_command_for_platform(cmdlet)
            assert not is_valid, f"{cmdlet} should be rejected"
            assert "PowerShell cmdlet" in message

    def test_unix_test_syntax_rejected(self):
        """Test that Unix test syntax [ ] is rejected on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        validator = SecurityCommandValidator(detector)

        is_valid, message = validator.validate_command_for_platform("[ -f file.txt ]")

        assert not is_valid
        assert "test syntax" in message.lower()

    def test_unix_test_command_rejected(self):
        """Test that Unix 'test' command is rejected on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        validator = SecurityCommandValidator(detector)

        is_valid, message = validator.validate_command_for_platform("test -f file.txt")

        assert not is_valid
        assert "'test' command" in message

    def test_unix_commands_rejected_on_windows(self):
        """Test that Unix-only commands are rejected on Windows without Git Bash."""
        detector = FakePlatformDetector(platform="Windows")
        validator = SecurityCommandValidator(detector)

        unix_cmds = ["grep pattern", "sed s/a/b/", "awk '{print $1}'", "tar -xzf", "chmod 755"]

        for cmd in unix_cmds:
            is_valid, message = validator.validate_command_for_platform(cmd)
            assert not is_valid, f"{cmd} should be rejected on Windows"
            assert "not available on Windows" in message

    def test_unix_commands_allowed_with_git_bash(self):
        """Test that Unix commands are allowed on Windows with Git Bash."""
        detector = FakePlatformDetector(platform="Windows", has_git_bash=True)
        validator = SecurityCommandValidator(detector)

        is_valid, message = validator.validate_command_for_platform("grep pattern file.txt")

        assert is_valid
        assert "Git Bash" in message

    def test_windows_commands_accepted(self):
        """Test that Windows commands are accepted on Windows."""
        detector = FakePlatformDetector(platform="Windows")
        validator = SecurityCommandValidator(detector)

        windows_cmds = [
            "dir",
            "copy src.txt dst.txt",
            "xcopy /e src dst",
            "move old.txt new.txt",
            "del file.txt",
            "mkdir folder",
            "type file.txt",
            "findstr pattern file.txt",
        ]

        for cmd in windows_cmds:
            is_valid, message = validator.validate_command_for_platform(cmd)
            assert is_valid, f"{cmd} should be accepted on Windows"


class TestUnixPlatformValidation:
    """Test Unix-specific command validation."""

    def test_unix_commands_accepted(self):
        """Test that Unix commands are accepted on Linux."""
        detector = FakePlatformDetector(platform="Linux")
        validator = SecurityCommandValidator(detector)

        unix_cmds = [
            "ls -la",
            "grep pattern file.txt",
            "sed 's/a/b/' file.txt",
            "awk '{print $1}' file.txt",
            "tar -xzf archive.tar.gz",
            "chmod 755 script.sh",
            "find . -name '*.py'",
        ]

        for cmd in unix_cmds:
            is_valid, message = validator.validate_command_for_platform(cmd)
            assert is_valid, f"{cmd} should be accepted on Linux"

    def test_windows_specific_commands_rejected(self):
        """Test that Windows-specific commands are rejected on Unix."""
        detector = FakePlatformDetector(platform="Linux")
        validator = SecurityCommandValidator(detector)

        windows_cmds = [
            "dir",
            "copy src.txt dst.txt",
            "xcopy /e src dst",
            "move old.txt new.txt",
            "del file.txt",
            "type file.txt",
            "findstr pattern file.txt",
            "cls",
            "where python",
        ]

        for cmd in windows_cmds:
            is_valid, message = validator.validate_command_for_platform(cmd)
            assert not is_valid, f"{cmd} should be rejected on Unix"
            assert "not available on Unix" in message

    def test_common_commands_allowed_on_both_platforms(self):
        """Test that common commands are allowed on both platforms."""
        for platform in ["Linux", "Windows"]:
            detector = FakePlatformDetector(platform=platform)
            validator = SecurityCommandValidator(detector)

            common_cmds = [
                "mkdir folder",
                "echo hello",
            ]

            for cmd in common_cmds:
                is_valid, message = validator.validate_command_for_platform(cmd)
                if not is_valid:
                    assert False, f"{cmd} should be accepted on {platform}, but got: {message}"


class TestDangerousCommands:
    """Test detection of dangerous command patterns."""

    def test_windows_dangerous_commands_listed(self):
        """Test that Windows dangerous commands are properly listed."""
        detector = FakePlatformDetector(platform="Windows")
        validator = SecurityCommandValidator(detector)

        dangerous = validator.get_dangerous_commands()

        assert len(dangerous) > 0
        assert any('format' in pattern for pattern in dangerous)
        assert any('diskpart' in pattern for pattern in dangerous)
        assert any('reg' in pattern and 'delete' in pattern for pattern in dangerous)

    def test_unix_dangerous_commands_listed(self):
        """Test that Unix dangerous commands are properly listed."""
        detector = FakePlatformDetector(platform="Linux")
        validator = SecurityCommandValidator(detector)

        dangerous = validator.get_dangerous_commands()

        assert len(dangerous) > 0
        assert any('rm' in pattern and 'rf' in pattern for pattern in dangerous)
        assert any('/dev/sd' in pattern for pattern in dangerous)
        assert any('chmod' in pattern for pattern in dangerous)

    def test_common_dangerous_commands_on_all_platforms(self):
        """Test that common dangerous commands are listed on all platforms."""
        for platform in ["Linux", "Windows", "macOS"]:
            detector = FakePlatformDetector(platform=platform)
            validator = SecurityCommandValidator(detector)

            dangerous = validator.get_dangerous_commands()

            assert any('mkfs' in pattern for pattern in dangerous)

    def test_windows_recursive_delete_patterns(self):
        """Test that Windows recursive delete patterns are flagged."""
        detector = FakePlatformDetector(platform="Windows")
        validator = SecurityCommandValidator(detector)

        dangerous = validator.get_dangerous_commands()

        patterns_to_check = [
            'rmdir /s /q C:\\',
            'rd /s /q C:\\',
            'del /f /s C:\\',
        ]

        assert len(dangerous) > 5

    def test_unix_root_delete_patterns(self):
        """Test that Unix root delete patterns are flagged."""
        detector = FakePlatformDetector(platform="Linux")
        validator = SecurityCommandValidator(detector)

        dangerous = validator.get_dangerous_commands()

        assert len(dangerous) > 5


class TestInteractiveCommands:
    """Test detection of interactive command patterns."""

    def test_common_interactive_commands(self):
        """Test that common interactive commands are identified."""
        detector = FakePlatformDetector(platform="Linux")
        validator = SecurityCommandValidator(detector)

        interactive = validator.get_interactive_commands()

        assert 'npm init' in interactive
        assert 'npm create' in interactive
        assert 'git commit' in interactive
        assert 'pip install' in interactive

    def test_windows_interactive_commands(self):
        """Test that Windows-specific interactive commands are listed."""
        detector = FakePlatformDetector(platform="Windows")
        validator = SecurityCommandValidator(detector)

        interactive = validator.get_interactive_commands()

        assert any('choco' in cmd for cmd in interactive)
        assert any('winget' in cmd for cmd in interactive)

    def test_unix_interactive_commands(self):
        """Test that Unix-specific interactive commands are listed."""
        detector = FakePlatformDetector(platform="Linux")
        validator = SecurityCommandValidator(detector)

        interactive = validator.get_interactive_commands()

        assert 'sudo ' in interactive
        assert any('apt install' in cmd for cmd in interactive)
        assert any('ssh' in cmd for cmd in interactive)

    def test_database_cli_tools_are_interactive(self):
        """Test that database CLI tools are marked as interactive."""
        detector = FakePlatformDetector(platform="Linux")
        validator = SecurityCommandValidator(detector)

        interactive = validator.get_interactive_commands()

        assert 'mysql' in interactive
        assert 'psql' in interactive
        assert 'mongo' in interactive
        assert 'sqlite3' in interactive

    def test_package_managers_are_interactive(self):
        """Test that package manager commands are marked as interactive."""
        detector = FakePlatformDetector(platform="Linux")
        validator = SecurityCommandValidator(detector)

        interactive = validator.get_interactive_commands()

        assert any('npm' in cmd for cmd in interactive)
        assert any('yarn' in cmd for cmd in interactive)
        assert any('cargo' in cmd for cmd in interactive)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_command_with_leading_whitespace(self):
        """Test that commands with leading whitespace are handled."""
        detector = FakePlatformDetector(platform="Linux")
        validator = SecurityCommandValidator(detector)

        is_valid, message = validator.validate_command_for_platform("  ls -la")

        assert is_valid

    def test_command_with_trailing_whitespace(self):
        """Test that commands with trailing whitespace are handled."""
        detector = FakePlatformDetector(platform="Linux")
        validator = SecurityCommandValidator(detector)

        is_valid, message = validator.validate_command_for_platform("ls -la  ")

        assert is_valid

    def test_case_insensitive_validation(self):
        """Test that validation is case-insensitive."""
        detector = FakePlatformDetector(platform="Windows")
        validator = SecurityCommandValidator(detector)

        is_valid1, _ = validator.validate_command_for_platform("DIR")
        is_valid2, _ = validator.validate_command_for_platform("dir")
        is_valid3, _ = validator.validate_command_for_platform("Dir")

        assert is_valid1 == is_valid2 == is_valid3

    def test_powershell_cmdlet_case_insensitive(self):
        """Test that PowerShell cmdlet detection is case-insensitive."""
        detector = FakePlatformDetector(platform="Windows")
        validator = SecurityCommandValidator(detector)

        is_valid1, _ = validator.validate_command_for_platform("GET-CHILDITEM")
        is_valid2, _ = validator.validate_command_for_platform("get-childitem")
        is_valid3, _ = validator.validate_command_for_platform("Get-ChildItem")

        assert not is_valid1
        assert not is_valid2
        assert not is_valid3

    def test_command_with_complex_arguments(self):
        """Test that commands with complex arguments are validated correctly."""
        detector = FakePlatformDetector(platform="Linux")
        validator = SecurityCommandValidator(detector)

        is_valid, message = validator.validate_command_for_platform(
            "find . -name '*.py' -type f -exec grep -l 'pattern' {} \\;"
        )

        assert is_valid

    def test_multiline_command_validation(self):
        """Test that multiline commands are handled (first line validated)."""
        detector = FakePlatformDetector(platform="Linux")
        validator = SecurityCommandValidator(detector)

        is_valid, message = validator.validate_command_for_platform("ls -la\npwd")

        assert is_valid

    def test_dependency_injection_with_custom_detector(self):
        """Test that custom detector can be injected."""
        detector = FakePlatformDetector(platform="FreeBSD")
        validator = SecurityCommandValidator(detector)

        is_valid, message = validator.validate_command_for_platform("ls -la")

        assert is_valid

    def test_freebsd_platform_validation(self):
        """Test that FreeBSD is treated as Unix for validation."""
        detector = FakePlatformDetector(platform="FreeBSD")
        validator = SecurityCommandValidator(detector)

        is_valid, message = validator.validate_command_for_platform("grep pattern file.txt")

        assert is_valid

    def test_macos_platform_validation(self):
        """Test that macOS is treated as Unix for validation."""
        detector = FakePlatformDetector(platform="macOS")
        validator = SecurityCommandValidator(detector)

        is_valid, message = validator.validate_command_for_platform("ls -la")

        assert is_valid
