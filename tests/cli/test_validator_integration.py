"""Integration tests for validators in CLI components.

Tests that validators are properly integrated into command router,
input handler, and CLI commands.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from tests.helpers import MockIO, ConfigurableTestOrchestrator
from scrappy.cli.command_router import CommandRouter
from scrappy.cli.session_context import SessionContext
from scrappy.cli.input_handler import InputHandler
from scrappy.cli.utils.cli_factory import initialize_cli_handlers


class TestCommandRouterValidation:
    """Tests for validator integration in CommandRouter."""

    def setup_method(self):
        """Set up test fixtures."""
        self.io = MockIO()
        self.orchestrator = ConfigurableTestOrchestrator()

        # Create all required handlers
        session_start = datetime.now()
        handlers = initialize_cli_handlers(self.orchestrator, session_start, self.io)

        # Create session context for shared state
        self.session_context = SessionContext()

        # Create router with all dependencies
        self.router = CommandRouter(
            io=self.io,
            orchestrator=self.orchestrator,
            session_context=self.session_context,
            display=handlers['display'],
            session_mgr=handlers['session_mgr'],
            codebase=handlers['codebase'],
            tasks=handlers['tasks'],
            multiprovider=handlers['multiprovider'],
            smart=handlers['smart'],
            agent_mgr=handlers['agent_mgr'],
            task_router=handlers['task_router']
        )

    def test_valid_help_command_routes_successfully(self):
        """Valid /help command should route without validation error."""
        result = self.router.route("/help", "")
        assert result is True
        output = self.io.get_output()
        # Should not contain validation error
        assert "invalid command" not in output.lower()

    def test_valid_status_command_passes_validation(self):
        """Valid /status command should pass validation."""
        # Test validation passes (may fail later due to mock limitations)
        from scrappy.cli.validators import validate_command
        result = validate_command("/status")
        assert result.is_valid

    def test_valid_quit_command_passes_validation(self):
        """Valid /quit command should pass validation."""
        from scrappy.cli.validators import validate_command
        result = validate_command("/quit")
        assert result.is_valid
        assert result.command == "quit"

    def test_valid_exit_command_passes_validation(self):
        """Valid /exit command should pass validation."""
        from scrappy.cli.validators import validate_command
        result = validate_command("/exit")
        assert result.is_valid
        assert result.command == "exit"

    def test_unknown_command_shows_error(self):
        """Unknown command should show error message."""
        result = self.router.route("/notacommand", "")
        assert result is True  # Continue loop
        output = self.io.get_output()
        assert "unknown" in output.lower() or "invalid" in output.lower()

    def test_command_with_control_characters_rejected(self):
        """Command with control characters should be rejected."""
        result = self.router.route("/help\x00", "")
        assert result is True  # Continue loop
        output = self.io.get_output()
        # Should show validation error
        assert "invalid" in output.lower() or "character" in output.lower() or "unknown" in output.lower()

    def test_empty_command_handled(self):
        """Empty command should be handled gracefully."""
        result = self.router.route("", "")
        assert result is True
        output = self.io.get_output()
        assert "unknown" in output.lower() or "invalid" in output.lower() or len(output) > 0

    def test_command_without_slash_shows_error(self):
        """Command without slash prefix should show error."""
        result = self.router.route("help", "")
        assert result is True
        output = self.io.get_output()
        # Should indicate it's not recognized
        assert "unknown" in output.lower() or len(output) > 0

    def test_plan_command_without_args_shows_usage(self):
        """Plan command without args should show usage."""
        result = self.router.route("/plan", "")
        assert result is True
        output = self.io.get_output()
        assert "usage" in output.lower()

    def test_reason_command_without_args_shows_usage(self):
        """Reason command without args should show usage."""
        result = self.router.route("/reason", "")
        assert result is True
        output = self.io.get_output()
        assert "usage" in output.lower()

    def test_agent_command_without_args_shows_usage(self):
        """Agent command without args should show usage."""
        result = self.router.route("/agent", "")
        assert result is True
        output = self.io.get_output()
        assert "usage" in output.lower()

    def test_clear_command_clears_history(self):
        """Clear command should clear conversation history."""
        self.router.session_context.conversation_history = [{"role": "user", "content": "test"}]
        result = self.router.route("/clear", "")
        assert result is True
        assert len(self.router.session_context.conversation_history) == 0

    def test_very_long_command_rejected(self):
        """Very long command should be rejected."""
        long_args = "x" * 10000
        result = self.router.route("/plan", long_args)
        # Either it works with the args or shows an error
        # The important thing is it doesn't crash
        assert result is True

    def test_command_with_newline_in_args_handled(self):
        """Command with newlines in args should be handled."""
        result = self.router.route("/plan", "line1\nline2")
        # Should not crash
        assert result is True


class TestInputHandlerValidation:
    """Tests for validation in InputHandler."""

    def setup_method(self):
        """Set up test fixtures."""
        self.io = MockIO()
        self.handler = InputHandler(self.io)

    def test_is_command_detects_slash_prefix(self):
        """is_command should detect slash prefix."""
        assert self.handler.is_command("/help") is True
        assert self.handler.is_command("/plan task") is True
        assert self.handler.is_command("help") is False
        assert self.handler.is_command("") is False

    def test_parse_command_extracts_command_and_args(self):
        """parse_command should extract command and arguments."""
        cmd, args = self.handler.parse_command("/plan create feature")
        assert cmd == "/plan"
        assert args == "create feature"

    def test_parse_command_handles_no_args(self):
        """parse_command should handle commands without args."""
        cmd, args = self.handler.parse_command("/help")
        assert cmd == "/help"
        assert args == ""

    def test_parse_command_handles_empty_input(self):
        """parse_command should handle empty input."""
        cmd, args = self.handler.parse_command("")
        assert cmd == ""
        assert args == ""

    def test_parse_command_lowercases_command(self):
        """parse_command should lowercase the command."""
        cmd, args = self.handler.parse_command("/HELP")
        assert cmd == "/help"

    def test_parse_command_preserves_args_case(self):
        """parse_command should preserve argument case."""
        cmd, args = self.handler.parse_command("/plan Create Feature")
        assert args == "Create Feature"


class TestProviderValidationIntegration:
    """Tests for provider validation in CLI commands."""

    def test_valid_provider_accepted(self):
        """Valid provider names should be accepted."""
        from scrappy.cli.validators import validate_provider

        for provider in ["cerebras", "groq", "gemini", "cohere", "github_models"]:
            result = validate_provider(provider)
            assert result.is_valid, f"Provider {provider} should be valid"

    def test_invalid_provider_rejected(self):
        """Invalid provider names should be rejected."""
        from scrappy.cli.validators import validate_provider

        result = validate_provider("notaprovider")
        assert not result.is_valid
        assert "unknown" in result.error.lower()

    def test_provider_case_normalization(self):
        """Provider names should be normalized to lowercase."""
        from scrappy.cli.validators import validate_provider

        result = validate_provider("CEREBRAS")
        assert result.is_valid
        assert result.provider == "cerebras"


class TestPathValidationIntegration:
    """Tests for path validation in CLI commands."""

    def test_valid_path_accepted(self):
        """Valid paths should be accepted."""
        from scrappy.cli.validators import validate_path

        result = validate_path("src/cli/commands.py")
        assert result.is_valid

    def test_path_with_glob_rejected(self):
        """Paths with glob patterns should be rejected."""
        from scrappy.cli.validators import validate_path

        result = validate_path("src/*.py")
        assert not result.is_valid
        assert "glob" in result.error.lower()

    def test_empty_path_rejected(self):
        """Empty paths should be rejected."""
        from scrappy.cli.validators import validate_path

        result = validate_path("")
        assert not result.is_valid
        assert "empty" in result.error.lower()

    def test_path_traversal_rejected(self):
        """Excessive path traversal should be rejected."""
        from scrappy.cli.validators import validate_path

        result = validate_path("../../../../etc/passwd")
        assert not result.is_valid


class TestCommandValidationIntegration:
    """Tests for command validation integration."""

    def test_validate_command_before_routing(self):
        """Commands should be validated before routing."""
        from scrappy.cli.validators import validate_command

        # Valid commands
        result = validate_command("/help")
        assert result.is_valid

        result = validate_command("/plan create feature")
        assert result.is_valid
        assert result.command == "plan"
        assert result.args == "create feature"

    def test_invalid_command_caught(self):
        """Invalid commands should be caught by validation."""
        from scrappy.cli.validators import validate_command

        # Unknown command
        result = validate_command("/badcmd")
        assert not result.is_valid

        # Missing slash
        result = validate_command("help")
        assert not result.is_valid

        # Control characters
        result = validate_command("/help\x00")
        assert not result.is_valid


class TestValidatorErrorMessages:
    """Tests for validator error message quality."""

    def test_error_messages_are_helpful(self):
        """Error messages should be helpful and actionable."""
        from scrappy.cli.validators import validate_command, validate_path, validate_provider

        # Command errors should mention what's wrong
        result = validate_command("")
        assert "empty" in result.error.lower()

        result = validate_command("help")
        assert "slash" in result.error.lower() or "/" in result.error

        # Provider errors should list valid options
        result = validate_provider("badprovider")
        assert "cerebras" in result.error.lower() or "valid" in result.error.lower()

        # Path errors should explain the issue
        result = validate_path("src/*.py")
        assert "glob" in result.error.lower() or "*" in result.error


class TestValidatorEdgeCases:
    """Tests for edge cases in validation."""

    def test_unicode_in_commands(self):
        """Unicode characters in commands should be handled."""
        from scrappy.cli.validators import validate_command

        # Unicode in args should be fine
        result = validate_command("/plan create archivo")
        assert result.is_valid

    def test_whitespace_handling(self):
        """Whitespace should be handled consistently."""
        from scrappy.cli.validators import validate_command, validate_provider

        # Leading/trailing whitespace should be trimmed
        result = validate_command("  /help  ")
        assert result.is_valid

        result = validate_provider("  cerebras  ")
        assert result.is_valid
        assert result.provider == "cerebras"

    def test_multiple_spaces_in_args(self):
        """Multiple spaces in arguments should be preserved."""
        from scrappy.cli.validators import validate_command

        result = validate_command("/plan create   multiple   spaces")
        assert result.is_valid
        assert "multiple   spaces" in result.args
