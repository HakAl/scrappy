"""
Tests for CommandSecurity component.

Tests security validation functionality following TDD principles.
"""

import pytest
from src.agent_tools.components.command_security import CommandSecurity


class TestCommandSecurityDangerousCommands:
    """Test dangerous command detection."""

    def test_blocks_rm_rf_root(self):
        """Should block rm -rf / command."""
        security = CommandSecurity()
        with pytest.raises(ValueError, match="dangerous"):
            security.validate("rm -rf /")

    def test_blocks_rm_rf_wildcard(self):
        """Should block rm -rf * command."""
        security = CommandSecurity()
        with pytest.raises(ValueError, match="dangerous"):
            security.validate("rm -rf *")

    def test_blocks_format_drive(self):
        """Should block format C: command on Windows."""
        security = CommandSecurity()
        with pytest.raises(ValueError, match="dangerous"):
            security.validate("format C:")

    def test_blocks_mkfs(self):
        """Should block mkfs commands that format disks."""
        security = CommandSecurity()
        with pytest.raises(ValueError, match="dangerous"):
            security.validate("mkfs.ext4 /dev/sda1")

    def test_blocks_dd_commands(self):
        """Should block dd commands that can overwrite disks."""
        security = CommandSecurity()
        with pytest.raises(ValueError, match="dangerous"):
            security.validate("dd if=/dev/zero of=/dev/sda")

    def test_blocks_fork_bomb(self):
        """Should block fork bomb pattern."""
        security = CommandSecurity()
        with pytest.raises(ValueError, match="dangerous"):
            security.validate(":(){ :|:& };:")

    def test_blocks_sudo_rm(self):
        """Should block sudo rm commands."""
        security = CommandSecurity()
        with pytest.raises(ValueError, match="dangerous"):
            security.validate("sudo rm -rf /etc")


class TestCommandSecuritySafeCommands:
    """Test that safe commands are allowed."""

    def test_allows_ls(self):
        """Should allow ls command."""
        security = CommandSecurity()
        security.validate("ls -la")

    def test_allows_npm_install(self):
        """Should allow npm install."""
        security = CommandSecurity()
        security.validate("npm install react")

    def test_allows_git_commands(self):
        """Should allow git commands."""
        security = CommandSecurity()
        security.validate("git status")
        security.validate("git commit -m 'test'")

    def test_allows_mkdir(self):
        """Should allow mkdir command."""
        security = CommandSecurity()
        security.validate("mkdir test-dir")

    def test_allows_cat(self):
        """Should allow cat command."""
        security = CommandSecurity()
        security.validate("cat package.json")

    def test_allows_python_commands(self):
        """Should allow python commands."""
        security = CommandSecurity()
        security.validate("python -m pytest tests/")


class TestCommandSecurityCaseInsensitive:
    """Test case-insensitive pattern matching."""

    def test_blocks_uppercase_rm_rf(self):
        """Should block RM -RF / regardless of case."""
        security = CommandSecurity()
        with pytest.raises(ValueError, match="dangerous"):
            security.validate("RM -RF /")

    def test_blocks_mixed_case_format(self):
        """Should block FORMAT C: regardless of case."""
        security = CommandSecurity()
        with pytest.raises(ValueError, match="dangerous"):
            security.validate("FORMAT C:")


class TestCommandSecurityCustomPatterns:
    """Test custom dangerous patterns."""

    def test_accepts_custom_patterns(self):
        """Should accept and enforce custom dangerous patterns."""
        custom_patterns = [
            r'rm\s+-rf\s+/',
            r'custom_dangerous_cmd',
        ]
        security = CommandSecurity(dangerous_patterns=custom_patterns)

        with pytest.raises(ValueError):
            security.validate("custom_dangerous_cmd arg1")

    def test_custom_patterns_override_defaults(self):
        """Custom patterns should replace defaults, not extend."""
        custom_patterns = [r'only_this_is_dangerous']
        security = CommandSecurity(dangerous_patterns=custom_patterns)

        security.validate("rm -rf /")

        with pytest.raises(ValueError):
            security.validate("only_this_is_dangerous")


class TestCommandSecurityEdgeCases:
    """Test edge cases and boundaries."""

    def test_empty_command(self):
        """Should allow empty command (will fail elsewhere)."""
        security = CommandSecurity()
        security.validate("")

    def test_whitespace_only_command(self):
        """Should allow whitespace-only command."""
        security = CommandSecurity()
        security.validate("   ")

    def test_command_with_escaped_characters_is_blocked(self):
        """Should block dangerous patterns even when quoted (safer approach)."""
        security = CommandSecurity()
        with pytest.raises(ValueError):
            security.validate("echo 'rm -rf /'")

    def test_command_in_quotes_is_still_blocked(self):
        """Dangerous commands should be blocked even in execution context."""
        security = CommandSecurity()
        with pytest.raises(ValueError):
            security.validate("bash -c 'rm -rf /'")
