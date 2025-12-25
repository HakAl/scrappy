"""
Tests for config CLI commands.

Tests the `scrappy config` command group:
- config list: List configured providers
- config set: Add/update provider API key
- config remove: Remove provider API key
"""

from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from scrappy.cli.commands import cli

# Patch target - where the function is imported in the command handlers
PATCH_TARGET = 'scrappy.infrastructure.config.api_keys.create_api_key_service'


class TestConfigList:
    """Tests for `scrappy config list` command."""

    def test_list_shows_configured_providers(self):
        """Should display configured providers with masked keys."""
        runner = CliRunner()

        # Mock the config service
        mock_service = MagicMock()
        mock_service.get_key.side_effect = lambda k: {
            'CEREBRAS_API_KEY': 'csk_test_key_1234567890',
            'GROQ_API_KEY': None,
            'GEMINI_API_KEY': None,
            'SAMBANOVA_API_KEY': None,
        }.get(k)

        with patch(PATCH_TARGET, return_value=mock_service):
            result = runner.invoke(cli, ['config', 'list'])

        assert result.exit_code == 0
        assert 'Configured providers' in result.output
        assert 'cerebras' in result.output
        # Key should be masked (first 4 chars...last 4 chars)
        assert 'csk_...7890' in result.output

    def test_list_shows_unconfigured_providers(self):
        """Should display unconfigured providers with setup info."""
        runner = CliRunner()

        mock_service = MagicMock()
        mock_service.get_key.return_value = None  # No keys configured

        with patch(PATCH_TARGET, return_value=mock_service):
            result = runner.invoke(cli, ['config', 'list'])

        assert result.exit_code == 0
        assert 'Unconfigured providers' in result.output
        assert 'CEREBRAS_API_KEY' in result.output
        assert 'GROQ_API_KEY' in result.output

    def test_list_shows_no_providers_message_when_empty(self):
        """Should show message when no providers configured."""
        runner = CliRunner()

        mock_service = MagicMock()
        mock_service.get_key.return_value = None

        with patch(PATCH_TARGET, return_value=mock_service):
            result = runner.invoke(cli, ['config', 'list'])

        assert result.exit_code == 0
        assert 'No providers configured' in result.output


class TestConfigSet:
    """Tests for `scrappy config set` command."""

    def test_set_rejects_unknown_provider(self):
        """Should reject unknown provider names."""
        runner = CliRunner()

        result = runner.invoke(cli, ['config', 'set', 'unknown_provider'])

        assert result.exit_code == 1
        assert 'Unknown provider' in result.output
        assert 'Available providers' in result.output

    def test_set_prompts_for_key(self):
        """Should prompt for API key with hidden input."""
        runner = CliRunner()

        mock_service = MagicMock()

        with patch(PATCH_TARGET, return_value=mock_service):
            # Simulate user entering a key (with confirmation)
            result = runner.invoke(
                cli,
                ['config', 'set', 'groq'],
                input='gsk_test_key_1234567890\ngsk_test_key_1234567890\n'
            )

        assert result.exit_code == 0
        assert 'saved successfully' in result.output
        mock_service.set_key.assert_called_once_with('GROQ_API_KEY', 'gsk_test_key_1234567890')

    def test_set_validates_key(self):
        """Should validate key before saving."""
        runner = CliRunner()

        mock_service = MagicMock()
        from scrappy.infrastructure.config.api_keys import ApiKeyValidationError
        mock_service.set_key.side_effect = ApiKeyValidationError("Key too short")

        with patch(PATCH_TARGET, return_value=mock_service):
            result = runner.invoke(
                cli,
                ['config', 'set', 'groq'],
                input='short\nshort\n'
            )

        assert result.exit_code == 1
        assert 'Invalid API key' in result.output


class TestConfigRemove:
    """Tests for `scrappy config remove` command."""

    def test_remove_rejects_unknown_provider(self):
        """Should reject unknown provider names."""
        runner = CliRunner()

        result = runner.invoke(cli, ['config', 'remove', 'unknown_provider'])

        assert result.exit_code == 1
        assert 'Unknown provider' in result.output

    def test_remove_reports_when_no_key_exists(self):
        """Should report when no key is configured for provider."""
        runner = CliRunner()

        mock_service = MagicMock()
        mock_service.get_key.return_value = None

        with patch(PATCH_TARGET, return_value=mock_service):
            result = runner.invoke(cli, ['config', 'remove', 'groq'])

        assert result.exit_code == 0
        assert 'No API key configured' in result.output

    def test_remove_prompts_for_confirmation(self):
        """Should prompt for confirmation before removing."""
        runner = CliRunner()

        mock_service = MagicMock()
        mock_service.get_key.return_value = 'existing_key_123'
        mock_config = MagicMock()
        mock_config.api_keys = {'GROQ_API_KEY': 'existing_key_123'}
        mock_service.load.return_value = mock_config

        with patch(PATCH_TARGET, return_value=mock_service):
            # User declines
            result = runner.invoke(cli, ['config', 'remove', 'groq'], input='n\n')

        assert result.exit_code == 0
        assert 'Cancelled' in result.output
        mock_service.save.assert_not_called()

    def test_remove_with_force_skips_confirmation(self):
        """Should skip confirmation with --force flag."""
        runner = CliRunner()

        mock_service = MagicMock()
        mock_service.get_key.return_value = 'existing_key_123'
        mock_config = MagicMock()
        mock_config.api_keys = {'GROQ_API_KEY': 'existing_key_123'}
        mock_service.load.return_value = mock_config

        with patch(PATCH_TARGET, return_value=mock_service):
            result = runner.invoke(cli, ['config', 'remove', 'groq', '--force'])

        assert result.exit_code == 0
        assert 'removed' in result.output
        mock_service.save.assert_called_once()

    def test_remove_deletes_key_from_config(self):
        """Should remove key from config and save."""
        runner = CliRunner()

        mock_service = MagicMock()
        mock_service.get_key.return_value = 'existing_key_123'
        mock_config = MagicMock()
        mock_config.api_keys = {'GROQ_API_KEY': 'existing_key_123'}
        mock_service.load.return_value = mock_config

        with patch(PATCH_TARGET, return_value=mock_service):
            result = runner.invoke(cli, ['config', 'remove', 'groq', '-f'])

        assert result.exit_code == 0
        # Key should be deleted
        assert 'GROQ_API_KEY' not in mock_config.api_keys
        mock_service.save.assert_called_once_with(mock_config)
