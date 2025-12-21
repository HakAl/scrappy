"""Tests for CLI input validators.

Tests the validation layer that provides input sanitization and validation
for commands, paths, and providers.
"""

import pytest
from scrappy.cli.validators import (
    validate_command,
    validate_path,
    validate_provider,
    ValidationError,
)


class TestValidateCommand:
    """Tests for validate_command() function."""

    # Valid commands
    def test_valid_help_command(self):
        """Should accept /help command."""
        result = validate_command("/help")
        assert result.is_valid
        assert result.command == "help"
        assert result.args == ""

    def test_valid_status_command(self):
        """Should accept /status command."""
        result = validate_command("/status")
        assert result.is_valid
        assert result.command == "status"

    def test_valid_plan_command_with_args(self):
        """Should accept /plan command with arguments."""
        result = validate_command("/plan create a new feature")
        assert result.is_valid
        assert result.command == "plan"
        assert result.args == "create a new feature"

    def test_valid_reason_command_with_args(self):
        """Should accept /reason command with arguments."""
        result = validate_command("/reason why does this work?")
        assert result.is_valid
        assert result.command == "reason"
        assert result.args == "why does this work?"

    def test_valid_agent_command(self):
        """Should accept /agent command."""
        result = validate_command("/agent implement login")
        assert result.is_valid
        assert result.command == "agent"

    def test_valid_smart_command(self):
        """Should accept /smart command."""
        result = validate_command("/smart research best practices")
        assert result.is_valid
        assert result.command == "smart"

    def test_valid_context_command(self):
        """Should accept /context command."""
        result = validate_command("/context")
        assert result.is_valid
        assert result.command == "context"

    def test_valid_quit_command(self):
        """Should accept /quit command."""
        result = validate_command("/quit")
        assert result.is_valid
        assert result.command == "quit"

    def test_valid_exit_command(self):
        """Should accept /exit command."""
        result = validate_command("/exit")
        assert result.is_valid
        assert result.command == "exit"

    def test_valid_q_shortcut(self):
        """Should accept /q shortcut."""
        result = validate_command("/q")
        assert result.is_valid
        assert result.command == "q"

    def test_valid_verbose_command(self):
        """Should accept /verbose command."""
        result = validate_command("/verbose")
        assert result.is_valid
        assert result.command == "verbose"

    def test_valid_v_command(self):
        """Should accept /v command (verbose shortcut)."""
        result = validate_command("/v")
        assert result.is_valid
        assert result.command == "v"

    def test_valid_ml_command(self):
        """Should accept /ml command."""
        result = validate_command("/ml")
        assert result.is_valid
        assert result.command == "ml"

    # Empty and whitespace checks
    def test_empty_command_fails(self):
        """Should reject empty string."""
        result = validate_command("")
        assert not result.is_valid
        assert "empty" in result.error.lower()

    def test_whitespace_only_fails(self):
        """Should reject whitespace-only input."""
        result = validate_command("   ")
        assert not result.is_valid
        assert "empty" in result.error.lower()

    def test_slash_only_fails(self):
        """Should reject just a slash with no command."""
        result = validate_command("/")
        assert not result.is_valid
        assert "command name" in result.error.lower() or "empty" in result.error.lower()

    # Missing slash prefix
    def test_missing_slash_prefix_fails(self):
        """Should reject command without slash prefix."""
        result = validate_command("help")
        assert not result.is_valid
        assert "slash" in result.error.lower() or "/" in result.error

    # Unknown commands
    def test_unknown_command_fails(self):
        """Should reject unknown commands."""
        result = validate_command("/notacommand")
        assert not result.is_valid
        assert "unknown" in result.error.lower() or "invalid" in result.error.lower()

    def test_unknown_command_with_args_fails(self):
        """Should reject unknown commands even with arguments."""
        result = validate_command("/fakecmd some args")
        assert not result.is_valid

    # Length limits
    def test_command_exceeds_max_length_fails(self):
        """Should reject commands exceeding maximum length."""
        long_args = "x" * 10000
        result = validate_command(f"/plan {long_args}")
        assert not result.is_valid
        assert "length" in result.error.lower() or "long" in result.error.lower()

    def test_command_at_reasonable_length_succeeds(self):
        """Should accept commands at reasonable length."""
        args = "x" * 500
        result = validate_command(f"/plan {args}")
        assert result.is_valid

    # Invalid characters
    def test_null_character_fails(self):
        """Should reject commands with null characters."""
        result = validate_command("/help\x00")
        assert not result.is_valid
        assert "character" in result.error.lower() or "invalid" in result.error.lower()

    def test_control_characters_fail(self):
        """Should reject commands with control characters."""
        result = validate_command("/plan\x07test")
        assert not result.is_valid

    # Case sensitivity
    def test_uppercase_command_normalized(self):
        """Should handle uppercase commands appropriately."""
        result = validate_command("/HELP")
        # Either accept with normalization or reject - just be consistent
        # Most CLIs normalize to lowercase
        if result.is_valid:
            assert result.command == "help"
        else:
            assert "case" in result.error.lower() or "unknown" in result.error.lower()

    # Edge cases
    def test_command_with_extra_whitespace_normalized(self):
        """Should handle extra whitespace in arguments."""
        result = validate_command("/plan   lots   of   spaces  ")
        assert result.is_valid
        assert result.command == "plan"
        # Args should be preserved or normalized

    def test_command_with_newline_in_args_allowed(self):
        """Should allow newlines in command arguments (multiline input)."""
        result = validate_command("/plan line1\nline2")
        assert result.is_valid
        assert result.command == "plan"
        assert "line1" in result.args
        assert "line2" in result.args

    def test_command_with_tab_in_args(self):
        """Should handle tabs in arguments appropriately."""
        result = validate_command("/plan task\twith\ttabs")
        # Tabs might be allowed in args, or converted to spaces
        # Just verify consistent behavior
        assert result.is_valid or "character" in result.error.lower()


