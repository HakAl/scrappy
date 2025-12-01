"""Tests for subcommand validation.

Tests the validation layer for command subarguments like 'cache clear',
'context explore', 'session save', etc.
"""

import pytest
from scrappy.cli.validators.subcommand import (
    validate_subcommand,
    SubcommandValidationResult,
    COMMAND_SUBCOMMANDS,
)

class TestValidateSubcommand:
    """Tests for validate_subcommand() function."""

    # Valid subcommands for cache command
    def test_cache_clear_valid(self):
        """Should accept 'clear' as valid cache subcommand."""
        result = validate_subcommand("cache", "clear")
        assert result.is_valid
        assert result.subcommand == "clear"
        assert result.args == ""

    def test_cache_toggle_valid(self):
        """Should accept 'toggle' as valid cache subcommand."""
        result = validate_subcommand("cache", "toggle")
        assert result.is_valid
        assert result.subcommand == "toggle"

    def test_cache_empty_valid(self):
        """Should accept empty string (show status) as valid."""
        result = validate_subcommand("cache", "")
        assert result.is_valid
        assert result.subcommand == ""

    def test_cache_none_valid(self):
        """Should accept None (show status) as valid."""
        result = validate_subcommand("cache", None)
        assert result.is_valid
        assert result.subcommand == ""

    # Valid subcommands for context command
    def test_context_explore_removed(self):
        """Should reject 'explore' (removed in Phase 2, use /explore instead)."""
        result = validate_subcommand("context", "explore")
        assert not result.is_valid
        # explore was removed - users should use /explore command instead

    def test_context_refresh_valid(self):
        """Should accept 'refresh' as valid context subcommand."""
        result = validate_subcommand("context", "refresh")
        assert result.is_valid
        assert result.subcommand == "refresh"

    def test_context_clear_valid(self):
        """Should accept 'clear' as valid context subcommand."""
        result = validate_subcommand("context", "clear")
        assert result.is_valid
        assert result.subcommand == "clear"

    def test_context_add_valid(self):
        """Should accept 'add' as valid context subcommand."""
        result = validate_subcommand("context", "add")
        assert result.is_valid
        assert result.subcommand == "add"

    # Valid subcommands for session command
    def test_session_save_valid(self):
        """Should accept 'save' as valid session subcommand."""
        result = validate_subcommand("session", "save")
        assert result.is_valid
        assert result.subcommand == "save"

    def test_session_load_valid(self):
        """Should accept 'load' as valid session subcommand."""
        result = validate_subcommand("session", "load")
        assert result.is_valid
        assert result.subcommand == "load"

    def test_session_clear_valid(self):
        """Should accept 'clear' as valid session subcommand."""
        result = validate_subcommand("session", "clear")
        assert result.is_valid
        assert result.subcommand == "clear"

    def test_session_toggle_valid(self):
        """Should accept 'toggle' as valid session subcommand."""
        result = validate_subcommand("session", "toggle")
        assert result.is_valid
        assert result.subcommand == "toggle"

    # Valid subcommands for limits command (rate limiter)
    def test_limits_reset_valid(self):
        """Should accept 'reset' as valid limits subcommand."""
        result = validate_subcommand("limits", "reset")
        assert result.is_valid
        assert result.subcommand == "reset"

    def test_limits_reset_with_provider_valid(self):
        """Should accept 'reset provider' with args."""
        result = validate_subcommand("limits", "reset cerebras")
        assert result.is_valid
        assert result.subcommand == "reset"
        assert result.args == "cerebras"

    def test_limits_with_provider_filter_valid(self):
        """Should accept provider name as filter (passthrough)."""
        result = validate_subcommand("limits", "anthropic")
        assert result.is_valid
        # Provider filter is not a subcommand, passes through
        assert result.subcommand == ""
        assert result.args == "anthropic"

    # Case insensitivity tests
    def test_cache_clear_uppercase_valid(self):
        """Should accept uppercase subcommands."""
        result = validate_subcommand("cache", "CLEAR")
        assert result.is_valid
        assert result.subcommand == "clear"

    def test_context_refresh_mixed_case_valid(self):
        """Should accept mixed case subcommands."""
        result = validate_subcommand("context", "Refresh")
        assert result.is_valid
        assert result.subcommand == "refresh"

    def test_session_save_mixed_case_valid(self):
        """Should normalize mixed case to lowercase."""
        result = validate_subcommand("session", "SAVE")
        assert result.is_valid
        assert result.subcommand == "save"

    # Invalid subcommands
    def test_cache_invalid_subcommand_fails(self):
        """Should reject unknown cache subcommand."""
        result = validate_subcommand("cache", "invalid")
        assert not result.is_valid
        assert "unknown" in result.error.lower() or "invalid" in result.error.lower()

    def test_context_invalid_subcommand_fails(self):
        """Should reject unknown context subcommand."""
        result = validate_subcommand("context", "delete")
        assert not result.is_valid

    def test_session_invalid_subcommand_fails(self):
        """Should reject unknown session subcommand."""
        result = validate_subcommand("session", "remove")
        assert not result.is_valid

    # Unknown command validation
    def test_unknown_command_fails(self):
        """Should reject validation for unknown commands."""
        result = validate_subcommand("notacommand", "anything")
        assert not result.is_valid
        assert "command" in result.error.lower()

    # Whitespace handling
    def test_subcommand_with_leading_whitespace(self):
        """Should trim leading whitespace from subcommand."""
        result = validate_subcommand("cache", "  clear")
        assert result.is_valid
        assert result.subcommand == "clear"

    def test_subcommand_with_trailing_whitespace(self):
        """Should trim trailing whitespace from subcommand."""
        result = validate_subcommand("cache", "toggle  ")
        assert result.is_valid
        assert result.subcommand == "toggle"

    def test_whitespace_only_treated_as_empty(self):
        """Should treat whitespace-only as empty subcommand."""
        result = validate_subcommand("cache", "   ")
        assert result.is_valid
        assert result.subcommand == ""

    # Edge cases
    def test_subcommand_with_extra_args(self):
        """Should extract subcommand and preserve remaining args."""
        result = validate_subcommand("session", "save my_session_name")
        assert result.is_valid
        assert result.subcommand == "save"
        assert result.args == "my_session_name"

    def test_context_add_with_path_arg(self):
        """Should preserve path argument for context add."""
        result = validate_subcommand("context", "add src/cli/commands.py")
        assert result.is_valid
        assert result.subcommand == "add"
        assert result.args == "src/cli/commands.py"

    def test_command_case_insensitivity(self):
        """Should accept command name in any case."""
        result = validate_subcommand("CACHE", "clear")
        assert result.is_valid
        assert result.subcommand == "clear"

    def test_command_with_extra_whitespace(self):
        """Should handle command with leading/trailing whitespace."""
        result = validate_subcommand("  session  ", "save")
        assert result.is_valid
        assert result.subcommand == "save"


