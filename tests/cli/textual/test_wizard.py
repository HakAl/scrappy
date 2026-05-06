"""
Tests for setup wizard using Textual native testing.

Covers:
- Wizard screen creation and display
- Basic navigation in wizard
- Input handling

Migrated from: tests/e2e/tests/wizard.spec.ts

Note: These tests focus on the wizard screen component itself,
not the full app flow (which requires complex API key mocking).
"""

import pytest
from unittest.mock import MagicMock

from scrappy.cli.screens.wizard_screen import SetupWizardScreen
from scrappy.cli.setup_wizard import SetupWizard


class TestSetupWizardScreen:
    """Tests for SetupWizardScreen component."""

    def test_wizard_screen_can_be_created(self):
        """SetupWizardScreen can be instantiated."""
        # Create mock dependencies matching actual constructor signature
        mock_io = MagicMock()
        mock_io.theme = MagicMock()
        mock_validator = MagicMock()
        mock_clipboard = MagicMock()

        screen = SetupWizardScreen(io=mock_io, key_validator=mock_validator, clipboard=mock_clipboard)
        assert screen is not None

    def test_wizard_screen_stores_dependencies(self):
        """Screen should store its dependencies."""
        mock_io = MagicMock()
        mock_io.theme = MagicMock()
        mock_validator = MagicMock()
        mock_clipboard = MagicMock()

        screen = SetupWizardScreen(io=mock_io, key_validator=mock_validator, clipboard=mock_clipboard)
        assert screen._io is mock_io
        assert screen._key_validator is mock_validator
        assert screen._clipboard is mock_clipboard

    def test_right_click_pastes_clipboard_text(self):
        """Right-click should paste clipboard text into the wizard input."""
        mock_io = MagicMock()
        mock_io.theme = MagicMock()
        mock_validator = MagicMock()
        mock_clipboard = MagicMock()
        screen = SetupWizardScreen(io=mock_io, key_validator=mock_validator, clipboard=mock_clipboard)
        screen._surface = MagicMock()
        event = MagicMock()
        event.button = 3

        screen.on_click(event)

        screen._surface.handle_click.assert_called_once_with(event, mock_clipboard)


class TestSetupWizard:
    """Tests for SetupWizard logic (non-UI)."""

    def test_wizard_can_be_created(self):
        """SetupWizard can be instantiated with mocks."""
        mock_io = MagicMock()
        mock_io.theme = MagicMock()
        mock_validator = MagicMock()
        mock_config = MagicMock()

        wizard = SetupWizard(
            io=mock_io,
            key_validator=mock_validator,
            config_service=mock_config,
        )
        assert wizard is not None

    def test_wizard_starts_inactive(self):
        """Wizard should start inactive."""
        mock_io = MagicMock()
        mock_io.theme = MagicMock()
        mock_validator = MagicMock()
        mock_config = MagicMock()

        wizard = SetupWizard(
            io=mock_io,
            key_validator=mock_validator,
            config_service=mock_config,
        )
        assert wizard.is_active is False

    def test_wizard_start_activates(self):
        """start() should activate wizard."""
        mock_io = MagicMock()
        mock_io.theme = MagicMock()
        mock_validator = MagicMock()
        mock_config = MagicMock()
        mock_config.keys = {}

        wizard = SetupWizard(
            io=mock_io,
            key_validator=mock_validator,
            config_service=mock_config,
        )
        wizard.start(allow_cancel=True)

        assert wizard.is_active is True

    def test_wizard_has_prompt_after_start(self):
        """After start, wizard should have a prompt."""
        mock_io = MagicMock()
        mock_io.theme = MagicMock()
        mock_validator = MagicMock()
        mock_config = MagicMock()
        mock_config.keys = {}

        wizard = SetupWizard(
            io=mock_io,
            key_validator=mock_validator,
            config_service=mock_config,
        )
        wizard.start(allow_cancel=True)

        assert wizard.current_prompt is not None
        assert len(wizard.current_prompt) > 0


class TestWizardInputHandling:
    """Tests for wizard input handling."""

    def test_wizard_handles_quit_input(self):
        """Wizard should handle 'q' input."""
        mock_io = MagicMock()
        mock_io.theme = MagicMock()
        mock_validator = MagicMock()
        mock_config = MagicMock()
        mock_config.keys = {"SOME_KEY": "value"}  # Has a key so q works

        wizard = SetupWizard(
            io=mock_io,
            key_validator=mock_validator,
            config_service=mock_config,
        )
        wizard.start(allow_cancel=True)
        wizard.handle_input("q")

        # After q, wizard should be inactive
        assert wizard.is_active is False

    def test_wizard_handles_number_selection(self):
        """Wizard should handle number input for menu."""
        mock_io = MagicMock()
        mock_io.theme = MagicMock()
        mock_validator = MagicMock()
        mock_config = MagicMock()
        mock_config.keys = {}

        wizard = SetupWizard(
            io=mock_io,
            key_validator=mock_validator,
            config_service=mock_config,
        )
        wizard.start(allow_cancel=True)

        # Select first provider
        wizard.handle_input("1")

        # Should still be active (waiting for API key)
        assert wizard.is_active is True
        # Prompt should change (asking for API key now)
        assert "API" in wizard.current_prompt or "key" in wizard.current_prompt.lower()

    def test_wizard_handles_invalid_input(self):
        """Wizard should handle invalid input gracefully."""
        mock_io = MagicMock()
        mock_io.theme = MagicMock()
        mock_validator = MagicMock()
        mock_config = MagicMock()
        mock_config.keys = {}

        wizard = SetupWizard(
            io=mock_io,
            key_validator=mock_validator,
            config_service=mock_config,
        )
        wizard.start(allow_cancel=True)

        # Invalid input
        wizard.handle_input("xyz")

        # Should still be active
        assert wizard.is_active is True


class TestWizardScreenIntegration:
    """Integration tests for wizard screen with Textual."""

    @pytest.mark.asyncio
    async def test_wizard_screen_mounts(self):
        """Wizard screen should mount without errors."""
        from textual.app import App

        mock_io = MagicMock()
        mock_io.theme = MagicMock()
        mock_io.output_sink = MagicMock()
        mock_validator = MagicMock()
        mock_clipboard = MagicMock()

        class TestApp(App):
            def compose(self):
                yield SetupWizardScreen(io=mock_io, key_validator=mock_validator, clipboard=mock_clipboard)

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.screen is not None

    @pytest.mark.asyncio
    async def test_wizard_screen_responds_to_keys(self):
        """Wizard screen should respond to key presses."""
        from textual.app import App

        mock_io = MagicMock()
        mock_io.theme = MagicMock()
        mock_io.output_sink = MagicMock()
        mock_validator = MagicMock()
        mock_clipboard = MagicMock()

        class TestApp(App):
            def compose(self):
                yield SetupWizardScreen(io=mock_io, key_validator=mock_validator, clipboard=mock_clipboard)

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Press keys
            await pilot.press("1")
            await pilot.pause()

            # Should not crash
            assert app.screen is not None
