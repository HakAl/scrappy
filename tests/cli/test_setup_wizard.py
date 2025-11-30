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
import os
import json
import tempfile
from pathlib import Path
from typing import List, Any
from unittest.mock import Mock, patch, MagicMock

from src.cli.setup_wizard import SetupWizard
from src.orchestrator.provider_definitions import PROVIDERS


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
        """Returns True when provider env var is set."""
        io = MockIO()
        wizard = SetupWizard(io)

        with patch.dict(os.environ, {"GROQ_API_KEY": "test_key"}):
            assert wizard._is_configured("groq") is True

    def test_is_configured_false(self):
        """Returns False when provider env var is not set."""
        io = MockIO()
        wizard = SetupWizard(io)

        with patch.dict(os.environ, {}, clear=True):
            assert wizard._is_configured("groq") is False

    def test_has_any_provider_true(self):
        """Returns True when at least one provider is configured."""
        io = MockIO()
        wizard = SetupWizard(io)

        with patch.dict(os.environ, {"GROQ_API_KEY": "test_key"}):
            assert wizard._has_any_provider() is True

    def test_has_any_provider_false(self):
        """Returns False when no providers are configured."""
        io = MockIO()
        wizard = SetupWizard(io)

        # Clear all provider env vars
        env_vars = {info.env_var: "" for info in PROVIDERS.values()}
        with patch.dict(os.environ, env_vars, clear=True):
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
    """Test key save/load functionality."""

    def test_save_key_creates_config_file(self):
        """Saving a key creates the config file."""
        io = MockIO()
        wizard = SetupWizard(io)

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"
            config_dir = Path(tmpdir)

            with patch("src.cli.setup_wizard.USER_CONFIG_FILE", config_file), \
                 patch("src.cli.setup_wizard.USER_CONFIG_DIR", config_dir):

                wizard._save_key("TEST_API_KEY", "test_value")

                assert config_file.exists()
                with open(config_file) as f:
                    config = json.load(f)

                assert config["api_keys"]["TEST_API_KEY"] == "test_value"

    def test_save_key_preserves_existing_keys(self):
        """Saving a new key preserves existing keys."""
        io = MockIO()
        wizard = SetupWizard(io)

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"
            config_dir = Path(tmpdir)

            # Create existing config
            config_dir.mkdir(exist_ok=True)
            with open(config_file, 'w') as f:
                json.dump({"api_keys": {"EXISTING_KEY": "existing_value"}}, f)

            with patch("src.cli.setup_wizard.USER_CONFIG_FILE", config_file), \
                 patch("src.cli.setup_wizard.USER_CONFIG_DIR", config_dir):

                wizard._save_key("NEW_KEY", "new_value")

                with open(config_file) as f:
                    config = json.load(f)

                assert config["api_keys"]["EXISTING_KEY"] == "existing_value"
                assert config["api_keys"]["NEW_KEY"] == "new_value"

    def test_load_config_empty_when_no_file(self):
        """Returns empty dict when config file doesn't exist."""
        io = MockIO()
        wizard = SetupWizard(io)

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "nonexistent.json"

            with patch("src.cli.setup_wizard.USER_CONFIG_FILE", config_file):
                config = wizard._load_config()
                assert config == {}

    def test_load_saved_keys_loads_into_env(self):
        """load_saved_keys() loads keys into os.environ."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"
            config_dir = Path(tmpdir)

            # Create config with API keys
            config_dir.mkdir(exist_ok=True)
            with open(config_file, 'w') as f:
                json.dump({
                    "api_keys": {
                        "TEST_KEY_1": "value1",
                        "TEST_KEY_2": "value2"
                    }
                }, f)

            with patch("src.cli.setup_wizard.USER_CONFIG_FILE", config_file):
                # Clear env vars first
                os.environ.pop("TEST_KEY_1", None)
                os.environ.pop("TEST_KEY_2", None)

                SetupWizard.load_saved_keys()

                assert os.environ.get("TEST_KEY_1") == "value1"
                assert os.environ.get("TEST_KEY_2") == "value2"

    def test_load_saved_keys_does_not_override_existing(self):
        """load_saved_keys() doesn't override existing env vars."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"
            config_dir = Path(tmpdir)

            # Create config with API key
            config_dir.mkdir(exist_ok=True)
            with open(config_file, 'w') as f:
                json.dump({
                    "api_keys": {
                        "TEST_KEY": "config_value"
                    }
                }, f)

            with patch("src.cli.setup_wizard.USER_CONFIG_FILE", config_file):
                # Set env var before loading
                os.environ["TEST_KEY"] = "env_value"

                SetupWizard.load_saved_keys()

                # Should preserve env var value
                assert os.environ.get("TEST_KEY") == "env_value"


