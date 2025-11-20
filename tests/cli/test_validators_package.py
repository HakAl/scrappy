"""Tests for validators package structure.

Tests that the validators package is properly decomposed into modules
while maintaining backward compatibility.
"""

import pytest
import importlib
import sys


class TestValidatorsPackageStructure:
    """Tests for the validators package module structure."""







class TestBaseModule:
    """Tests for the base.py module."""

    def test_validation_error_in_base(self):
        """ValidationError should be defined in base module."""
        from src.cli.validators.base import ValidationError

        error = ValidationError("test error", field="test", value="bad")
        assert str(error) == "test error"
        assert error.field == "test"
        assert error.value == "bad"

    def test_control_chars_pattern_in_base(self):
        """CONTROL_CHARS_PATTERN should be defined in base module."""
        from src.cli.validators.base import CONTROL_CHARS_PATTERN

        assert CONTROL_CHARS_PATTERN.search("\x00") is not None
        assert CONTROL_CHARS_PATTERN.search("\x07") is not None
        assert CONTROL_CHARS_PATTERN.search("normal") is None

    def test_newline_pattern_in_base(self):
        """NEWLINE_PATTERN should be defined in base module."""
        from src.cli.validators.base import NEWLINE_PATTERN

        assert NEWLINE_PATTERN.search("\n") is not None
        assert NEWLINE_PATTERN.search("\r") is not None
        assert NEWLINE_PATTERN.search("normal") is None


class TestCommandModule:
    """Tests for the command.py module."""

    def test_command_validation_result_in_command(self):
        """CommandValidationResult should be defined in command module."""
        from src.cli.validators.command import CommandValidationResult

        result = CommandValidationResult(
            is_valid=True,
            command="help",
            args="test"
        )
        assert result.is_valid
        assert result.command == "help"
        assert result.args == "test"

    def test_validate_command_in_command(self):
        """validate_command should be defined in command module."""
        from src.cli.validators.command import validate_command

        result = validate_command("/help")
        assert result.is_valid
        assert result.command == "help"

    def test_valid_commands_in_command(self):
        """VALID_COMMANDS should be defined in command module."""
        from src.cli.validators.command import VALID_COMMANDS

        assert "help" in VALID_COMMANDS
        assert "plan" in VALID_COMMANDS
        assert "quit" in VALID_COMMANDS

    def test_max_command_length_in_command(self):
        """MAX_COMMAND_LENGTH should be defined in command module."""
        from src.cli.validators.command import MAX_COMMAND_LENGTH

        assert MAX_COMMAND_LENGTH == 5000


class TestPathModule:
    """Tests for the path.py module."""

    def test_path_validation_result_in_path(self):
        """PathValidationResult should be defined in path module."""
        from src.cli.validators.path import PathValidationResult

        result = PathValidationResult(
            is_valid=True,
            path="src/file.py"
        )
        assert result.is_valid
        assert result.path == "src/file.py"

    def test_validate_path_in_path(self):
        """validate_path should be defined in path module."""
        from src.cli.validators.path import validate_path

        result = validate_path("src/cli/validators.py")
        assert result.is_valid
        assert result.path == "src/cli/validators.py"

    def test_max_path_length_in_path(self):
        """MAX_PATH_LENGTH should be defined in path module."""
        from src.cli.validators.path import MAX_PATH_LENGTH

        assert MAX_PATH_LENGTH == 500

    def test_max_path_component_length_in_path(self):
        """MAX_PATH_COMPONENT_LENGTH should be defined in path module."""
        from src.cli.validators.path import MAX_PATH_COMPONENT_LENGTH

        assert MAX_PATH_COMPONENT_LENGTH == 255

    def test_windows_invalid_chars_in_path(self):
        """WINDOWS_INVALID_CHARS should be defined in path module."""
        from src.cli.validators.path import WINDOWS_INVALID_CHARS

        assert WINDOWS_INVALID_CHARS.search("<") is not None
        assert WINDOWS_INVALID_CHARS.search(">") is not None
        assert WINDOWS_INVALID_CHARS.search("normal") is None

    def test_glob_chars_pattern_in_path(self):
        """GLOB_CHARS_PATTERN should be defined in path module."""
        from src.cli.validators.path import GLOB_CHARS_PATTERN

        assert GLOB_CHARS_PATTERN.search("*") is not None
        assert GLOB_CHARS_PATTERN.search("?") is not None
        assert GLOB_CHARS_PATTERN.search("normal") is None


