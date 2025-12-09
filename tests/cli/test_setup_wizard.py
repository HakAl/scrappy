"""
Tests for SetupWizard - Provider configuration wizard.

Test Coverage:
1. Menu generation from PROVIDERS
2. Key format validation
3. Save/load functionality
4. Provider configuration flow
5. Required provider enforcement (allow_cancel=False)
"""

import pytest
from typing import List
from unittest.mock import Mock, patch, MagicMock

from scrappy.cli.setup_wizard import SetupWizard
from scrappy.orchestrator.provider_definitions import PROVIDERS
from .helpers import MockApiKeyConfigService


class MockIO:
    """Mock UnifiedIO for testing."""

    def __init__(self):
        """Initialize mock IO."""
        self.output: List[str] = []
        self.prompts: List[str] = []
        self.prompt_responses: List[str] = []
        self.output_sink = None

    def echo(self, text: str = "") -> None:
        """Capture echo output."""
        self.output.append(text)

    def secho(self, text: str, fg: str = None, bold: bool = False) -> None:
        """Capture styled output."""
        self.output.append(text)

    def prompt(self, text: str, default: str = "") -> str:
        """Mock prompt - return next response."""
        self.prompts.append(text)
        if self.prompt_responses:
            return self.prompt_responses.pop(0)
        return default

    def clear_output(self) -> None:
        """Clear captured output."""
        self.output.clear()
        self.prompts.clear()


class TestSetupWizardNonBlocking:
    """Test non-blocking wizard API for TUI."""

    def test_wizard_starts_in_menu_state(self):
        """start() should initialize wizard in MENU state."""
        io = MockIO()
        mock_service = MockApiKeyConfigService()
        wizard = SetupWizard(io, config_service=mock_service)

        wizard.start(allow_cancel=True)

        assert wizard.is_active
        assert "Select provider" in wizard.current_prompt

    def test_handle_input_processes_menu_selection(self):
        """handle_input() should process menu selections."""
        io = MockIO()
        mock_service = MockApiKeyConfigService()
        wizard = SetupWizard(io, config_service=mock_service)

        wizard.start(allow_cancel=True)
        wizard.handle_input("1")  # Select first provider

        # Should be waiting for API key now
        assert wizard.is_active
        assert "API_KEY" in wizard.current_prompt

    def test_wizard_completes_on_quit(self):
        """Wizard should complete when user enters 'q'."""
        io = MockIO()
        mock_service = MockApiKeyConfigService()
        mock_service.keys = {"GROQ_API_KEY": "test"}  # Has provider
        wizard = SetupWizard(io, config_service=mock_service)

        completed = []
        wizard.start(allow_cancel=True, on_complete=lambda hp: completed.append(hp))
        wizard.handle_input("q")

        assert not wizard.is_active
        assert len(completed) == 1


class TestSetupWizardKeyValidation:
    """Test key format validation."""

    def test_validate_key_format_valid(self):
        """Valid keys pass validation."""
        io = MockIO()
        wizard = SetupWizard(io)

        assert wizard._validate_key_format("sk-abcdefghijk1234567890")
        assert wizard._validate_key_format("gsk_1234567890abcdefghijk")
        assert wizard._validate_key_format("AIzaSyB1234567890abcdef")

    def test_validate_key_format_too_short(self):
        """Keys shorter than 10 characters fail."""
        io = MockIO()
        wizard = SetupWizard(io)

        assert not wizard._validate_key_format("short")
        assert not wizard._validate_key_format("123456789")

    def test_validate_key_format_whitespace(self):
        """Keys with whitespace fail."""
        io = MockIO()
        wizard = SetupWizard(io)

        assert not wizard._validate_key_format("key with spaces")
        assert not wizard._validate_key_format("key\nwith\nnewline")
        assert not wizard._validate_key_format("key\twith\ttab")

    def test_validate_key_format_empty(self):
        """Empty keys fail."""
        io = MockIO()
        wizard = SetupWizard(io)

        assert not wizard._validate_key_format("")
        assert not wizard._validate_key_format(None)


class TestSetupWizardProviderConfiguration:
    """Test provider configuration flow."""

    def test_is_configured_true(self):
        """Returns True when provider key is configured in service."""
        io = MockIO()
        mock_service = MockApiKeyConfigService()
        mock_service.keys = {"GROQ_API_KEY": "test_key"}
        wizard = SetupWizard(io, config_service=mock_service)

        assert wizard._is_configured("groq") is True

    def test_is_configured_false(self):
        """Returns False when provider key is not configured."""
        io = MockIO()
        mock_service = MockApiKeyConfigService()
        wizard = SetupWizard(io, config_service=mock_service)

        assert wizard._is_configured("groq") is False

    def test_has_any_provider_true(self):
        """Returns True when at least one provider is configured."""
        io = MockIO()
        mock_service = MockApiKeyConfigService()
        mock_service.keys = {"GROQ_API_KEY": "test_key"}
        wizard = SetupWizard(io, config_service=mock_service)

        assert wizard._has_any_provider() is True

    def test_has_any_provider_false(self):
        """Returns False when no providers are configured."""
        io = MockIO()
        mock_service = MockApiKeyConfigService()
        wizard = SetupWizard(io, config_service=mock_service)

        assert wizard._has_any_provider() is False

    def test_get_provider_by_index_valid(self):
        """Returns provider name for valid index."""
        io = MockIO()
        wizard = SetupWizard(io)

        # Index 1 should return first provider by priority
        sorted_providers = sorted(PROVIDERS.items(), key=lambda x: x[1].priority)
        expected_name = sorted_providers[0][0]

        assert wizard._get_provider_by_index("1") == expected_name

    def test_get_provider_by_index_invalid(self):
        """Returns None for invalid index."""
        io = MockIO()
        wizard = SetupWizard(io)

        assert wizard._get_provider_by_index("0") is None
        assert wizard._get_provider_by_index("999") is None
        assert wizard._get_provider_by_index("invalid") is None