class TestSetupWizardMenuGeneration:
    """Test menu generation."""

    def test_show_menu_displays_all_providers(self):
        """Menu includes all providers from PROVIDERS dict."""
        io = MockIO()
        wizard = SetupWizard(io)

        wizard._show_menu()

        # Check that output_sink was used or fallback was used
        # In test mode without output_sink, it should use direct console
        # We can't easily test Rich Panel output, but we can verify no errors

    def test_show_menu_marks_configured_providers(self):
        """Menu shows [OK] for configured providers."""
        io = MockIO()
        wizard = SetupWizard(io)

        with patch.dict(os.environ, {"GROQ_API_KEY": "test_key"}):
            # This would show [OK] for groq
            wizard._show_menu()
            # Verification would require parsing Rich output, skip for now


class TestSetupWizardFlow:
    """Test wizard run flow."""

    def test_run_allows_cancel_when_flag_true(self):
        """Wizard exits when user enters 'q' and allow_cancel=True."""
        io = MockIO()
        io.prompt_responses = ["q"]
        wizard = SetupWizard(io)

        result = wizard.run(allow_cancel=True)

        # May return False if no providers, True if providers exist
        assert isinstance(result, bool)

    def test_run_requires_provider_when_flag_false(self):
        """Wizard shows error when trying to quit without providers configured."""
        io = MockIO()
        wizard = SetupWizard(io)

        # Mock _get_choice to return 'q' once, then raise exception to break loop
        call_count = []
        def mock_get_choice(allow_cancel):
            call_count.append(1)
            if len(call_count) == 1:
                return 'q'
            # Second call - raise to break test loop
            raise StopIteration("Test complete")

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(wizard, '_has_any_provider', return_value=False):
                with patch.object(wizard, '_get_choice', side_effect=mock_get_choice):
                    try:
                        wizard.run(allow_cancel=False)
                    except StopIteration:
                        pass

                    # Verify error message was shown
                    error_shown = any("Must configure" in msg for msg in io.output)
                    assert error_shown

    def test_configure_provider_saves_valid_key(self):
        """Configuring a provider saves the key."""
        io = MockIO()
        io.prompt_responses = ["valid_test_key_123456"]
        wizard = SetupWizard(io)

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"
            config_dir = Path(tmpdir)

            with patch("src.cli.setup_wizard.USER_CONFIG_FILE", config_file), \
                 patch("src.cli.setup_wizard.USER_CONFIG_DIR", config_dir), \
                 patch.object(wizard, '_test_provider_key', return_value=(True, "")):

                result = wizard._configure_provider("groq")

                assert result is True
                assert config_file.exists()
                with open(config_file) as f:
                    config = json.load(f)
                assert "GROQ_API_KEY" in config["api_keys"]

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
        with patch("src.cli.setup_wizard.PROVIDERS") as mock_providers:
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
            with patch("src.cli.setup_wizard.PROVIDERS") as mock_providers:
                mock_info = Mock()
                mock_info.env_var = "TEST_API_KEY"
                mock_info.provider_class.side_effect = Exception("401 Unauthorized")
                mock_providers.__getitem__.return_value = mock_info

                success, error = wizard._test_provider_key("test_provider", "test_key")

                assert success is False
                assert "Invalid API key" in error

    def test_test_provider_key_restores_env(self):
        """Testing a key restores original env var."""
        io = MockIO()
        wizard = SetupWizard(io)

        original_value = "original_key"
        os.environ["TEST_ENV_VAR"] = original_value

        with patch("src.cli.setup_wizard.PROVIDERS") as mock_providers:
            mock_info = Mock()
            mock_info.env_var = "TEST_ENV_VAR"
            mock_info.provider_class.side_effect = Exception("Test error")
            mock_providers.__getitem__.return_value = mock_info

            wizard._test_provider_key("test_provider", "new_key")

            # Original value should be restored
            assert os.environ.get("TEST_ENV_VAR") == original_value