class TestProviderModule:
    """Tests for the provider.py module."""

    def test_provider_validation_result_in_provider(self):
        """ProviderValidationResult should be defined in provider module."""
        from src.cli.validators.provider import ProviderValidationResult

        result = ProviderValidationResult(
            is_valid=True,
            provider="cerebras"
        )
        assert result.is_valid
        assert result.provider == "cerebras"

    def test_validate_provider_in_provider(self):
        """validate_provider should be defined in provider module."""
        from src.cli.validators.provider import validate_provider

        result = validate_provider("cerebras")
        assert result.is_valid
        assert result.provider == "cerebras"

    def test_valid_providers_in_provider(self):
        """VALID_PROVIDERS should be defined in provider module."""
        from src.cli.validators.provider import VALID_PROVIDERS

        assert "cerebras" in VALID_PROVIDERS
        assert "groq" in VALID_PROVIDERS
        assert "gemini" in VALID_PROVIDERS

    def test_max_provider_length_in_provider(self):
        """MAX_PROVIDER_LENGTH should be defined in provider module."""
        from src.cli.validators.provider import MAX_PROVIDER_LENGTH

        assert MAX_PROVIDER_LENGTH == 50


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing imports."""

    def test_validation_error_importable_from_validators(self):
        """ValidationError should be importable from src.cli.validators."""
        from src.cli.validators import ValidationError

        error = ValidationError("test")
        assert str(error) == "test"

    def test_command_validation_result_importable(self):
        """CommandValidationResult should be importable from src.cli.validators."""
        from src.cli.validators import CommandValidationResult

        result = CommandValidationResult(is_valid=True, command="test")
        assert result.is_valid

    def test_path_validation_result_importable(self):
        """PathValidationResult should be importable from src.cli.validators."""
        from src.cli.validators import PathValidationResult

        result = PathValidationResult(is_valid=True, path="test")
        assert result.is_valid

    def test_provider_validation_result_importable(self):
        """ProviderValidationResult should be importable from src.cli.validators."""
        from src.cli.validators import ProviderValidationResult

        result = ProviderValidationResult(is_valid=True, provider="test")
        assert result.is_valid

    def test_validate_command_importable(self):
        """validate_command should be importable from src.cli.validators."""
        from src.cli.validators import validate_command

        result = validate_command("/help")
        assert result.is_valid

    def test_validate_path_importable(self):
        """validate_path should be importable from src.cli.validators."""
        from src.cli.validators import validate_path

        result = validate_path("src/file.py")
        assert result.is_valid

    def test_validate_provider_importable(self):
        """validate_provider should be importable from src.cli.validators."""
        from src.cli.validators import validate_provider

        result = validate_provider("cerebras")
        assert result.is_valid

    def test_valid_commands_importable(self):
        """VALID_COMMANDS should be importable from src.cli.validators."""
        from src.cli.validators import VALID_COMMANDS

        assert "help" in VALID_COMMANDS

    def test_valid_providers_importable(self):
        """VALID_PROVIDERS should be importable from src.cli.validators."""
        from src.cli.validators import VALID_PROVIDERS

        assert "cerebras" in VALID_PROVIDERS


class TestModuleIndependence:
    """Tests that modules can be used independently."""

    def test_command_module_uses_base(self):
        """Command module should import shared patterns from base."""
        from src.cli.validators.command import validate_command

        # Control characters should be rejected (uses CONTROL_CHARS_PATTERN from base)
        result = validate_command("/help\x00")
        assert not result.is_valid
        assert "character" in result.error.lower()

    def test_path_module_uses_base(self):
        """Path module should import shared patterns from base."""
        from src.cli.validators.path import validate_path

        # Control characters should be rejected (uses CONTROL_CHARS_PATTERN from base)
        result = validate_path("src/\x00file.py")
        assert not result.is_valid
        assert "character" in result.error.lower()

    def test_provider_module_uses_base(self):
        """Provider module should import shared patterns from base."""
        from src.cli.validators.provider import validate_provider

        # Control characters should be rejected (uses CONTROL_CHARS_PATTERN from base)
        result = validate_provider("cerebras\x00")
        assert not result.is_valid
        assert "character" in result.error.lower()


class TestAllExport:
    """Tests for __all__ exports in the package."""

    def test_all_exports_defined(self):
        """__all__ should be defined in validators package."""
        from src.cli import validators

        assert hasattr(validators, '__all__')
        assert len(validators.__all__) > 0


    def test_all_exports_complete(self):
        """__all__ should include all public exports."""
        from src.cli import validators

        expected = {
            'ValidationError',
            'CommandValidationResult', 'validate_command', 'VALID_COMMANDS',
            'PathValidationResult', 'validate_path',
            'ProviderValidationResult', 'validate_provider', 'VALID_PROVIDERS',
        }

        for name in expected:
            assert name in validators.__all__, f"{name} missing from __all__"


class TestExistingTestsStillWork:
    """Verify existing test patterns still work after refactoring."""

    def test_original_import_pattern(self):
        """Original import pattern from existing tests should work."""
        from src.cli.validators import (
            validate_command,
            validate_path,
            validate_provider,
            ValidationError,
        )

        # Same tests as in test_validators.py
        result = validate_command("/help")
        assert result.is_valid
        assert result.command == "help"

        result = validate_path("src/cli/commands.py")
        assert result.is_valid

        result = validate_provider("cerebras")
        assert result.is_valid
        assert result.provider == "cerebras"

        error = ValidationError("test error", field="test", value="bad")
        assert error.field == "test"

    def test_valid_commands_complete(self):
        """VALID_COMMANDS should contain all expected commands."""
        from src.cli.validators import VALID_COMMANDS

        expected_commands = {
            "help", "status", "quit", "exit", "q", "clear",
            "plan", "reason", "agent", "smart", "tasks", "classify",
            "providers", "brain", "usage", "models",
            "context", "cache", "session", "limits",
            "synthesize", "delegate",
            "explore",
            "auto", "route", "autoroute", "ml", "multiline", "paste", "autoexec"
        }

        for cmd in expected_commands:
            assert cmd in VALID_COMMANDS, f"{cmd} missing from VALID_COMMANDS"

    def test_valid_providers_complete(self):
        """VALID_PROVIDERS should contain all expected providers."""
        from src.cli.validators import VALID_PROVIDERS

        expected_providers = {
            "cerebras", "groq", "gemini", "cohere", "github_models"
        }

        for provider in expected_providers:
            assert provider in VALID_PROVIDERS, f"{provider} missing from VALID_PROVIDERS"


class TestFunctionalityPreserved:
    """Tests that all validation functionality is preserved after refactoring."""

    # Command validation
    def test_command_none_input(self):
        """validate_command should handle None input."""
        from src.cli.validators import validate_command

        result = validate_command(None)
        assert not result.is_valid
        assert "none" in result.error.lower()

    def test_command_empty_input(self):
        """validate_command should reject empty input."""
        from src.cli.validators import validate_command

        result = validate_command("")
        assert not result.is_valid
        assert "empty" in result.error.lower()

    def test_command_missing_slash(self):
        """validate_command should require slash prefix."""
        from src.cli.validators import validate_command

        result = validate_command("help")
        assert not result.is_valid
        assert "slash" in result.error.lower()

    def test_command_unknown(self):
        """validate_command should reject unknown commands."""
        from src.cli.validators import validate_command

        result = validate_command("/notacommand")
        assert not result.is_valid
        assert "unknown" in result.error.lower()

    def test_command_too_long(self):
        """validate_command should reject overly long commands."""
        from src.cli.validators import validate_command

        long_args = "x" * 10000
        result = validate_command(f"/plan {long_args}")
        assert not result.is_valid
        assert "length" in result.error.lower()

    # Path validation
    def test_path_none_input(self):
        """validate_path should handle None input."""
        from src.cli.validators import validate_path

        result = validate_path(None)
        assert not result.is_valid
        assert "none" in result.error.lower()

    def test_path_empty_input(self):
        """validate_path should reject empty input."""
        from src.cli.validators import validate_path

        result = validate_path("")
        assert not result.is_valid
        assert "empty" in result.error.lower()

    def test_path_glob_chars(self):
        """validate_path should reject glob characters."""
        from src.cli.validators import validate_path

        result = validate_path("src/*.py")
        assert not result.is_valid
        assert "glob" in result.error.lower()

    def test_path_too_long(self):
        """validate_path should reject overly long paths."""
        from src.cli.validators import validate_path

        long_path = "a" * 600
        result = validate_path(long_path)
        assert not result.is_valid
        assert "length" in result.error.lower()

    def test_path_traversal(self):
        """validate_path should reject excessive path traversal."""
        from src.cli.validators import validate_path

        result = validate_path("../../../../etc/passwd")
        assert not result.is_valid
        assert "traversal" in result.error.lower()

    # Provider validation
    def test_provider_none_input(self):
        """validate_provider should handle None input."""
        from src.cli.validators import validate_provider

        result = validate_provider(None)
        assert not result.is_valid
        assert "none" in result.error.lower()

    def test_provider_empty_input(self):
        """validate_provider should reject empty input."""
        from src.cli.validators import validate_provider

        result = validate_provider("")
        assert not result.is_valid
        assert "empty" in result.error.lower()

    def test_provider_unknown(self):
        """validate_provider should reject unknown providers."""
        from src.cli.validators import validate_provider

        result = validate_provider("notaprovider")
        assert not result.is_valid
        assert "unknown" in result.error.lower()

    def test_provider_case_normalization(self):
        """validate_provider should normalize case."""
        from src.cli.validators import validate_provider

        result = validate_provider("CEREBRAS")
        assert result.is_valid
        assert result.provider == "cerebras"

    def test_provider_with_spaces(self):
        """validate_provider should reject spaces."""
        from src.cli.validators import validate_provider

        result = validate_provider("github models")
        assert not result.is_valid
        assert "space" in result.error.lower()