class TestSubcommandValidatorIntegration:
    """Integration tests for subcommand validation."""


    def test_validator_is_pure_function(self):
        """Validator should have no side effects."""
        result1 = validate_subcommand("cache", "clear")
        result2 = validate_subcommand("cache", "clear")

        assert result1.is_valid == result2.is_valid
        assert result1.subcommand == result2.subcommand
        assert result1.args == result2.args

    def test_all_registered_commands_validate(self):
        """All registered commands should successfully validate their subcommands."""
        for command, subcommands in COMMAND_SUBCOMMANDS.items():
            for subcommand in subcommands:
                result = validate_subcommand(command, subcommand)
                assert result.is_valid, f"{command} {subcommand} should be valid"


class TestSubcommandErrorMessages:
    """Tests for helpful error messages."""

    def test_unknown_command_error_mentions_command(self):
        """Error for unknown command should mention the command."""
        result = validate_subcommand("badcommand", "anything")
        assert "badcommand" in result.error.lower() or "command" in result.error.lower()

    def test_unknown_subcommand_error_lists_valid_options(self):
        """Error for unknown subcommand should list valid options."""
        result = validate_subcommand("cache", "badsubcommand")
        assert not result.is_valid
        # Error should mention valid options
        assert "clear" in result.error or "toggle" in result.error or "valid" in result.error.lower()

    def test_error_for_similar_subcommand(self):
        """Should provide helpful error for typos."""
        result = validate_subcommand("cache", "cler")  # typo for 'clear'
        assert not result.is_valid
        # Should still reject but could suggest 'clear'