class TestValidatePath:
    """Tests for validate_path() function."""

    # Valid paths
    def test_valid_relative_path(self):
        """Should accept valid relative path."""
        result = validate_path("src/cli/commands.py")
        assert result.is_valid
        assert result.path == "src/cli/commands.py"

    def test_valid_absolute_unix_path(self):
        """Should accept valid absolute Unix path."""
        result = validate_path("/home/user/project/file.py")
        assert result.is_valid

    def test_valid_absolute_windows_path(self):
        """Should accept valid absolute Windows path."""
        result = validate_path("C:\\Users\\user\\project\\file.py")
        assert result.is_valid

    def test_valid_windows_forward_slash(self):
        """Should accept Windows path with forward slashes."""
        result = validate_path("C:/Users/user/project/file.py")
        assert result.is_valid

    def test_valid_directory_path(self):
        """Should accept directory paths."""
        result = validate_path("src/cli/")
        assert result.is_valid

    def test_valid_simple_filename(self):
        """Should accept simple filename."""
        result = validate_path("README.md")
        assert result.is_valid

    def test_valid_dotfile(self):
        """Should accept dotfiles."""
        result = validate_path(".gitignore")
        assert result.is_valid

    def test_valid_path_with_dots(self):
        """Should accept paths with parent directory references."""
        result = validate_path("../other/file.py")
        assert result.is_valid

    def test_valid_path_with_numbers(self):
        """Should accept paths with numbers."""
        result = validate_path("src/v2/module123.py")
        assert result.is_valid

    def test_valid_path_with_hyphens_underscores(self):
        """Should accept paths with hyphens and underscores."""
        result = validate_path("my-project/sub_dir/file-name_v2.py")
        assert result.is_valid

    # Empty and whitespace checks
    def test_empty_path_fails(self):
        """Should reject empty path."""
        result = validate_path("")
        assert not result.is_valid
        assert "empty" in result.error.lower()

    def test_whitespace_only_path_fails(self):
        """Should reject whitespace-only path."""
        result = validate_path("   ")
        assert not result.is_valid
        assert "empty" in result.error.lower()

    # Invalid characters
    def test_null_character_in_path_fails(self):
        """Should reject paths with null characters."""
        result = validate_path("src/file\x00.py")
        assert not result.is_valid
        assert "character" in result.error.lower()

    def test_newline_in_path_fails(self):
        """Should reject paths with newlines."""
        result = validate_path("src/file\n.py")
        assert not result.is_valid

    def test_control_characters_in_path_fail(self):
        """Should reject paths with control characters."""
        result = validate_path("src/\x07file.py")
        assert not result.is_valid

    # Platform-specific invalid characters
    def test_invalid_windows_characters_detected(self):
        """Should detect invalid Windows filename characters."""
        # Characters invalid in Windows filenames: < > : " | ? *
        result = validate_path("src/file<name>.py")
        # Should warn or fail on Windows-invalid chars
        assert not result.is_valid or result.warnings

    def test_colon_in_filename_detected(self):
        """Should detect colon in filename (invalid on Windows)."""
        result = validate_path("src/file:name.py")
        # Note: C: at start is valid, but : elsewhere is not
        assert not result.is_valid or result.warnings

    def test_asterisk_in_path_fails(self):
        """Should reject paths with asterisks (glob chars)."""
        result = validate_path("src/*.py")
        # Glob patterns should not be accepted as file paths
        assert not result.is_valid

    def test_question_mark_in_path_fails(self):
        """Should reject paths with question marks."""
        result = validate_path("src/file?.py")
        assert not result.is_valid

    # Length limits
    def test_path_exceeds_max_length_fails(self):
        """Should reject paths exceeding maximum length."""
        long_path = "a" * 300 + "/" + "b" * 300
        result = validate_path(long_path)
        assert not result.is_valid
        assert "length" in result.error.lower() or "long" in result.error.lower()

    def test_path_component_exceeds_max_length_fails(self):
        """Should reject path components exceeding 255 characters."""
        long_component = "x" * 300
        result = validate_path(f"src/{long_component}/file.py")
        assert not result.is_valid

    def test_reasonable_path_length_succeeds(self):
        """Should accept paths of reasonable length."""
        path = "src/" + "/".join(["dir"] * 10) + "/file.py"
        result = validate_path(path)
        assert result.is_valid

    # Edge cases
    def test_path_with_spaces(self):
        """Should handle paths with spaces."""
        result = validate_path("My Documents/file.py")
        assert result.is_valid

    def test_path_with_unicode(self):
        """Should handle paths with unicode characters."""
        result = validate_path("src/archivo.py")
        assert result.is_valid

    def test_double_slashes_normalized(self):
        """Should handle or reject double slashes."""
        result = validate_path("src//cli//file.py")
        # Either normalize or reject - just be consistent
        if result.is_valid:
            assert "//" not in result.path

    def test_trailing_slash(self):
        """Should accept trailing slashes for directories."""
        result = validate_path("src/cli/")
        assert result.is_valid

    def test_current_directory_reference(self):
        """Should accept current directory reference."""
        result = validate_path("./file.py")
        assert result.is_valid

    def test_multiple_dots_in_path(self):
        """Should handle multiple dots appropriately."""
        result = validate_path("src/file.test.py")
        assert result.is_valid

    # Security concerns
    def test_path_traversal_warning(self):
        """Should warn about excessive path traversal."""
        result = validate_path("../../../../etc/passwd")
        # Should either warn or restrict dangerous traversals
        assert not result.is_valid or result.warnings