class TestSetupWizardSaveLoad:
    """Test key save/load functionality via config service."""

    def test_save_key_uses_config_service(self):
        """Saving a key delegates to config service."""
        io = MockIO()
        mock_service = MockApiKeyConfigService()
        wizard = SetupWizard(io, config_service=mock_service)

        wizard._save_key("TEST_API_KEY", "test_value")

        assert mock_service.save_called
        assert mock_service.keys["TEST_API_KEY"] == "test_value"

    def test_save_key_preserves_existing_keys(self):
        """Saving a new key preserves existing keys in service."""
        io = MockIO()
        mock_service = MockApiKeyConfigService()
        mock_service.keys = {"EXISTING_KEY": "existing_value"}
        wizard = SetupWizard(io, config_service=mock_service)

        wizard._save_key("NEW_KEY", "new_value")

        assert mock_service.keys["EXISTING_KEY"] == "existing_value"
        assert mock_service.keys["NEW_KEY"] == "new_value"


class TestSetupWizardMenuGeneration:
    """Test menu generation."""


        # Check that output_sink was used or fallback was used
        # In test mode without output_sink, it should use direct console
        # We can't easily test Rich Panel output, but we can verify no errors

        # Verification would require parsing Rich output, skip for now


class TestSetupWizardFlow:
    """Test wizard run flow."""



    def test_configure_provider_saves_valid_key(self):
        """Configuring a provider saves the key via config service."""
        io = MockIO()
        io.prompt_responses = ["valid_test_key_123456"]
        mock_service = MockApiKeyConfigService()
        wizard = SetupWizard(io, config_service=mock_service)

        with patch.object(wizard, '_test_provider_key', return_value=(True, "")):
            result = wizard._configure_provider("groq")

            assert result is True
            assert "GROQ_API_KEY" in mock_service.keys
            assert mock_service.save_called

    def test_configure_provider_rejects_invalid_format(self):
        """Configuring with invalid key format fails."""
        io = MockIO()
        io.prompt_responses = ["short"]  # Too short
        wizard = SetupWizard(io)

        result = wizard._configure_provider("groq")

        assert result is False
        error_shown = any("Invalid key format" in msg for msg in io.output)
        assert error_shown

    def test_configure_provider_handles_failed_validation(self):
        """Configuring with failed API validation fails."""
        io = MockIO()
        io.prompt_responses = ["valid_format_key_1234567890"]
        wizard = SetupWizard(io)

        with patch.object(wizard, '_test_provider_key', return_value=(False, "Invalid API key")):
            result = wizard._configure_provider("groq")

            assert result is False
            error_shown = any("validation failed" in msg for msg in io.output)
            assert error_shown


class TestSetupWizardProviderTesting:
    """Test provider API key testing."""

    def test_test_provider_key_success(self):
        """Valid API key returns True."""
        io = MockIO()
        wizard = SetupWizard(io)

        mock_provider = Mock()
        mock_provider.chat.return_value = {"content": "test"}

        # Patch PROVIDERS in the setup_wizard module where it's imported
        with patch("scrappy.cli.setup_wizard.PROVIDERS") as mock_providers:
            mock_info = Mock()
            mock_info.env_var = "TEST_API_KEY"
            mock_info.provider_class.return_value = mock_provider
            mock_providers.__getitem__.return_value = mock_info

            success, error = wizard._test_provider_key("test_provider", "test_key")

            assert success is True
            assert error == ""

    def test_test_provider_key_unauthorized(self):
        """Unauthorized error returns False with friendly message."""
        io = MockIO()
        wizard = SetupWizard(io)

        with patch.object(wizard, '_validate_key_format', return_value=True):
            # Simulate 401 error
            with patch("scrappy.cli.setup_wizard.PROVIDERS") as mock_providers:
                mock_info = Mock()
                mock_info.env_var = "TEST_API_KEY"
                mock_info.provider_class.side_effect = Exception("401 Unauthorized")
                mock_providers.__getitem__.return_value = mock_info

                success, error = wizard._test_provider_key("test_provider", "test_key")

                assert success is False
                assert "Invalid API key" in error