class TestValidateProvider:
    """Tests for validate_provider() function."""

    # Valid providers
    def test_valid_cerebras_provider(self):
        """Should accept cerebras provider."""
        result = validate_provider("cerebras")
        assert result.is_valid
        assert result.provider == "cerebras"

    def test_valid_groq_provider(self):
        """Should accept groq provider."""
        result = validate_provider("groq")
        assert result.is_valid
        assert result.provider == "groq"

    def test_valid_gemini_provider(self):
        """Should accept gemini provider."""
        result = validate_provider("gemini")
        assert result.is_valid
        assert result.provider == "gemini"

    def test_valid_sambanova_provider(self):
        """Should accept sambanova provider."""
        result = validate_provider("sambanova")
        assert result.is_valid
        assert result.provider == "sambanova"

    # Empty and whitespace checks
    def test_empty_provider_fails(self):
        """Should reject empty provider."""
        result = validate_provider("")
        assert not result.is_valid
        assert "empty" in result.error.lower()

    def test_whitespace_only_provider_fails(self):
        """Should reject whitespace-only provider."""
        result = validate_provider("   ")
        assert not result.is_valid
        assert "empty" in result.error.lower()

    # Unknown providers
    def test_unknown_provider_fails(self):
        """Should reject unknown providers."""
        result = validate_provider("notaprovider")
        assert not result.is_valid
        assert "unknown" in result.error.lower() or "invalid" in result.error.lower()

    def test_misspelled_provider_fails(self):
        """Should reject misspelled providers."""
        result = validate_provider("cerebrass")  # extra 's'
        assert not result.is_valid

    def test_partial_provider_name_fails(self):
        """Should reject partial provider names."""
        result = validate_provider("cere")
        assert not result.is_valid

    # Case sensitivity
    def test_uppercase_provider_normalized(self):
        """Should normalize uppercase providers."""
        result = validate_provider("CEREBRAS")
        if result.is_valid:
            assert result.provider == "cerebras"
        else:
            # If strict, should at least give helpful error
            assert "cerebras" in result.error.lower()

    def test_mixed_case_provider_normalized(self):
        """Should normalize mixed case providers."""
        result = validate_provider("Gemini")
        if result.is_valid:
            assert result.provider == "gemini"

    # Invalid characters
    def test_provider_with_spaces_fails(self):
        """Should reject providers with spaces."""
        result = validate_provider("github models")
        assert not result.is_valid

    def test_provider_with_special_chars_fails(self):
        """Should reject providers with special characters."""
        result = validate_provider("cerebras!")
        assert not result.is_valid

    def test_provider_with_null_char_fails(self):
        """Should reject providers with null characters."""
        result = validate_provider("groq\x00")
        assert not result.is_valid

    # Length limits
    def test_provider_exceeds_max_length_fails(self):
        """Should reject provider names exceeding reasonable length."""
        long_provider = "x" * 100
        result = validate_provider(long_provider)
        assert not result.is_valid
        assert "length" in result.error.lower() or "unknown" in result.error.lower()

    # Edge cases
    def test_provider_with_leading_whitespace_normalized(self):
        """Should trim leading whitespace."""
        result = validate_provider("  cerebras")
        if result.is_valid:
            assert result.provider == "cerebras"

    def test_provider_with_trailing_whitespace_normalized(self):
        """Should trim trailing whitespace."""
        result = validate_provider("groq  ")
        if result.is_valid:
            assert result.provider == "groq"

    def test_provider_with_underscore_format_valid(self):
        """Should accept underscore format (fails on unknown provider, not format)."""
        result = validate_provider("some_provider")
        # Format is valid (has underscore) but rejected because not in VALID_PROVIDERS
        assert not result.is_valid
        assert "unknown provider" in result.error.lower()

    def test_numeric_provider_fails(self):
        """Should reject purely numeric providers."""
        result = validate_provider("12345")
        assert not result.is_valid

    def test_provider_starting_with_number_fails(self):
        """Should reject providers starting with numbers."""
        result = validate_provider("2fast")
        assert not result.is_valid

class TestValidatorIntegration:
    """Integration tests for validators working together."""


    def test_validators_handle_none_input_gracefully(self):
        """Validators should handle None input without crashing."""
        # Should either raise TypeError or return invalid result
        for validator, name in [
            (validate_command, "command"),
            (validate_path, "path"),
            (validate_provider, "provider")
        ]:
            try:
                result = validator(None)
                assert not result.is_valid
            except (TypeError, ValidationError):
                pass  # Also acceptable

    def test_validators_are_pure_functions(self):
        """Validators should not have side effects."""
        # Same input should always produce same output
        for _ in range(3):
            result1 = validate_command("/help")
            result2 = validate_command("/help")
            assert result1.is_valid == result2.is_valid
            assert result1.command == result2.command
